/** Task runner: explicit run, no daemon/retry loop. Keep credential-bearing data in browser memory. */
import fs from 'node:fs';import path from 'node:path';import {fileURLToPath,pathToFileURL} from 'node:url';import {spawnSync} from 'node:child_process';
import {RateGate,validate} from './request_policy.mjs';import {pageStateExpression,startExpression,readExpression,abortExpression} from './browser_worker.mjs';
import {parseOptions,shouldRequest,unresolvedPrices,waitUntilNext,PRICE_RECHECK_VERSION} from './collection_policy.mjs';
import {taskContext} from './task_context.mjs';
const {runRequested,recheckPrices,interval,maxRequests,root}=parseOptions(process.argv.slice(2));
const dir=path.dirname(fileURLToPath(import.meta.url));
if(!fs.existsSync(root))throw Error('ROOT_NOT_FOUND');
const stage=path.join(root,'.collector_state');
const {session,tab,idleTimeout,wcli}=taskContext(stage);
function atomic(file,value){fs.mkdirSync(path.dirname(file),{recursive:true});const tmp=file+'.pending';fs.writeFileSync(tmp,JSON.stringify(value,null,2),'utf8');fs.renameSync(tmp,file)}
function json(file){return JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''))}
const decode=value=>typeof value==='string'?JSON.parse(value):value;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const stateFile=path.join(stage,'runner_state.json');
const requestClock=path.join(stage,'request_clock.json');
const finishRequest=()=>atomic(requestClock,{finishedAt:Date.now()});
const state={state:'STARTING',startedAt:new Date().toISOString(),successful:0,requests:0,navigations:0,unavailable:0,reason:null};
function checkpoint(){state.updatedAt=new Date().toISOString();atomic(stateFile,state)}
function halt(reason){state.state='HALTED';state.reason=reason;checkpoint();console.log(JSON.stringify({state:state.state,reason,successful:state.successful,requests:state.requests,navigations:state.navigations}));}
process.argv[1]=wcli.main;
await import(pathToFileURL(wcli.preload).href);
const {Page}=await import(pathToFileURL(wcli.page).href);const page=new Page(session,idleTimeout,undefined,'background');page.setActivePage(tab);
try{
 const observed=decode(await page.evaluate(pageStateExpression()));
 if(observed.isFrequencyPage){halt('PAGE_FREQUENCY_LIMIT');process.exitCode=2;}
 else if(observed.isChallenge){halt('VERIFICATION_REQUIRED');process.exitCode=2;}
 else if(!observed.isTaskItem){halt('TASK_ITEM_PAGE_REQUIRED');process.exitCode=2;}
 else if(observed.pending){halt('PREVIOUS_REQUEST_STILL_PENDING');process.exitCode=2;}
 else if(!observed.sdkReady){halt('PAGE_SDK_MISSING');process.exitCode=2;}
 else if(!runRequested){state.state='READY_NOT_RUNNING';checkpoint();console.log(JSON.stringify({state:state.state,needsExplicitRun:true}));}
 else{
  fs.mkdirSync(stage,{recursive:true});const lock=path.join(stage,'runner.lock');const fd=fs.openSync(lock,'wx');fs.writeFileSync(fd,String(process.pid));
  try{
   const tasks=json(path.join(stage,'keyword_tasks.json'));const queue=[...new Set(Object.values(tasks).flat().map(x=>String(x.pid)))];const expanded=new Set();
   const gate=new RateGate(interval);state.intervalMs=interval;state.maxRequests=maxRequests;state.priceRecheck=recheckPrices;state.state='RUNNING';checkpoint();
   for(let i=0;i<queue.length;i++){
    const sku=queue[i];const unavailable=path.join(stage,'errors',sku+'.json');if(fs.existsSync(unavailable)&&json(unavailable).reason==='PRODUCT_UNAVAILABLE'){state.unavailable++;continue;}const cache=path.join(stage,'data',sku+'.json');let data=null;let partial=false;const partialCache=path.join(stage,'partial_data',sku+'.json');if(fs.existsSync(partialCache)){data=json(partialCache).data;partial=true;}
    if(fs.existsSync(cache)){try{const saved=json(cache);validate(sku,saved.data);if(saved.source==='live_signed_page'){data=saved.data;partial=false;}}catch{}}
    const partialRecord=fs.existsSync(partialCache)?json(partialCache):null;
    if(shouldRequest({validCache:!!data&&!partial,partialCache:partialRecord,recheckPrices})){
     if(state.requests>=maxRequests){state.state='COOLDOWN_REQUIRED';checkpoint();console.log(JSON.stringify({state:state.state,requests:state.requests}));break}
     const lastFinished=fs.existsSync(requestClock)?json(requestClock).finishedAt:0;
     await sleep(Math.max(gate.wait(Date.now()),waitUntilNext(Date.now(),lastFinished,interval)));const before=decode(await page.evaluate(pageStateExpression()));
     if(before.isFrequencyPage){halt('PAGE_FREQUENCY_LIMIT');break}if(before.isChallenge){halt('VERIFICATION_REQUIRED');break}if(!before.isTaskItem||before.pending){halt('PAGE_CHANGED_OR_PENDING');break}
     gate.begin(Date.now());const started=decode(await page.evaluate(startExpression(sku)));if(!started.ok){gate.halt(started.reason);halt(started.reason);break}
     state.requests++;state.currentSku=sku;checkpoint();
     const deadline=Date.now()+25000;let result=null;
     while(Date.now()<deadline){await sleep(2500);const j=decode(await page.evaluate(readExpression));if(j?.phase==='DONE'){result=j;break}const at=decode(await page.evaluate(pageStateExpression()));if(at.isChallenge){result={ok:false,reason:'VERIFICATION_REQUIRED'};break}}
     if(!result){try{await page.evaluate(abortExpression)}catch{}gate.halt('REQUEST_RESULT_UNKNOWN');halt('REQUEST_RESULT_UNKNOWN');break}
     finishRequest();
     if(!result.ok){
      if(result.reason==='ARRIVAL_PRICE_MISSING'&&result.partialData?.login===true&&result.partialData?.responseSku===sku){
       data=result.partialData;partial=true;atomic(partialCache,{source:'live_signed_page_arrival_pending',collectedAt:new Date().toISOString(),...(recheckPrices?{priceRecheckVersion:PRICE_RECHECK_VERSION}:{}),data});
       atomic(unavailable,{sku,reason:result.reason,state:'PRICE_PENDING'});gate.end(Date.now());checkpoint();console.log(JSON.stringify({sku,state:'ARRIVAL_PRICE_PENDING'}));
      }else{
      if(result.reason==='PRODUCT_UNAVAILABLE'){
       atomic(unavailable,{collectedAt:new Date().toISOString(),sku,reason:result.reason,evidence:result.evidence});state.unavailable++;gate.end(Date.now());checkpoint();console.log(JSON.stringify({sku,state:'PRODUCT_UNAVAILABLE',tip:result.evidence?.itemOverTip}));continue;
      }
      state.retryAfter=result.retryAfter||null;gate.halt(result.reason);halt(result.reason);break
      }
     }
     if(result.ok){partial=false;data=validate(sku,result.data);atomic(cache,{collectedAt:new Date().toISOString(),source:'live_signed_page',data});state.successful++;gate.end(Date.now());checkpoint();}
     if(!partial)console.log(JSON.stringify({sku,arrivalPrice:data.pp,successful:state.successful,requests:state.requests}));
    }
    if(!expanded.has(sku)){
     expanded.add(sku);
     const check=spawnSync('python',['-X','utf8',path.join(dir,'variant_queue.py'),partial?partialCache:cache],{encoding:'utf8'});
     if(check.status!==0){halt('SKU_MATRIX_INVALID');break}
     const real=JSON.parse(check.stdout);const extra=real.filter(id=>!queue.includes(id));queue.splice(i+1,0,...extra);
    }
    state.queueLength=queue.length;state.currentSku=sku;state.processed=i+1;checkpoint();
   }
   if(state.state==='RUNNING'){
    const partialDir=path.join(stage,'partial_data');const pending=fs.existsSync(partialDir)?unresolvedPrices(fs.readdirSync(partialDir).filter(x=>x.endsWith('.json')).map(x=>json(path.join(partialDir,x))),new Set(queue.filter(sku=>{try{validate(sku,json(path.join(stage,'data',sku+'.json')).data);return true}catch{return false}}))):[];
    state.pendingPriceSkus=pending.map(x=>x.data.responseSku);state.state=pending.length?'DATA_COLLECTED_PRICE_PENDING':'DATA_COMPLETE';checkpoint();console.log(JSON.stringify({state:state.state,successful:state.successful,requests:state.requests,pendingPriceSkus:state.pendingPriceSkus}));
   }
  }finally{fs.closeSync(fd);fs.unlinkSync(lock)}
 }
}catch(e){halt(e.code==='EEXIST'?'ANOTHER_RUNNER_OR_UNRESOLVED_LOCK':'LOCAL_OR_TRANSPORT_ERROR');process.exitCode=2;}




