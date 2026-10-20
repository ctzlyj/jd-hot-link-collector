"""Download already-collected public material; never query prices or touch login."""
from __future__ import annotations
import concurrent.futures
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collector_guard import atomic_json, ordered_variants
from jpeg_cache import save_cached_jpeg

import os
ROOT = Path(os.environ['JD_COLLECTOR_ROOT']).resolve() if os.environ.get('JD_COLLECTOR_ROOT') else Path(r'D:\caotong.888\Desktop\京东链接搬运')
STAGE = Path(os.environ['JD_COLLECTOR_STATE_DIR']).resolve() if os.environ.get('JD_COLLECTOR_STATE_DIR') else ROOT / '.batch_work4_resume'
CACHE = STAGE / 'asset_cache'

def safe_name(text):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(text)).strip(' .') or '未命名'
    if len(text) > 100:
        text = text[:85] + '_' + hashlib.sha256(text.encode()).hexdigest()[:10]
    return text

def image_url(raw):
    if raw.startswith('//'): return 'https:' + raw
    if raw.startswith(('https://', 'http://')): return raw
    return 'https://img14.360buyimg.com/img/' + raw.lstrip('/')

def get_public(url):
    host = urlparse(url).hostname or ''
    if not (host.endswith('.360buyimg.com') or host == 'd.3.cn' or host.endswith('.300hu.com')):
        raise ValueError('Unexpected public material host')
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152 Safari/537.36', 'Referer': 'https://item.jd.com/'}, timeout=(10, 30))
    r.raise_for_status()
    return r.content

def save_jpeg(url, destination):
    return save_cached_jpeg(url, destination, CACHE, STAGE, get_public)

def detail_urls(spu):
    cache = STAGE / 'details' / f'{spu}.json'
    if cache.exists(): return json.loads(cache.read_text(encoding='utf-8'))
    raw = get_public(f'https://d.3.cn/desc/{spu}').decode('utf-8')
    sys.path.insert(0, str(Path.home()/'.joycode/skills/jd-jingmai-hot-product-mover/scripts'))
    from jd_product_mover import parse_detail_urls
    urls = parse_detail_urls(raw)
    atomic_json(cache, urls)
    return urls

def final_state(initial, detail_count, missing_count, price_complete):
    if initial != 'ASSETS_STAGING' or not detail_count or missing_count:
        return 'ASSETS_INCOMPLETE_PRICE_PENDING'
    return 'ASSETS_READY_PRICE_PENDING' if not price_complete else 'ASSETS_READY'

def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    all_data = {}
    for path in ROOT.glob('.wb_mains_*.json'):
        all_data.update(json.loads(path.read_text(encoding='utf-8')))
    status = {}
    jobs = {}
    for pid, data in all_data.items():
        if not (data.get('ok') and data.get('pp') and data.get('realSpuId') and data.get('title')): continue
        rows = ordered_variants(pid, data.get('colorSize') or [])
        folder = STAGE / 'assets' / pid
        for name in ['主图', '详情图', 'SKU图', '主图视频']: (folder/name).mkdir(parents=True, exist_ok=True)
        row_names = set()
        for row in rows:
            name = safe_name(row['spec1'] or row['sku'])
            if name in row_names: name += '_' + row['sku']
            row_names.add(name)
            if row['image']: jobs[folder/'SKU图'/(name+'.jpg')] = image_url(row['image'])
        for i, image in enumerate([x['u'] for x in data.get('carousel', []) if x.get('u')], 1):
            jobs[folder/'主图'/f'主图_{i}.jpg'] = image_url(image)
        try:
            urls = detail_urls(data['realSpuId'])
            for i, url in enumerate(urls, 1): jobs[folder/'详情图'/f'详情图_{i}.jpg'] = url
            status[pid] = {'state': 'ASSETS_STAGING', 'title': data['title'], 'skuCount': len(rows), 'detailCount': len(urls), 'priceComplete': False}
        except Exception as exc:
            status[pid] = {'state': 'DETAIL_ERROR', 'error': type(exc).__name__, 'priceComplete': False}
        atomic_json(folder/'source_metadata.json', {'sourceSku': pid, 'title': data['title'], 'variants': rows, 'mainSnapshot': data, 'notCompletePackage': True, 'priceStatus': 'PENDING_LIVE_PER_SKU'})
    grouped = {}
    for destination, url in jobs.items(): grouped.setdefault(url, []).append(destination)
    failures=[]
    def run_one(url, destinations):
        # One public download per URL; serial destinations share cache.
        for dst in destinations: save_jpeg(url, dst)
        return len(destinations)
    count=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        future_map={pool.submit(run_one,u,paths):(u,paths) for u,paths in grouped.items()}
        for future in concurrent.futures.as_completed(future_map):
            _,paths=future_map[future]
            try: count += future.result()
            except Exception as exc: failures.append({'files':[str(p.relative_to(STAGE)) for p in paths], 'error':type(exc).__name__, 'status': getattr(getattr(exc, 'response', None), 'status_code', None)})
    for pid,s in status.items():
        folder=STAGE/'assets'/pid
        s['jpegCount']=sum(1 for _ in folder.rglob('*.jpg'))
        s['expectedImages'] = sum(1 for p in jobs if folder in p.parents)
        s['missingImages'] = sum(1 for p in jobs if folder in p.parents and not p.exists())
        s['state'] = final_state(s['state'], s.get('detailCount', 0), s['missingImages'], s['priceComplete'])
        s['videoStatus'] = 'PENDING_VERIFICATION'
    report={'products':status,'files':count,'uniquePublicImages':len(grouped),'failures':failures,'businessRequests':0,'completePackages':0}
    atomic_json(STAGE/'assets_report.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__': main()

