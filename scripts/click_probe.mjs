/** Single-tab recovery probe: one normal product load, no clicks, no programmatic requests. */
import fs from 'node:fs';import path from 'node:path';import {pathToFileURL} from 'node:url';
import {project,validate} from './request_policy.mjs';
import {taskContext} from './task_context.mjs';
import {parseOptions} from './collection_policy.mjs';
const root=parseOptions(process.argv.slice(2)).root;
if(!fs.existsSync(root))throw Error('ROOT_NOT_FOUND');
const stage=path.join(root,'.collector_state');
const {session,idleTimeout,probeSku,wcli}=taskContext(stage);
function atomic(file,value){const tmp=file+'.pending';fs.writeFileSync(tmp,JSON.stringify(value,null,2),'utf8');fs.renameSync(tmp,file)}
const decode=v=>typeof v==='string'?JSON.parse(v):v;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
process.argv[1]=wcli.main;
await import(pathToFileURL(wcli.preload).href);
const {Page}=await import(pathToFileURL(wcli.page).href);
const bus=new Page(session,idleTimeout,undefined,'background');
let result={ok:false,reason:null,checkedAt:new Date().toISOString()};
let tab=null;
try{
 tab=await bus.newTab(`https://item.jd.com/${probeSku}.html`);
 const page=new Page(session,idleTimeout,undefined,'background');page.setActivePage(tab);
 await page.startNetworkCapture('pc_detailpage_wareBusiness');
 const deadline=Date.now()+90000;
 while(Date.now()<deadline&&!result.ok){
  await sleep(3000);
  const st=decode(await page.evaluate(`JSON.stringify({host:location.hostname,isFrequencyPage:location.hostname==='pc-frequent-pro.pf.jd.com',isChallenge:location.hostname==='cfe.m.jd.com'||/risk_handler/.test(location.pathname),isItem:location.hostname==='item.jd.com'})`));
  if(st.isFrequencyPage){result={ok:false,reason:'PAGE_FREQUENCY_LIMIT',checkedAt:new Date().toISOString()};break}
  if(st.isChallenge){result={ok:false,reason:'VERIFICATION_REQUIRED',checkedAt:new Date().toISOString()};break}
  const rows=await page.readNetworkCapture();
  for(const r of rows){
   let raw=null;try{raw=JSON.parse(r.responseBody||r.responsePreview||'')}catch{}
   if(raw?.skuHeadVO){
    const d=project(raw);
    try{validate(d.responseSku,d);atomic(path.join(stage,'data',d.responseSku+'.json'),{source:'live_native_page',collectedAt:new Date().toISOString(),data:d});result={ok:true,sku:d.responseSku,arrival:d.pp,checkedAt:new Date().toISOString()}}
    catch{result={ok:false,reason:'ARRIVAL_PRICE_PENDING',sku:d.responseSku,checkedAt:new Date().toISOString()}}
    break;
   }
  }
 }
 if(!result.ok&&!result.reason)result={ok:false,reason:'INITIAL_RESPONSE_MISSING',checkedAt:new Date().toISOString()};
}catch(e){result={ok:false,reason:/stale page identity|Page not found/.test(e.message)?'STALE_TASK_PAGE':'LOCAL_OR_TRANSPORT_ERROR',checkedAt:new Date().toISOString()}}
finally{if(tab){try{const p2=new Page(session,idleTimeout,undefined,'background');p2.setActivePage(tab);await p2.closeTab(tab)}catch{}}}
atomic(path.join(stage,'click_probe_status.json'),result);
console.log(JSON.stringify(result));
