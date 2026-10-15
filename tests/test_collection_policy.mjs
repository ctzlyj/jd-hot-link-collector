import {test} from 'node:test';import assert from 'node:assert/strict';
import {parseOptions,shouldRequest,PRICE_RECHECK_VERSION,unresolvedPrices,waitUntilNext,partialRecheckEvidence} from '../scripts/collection_policy.mjs';
test('defaults are bounded and run flag survives preload argv changes',()=>{
 const p=parseOptions(['--run','--root=D:/x']);assert.equal(p.interval,30000);assert.equal(p.maxRequests,20);assert.equal(p.runRequested,true);
});
test('invalid limits cannot disable throttle or run indefinitely',()=>{
 for(const arg of ['--interval-ms=NaN','--interval-ms=0','--interval-ms=6000','--max-requests=NaN','--max-requests=0','--max-requests=21'])assert.throws(()=>parseOptions([arg,'--root=D:/x']),/INVALID_REQUEST/);
assert.throws(()=>parseOptions(['--run']),/ROOT_REQUIRED/);
});
test('complete cached price is never requested again',()=>assert.equal(shouldRequest({validCache:true,recheckPrices:true}),false));
test('main phase keeps partial data for SKU expansion without requerying',()=>assert.equal(shouldRequest({partialCache:{},recheckPrices:false}),false));
test('supplement phase retries old missing price only once per extraction version',()=>{
 assert.equal(shouldRequest({partialCache:{},recheckPrices:true}),true);
 assert.equal(shouldRequest({partialCache:{priceRecheckVersion:PRICE_RECHECK_VERSION,priceRecheckedAt:'2026-10-13T00:00:00Z'},recheckPrices:true}),false);
 assert.equal(shouldRequest({partialCache:{priceRecheckVersion:PRICE_RECHECK_VERSION},recheckPrices:true}),true);
});
test('ordinary snapshot never falsely records a completed supplement pass',()=>{
 assert.deepEqual(partialRecheckEvidence(false,{},'now'),{});
 assert.deepEqual(partialRecheckEvidence(true,{},'now'),{priceRecheckVersion:PRICE_RECHECK_VERSION,priceRecheckedAt:'now'});
 assert.deepEqual(partialRecheckEvidence(false,{priceRecheckVersion:PRICE_RECHECK_VERSION,priceRecheckedAt:'old'},'new'),{priceRecheckVersion:PRICE_RECHECK_VERSION,priceRecheckedAt:'old'});
});
test('resolved partial files do not keep batch pending',()=>assert.equal(unresolvedPrices([{data:{responseSku:'123'}}],new Set(['123'])).length,0));
test('spacing spans recovery probe and separate collector runs',()=>assert.equal(waitUntilNext(11000,10000,30000),29000));
test('documented space-separated root and paths containing equals are accepted',()=>{assert.equal(parseOptions(['--root','D:/path=folder','--run']).root,'D:/path=folder');assert.equal(parseOptions(['--root=D:/path=folder']).root,'D:/path=folder')});
