"""One user-goal-confirmed continuation after a platform frequency cooldown.
Only for PAGE_FREQUENCY_LIMIT stops after a real cooldown; budgets are never reset."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from checkpoint_io import atomic_state
from driver_policy import HUMAN_REASONS, REFUSED_REASONS


FREQUENCY_REASON = 'PAGE_FREQUENCY_LIMIT'
MIN_COOLDOWN_SECONDS = int(os.environ.get('JD_PLATFORM_COOLDOWN_SECONDS', '5400'))


def result_state(driver):
    reason = driver.get('platformReason') or (driver.get('lastRunner') or {}).get('reason')
    if reason in HUMAN_REASONS:
        return {'state': 'HUMAN_REQUIRED', 'reason': reason}
    if reason in REFUSED_REASONS:
        return {'state': 'EXHAUSTED', 'reason': reason}
    return {'state': 'STOP', 'reason': driver.get('phase') or 'UNKNOWN_RESULT'}


def cooldown_elapsed(driver, now=None):
    now = now if now is not None else time.time()
    stopped_at = driver.get('updatedAt')
    if not stopped_at:
        return False, 'STOP_TIME_MISSING'
    stopped = datetime.fromisoformat(stopped_at).timestamp()
    if now - stopped < MIN_COOLDOWN_SECONDS:
        return False, 'COOLDOWN_NOT_ELAPSED'
    return True, None


def main():
    stage = Path(os.environ['JD_BATCH_STATE_DIR']).resolve()
    state_file = stage / 'keeper_state.json'
    keeper = json.loads(state_file.read_text(encoding='utf-8-sig'))
    driver = json.loads((stage / 'batch_driver_state.json').read_text(encoding='utf-8-sig'))
    if keeper.get('state') != 'EXHAUSTED' or keeper.get('childPid'):
        raise RuntimeError('RESUME_STATE_CHANGED')
    if keeper.get('reason') != FREQUENCY_REASON or driver.get('platformReason') != FREQUENCY_REASON:
        raise RuntimeError('RESUME_REASON_NOT_FREQUENCY_LIMIT')
    if driver.get('phase') != 'BLOCKED_PLATFORM':
        raise RuntimeError('DRIVER_PHASE_NOT_PLATFORM_BLOCKED')
    if (stage / 'runner.lock').exists():
        raise RuntimeError('ACTIVE_OR_UNRESOLVED_RUNNER_LOCK')
    ok, why = cooldown_elapsed(driver)
    if not ok:
        raise RuntimeError(why)
    now = lambda: datetime.now(timezone.utc).isoformat()
    keeper.update(state='PLATFORM_COOLDOWN_RESUME', reason=None, platformCooldownSeconds=MIN_COOLDOWN_SECONDS,
                  platformCooldownResumedAt=now(), nextRetryAt=None)
    atomic_state(state_file, keeper)
    try:
        with (stage / 'platform_cooldown_driver.log').open('a', encoding='utf-8') as log:
            p = subprocess.Popen([sys.executable, '-X', 'utf8', str(Path(__file__).with_name('batch_driver.py'))],
                                 stdout=log, stderr=log, cwd=str(Path(__file__).parent),
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            keeper.update(state='RUNNING', childPid=p.pid, updatedAt=now())
            atomic_state(state_file, keeper)
            code = p.wait()
        driver = json.loads((stage / 'batch_driver_state.json').read_text(encoding='utf-8-sig'))
        keeper.update(result_state(driver), childPid=None, lastExitCode=code, updatedAt=now(),
                      lastResult={k: driver.get(k) for k in ['phase', 'workPhase', 'platformReason', 'rounds', 'lastValidation']})
        atomic_state(state_file, keeper)
    except Exception as error:
        keeper.update(state='STOP', reason='RESUME_LOCAL_ERROR', errorType=type(error).__name__, updatedAt=now())
        atomic_state(state_file, keeper)
        raise


if __name__ == '__main__':
    main()
