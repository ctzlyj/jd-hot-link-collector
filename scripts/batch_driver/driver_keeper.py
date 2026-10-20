"""Finite passive cooldown and continuation. Never retries login/verification."""
import os,json,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
from driver_policy import recovery_decision
from checkpoint_io import atomic_state

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def stamp():return datetime.now(timezone.utc).isoformat()

def main():
    stage=Path(os.environ['JD_BATCH_STATE_DIR']).resolve()
    file=stage/'keeper_state.json';driver=Path(__file__).with_name('batch_driver.py')
    keeper=read(file) if file.exists() else {'attempts':0}
    keeper.update(resumedAt=stamp(),state='STARTING',childPid=None)
    def save(**fields):
        keeper.update(fields,updatedAt=stamp());atomic_state(file,keeper)
    # Preserve the previously promised earliest recovery time after replacing the idle loop.
    deadline=0
    if keeper.get('nextRetryAt'):
        try:deadline=datetime.fromisoformat(keeper['nextRetryAt']).timestamp()
        except ValueError:pass
    while True:
        previous=read(stage/'batch_driver_state.json') if (stage/'batch_driver_state.json').exists() else {}
        policy=recovery_decision(previous,keeper,time.time())
        if policy['action']!='WAIT_AND_RESUME':save(state=policy['action'],reason=policy.get('reason'));break
        not_before=deadline or policy['notBefore'];deadline=0
        save(state='WAITING',nextRetryAt=datetime.fromtimestamp(not_before,timezone.utc).isoformat(),reason=policy['reason'])
        time.sleep(max(0,not_before-time.time()))
        keeper['attempts']=int(keeper.get('attempts') or 0)+1
        with (stage/'driver_keeper.log').open('a',encoding='utf-8') as out:
            p=subprocess.Popen([sys.executable,'-X','utf8',str(driver)],stdout=out,stderr=out,cwd=str(driver.parent),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            save(state='RUNNING',childPid=p.pid);code=p.wait()
        current=read(stage/'batch_driver_state.json')
        save(childPid=None,lastExitCode=code,lastResult={k:current.get(k) for k in ['phase','workPhase','platformReason','rounds','lastValidation']})
        # Remaining retry count is deliberately not reset merely because a few requests succeeded.
    print(json.dumps(keeper,ensure_ascii=False))

if __name__=='__main__':main()
