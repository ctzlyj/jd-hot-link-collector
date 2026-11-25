/** Pure contracts of the shop-level SKU counter; no browser involved. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {countMatrixSkus, parseShopPage, chunk, SHOP_PAGE_SIZE, SHOP_PAGE_LIMIT,
        extractCategories, mergeShardIds, shopEnumerationSummary} from '../scripts/shop_sku_count.mjs';

test('a single-SKU product still counts as one SKU', () => {
  assert.equal(countMatrixSkus([]), 1);
  assert.equal(countMatrixSkus(null), 1);
  assert.equal(countMatrixSkus([{dim: 1, buttons: []}]), 1);
});

test('every matrix button is one on-sale SKU', () => {
  const matrix = [
    {dim: 1, buttons: [{no: 1, skuId: '1'}, {no: 2, skuId: '2'}]},
    {dim: 2, buttons: [{no: 1, skuId: '3'}, {no: 2, skuId: '4'}, {no: 3, skuId: '5'}]},
  ];
  assert.equal(countMatrixSkus(matrix), 5);
});

test('shop page response yields ids, total and shop name', () => {
  const body = JSON.stringify({isSuccess: true, code: '0', result: {
    totalCount: 1058, pageIdx: 1, shopName: '熙染厨具企业店',
    wareInfo: [{wareId: 10238944742489}, {wareId: '10239929617220'}],
  }});
  const parsed = parseShopPage(body);
  assert.equal(parsed.ok, true);
  assert.equal(parsed.total, 1058);
  assert.equal(parsed.shopName, '熙染厨具企业店');
  assert.deepEqual(parsed.ids, ['10238944742489', '10239929617220']);
});

test('failed or malformed shop page responses fail closed', () => {
  assert.equal(parseShopPage('{"code":"1","message":"pageSize过大！"}').ok, false);
  assert.equal(parseShopPage('not json').reason, 'SHOP_PAGE_NOT_JSON');
});

test('page size stays at the storefront limit and chunking keeps order', () => {
  assert.equal(SHOP_PAGE_SIZE, 30);
  assert.deepEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
  assert.deepEqual(chunk([], 10), []);
});

test('page limit stays at the storefront front-end cap', () => {
  assert.equal(SHOP_PAGE_LIMIT, 80);
});

test('shop page categories are extracted from any supported response key', () => {
  const body = JSON.stringify({result: {totalCount: 2, shopName: 's',
    cateList: [{catId: 101, name: '锅'}, {catId: 102, cateName: '铲'}],
    wareInfo: [{wareId: 1}]}});
  const parsed = parseShopPage(body);
  assert.deepEqual(parsed.categories, [{id: '101', name: '锅'}, {id: '102', name: '铲'}]);
  assert.deepEqual(extractCategories({categoryList: [{id: 7}]}), [{id: '7', name: ''}]);
  assert.deepEqual(extractCategories({result: {wareInfo: []}}), []);
});

test('shard ids merge after the base list with duplicate audit', () => {
  const merged = mergeShardIds(['1', '2'], ['2', '3', '3', '1']);
  assert.deepEqual(merged.ids, ['1', '2', '3']);
  assert.deepEqual(merged.duplicates, ['2', '3', '1']);
});

test('shops under the paging cap are complete and keep no shard state', () => {
  const summary = shopEnumerationSummary({ids: ['1', '2'], total: 2, note: null, categories: []}, []);
  assert.equal(summary.pagingCapExceeded, false);
  assert.equal(summary.incomplete, false);
  assert.equal(summary.note, null);
});

test('paging cap without categories is flagged incomplete instead of undercounting silently', () => {
  const summary = shopEnumerationSummary({ids: Array.from({length: 2400}, (_, i) => String(i)),
                                           total: 2600, note: null, categories: []}, []);
  assert.equal(summary.pagingCapExceeded, true);
  assert.equal(summary.incomplete, true);
  assert.equal(summary.note, 'PAGING_CAP_EXCEEDED');
  assert.equal(summary.ids.length, 2400);
});

test('category shards cover the cap and report per-shard counts', () => {
  const base = {ids: ['1', '2'], total: 4, note: null,
                categories: [{id: '9', name: '锅'}]};
  const summary = shopEnumerationSummary(base, [{id: '9', ids: ['2', '3', '4'], note: null, total: 3}]);
  assert.deepEqual(summary.ids, ['1', '2', '3', '4']);
  assert.equal(summary.incomplete, false);
  assert.equal(summary.pagingCapExceeded, true);
  assert.deepEqual(summary.shards, {'9': {products: 3, total: 3}});
  assert.equal(summary.shardDuplicates, 1);
});

test('a failed shard is recorded without discarding the rest of the shop', () => {
  const base = {ids: ['1'], total: 3, note: null, categories: [{id: '9'}, {id: '8'}]};
  const summary = shopEnumerationSummary(base, [
    {id: '9', ids: ['2'], note: null, total: 1},
    {id: '8', ids: [], note: 'SHOP_PAGE_FAILED', total: 0},
  ]);
  assert.deepEqual(summary.ids, ['1', '2']);
  assert.equal(summary.incomplete, true);
  assert.deepEqual(summary.shards['8'], {note: 'SHOP_PAGE_FAILED'});
});

test('a base enumeration failure keeps the old note-and-stop behaviour', () => {
  const summary = shopEnumerationSummary({ids: ['1'], total: 0, note: 'SHOP_PAGE_FAILED', categories: []}, []);
  assert.equal(summary.note, 'SHOP_PAGE_FAILED');
  assert.equal(summary.pagingCapExceeded, false);
});
