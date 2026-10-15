"""Offline correspondence between source URL caches and delivered media."""
import hashlib
from pathlib import Path


def verify_media_evidence(folder, stage, entries):
    folder, stage = Path(folder).resolve(), Path(stage).resolve()
    expected = set()
    for entry in entries:
        destination = (folder / entry['file']).resolve()
        if not destination.is_relative_to(folder):
            raise ValueError('MEDIA_PATH_ESCAPE')
        relative = destination.relative_to(folder).as_posix()
        if relative in expected:
            raise ValueError('MEDIA_DESTINATION_COLLISION')
        expected.add(relative)
        if entry['cacheGroup'] not in {'asset_cache', 'video_cache'} or entry['suffix'] not in {'.jpg', '.mp4'}:
            raise ValueError('MEDIA_CACHE_KIND_INVALID')
        key = hashlib.sha256(entry['url'].encode()).hexdigest()
        cached = stage / entry['cacheGroup'] / (key + entry['suffix'])
        if not cached.is_file():
            raise ValueError('SOURCE_CACHE_MISSING')
        if not destination.is_file():
            raise ValueError('MEDIA_DESTINATION_MISSING')
        if hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(cached.read_bytes()).digest():
            raise ValueError('SOURCE_CONTENT_MISMATCH')
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob('*')
              if p.is_file() and p.suffix.lower() in {'.jpg', '.jpeg', '.mp4'}}
    if actual != expected:
        raise ValueError('MEDIA_FILE_SET_MISMATCH')
    return len(expected)


def expected_media_entries(main, rows, prices, detail_urls, safe_name, image_url):
    main_dir, detail_dir, sku_dir, video_dir = '\u4e3b\u56fe', '\u8be6\u60c5\u56fe', 'SKU\u56fe', '\u4e3b\u56fe\u89c6\u9891'
    entries = []
    def add(group, name, url, video=False):
        entries.append({'file': group + '/' + name, 'url': url,
                        'cacheGroup': 'video_cache' if video else 'asset_cache',
                        'suffix': '.mp4' if video else '.jpg'})
    for index, car in enumerate([c for c in main['carousel'] if c.get('u')], 1):
        add(main_dir, main_dir + '_' + str(index) + '.jpg', image_url(car['u']))
    for index, url in enumerate(detail_urls, 1):
        add(detail_dir, detail_dir + '_' + str(index) + '.jpg', url)
    names = set()
    for row in rows:
        image = row['image'] or next((c['u'] for c in prices[row['sku']]['carousel'] if c.get('u')), '')
        if not image:
            raise ValueError('SKU_IMAGE_MISSING')
        name = safe_name(' '.join(x for x in [row['spec1'], row['spec2']] if x) or row['sku'])
        if name in names:
            name += '_' + row['sku']
        names.add(name)
        add(sku_dir, name + '.jpg', image_url(image))
    videos = list(dict.fromkeys(v['p'] for d in [main, *prices.values()]
                              for c in d['carousel'] for v in c.get('v', []) if v.get('p')))
    for index, url in enumerate(videos, 1):
        add(video_dir, video_dir + '_' + str(index) + '.mp4', url, True)
    return entries
