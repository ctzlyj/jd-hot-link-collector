import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
import hashlib
import tempfile
import unittest
from pathlib import Path
from staging_cache import media_fingerprint, ready_cache_matches


class StagingCacheTests(unittest.TestCase):
    def test_prices_do_not_invalidate_media_but_new_video_does(self):
        d = {'responseSku': '1', 'title': 'Product', 'realSpuId': '10',
             'pp': '5', 'carousel': [{'u': 'image', 'v': []}]}
        first = media_fingerprint(d, [], [d])
        d['pp'] = '6'
        self.assertEqual(media_fingerprint(d, [], [d]), first)
        d['carousel'][0]['v'].append({'p': 'new-video'})
        self.assertNotEqual(media_fingerprint(d, [], [d]), first)

    def test_verified_unchanged_cache_has_zero_network_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp);p = folder / 'image.jpg';p.write_bytes(b'bytes')
            m = {'state': 'MATERIALS_READY_PRICE_PENDING', 'mediaFingerprint': 'fp',
                 'issues': [], 'expectedImages': 1, 'expectedVideos': 0,
                 'images': [{'file': 'image.jpg', 'sha256': hashlib.sha256(b'bytes').hexdigest()}],
                 'videos': []}
            self.assertTrue(ready_cache_matches(folder, m, 'fp'))
            self.assertFalse(ready_cache_matches(folder, m, 'new'))
            p.write_bytes(b'changed')
            self.assertFalse(ready_cache_matches(folder, m, 'fp'))

    def test_missing_and_escaped_media_do_not_reuse_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = {'state': 'MATERIALS_READY_PRICE_PENDING', 'mediaFingerprint': 'fp',
                 'issues': [], 'expectedImages': 1, 'expectedVideos': 0,
                 'images': [{'file': '../outside.jpg', 'sha256': 'none'}], 'videos': []}
            self.assertFalse(ready_cache_matches(Path(tmp), m, 'fp'))


if __name__ == '__main__':
    unittest.main()