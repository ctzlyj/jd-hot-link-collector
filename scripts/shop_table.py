"""Read shop ids from an operations workbook and write SKU counts back. No network."""
from __future__ import annotations
import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from openpyxl import load_workbook
from prepare_batch import HEADER_LABELS

SHOP_HEADER_LABELS = {'店铺', '店铺ID', '店铺id', '店铺Id', '店铺链接', '店铺主页'}
SHOP_URL_PATTERNS = (
    re.compile(r'mall\.jd\.com/index-(\d{5,})\.html', re.I),
    re.compile(r'shop\.m\.jd\.com/\?[^#]*?shopId=(\d{5,})', re.I),
    re.compile(r'shop\.jd\.com/(\d{5,})', re.I),
)
RESULT_HEADERS = ('在售SKU数', '在售商品数', '待补商品数', '店铺采集时间')


def normalize_shop_cell(value):
    """A shop id, or the id inside a shop homepage URL; shop names stay unresolved."""
    text = str(value).strip() if value is not None else ''
    if not text:
        return None
    if re.fullmatch(r'\d{5,}', text):
        return text
    for pattern in SHOP_URL_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(1)
    return None


def shop_column_index(rows):
    for row in rows[:8]:
        for idx, cell in enumerate(row):
            if str(cell).strip() in SHOP_HEADER_LABELS:
                return idx
    return None


def _is_header_row(row):
    values = {str(c).strip() for c in row if c is not None}
    return bool(values & HEADER_LABELS)


def extract_shops(rows):
    """Distinct shop ids from the shop column (or URL cells when no header exists).

    Pure numbers or shop URLs resolve; plain shop names are audited, never guessed.
    """
    idx = shop_column_index(rows)
    shops, audit, seen = [], [], {}

    def record(row, value):
        sid = normalize_shop_cell(value)
        text = str(value).strip()
        if sid is None:
            if text:
                audit.append({'row': row, 'value': text[:80], 'reason': 'SHOP_ID_UNRESOLVED'})
            return
        if sid in seen:
            audit.append({'row': row, 'value': text[:80], 'reason': 'DUPLICATE_SHOP',
                          'shopId': sid, 'firstRow': seen[sid]})
            return
        seen[sid] = row
        shops.append({'shopId': sid, 'row': row})

    if idx is None:
        # No shop header: only unambiguous shop homepage URLs are trusted.
        for ri, row in enumerate(rows, 1):
            for cell in row:
                text = str(cell).strip() if cell is not None else ''
                if text and any(p.search(text) for p in SHOP_URL_PATTERNS):
                    record(ri, cell)
    else:
        for ri, row in enumerate(rows, 1):
            if _is_header_row(row):
                continue
            record(ri, row[idx] if idx < len(row) else None)
    return {'shops': shops, 'audit': audit, 'columnIndex': idx}


def read_workbook_rows(path):
    wb = load_workbook(path, read_only=True, data_only=False)
    try:
        return [list(r) for r in wb.active.values]
    finally:
        wb.close()


def extract_shops_from_workbook(path):
    return extract_shops(read_workbook_rows(path))


def write_back(source, output, results, collected_at=''):
    """Append per-shop SKU count columns to a copy of the operations workbook.

    `results` maps shopId to the counter record (skuCount/productCount/missing).
    The source workbook is never modified; shops without a collected record keep
    blank cells so missing data stays visible instead of being invented.
    """
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError('WRITE_BACK_OUTPUT_MUST_BE_A_COPY')
    wb = load_workbook(source)
    ws = wb.active
    rows = list(ws.values)
    idx = shop_column_index(rows)
    if idx is None:
        raise ValueError('SHOP_COLUMN_NOT_FOUND')
    header_row = next(ri for ri, row in enumerate(rows, 1)
                      if idx < len(row) and str(row[idx]).strip() in SHOP_HEADER_LABELS)
    start_col = ws.max_column + 1
    for offset, label in enumerate(RESULT_HEADERS):
        ws.cell(header_row, start_col + offset, label)
    matched = written = 0
    for ri in range(header_row + 1, ws.max_row + 1):
        sid = normalize_shop_cell(ws.cell(ri, idx + 1).value)
        if sid is None:
            continue
        matched += 1
        rec = results.get(sid)
        if not isinstance(rec, dict):
            continue
        ws.cell(ri, start_col, rec.get('skuCount'))
        ws.cell(ri, start_col + 1, rec.get('productCount'))
        ws.cell(ri, start_col + 2, len(rec.get('missing') or []))
        ws.cell(ri, start_col + 3, collected_at)
        written += 1
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix='.xlsx')
    os.close(fd)
    staged = Path(temporary)
    try:
        wb.save(staged)
        wb.close()
        check = load_workbook(staged, read_only=True, data_only=False)
        try:
            check_rows = list(check.active.values)
        finally:
            check.close()
        observed = check_rows[header_row - 1][start_col - 1:start_col - 1 + len(RESULT_HEADERS)]
        if tuple(observed) != RESULT_HEADERS or len(check_rows) != len(rows):
            raise ValueError('WRITE_BACK_READBACK_MISMATCH')
        os.replace(staged, output)
    finally:
        staged.unlink(missing_ok=True)
    return {'output': str(output), 'shopsMatched': matched, 'shopsWritten': written,
            'columns': list(RESULT_HEADERS)}

def main():
    parser = argparse.ArgumentParser(description="Return verified shop identifiers or append supplied counts to a workbook copy.")
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--root', type=Path, help="output directory")
    parser.add_argument('--results', type=Path, help="authorized shop counter JSON with a shops mapping")
    parser.add_argument('--result-xlsx', type=Path)
    parser.add_argument('--collected-at', default='', help="original collection time when recorded")
    args = parser.parse_args()
    table = extract_shops_from_workbook(args.input)
    if args.results is None:
        if args.result_xlsx:
            parser.error('--result-xlsx requires --results')
        print(json.dumps(table, ensure_ascii=False))
        return
    data = json.loads(args.results.read_text(encoding='utf-8-sig'))
    records = data['shops']
    if not isinstance(records, dict):
        raise ValueError('SHOP_RESULTS_INVALID')
    selected = {s['shopId'] for s in table['shops']}
    known = {}
    for sid in selected & records.keys():
        rec = records[sid]
        if not isinstance(rec, dict) or str(rec.get('shopId', sid)) != sid:
            raise ValueError('SHOP_RESULT_ID_MISMATCH')
        if rec.get('done') is False or any(type(rec.get(k)) is not int or rec[k] < 0 for k in ('skuCount', 'productCount')):
            continue
        if not isinstance(rec.get('missing'), list):
            continue
        known[sid] = rec
    output = args.result_xlsx or (args.root or args.input.parent) / (args.input.stem + '_SKU结果.xlsx')
    result = write_back(args.input, output, known, args.collected_at)
    pending = [sid for sid in sorted(selected) if sid not in known or known[sid]['missing']]
    print(json.dumps({**result, 'pendingShopIds': pending, 'audit': table['audit']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
