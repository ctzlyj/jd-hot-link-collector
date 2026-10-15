import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
from unittest.mock import patch, Mock
import os, tempfile, io, hashlib, concurrent.futures
from PIL import Image
os.environ.setdefault('JD_COLLECTOR_ROOT', tempfile.mkdtemp())
import asset_paths as assets
class AssetTests(unittest.TestCase):
 def jpeg(self):
  out=io.BytesIO();Image.new('RGB',(12,15),'red').save(out,'JPEG');return out.getvalue()
 def test_corrupt_owned_destination_repairs_from_valid_cache_without_network(self):
  with tempfile.TemporaryDirectory() as tmp:
   stage=Path(tmp);cache=stage/'cache';cache.mkdir();url='https://img10.360buyimg.com/imgzone/jfs/x.jpg'
   expected=self.jpeg();(cache/(hashlib.sha256(url.encode()).hexdigest()+'.jpg')).write_bytes(expected)
   dst=stage/'pending'/'1.jpg';dst.parent.mkdir();dst.write_bytes(b'truncated')
   with patch.object(assets,'CACHE',cache),patch.object(assets,'STAGE',stage),patch.object(assets,'get_public',side_effect=AssertionError('Unexpected download')):
    assets.save_jpeg(url,dst)
   self.assertEqual(dst.read_bytes(),expected)
 def test_concurrent_shared_url_has_one_download_and_complete_jpegs(self):
  with tempfile.TemporaryDirectory() as tmp:
   stage=Path(tmp);cache=stage/'cache';cache.mkdir();url='https://img10.360buyimg.com/imgzone/jfs/x.jpg'
   with patch.object(assets,'CACHE',cache),patch.object(assets,'STAGE',stage),patch.object(assets,'get_public',return_value=self.jpeg()) as get:
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
     files=list(pool.map(lambda i:assets.save_jpeg(url,stage/str(i)/'1.jpg'),range(12)))
   self.assertEqual(get.call_count,1)
   for name in files:
    with Image.open(stage/name) as image:image.load();self.assertEqual(image.format,'JPEG')
 def test_failed_download_preserves_existing_destination(self):
  with tempfile.TemporaryDirectory() as tmp:
   stage=Path(tmp);cache=stage/'cache';cache.mkdir();dst=stage/'1.jpg';dst.write_bytes(b'original')
   with patch.object(assets,'CACHE',cache),patch.object(assets,'STAGE',stage),patch.object(assets,'get_public',side_effect=ValueError('download failed')):
    with self.assertRaises(ValueError):assets.save_jpeg('https://img10.360buyimg.com/imgzone/jfs/x.jpg',dst)
   self.assertEqual(dst.read_bytes(),b'original')
 def test_corrupt_cache_is_not_reused(self):
  with tempfile.TemporaryDirectory() as tmp:
   stage=Path(tmp);cache=stage/'cache';cache.mkdir();url='https://img10.360buyimg.com/imgzone/jfs/x.jpg'
   (cache/(hashlib.sha256(url.encode()).hexdigest()+'.jpg')).write_bytes(b'truncated')
   with patch.object(assets,'CACHE',cache),patch.object(assets,'STAGE',stage),patch.object(assets,'get_public',return_value=self.jpeg()) as get:
    assets.save_jpeg(url,stage/'1.jpg')
   self.assertEqual(get.call_count,1)
   with Image.open(stage/'1.jpg') as image:image.load();self.assertEqual(image.format,'JPEG')
 def test_destination_outside_owned_stage_is_rejected_before_download(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);stage=root/'stage';stage.mkdir();dst=root/'outside.jpg';dst.write_bytes(b'preserved')
   with patch.object(assets,'CACHE',stage/'cache'),patch.object(assets,'STAGE',stage),patch.object(assets,'get_public',side_effect=AssertionError('Unexpected download')):
    with self.assertRaisesRegex(ValueError,'JPEG_DESTINATION_OUTSIDE_STAGE'):assets.save_jpeg('https://img10.360buyimg.com/x.jpg',dst)
   self.assertEqual(dst.read_bytes(),b'preserved')
 def test_public_download_uses_normal_source_context(self):
  r=Mock(content=b'image');r.raise_for_status=Mock()
  with patch.object(assets.requests,'get',return_value=r) as get:
   self.assertEqual(assets.get_public('https://img10.360buyimg.com/imgzone/jfs/x.jpg'),b'image')
  headers=get.call_args.kwargs.get('headers',{})
  self.assertIn('Mozilla/5.0',headers.get('User-Agent',''))
  self.assertEqual(headers.get('Referer'),'https://item.jd.com/')
 def test_failed_asset_not_marked_ready(self):
  result=assets.final_state('ASSETS_STAGING',2,1,False)
  self.assertEqual(result,'ASSETS_INCOMPLETE_PRICE_PENDING')
 def test_complete_assets_still_price_pending(self):
  self.assertEqual(assets.final_state('ASSETS_STAGING',2,0,False),'ASSETS_READY_PRICE_PENDING')
 def test_public_host_boundary(self):
  with self.assertRaises(ValueError):assets.get_public('https://img10.360buyimg.com.attacker.test/x.jpg')
if __name__=='__main__':unittest.main(verbosity=2)
