/** One request using the current page SDK; credentials and native request context stay in memory. */
import fs from 'node:fs';import path from 'node:path';import {pathToFileURL} from 'node:url';
import {project,validate,classifyResponse} from './request_policy.mjs';
const args=Object.fromEntries(process.argv.slice(2).map(x=>x.split('=',2)));
const root=args['--root'];const sku=args['--sku'];if(!root||!/^\d{8,}$/.test(sku))throw Error('ROOT_AND_SKU_REQUIRED');
const c=JSON.parse(fs.readFileSync(path.join(root,'browser_context.json'),'utf8').replace(/^\uFEFF/,''));
const diag=JSON.parse(fs.readFileSync(path.join(root,'native_diagnosis.json'),'utf8'));
process.argv[1]=c.wcli.main;await import(pathToFileURL(c.wcli.preload).href);
const {Page}=await import(pathToFileURL(c.wcli.page).href);const p=new Page(c.session,86400,undefined,'background');p.setActivePage(diag.tab);
const expression=`(()=>{
 const project=${project.toString()},validate=${validate.toString()},classify=${classifyResponse.toString()};
 const sku=${JSON.stringify(sku)};
 if(location.hostname!=='item.jd.com')return JSON.stringify({ok:false,reason:'TASK_PAGE_REQUIRED'});
 if(!window.__jdNativeRequestContext)return JSON.stringify({ok:false,reason:'NATIVE_CONTEXT_MISSING'});
 const job={phase:'STARTED',sku,timeline:[],sent:false};window.__jdInterfaceProbe=job;
 const phase=p=>{job.phase=p;job.timeline.push({phase:p,at:Date.now()})};
 (async()=>{try{
  const native=window.__jdNativeRequestContext;const u=new URL(native.url),body=JSON.parse(u.searchParams.get('body'));
  body.skuId=sku;const rawBody=JSON.stringify(body),t=Date.now();
  phase('TOKEN');const token=await new Promise(resolve=>window.getJsToken(x=>resolve(x?.jsToken||'')));
  if(!token)throw Error('TOKEN_UNAVAILABLE');
  phase('SIGN');const signed=await window.PSign.sign({appid:u.searchParams.get('appid'),clientVersion:u.searchParams.get('clientVersion'),client:u.searchParams.get('client'),t,body:window.SHA256(rawBody),functionId:'pc_detailpage_wareBusiness'});
  if(!signed?.h5st)throw Error('SIGN_UNAVAILABLE');
  const query=Object.fromEntries(u.searchParams);query.body=rawBody;query.scval=sku;query.t=String(t);query.h5st=encodeURI(signed.h5st);query['x-api-eid-token']=token;
  const enc=v=>encodeURIComponent(v).replace(/%3A/gi,':').replace(/%24/g,'$').replace(/%2C/gi,',').replace(/%20/g,'+').replace(/%5B/gi,'[').replace(/%5D/gi,']');
  const url=u.origin+u.pathname+'?'+Object.entries(query).map(([k,v])=>enc(k)+'='+enc(v)).join('&');
  const headers={'Accept':'application/json, text/plain, */*','Content-Type':'application/x-www-form-urlencoded'};
  const params=new URL(location.href).searchParams;for(const [key,name] of [['pcdk','X-Skuid-Param'],['sdx','x-sdx'],['soaRate','soaRate']]){const value=params.get(key);if(value)headers[name]=value}
  const xhr=new XMLHttpRequest();xhr.open('GET',url,true);xhr.withCredentials=true;xhr.timeout=15000;
  for(const [k,v] of Object.entries(headers))xhr.setRequestHeader(k,v);
  const handle=()=>{let raw=null,text='';try{text=xhr.responseText;raw=JSON.parse(text)}catch{}
   job.httpStatus=xhr.status;const outcome=classify(xhr.status,text,raw,xhr.getResponseHeader('retry-after'));job.outcome=outcome;
   if(outcome.ok){const data=project(raw);try{validate(sku,data);job.ok=true;job.data=data}catch(e){job.ok=false;job.reason=e.message;job.partialData=data}}
   else{job.ok=false;job.reason=outcome.reason}phase('DONE');
  };
  xhr.onload=handle;xhr.onerror=()=>{job.reason='NETWORK_ERROR';phase('DONE')};xhr.ontimeout=()=>{job.reason='XHR_TIMEOUT';phase('DONE')};
  xhr.onabort=()=>{job.reason='XHR_ABORTED';phase('DONE')};window.__jdInterfaceProbeAbort=()=>xhr.abort();
  phase('SEND');job.sent=true;xhr.send(null);
 }catch(e){job.reason=/^[A-Z_]{1,80}$/.test(e.message)?e.message:'LOCAL_PAGE_ERROR';job.errorName=e.name;phase('DONE')}})();
 return JSON.stringify({started:true,sku});
})()`;
const decode=v=>typeof v==='string'?JSON.parse(v):v;
console.log(await p.evaluate(expression));let result;const end=Date.now()+30000;
while(Date.now()<end){await new Promise(r=>setTimeout(r,2000));result=decode(await p.evaluate('JSON.stringify(window.__jdInterfaceProbe)'));if(result?.phase==='DONE')break}
const safe={...result,checkedAt:new Date().toISOString()};fs.writeFileSync(path.join(root,'interface-probe-'+sku+'.json'),JSON.stringify(safe,null,2));
console.log(JSON.stringify({phase:result?.phase,reason:result?.reason,ok:result?.ok,status:result?.httpStatus,sku:result?.data?.responseSku,arrival:result?.data?.pp,priceSource:result?.data?.priceSource,timeline:result?.timeline,sent:result?.sent}));
