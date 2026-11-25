import {test} from 'node:test';
import assert from 'node:assert/strict';
import {materialRecord, parseIds} from '../scripts/collect_materials.mjs';

test('material record keeps public material fields and drops price data', () => {
  const record = materialRecord('1001', {
    title: 'T', realSpuId: 'SPU', pp: '9.9', login: true,
    crumbs: [{text: '生活日用'}, {text: '日用杂货'}, {text: ''}],
    carousel: [{u: 'jfs/a.jpg', v: [{p: '//v/1.mp4'}]}, {u: ''}],
    colorSize: [{dim: 1, buttons: [{text: '36L', skuId: 1002, fullImageUrl: 'jfs/b.jpg'}]}],
  });
  assert.deepEqual(record, {
    sku: '1001', ok: true, title: 'T', spu: 'SPU',
    crumbs: ['生活日用', '日用杂货'],
    carousel: ['jfs/a.jpg'],
    colorSize: [{dim: 1, buttons: [{text: '36L', skuId: '1002', fullImageUrl: 'jfs/b.jpg'}]}],
    videos: ['//v/1.mp4'],
  });
  assert.equal('pp' in record, false);
});

test('parseIds accepts arrays, category objects and line lists', () => {
  assert.deepEqual(parseIds('["100000001","100000001","bad"]'), ['100000001']);
  assert.deepEqual(parseIds('{"a":["100000001"],"b":["100000002"]}'), ['100000001', '100000002']);
  assert.deepEqual(parseIds('100000001\n100000002\n'), ['100000001', '100000002']);
  assert.deepEqual(parseIds(''), []);
});
