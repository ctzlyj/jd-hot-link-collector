"""User-authorized original-price fallback resolver (2026-10-15).
Pure helper: no package_live import, so callers control which package_live is patched."""
import json
import re

PENDING_SOURCES = ('live_signed_page_arrival_pending', 'live_native_page_arrival_pending')
FALLBACK_PRICE_SOURCE = 'original_price_user_authorized_20261015'


def attach_fallback(package_live):
    """Patch the given (skill) package_live module with the fallback resolver."""
    original_live_data = package_live.live_data

    def live_data_with_fallback(sku):
        value = original_live_data(sku)
        if value is not None:
            return value
        partial = package_live.STAGE / 'partial_data' / f'{sku}.json'
        if not partial.exists():
            return None
        try:
            saved = json.loads(partial.read_text(encoding='utf-8-sig'))
            data = saved.get('data') or {}
            price = data.get('p')
            if (saved.get('source') in PENDING_SOURCES
                    and data.get('login') is True and str(data.get('responseSku')) == str(sku)
                    and data.get('title') and data.get('realSpuId')
                    and re.fullmatch(r'\d+(?:\.\d+)?', str(price)) and float(price) > 0):
                fallback = dict(data)
                fallback['pp'] = price
                fallback['priceSource'] = FALLBACK_PRICE_SOURCE
                fallback['originalPriceFallback'] = True
                return fallback
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return None

    package_live.live_data = live_data_with_fallback
    return live_data_with_fallback
