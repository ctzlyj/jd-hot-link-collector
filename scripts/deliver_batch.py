"""Build delivery manifest and CRC-verified zip packages from VERIFIED collection results."""
from __future__ import annotations
import argparse, json, zipfile
from datetime import datetime
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font

HEADERS = ['关键词', '商品标题', '源SKU', 'SKU数', '图片数', '视频数', '用原价SKU数', '到手价区间', '文件夹']
MANIFEST_NAME = '上架清单.xlsx'
INCREMENTAL_MANIFEST_NAME = '增量上架清单.xlsx'

def load_json(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def verified_items(report, stage, root):
    items = []
    for r in report.get('results', []):
        if r.get('state') != 'VERIFIED': continue
        pid = str(r['sourceSku'])
        meta = load_json(Path(stage) / 'packages' / pid / 'package_metadata.json')
        prices = [float(v) for v in meta['arrivalPrices'].values()]
        if not prices: raise ValueError('NO_PRICE_EVIDENCE:' + pid)
        folder = Path(r['folder'])
        items.append({
            'keyword': r['keyword'], 'pid': pid, 'title': meta['title'],
            'skuCount': len(meta['variants']), 'images': r.get('images'), 'videos': r.get('videos'),
            'fallback': sum(1 for s in meta.get('priceSources', {}).values() if str(s).startswith('original_price')),
            'priceRange': (min(prices), max(prices)),
            'folder': folder, 'rel': folder.relative_to(root).as_posix(),
        })
    items.sort(key=lambda x: (x['keyword'], x['pid']))
    return items

def delivered_keys(previous_zips):
    """Keys are posix 关键词/商品标题 pairs; zip entry separators are normalized both ways."""
    delivered = set()
    for zp in previous_zips:
        with zipfile.ZipFile(zp) as zf:
            for name in zf.namelist():
                parts = name.replace('\\', '/').split('/')
                if len(parts) >= 2 and parts[0] and parts[1]:
                    delivered.add('/'.join(parts[:2]))
    return delivered

def incremental_items(items, previous_zips):
    delivered = delivered_keys(previous_zips)
    return [x for x in items if x['rel'] not in delivered]

def write_manifest(items, path, incremental=False):
    wb = Workbook(); ws = wb.active
    ws.title = '增量上架清单' if incremental else '上架清单'
    ws.append(HEADERS)
    for c in range(1, len(HEADERS) + 1): ws.cell(row=1, column=c).font = Font(bold=True)
    for x in items:
        ws.append([x['keyword'], x['title'], x['pid'], x['skuCount'], x['images'], x['videos'],
                   x['fallback'], '%.2f-%.2f' % x['priceRange'], x['rel']])
    for col, width in zip('ABCDEFGHI', (24, 60, 16, 8, 8, 8, 12, 16, 60)):
        ws.column_dimensions[col].width = width
    wb.save(str(path))

def keyword_bins(items, max_mb):
    """Group whole keywords into size-bounded bins. A single keyword larger than the
    cap (e.g. one flat-list bucket) is split at product granularity instead of failing."""
    kw_size = {}; kw_items = {}
    for x in items:
        size = sum(f.stat().st_size for f in x['folder'].rglob('*') if f.is_file())
        x['size'] = size
        kw_size[x['keyword']] = kw_size.get(x['keyword'], 0) + size
        kw_items.setdefault(x['keyword'], []).append(x)
    if not max_mb:
        return [{'keywords': list(kw_items), 'items': items}]
    cap = max_mb * 1024 * 1024
    for x in items:
        if x['size'] > cap: raise ValueError('PRODUCT_EXCEEDS_SIZE_CAP:' + x['pid'])
    oversize = {kw for kw, size in kw_size.items() if size > cap}
    units = []
    for kw in sorted(kw_size, key=lambda k: -kw_size[k]):
        if kw in oversize:
            for x in sorted(kw_items[kw], key=lambda y: -y['size']):
                units.append({'keywords': [kw], 'items': [x], 'size': x['size']})
        else:
            units.append({'keywords': [kw], 'items': kw_items[kw], 'size': kw_size[kw]})
    bins = [{'size': 0, 'keywords': [], 'items': []}]
    for unit in units:
        target = min(bins, key=lambda b: b['size'])
        if target['size'] + unit['size'] > cap:
            target = {'size': 0, 'keywords': [], 'items': []}
            bins.append(target)
        target['keywords'].extend(unit['keywords']); target['items'].extend(unit['items'])
        target['size'] += unit['size']
    return bins

def write_zip(items, zip_path, manifest_path, manifest_entry):
    count = 0
    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.write(str(manifest_path), manifest_entry); count += 1
        for x in sorted(items, key=lambda x: (x['keyword'], x['rel'])):
            for f in sorted(x['folder'].rglob('*')):
                if f.is_file():
                    zf.write(str(f), x['rel'] + '/' + f.relative_to(x['folder']).as_posix()); count += 1
    with zipfile.ZipFile(str(zip_path)) as zf:
        bad = zf.testzip()
        if bad is not None: raise ValueError('ZIP_CRC_FAILED:' + bad)
        if len(zf.namelist()) != count: raise ValueError('ZIP_ENTRY_COUNT_MISMATCH')
    return {'path': str(zip_path), 'files': count, 'sizeMb': round(zip_path.stat().st_size / 1048576, 1)}

def output_paths(root, name, count, date, incremental, part=None):
    kind = '增量' if incremental else ''
    suffix = '' if part is None else '-Part%d' % part
    manifest = root / f'{name}{kind}上架清单-{count}个-{date}.xlsx'
    archive = root / f'{name}{kind}完整商品包-{count}个-{date}{suffix}.zip'
    return manifest, archive

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', required=True)
    ap.add_argument('--state-dir')
    ap.add_argument('--name', default='本批')
    ap.add_argument('--date', default=datetime.now().strftime('%Y%m%d'))
    ap.add_argument('--max-size-mb', type=int, default=0, help='0 disables splitting')
    ap.add_argument('--previous-zip', action='append', default=[], help='exclude entries already delivered by this zip')
    ap.add_argument('--overwrite', action='store_true')
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    stage = Path(args.state_dir).expanduser().resolve() if args.state_dir else root / '.collector_state'
    report_path = stage / 'independent_validation.json'
    if not report_path.exists(): raise SystemExit('VALIDATION_REPORT_NOT_FOUND:' + str(report_path))
    items = verified_items(load_json(report_path), stage, root)
    incremental = bool(args.previous_zip)
    if incremental: items = incremental_items(items, args.previous_zip)
    if not items: raise SystemExit('NO_VERIFIED_ITEMS')
    manifest, archive = output_paths(root, args.name, len(items), args.date, incremental)
    bins = keyword_bins(items, args.max_size_mb)
    archives = [archive] if len(bins) == 1 else [
        output_paths(root, args.name, len(items), args.date, incremental, i)[1] for i in range(1, len(bins) + 1)]
    for target in [manifest] + archives:
        if target.exists() and not args.overwrite: raise SystemExit('OUTPUT_EXISTS:' + str(target))
    # Every archive carries the complete manifest, including when the batch is split.
    write_manifest(items, manifest, incremental)
    entry = INCREMENTAL_MANIFEST_NAME if incremental else MANIFEST_NAME
    outputs = [write_zip(b['items'], a, manifest, entry) for b, a in zip(bins, archives)]
    print(json.dumps({'products': len(items), 'keywords': len({x['keyword'] for x in items}),
                      'incremental': incremental, 'archives': outputs}, ensure_ascii=False))

if __name__ == '__main__': main()
