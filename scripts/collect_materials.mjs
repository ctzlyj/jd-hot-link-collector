/** Material-only collection: one reusable tab, batch native API, no prices. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {taskContext} from './task_context.mjs';
import {openNativePage} from './native_page.mjs';
import {collectBatchExpression} from './browser_worker.mjs';
import {acquireRunnerLock} from './runner_lock.mjs';

const PLATFORM_REASONS = new Set(['VERIFICATION_REQUIRED', 'PAGE_FREQUENCY_LIMIT',
  'HTTP_403_REFUSED', 'HTTP_429_RATE_LIMIT', 'LOGIN_REQUIRED', 'LOGIN_STATE_UNKNOWN']);

/** Public material record from a projected native response; prices are irrelevant. */
export function materialRecord(sku, data) {
  return {
    sku: String(sku),
    ok: true,
    title: data.title || '',
    spu: String(data.realSpuId || ''),
    crumbs: (data.crumbs || []).map((x) => x.text).filter(Boolean),
    carousel: (data.carousel || []).map((x) => x.u).filter(Boolean),
    colorSize: (data.colorSize || []).map((d) => ({
      dim: d.dim,
      buttons: (d.buttons || []).map((b) => ({
        text: b.text || '', skuId: String(b.skuId || ''), fullImageUrl: b.fullImageUrl || '',
      })),
    })),
    videos: (data.carousel || []).flatMap((x) => x.v || []).filter((v) => v.p).map((v) => v.p),
  };
}

/** Accept a JSON array, a {category: [ids]} object, or one id per line. */
export function parseIds(text) {
  const trimmed = String(text || '').trim();
  if (!trimmed) return [];
  try {
    const value = JSON.parse(trimmed);
    const list = Array.isArray(value) ? value : Object.values(value).flat();
    return [...new Set(list.map(String).filter((x) => /^\d{8,}$/.test(x)))];
  } catch {
    return [...new Set(trimmed.split(/\r?\n/).map((x) => x.trim()).filter((x) => /^\d{8,}$/.test(x)))];
  }
}

function parseArgs(argv) {
  const options = new Map();
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith('--') && arg.includes('=')) {
      const [k, ...rest] = arg.split('=');
      options.set(k, rest.join('='));
    } else if (arg.startsWith('--') && argv[i + 1] && !argv[i + 1].startsWith('--')) {
      options.set(arg, argv[++i]);
    }
  }
  return options;
}

const json = (file) => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
const atomic = (file, value) => {
  fs.mkdirSync(path.dirname(file), {recursive: true});
  const pending = file + '.pending';
  fs.writeFileSync(pending, JSON.stringify(value, null, 2), 'utf8');
  fs.renameSync(pending, file);
};

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const stage = path.resolve(options.get('--state-dir') || '');
  if (!options.get('--state-dir')) throw Error('STATE_DIR_REQUIRED');
  const idsFile = options.get('--ids-file');
  if (!idsFile) throw Error('IDS_FILE_REQUIRED');
  const ids = parseIds(fs.readFileSync(idsFile, 'utf8'));
  if (!ids.length) throw Error('IDS_EMPTY');
  const output = path.resolve(options.get('--output') || path.join(stage, 'materials.jsonl'));
  const batchSize = Math.max(1, Math.min(30, Number(options.get('--batch') || 20)));
  const intervalMs = Math.max(0, Number(options.get('--interval-ms') || 100));
  const context = taskContext(stage);
  fs.mkdirSync(path.dirname(output), {recursive: true});

  const done = new Set();
  if (fs.existsSync(output)) {
    for (const line of fs.readFileSync(output, 'utf8').split(/\r?\n/)) {
      if (!line.trim()) continue;
      try { const row = JSON.parse(line); if (row.ok) done.add(String(row.sku)); } catch {}
    }
  }
  const pending = ids.filter((id) => !done.has(id));
  const stateFile = path.join(stage, 'material_runner_state.json');
  const state = {state: 'STARTING', startedAt: new Date().toISOString(), total: ids.length,
                 done: done.size, failed: 0, currentSku: null, output};
  const checkpoint = (fields = {}) => {
    Object.assign(state, fields, {updatedAt: new Date().toISOString()});
    atomic(stateFile, state);
  };
  const append = (row) => fs.appendFileSync(output, JSON.stringify(row) + '\n', 'utf8');
  checkpoint({state: 'RUNNING', pending: pending.length});

  const release = acquireRunnerLock(stage);
  let tab = null;
  let owner = null;
  try {
    process.argv[1] = context.wcli.main;
    await import(pathToFileURL(context.wcli.preload).href);
    const {Page} = await import(pathToFileURL(context.wcli.page).href);
    const {sendCommandFull} = await import(pathToFileURL(path.join(path.dirname(context.wcli.page), 'daemon-client.js')).href);
    owner = new Page(context.session, context.idleTimeout, undefined, 'background');

    // One tab for the whole batch: no per-product tab churn, no extra memory.
    const opened = await openNativePage(owner, Page, sendCommandFull, context, context.probeSku, null);
    tab = opened.tab;
    if (!opened.result.ok) throw Error('PROBE_PAGE_FAILED:' + opened.result.reason);

    for (let offset = 0; offset < pending.length; offset += batchSize) {
      const batch = pending.slice(offset, offset + batchSize);
      checkpoint({currentSku: batch[0]});
      await opened.page.evaluate(`window.__jdNativeRequestContext.allowedSkuIds=${JSON.stringify(batch)};undefined`);
      let rows = [];
      try {
        rows = JSON.parse(await opened.page.evaluate(collectBatchExpression(batch)));
      } catch (error) {
        rows = batch.map((sku) => ({sku, result: {ok: false, reason: 'BATCH_EVALUATE_FAILED'}}));
      }
      for (const item of rows) {
        const result = item.result || {};
        const data = result.data || result.partialData;
        if (data && String(data.responseSku) === String(item.sku)) {
          append(materialRecord(item.sku, data));
          state.done += 1;
        } else {
          const reason = result.reason || (result.phase === 'TIMEOUT' ? 'REQUEST_TIMEOUT' : 'NO_DATA');
          append({sku: String(item.sku), ok: false, reason});
          state.failed += 1;
          if (PLATFORM_REASONS.has(reason)) {
            checkpoint({state: 'HALTED', reason});
            throw Object.assign(Error(reason), {taskStop: true});
          }
        }
      }
      checkpoint();
      if (offset + batchSize < pending.length) await new Promise((r) => setTimeout(r, intervalMs));
    }
    checkpoint({state: 'DONE', currentSku: null});
  } catch (error) {
    if (!error.taskStop) checkpoint({state: 'HALTED', reason: String(error.message || error).slice(0, 160)});
    process.exitCode = 2;
  } finally {
    if (tab && owner) { try { await owner.closeTab(tab); } catch {} }
    release?.();
    console.log(JSON.stringify({state: state.state, done: state.done, failed: state.failed, output}));
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url))) {
  main().catch((error) => { console.error(String(error?.message || error)); process.exitCode = 1; });
}
