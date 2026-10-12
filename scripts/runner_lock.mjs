import fs from 'node:fs';import path from 'node:path';
export function acquireRunnerLock(stage){
 fs.mkdirSync(stage,{recursive:true});const file=path.join(stage,'runner.lock');
 let fd;try{fd=fs.openSync(file,'wx')}catch(e){if(e.code==='EEXIST')throw Error('ANOTHER_RUNNER_OR_UNRESOLVED_LOCK');throw e}
 try{fs.writeFileSync(fd,String(process.pid))}catch(e){fs.closeSync(fd);fs.unlinkSync(file);throw e}
 let released=false;return ()=>{if(released)return;released=true;fs.closeSync(fd);if(fs.existsSync(file)&&fs.readFileSync(file,'utf8')===String(process.pid))fs.unlinkSync(file)};
}
