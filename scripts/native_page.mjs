/** Observe one native page load before making per-SKU interface calls. */
import {project,classifyResponse} from './request_policy.mjs';
export const nativePageState=`JSON.stringify({host:location.hostname,path:location.pathname,ready:document.readyState,isFrequencyPage:location.hostname==='pc-frequent-pro.pf.jd.com',isChallenge:location.hostname==='cfe.m.jd.com'||/risk_handler/.test(location.pathname),apiFinished:performance.getEntriesByType('resource').some(x=>x.name.includes('pc_detailpage_wareBusiness')&&x.duration>0)})`;
const decode=v=>typeof v==='string'?JSON.parse(v):v;
function requestState(sku){
 const completed=performance.getEntriesByType('resource').filter(x=>{
  if(x.duration<=0)return false;
  try{const u=new URL(x.name);return u.searchParams.get('functionId')==='pc_detailpage_wareBusiness'&&String(JSON.parse(u.searchParams.get('body')||'{}').skuId)===sku}catch{return false}
 }).length;
 return JSON.stringify({isFrequencyPage:location.hostname==='pc-frequent-pro.pf.jd.com',isChallenge:location.hostname==='cfe.m.jd.com'||/risk_handler/.test(location.pathname),apiFinished:completed>0,completed});
}
export function completedRequestState(sku){return `(${requestState.toString()})(${JSON.stringify(String(sku))})`}
export function capturedBusiness(rows,expectedSku){
 for(const r of rows){
  if(r.method==='OPTIONS')continue;
  if(r.responseStatus===403)return {ok:false,reason:'HTTP_403_REFUSED'};
  if(r.responseStatus===429)return {ok:false,reason:'HTTP_429_RATE_LIMIT'};
  if(r.responseBodyTruncated)return {ok:false,reason:'CAPTURE_BODY_TRUNCATED'};
  let raw;try{raw=JSON.parse(r.responsePreview||r.responseBody||'')}catch{continue}
  if(!raw?.skuHeadVO)continue;
  const outcome=classifyResponse(r.responseStatus,'',raw);
  if(!outcome.ok)return outcome;
  const data=project(raw);if(data.responseSku!==expectedSku)return {ok:false,reason:'SKU_ID_MISMATCH'};
  // Only ordinary page request headers needed by its own interface are retained in memory.
  const allowed=new Set(['accept','content-type','x-skuid-param','x-sdx','soarate']);
  const headers=Object.fromEntries(Object.entries(r.requestHeaders||{}).filter(([k])=>allowed.has(k.toLowerCase())));
  return {ok:true,data,context:{url:r.url,headers,method:r.method||'GET'}};
 }
 return null;
}
export async function waitNativePage(page,sku,{timeoutMs=45000,afterCount=null,sleep=ms=>new Promise(r=>setTimeout(r,ms)),now=Date.now}={}){
 const deadline=now()+timeoutMs;
 while(now()<deadline){
  await sleep(1000);const state=decode(await page.evaluate(afterCount!==null?completedRequestState(sku):nativePageState));
  if(state.isChallenge)return {ok:false,reason:'VERIFICATION_REQUIRED'};
  if(state.isFrequencyPage)return {ok:false,reason:'PAGE_FREQUENCY_LIMIT'};
  // An item URL that lands on the JD homepage is a dead product page; report it
  // immediately instead of burning the full timeout on a transport-looking stall.
  if(state.host==='www.jd.com'&&(!state.path||state.path==='/'))return {ok:false,reason:'PRODUCT_UNAVAILABLE_REDIRECT'};
  if(!state.apiFinished||(afterCount!==null&&state.completed!==undefined&&state.completed<=afterCount))continue;
  // Network capture is destructive. Read only after loadingFinished, never on requestWillBeSent.
  await sleep(250);const result=capturedBusiness(await page.readNetworkCapture(),sku);
  if(result)return result;
 }
 return {ok:false,reason:'INITIAL_RESPONSE_MISSING'};
}
export async function openNativePage(owner,Page,sendCommandFull,context,sku){
 const tab=await owner.newTab();const page=new Page(context.session,context.idleTimeout,undefined,'background');page.setActivePage(tab);
 try{
  const started=await page.startNetworkCapture('pc_detailpage_wareBusiness');
  if(started===false)throw Error('NETWORK_CAPTURE_UNSUPPORTED');
  await sendCommandFull('navigate',{url:`https://item.jd.com/${sku}.html`,session:context.session,page:tab,idleTimeout:context.idleTimeout,windowMode:'background',surface:'browser'});
  const result=await waitNativePage(page,sku);
  if(!result.ok)return {tab,page,result};
  // Context (including signed URL) is handed straight back to page memory; never saved or printed.
  await page.evaluate(`window.__jdNativeRequestContext=${JSON.stringify(result.context)};undefined`);
  return {tab,page,result:{ok:true,data:result.data}};
 }catch(e){try{await page.closeTab(tab)}catch{}throw e}
}
