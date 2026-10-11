"""Create completed collection packages from live per-SKU checkpoints only."""
from __future__ import annotations
import json,sys,hashlib,subprocess,concurrent.futures,shutil
from pathlib import Path
from datetime import datetime,timezone
from collector_guard import atomic_json,validate_main,ordered_variants
from asset_paths import ROOT,STAGE,CACHE,safe_name,image_url,save_jpeg,get_public
from workbook_writer import write_workbook
from package_contract import ordered_detail_urls,HEADERS,table_matrix,error_state
from media_guard import inspect_mp4
SCRIPT=Path(__file__).parent

def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def live_data(sku):
    p=STAGE/'data'/f'{sku}.json'
    if not p.exists():return None
    try:
        d=load(p)
        if d.get('source')!='live_signed_page':return None
        return validate_main(sku,d['data'])
    except (KeyError,ValueError,RuntimeError):return None

def details(spu):
    p=STAGE/'details_ordered'/f'{spu}.json'
    if p.exists():return load(p)
    data=ordered_detail_urls(get_public(f'https://d.3.cn/desc/{spu}').decode('utf-8'))
    if not data:raise ValueError('DETAIL_IMAGES_EMPTY')
    atomic_json(p,data);return data

def plan_product(keyword,item,known_names):
    pid=item['pid'];main=live_data(pid)
    if not main:
        error=STAGE/'errors'/f'{pid}.json'
        if error.exists():return {'pid':pid,'keyword':keyword,'state':error_state(load(error)),'reason':load(error).get('evidence',{}).get('itemOverTip') or load(error).get('reason')}
        return {'pid':pid,'keyword':keyword,'state':'MAIN_OR_PRICE_PENDING'}
    rows=ordered_variants(pid,main['colorSize']);prices={r['sku']:live_data(r['sku']) for r in rows}
    missing=[k for k,v in prices.items() if v is None]
    if missing:return {'pid':pid,'keyword':keyword,'state':'SKU_PRICES_PENDING','missingSku':missing}
    title=safe_name(main['title']);key=(keyword,title)
    if key in known_names and known_names[key]!=pid:title+='_'+pid
    known_names[key]=pid
    temp=STAGE/'packages'/pid;final=ROOT/safe_name(keyword)/title
    receipt=STAGE/'receipts'/f'{pid}.json'
    if receipt.exists():
        r=load(receipt)
        if r.get('state')=='COMPLETE' and Path(r['folder']).exists():return {'pid':pid,'keyword':keyword,'state':'COMPLETE','folder':r['folder']}
    temp.mkdir(parents=True,exist_ok=True)
    for name in ['主图','详情图','SKU图','主图视频']:(temp/name).mkdir(exist_ok=True)
    jobs=[]
    for i,c in enumerate([c for c in main['carousel'] if c.get('u')],1):jobs.append((image_url(c['u']),temp/'主图'/f'主图_{i}.jpg'))
    for i,u in enumerate(details(main['realSpuId']),1):jobs.append((u,temp/'详情图'/f'详情图_{i}.jpg'))
    names=set()
    for row in rows:
        image=row['image'] or next((c['u'] for c in prices[row['sku']]['carousel'] if c.get('u')),'')
        if not image:raise ValueError('SKU_IMAGE_MISSING')
        n=safe_name(' '.join(x for x in [row['spec1'],row['spec2']] if x) or row['sku'])
        if n in names:n+='_'+row['sku']
        names.add(n);jobs.append((image_url(image),temp/'SKU图'/(n+'.jpg')))
    groups={}
    for u,p in jobs:groups.setdefault(u,[]).append(p)
    def download(u,paths):
        for p in paths:save_jpeg(u,p)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(download,u,paths) for u,paths in groups.items()]
        for f in futures:f.result()
    video_urls=list(dict.fromkeys(v['p'] for d in [main,*prices.values()] for c in d['carousel'] for v in c.get('v',[]) if v.get('p')))
    videos=[]
    for i,u in enumerate(video_urls,1):
        vp=temp/'主图视频'/f'主图视频_{i}.mp4'
        if not vp.exists():
            cached=STAGE/'video_cache'/(hashlib.sha256(u.encode()).hexdigest()+'.mp4');cached.parent.mkdir(exist_ok=True)
            if not cached.exists():
                b=get_public(u);inspect_mp4(b);part=cached.with_suffix('.part');part.write_bytes(b);part.replace(cached)
            shutil.copyfile(cached,vp)
        videos.append({'file':str(vp.relative_to(temp)),**inspect_mp4(vp.read_bytes())})
    matrix=table_matrix(main,rows,prices)
    spec={'headers':HEADERS,'rows':matrix,'output':str(temp/'商品信息.xlsx')}
    metadata={'sourceSku':pid,'keyword':keyword,'title':main['title'],'finalFolder':str(final),'variants':rows,'arrivalPrices':{r['sku']:prices[r['sku']]['pp'] for r in rows},'expectedImages':len(jobs),'videos':videos,'priceSource':'live_signed_page','priceSources':{r['sku']:prices[r['sku']].get('priceSource','bestPromotion.purchasePrice') for r in rows},'collectedAt':datetime.now(timezone.utc).isoformat(),'state':'AWAITING_WORKBOOK'}
    atomic_json(temp/'package_metadata.json',metadata)
    return {'pid':pid,'keyword':keyword,'state':'AWAITING_WORKBOOK','spec':spec,'metadata':metadata,'temp':str(temp),'final':str(final)}

def verify_table(p,metadata):
    from openpyxl import load_workbook
    w=load_workbook(p,read_only=True,data_only=False);s=w.active
    rows=list(s.values);w.close()
    if list(rows[0])!=HEADERS or len(rows)-1!=len(metadata['variants']):raise ValueError('WORKBOOK_ROWS_OR_COLUMNS_WRONG')
    for i,(v,row) in enumerate(zip(metadata['variants'],rows[1:])):
        if (row[5] or '')!=v['spec1'] or (row[6] or '')!=v['spec2'] or abs(float(row[7])-float(metadata['arrivalPrices'][v['sku']]))>0.000001 or row[8]!=999:raise ValueError('WORKBOOK_SKU_ORDER_OR_PRICE_WRONG')
        if i==0 and row[0]!=metadata['title']:raise ValueError('WORKBOOK_TITLE_WRONG')
        if i and any(row[x] is not None for x in range(5)):raise ValueError('PRODUCT_FIELDS_REPEATED')

def finalize(p):
    from PIL import Image
    temp=Path(p['temp']);meta=p['metadata'];verify_table(temp/'商品信息.xlsx',meta)
    images=list(temp.rglob('*.jpg'))
    if len(images)!=meta['expectedImages']:raise ValueError('IMAGE_COUNT_MISMATCH')
    for image in images:
        with Image.open(image) as im:
            if im.format!='JPEG':raise ValueError('NOT_REAL_JPEG')
            im.verify()
    for v in meta['videos']:inspect_mp4((temp/v['file']).read_bytes())
    final=Path(p['final']);final.parent.mkdir(exist_ok=True)
    if final.exists():raise ValueError('USER_FOLDER_COLLISION')
    # Only copy complete business artifacts; metadata stays in task work area.
    final.mkdir()
    for name in ['主图','详情图','SKU图','主图视频']:shutil.copytree(temp/name,final/name)
    shutil.copyfile(temp/'商品信息.xlsx',final/'商品信息.xlsx')
    verify_table(final/'商品信息.xlsx',meta)
    receipt={'state':'COMPLETE','sourceSku':p['pid'],'keyword':p['keyword'],'folder':str(final),'skuCount':len(meta['variants']),'images':len(images),'videos':len(meta['videos']),'validatedAt':datetime.now(timezone.utc).isoformat()}
    atomic_json(STAGE/'receipts'/f"{p['pid']}.json",receipt);return receipt

def main():
    CACHE.mkdir(parents=True,exist_ok=True)
    tasks=load(STAGE/'keyword_tasks.json');report=[];prepared=[];names={}
    for kw,items in tasks.items():
        for it in items:
            try:
                p=plan_product(kw,it,names);report.append({k:v for k,v in p.items() if k in ['pid','keyword','state','folder','missingSku']})
                if p['state']=='AWAITING_WORKBOOK':prepared.append(p)
            except Exception as e:report.append({'pid':it['pid'],'keyword':kw,'state':'MATERIAL_ERROR','error':type(e).__name__,'errorCode':str(e) if isinstance(e,ValueError) else '', 'httpStatus':getattr(getattr(e,'response',None),'status_code',None)})
    if prepared:
        for p in prepared: write_workbook(p['spec'])
        for p in prepared:
            result=finalize(p)
            for x in report:
                if x['pid']==p['pid']:x.update(result)
            print(json.dumps(result,ensure_ascii=False),flush=True)
    atomic_json(STAGE/'package_report.json',report)
    print(json.dumps({'scope':len(report),'complete':sum(x['state']=='COMPLETE' for x in report),'pending':sum(x['state']!='COMPLETE' for x in report)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()


