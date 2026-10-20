"""Index prior-batch receipts so same-pid package folders can be safely rebuilt."""
import json, os
from pathlib import Path


def activate(root, stage):
    root = Path(root).resolve(); stage = Path(stage).resolve()
    prior = []
    for d in sorted(root.glob('.batch_*')):
        try:
            if d.resolve() == stage or not (d / 'receipts').is_dir():
                continue
        except OSError:
            continue
        for f in (d / 'receipts').glob('*.json'):
            try:
                r = json.loads(f.read_text(encoding='utf-8-sig'))
            except ValueError:
                continue
            if r.get('state') == 'COMPLETE' and r.get('folder') and r.get('sourceSku'):
                prior.append({'sourceSku': str(r['sourceSku']), 'folder': r['folder']})
    index = stage / 'prior_receipts.json'
    index.write_text(json.dumps(prior, ensure_ascii=False), encoding='utf-8')
    os.environ['JD_COLLECTOR_PRIOR_RECEIPTS'] = str(index)
    return len(prior)
