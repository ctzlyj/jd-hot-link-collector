"""Bounded local checkpoint replacement; never replay a browser/API operation."""
import json
import time


def atomic_state(path, value, sleep=time.sleep):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.json.pending')
    pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    for attempt in range(8):
        try:
            pending.replace(path)
            return
        except PermissionError:
            if attempt == 7:
                raise
            sleep(min(0.025 * (2 ** attempt), 0.2))
