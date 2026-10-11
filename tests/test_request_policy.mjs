import {test} from 'node:test';import assert from 'node:assert/strict';
import {classifyResponse, project, validate, RateGate} from '../scripts/request_policy.mjs';
const raw=()=>({isLogin:true,pageConfigVO:{skuid:'10000000000001'},skuHeadVO:{skuTitle:'商品'},bestPromotion:{purchasePrice:'8'},price:{p:'10'},wareInfoReadMap:{realSpuId:'123'},mainImageVO:{carouselArea:[{imageUrl:'jfs/x.jpg'}]},colorSizeVO:{colorSizeList:[{dim:1,privateField:'secret',buttons:[{no:'1',text:'A',skuId:'10000000000001',skuList:['10000000000001'],privateField:'secret'}]}]},userInfo:{pin:'secret'},token:'secret'});
test('403 classified as refusal not assumed timed rate limit',()=>assert.equal(classifyResponse(403,'',null).reason,'HTTP_403_REFUSED'));
test('429 honors server retry after but halts current run',()=>assert.equal(classifyResponse(429,'',null,'120').retryAfter,'120'));
test('HTML challenge with HTTP 200 does not become successful response',()=>assert.equal(classifyResponse(200,'<html>京东验证</html>',null).reason,'VERIFICATION_REQUIRED'));
test('login expiration stops',()=>assert.equal(classifyResponse(200,'', {...raw(),isLogin:false}).reason,'LOGIN_REQUIRED'));
test('original price never fills missing arrival price',()=>assert.throws(()=>validate('10000000000001',project({...raw(),bestPromotion:{}})),/ARRIVAL_PRICE_MISSING/));
test('response SKU is required and exact',()=>{assert.throws(()=>validate('2',project(raw())),/SKU_ID_MISMATCH/);const d=project(raw());d.responseSku='';assert.throws(()=>validate('1',d),/SKU_ID_MISSING/)});
test('nested personal or unneeded data removed',()=>{const d=project(raw());const s=JSON.stringify(d);assert.ok(!s.includes('secret'));assert.equal(d.colorSize[0].buttons[0].text,'A')});
test('only one in flight and release controls next dispatch',()=>{const g=new RateGate(6000);g.begin(0);assert.throws(()=>g.begin(6000),/REQUEST_IN_FLIGHT/);g.end(2000);assert.equal(g.wait(5000),3000);assert.equal(g.wait(8000),0)});
test('uncertain request permanently halts gate',()=>{const g=new RateGate(6000);g.begin(0);g.halt('REQUEST_RESULT_UNKNOWN');assert.throws(()=>g.begin(7000),/HALTED/)});

test('explicit unavailable response is item error not login expiration',()=>assert.equal(classifyResponse(200,'',{skuHeadVO:{skuTitle:'商品'},pageConfigVO:{isOver:true},itemOverVO:{itemOverTip:'商品已下架'}}).reason,'PRODUCT_UNAVAILABLE'));
test('unproven missing login stays global unknown',()=>assert.equal(classifyResponse(200,'',{skuHeadVO:{skuTitle:'商品'}}).reason,'LOGIN_STATE_UNKNOWN'));

test('front end explicitly labeled final price is accepted without bestPromotion',()=>{const j={...raw(),bestPromotion:{},warePriceGatherVO:{priceItemList:[{price:'9.25',priceType:'finalPrice',priceLabelList:[{labelTxt:'到手价'}]},{price:'10',priceType:'jdPrice'}]}};assert.equal(project(j).pp,'9.25');assert.equal(project(j).priceSource,'warePriceGatherVO.finalPrice')});
test('front end ordinary jdPrice never substitutes arrival',()=>{const j={...raw(),bestPromotion:{},warePriceGatherVO:{priceItemList:[{price:'10',priceType:'jdPrice'}]}};assert.equal(project(j).pp,undefined)});
test('crossed out final price is not active arrival price',()=>{for(const hitLine of [true,1,'1']){const j={...raw(),bestPromotion:{},warePriceGatherVO:{priceItemList:[{price:'10',priceType:'finalPrice',hitLine}]}};assert.equal(project(j).pp,undefined)}});
test('current displayed finalPrice takes precedence over different legacy promotion',()=>{const j={...raw(),warePriceGatherVO:{priceItemList:[{price:'7.25',priceType:'finalPrice',hitLine:false}]}};assert.equal(project(j).pp,'7.25');assert.equal(project(j).priceSource,'warePriceGatherVO.finalPrice')});
