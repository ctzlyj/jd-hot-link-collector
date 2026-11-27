"""Main-image n12 variant fallback: URL logic, wiring and durable notes."""
import hashlib, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
os.environ.setdefault('JD_COLLECTOR_ROOT', tempfile.mkdtemp())
os.environ.setdefault('JD_COLLECTOR_STATE_DIR', os.path.join(os.environ['JD_COLLECTOR_ROOT'], 'state'))
import image_variants


class N0VariantTests(unittest.TestCase):
    def test_size_segments_switch_to_n12_on_the_same_host(self):
        self.assertEqual(image_variants.clean_variant('https://img14.360buyimg.com/n1/jfs/t1/a.jpg'),
                         'https://img14.360buyimg.com/n12/jfs/t1/a.jpg')
        self.assertEqual(image_variants.clean_variant('https://img10.360buyimg.com/s800x800_/jfs/t1/a.jpg?x=1'),
                         'https://img10.360buyimg.com/n12/jfs/t1/a.jpg?x=1')
        self.assertEqual(image_variants.clean_variant('//img14.360buyimg.com/n5/jfs/a.jpg'),
                         '//img14.360buyimg.com/n12/jfs/a.jpg')

    def test_foreign_hosts_and_plain_paths_have_no_variant(self):
        self.assertIsNone(image_variants.clean_variant('https://img10.360buyimg.com.attacker.test/n1/a.jpg'))
        self.assertIsNone(image_variants.clean_variant('https://example.com/n1/a.jpg'))
        self.assertIsNone(image_variants.clean_variant('https://img14.360buyimg.com/imgzone/'))
        self.assertIsNone(image_variants.clean_variant('https://img14.360buyimg.com/jfs/a.jpg'))

    def test_fallback_returns_a_note_only_when_the_variant_is_used(self):
        dst = Path('main_1.jpg')
        def failing(url, destination):
            if '/n12/' not in url: raise ValueError('JPEG_VALIDATION_FAILED')
        note = image_variants.save_with_clean_fallback(lambda u, d: None, 'https://img14.360buyimg.com/n1/a.jpg', dst)
        self.assertIsNone(note)
        note = image_variants.save_with_clean_fallback(failing, 'https://img14.360buyimg.com/n1/a.jpg', dst)
        self.assertEqual(note, {'file': 'main_1.jpg',
                                'originalUrl': 'https://img14.360buyimg.com/n1/a.jpg',
                                'variantUrl': 'https://img14.360buyimg.com/n12/a.jpg',
                                'reason': 'ValueError'})

    def test_fallback_fails_closed_without_a_usable_variant(self):
        def failing(url, destination): raise ValueError('boom')
        with self.assertRaises(ValueError):
            image_variants.save_with_clean_fallback(failing, 'https://example.com/n1/a.jpg', Path('x.jpg'))
        calls = []
        def always_failing(url, destination): calls.append(url); raise ValueError('JPEG_VALIDATION_FAILED')
        with self.assertRaises(ValueError):
            image_variants.save_with_clean_fallback(always_failing, 'https://img14.360buyimg.com/n1/a.jpg', Path('x.jpg'))
        self.assertEqual(calls, ['https://img14.360buyimg.com/n1/a.jpg', 'https://img14.360buyimg.com/n12/a.jpg'])


class WiringTests(unittest.TestCase):
    def test_asset_paths_and_stage_assets_delegate_to_their_own_jpeg_saver(self):
        import asset_paths
        with patch.object(asset_paths, 'save_jpeg') as save:
            asset_paths.save_main_jpeg('https://img14.360buyimg.com/n1/a.jpg', Path('a.jpg'))
            save.assert_called_once_with('https://img14.360buyimg.com/n1/a.jpg', Path('a.jpg'))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
        import stage_cached_assets
        with patch.object(stage_cached_assets, 'save_jpeg') as save:
            stage_cached_assets.save_main_jpeg('https://img14.360buyimg.com/n1/a.jpg', Path('a.jpg'))
            save.assert_called_once_with('https://img14.360buyimg.com/n1/a.jpg', Path('a.jpg'))


class ManifestNoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.stage = self.root / 'state'; self.stage.mkdir()
        self.data = {'ok': True, 'login': True, 'responseSku': '1001', 'title': 'T', 'p': '10.0',
                     'pp': '9.9', 'priceSource': 'warePriceGatherVO.finalPrice', 'realSpuId': 'SPU1',
                     'crumbs': [], 'attrs': [], 'colorSize': [],
                     'carousel': [{'u': '//img14.360buyimg.com/n1/jfs/a.jpg', 'v': []}]}
        (self.stage / 'data').mkdir(parents=True)
        (self.stage / 'data' / '1001.json').write_text(
            json.dumps({'source': 'live_signed_page', 'data': self.data}), encoding='utf-8')
        (self.stage / 'details_ordered').mkdir(parents=True)
        (self.stage / 'details_ordered' / 'SPU1.json').write_text('[]', encoding='utf-8')

    def _stage_module(self):
        os.environ['JD_COLLECTOR_ROOT'] = str(self.root)
        os.environ['JD_COLLECTOR_STATE_DIR'] = str(self.stage)
        for name in [m for m in list(sys.modules) if m in ('stage_cached_assets', 'stage_pending_materials', 'asset_paths', 'package_live')]:
            del sys.modules[name]
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
        import stage_cached_assets
        import stage_pending_materials
        return stage_pending_materials

    def test_stage_manifest_records_the_substitution(self):
        stage_pending = self._stage_module()
        payload = b'fakejpg'
        def fake_main(url, destination):
            Path(destination).write_bytes(payload)
            return {'file': Path(destination).name, 'originalUrl': url,
                    'variantUrl': 'https://img14.360buyimg.com/n12/jfs/a.jpg', 'reason': 'ValueError'}
        def fake_save(url, destination): Path(destination).write_bytes(payload)
        with patch.object(stage_pending, 'save_main_jpeg', fake_main), \
             patch.object(stage_pending, 'save_jpeg', fake_save):
            result = stage_pending.stage_one('kw', {'pid': '1001', 'row': 1})
        manifest = json.loads((self.stage / 'pending_materials' / '1001' / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['expectedImages'], 2)
        self.assertEqual(len(manifest['images']), 2)
        self.assertEqual(manifest['sourceNotes'][0]['variantUrl'], 'https://img14.360buyimg.com/n12/jfs/a.jpg')
        self.assertEqual(result['state'], 'MATERIALS_READY_PRICE_PENDING')

    def test_package_receipt_records_the_substitution(self):
        self._stage_module()
        import package_live
        package_live.ROOT = self.root; package_live.STAGE = self.stage
        payload = b'fakejpg'
        def fake_main(url, destination):
            Path(destination).write_bytes(payload)
            return {'file': Path(destination).name, 'originalUrl': url,
                    'variantUrl': 'https://img14.360buyimg.com/n12/jfs/a.jpg', 'reason': 'ValueError'}
        def fake_save(url, destination): Path(destination).write_bytes(payload)
        with patch.object(package_live, 'save_main_jpeg', fake_main), \
             patch.object(package_live, 'save_jpeg', fake_save):
            planned = package_live.plan_product('kw', {'pid': '1001', 'row': 1}, {})
        self.assertEqual(planned['state'], 'AWAITING_WORKBOOK')
        self.assertEqual(planned['metadata']['expectedImages'], 2)
        self.assertEqual(planned['metadata']['sourceNotes'][0]['variantUrl'],
                         'https://img14.360buyimg.com/n12/jfs/a.jpg')
        receipt = json.loads((self.stage / 'packages' / '1001' / 'package_metadata.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['sourceNotes'][0]['originalUrl'], 'https://img14.360buyimg.com/n1/jfs/a.jpg')


if __name__ == '__main__':
    unittest.main()
