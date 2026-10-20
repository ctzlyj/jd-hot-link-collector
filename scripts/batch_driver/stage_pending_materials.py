"""Stage already observed public media. No JD business requests, prices or workbooks."""
import concurrent.futures,hashlib,json,shutil,sys
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from collector_guard import atomic_json,ordered_variants
from stage_cached_assets import ROOT,STAGE,CACHE,image_url,safe_name,save_jpeg,get_public
from package_contract import ordered_detail_urls
from media_guard import inspect_mp4
from staging_cache import media_fingerprint,ready_cache_matches

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def stamp():return datetime.now(timezone.utc).isoformat()
def decode(b):
    try:return b.decode('utf-8-sig')
    except UnicodeDecodeError:return b.decode('gb18030')

def stage_one(kw,item):
    pid=item['pid'];main=None
    if (STAGE/'receipts'/(pid+'.json')).exists():return {'sku':pid,'state':'COMPLETE_PRESERVED'}
    for group in ['data','partial_data']:
        p=STAGE/group/(pid+'.json')
        if p.exists():
            saved=read(p);d=saved.get('data') or {}
            if d.get('login') is True and d.get('responseSku')==pid and saved.get('source') in ['live_signed_page','live_native_page','live_signed_page_arrival_pending','live_native_page_arrival_pending']:
                main=d;break
    if not main:return {'sku':pid,'state':'MAIN_PENDING'}
    rows=ordered_variants(pid,main.get('colorSize') or [])
    folder=STAGE/'pending_materials'/pid
    data_list=[main]
    for row in rows:
        p=STAGE/'data'/(row['sku']+'.json')
        if p.exists():data_list.append(read(p)['data'])
    fingerprint=media_fingerprint(main,rows,data_list)
    manifest=folder/'manifest.json'
    if manifest.exists():
        saved=read(manifest)
        if ready_cache_matches(folder,saved,fingerprint):return saved
    for name in ['main','detail','sku','main_video']:(folder/name).mkdir(parents=True,exist_ok=True)
    jobs=[];issues=[]
    for i,car in enumerate([c for c in main.get('carousel',[]) if c.get('u')],1):jobs.append((image_url(car['u']),folder/'main'/(str(i)+'.jpg')))
    try:
        cache=STAGE/'details_ordered'/(str(main['realSpuId'])+'.json')
        if cache.exists():urls=read(cache)
        else:
            urls=ordered_detail_urls(decode(get_public('https://d.3.cn/desc/'+str(main['realSpuId']))))
            if not urls:raise ValueError('DETAIL_IMAGES_EMPTY')
            atomic_json(cache,urls)
        for i,url in enumerate(urls,1):jobs.append((url,folder/'detail'/(str(i)+'.jpg')))
    except Exception as e:issues.append({'step':'detail','error':type(e).__name__,'status':getattr(getattr(e,'response',None),'status_code',None)})
    for i,row in enumerate(rows,1):
        image=row.get('image')
        if not image:
            p=STAGE/'data'/(row['sku']+'.json');data=read(p)['data'] if p.exists() else main
            image=next((c['u'] for c in data.get('carousel',[]) if c.get('u')),'')
        if image:jobs.append((image_url(image),folder/'sku'/(str(i).zfill(3)+'.jpg')))
        else:issues.append({'step':'sku-image','sku':row['sku'],'error':'IMAGE_MISSING'})
    images=[]
    for url,dst in jobs:
        try:
            save_jpeg(url,dst);images.append({'file':str(dst.relative_to(folder)),'sha256':hashlib.sha256(dst.read_bytes()).hexdigest()})
        except Exception as e:issues.append({'step':'image','file':str(dst.relative_to(folder)),'error':type(e).__name__,'status':getattr(getattr(e,'response',None),'status_code',None)})
    video_urls=[]
    for data in data_list:
        for c in data.get('carousel',[]):
            for v in c.get('v') or []:
                if v.get('p') and v['p'] not in video_urls:video_urls.append(v['p'])
    videos=[]
    for i,url in enumerate(video_urls,1):
        try:
            cache=STAGE/'video_cache'/(hashlib.sha256(url.encode()).hexdigest()+'.mp4');cache.parent.mkdir(exist_ok=True)
            if not cache.exists():
                b=get_public(url);inspect_mp4(b);tmp=cache.with_suffix('.part');tmp.write_bytes(b);tmp.replace(cache)
            dst=folder/'main_video'/(str(i)+'.mp4')
            if not dst.exists():shutil.copy2(cache,dst)
            videos.append({'file':str(dst.relative_to(folder)),'sha256':hashlib.sha256(dst.read_bytes()).hexdigest(),**inspect_mp4(dst.read_bytes())})
        except Exception as e:issues.append({'step':'video','index':i,'error':type(e).__name__,'status':getattr(getattr(e,'response',None),'status_code',None)})
    result={'sku':pid,'keyword':kw,'title':main['title'],'state':'MATERIALS_READY_PRICE_PENDING' if not issues else 'MATERIALS_INCOMPLETE','variants':rows,'expectedImages':len(jobs),'savedImages':len(images),'images':images,'expectedVideos':len(video_urls),'videos':videos,'issues':issues,'priceComplete':False,'completePackage':False,'businessRequests':0,'checkedAt':stamp()}
    result['mediaFingerprint']=fingerprint
    atomic_json(folder/'manifest.json',result);return result

def main():
    CACHE.mkdir(parents=True,exist_ok=True);tasks=read(STAGE/'keyword_tasks.json');work=[(kw,it) for kw,items in tasks.items() for it in items];results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(stage_one,kw,it):(kw,it) for kw,it in work}
        for f in concurrent.futures.as_completed(futures):
            kw,it=futures[f]
            try:r=f.result()
            except Exception as e:r={'sku':it['pid'],'keyword':kw,'state':'MATERIALS_INCOMPLETE','error':type(e).__name__}
            results.append(r)
            report={'scope':len(work),'processed':len(results),'ready':sum(x['state']=='MATERIALS_READY_PRICE_PENDING' for x in results),'images':sum(x.get('savedImages',0) for x in results),'videos':sum(len(x.get('videos',[])) for x in results),'businessRequests':0,'completePackagesCreated':0,'checkedAt':stamp(),'products':results}
            atomic_json(STAGE/'pending_materials_report.json',report)
            if r['state'] not in ['MAIN_PENDING','COMPLETE_PRESERVED']:print(json.dumps({k:r.get(k) for k in ['sku','state','savedImages','expectedImages','expectedVideos']},ensure_ascii=False),flush=True)
    print(json.dumps({k:v for k,v in report.items() if k!='products'},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
