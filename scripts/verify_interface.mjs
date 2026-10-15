/** Verify the actual shared worker on one task-owned page and save whitelisted product evidence. */
import fs from 'node:fs';import path from 'node:path';import {pathToFileURL} from 'node:url';
import {startExpression,readExpression,pageStateExpression,abortExpression} from './browser_worker.mjs';
const options=Object.fromEntries(process.argv.slice(2).map(x=>x.split('=',2)));
const root=options['--root'],sku=options['--sku'];if(!root||!/^\d{8,}$/.test(sku))throw Error('ROOT_AND_SKU_REQUIRED');
const c=JSON.parse(fs.readFileSync(path.join(root,'browser_context.json'),'utf8').replace(/^\uFEFF/,''));
const diag=JSON.parse(fs.readFileSync(path.join(root,'native_diagnosis.json'),'utf8'));
process.argv[1]=c.wcli.main;await import(pathToFileURL(c.wcli.preload).href);
const {Page}=await import(pathToFileURL(c.wcli.page).href);const p=new Page(c.session,86400,undefined,'background');p.setActivePage(diag.tab);
const decode=v=>typeof v==='string'?JSON.parse(v):v;
const before=decode(await p.evaluate(pageStateExpression()));
if(!before.isTaskItem||before.isFrequencyPage||before.isChallenge||before.pending)throw Error('TASK_PAGE_NOT_READY');
const start=decode(await p.evaluate(startExpression(sku)));let result;
if(!start.ok)result=start;
else{const until=Date.now()+22000;while(Date.now()<until){await new Promise(r=>setTimeout(r,1500));result=decode(await p.evaluate(readExpression));if(result?.phase==='DONE')break}if(result?.phase!=='DONE'){await p.evaluate(abortExpression);throw Error('UNRESOLVED_RESPONSE')}}
fs.writeFileSync(path.join(root,'verified-interface-'+sku+'.json'),JSON.stringify({source:'live_signed_page',collectedAt:new Date().toISOString(),...result},null,2));
console.log(JSON.stringify({ok:result.ok,reason:result.reason,status:result.evidence?.httpStatus,sku:result.data?.responseSku||result.partialData?.responseSku,arrival:result.data?.pp,priceSource:result.data?.priceSource,dimensions:result.data?.colorSize?.length,phase:result.phase,elapsedMs:Date.now()-(result.started||Date.now()),checkedAt:new Date().toISOString()}));
