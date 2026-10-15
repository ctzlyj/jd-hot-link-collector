"""Parse a keyword-sectioned JD listing workbook into the collector manifest."""
import argparse, hashlib, json, re
from pathlib import Path
from openpyxl import load_workbook

def _pad(row):
    values = list(row)
    if len(values) < 13: values += [None] * (13 - len(values))
    return values[:13]

def detect_layout(rows):
    """Pick the standard B/C/M layout or the A-keyword/D-pid listing layout by evidence only."""
    c_pids = d_pids = links = 0
    for row in rows:
        values = _pad(row)
        if re.fullmatch(r'\d{8,}', str(values[2] or '')): c_pids += 1
        if re.fullmatch(r'\d{8,}', str(values[3] or '')): d_pids += 1
        if re.findall(r'item\.jd\.com/(\d+)\.html', str(values[12] or '')): links += 1
    return 'alternate' if c_pids == 0 and d_pids > 0 and links == 0 else 'standard'

def parse_rows(rows):
    return (parse_rows_standard if detect_layout(rows) == 'standard' else parse_rows_alternate)(rows)

def parse_rows_alternate(rows):
    """A=keyword, C=title, D=product id; header/blank rows carry no numeric D id."""
    keyword = None
    sections = {}
    shifted = []
    for n, row in enumerate(rows, 1):
        values = _pad(row)
        first = values[0]
        pid = str(values[3] or '').strip()
        if re.fullmatch(r'\d{8,}', pid):
            if keyword is None: raise ValueError('PRODUCT_BEFORE_KEYWORD_SECTION:' + str(n))
            sec = sections.setdefault(keyword, {'products': {}, 'linkIds': set()})
            item = sec['products'].setdefault(pid, {'pid': pid, 'rows': [], 'title': str(values[2] or '')})
            item['rows'].append(n)
            continue
        a_text = str(first).strip() if first is not None else ''
        if a_text and not re.fullmatch(r'\d{6,}', a_text) and not a_text.startswith(('http://', 'https://')):
            keyword = a_text
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
            keyword = str(first)
            sections.setdefault(keyword, {'products': {}, 'linkIds': set()})
            continue
        if not pid and not links: continue
        if keyword is None: raise ValueError('PRODUCT_BEFORE_KEYWORD_SECTION:' + str(n))
        sec = sections.setdefault(keyword, {'products': {}, 'linkIds': set()})
        sec['linkIds'].update(links)
        # Header/label rows carry neither a numeric product id nor a product link; skip them.
        if not links and not re.fullmatch(r'\d{8,}', pid): continue
        if not pid: continue  # link-only row: link evidence only, not a product
        if not re.fullmatch(r'\d{8,}', pid): raise ValueError('INVALID_PRODUCT_ID:' + str(n))
        item = sec['products'].setdefault(pid, {'pid': pid, 'rows': [], 'title': str(values[1] or '')})
        item['rows'].append(n)
        if links and pid not in links:
            shifted.append({'row': n, 'productId': pid, 'linkProductId': links[0]})
    for kw, sec in sections.items():
        if set(sec['products']) != sec['linkIds']: raise ValueError('IDS_AND_LINKS_DISAGREE:' + kw)
    tasks = {kw: [dict(item, row=item['rows'][0]) for item in sec['products'].values()] for kw, sec in sections.items()}
    return tasks, shifted

def parse_batch(rows):
    """Parse, then keep only the first occurrence of a product id across keyword sections."""
    layout = detect_layout(rows)
    tasks, shifted = (parse_rows_standard if layout == 'standard' else parse_rows_alternate)(rows)
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
    a = ap.parse_args()
    source = Path(a.input).expanduser().resolve()
    root = Path(a.root).expanduser().resolve()
    if not source.is_file(): raise SystemExit('INPUT_NOT_FOUND')
    if not root.is_dir(): raise SystemExit('ROOT_NOT_FOUND')
    wb = load_workbook(source, read_only=True, data_only=False)
    try: rows = list(wb.active.values)
    finally: wb.close()
    tasks, shifted, layout, duplicates, total_rows = parse_batch(rows)
    stage = root / '.collector_state'
    stage.mkdir(parents=True, exist_ok=True)
    atomic(stage / 'keyword_tasks.json', tasks)
    scope = sum(len(v) for v in tasks.values())
    audit = {'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'layout': layout, 'keywords': list(tasks), 'sourceProducts': scope, 'sourceProductRows': total_rows,
             'duplicateRows': total_rows - scope, 'crossKeywordDuplicates': duplicates,
             'shiftedLinkRows': shifted, 'rowAlignmentErrors': []}
    atomic(stage / 'input_audit.json', audit)
    print(json.dumps({k: v for k, v in audit.items() if k != 'shiftedLinkRows'}, ensure_ascii=False))

if __name__ == '__main__': main()
