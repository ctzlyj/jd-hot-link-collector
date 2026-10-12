import json,sys
from pathlib import Path
from collector_guard import validate_main,ordered_variants
def main():
    file=Path(sys.argv[1]);saved=json.loads(file.read_text(encoding='utf-8-sig'));data=saved['data']
    if saved.get('source') in ('live_signed_page_arrival_pending','live_native_page_arrival_pending'):
        if data.get('login') is not True or str(data.get('responseSku'))!=file.stem:raise ValueError('PARTIAL_IDENTITY_INVALID')
    else:validate_main(file.stem,data)
    rows=ordered_variants(file.stem,data.get('colorSize') or [])
    print(json.dumps(rows if '--rows' in sys.argv else [r['sku'] for r in rows],ensure_ascii=False))

if __name__=='__main__':main()

