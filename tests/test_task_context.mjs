import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {taskContext} from '../scripts/task_context.mjs';

const good = {
  session: 'task-session',
  tab: 'A1B2C3D4E5F60718293A4B5C6D7E8F90',
  idleTimeout: 86400,
  windowMode: 'background',
  probeSku: '12345678',
  wcli: {main: 'D:/tools/main.js', preload: 'D:/tools/preload.mjs', page: 'D:/tools/page.js'}
};

function ctx(value) {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'ctx-'));
  fs.writeFileSync(path.join(d, 'browser_context.json'), JSON.stringify(value));
  return d;
}

test('valid owned background context is accepted', () => {
  assert.equal(taskContext(ctx(good)).probeSku, '12345678');
});

test('missing context file is explicit', () => {
  assert.throws(() => taskContext(fs.mkdtempSync(path.join(os.tmpdir(), 'ctx-'))), /TASK_BROWSER_CONTEXT_MISSING/);
});

const badCases = [
  ['badTab', {tab: 'short'}],
  ['badMode', {windowMode: 'foreground'}],
  ['shortLease', {idleTimeout: 600}],
  ['noProbeSku', {probeSku: ''}],
  ['badSession', {session: ''}],
  ['noWcli', {wcli: null}],
  ['partialWcli', {wcli: {main: 'D:/x'}}]
];

for (const [name, patch] of badCases) {
  test(`invalid context rejected: ${name}`, () => {
    assert.throws(() => taskContext(ctx({...good, ...patch})), /TASK_BROWSER_CONTEXT_INVALID/);
  });
}
