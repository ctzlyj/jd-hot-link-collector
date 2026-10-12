import {spawnSync} from 'node:child_process';
export function variantRows(script,file,python=process.env.JD_COLLECTOR_PYTHON||'python'){
 const result=spawnSync(python,['-X','utf8',script,file,'--rows'],{encoding:'utf8'});
 if(result.status!==0)throw Error('SKU_MATRIX_INVALID');
 let rows;try{rows=JSON.parse(result.stdout)}catch{throw Error('SKU_MATRIX_INVALID')}
 if(!Array.isArray(rows)||!rows.length||rows.some(r=>!r||typeof r.sku!=='string'||typeof r.spec1!=='string'||typeof r.spec2!=='string'))throw Error('SKU_MATRIX_INVALID');
 return rows;
}
