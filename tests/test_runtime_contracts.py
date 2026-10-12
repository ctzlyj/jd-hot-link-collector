import io,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collector_guard import signed_response_projection,ordered_variants

class RuntimeContracts(unittest.TestCase):
 def sample(self):
  return {'ok':True,'login':True,'responseSku':'10000000000001','title':'title','pp':'8','realSpuId':'123','carousel':[{'u':'jfs/x.jpg'}],'colorSize':[{'dim':1,'buttons':[{'no':2,'text':'B','skuId':'10000000000002'},{'no':1,'text':'A','skuId':'10000000000001'}]}]}
 def test_variant_cli_rows_have_the_specs_clicked_by_collector(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'10000000000001.json';p.write_text(json.dumps({'source':'live_native_page','data':self.sample()}),encoding='utf-8')
   r=subprocess.run([sys.executable,'-X','utf8',str(Path(__file__).resolve().parents[1]/'scripts/variant_queue.py'),str(p),'--rows'],capture_output=True,text=True,encoding='utf-8')
   self.assertEqual(r.returncode,0,r.stderr);rows=json.loads(r.stdout);self.assertEqual([x['spec1'] for x in rows],['A','B']);self.assertEqual(rows,ordered_variants(p.stem,self.sample()['colorSize']))
 def test_native_partial_cli_does_not_require_price_but_requires_identity(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'10000000000001.json';data=self.sample();data['pp']=None;p.write_text(json.dumps({'source':'live_native_page_arrival_pending','data':data}),encoding='utf-8')
   cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/variant_queue.py'),str(p),'--rows'];r=subprocess.run(cmd,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   data['responseSku']='10000000000002';p.write_text(json.dumps({'source':'live_native_page_arrival_pending','data':data}),encoding='utf-8');self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
 def test_python_projection_matches_frontend_final_price(self):
  r={'bestPromotion':{'purchasePrice':'10'},'warePriceGatherVO':{'priceItemList':[{'priceType':'finalPrice','price':'7.25','hitLine':False}]}}
  self.assertEqual(signed_response_projection(r)['pp'],'7.25');self.assertEqual(signed_response_projection(r)['priceSource'],'warePriceGatherVO.finalPrice')
 def test_real_jpeg_download_and_path_helpers_are_callable(self):
  import asset_paths as a
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);cache=root/'asset_cache';cache.mkdir();buf=io.BytesIO();Image.new('RGB',(10,10),'white').save(buf,format='PNG')
   with patch.object(a,'CACHE',cache),patch.object(a,'STAGE',root),patch.object(a,'get_public',return_value=buf.getvalue()):
    out=root/'images'/'one.jpg';a.save_jpeg('https://img10.360buyimg.com/img/x.png',out)
    with Image.open(out) as im:self.assertEqual(im.format,'JPEG');im.verify()
    self.assertEqual(a.safe_name('A/B'),'A_B')
if __name__=='__main__':unittest.main()
