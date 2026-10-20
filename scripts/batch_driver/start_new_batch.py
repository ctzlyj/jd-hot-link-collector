"""Fresh-batch start for a new state directory; same bounded controller pattern."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from checkpoint_io import atomic_state
from driver_policy import HUMAN_REASONS, REFUSED_REASONS


def result_state(driver):
    reason = driver.get('platformReason') or (driver.get('lastRunner') or {}).get('reason')
    if reason in HUMAN_REASONS:
        return {'state': 'HUMAN_REQUIRED', 'reason': reason}
    if reason in REFUSED_REASONS:
        return {'state': 'EXHAUSTED', 'reason': reason}
    return {'state': 'STOP', 'reason': driver.get('phase') or 'UNKNOWN_RESULT'}


def main():
    stage = Path(os.environ['JD_BATCH_STATE_DIR']).resolve()
    if not (stage / 'keyword_tasks.json').is_file():
        raise RuntimeError('KEYWORD_TASKS_MISSING')
    if not (stage / 'browser_context.json').is_file():
        raise RuntimeError('BROWSER_CONTEXT_MISSING')
    if (stage / 'batch_driver_state.json').exists():
        raise RuntimeError('BATCH_ALREADY_STARTED')
    if (stage / 'runner.lock').exists():
        raise RuntimeError('ACTIVE_OR_UNRESOLVED_RUNNER_LOCK')
    now = lambda: datetime.now(timezone.utc).isoformat()
    keeper = {'startedAt': now(), 'attempts': 0, 'state': 'FRESH_START', 'childPid': None}
    atomic_state(stage / 'keeper_state.json', keeper)
    try:
        with (stage / 'new_batch_driver.log').open('a', encoding='utf-8') as log:
            p = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__).with_name('batch_driver.py'))],
                                 stdout=log, stderr=log, cwd=str(Path(__file__).parent),
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            keeper.update(state='RUNNING', childPid=p.pid, updatedAt=now())
            atomic_state(stage / 'keeper_state.json', keeper)
            code = p.wait()
        driver = json.loads((stage / 'batch_driver_state.json').read_text(encoding='utf-8-sig'))
        keeper.update(result_state(driver), childPid=None, lastExitCode=code, updatedAt=now(),
                      lastResult={k: driver.get(k) for k in ['phase', 'workPhase', 'platformReason', 'rounds', 'lastValidation']})
        atomic_state(stage / 'keeper_state.json', keeper)
    except Exception as error:
        keeper.update(state='STOP', reason='START_LOCAL_ERROR', errorType=type(error).__name__, updatedAt=now())
        atomic_state(stage / 'keeper_state.json', keeper)
        raise


if __name__ == '__main__':
    main()
