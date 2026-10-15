/** Observe the site's own requests without changing request parameters or credentials. */
import {project,classifyResponse} from './request_policy.mjs';
export function observerExpression(){
 return `(()=>{
  if(window.__jdNativeObserverInstalled)return;
  window.__jdNativeObserverInstalled=true;window.__jdNativeSnapshots=[];
  const project=${project.toString()},classify=${classifyResponse.toString()};
  const open=XMLHttpRequest.prototype.open,send=XMLHttpRequest.prototype.send,setHeader=XMLHttpRequest.prototype.setRequestHeader;
  const target=u=>{try{const x=new URL(u,location.href);return x.hostname==='api.m.jd.com'&&x.searchParams.get('functionId')==='pc_detailpage_wareBusiness'}catch{return false}};
  XMLHttpRequest.prototype.open=function(method,url,...rest){this.__jdCapture={method,url:String(url),headers:{}};return open.call(this,method,url,...rest)};
  XMLHttpRequest.prototype.setRequestHeader=function(k,v){if(this.__jdCapture)this.__jdCapture.headers[k]=v;return setHeader.call(this,k,v)};
  XMLHttpRequest.prototype.send=function(body){
   const ctx=this.__jdCapture;
   if(ctx&&target(ctx.url))this.addEventListener('load',()=>{
    let raw=null,text='';try{text=this.responseText;raw=JSON.parse(text)}catch{}
    const outcome=classify(this.status,text,raw,this.getResponseHeader('retry-after'));
    if(raw?.skuHeadVO){const data=project(raw);window.__jdNativeSnapshots.push({status:this.status,outcome,data});if(outcome.ok)window.__jdNativeRequestContext={...ctx,body,withCredentials:this.withCredentials}}
    else window.__jdNativeSnapshots.push({status:this.status,outcome});
   },{once:true});
   return send.call(this,body);
  };
 })()`;
}
export const observerReadExpression=`JSON.stringify({host:location.hostname,path:location.pathname,ready:document.readyState,isFrequencyPage:location.hostname==='pc-frequent-pro.pf.jd.com',isChallenge:location.hostname==='cfe.m.jd.com'||/risk_handler/.test(location.pathname),snapshots:window.__jdNativeSnapshots||[],hasNativeContext:!!window.__jdNativeRequestContext,specCount:document.querySelectorAll('.specification-item-sku').length,sdkReady:typeof window.PSign?.sign==='function'})`;
