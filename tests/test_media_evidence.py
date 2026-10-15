import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from media_evidence import verify_media_evidence


class MediaEvidenceTests(unittest.TestCase):
    def fixture(self, root):
        folder = root / 'product';folder.mkdir()
        cache = root / 'state' / 'asset_cache';cache.mkdir(parents=True)
        url = 'https://example.test/source.jpg'
        relative = 'main/1.jpg'
        target = folder / relative;target.parent.mkdir();target.write_bytes(b'original-media')
        source = cache / (hashlib.sha256(url.encode()).hexdigest() + '.jpg')
        source.write_bytes(b'original-media')
        return folder,root/'state',[{'file':relative,'url':url,'cacheGroup':'asset_cache','suffix':'.jpg'}],target

    def test_exact_cached_source_content_is_verified_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder,stage,entries,_=self.fixture(Path(tmp))
            self.assertEqual(verify_media_evidence(folder,stage,entries),1)

    def test_same_file_count_with_wrong_image_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder,stage,entries,target=self.fixture(Path(tmp))
            target.write_bytes(b'different-product-image')
            with self.assertRaisesRegex(ValueError,'SOURCE_CONTENT_MISMATCH'):
                verify_media_evidence(folder,stage,entries)

    def test_missing_source_cache_cannot_claim_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder,stage,entries,_=self.fixture(Path(tmp))
            next((stage/'asset_cache').iterdir()).unlink()
            with self.assertRaisesRegex(ValueError,'SOURCE_CACHE_MISSING'):
                verify_media_evidence(folder,stage,entries)

    def test_unexpected_extra_video_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder,stage,entries,_=self.fixture(Path(tmp))
            (folder/'extra.mp4').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError,'MEDIA_FILE_SET_MISMATCH'):
                verify_media_evidence(folder,stage,entries)

    def test_escape_or_duplicate_destination_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder,stage,entries,_=self.fixture(Path(tmp))
            with self.assertRaisesRegex(ValueError,'MEDIA_DESTINATION_COLLISION'):
                verify_media_evidence(folder,stage,entries+entries)
            entries[0]['file']='../outside.jpg'
            with self.assertRaisesRegex(ValueError,'MEDIA_PATH_ESCAPE'):
                verify_media_evidence(folder,stage,entries)


if __name__ == '__main__':
    unittest.main()
