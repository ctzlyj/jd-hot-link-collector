import {test} from 'node:test';import assert from 'node:assert/strict';
import {capturedBusiness,waitNativePage} from '../scripts/native_page.mjs';
const sku='10000000000001';
const response=(id=sku)=>({url:'https://api.m.jd.com/?functionId=pc_detailpage_wareBusiness',method:'GET',responseStatus:200,requestHeaders:{'X-Skuid-Param':'page-context',Cookie:'secret'},responsePreview:JSON.stringify({isLogin:true,pageConfigVO:{skuid:id},skuHeadVO:{skuTitle:'test'},bestPromotion:{purchasePrice:'8'},wareInfoReadMap:{realSpuId:'1'},mainImageVO:{carouselArea:[{imageUrl:'jfs/image.jpg'}]}})});
test('wait does not clear pending capture entries before API loading finished',async()=>{
 let time=0,observations=0,reads=0;
 const page={evaluate:async()=>JSON.stringify({apiFinished:++observations>=3}),readNetworkCapture:async()=>{reads++;return [response()]}};
 const r=await waitNativePage(page,sku,{timeoutMs:5000,now:()=>time,sleep:async ms=>{time+=ms}});assert.equal(r.ok,true);assert.equal(reads,1);assert.equal(observations,3);
});
test('OPTIONS success is not successful product evidence',()=>assert.equal(capturedBusiness([{method:'OPTIONS',responseStatus:200}],sku),null));
test('whitelist excludes credentials and mismatched SKU is never saved',()=>{const r=capturedBusiness([response()],sku);assert.equal(r.context.headers.Cookie,undefined);assert.equal(r.context.headers['X-Skuid-Param'],'page-context');assert.equal(capturedBusiness([response('10000000000002')],sku).reason,'SKU_ID_MISMATCH')});
test('item URL redirected to JD homepage is an unavailable product, not a transport stall',async()=>{
 let time=0,reads=0;
 const page={evaluate:async()=>JSON.stringify({host:'www.jd.com',path:'/',isFrequencyPage:false,isChallenge:false,apiFinished:false}),readNetworkCapture:async()=>{reads++;return []}};
 const r=await waitNativePage(page,sku,{timeoutMs:60000,now:()=>time,sleep:async ms=>{time+=ms}});
 assert.equal(r.ok,false);assert.equal(r.reason,'PRODUCT_UNAVAILABLE_REDIRECT');assert.equal(reads,0);assert.ok(time<10000);
});
test('item pages on item.jd.com never trigger the redirect shortcut',async()=>{
 let time=0;
 const page={evaluate:async()=>JSON.stringify({host:'item.jd.com',path:'/10000000000001.html',isFrequencyPage:false,isChallenge:false,apiFinished:true}),readNetworkCapture:async()=>[response()]};
 const r=await waitNativePage(page,sku,{timeoutMs:5000,now:()=>time,sleep:async ms=>{time+=ms}});assert.equal(r.ok,true);
});
test('genuine platform refusals remain visible',async()=>{let time=0;const p={evaluate:async()=>JSON.stringify({isChallenge:true}),readNetworkCapture:()=>{throw Error('not allowed')}};const r=await waitNativePage(p,sku,{now:()=>time,sleep:async ms=>{time+=ms}});assert.equal(r.reason,'VERIFICATION_REQUIRED')});
test('request-only capture is not classified as platform refusal',()=>assert.equal(capturedBusiness([{url:'request-only'}],sku),null));
test('truncated business evidence fails closed',()=>assert.equal(capturedBusiness([{...response(),responseBodyTruncated:true}],sku).reason,'CAPTURE_BODY_TRUNCATED'));
test('first click with baseline zero waits for its own completed request instead of the initial page request',async()=>{
 let time=0,observations=0,reads=0;
 const page={evaluate:async expression=>{assert.ok(expression.includes('requestState'));return JSON.stringify({apiFinished:true,completed:++observations<3?0:1})},readNetworkCapture:async()=>{reads++;return [response()]}};
 const r=await waitNativePage(page,sku,{afterCount:0,timeoutMs:5000,now:()=>time,sleep:async ms=>{time+=ms}});assert.equal(r.ok,true);assert.equal(reads,1);assert.equal(observations,3);
});
