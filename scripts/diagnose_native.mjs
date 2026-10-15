/** One authorized native page load; whitelist response data before leaving the browser. */
import fs from 'node:fs';import path from 'node:path';import {pathToFileURL} from 'node:url';
import {observerExpression,observerReadExpression} from './native_observer.mjs';
const options=Object.fromEntries(process.argv.slice(2).map(v=>v.split('=',2)));
const root=options['--root'];if(!root)throw Error('ROOT_REQUIRED');
const context=JSON.parse(fs.readFileSync(path.join(root,'browser_context.json'),'utf8').replace(/^\uFEFF/,''));
const w=context.wcli;process.argv[1]=w.main;await import(pathToFileURL(w.preload).href);
const {Page}=await import(pathToFileURL(w.page).href);
const {sendCommandFull}=await import(pathToFileURL(path.join(path.dirname(w.page),'daemon-client.js')).href);
const owner=new Page(context.session,context.idleTimeout,undefined,'background');
const tab=await owner.newTab();const page=new Page(context.session,context.idleTimeout,undefined,'background');page.setActivePage(tab);
await page.startNetworkCapture('pc_detailpage_wareBusiness');
await sendCommandFull('navigate',{url:'https://item.jd.com/'+(options['--sku']||context.probeSku)+'.html',session:context.session,page:tab,idleTimeout:context.idleTimeout,windowMode:'background',surface:'browser'});
const decode=v=>typeof v==='string'?JSON.parse(v):v;
let result;const deadline=Date.now()+45000;
while(Date.now()<deadline){await new Promise(r=>setTimeout(r,2000));result=decode(await page.evaluate(observerReadExpression));if(result.isFrequencyPage||result.isChallenge||result.specCount)break}
await new Promise(r=>setTimeout(r,5000));
const records=await page.readNetworkCapture();
const {project,classifyResponse}=await import('./request_policy.mjs');
for(const r of records){let raw;try{raw=JSON.parse(r.responsePreview||r.responseBody||'')}catch{continue}if(!raw?.skuHeadVO)continue;result.snapshots.push({status:r.responseStatus,outcome:classifyResponse(r.responseStatus,'',raw),data:project(raw)});}
const native=records.find(r=>{let j;try{j=JSON.parse(r.responsePreview||r.responseBody||'')}catch{return false}return j?.skuHeadVO&&j?.isLogin===true});
if(native)await page.evaluate(`window.__jdNativeRequestContext=${JSON.stringify({url:native.url,headers:native.requestHeaders||{},method:native.method||'GET'})};undefined`);
fs.writeFileSync(path.join(root,'native_diagnosis.json'),JSON.stringify({tab,...result,checkedAt:new Date().toISOString()},null,2));
console.log(JSON.stringify({tab,host:result.host,path:result.path,ready:result.ready,specCount:result.specCount,hasNativeContext:result.hasNativeContext,results:result.snapshots.map(x=>({status:x.status,ok:x.outcome?.ok,reason:x.outcome?.reason,sku:x.data?.responseSku,arrival:x.data?.pp,priceSource:x.data?.priceSource,frontendPriceItems:x.data?.frontendPriceItems})),checkedAt:new Date().toISOString()}));
