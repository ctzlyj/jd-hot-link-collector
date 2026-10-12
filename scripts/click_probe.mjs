/** One normal page load; captures the complete native response before judging price availability. */
import fs from 'node:fs';import path from 'node:path';import {pathToFileURL} from 'node:url';
import {validate} from './request_policy.mjs';
import {taskContext} from './task_context.mjs';import {parseOptions} from './collection_policy.mjs';
import {openNativePage} from './native_page.mjs';import {acquireRunnerLock} from './runner_lock.mjs';
const options=parseOptions(process.argv.slice(2));const root=path.resolve(options.root);
const stage=options.stateDir?path.resolve(options.stateDir):path.join(root,'.collector_state');
const context=taskContext(stage);
function atomic(file,value){fs.mkdirSync(path.dirname(file),{recursive:true});const tmp=file+'.pending';fs.writeFileSync(tmp,JSON.stringify(value,null,2),'utf8');fs.renameSync(tmp,file)}
let release,opened,result;
try{
 release=acquireRunnerLock(stage);process.argv[1]=context.wcli.main;
 await import(pathToFileURL(context.wcli.preload).href);
 const {Page}=await import(pathToFileURL(context.wcli.page).href);
 const {sendCommandFull}=await import(pathToFileURL(path.join(path.dirname(context.wcli.page),'daemon-client.js')).href);
 const owner=new Page(context.session,context.idleTimeout,undefined,'background');
 opened=await openNativePage(owner,Page,sendCommandFull,context,context.probeSku);
 if(!opened.result.ok)result=opened.result;
 else{
  const data=opened.result.data;
  try{
   validate(context.probeSku,data);
   const file=path.join(stage,'data',data.responseSku+'.json');
   if(!fs.existsSync(file))atomic(file,{source:'live_native_page',collectedAt:new Date().toISOString(),data});
   result={ok:true,sku:data.responseSku,arrival:data.pp,priceSource:data.priceSource};
  }catch(e){result={ok:false,reason:e.message,sku:data.responseSku}}
 }
}catch(e){result={ok:false,reason:['ANOTHER_RUNNER_OR_UNRESOLVED_LOCK','NETWORK_CAPTURE_UNSUPPORTED'].includes(e.message)?e.message:'LOCAL_OR_TRANSPORT_ERROR'}}
finally{
 if(opened){try{await opened.page.closeTab(opened.tab)}catch{result.cleanupPendingTab=opened.tab}}
 release?.();
}
result.checkedAt=new Date().toISOString();
if(result.reason!=='ANOTHER_RUNNER_OR_UNRESOLVED_LOCK')atomic(path.join(stage,'click_probe_status.json'),result);
console.log(JSON.stringify(result));
