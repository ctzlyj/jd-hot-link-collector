import {test} from 'node:test';import assert from 'node:assert/strict';
import {clickSpecExpression} from '../scripts/browser_worker.mjs';
import vm from 'node:vm';
function pageContext(clicks){
 const element={innerText:'  口径15cm高50cm  ',click(){clicks.push('first')}};
 const element2={innerText:'口径20cm高50cm',click(){clicks.push('second')}};
 element.parentElement=null;element2.parentElement=null;
 const c={document:{querySelectorAll:()=>[element,element2]},JSON,String,Array};
 c.window=c;return {context:vm.createContext(c),element,element2};
}
test('single dimension click dispatches exactly one real click',()=>{
 const clicks=[];const {context}=pageContext(clicks);
 const out=JSON.parse(vm.runInContext(clickSpecExpression('口径15cm高50cm'),context));
 assert.equal(out.ok,true);assert.deepEqual(clicks,['first']);
});
test('two dimension click dispatches both specs in order',()=>{
 const clicks=[];const {context}=pageContext(clicks);
 const out=JSON.parse(vm.runInContext(clickSpecExpression('口径15cm高50cm','口径20cm高50cm'),context));
 assert.equal(out.ok,true);assert.deepEqual(clicks,['first','second']);
});
test('missing button is reported without dispatching',()=>{
 const clicks=[];const {context}=pageContext(clicks);
 const out=JSON.parse(vm.runInContext(clickSpecExpression('不存在'),context));
 assert.equal(out.ok,false);assert.equal(out.reason,'SPEC_BUTTON_MISSING');assert.equal(clicks.length,0);
});
test('invalid spec inputs rejected at build time',()=>{
 assert.throws(()=>clickSpecExpression(''),/INVALID_SPEC/);
 assert.throws(()=>clickSpecExpression('A',null),/INVALID_SPEC/);
});
