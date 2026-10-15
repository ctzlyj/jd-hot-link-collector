import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from checkpoint_status import pending_checkpoint_status


class CheckpointStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.stage = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def save(self, folder, sku, data, source='live_native_page'):
        p = self.stage / folder / (sku + '.json')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'source': source, 'data': data}), encoding='utf-8')

    def main(self, sku='1', price=None):
        d = {'ok': True, 'login': True, 'responseSku': sku, 'title': 'Product',
             'realSpuId': '10', 'carousel': [{'u': 'https://example.test/1.jpg'}],
             'colorSize': []}
        if price is not None:
            d['pp'] = price
        return d

    def test_unknown_matrix_is_main_pending(self):
        self.assertEqual(pending_checkpoint_status(self.stage, '1')['state'], 'MAIN_PENDING')

    def test_main_without_price_is_price_pending(self):
        self.save('partial_data', '1', self.main(), 'live_native_page_arrival_pending')
        r = pending_checkpoint_status(self.stage, '1')
        self.assertEqual(r['state'], 'PRICE_PENDING')
        self.assertEqual(r['missingPriceSkus'], ['1'])

    def test_sibling_missing_price_is_not_unknown_main(self):
        d = self.main(price='5')
        d['colorSize'] = [{'dim': 1, 'buttons': [
            {'no': 1, 'text': 'A', 'skuId': '1', 'skuList': ['1']},
            {'no': 2, 'text': 'B', 'skuId': '2', 'skuList': ['2']}]}]
        self.save('data', '1', d)
        r = pending_checkpoint_status(self.stage, '1')
        self.assertEqual(r['state'], 'PRICE_PENDING')
        self.assertEqual(r['missingPriceSkus'], ['2'])
        self.assertEqual(r['knownSkuCount'], 2)

    def test_prices_without_receipt_are_not_verified(self):
        self.save('data', '1', self.main(price='5'))
        self.assertEqual(pending_checkpoint_status(self.stage, '1')['state'], 'PACKAGING_PENDING')

    def test_untrusted_or_wrong_identity_is_not_known(self):
        self.save('data', '1', self.main('2', '5'))
        self.assertEqual(pending_checkpoint_status(self.stage, '1')['state'], 'MAIN_PENDING')
        self.save('data', '1', self.main(price='5'), 'historical_import')
        self.assertEqual(pending_checkpoint_status(self.stage, '1')['state'], 'MAIN_PENDING')

    def test_explicit_unavailable_remains_separate(self):
        p = self.stage / 'errors' / '1.json'
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({'reason': 'PRODUCT_UNAVAILABLE'}), encoding='utf-8')
        self.assertEqual(pending_checkpoint_status(self.stage, '1')['state'], 'PRODUCT_UNAVAILABLE')

    def test_corrupt_checkpoint_is_unresolved_not_crash(self):
        p = self.stage / 'partial_data' / '1.json'
        p.parent.mkdir(parents=True)
        p.write_text('{', encoding='utf-8')
        self.assertEqual(pending_checkpoint_status(self.stage, '1')['state'], 'MAIN_PENDING')


if __name__ == '__main__':
    unittest.main()
