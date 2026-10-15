"""Public material helpers and collector root resolution; never queries prices or login."""
from __future__ import annotations
import os,sys,re,hashlib,io
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image
from collector_guard import atomic_json, ordered_variants
from jpeg_cache import save_cached_jpeg

def resolve_root():
    for arg in sys.argv[1:]:
        if arg.startswith('--root='): return Path(arg.split('=',1)[1]).expanduser().resolve()
    if '--root' in sys.argv:
        at=sys.argv.index('--root')
        if len(sys.argv)>at+1:return Path(sys.argv[at+1]).expanduser().resolve()
    env=os.environ.get('JD_COLLECTOR_ROOT')
    if env: return Path(env).expanduser().resolve()
    raise SystemExit('ROOT_REQUIRED: pass --root=<output-dir> or JD_COLLECTOR_ROOT')
ROOT = resolve_root()
STAGE = Path(os.environ['JD_COLLECTOR_STATE_DIR']).resolve() if os.environ.get('JD_COLLECTOR_STATE_DIR') else ROOT / '.collector_state'
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

def final_state(initial, detail_count, missing_count, price_complete):
    if initial != 'ASSETS_STAGING' or not detail_count or missing_count:
        return 'ASSETS_INCOMPLETE_PRICE_PENDING'
    return 'ASSETS_READY_PRICE_PENDING' if not price_complete else 'ASSETS_READY'

def save_jpeg(url, destination):
    return save_cached_jpeg(url, destination, CACHE, STAGE, get_public)
