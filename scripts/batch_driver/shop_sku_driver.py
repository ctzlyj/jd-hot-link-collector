"""Drive shop-SKU counting for an operations table through shop_sku_count.mjs."""
import argparse, json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from checkpoint_io import atomic_state
from shop_table import extract_shops_from_workbook, write_back

# Counter failures carrying these markers are platform stops, not chunk bugs.
PLATFORM_MARKERS = ('VERIFICATION_REQUIRED', 'LOGIN_REQUIRED', 'LOGIN_STATE_UNKNOWN',
                    'HTTP_403_REFUSED', 'HTTP_429_RATE_LIMIT', 'PAGE_FREQUENCY_LIMIT')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def completed_shops(output):
    """Shop ids already fully counted in an existing counter output (resume)."""
    try:
        data = read(output)
    except (OSError, ValueError):
        return set()
    done = set()
    for sid, rec in (data.get('shops') or {}).items():
        if isinstance(rec, dict) and rec.get('done') and not rec.get('missing'):
            done.add(str(sid))
    return done


def run_chunks(script, stage, output, pending, args, save):
    """Run the counter per shop chunk; completed shops are skipped on resume."""
    failures = 0
    queue = list(pending)
    attempt = 0
    while queue:
        chunk = queue[:args.chunk_shops]
        command = ['node', str(script), '--state-dir', str(stage), '--shops', ','.join(chunk),
                   '--output', str(output)]
        attempt += 1
        with (stage / 'shop_sku_driver.log').open('a', encoding='utf-8') as log:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            proc = subprocess.run(command, cwd=str(script.parent), stdout=log,
                                  stderr=subprocess.PIPE, text=True, encoding='utf-8',
                                  errors='replace', creationflags=flags)
        error = (proc.stderr or '').strip()
        done = completed_shops(output)
        queue = [sid for sid in queue if sid not in done]
        if not queue:
            save(chunksDone=attempt, chunkFailures=failures)
            return {'state': 'DONE', 'attempts': attempt, 'failures': failures}
        platform = next((m for m in PLATFORM_MARKERS if m in error), None)
        if platform:
            save(phase='BLOCKED_PLATFORM', reason=platform, pendingShops=queue)
            return {'state': 'BLOCKED_PLATFORM', 'reason': platform, 'pendingShops': queue}
        failures += 1
        if failures >= args.max_chunk_failures:
            save(phase='BLOCKED_UNKNOWN', reason='SHOP_CHUNK_FAILED', pendingShops=queue,
                 lastError=error[-300:])
            return {'state': 'BLOCKED_UNKNOWN', 'reason': 'SHOP_CHUNK_FAILED',
                    'pendingShops': queue}
        time.sleep(max(0, args.chunk_cooldown_seconds))
    return {'state': 'DONE', 'attempts': attempt, 'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='operations xlsx with a shop column')
    parser.add_argument('--state-dir', default=os.environ.get('JD_BATCH_STATE_DIR'))
    parser.add_argument('--output', default=None, help='counter result json')
    parser.add_argument('--result-xlsx', default=None, help='result workbook copy')
    parser.add_argument('--chunk-shops', type=int, default=10)
    parser.add_argument('--max-chunk-failures', type=int, default=3)
    parser.add_argument('--chunk-cooldown-seconds', type=int, default=30)
    args = parser.parse_args()

    stage = Path(args.state_dir).resolve() if args.state_dir else None
    if not stage or not (stage / 'browser_context.json').is_file():
        raise SystemExit('STATE_DIR_WITH_BROWSER_CONTEXT_REQUIRED')
    source = Path(args.input)
    if not source.is_file():
        raise SystemExit('INPUT_NOT_FOUND')
    args.chunk_shops = max(1, args.chunk_shops)
    args.max_chunk_failures = max(1, args.max_chunk_failures)
    output = Path(args.output).resolve() if args.output else stage / 'shop_sku_count.json'
    state_file = stage / 'shop_sku_driver_state.json'
    state = {'phase': 'STARTING', 'startedAt': stamp(), 'input': str(source),
             'output': str(output), 'updatedAt': stamp()}

    def save(**fields):
        state.update(fields, updatedAt=stamp())
        atomic_state(state_file, state)

    table = extract_shops_from_workbook(source)
    all_ids = [s['shopId'] for s in table['shops']]
    if table['audit']:
        atomic_state(stage / 'shop_table_audit.json',
                     {'input': str(source), 'audit': table['audit']})
    save(phase='RUNNING', scope=len(all_ids), auditedCells=len(table['audit']))

    script = Path(__file__).resolve().parents[1] / 'shop_sku_count.mjs'
    pending = [sid for sid in all_ids if sid not in completed_shops(output)]
    result = run_chunks(script, stage, output, pending, args, save)
    if result['state'] != 'DONE':
        print(json.dumps(state, ensure_ascii=False))
        raise SystemExit(2)

    data = read(output) if output.is_file() else {'shops': {}}
    records = data.get('shops') or {}
    missing = [sid for sid in all_ids
               if not (records.get(sid) or {}).get('done') or (records.get(sid) or {}).get('missing')]
    result_xlsx = Path(args.result_xlsx) if args.result_xlsx else source.with_name(
        source.stem + '_SKU结果_' + datetime.now().strftime('%Y%m%d') + source.suffix)
    written = write_back(source, result_xlsx, records, collected_at=stamp())
    save(phase='DONE_WITH_PENDING' if missing else 'DONE', pendingShops=missing,
         resultWorkbook=written['output'], shopsWritten=written['shopsWritten'])
    print(json.dumps({'state': state['phase'], 'scope': len(all_ids), 'pendingShops': missing,
                      'resultWorkbook': written['output']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
