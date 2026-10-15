"""Read-only pending-state classification from trusted per-SKU checkpoints."""
import json
from collector_guard import ordered_variants, positive_price


def _read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return {}


def _snapshot(stage, sku, price_required=False):
    sources = {'live_signed_page', 'live_native_page'}
    folders = ['data']
    if not price_required:
        sources |= {'live_signed_page_arrival_pending', 'live_native_page_arrival_pending'}
        folders.append('partial_data')
    for folder in folders:
        saved = _read(stage / folder / (sku + '.json'))
        d = saved.get('data') or {}
        if (saved.get('source') in sources and d.get('ok') is True
                and d.get('login') is True and d.get('responseSku') == sku
                and d.get('title') and d.get('realSpuId')
                and any(c.get('u') for c in d.get('carousel') or [])
                and (not price_required or positive_price(d.get('pp')))):
            return d
    return None


def pending_checkpoint_status(stage, sku):
    """A known matrix lacking any price is distinct from an unseen product."""
    sku = str(sku)
    error = _read(stage / 'errors' / (sku + '.json'))
    if error.get('reason') == 'PRODUCT_UNAVAILABLE':
        return {'state': 'PRODUCT_UNAVAILABLE', 'skuMatrixKnown': False}
    main = _snapshot(stage, sku)
    if main is None:
        return {'state': 'MAIN_PENDING', 'skuMatrixKnown': False}
    try:
        rows = ordered_variants(sku, main.get('colorSize') or [])
    except (RuntimeError, TypeError, ValueError, KeyError):
        return {'state': 'CHECKPOINT_INVALID', 'skuMatrixKnown': False}
    missing = [r['sku'] for r in rows if _snapshot(stage, r['sku'], True) is None]
    return {'state': 'PRICE_PENDING' if missing else 'PACKAGING_PENDING',
            'skuMatrixKnown': True, 'knownSkuCount': len(rows),
            'missingPriceSkus': missing}
