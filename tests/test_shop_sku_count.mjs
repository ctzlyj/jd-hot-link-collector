/** Pure contracts of the shop-level SKU counter; no browser involved. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {countMatrixSkus, parseShopPage, chunk, SHOP_PAGE_SIZE} from '../scripts/shop_sku_count.mjs';

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
