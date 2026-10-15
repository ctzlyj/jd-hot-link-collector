"""Independent batch validation against original inputs, live checkpoints and filesystem."""
import json,hashlib,collections
from pathlib import Path
from openpyxl import load_workbook
from PIL import Image
from collector_guard import ordered_variants,atomic_json
from package_live import ROOT,STAGE,live_data,verify_table
from package_contract import table_matrix,error_state
from media_guard import inspect_mp4
from checkpoint_status import pending_checkpoint_status
from asset_paths import safe_name,image_url
from media_evidence import verify_media_evidence,expected_media_entries

def run():
 tasks=json.loads((STAGE/'keyword_tasks.json').read_text(encoding='utf-8'));results=[]
 for kw,items in tasks.items():
  for item in items:
   sku=item['pid'];rp=STAGE/'receipts'/f'{sku}.json';r={'keyword':kw,'sourceSku':sku,'row':item['row'],'complete':False}
   if not rp.exists():
    r.update(pending_checkpoint_status(STAGE,sku));results.append(r);continue
   receipt=json.loads(rp.read_text(encoding='utf-8'));folder=Path(receipt['folder']);metadata=json.loads((STAGE/'packages'/sku/'package_metadata.json').read_text(encoding='utf-8'))
   try:
    main=live_data(sku)
    if not main:raise ValueError('SOURCE_LIVE_DATA_MISSING')
    rows=ordered_variants(sku,main['colorSize']);prices={v['sku']:live_data(v['sku']) for v in rows}
    if any(v is None for v in prices.values()):raise ValueError('SKU_PRICE_EVIDENCE_MISSING')
    detail_cache=STAGE/'details_ordered'/(str(main['realSpuId'])+'.json')
    if not detail_cache.is_file():raise ValueError('DETAIL_SOURCE_CACHE_MISSING')
    detail_urls=json.loads(detail_cache.read_text(encoding='utf-8-sig'))
    entries=expected_media_entries(main,rows,prices,detail_urls,safe_name,image_url)
    verified_media=verify_media_evidence(folder,STAGE,entries)
    expected=table_matrix(main,rows,prices);verify_table(folder/'商品信息.xlsx',metadata)
    wb=load_workbook(folder/'商品信息.xlsx',read_only=True,data_only=False);actual=list(wb.active.values)[1:];wb.close()
    for a,e in zip(actual,expected):
     if list(a)!=[x if x!='' else None for x in e]:raise ValueError('FULL_ROW_CONTENT_MISMATCH')
    if receipt['keyword']!=kw or folder.parent.name!=kw:raise ValueError('KEYWORD_FOLDER_WRONG')
    if receipt['skuCount']!=len(rows) or receipt['images']!=metadata['expectedImages']:raise ValueError('MANIFEST_COUNT_WRONG')
    for name in ['主图','详情图','SKU图','主图视频']:
     if not (folder/name).is_dir():raise ValueError('REQUIRED_FOLDER_MISSING')
    images=list(folder.rglob('*.jpg'))
    if len(images)!=metadata['expectedImages']:raise ValueError('IMAGE_COUNT_WRONG')
    for p in images:
     with Image.open(p) as im:
      if im.format!='JPEG':raise ValueError('IMAGE_ENCODING_WRONG')
      im.verify()
    videos=list((folder/'主图视频').glob('*.mp4'))
    if len(videos)!=len(metadata['videos']):raise ValueError('VIDEO_COUNT_WRONG')
    for p in videos:inspect_mp4(p.read_bytes())
    r.update(complete=True,state='VERIFIED',folder=str(folder),skuCount=len(rows),images=len(images),videos=len(videos),sourceMediaHashesVerified=verified_media)
   except Exception as e:r.update(state='VALIDATION_ERROR',error=str(e))
   results.append(r)
 counts=dict(collections.Counter(x['state'] for x in results));report={'scope':len(results),'keywords':len(tasks),'counts':counts,'complete':all(x['complete'] for x in results),'results':results}
 atomic_json(STAGE/'independent_validation.json',report);print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
 return report
if __name__=='__main__':run()

