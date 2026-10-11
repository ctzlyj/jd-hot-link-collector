/** Safe response contract. No account data, raw request URL, headers, or signatures leave page memory. */
export function classifyResponse(status,text,json,retryAfter=null){
 if(status===401)return{ok:false,reason:'LOGIN_REQUIRED'};
 if(status===403)return{ok:false,reason:'HTTP_403_REFUSED'};
 if(status===429)return{ok:false,reason:'HTTP_429_RATE_LIMIT',retryAfter:retryAfter&&/^[\dA-Za-z,: -]{1,80}$/.test(retryAfter)?retryAfter:null};
 if(/cfe\.m\.jd\.com|京东验证|验证一下|risk_handler/.test(text)&&!json?.skuHeadVO)return{ok:false,reason:'VERIFICATION_REQUIRED'};
 if(status!==200)return{ok:false,reason:'HTTP_'+status};
 if(!json||!json.skuHeadVO)return{ok:false,reason:'INVALID_RESPONSE'};
 if(json.isLogin!==true){if(json.isLogin===undefined&&(json.pageConfigVO?.isOver===true||json.itemOverVO?.itemOverTip))return{ok:false,reason:'PRODUCT_UNAVAILABLE'};return{ok:false,reason:json.isLogin===false?'LOGIN_REQUIRED':'LOGIN_STATE_UNKNOWN'}};
 return{ok:true};
}
export function project(j){
 const finalItem=(j.warePriceGatherVO?.priceItemList||[]).find(x=>x.priceType==='finalPrice'&&!x.hitLine);
 return{
 ok:true,login:j.isLogin===true,responseSku:String(j.pageConfigVO?.skuid||''),title:j.skuHeadVO?.skuTitle||'',
 p:j.price?.p,pp:finalItem?finalItem.price:j.bestPromotion?.purchasePrice,priceSource:finalItem?'warePriceGatherVO.finalPrice':'bestPromotion.purchasePrice',frontendPriceItems:(j.warePriceGatherVO?.priceItemList||[]).map(x=>({price:x.price,priceType:x.priceType,hitLine:!!x.hitLine,labels:(x.priceLabelList||[]).map(l=>l.labelTxt||'')})),realSpuId:String(j.wareInfoReadMap?.realSpuId||''),
 crumbs:(j.crumbInfoVO?.crumbs||[]).map(x=>({text:x.text||''})),
 attrs:(j.productAttributeVO?.attributes||[]).map(x=>({labelName:x.labelName||'',labelValue:x.labelValue||''})),
 colorSize:(j.colorSizeVO?.colorSizeList||[]).map(d=>({dim:d.dim,buttons:(d.buttons||[]).map(b=>({no:b.no,text:b.text||'',skuId:b.skuId,skuList:b.skuList||[],fullImageUrl:b.fullImageUrl||''}))})),
 carousel:(j.mainImageVO?.carouselArea||[]).map(x=>({u:x.imageUrl||'',v:(x.videos||[]).map(v=>({p:v.playUrl||'',c:v.cover||''}))}))
};}
export function validate(sku,d){
 if(!d.ok)throw Error('INVALID_RESPONSE');if(!d.login)throw Error('LOGIN_REQUIRED');
 if(!d.responseSku)throw Error('SKU_ID_MISSING');if(d.responseSku!==String(sku))throw Error('SKU_ID_MISMATCH');
 if(!d.title)throw Error('TITLE_MISSING');if(!/^\d+(\.\d+)?$/.test(String(d.pp))||Number(d.pp)<=0)throw Error('ARRIVAL_PRICE_MISSING');
 if(!d.realSpuId)throw Error('DETAIL_ID_MISSING');if(!d.carousel.some(x=>x.u))throw Error('MAIN_IMAGES_MISSING');return d;
}
export class RateGate{
 constructor(interval=6000){this.interval=interval;this.inFlight=false;this.next=0;this.reason=null}
 wait(now){return Math.max(0,this.next-now)}
 begin(now){if(this.reason)throw Error('HALTED:'+this.reason);if(this.inFlight)throw Error('REQUEST_IN_FLIGHT');if(this.wait(now)>0)throw Error('REQUEST_TOO_SOON');this.inFlight=true}
 end(now){this.inFlight=false;this.next=now+this.interval}
 halt(reason){this.reason=reason}
}


