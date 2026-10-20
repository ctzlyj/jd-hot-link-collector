import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
import unittest
from unittest.mock import patch, Mock
import stage_cached_assets as assets
class AssetTests(unittest.TestCase):
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