/** Pure task-local scheduling rules; no browser calls or credentials. */
export const PRICE_RECHECK_VERSION = 'frontend-final-price-v1';
export function parseOptions(argv) {
 const options=new Map(argv.filter(x=>x.includes('=')).map(x=>x.split('=',2)));
 const root=options.get('--root');
 if(!root)throw Error('ROOT_REQUIRED');
 const interval=Number(options.get('--interval-ms')||30000);
 const maxRequests=Number(options.get('--max-requests')||20);
 if(!Number.isFinite(interval)||interval<30000)throw Error('INVALID_REQUEST_INTERVAL');
 if(!Number.isInteger(maxRequests)||maxRequests<1||maxRequests>20)throw Error('INVALID_REQUEST_LIMIT');
 return {runRequested:argv.includes('--run'),recheckPrices:argv.includes('--recheck-prices'),interval,maxRequests,root};
}
export function shouldRequest({validCache,partialCache,recheckPrices}) {
 if(validCache)return false;
 if(!partialCache)return true;
 return recheckPrices && partialCache.priceRecheckVersion!==PRICE_RECHECK_VERSION;
}
export function unresolvedPrices(partials,validSkus){
 return partials.filter(x=>!validSkus.has(String(x.data?.responseSku)));
}
export function waitUntilNext(now,lastFinished,interval){
 return Math.max(0,(Number(lastFinished)||0)+interval-now);
}
