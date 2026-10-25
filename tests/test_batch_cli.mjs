/** Run the real CLI against an offline browser fixture; do not contact JD. */
import {test} from 'node:test';import assert from 'node:assert/strict';
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import {spawnSync} from 'node:child_process';import {fileURLToPath} from 'node:url';
const scripts=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../scripts');
function fixture(){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'jd-batch-contract-')),stage=path.join(root,'.collector_state'),runtime=path.join(root,'runtime');fs.mkdirSync(stage);fs.mkdirSync(runtime);
 const first='10000000000001',second='20000000000001';
 const data=id=>({isLogin:true,pageConfigVO:{skuid:id},skuHeadVO:{skuTitle:id.startsWith('1')?'product one':'product two'},bestPromotion:{purchasePrice:'10'},warePriceGatherVO:{priceItemList:[{priceType:'finalPrice',price:id.endsWith('02')?'8.25':'9.25'}]},wareInfoReadMap:{realSpuId:id.slice(0,4)},mainImageVO:{carouselArea:[{imageUrl:'jfs/'+id+'.jpg'}]},colorSizeVO:{colorSizeList:[{dim:1,buttons:[{no:2,text:'secondary',skuId:id.slice(0,-2)+'02'},{no:1,text:'main',skuId:id.slice(0,-2)+'01'}]}]}});
 const products={};for(const id of [first,'10000000000002',second,'20000000000002'])products[id]=data(id);
 fs.writeFileSync(path.join(runtime,'fixture.json'),JSON.stringify(products));
 fs.writeFileSync(path.join(runtime,'main.js'),'');
 fs.writeFileSync(path.join(runtime,'preload.mjs'),`const realNow=Date.now;let clock=realNow();Date.now=()=>clock;globalThis.setTimeout=(fn,ms)=>{clock+=Number(ms)||0;queueMicrotask(fn);return 1};process.argv[1]=${JSON.stringify(path.join(runtime,'main.js'))};`);
 fs.writeFileSync(path.join(runtime,'page.js'),`import fs from 'node:fs';import path from 'node:path';import vm from 'node:vm';const data=JSON.parse(fs.readFileSync(new URL('./fixture.json',import.meta.url),'utf8'));const contexts=new Map();const trace=[];const tracePath=new URL('./trace.json',import.meta.url);function log(x){trace.push(x);fs.writeFileSync(tracePath,JSON.stringify(trace))}let page=0;export function navigate(tab,url){const id=new URL(url).pathname.match(/([0-9]+)[.]html/)[1];contexts.set(tab,{id,url,capture:false,raw:data[id]});log({navigation:id})}export class Page{constructor(){}setActivePage(p){this.tab=p}async newTab(){const tab=(++page).toString(16).padStart(32,'0').toUpperCase();contexts.set(tab,{});this.tab=tab;log({newTab:tab});return tab}async startNetworkCapture(){contexts.get(this.tab).capture=true;return true}async readNetworkCapture(){const c=contexts.get(this.tab);if(!c.capture||!c.raw)return [];const raw=c.raw;c.raw=null;const request='https://api.m.jd.com/?functionId=pc_detailpage_wareBusiness&appid=pc-item-soa&client=pc&clientVersion=1.0.0&h5st=normal&body='+encodeURIComponent(JSON.stringify({skuId:c.id,area:'1_2_3_0',num:'1'}));return [{url:request,method:'GET',responseStatus:200,responsePreview:JSON.stringify(raw),requestHeaders:{'X-Skuid-Param':'page-'+c.id}}]}async closeTab(tab){log({closed:tab});contexts.delete(tab)}async evaluate(s){const c=contexts.get(this.tab);if(!c.vm){const parent=c;class XHR{open(method,url){this.url=url;this.headers={}}setRequestHeader(k,v){this.headers[k]=v}getResponseHeader(){return null}send(){const id=JSON.parse(new URL(this.url).searchParams.get('body')).skuId;log({request:id,source:parent.id,headers:this.headers,timeout:this.timeout});this.status=200;this.responseText=JSON.stringify(data[id]);this.onload()}abort(){this.onabort?.()}}const v={window:null,location:{hostname:'item.jd.com',pathname:new URL(c.url).pathname,href:c.url},document:{readyState:'complete',title:'fixture'},performance:{getEntriesByType:()=>[{name:'https://api.m.jd.com/?functionId=pc_detailpage_wareBusiness',duration:1}]},XMLHttpRequest:XHR,PSign:{sign:async()=>({h5st:'signed'})},SHA256:()=> 'sha',getJsToken:f=>f({jsToken:'memory'}),Date,JSON,URL,Promise,encodeURI,encodeURIComponent,setTimeout,clearTimeout};v.window=v;c.vm=vm.createContext(v)}return vm.runInContext(s,c.vm)}}`);
 fs.writeFileSync(path.join(runtime,'daemon-client.js'),`import {navigate,Page} from './page.js';export async function sendCommandFull(action,p){if(action!=='navigate')throw Error('unexpected action');navigate(p.page,p.url);const page=new Page();page.setActivePage(p.page);await page.startNetworkCapture();return {page:p.page}}`);
 fs.writeFileSync(path.join(stage,'browser_context.json'),JSON.stringify({session:'offline-test',tab:'A'.repeat(32),idleTimeout:86400,windowMode:'background',probeSku:first,wcli:{main:path.join(runtime,'main.js'),preload:path.join(runtime,'preload.mjs'),page:path.join(runtime,'page.js')}}));
 fs.writeFileSync(path.join(stage,'keyword_tasks.json'),JSON.stringify({keyword:[{pid:first,row:3},{pid:second,row:4}]}));
 return {root,stage,runtime,first,second};
}
function run(f,args=[]){return spawnSync(process.execPath,[path.join(scripts,'collect_signed.mjs'),'--run','--root',f.root,'--max-requests=20',...args],{encoding:'utf8',timeout:20000})}
test('real batch CLI loads context once per product and calls SKU interfaces with that context',()=>{
 const f=fixture(),r=run(f);assert.equal(r.status,0,r.stderr+'\n'+r.stdout);const state=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));
 assert.equal(state.state,'DATA_COMPLETE');assert.equal(state.requests,4);assert.equal(state.navigations,2);assert.equal(state.successful,4);
 const trace=JSON.parse(fs.readFileSync(path.join(f.runtime,'trace.json'),'utf8'));assert.deepEqual(trace.filter(x=>x.navigation).map(x=>x.navigation),[f.first,f.second]);const requests=trace.filter(x=>x.request);assert.equal(requests.length,2);for(const x of requests)assert.equal(x.headers['X-Skuid-Param'],'page-'+x.source);
 for(const id of [f.first,'10000000000002',f.second,'20000000000002']){const saved=JSON.parse(fs.readFileSync(path.join(f.stage,'data',id+'.json'),'utf8'));assert.equal(saved.data.responseSku,id);assert.ok(saved.data.pp);assert.equal(saved.data.priceSource,'warePriceGatherVO.finalPrice')}
});
test('real CLI resumes native response cache without redownloading finished products',()=>{
 const f=fixture();assert.equal(run(f).status,0);const r=run(f);assert.equal(r.status,0,r.stderr);const s=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));assert.equal(s.requests,0);assert.equal(s.products,0);assert.equal(s.state,'DATA_COMPLETE');
});
test('main-only covers all source products before consuming sibling SKU requests',()=>{
 const f=fixture(),r=run(f,['--main-only']);assert.equal(r.status,0,r.stderr);const state=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));
 assert.equal(state.state,'MAIN_SCAN_COMPLETE');assert.equal(state.products,2);assert.equal(state.requests,2);assert.equal(state.successful,2);
 const trace=JSON.parse(fs.readFileSync(path.join(f.runtime,'trace.json'),'utf8'));assert.equal(trace.filter(x=>x.request).length,0);
 assert.equal(run(f,['--main-only']).status,0);const again=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));assert.equal(again.requests,0);
});
test('full sweep following main scan still fetches all genuine SKU prices',()=>{
 const f=fixture();assert.equal(run(f,['--main-only']).status,0);const r=run(f);assert.equal(r.status,0,r.stderr);
 const state=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));assert.equal(state.state,'DATA_COMPLETE');assert.equal(state.successful,2);
 for(const id of ['10000000000002','20000000000002'])assert.ok(fs.existsSync(path.join(f.stage,'data',id+'.json')));
});
test('deterministic spec-matrix failure is isolated to the failure list without halting the batch',()=>{
 const f=fixture();
 const third='30000000000001';
 const file=path.join(f.runtime,'fixture.json');const data=JSON.parse(fs.readFileSync(file,'utf8'));
 const raw=data[f.first];
 data[third]={...raw,pageConfigVO:{skuid:third},skuHeadVO:{skuTitle:'matrix broken'},wareInfoReadMap:{realSpuId:third.slice(0,4)},colorSizeVO:{colorSizeList:[
  {dim:1,buttons:[{no:1,text:'A',skuId:third.slice(0,-2)+'01',skuList:[third.slice(0,-2)+'01']}]},
  {dim:2,buttons:[{no:1,text:'B',skuId:third.slice(0,-2)+'01',skuList:[third.slice(0,-2)+'01']}]},
  {dim:3,buttons:[{no:1,text:'C',skuId:third.slice(0,-2)+'01',skuList:[third.slice(0,-2)+'01']}]}]}};
 fs.writeFileSync(file,JSON.stringify(data));
 fs.writeFileSync(path.join(f.stage,'keyword_tasks.json'),JSON.stringify({keyword:[{pid:f.first,row:3},{pid:third,row:4},{pid:f.second,row:5}]}));
 const r=run(f);assert.equal(r.status,0,r.stderr+'\n'+r.stdout);
 const state=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));
 assert.equal(state.state,'DATA_COMPLETE');assert.equal(state.unavailable,1);
 const err=JSON.parse(fs.readFileSync(path.join(f.stage,'errors',third+'.json'),'utf8'));
 assert.equal(err.reason,'PRODUCT_UNAVAILABLE');assert.equal(err.evidence.failureType,'SKU_MATRIX_INVALID');
 for(const id of [f.first,f.second])assert.ok(fs.existsSync(path.join(f.stage,'data',id+'.json')));
 assert.equal(run(f).status,0);
 const resumed=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));assert.equal(resumed.unavailable,1);assert.equal(resumed.requests,0);
});
test('missing prices get one real supplementary pass, never ordinary-price fallback',()=>{
 const f=fixture();const file=path.join(f.runtime,'fixture.json');const data=JSON.parse(fs.readFileSync(file,'utf8'));
 for(const raw of Object.values(data)){delete raw.bestPromotion;raw.warePriceGatherVO={priceItemList:[{priceType:'jdPrice',price:'9.25'}]};}
 fs.writeFileSync(file,JSON.stringify(data));
 let r=run(f);assert.equal(r.status,0,r.stderr);let s=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));assert.equal(s.state,'DATA_COLLECTED_PRICE_PENDING');assert.equal(s.requests,4);
 let saved=JSON.parse(fs.readFileSync(path.join(f.stage,'partial_data',f.first+'.json'),'utf8'));assert.equal(saved.priceRecheckedAt,undefined);assert.equal(fs.existsSync(path.join(f.stage,'data',f.first+'.json')),false);
 assert.equal(run(f).status,0);s=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));assert.equal(s.requests,0);
 r=run(f,['--recheck-prices']);assert.equal(r.status,0,r.stderr);s=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));assert.equal(s.requests,4);
 saved=JSON.parse(fs.readFileSync(path.join(f.stage,'partial_data',f.first+'.json'),'utf8'));assert.ok(saved.priceRecheckedAt);
 assert.equal(run(f,['--recheck-prices']).status,0);s=JSON.parse(fs.readFileSync(path.join(f.stage,'runner_state.json'),'utf8'));assert.equal(s.requests,0);
});

test('one task tab is reused for the whole round',()=>{
 const f=fixture();const r=run(f);assert.equal(r.status,0,r.stderr);
 const trace=JSON.parse(fs.readFileSync(path.join(f.runtime,'trace.json'),'utf8'));
 assert.equal(trace.filter(x=>x.newTab).length,1,'exactly one task tab per round');
 assert.equal(trace.filter(x=>x.closed).length,1,'the reused tab is closed when the round ends');
 assert.equal(trace.filter(x=>x.navigation).length,2,'both products load in that tab');
});
