"""Bounded local continuation for one authorized batch. No account/IP changes or challenge handling."""
import json,time,subprocess,sys,os
from pathlib import Path
from datetime import datetime,timezone
from collector_guard import atomic_json
from resume_policy import next_action
from package_live import ROOT,STAGE
DIR=Path(__file__).parent
STATE=STAGE/'supervisor_state.json'

def stamp():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(**fields):
 state.update(fields);state['updatedAt']=stamp();atomic_json(STATE,state)
def run(command,log):
 with (STAGE/log).open('a',encoding='utf-8') as out:
  proc=subprocess.Popen(command,stdout=out,stderr=out,cwd=str(DIR),creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
  save(childPid=proc.pid)
  code=proc.wait();save(childPid=None,lastExitCode=code);return code
def local_finish():
 if run([sys.executable,'-X','utf8',str(DIR/'package_live.py')],'supervisor_packages.log')!=0:return False
 return run([sys.executable,'-X','utf8',str(DIR/'verify_batch.py')],'supervisor_validation.log')==0

previous=read(STATE) if STATE.exists() else {}
state={'state':'STARTING','startedAt':stamp(),'refusalAttempts':previous.get('refusalAttempts',0),'runs':previous.get('runs',0),'childPid':None,'phase':previous.get('phase','COLLECT')}
save()
current=read(STAGE/'runner_state.json');reason=current.get('reason') or current['state']
last=datetime.fromisoformat(current['updatedAt']).timestamp()
probe=read(STAGE/'recovery_status.json') if (STAGE/'recovery_status.json').exists() else {}
if probe.get('checkedAt'):last=max(datetime.fromisoformat(current['updatedAt']).timestamp(),datetime.fromisoformat(probe['checkedAt']).timestamp())
deadline=datetime.fromisoformat(previous['notBefore']).timestamp() if previous.get('state')=='WAITING' and previous.get('notBefore') else 0
retry_after=probe.get('retryAfter') or current.get('retryAfter')
while True:
 policy=next_action(reason,state['refusalAttempts'],last,retry_after)
 if policy['action'] not in ['WAIT_AND_PROBE','WAIT_AND_RESUME']:
  save(state='STOPPED',reason=reason,stopAction=policy['action']);local_finish();break
 not_before=max(policy['notBefore'],deadline);deadline=0
 wait=max(0,not_before-time.time());save(state='WAITING',reason=reason,notBefore=datetime.fromtimestamp(not_before,timezone.utc).isoformat(),secondsToWait=round(wait))
 # Sleep does not touch browser, price interface or working tabs.
 if wait:time.sleep(wait)
 if policy['action']=='WAIT_AND_PROBE':
  save(state='PROBING');code=run(['node',str(DIR/'recovery_probe.mjs'),'--root',str(ROOT)],'supervisor_probe.log')
  if code!=0 or not (STAGE/'recovery_status.json').exists():save(state='STOPPED',reason='PROBE_PROCESS_FAILED');break
  probe=read(STAGE/'recovery_status.json')
  if not probe['ok']:
   reason=probe.get('reason') or 'LOCAL_OR_TRANSPORT_ERROR';last=time.time();retry_after=probe.get('retryAfter')
   if reason in ['HTTP_403_REFUSED','HTTP_429_RATE_LIMIT']:state['refusalAttempts']+=1
   save(lastProbe=probe);continue
  state['refusalAttempts']=0;save(lastProbe=probe)
 save(state='COLLECTING',runs=state['runs']+1)
 command=['node',str(DIR/'collect_signed.mjs'),'--run','--interval-ms=30000','--max-requests=20','--root',str(ROOT)]
 if state['phase']=='PRICE_RECHECK':command.append('--recheck-prices')
 code=run(command,'supervisor_collector.log')
 if not local_finish():save(state='STOPPED',reason='LOCAL_FINALIZATION_FAILED');break
 current=read(STAGE/'runner_state.json');last=time.time();retry_after=current.get('retryAfter')
 if code!=0 and current['state']!='HALTED':save(state='STOPPED',reason='COLLECTOR_PROCESS_FAILED');break
 if current['state'] in ['DATA_COMPLETE','DATA_COLLECTED_PRICE_PENDING']:
  report=read(STAGE/'independent_validation.json')
  if current['state']=='DATA_COLLECTED_PRICE_PENDING' and state['phase']=='COLLECT':
   save(phase='PRICE_RECHECK',lastCollector=current,counts=report['counts']);reason='COOLDOWN_REQUIRED';continue
  save(state='FINISHED_SCOPE_CHECK',complete=report['complete'],counts=report['counts'],reason=current['state']);break
 reason=current.get('reason') or current['state']
 if reason in ['HTTP_403_REFUSED','HTTP_429_RATE_LIMIT']:state['refusalAttempts']+=1
 save(lastCollector=current)
