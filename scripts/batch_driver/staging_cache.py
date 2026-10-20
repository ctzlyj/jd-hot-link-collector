"""Reusable media checkpoint fingerprint; no account fields or price substitution."""
import hashlib
import json


def media_fingerprint(main, variants, siblings):
    payload = {'title': main.get('title'), 'realSpuId': main.get('realSpuId'),
               'carousel': main.get('carousel'), 'variants': variants,
               'siblings': [{'responseSku': d.get('responseSku'),
                             'carousel': d.get('carousel')} for d in siblings]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def ready_cache_matches(folder, manifest, fingerprint):
    if (manifest.get('state') != 'MATERIALS_READY_PRICE_PENDING'
            or manifest.get('mediaFingerprint') != fingerprint or manifest.get('issues')
            or len(manifest.get('images', [])) != manifest.get('expectedImages')
            or len(manifest.get('videos', [])) != manifest.get('expectedVideos')):
        return False
    for entry in manifest.get('images', []) + manifest.get('videos', []):
        path = (folder / entry['file']).resolve()
        if not path.is_relative_to(folder.resolve()) or not path.is_file():
            return False
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get('sha256'):
            return False
    return True
