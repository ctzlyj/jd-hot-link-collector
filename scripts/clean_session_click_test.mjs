/** First-action test after a long cooldown. Never sends a programmatic business request first. */
import fs from 'node:fs';
import {project,validate} from './request_policy.mjs';
import {taskContext} from './task_context.mjs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseOptions} from './collection_policy.mjs';
const root=parseOptions(process.argv.slice(2)).root;
const stage=path.join(root,'.collector_state');
const {session,tab,idleTimeout,wcli}=taskContext(stage);
const decode=v=>typeof v==='string'?JSON.parse(v):v;
process.argv[1]=wcli.main;
await import(pathToFileURL(wcli.preload).href);
const {Page}=await import(pathToFileURL(wcli.page).href);
const p=new Page(session,idleTimeout,undefined,'background');p.setActivePage(tab);
const pre=decode(await p.evaluate(`JSON.stringify({host:location.hostname,isTaskItem:location.hostname==='item.jd.com',isFrequencyPage:location.hostname==='pc-frequent-pro.pf.jd.com',isChallenge:location.hostname==='cfe.m.jd.com'||/risk_handler/.test(location.pathname),sdkReady:typeof window.PSign?.sign==='function',hasNormalRequest:performance.getEntriesByType('resource').some(x=>x.name.includes('pc_detailpage_wareBusiness'))})`));
let result={preClean:pre,scriptRequestsBeforeClick:0,checkedAt:new Date().toISOString()};
if(pre.isFrequencyPage||pre.isChallenge){
 result.action='WAIT_REQUIRED'; // Active platform refusal: do not navigate, click or probe.
}else if(!pre.isTaskItem||!pre.sdkReady){
 result.action='TASK_PAGE_REQUIRED';
}else{
 await p.startNetworkCapture('pc_detailpage_wareBusiness');
 const click=decode(await p.evaluate(`(()=>{const items=Array.from(document.querySelectorAll('.specification-item-sku')).filter(e=>!e.className.includes('--selected'));if(!items.length)return JSON.stringify({ok:false,reason:'NO_OTHER_SPEC_BUTTON'});items[0].click();return JSON.stringify({ok:true,clickedText:(items[0].innerText||'').slice(0,80)})})()`));
 result.click=click;result.action=click.ok?'CLICKED':'NO_SPEC_BUTTON';
 const deadline=Date.now()+20000;let captured=[];
 while(Date.now()<deadline){await new Promise(r=>setTimeout(r,2500));captured=await p.readNetworkCapture();if(captured.some(r=>r.responseStatus>=400))break;if(captured.some(r=>r.responseStatus===200))break}
 result.responses=[];
 for(const r of captured){
  let raw=null;try{raw=JSON.parse(r.responseBody||r.responsePreview||'')}catch{}
  if(!raw?.skuHeadVO){result.responses.push({httpStatus:r.responseStatus,hasBusinessBody:false});continue}
  const d=project(raw);let reason=null;try{validate(d.responseSku,d)}catch(e){reason=e.message}
  result.responses.push({httpStatus:r.responseStatus,hasBusinessBody:true,login:d.login,responseSku:d.responseSku,arrival:d.pp,priceSource:d.priceSource,reason});
  if(!reason)fs.writeFileSync(stage+'/data/'+d.responseSku+'.json',JSON.stringify({source:'live_signed_page',collectedAt:new Date().toISOString(),data:d},null,2));
 }
 result.observed=decode(await p.evaluate(`JSON.stringify({host:location.hostname,isFrequencyPage:location.hostname==='pc-frequent-pro.pf.jd.com',selected:document.querySelector('.specification-item-sku--selected')?.innerText})`));
}
fs.writeFileSync(stage+'/clean_session_click_test.json',JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
