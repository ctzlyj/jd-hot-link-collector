import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {startExpression,readExpression,abortExpression} from '../scripts/browser_worker.mjs';
const sku='10000000000001';
const raw=id=>({isLogin:true,pageConfigVO:{skuid:id},skuHeadVO:{skuTitle:'商品'},warePriceGatherVO:{priceItemList:[{priceType:'finalPrice',price:'9.25',hitLine:false}]},wareInfoReadMap:{realSpuId:'123'},mainImageVO:{carouselArea:[{imageUrl:'jfs/image.jpg'}]}});
function makeContext(mode='success'){
 const requests=[];
 const native='https://api.m.jd.com/?functionId=pc_detailpage_wareBusiness&appid=pc-item-soa&clientVersion=1.0.0&client=pc&h5st=normal&body='+encodeURIComponent(JSON.stringify({skuId:sku,area:'1_2_3_0',num:'1'}));
 class XHR{
  open(method,url){this.method=method;this.url=url;this.headers={}}
  setRequestHeader(k,v){this.headers[k]=v}
  getResponseHeader(){return null}
  send(){requests.push(this);if(mode==='pending')return;if(mode==='network'){queueMicrotask(()=>this.onerror());return}if(mode==='timeout'){queueMicrotask(()=>this.ontimeout());return}queueMicrotask(()=>{this.status=mode==='refused'?403:200;const id=JSON.parse(new URL(this.url).searchParams.get('body')).skuId;this.responseText=this.status===403?'':JSON.stringify(raw(id));this.onload()})}
  abort(){this.onabort?.()}
 }
 const c={location:{hostname:'item.jd.com',href:'https://item.jd.com/'+sku+'.html?pcdk=page-device-context&sdx=page-source&soaRate=page-rate'},performance:{getEntriesByType:()=>[{name:native}]},Date,URL,JSON,Promise,encodeURI,encodeURIComponent,AbortController,XMLHttpRequest:XHR,queueMicrotask,setTimeout,clearTimeout,PSign:{sign:async p=>({...p,h5st:'normal-page-signature'})},SHA256:()=> 'mocksha',getJsToken:f=>f({jsToken:'in-memory'})};c.window=c;
 return {c:vm.createContext(c),requests};
}
const settle=()=>new Promise(r=>setImmediate(r));
test('XHR mirrors current page context headers and exact body/scval identity',async()=>{
 const {c,requests}=makeContext();vm.runInContext(startExpression(sku),c);await settle();
 const result=JSON.parse(vm.runInContext(readExpression,c));assert.equal(result.ok,true);assert.equal(result.data.pp,'9.25');
 assert.equal(requests.length,1);const x=requests[0];assert.equal(x.withCredentials,true);assert.equal(x.method,'GET');assert.equal(x.headers['X-Skuid-Param'],'page-device-context');assert.equal(x.headers['x-sdx'],'page-source');assert.equal(x.headers.soaRate,'page-rate');assert.equal(x.headers['Content-Type'],'application/x-www-form-urlencoded');assert.equal(x.timeout,15000);
 const u=new URL(x.url);assert.equal(u.searchParams.get('scval'),sku);assert.equal(JSON.parse(u.searchParams.get('body')).skuId,sku);
 assert.ok(!JSON.stringify(result).includes('in-memory'));
});
test('same page can request a second SKU without navigation or stale response',async()=>{
 const {c,requests}=makeContext();vm.runInContext(startExpression(sku),c);await settle();const next='10000000000002';vm.runInContext(startExpression(next),c);await settle();
 const r=JSON.parse(vm.runInContext(readExpression,c));assert.equal(r.ok,true);assert.equal(r.data.responseSku,next);assert.equal(requests.length,2);
});
for(const [mode,reason] of [['timeout','REQUEST_TIMEOUT'],['network','NETWORK_ERROR'],['refused','HTTP_403_REFUSED']]){
 test(mode+' terminates once without implicit business retry',async()=>{const {c,requests}=makeContext(mode);vm.runInContext(startExpression(sku),c);await settle();const r=JSON.parse(vm.runInContext(readExpression,c));assert.equal(r.phase,'DONE');assert.equal(r.reason,reason);assert.equal(requests.length,1)})
}
test('abort transitions pending native XHR into a resolved job',async()=>{
 const {c,requests}=makeContext('pending');vm.runInContext(startExpression(sku),c);await settle();vm.runInContext(abortExpression,c);const r=JSON.parse(vm.runInContext(readExpression,c));assert.equal(r.phase,'DONE');assert.equal(r.reason,'REQUEST_ABORTED');assert.equal(requests.length,1);
});
test('foreign source SKU is rejected before dispatch instead of reusing wrong device context',()=>{const {c,requests}=makeContext();c.__jdNativeRequestContext={allowedSkuIds:[sku]};const r=JSON.parse(vm.runInContext(startExpression('10000000000002'),c));assert.equal(r.reason,'SOURCE_PRODUCT_CONTEXT_MISMATCH');assert.equal(requests.length,0)});
