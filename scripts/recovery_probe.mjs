import fs from 'node:fs';import {startExpression,readExpression,pageStateExpression,abortExpression} from './browser_worker.mjs';
import {pathToFileURL} from 'node:url';
import {taskContext} from './task_context.mjs';
import path from 'node:path';
import {parseOptions} from './collection_policy.mjs';
const decode=v=>typeof v==='string'?JSON.parse(v):v;
const root=parseOptions(process.argv.slice(2)).root;
const stage=path.join(root,'.collector_state');
const output=path.join(stage,'recovery_status.json');
const clock=path.join(stage,'request_clock.json');
const {session,tab,idleTimeout,probeSku,wcli}=taskContext(stage);
process.argv[1]=wcli.main;await import(pathToFileURL(wcli.preload).href);const {Page}=await import(pathToFileURL(wcli.page).href);const p=new Page(session,idleTimeout,undefined,'background');p.setActivePage(tab);
let result;
try{
 const st=decode(await p.evaluate(pageStateExpression()));
 if(st.isFrequencyPage)result={ok:false,reason:'PAGE_FREQUENCY_LIMIT'};
 else if(st.isChallenge)result={ok:false,reason:'VERIFICATION_REQUIRED'};
 else if(st.pending)result={ok:false,reason:'PREVIOUS_REQUEST_STILL_PENDING'};
 else if(!st.isTaskItem)result={ok:false,reason:'TASK_ITEM_PAGE_REQUIRED'};
 else{
  const start=decode(await p.evaluate(startExpression(probeSku)));
  if(!start.ok)result=start;
  else{
   const deadline=Date.now()+25000;
   while(Date.now()<deadline){await new Promise(r=>setTimeout(r,2500));const j=decode(await p.evaluate(readExpression));if(j?.phase==='DONE'){result={ok:j.ok===true,reason:j.reason||null,sku:j.sku,price:j.data?.pp,retryAfter:j.retryAfter||null};fs.writeFileSync(clock+'.pending',JSON.stringify({finishedAt:Date.now()}));fs.renameSync(clock+'.pending',clock);break}}
   if(!result){await p.evaluate(abortExpression);result={ok:false,reason:'REQUEST_RESULT_UNKNOWN'}}
  }
 }
}catch(e){result={ok:false,reason:/stale page identity|Page not found/.test(String(e.message))?'STALE_TASK_PAGE':'LOCAL_OR_TRANSPORT_ERROR'}}
result.checkedAt=new Date().toISOString();fs.writeFileSync(output+'.pending',JSON.stringify(result,null,2));fs.renameSync(output+'.pending',output);console.log(JSON.stringify(result));
