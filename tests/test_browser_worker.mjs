import {test} from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';
import {startExpression,readExpression,pageStateExpression} from '../scripts/browser_worker.mjs';
const sku='10000000000001';
const native='https://api.m.jd.com/?appid=pc-item-soa&clientVersion=1.0.0&client=pc&functionId=pc_detailpage_wareBusiness&body='+encodeURIComponent(JSON.stringify({skuId:sku,area:'1_2_3_0',num:'1'}))+'&t=1&h5st=normal&uuid=inmemory';
const raw={isLogin:true,pageConfigVO:{skuid:sku},skuHeadVO:{skuTitle:'商品'},bestPromotion:{purchasePrice:'8'},price:{p:'10'},wareInfoReadMap:{realSpuId:'123'},mainImageVO:{carouselArea:[{imageUrl:'jfs/x.jpg'}]}};
function context(fetchImpl,host='item.jd.com'){
 const c={location:{hostname:host},performance:{getEntriesByType:()=>[{name:native}]},Date,URL,AbortController,encodeURI,encodeURIComponent,JSON,Promise,
  PSign:{sign:async x=>({...x,h5st:'SDK签名+测试'})},SHA256:()=> 'mocksha',getJsToken:fn=>fn({jsToken:'memory-token'}),fetch:fetchImpl};c.window=c;return vm.createContext(c);
}
const settle=()=>new Promise(r=>setImmediate(r));
test('existing signed page path creates one request then returns sanitized price',async()=>{
 let count=0;const c=context(async (url,opts)=>{count++;const u=new URL(url);assert.equal(JSON.parse(u.searchParams.get('body')).skuId,sku);assert.equal(u.searchParams.get('scval'),sku);assert.equal(JSON.parse(u.searchParams.get('body')).area,'1_2_3_0');assert.equal(decodeURI(u.searchParams.get('h5st')),'SDK签名+测试');assert.equal(opts.credentials,'include');return{status:200,text:async()=>JSON.stringify({...raw,userInfo:{pin:'never-leave-memory'}}),headers:{get:()=>null}}});
 assert.equal(JSON.parse(vm.runInContext(startExpression(sku),c)).phase,'STARTED');await settle();const out=JSON.parse(vm.runInContext(readExpression,c));assert.equal(count,1);assert.equal(out.data.pp,'8');assert.ok(!JSON.stringify(out).includes('never-leave-memory'));
});
test('challenge prevents any business request',()=>{let n=0;const c=context(()=>n++,'cfe.m.jd.com');assert.equal(JSON.parse(vm.runInContext(startExpression(sku),c)).reason,'VERIFICATION_REQUIRED');assert.equal(n,0)});
test('pending request cannot be dispatched twice',async()=>{let n=0;const c=context(()=>{n++;return new Promise(()=>{})});vm.runInContext(startExpression(sku),c);await settle();assert.equal(JSON.parse(vm.runInContext(startExpression(sku),c)).reason,'REQUEST_IN_FLIGHT');assert.equal(n,1)});
test('403 stops with refusal and never self retries',async()=>{let n=0;const c=context(async()=>{n++;return{status:403,text:async()=>'',headers:{get:()=>null}}});vm.runInContext(startExpression(sku),c);await settle();const j=JSON.parse(vm.runInContext(readExpression,c));assert.equal(j.reason,'HTTP_403_REFUSED');assert.equal(n,1)});
test('no normal signed context means no request',()=>{let n=0;const c=context(()=>n++);c.performance.getEntriesByType=()=>[];assert.equal(JSON.parse(vm.runInContext(startExpression(sku),c)).reason,'NORMAL_REQUEST_CONTEXT_MISSING');assert.equal(n,0)});
test('missing legacy promotion accepts current frontend final price',async()=>{const c=context(async()=>({status:200,text:async()=>JSON.stringify({...raw,bestPromotion:{},warePriceGatherVO:{priceItemList:[{price:'7.25',priceType:'finalPrice'}]}}),headers:{get:()=>null}}));vm.runInContext(startExpression(sku),c);await settle();const j=JSON.parse(vm.runInContext(readExpression,c));assert.equal(j.data.pp,'7.25');assert.equal(j.data.priceSource,'warePriceGatherVO.finalPrice')});
test('missing arrival remains partial and cannot succeed as original price',async()=>{const c=context(async()=>({status:200,text:async()=>JSON.stringify({...raw,bestPromotion:{}}),headers:{get:()=>null}}));vm.runInContext(startExpression(sku),c);await settle();const j=JSON.parse(vm.runInContext(readExpression,c));assert.equal(j.ok,false);assert.equal(j.reason,'ARRIVAL_PRICE_MISSING');assert.equal(j.partialData.p,'10')});
test('frequency-control page is distinct from logged-out or challenge',()=>{const c=context(()=>{},'pc-frequent-pro.pf.jd.com');c.location.pathname='/';c.document={title:'Frequency page'};const s=JSON.parse(vm.runInContext(pageStateExpression(),c));assert.equal(s.isFrequencyPage,true);assert.equal(s.isTaskItem,false);assert.equal(s.isChallenge,false)});

