"""Bounded self-resume for the click-driven collector after platform throttling.
Single-tab probe per cooldown; never bypasses verification or login gates."""
import argparse,json,time,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
from collector_guard import atomic_json
DIR=Path(__file__).parent
COOLDOWNS=[3600,5400,7200,10800,14400]
MAX_ATTEMPTS=5
HUMAN_STOP={'VERIFICATION_REQUIRED','LOGIN_REQUIRED','LOGIN_STATE_UNKNOWN'}

def stamp():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--root',required=True)
 a=ap.parse_args()
 root=Path(a.root).expanduser().resolve()
 stage=root/'.collector_state'
 state={'state':'WAITING','startedAt':stamp(),'attempts':0,'reason':'POST_VERIFICATION_PROBATION','notBefore':time.time()+COOLDOWNS[0]}
 def save(**f):
  state.update(f);state['updatedAt']=stamp();atomic_json(stage/'click_supervisor_state.json',state)
 def run(command,log):
  with (stage/log).open('a',encoding='utf-8') as out:
   return subprocess.run(command,stdout=out,stderr=out,cwd=str(DIR)).returncode
 save()
 while True:
  time.sleep(max(0,state['notBefore']-time.time()))
  save(state='PROBING')
  run(['node',str(DIR/'click_probe.mjs'),'--root='+str(root)],'click_supervisor_probe.log')
  probe=read(stage/'click_probe_status.json')
  save(lastProbe=probe)
  if probe['ok']:
   save(state='COLLECTING',attempts=0)
   run(['node',str(DIR/'click_collector.mjs'),'--root='+str(root)],'click_supervisor_collector.log')
   run([sys.executable,'-X','utf8',str(DIR/'package_live.py'),'--root='+str(root)],'click_supervisor_packages.log')
   run([sys.executable,'-X','utf8',str(DIR/'verify_batch.py'),'--root='+str(root)],'click_supervisor_validation.log')
   current=read(stage/'runner_state.json')
   if current['state']=='DATA_COLLECTION_SWEEP_DONE':
    report=read(stage/'independent_validation.json')
    save(state='FINISHED_SCOPE_CHECK',complete=report['complete'],counts=report['counts']);break
   reason=current.get('reason') or current['state']
  else:
   reason=probe.get('reason')
  if reason in HUMAN_STOP or 'VERIFICATION' in str(reason):save(state='STOPPED_HUMAN_REQUIRED',reason=reason);break
  if state['attempts']+1>=MAX_ATTEMPTS:save(state='STOPPED_EXHAUSTED',reason=reason);break
  state['attempts']+=1
  save(reason=reason,notBefore=time.time()+COOLDOWNS[min(state['attempts'],len(COOLDOWNS)-1)],state='WAITING')

if __name__=='__main__':main()
