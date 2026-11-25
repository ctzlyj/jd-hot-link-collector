/** Shop-level on-sale SKU counting: storefront product list + per-product SKU matrix. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {taskContext} from './task_context.mjs';

export const SHOP_PAGE_SIZE = 30; // the storefront API rejects larger pages ("pageSize过大")

/** SKU count of one product from its native colorSize matrix (a single-SKU product counts 1). */
export function countMatrixSkus(colorSize) {
  let n = 0;
  for (const dim of Array.isArray(colorSize) ? colorSize : []) {
    for (const button of dim?.buttons || []) n++;
  }
  return n || 1;
}

/** The storefront front end only exposes a bounded number of pages per query. */
export const SHOP_PAGE_LIMIT = 80;
/** Field names the storefront API has been observed to use for its category list. */
export const CATEGORY_KEYS = ['cateList', 'categoryList', 'catList', 'shopCategoryList', 'cateInfoList'];
/** Body field used to restrict a storefront query to one category shard. */
export const SHARD_BODY_FIELD = 'catId';

/** Category shards advertised by a shop page response (id + name), if any. */
export function extractCategories(json) {
  const result = json?.result ?? json;
  for (const key of CATEGORY_KEYS) {
    const list = result?.[key];
    if (!Array.isArray(list) || !list.length) continue;
    const cats = list.map((c) => ({id: String(c.catId ?? c.categoryId ?? c.id ?? ''),
                                   name: String(c.name || c.cateName || '')}))
                     .filter((c) => /^\d+$/.test(c.id));
    if (cats.length) return cats;
  }
  return [];
}

/** Parse one whx_searchWare response body into the product ids of that page. */
export function parseShopPage(text) {
  let json = null;
  try { json = JSON.parse(text); } catch { return {ok: false, reason: 'SHOP_PAGE_NOT_JSON'}; }
  const result = json?.result;
  if (!result) return {ok: false, reason: 'SHOP_PAGE_FAILED', head: String(text || '').slice(0, 120)};
  return {
    ok: true,
    total: Number(result.totalCount) || 0,
    shopName: result.shopName || '',
    ids: (result.wareInfo || []).map((w) => String(w.wareId)),
    categories: extractCategories(json),
  };
}

/** Merge shard ids after the base list, keeping first-seen order and auditing duplicates. */
export function mergeShardIds(baseIds, shardIds) {
  const seen = new Set((baseIds || []).map(String));
  const ids = [...seen];
  const duplicates = [];
  for (const id of (shardIds || []).map(String)) {
    if (seen.has(id)) { duplicates.push(id); continue; }
    seen.add(id); ids.push(id);
  }
  return {ids, duplicates};
}

/** Pure summary of one shop enumeration: honest cap flags and shard bookkeeping. */
export function shopEnumerationSummary(base, shardRuns) {
  if (base.note) {
    return {ids: base.ids, total: base.total, note: base.note, pagingCapExceeded: false,
            incomplete: false, shards: null, shardDuplicates: 0};
  }
  const cap = Number(base.total || 0) > (base.ids || []).length;
  if (!cap) {
    return {ids: base.ids, total: base.total, note: null, pagingCapExceeded: false,
            incomplete: false, shards: null, shardDuplicates: 0};
  }
  if (!(base.categories || []).length) {
    return {ids: base.ids, total: base.total, note: 'PAGING_CAP_EXCEEDED', pagingCapExceeded: true,
            incomplete: true, shards: null, shardDuplicates: 0};
  }
  const shards = {};
  const shardIds = [];
  for (const run of shardRuns || []) {
    shards[run.id] = run.note ? {note: run.note} : {products: run.ids.length, total: run.total};
    if (!run.note) shardIds.push(...run.ids);
  }
  const merged = mergeShardIds(base.ids, shardIds);
  return {ids: merged.ids, total: base.total, note: null, pagingCapExceeded: true,
          incomplete: merged.ids.length < Number(base.total || 0), shards,
          shardDuplicates: merged.duplicates.length};
}

export function chunk(list, size) {
  const out = [];
  for (let i = 0; i < list.length; i += size) out.push(list.slice(i, i + size));
  return out;
}

const SIGN_EXPRESSION = `
window.__shopPage = async function(shopId, pageIdx, pageSize, catId){
  const payload={shopId,mtest:"",pvid:"",pageIdx,pageSize,sourceRpc:"shop_app_home_bottom",queryKey:"",queryMessage:"",markTag:"1",searchType:"3",pageId:"Shop_NavigationProductsList"};
  if(catId)payload.catId=String(catId);
  const body=JSON.stringify(payload);
  const t=Date.now();
  const signed=await window.PSign.sign({appid:"mall_jd_com",clientVersion:"11.0.0",client:"pc",t,body:window.SHA256(body),functionId:"whx_searchWare"});
  const params=new URLSearchParams();
  params.set("functionId","whx_searchWare");params.set("body",body);params.set("t",String(t));params.set("appid","mall_jd_com");params.set("clientVersion","11.0.0");params.set("client","pc");
  params.set("area","1_2809_51226_0");params.set("uuid","17839145963031918689488");params.set("xAPIClientLanguage","zh_CN");
  params.set("h5st",signed.h5st);
  const r=await fetch("https://api.m.jd.com/client.action?"+params.toString(),{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},credentials:"include",body:params.toString()});
  return await r.text();
};
'undefined'`;

const COUNT_EXPRESSION = `
window.__countSkus = async function(skus){
  const out=[];const saved=window.__jdNativeRequestContext;
  const native=saved?.url||performance.getEntriesByType('resource').map(x=>x.name).reverse().find(x=>{try{const u=new URL(x);return u.hostname==='api.m.jd.com'&&u.searchParams.get('functionId')==='pc_detailpage_wareBusiness'&&u.searchParams.has('h5st')}catch{return false}});
  if(!native)return JSON.stringify({error:'NO_NATIVE'});
  for(const sku of skus){
    let done=false;
    for(let attempt=0;attempt<2&&!done;attempt++){
      try{
        const u=new URL(native),body=JSON.parse(u.searchParams.get('body'));body.skuId=sku;
        const rawBody=JSON.stringify(body),t=Date.now();
        const token=await new Promise(r=>window.getJsToken(v=>r(v&&v.jsToken||'')));
        const signed=await window.PSign.sign({appid:u.searchParams.get('appid'),clientVersion:u.searchParams.get('clientVersion'),client:u.searchParams.get('client'),t,body:window.SHA256(rawBody),functionId:'pc_detailpage_wareBusiness'});
        const values=Object.fromEntries(u.searchParams);values.body=rawBody;values.scval=sku;values.t=String(t);values.h5st=encodeURI(signed.h5st);values['x-api-eid-token']=token;
        const enc=v=>encodeURIComponent(v).replace(/%3A/gi,':').replace(/%24/g,'$').replace(/%2C/gi,',').replace(/%20/g,'+').replace(/%5B/gi,'[').replace(/%5D/gi,']');
        const url=u.origin+u.pathname+'?'+Object.entries(values).map(([k,v])=>enc(k)+'='+enc(v)).join('&');
        const res=await new Promise(resolve=>{const xhr=new XMLHttpRequest();xhr.open('GET',url,true);xhr.withCredentials=true;xhr.timeout=15000;xhr.setRequestHeader('Accept','application/json, text/plain, */*');xhr.onload=()=>resolve({status:xhr.status,text:xhr.responseText});xhr.onerror=()=>resolve({status:0,text:''});xhr.ontimeout=()=>resolve({status:-1,text:''});xhr.send(null);});
        let count=null,login=null;
        try{const j=JSON.parse(res.text);login=j.isLogin===true;const cs=j.colorSizeVO&&j.colorSizeVO.colorSizeList||[];let n=0;for(const d of cs)for(const b of(d.buttons||[]))n++;count=n||1;}catch(e){}
        if(res.status===200&&count!==null){out.push({sku,status:res.status,login,count});done=true;}
        else if(attempt===1){out.push({sku,status:res.status,login,count});done=true;}
        else{await new Promise(r=>setTimeout(r,300));}
      }catch(e){if(attempt===1)out.push({sku,error:String(e).slice(0,80)});else await new Promise(r=>setTimeout(r,300));}
    }
  }
  return JSON.stringify(out);
};
'undefined'`;

function parseArgs(argv) {
  const options = new Map();
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.includes('=')) { const at = arg.indexOf('='); options.set(arg.slice(0, at), arg.slice(at + 1)); }
    else if (arg.startsWith('--') && argv[i + 1] && !argv[i + 1].startsWith('--')) options.set(arg, argv[++i]);
  }
  return options;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const stage = path.resolve(options.get('--state-dir') || '');
  if (!options.get('--state-dir')) throw Error('STATE_DIR_REQUIRED');
  const context = taskContext(stage);
  const output = path.resolve(options.get('--output') || path.join(stage, 'shop_sku_count.json'));
  const workers = Math.max(1, Math.min(4, Number(options.get('--workers') || 3)));
  const chunkSize = Math.max(10, Math.min(80, Number(options.get('--chunk') || 60)));
  const shops = String(options.get('--shops') || '').split(',').map((x) => x.trim()).filter(Boolean);
  if (!shops.length) throw Error('SHOPS_REQUIRED');
  const state = fs.existsSync(output) ? JSON.parse(fs.readFileSync(output, 'utf8')) : {shops: {}};
  const save = () => fs.writeFileSync(output, JSON.stringify(state), 'utf8');

  process.argv[1] = context.wcli.main;
  await import(pathToFileURL(context.wcli.preload).href);
  const {Page} = await import(pathToFileURL(context.wcli.page).href);
  const {sendCommandFull} = await import(pathToFileURL(path.join(path.dirname(context.wcli.page), 'daemon-client.js')).href);
  const owner = new Page(context.session, context.idleTimeout, undefined, 'background');

  const openProductPage = async (sku) => {
    const tab = await owner.newTab(`https://item.jd.com/${sku}.html`);
    const page = new Page(context.session, context.idleTimeout, undefined, 'background');
    page.setActivePage(tab);
    await sendCommandFull('navigate', {url: `https://item.jd.com/${sku}.html`, session: context.session, page: tab, idleTimeout: context.idleTimeout, windowMode: 'background', surface: 'browser'});
    await new Promise((r) => setTimeout(r, 5000));
    return {tab, page};
  };

  // Phase 1: product ids per shop. The shop page itself has no PSign SDK, so the
  // storefront API is signed from a product page context.
  const sign = await openProductPage(context.probeSku);
  try {
    await sign.page.evaluate(SIGN_EXPRESSION);
    for (const shopId of shops) {
      const rec = state.shops[shopId] || {ids: null, results: {}, done: false};
      state.shops[shopId] = rec;
      if (rec.ids && rec.ids.length) continue;
      const enumerate = async (catId) => {
        const ids = [];
        let total = 0;
        let note = null;
        let categories = [];
        let pageIdx = 1;
        while (pageIdx <= SHOP_PAGE_LIMIT) {
          const args = [JSON.stringify(shopId), pageIdx, SHOP_PAGE_SIZE];
          if (catId) args.push(JSON.stringify(String(catId)));
          const text = await sign.page.evaluate(`window.__shopPage(${args.join(',')})`);
          const parsed = parseShopPage(text);
          if (!parsed.ok) { note = parsed.reason; break; }
          total = parsed.total;
          if (parsed.shopName) rec.name = parsed.shopName;
          if (pageIdx === 1) categories = parsed.categories || [];
          if (!parsed.ids.length) break;
          ids.push(...parsed.ids);
          if (ids.length >= total) break;
          pageIdx++;
          await new Promise((r) => setTimeout(r, 150));
        }
        return {ids, total, note, categories};
      };
      const base = await enumerate(null);
      let shardRuns = [];
      if (!base.note && Number(base.total || 0) > base.ids.length && base.categories.length) {
        // The front end caps paging; per-category shards enumerate the long tail.
        for (const cat of base.categories) {
          const run = await enumerate(cat.id);
          shardRuns.push({id: cat.id, ids: run.ids, note: run.note, total: run.total});
        }
      }
      const summary = shopEnumerationSummary(base, shardRuns);
      rec.ids = summary.ids;
      rec.productTotal = summary.total;
      rec.note = summary.note || (summary.ids.length ? undefined : 'EMPTY_SHOP');
      rec.pagingCapExceeded = summary.pagingCapExceeded || undefined;
      rec.incomplete = summary.incomplete || undefined;
      if (summary.shards) rec.shards = summary.shards;
      if (summary.shardDuplicates) rec.shardDuplicates = summary.shardDuplicates;
      save();
      console.log(JSON.stringify({shopId, name: rec.name || '', products: summary.ids.length,
                                   total: summary.total, pagingCapExceeded: summary.pagingCapExceeded,
                                   incomplete: summary.incomplete}));
    }
  } finally {
    try { await owner.closeTab(sign.tab); } catch {}
  }

  // Phase 2: per-product SKU matrix counts, a few pages in parallel. Three workers
  // are stable; five produced intermittent browser-command drops in testing.
  const queue = [];
  for (const shopId of shops) {
    const rec = state.shops[shopId];
    if (!rec?.ids?.length) continue;
    const pending = rec.ids.filter((id) => !rec.results[id]);
    if (pending.length) queue.push({shopId, pending});
  }
  const workerLoop = async () => {
    let session = null;
    try {
      while (true) {
        const job = queue.find((q) => q.pending.length);
        if (!job) break;
        const batch = job.pending.splice(0, chunkSize);
        if (!batch.length) continue;
        if (!session) {
          for (let attempt = 0; attempt < 3 && !session; attempt++) {
            try {
              const opened = await openProductPage(batch[0]);
              await opened.page.evaluate(COUNT_EXPRESSION);
              session = opened;
            } catch {
              try { if (session) await owner.closeTab(session.tab); } catch {}
              session = null;
              await new Promise((r) => setTimeout(r, 1500));
            }
          }
          if (!session) { job.pending.unshift(...batch); await new Promise((r) => setTimeout(r, 2000)); continue; }
        }
        try {
          const text = await session.page.evaluate(`window.__countSkus(${JSON.stringify(batch)})`);
          const rows = JSON.parse(text);
          if (rows?.error) {
            try { await owner.closeTab(session.tab); } catch {}
            session = null;
            job.pending.unshift(...batch);
            continue;
          }
          const rec = state.shops[job.shopId];
          for (const row of rows) rec.results[row.sku] = row;
          save();
        } catch {
          try { await owner.closeTab(session.tab); } catch {}
          session = null;
          job.pending.unshift(...batch);
        }
      }
    } finally {
      if (session) { try { await owner.closeTab(session.tab); } catch {} }
    }
  };
  const running = [];
  for (let i = 0; i < workers; i++) {
    await new Promise((r) => setTimeout(r, 800));
    running.push(workerLoop());
  }
  await Promise.all(running);

  for (const shopId of shops) {
    const rec = state.shops[shopId];
    if (!rec?.ids) continue;
    const rows = Object.values(rec.results);
    rec.productCount = rec.ids.length;
    rec.skuCount = rows.reduce((sum, row) => sum + (row.count || 0), 0);
    rec.missing = rec.ids.filter((id) => !rec.results[id]);
    rec.done = true;
    save();
    console.log(JSON.stringify({shopId, name: rec.name || '', products: rec.productCount, skus: rec.skuCount, missing: rec.missing.length}));
  }
  console.log(JSON.stringify({state: 'SHOP_SKU_DONE', shops: shops.length, output}));
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))) {
  main().catch((error) => { console.error(String(error?.message || error)); process.exitCode = 1; });
}
