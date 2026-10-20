"""Drive the whole authorized batch: coverage first, then every genuine SKU.
Platform refusals stop this run; completion requires independent package verification."""
import json,os,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
from driver_policy import initial_phase,stall_state,HUMAN_REASONS,REFUSED_REASONS,TRANSIENT_REASONS
from checkpoint_io import atomic_state

def task_paths():
    # Explicit task-local state directory; no generic home-directory fallback.
    stage=Path(os.environ['JD_BATCH_STATE_DIR']).resolve()
    return stage.parent,stage,Path(__file__).resolve().parents[1]

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def stamp():return datetime.now(timezone.utc).isoformat()

ROUND_COOLDOWN=int(os.environ.get('JD_BATCH_ROUND_COOLDOWN_SECONDS','120'))
INTERVAL_MS=os.environ.get('JD_BATCH_INTERVAL_MS','30000')
FALLBACK=os.environ.get('JD_BATCH_ORIGINAL_PRICE_FALLBACK','')=='1'
STAGE_EVERY=max(1,int(os.environ.get('JD_BATCH_STAGE_EVERY','1')))
def batch_scope(stage):
    import json as _json
    tasks=_json.loads((stage/'keyword_tasks.json').read_text(encoding='utf-8-sig'))
    return sum(len(v) for v in tasks.values() if isinstance(v,list))
def batch_done(report,scope):
    if not report or report.get('scope')!=scope:return False
    if report.get('complete'):return True
    counts=report.get('counts') or {}
    return set(counts)=={'VERIFIED','PRODUCT_UNAVAILABLE'}

MAX_REQUESTS=str(int(os.environ.get('JD_BATCH_MAX_REQUESTS','20')))
def main():
    root,stage,skill=task_paths();file=stage/'batch_driver_state.json'
    previous=read(file) if file.exists() else {}
    work=initial_phase(previous)
    state={'coverageVersion':2,'phase':work,'workPhase':work,'rounds':previous.get('rounds',0),'startedAt':stamp(),'childPid':None,'stall':previous.get('stall'),'stallCount':previous.get('stallCount',0)}
    def save(**fields):
        state.update(fields);state['updatedAt']=stamp();atomic_state(file,state)
    def run(command,log,extra=None):
        env=dict(os.environ);env.update(extra or {})
        with (stage/log).open('a',encoding='utf-8') as out:
            flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
            p=subprocess.Popen(command,stdout=out,stderr=out,cwd=str(skill),env=env,creationflags=flags)
            save(childPid=p.pid);code=p.wait();save(childPid=None);return code
    def local_finish():
        env={'JD_COLLECTOR_ROOT':str(root),'JD_COLLECTOR_STATE_DIR':str(stage)}
        # Independent CDN material work progresses even while SKU prices are pending.
        run([sys.executable,'-X','utf8',str(Path(__file__).with_name('stage_pending_materials.py'))],'driver_staging.log',env)
        packager=Path(__file__).with_name('package_with_fallback.py' if FALLBACK else 'package_with_artifacts.py')
        verifier=Path(__file__).with_name('verify_batch_fallback.py') if FALLBACK else skill/'verify_batch.py'
        a=run([sys.executable,'-X','utf8',str(packager)],'driver_package.log',env)
        b=run([sys.executable,'-X','utf8',str(verifier)],'driver_package.log',env)
        report=read(stage/'independent_validation.json') if b==0 and (stage/'independent_validation.json').exists() else None
        if report:save(lastValidation={k:report[k] for k in ['scope','counts','complete']})
        return a==0 and b==0,report
    save();last_started=None
    try:
        while True:
            work=state['workPhase']
            command=['node',str(skill/'collect_signed.mjs'),'--run','--root='+str(root),'--state-dir='+str(stage),'--interval-ms='+INTERVAL_MS,'--max-requests='+MAX_REQUESTS]
            if work=='HEADERS':command.append('--main-only')
            if work=='RECHECK':command.append('--recheck-prices')
            code=run(command,'driver_collect.log');runner=read(stage/'runner_state.json')
            if runner.get('startedAt')==last_started:save(phase='BLOCKED_DRIVER',reason='STALE_RUNNER_RESULT');break
            last_started=runner.get('startedAt')
            state['rounds']+=1
            save(lastRunner={k:runner.get(k) for k in ['state','reason','requests','successful','partial','products','navigations','currentProduct','currentSku','startedAt']},lastExitCode=code)
            reason=runner.get('reason');status=runner.get('state')
            if reason in HUMAN_REASONS|REFUSED_REASONS:
                save(phase='BLOCKED_PLATFORM',platformReason=reason);local_finish();break
            if reason=='ANOTHER_RUNNER_OR_UNRESOLVED_LOCK' or status=='REFUSED':save(phase='BLOCKED_LOCK');break
            if status=='HALTED':
                if reason not in TRANSIENT_REASONS:save(phase='BLOCKED_UNKNOWN',reason=reason);local_finish();break
                key=[runner.get('currentProduct'),runner.get('currentSku'),reason]
                save(**stall_state(state,key));local_finish()
                if state['stallCount']>=3:
                    stall_pid=str(runner.get('currentProduct') or '').strip()
                    if stall_pid.isdigit():
                        # Three consecutive stalls on the same product/SKU are a deterministic
                        # product failure: isolate it to the failure list and keep the batch running
                        # instead of stopping the whole authorized scope.
                        errors=stage/'errors';errors.mkdir(parents=True,exist_ok=True)
                        (errors/(stall_pid+'.json')).write_text(json.dumps({'sku':stall_pid,'reason':'PRODUCT_UNAVAILABLE','evidence':{'failureType':'STALL_'+str(runner.get('reason') or 'UNKNOWN'),'note':'auto-isolated after 3 consecutive stalls on the same product/SKU'}},ensure_ascii=False),encoding='utf-8')
                        save(stall=None,stallCount=0,isolatedProduct=stall_pid,phase=work);continue
                    save(phase='BLOCKED_STALL');break
                # Unknown responses have been aborted and read back by the collector.
                save(phase='COOLING',notBefore=time.time()+ROUND_COOLDOWN);time.sleep(ROUND_COOLDOWN);save(phase=work);continue
            save(stall=None,stallCount=0)
            if status=='COOLDOWN_REQUIRED':
                ok,report=(True,None) if state['rounds']%STAGE_EVERY else local_finish()
                if not ok:save(phase='BLOCKED_MATERIAL');break
                save(phase='COOLING',notBefore=time.time()+ROUND_COOLDOWN);time.sleep(ROUND_COOLDOWN);save(phase=work);continue
            if status=='MAIN_SCAN_COMPLETE' and work=='HEADERS':
                ok,report=local_finish()
                if not ok:save(phase='BLOCKED_MATERIAL');break
                save(phase='SWEEP',workPhase='SWEEP');continue
            if status in ['DATA_COMPLETE','DATA_COLLECTED_PRICE_PENDING']:
                ok,report=local_finish()
                if not ok:save(phase='BLOCKED_MATERIAL');break
                if batch_done(report,batch_scope(stage)):save(phase='DONE',complete=True);break
                if status=='DATA_COLLECTED_PRICE_PENDING' and work=='SWEEP' and not FALLBACK:save(phase='RECHECK',workPhase='RECHECK');continue
                save(phase='AWAITING_PRICE_DECISION' if status=='DATA_COLLECTED_PRICE_PENDING' else 'BLOCKED_MATERIAL',complete=False);break
            save(phase='BLOCKED_UNKNOWN',reason=status);local_finish();break
    except Exception as e:save(phase='BLOCKED_DRIVER',errorType=type(e).__name__)
    print(json.dumps(state,ensure_ascii=False))

if __name__=='__main__':main()
