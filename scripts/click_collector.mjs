/** Click-driven collector: fresh tab per product, real spec clicks, native responses only.
 * Programmatic SDK requests may be silently tarpitted; this path uses the page's own traffic. */
import fs from 'node:fs';import path from 'node:path';import {fileURLToPath,pathToFileURL} from 'node:url';import {spawnSync} from 'node:child_process';
import {project,validate,classifyResponse} from './request_policy.mjs';
import {clickSpecExpression} from './browser_worker.mjs';
import {taskContext} from './task_context.mjs';
import {parseOptions} from './collection_policy.mjs';
import {variantRows} from './variant_bridge.mjs';
import {acquireRunnerLock} from './runner_lock.mjs';
import {waitNativePage,completedRequestState} from './native_page.mjs';
const dir=path.dirname(fileURLToPath(import.meta.url));
const {root,stateDir}=parseOptions(process.argv.slice(2));
if(!fs.existsSync(root))throw Error('ROOT_NOT_FOUND');
const stage=stateDir?path.resolve(stateDir):path.join(root,'.collector_state');
const {session,idleTimeout,wcli}=taskContext(stage);
const CLICK_INTERVAL_MS=30000;const INTER_PRODUCT_MS=60000;const RESPONSE_TIMEOUT_MS=30000;const LOAD_TIMEOUT_MS=60000;
function atomic(file,value){fs.mkdirSync(path.dirname(file),{recursive:true});const tmp=file+'.pending';fs.writeFileSync(tmp,JSON.stringify(value,null,2),'utf8');fs.renameSync(tmp,file)}
function json(file){return JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''))}
const decode=v=>typeof v==='string'?JSON.parse(v):v;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const state={state:'STARTING',startedAt:new Date().toISOString(),products:0,collections:0,clicks:0,tabs:0,unavailable:0,reason:null,currentProduct:null};
state.pid=process.pid;
const stateFile=path.join(stage,'runner_state.json');
function checkpoint(){state.updatedAt=new Date().toISOString();atomic(stateFile,state)}
function halt(reason){if(state.state==='HALTED')return;state.state='HALTED';state.reason=reason;checkpoint();console.log(JSON.stringify({state:state.state,reason,products:state.products,collections:state.collections,clicks:state.clicks}));process.exitCode=2;throw new Error('HALTED')}
process.argv[1]=wcli.main;
await import(pathToFileURL(wcli.preload).href);
const {Page}=await import(pathToFileURL(wcli.page).href);
const {sendCommandFull}=await import(pathToFileURL(path.join(path.dirname(wcli.page),'daemon-client.js')).href);
const releaseLock=acquireRunnerLock(stage);
const bus=new Page(session,idleTimeout,undefined,'background');
const pageOf=tab=>{const p=new Page(session,idleTimeout,undefined,'background');p.setActivePage(tab);return p};
async function pageState(page){return decode(await page.evaluate(`JSON.stringify({host:location.hostname,isTaskItem:location.hostname==='item.jd.com',isFrequencyPage:location.hostname==='pc-frequent-pro.pf.jd.com',isChallenge:location.hostname==='cfe.m.jd.com'||/risk_handler/.test(location.pathname),specs:document.querySelectorAll('.specification-item-sku').length})`))}
function saveSku(raw){
 const d=raw.responseSku?raw:project(raw);
 try{validate(d.responseSku,d);atomic(path.join(stage,'data',d.responseSku+'.json'),{source:'live_native_page',collectedAt:new Date().toISOString(),data:d});state.collections++;return {saved:true,sku:d.responseSku,arrival:d.pp}}
 catch(e){
  if(e.message==='ARRIVAL_PRICE_MISSING'&&d.login===true&&d.responseSku&&d.title&&d.realSpuId&&(d.carousel||[]).some(x=>x.u)){
   atomic(path.join(stage,'partial_data',d.responseSku+'.json'),{source:'live_native_page_arrival_pending',collectedAt:new Date().toISOString(),data:d});
   atomic(path.join(stage,'errors',d.responseSku+'.json'),{sku:d.responseSku,reason:'ARRIVAL_PRICE_MISSING',state:'PRICE_PENDING'});return {saved:false,sku:d.responseSku,reason:'ARRIVAL_PRICE_PENDING'}
  }
  return {saved:false,sku:d.responseSku||null,reason:e.message}
 }
}
function variantsOf(cacheFile){
 return variantRows(path.join(dir,'variant_queue.py'),cacheFile);
}
/** Read new capture rows, save every business response, halt on platform refusal. */
async function drainBusiness(page,matched,expectSku){
 const rows=await page.readNetworkCapture();
 for(const r of rows){
  let raw=null;try{raw=JSON.parse(r.responseBody||r.responsePreview||'')}catch{}
  if(raw?.skuHeadVO){const verdict=classifyResponse(r.responseStatus,'',raw);if(!verdict.ok)halt(verdict.reason);if(expectSku&&String(raw.pageConfigVO?.skuid)!==expectSku)continue;const res=saveSku(raw);if(!matched)matched=res}
  else if(r.responseStatus===403)halt('HTTP_403_REFUSED');
 }
 return matched;
}
async function guardPage(page){
 const st=await pageState(page);
 if(st.isFrequencyPage)halt('PAGE_FREQUENCY_LIMIT');
 else if(st.isChallenge)halt('VERIFICATION_REQUIRED');
 return st;
}
try{
 const tasks=json(path.join(stage,'keyword_tasks.json'));
 const queue=[...new Set(Object.values(tasks).flat().map(x=>String(x.pid)))];
 state.state='RUNNING';state.queueLength=queue.length;checkpoint();
 for(const pid of queue){
  const unavailable=path.join(stage,'errors',pid+'.json');
  if(fs.existsSync(unavailable)&&json(unavailable).reason==='PRODUCT_UNAVAILABLE'){state.unavailable++;continue}
  const mainCache=path.join(stage,'data',pid+'.json');const partialCache=path.join(stage,'partial_data',pid+'.json');
  let known=null;
  if(fs.existsSync(mainCache)){try{const saved=json(mainCache);validate(pid,saved.data);if(['live_signed_page','live_native_page'].includes(saved.source))known=mainCache}catch{}}
  if(!known&&fs.existsSync(partialCache))known=partialCache;
  let needed=[];
  if(known){
   const variants=variantsOf(known)||[];
   needed=variants.filter(row=>{const p=path.join(stage,'data',row.sku+'.json');if(!fs.existsSync(p))return true;try{const saved=json(p);validate(row.sku,saved.data);return !['live_signed_page','live_native_page'].includes(saved.source)}catch{return true}});
   if(!needed.length)continue;
  }
  state.currentProduct=pid;state.products++;checkpoint();
  await sleep(INTER_PRODUCT_MS); // Rapid consecutive product loads previously triggered the verification page.
  const tab=await bus.newTab();state.tabs++;checkpoint();
  const page=pageOf(tab);
  try{
   await page.startNetworkCapture('pc_detailpage_wareBusiness');
   // Start capture before navigation. Avoid goto's unrelated page-global injection.
   await sendCommandFull('navigate',{url:`https://item.jd.com/${pid}.html`,session,page:tab,idleTimeout,windowMode:'background',surface:'browser'});
   const initialResponse=await waitNativePage(page,pid,{timeoutMs:LOAD_TIMEOUT_MS});
   if(!initialResponse.ok)halt(initialResponse.reason);
   const initial=saveSku(initialResponse.data);
   console.log(JSON.stringify({product:pid,initial}));
   const variantsFile=fs.existsSync(mainCache)?mainCache:partialCache;
   const variants=variantsOf(variantsFile)||[];
   const pending=[];
   for(const row of variants){
    const p=path.join(stage,'data',row.sku+'.json');
    if(fs.existsSync(p)){try{const saved=json(p);validate(row.sku,saved.data);if(['live_signed_page','live_native_page'].includes(saved.source))continue}catch{}}
    pending.push(row);
   }
   for(const row of pending){
    await sleep(CLICK_INTERVAL_MS);await guardPage(page);
    const baseline=decode(await page.evaluate(completedRequestState(row.sku))).completed;
    const clicked=decode(await page.evaluate(clickSpecExpression(row.spec1,row.spec2)));
    if(!clicked.ok){atomic(path.join(stage,'errors',row.sku+'.json'),{sku:row.sku,reason:clicked.reason,state:'SPEC_CLICK_FAILED'});continue}
    state.clicks++;checkpoint();
    const captured=await waitNativePage(page,row.sku,{timeoutMs:RESPONSE_TIMEOUT_MS,afterCount:baseline});
    if(captured.ok){const got=saveSku(captured.data);console.log(JSON.stringify({product:pid,target:row.sku,result:got}))}
    else if(['HTTP_403_REFUSED','HTTP_429_RATE_LIMIT','PAGE_FREQUENCY_LIMIT','VERIFICATION_REQUIRED','LOGIN_REQUIRED'].includes(captured.reason))halt(captured.reason);
    else atomic(path.join(stage,'errors',row.sku+'.json'),{sku:row.sku,reason:captured.reason,state:'CLICK_NO_RESPONSE'});
   }
  }finally{try{await page.closeTab(tab)}catch{state.tabCloseFailed=(state.tabCloseFailed||0)+1}checkpoint()}
 }
 state.state='DATA_COLLECTION_SWEEP_DONE';checkpoint();
 console.log(JSON.stringify({state:state.state,products:state.products,collections:state.collections,clicks:state.clicks}));
 }catch(e){if(e.message!=='HALTED'){state.state='HALTED';state.reason=e.message==='SKU_MATRIX_INVALID'?e.message:'LOCAL_OR_TRANSPORT_ERROR';checkpoint();process.exitCode=2}}
 finally{releaseLock()}
