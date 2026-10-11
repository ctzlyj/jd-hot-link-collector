import fs from 'node:fs';
import path from 'node:path';
/** Validates the saved task-tab context; credentials never enter this file. */
export function taskContext(stage){
 const p=path.join(stage,'browser_context.json');
 if(!fs.existsSync(p))throw Error('TASK_BROWSER_CONTEXT_MISSING');
 let c;try{c=JSON.parse(fs.readFileSync(p,'utf8'))}catch{throw Error('TASK_BROWSER_CONTEXT_INVALID')}
 if(!c.session||typeof c.session!=='string'||/[^A-Za-z0-9_-]/.test(c.session))throw Error('TASK_BROWSER_CONTEXT_INVALID');
 if(!/^[A-F0-9]{32}$/.test(String(c.tab||'')))throw Error('TASK_BROWSER_CONTEXT_INVALID');
 if(c.windowMode!=='background'||Number(c.idleTimeout)<7200)throw Error('TASK_BROWSER_CONTEXT_INVALID');
 if(!/^\d{8,}$/.test(String(c.probeSku||'')))throw Error('TASK_BROWSER_CONTEXT_INVALID');
 const w=c.wcli||{};
 if(!w.main||!w.preload||!w.page)throw Error('TASK_BROWSER_CONTEXT_INVALID');
 return c;
}
