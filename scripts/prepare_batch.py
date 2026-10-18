"""Parse a keyword-sectioned JD listing workbook into the collector manifest."""
import argparse, hashlib, json, re
from pathlib import Path
from openpyxl import load_workbook

def _pad(row):
    values = list(row)
    if len(values) < 13: values += [None] * (13 - len(values))
    return values[:13]

def _has_keyword_rows(rows):
    for row in rows:
        values = _pad(row)
        if keyword_cell(values, 0) and not any(v not in (None, '') for v in values[1:]): return True
        if keyword_cell(values, 1) and not any(v not in (None, '') for v in values[:1] + values[2:]): return True
    return False

def detect_layout(rows):
    """Pick standard, listing, alternate or flat layouts by evidence only."""
    c_pids = d_pids = links = url_first = 0
    for row in rows:
        values = _pad(row)
        if re.fullmatch(r'\d{8,}', str(values[2] or '')): c_pids += 1
        if re.fullmatch(r'\d{8,}', str(values[3] or '')): d_pids += 1
        if re.findall(r'item\.jd\.com/(\d+)\.html', str(values[12] or '')): links += 1
        if str(values[0] or '').startswith(('http://', 'https://')): url_first += 1
    has_kw = _has_keyword_rows(rows)
    if c_pids and links and has_kw: return 'standard'
    # A-url product rows without any keyword section are a flat product list;
    # with keyword sections they are the link-less listing layout.
    if c_pids and url_first: return 'flat' if not has_kw else 'listing'
    if c_pids and links and not has_kw:
        # C-pid rows with links but no keyword structure and no A-urls stay on the
        # standard path so a missing keyword header fails loudly instead of guessing.
        return 'standard'
    # D-pid keyword-sectioned listings (shop-name or other columns may occupy M).
    if d_pids and not c_pids: return 'alternate'
    return 'standard'

HEADER_LABELS = {'主图', '标题', '商品ID', '类型', '价格', '到手价', '原价', '补贴金额', '商品标签', '评价数', '总销量', '店铺', '商品链接'}

def keyword_cell(values, col):
    cell = values[col]
    text = str(cell).strip() if cell is not None else ''
    if not text or re.fullmatch(r'\d{6,}', text) or text.startswith(('http://', 'https://')) or text in HEADER_LABELS:
        return None
    return text

def alternate_keyword_column(rows):
    """Keyword sections may live in column A or B; pick the one with more keyword-only rows."""
    a_only = b_only = 0
    for row in rows:
        values = _pad(row)
        if keyword_cell(values, 0) and not any(v not in (None, '') for v in values[1:]): a_only += 1
        if keyword_cell(values, 1) and not any(v not in (None, '') for v in values[:1] + values[2:]): b_only += 1
    return 1 if b_only > a_only else 0

def parse_rows_flat(rows, default_keyword='未分组'):
    """A=url, B=title, C=product id; links may sit in column E or M. No keyword
    sections exist, so every product joins one bucket named after the source."""
    products = {}
    shifted = []
    link_ids = set()
    for n, row in enumerate(rows, 1):
        values = _pad(row)
        pid = str(values[2] or '').strip()
        row_links = []
        for idx in (4, 12):
            if len(values) > idx:
                row_links.extend(re.findall(r'item\.jd\.com/(\d+)\.html', str(values[idx] or '')))
        link_ids.update(row_links)
        if not re.fullmatch(r'\d{8,}', pid):
            # Link-only rows: the official item link itself is the product identity.
            if row_links:
                item = products.setdefault(row_links[0], {'pid': row_links[0], 'rows': [], 'title': str(values[1] or ''), 'linkDerived': True})
                item['rows'].append(n)
            continue
        item = products.setdefault(pid, {'pid': pid, 'rows': [], 'title': str(values[1] or '')})
        item['rows'].append(n)
        if row_links and pid not in row_links:
            shifted.append({'row': n, 'productId': pid, 'linkProductId': row_links[0]})
    if link_ids - set(products): raise ValueError('IDS_AND_LINKS_DISAGREE:flat')
    tasks = {default_keyword: [dict(item, row=item['rows'][0]) for item in products.values()]}
    return tasks, shifted

def parse_rows(rows, default_keyword='未分组'):
    layout = detect_layout(rows)
    if layout == 'flat': return parse_rows_flat(rows, default_keyword)
    if layout == 'alternate': return parse_rows_alternate(rows, alternate_keyword_column(rows))
    parser = {'standard': parse_rows_standard, 'listing': parse_rows_listing}[layout]
    return parser(rows)

def parse_rows_listing(rows):
    """A=main-image url, B=title, C=product id; keyword rows carry only column A."""
    keyword = None
    sections = {}
    for n, row in enumerate(rows, 1):
        values = _pad(row)
        pid = str(values[2] or '').strip()
        if re.fullmatch(r'\d{8,}', pid):
            if keyword is None: raise ValueError('PRODUCT_BEFORE_KEYWORD_SECTION:' + str(n))
            sec = sections.setdefault(keyword, {'products': {}})
            item = sec['products'].setdefault(pid, {'pid': pid, 'rows': [], 'title': str(values[1] or '')})
            item['rows'].append(n)
            continue
        a_text = str(values[0]).strip() if values[0] is not None else ''
        rest = [v for v in values[1:] if v not in (None, '')]
        if a_text and not rest and not re.fullmatch(r'\d{6,}', a_text) and not a_text.startswith(('http://', 'https://')):
            keyword = a_text
            sections.setdefault(keyword, {'products': {}})
    tasks = {kw: [dict(item, row=item['rows'][0]) for item in sec['products'].values()]
             for kw, sec in sections.items() if sec['products']}
    return tasks, []

def parse_rows_alternate(rows, keyword_col=0):
    """Keyword sections in column A or B; products carry C=title, D=product id.
    Column A may hold an unrelated keyword index next to product rows; it is ignored
    whenever the keyword column is B, and header-label cells never start sections."""
    keyword = None
    sections = {}
    shifted = []
    for n, row in enumerate(rows, 1):
        values = _pad(row)
        pid = str(values[3] or '').strip()
        if re.fullmatch(r'\d{8,}', pid):
            if keyword is None: raise ValueError('PRODUCT_BEFORE_KEYWORD_SECTION:' + str(n))
            sec = sections.setdefault(keyword, {'products': {}, 'linkIds': set()})
            item = sec['products'].setdefault(pid, {'pid': pid, 'rows': [], 'title': str(values[2] or '')})
            item['rows'].append(n)
            continue
        kw = keyword_cell(values, keyword_col)
        if kw:
            keyword = kw
            sections.setdefault(keyword, {'products': {}, 'linkIds': set()})
    tasks = {kw: [dict(item, row=item['rows'][0]) for item in sec['products'].values()]
             for kw, sec in sections.items() if sec['products']}
    return tasks, shifted

def parse_rows_standard(rows):
    keyword = None
    sections = {}
    shifted = []
    for n, row in enumerate(rows, 1):
        values = _pad(row)
        first = values[0]
        pid = str(values[2] or '')
        links = re.findall(r'item\.jd\.com/(\d+)\.html', str(values[12] or ''))
        if first is not None and all(v is None for v in values[1:]) and not str(first).startswith(('http://', 'https://')):
            keyword = str(first).strip()
            sections.setdefault(keyword, {'products': {}, 'linkIds': set()})
            continue
        if not pid and not links: continue
        if keyword is None: raise ValueError('PRODUCT_BEFORE_KEYWORD_SECTION:' + str(n))
        sec = sections.setdefault(keyword, {'products': {}, 'linkIds': set()})
        sec['linkIds'].update(links)
        # Header/label rows carry neither a numeric product id nor a product link; skip them.
        if not links and not re.fullmatch(r'\d{8,}', pid): continue
        if not pid:
            # Link-only row: the official item link itself is the product identity.
            if links:
                item = sec['products'].setdefault(links[0], {'pid': links[0], 'rows': [], 'title': str(values[1] or ''), 'linkDerived': True})
                item['rows'].append(n)
            continue
        if not re.fullmatch(r'\d{8,}', pid): raise ValueError('INVALID_PRODUCT_ID:' + str(n))
        item = sec['products'].setdefault(pid, {'pid': pid, 'rows': [], 'title': str(values[1] or '')})
        item['rows'].append(n)
        if links and pid not in links:
            shifted.append({'row': n, 'productId': pid, 'linkProductId': links[0]})
    for kw, sec in sections.items():
        if set(sec['products']) != sec['linkIds']: raise ValueError('IDS_AND_LINKS_DISAGREE:' + kw)
    tasks = {kw: [dict(item, row=item['rows'][0]) for item in sec['products'].values()] for kw, sec in sections.items()}
    return tasks, shifted

def parse_batch(rows, default_keyword='未分组'):
    """Parse, then keep only the first occurrence of a product id across keyword sections."""
    layout = detect_layout(rows)
    if layout == 'flat':
        tasks, shifted = parse_rows_flat(rows, default_keyword)
    elif layout == 'alternate':
        tasks, shifted = parse_rows_alternate(rows, alternate_keyword_column(rows))
    else:
        parser = {'standard': parse_rows_standard, 'listing': parse_rows_listing}[layout]
        tasks, shifted = parser(rows)
    total_rows = sum(len(x['rows']) for items in tasks.values() for x in items)
    seen = {}
    duplicates = []
    for kw in list(tasks):
        kept = []
        for item in tasks[kw]:
            if item['pid'] in seen:
                duplicates.append({'productId': item['pid'], 'rows': item['rows'], 'keptKeyword': seen[item['pid']]})
            else:
                seen[item['pid']] = kw
                kept.append(item)
        if kept: tasks[kw] = kept
        else: del tasks[kw]
    return tasks, shifted, layout, duplicates, total_rows

def atomic(p, value):
    tmp = p.with_suffix(p.suffix + '.pending')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(p)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='keyword-sectioned listing .xlsx')
    ap.add_argument('--root', required=True, help='collection output root directory')
    ap.add_argument('--state-dir', help='task-local state directory (default <root>/.collector_state)')
    a = ap.parse_args()
    source = Path(a.input).expanduser().resolve()
    root = Path(a.root).expanduser().resolve()
    if not source.is_file(): raise SystemExit('INPUT_NOT_FOUND')
    if not root.is_dir(): raise SystemExit('ROOT_NOT_FOUND')
    wb = load_workbook(source, read_only=True, data_only=False)
    try: rows = list(wb.active.values)
    finally: wb.close()
    tasks, shifted, layout, duplicates, total_rows = parse_batch(rows, source.stem)
    link_derived = sum(1 for items in tasks.values() for x in items if x.get('linkDerived'))
    stage = Path(a.state_dir).expanduser().resolve() if a.state_dir else root / '.collector_state'
    stage.mkdir(parents=True, exist_ok=True)
    atomic(stage / 'keyword_tasks.json', tasks)
    scope = sum(len(v) for v in tasks.values())
    audit = {'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'layout': layout, 'keywords': list(tasks), 'sourceProducts': scope, 'sourceProductRows': total_rows,
             'duplicateRows': total_rows - scope, 'crossKeywordDuplicates': duplicates,
             'linkDerivedProducts': link_derived,
             'shiftedLinkRows': shifted, 'rowAlignmentErrors': []}
    atomic(stage / 'input_audit.json', audit)
    print(json.dumps({k: v for k, v in audit.items() if k != 'shiftedLinkRows'}, ensure_ascii=False))

if __name__ == '__main__': main()
