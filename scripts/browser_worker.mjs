/** Normal in-page JD signer only; this is not a signature implementation or verification bypass. */
import {classifyResponse,project,validate} from './request_policy.mjs';
export function pageStateExpression(){return `JSON.stringify({host:location.hostname,path:location.pathname,title:document.title,isTaskItem:location.hostname==='item.jd.com',isFrequencyPage:location.hostname==='pc-frequent-pro.pf.jd.com',isChallenge:location.hostname==='cfe.m.jd.com'||/risk_handler/.test(location.pathname),sdkReady:typeof window.PSign?.sign==='function'&&typeof window.SHA256==='function'&&typeof window.getJsToken==='function',pending:window.__jdCollectorJob?.phase==='PENDING'||window.__jdCollectorJob?.phase==='FETCH'})`}
export function startExpression(sku){
 if(!/^\d{8,}$/.test(String(sku)))throw Error('INVALID_SKU');
 return `(()=>{
  const classify=${classifyResponse.toString()};const project=${project.toString()};const validate=${validate.toString()};
  if(location.hostname!=='item.jd.com')return JSON.stringify({ok:false,reason:location.hostname==='cfe.m.jd.com'?'VERIFICATION_REQUIRED':'TASK_ITEM_PAGE_REQUIRED'});
  if(['PENDING','FETCH'].includes(window.__jdCollectorJob?.phase))return JSON.stringify({ok:false,reason:'REQUEST_IN_FLIGHT'});
  const native=performance.getEntriesByType('resource').map(x=>x.name).reverse().find(x=>{try{const u=new URL(x);return u.hostname==='api.m.jd.com'&&u.searchParams.get('functionId')==='pc_detailpage_wareBusiness'&&u.searchParams.has('h5st')}catch{return false}});
  if(!native)return JSON.stringify({ok:false,reason:'NORMAL_REQUEST_CONTEXT_MISSING'});
  if(typeof PSign?.sign!=='function'||typeof SHA256!=='function'||typeof getJsToken!=='function')return JSON.stringify({ok:false,reason:'PAGE_SDK_MISSING'});
  const sku=${JSON.stringify(String(sku))};window.__jdCollectorJob={phase:'PENDING',sku,started:Date.now(),sent:false};
  (async()=>{try{
   const u=new URL(native),body=JSON.parse(u.searchParams.get('body'));if(!body.area)throw Error('ADDRESS_CONTEXT_MISSING');body.skuId=sku;
   const rawBody=JSON.stringify(body),t=Date.now();
   const token=await new Promise(resolve=>getJsToken(v=>resolve(v?.jsToken||'')));if(!token)throw Error('PAGE_CONTEXT_MISSING');
   const signed=await PSign.sign({appid:u.searchParams.get('appid'),clientVersion:u.searchParams.get('clientVersion'),client:u.searchParams.get('client'),t,body:SHA256(rawBody),functionId:'pc_detailpage_wareBusiness'});
   if(!signed?.h5st)throw Error('NORMAL_SIGNATURE_MISSING');
   const values=Object.fromEntries(u.searchParams);values.body=rawBody;values.scval=sku;values.t=String(t);values.h5st=encodeURI(signed.h5st);values['x-api-eid-token']=token;
   const enc=v=>encodeURIComponent(v).replace(/%3A/gi,':').replace(/%24/g,'$').replace(/%2C/gi,',').replace(/%20/g,'+').replace(/%5B/gi,'[').replace(/%5D/gi,']');
   const url=u.origin+u.pathname+'?'+Object.entries(values).map(([k,v])=>enc(k)+'='+enc(v)).join('&');
   const controller=new AbortController();window.__jdCollectorAbort=controller;
   window.__jdCollectorJob.phase='FETCH';window.__jdCollectorJob.sent=true;
   const response=await fetch(url,{credentials:'include',signal:controller.signal});const text=await response.text();let raw=null;try{raw=JSON.parse(text)}catch{}
   const outcome=classify(response.status,text,raw,response.headers.get('retry-after'));
   if(!outcome.ok){window.__jdCollectorJob={phase:'DONE',sku,sent:true,...outcome,evidence:{responseSku:String(raw?.pageConfigVO?.skuid||''),hasTitle:!!raw?.skuHeadVO?.skuTitle,hasArrival:!!raw?.bestPromotion?.purchasePrice,isLogin:raw?.isLogin===true,httpStatus:response.status,isOver:raw?.pageConfigVO?.isOver,itemOverTip:raw?.itemOverVO?.itemOverTip,redirectKey:raw?.urlRedirectVO?.key,redirectDestination:raw?.urlRedirectVO?.url?(()=>{try{const u=new URL(raw.urlRedirectVO.url,location.href);return {host:u.hostname,path:u.pathname}}catch{return null}})():null,noSale:raw?.pageConfigVO?.noSale,noSaleReason:raw?.pageConfigVO?.noSaleReason,rawKeys:raw?Object.keys(raw):[],stock:raw?.stockInfo?.stockState,urlRedirect:raw?.urlRedirectVO?Object.keys(raw.urlRedirectVO):[],code:raw?.code}};return}
   const projected=project(raw);window.__jdCollectorLastData=projected;window.__jdCollectorPriceEvidence={priceKeys:Object.keys(raw.price||{}),promotionKeys:Object.keys(raw.bestPromotion||{}),hasLogin:raw.isLogin===true,stock:raw.stockInfo?.stockState};const data=validate(sku,projected);window.__jdCollectorJob={phase:'DONE',sku,sent:true,ok:true,data};
  }catch(e){const allowed=/^(ARRIVAL_PRICE_MISSING|SKU_ID_MISSING|SKU_ID_MISMATCH|TITLE_MISSING|DETAIL_ID_MISSING|MAIN_IMAGES_MISSING|NORMAL_SIGNATURE_MISSING|ADDRESS_CONTEXT_MISSING|PAGE_CONTEXT_MISSING)$/;const redact=x=>String(x).replace(/https?:[^ ]+/g,'[url]').slice(0,160);window.__jdCollectorJob={phase:'DONE',sku,ok:false,reason:allowed.test(e.message)?e.message:'REQUEST_RESULT_UNKNOWN',...(e.message==='ARRIVAL_PRICE_MISSING'?{partialData:window.__jdCollectorLastData}:{} ),errorEvidence:{name:redact(e&&e.name||'Error'),message:redact(e&&e.message||'')}}}})();
  return JSON.stringify({ok:true,phase:'STARTED',sku});
 })()`;
}
export const readExpression=`JSON.stringify(window.__jdCollectorJob?{...window.__jdCollectorJob}:null)`;
export const abortExpression=`(()=>{window.__jdCollectorAbort?.abort();return JSON.stringify({abortRequested:!!window.__jdCollectorAbort})})()`;
/** Real in-page spec click; spec2 empty means single-dimension product. */
export function clickSpecExpression(spec1,spec2){
 if(typeof spec1!=='string'||!spec1.trim())throw Error('INVALID_SPEC');
 if(spec2!==undefined&&typeof spec2!=='string')throw Error('INVALID_SPEC');
 return `(()=>{const find=t=>Array.from(document.querySelectorAll('.specification-item-sku')).find(e=>(e.innerText||'').trim()===t);const a=find(${JSON.stringify(spec1)});if(!a)return JSON.stringify({ok:false,reason:'SPEC_BUTTON_MISSING'});a.click();const second=${JSON.stringify(spec2||'')};if(second){const b=find(second);if(!b)return JSON.stringify({ok:false,reason:'SPEC_BUTTON_MISSING'});b.click();}return JSON.stringify({ok:true})})()`;
}





