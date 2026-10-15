/** Interface-first collection: one native page context per source product, no per-SKU navigation. */
import fs from 'node:fs';import path from 'node:path';import {fileURLToPath,pathToFileURL} from 'node:url';
import {validate} from './request_policy.mjs';
import {startExpression,readExpression,pageStateExpression,abortExpression} from './browser_worker.mjs';
import {parseOptions,shouldRequest,unresolvedPrices,waitUntilNext,partialRecheckEvidence} from './collection_policy.mjs';
import {taskContext} from './task_context.mjs';
import {acquireRunnerLock} from './runner_lock.mjs';
import {variantRows} from './variant_bridge.mjs';
import {openNativePage} from './native_page.mjs';

const options=parseOptions(process.argv.slice(2)); // Capture before WebCLI preload changes argv[1].
const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(options.root),stage=options.stateDir?path.resolve(options.stateDir):path.join(root,'.collector_state');
if(!fs.existsSync(root))throw Error('ROOT_NOT_FOUND');
const context=taskContext(stage);
const decode=v=>typeof v==='string'?JSON.parse(v):v;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const json=file=>JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
function atomic(file,value){fs.mkdirSync(path.dirname(file),{recursive:true});const pending=file+'.pending';fs.writeFileSync(pending,JSON.stringify(value,null,2),'utf8');fs.renameSync(pending,file)}
const goodSource=new Set(['live_signed_page','live_native_page']);
function validCache(sku){const file=path.join(stage,'data',sku+'.json');try{const saved=json(file);if(!goodSource.has(saved.source))return null;return validate(sku,saved.data)}catch{return null}}
function partialCache(sku){try{return json(path.join(stage,'partial_data',sku+'.json'))}catch{return null}}
function cacheRows(sku){const main=validCache(sku);const file=path.join(stage,main?'data':'partial_data',sku+'.json');return variantRows(path.join(dir,'variant_queue.py'),file)}
const state={state:'STARTING',pid:process.pid,startedAt:new Date().toISOString(),route:'per-product-native-xhr',successful:0,partial:0,requests:0,products:0,navigations:0,unavailable:0,reason:null,intervalMs:options.interval,maxRequests:options.maxRequests};
const stateFile=path.join(stage,'runner_state.json'),clockFile=path.join(stage,'request_clock.json');
function checkpoint(fields={}){Object.assign(state,fields,{updatedAt:new Date().toISOString()});atomic(stateFile,state)}
function halt(reason){checkpoint({state:'HALTED',reason});const error=Error(reason);error.taskStop=true;throw error}
function clock(){try{return json(clockFile).finishedAt}catch{return 0}}
function finishRequest(){atomic(clockFile,{finishedAt:Date.now()})}
function save(sku,data,source){
 if(data?.responseSku!==sku)halt('SKU_ID_MISMATCH');
 try{validate(sku,data)}catch(e){
  if(e.message!=='ARRIVAL_PRICE_MISSING')halt(e.message);
  if(!data?.login||!data?.title||!data?.realSpuId||!data.carousel?.some(x=>x.u))halt('INVALID_PARTIAL_DATA');
  const timestamp=new Date().toISOString();
  atomic(path.join(stage,'partial_data',sku+'.json'),{source:source+'_arrival_pending',collectedAt:timestamp,...partialRecheckEvidence(options.recheckPrices,partialCache(sku),timestamp),data});
  atomic(path.join(stage,'errors',sku+'.json'),{sku,reason:'ARRIVAL_PRICE_MISSING',state:'PRICE_PENDING'});state.partial++;
  return 'ARRIVAL_PRICE_PENDING';
 }
 // Preserve accepted receipts and earlier successful prices; only fill missing cache entries.
 if(!validCache(sku)){
  atomic(path.join(stage,'data',sku+'.json'),{source,collectedAt:new Date().toISOString(),data});state.successful++;
 }
 return 'PRICE_VERIFIED';
}
let release,owner,current;
try{
 release=acquireRunnerLock(stage);
 if(!options.runRequested){checkpoint({state:'READY_NOT_RUNNING'});console.log(JSON.stringify({state:state.state,route:state.route}));}
 else{
  process.argv[1]=context.wcli.main;await import(pathToFileURL(context.wcli.preload).href);
  const {Page}=await import(pathToFileURL(context.wcli.page).href);
  const {sendCommandFull}=await import(pathToFileURL(path.join(path.dirname(context.wcli.page),'daemon-client.js')).href);
  owner=new Page(context.session,context.idleTimeout,undefined,'background');
  const tasks=json(path.join(stage,'keyword_tasks.json'));
  const ids=[...new Set(Object.values(tasks).flat().map(x=>String(x.pid)))];checkpoint({state:'RUNNING',sourceProducts:ids.length});
  for(const pid of ids){
   let unavailable=false;try{unavailable=json(path.join(stage,'errors',pid+'.json')).reason==='PRODUCT_UNAVAILABLE'}catch{}
   if(unavailable){state.unavailable++;continue}
   const known=validCache(pid)||partialCache(pid)?.data;
   if(known&&options.mainOnly)continue;
   if(known){const needed=cacheRows(pid).filter(r=>shouldRequest({validCache:!!validCache(r.sku),partialCache:partialCache(r.sku),recheckPrices:options.recheckPrices}));if(!needed.length)continue}
   if(state.requests>=options.maxRequests||(options.maxProducts&&state.products>=options.maxProducts)){checkpoint({state:'COOLDOWN_REQUIRED'});break}
   // The document also calls the business interface. Share its throttle with SKU requests.
   await sleep(waitUntilNext(Date.now(),clock(),Math.max(Number(process.env.JD_COLLECTOR_NAV_MIN_MS||'60000'),options.interval)));
   state.products++;state.navigations++;checkpoint({currentProduct:pid,currentSku:pid});
   const opened=await openNativePage(owner,Page,sendCommandFull,context,pid);current=opened;
   state.requests++;finishRequest();
   if(!opened.result.ok){
    if(opened.result.reason==='PRODUCT_UNAVAILABLE'){atomic(path.join(stage,'errors',pid+'.json'),{sku:pid,reason:'PRODUCT_UNAVAILABLE'});state.unavailable++;await opened.page.closeTab(opened.tab);current=null;continue}
    halt(opened.result.reason);
   }
   const initialState=save(pid,opened.result.data,'live_native_page');
   const rows=cacheRows(pid);
   await opened.page.evaluate(`window.__jdNativeRequestContext.allowedSkuIds=${JSON.stringify(rows.map(r=>r.sku))};undefined`);
   console.log(JSON.stringify({product:pid,sku:pid,state:initialState,arrivalPrice:opened.result.data.pp,skuCount:rows.length,requests:state.requests}));checkpoint();
   if(options.mainOnly){await opened.page.closeTab(opened.tab);current=null;continue;}
   for(const row of rows){
    const sku=row.sku;if(sku===pid)continue;
    if(!shouldRequest({validCache:!!validCache(sku),partialCache:partialCache(sku),recheckPrices:options.recheckPrices}))continue;
    if(state.requests>=options.maxRequests){checkpoint({state:'COOLDOWN_REQUIRED'});break}
    await sleep(waitUntilNext(Date.now(),clock(),options.interval));
    const observed=decode(await opened.page.evaluate(pageStateExpression()));
    if(observed.isFrequencyPage)halt('PAGE_FREQUENCY_LIMIT');if(observed.isChallenge)halt('VERIFICATION_REQUIRED');if(!observed.isTaskItem||observed.pending)halt('PAGE_CHANGED_OR_PENDING');
    const started=decode(await opened.page.evaluate(startExpression(sku)));if(!started.ok)halt(started.reason);
    state.requests++;checkpoint({currentSku:sku});let result;const deadline=Date.now()+22000;
    while(Date.now()<deadline){await sleep(1500);result=decode(await opened.page.evaluate(readExpression));if(result?.phase==='DONE')break}
    if(result?.phase!=='DONE'){await opened.page.evaluate(abortExpression);halt('REQUEST_RESULT_UNKNOWN')}
    finishRequest();
    if(!result.ok&&result.reason!=='ARRIVAL_PRICE_MISSING'){checkpoint({retryAfter:result.retryAfter||null});halt(result.reason)}
    const data=result.data||result.partialData;const priceState=save(sku,data,'live_signed_page');checkpoint();
    console.log(JSON.stringify({product:pid,sku,state:priceState,arrivalPrice:data.pp,requests:state.requests}));
   }
   await opened.page.closeTab(opened.tab);current=null;
   if(state.state==='COOLDOWN_REQUIRED')break;
  }
  if(state.state==='RUNNING'){
   const partialDir=path.join(stage,'partial_data');const partials=fs.existsSync(partialDir)?fs.readdirSync(partialDir).filter(x=>x.endsWith('.json')).map(x=>json(path.join(partialDir,x))):[];
   const resolved=new Set(partials.filter(x=>validCache(x.data?.responseSku)).map(x=>x.data.responseSku));
   const remaining=unresolvedPrices(partials,resolved);checkpoint({state:options.mainOnly?'MAIN_SCAN_COMPLETE':remaining.length?'DATA_COLLECTED_PRICE_PENDING':'DATA_COMPLETE',pendingPriceSkus:remaining.map(x=>x.data.responseSku)});
  }
 }
}catch(e){if(e.message==='ANOTHER_RUNNER_OR_UNRESOLVED_LOCK'){state.state='REFUSED';state.reason=e.message}else if(!e.taskStop){checkpoint({state:'HALTED',reason:e.message==='SKU_MATRIX_INVALID'?e.message:'LOCAL_OR_TRANSPORT_ERROR',errorType:e.name})}process.exitCode=2;}
finally{
 if(current){try{await current.page.closeTab(current.tab)}catch{checkpoint({cleanupPendingTab:current.tab})}}
 release?.();console.log(JSON.stringify({state:state.state,reason:state.reason,successful:state.successful,partial:state.partial,requests:state.requests,products:state.products,navigations:state.navigations}));
}
