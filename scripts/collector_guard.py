"""Task-local validation and durable checkpoints. No credentials or price guessing."""
from __future__ import annotations
import itertools
import json
import re
from datetime import datetime, timezone
from pathlib import Path

class CollectionError(RuntimeError):
    pass

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.pending')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    pending.replace(path)

def positive_price(value):
    return isinstance(value, (int, float, str)) and bool(re.fullmatch(r'\d+(?:\.\d+)?', str(value))) and float(value) > 0

def signed_response_projection(raw):
    car = (raw.get('mainImageVO') or {}).get('carouselArea') or []
    return {
        'ok': True,
        'login': raw.get('isLogin') is True,
        'responseSku': str((raw.get('pageConfigVO') or {}).get('skuid') or ''),
        'title': (raw.get('skuHeadVO') or {}).get('skuTitle') or '',
        'p': (raw.get('price') or {}).get('p'),
        'pp': (raw.get('bestPromotion') or {}).get('purchasePrice'),
        'realSpuId': str((raw.get('wareInfoReadMap') or {}).get('realSpuId') or ''),
        'crumbs': [{'text': x.get('text', '')} for x in (raw.get('crumbInfoVO') or {}).get('crumbs', [])],
        'attrs': [{'labelName': x.get('labelName', ''), 'labelValue': x.get('labelValue', '')} for x in (raw.get('productAttributeVO') or {}).get('attributes', [])],
        'colorSize': [{'dim': d.get('dim'), 'buttons': [{'no': b.get('no'), 'text': b.get('text') or '', 'skuId': b.get('skuId'), 'skuList': b.get('skuList') or [], 'fullImageUrl': b.get('fullImageUrl') or ''} for b in d.get('buttons') or []]} for d in (raw.get('colorSizeVO') or {}).get('colorSizeList') or []],
        'carousel': [{'u': x.get('imageUrl'), 'v': [{'p': v.get('playUrl'), 'c': v.get('cover')} for v in x.get('videos', [])]} for x in car],
    }

def validate_main(sku, data):
    if not data.get('ok'):
        raise CollectionError('INVALID_RESPONSE')
    if data.get('login') is not True:
        raise CollectionError('LOGIN_REQUIRED')
    if not data.get('responseSku'):
        raise CollectionError('SKU_ID_MISSING')
    if str(data['responseSku']) != str(sku):
        raise CollectionError('SKU_ID_MISMATCH')
    if not data.get('title'):
        raise CollectionError('TITLE_MISSING')
    if not positive_price(data.get('pp')):
        raise CollectionError('ARRIVAL_PRICE_MISSING')
    if not data.get('realSpuId'):
        raise CollectionError('DETAIL_ID_MISSING')
    if not any(x.get('u') for x in data.get('carousel', [])):
        raise CollectionError('MAIN_IMAGES_MISSING')
    ordered_variants(str(sku), data.get('colorSize') or [])
    return data

def ordered_variants(input_sku, dimensions):
    """Intersect explicit real SKU groups, never invent a SKU Cartesian product."""
    dims = sorted(dimensions, key=lambda x: int(x.get('dim') or 0))
    if not dims:
        return [{'sku': str(input_sku), 'spec1': '', 'spec2': '', 'image': ''}]
    if len(dims) > 2:
        raise CollectionError('TOO_MANY_SALE_DIMENSIONS')
    sorted_buttons = []
    for dim in dims:
        buttons = dim.get('buttons') or []
        if not buttons:
            raise CollectionError('EMPTY_SKU_DIMENSION')
        for b in buttons:
            if not str(b.get('no', '')).isdigit():
                raise CollectionError('FRONTEND_ORDER_MISSING')
        sorted_buttons.append(sorted(buttons, key=lambda b: int(b['no'])))
    result, seen = [], set()
    for group in itertools.product(*sorted_buttons):
        sets = [set(str(x) for x in (b.get('skuList') or [b.get('skuId')]) if x) for b in group]
        matching = set.intersection(*sets)
        if not matching:
            continue
        if len(matching) != 1:
            raise CollectionError('AMBIGUOUS_SKU_COMBINATION')
        sku = next(iter(matching))
        if sku in seen:
            raise CollectionError('DUPLICATE_SKU_COMBINATION')
        seen.add(sku)
        result.append({'sku': sku, 'spec1': str(group[0].get('text') or ''),
                       'spec2': str(group[1].get('text') or '') if len(group) > 1 else '',
                       'image': next((str(b['fullImageUrl']) for b in group if b.get('fullImageUrl')), '')})
    expected = set().union(*(set(str(x) for x in (b.get('skuList') or [b.get('skuId')]) if x) for b in sorted_buttons[0]))
    if seen != expected or str(input_sku) not in seen:
        raise CollectionError('INCOMPLETE_SKU_MATRIX')
    return result

class Checkpoint:
    def __init__(self, root):
        self.root = Path(root)
        self.data_root = self.root / 'data'
        self.state_path = self.root / 'checkpoint.json'
    def load_state(self):
        return json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {'state': 'NEW', 'successful': []}
    def has(self, sku):
        p = self.data_root / f'{sku}.json'
        if not p.exists():
            return False
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            validate_main(sku, d['data'])
            return d.get('source') == 'live_signed_page'
        except (ValueError, KeyError, CollectionError):
            return False
    def read(self, sku):
        return json.loads((self.data_root / f'{sku}.json').read_text(encoding='utf-8'))['data']
    def put(self, sku, data):
        validate_main(sku, data)
        atomic_json(self.data_root / f'{sku}.json', {'collectedAt': stamp(), 'source': 'live_signed_page', 'data': data})
        state = self.load_state()
        state.update(state='RUNNING', updatedAt=stamp())
        state['successful'] = sorted(set(state.get('successful', []) + [str(sku)]))
        atomic_json(self.state_path, state)
    def halt(self, reason):
        state = self.load_state()
        state.update(state='HALTED', reason=reason, updatedAt=stamp())
        atomic_json(self.state_path, state)

