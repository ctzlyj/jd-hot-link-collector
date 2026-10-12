import json,sys
from pathlib import Path
from collector_guard import validate_main,ordered_variants
saved=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'));data=saved['data']
if saved.get('source') not in ('live_signed_page_arrival_pending','live_native_page_arrival_pending'):validate_main(Path(sys.argv[1]).stem,data)
print(json.dumps([r['sku'] for r in ordered_variants(Path(sys.argv[1]).stem,data.get('colorSize') or [])]))

