import sys, unittest, json, tempfile, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
os.environ.setdefault('JD_COLLECTOR_ROOT', tempfile.mkdtemp())
import package_live as pl

def partial(sku, p='37.06'):
    return {'source':'live_signed_page_arrival_pending','data':{'ok':True,'login':True,'responseSku':sku,'title':'商品','p':p,'pp':None,'realSpuId':'123','carousel':[{'u':'jfs/x.jpg'}],'colorSize':[{'dim':1,'buttons':[{'no':'1','text':'A','skuId':sku,'skuList':[sku]}]}]}}

class FallbackTests(unittest.TestCase):
    def stage_with(self, sku, payload):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        stage=Path(tmp.name); d=stage/'partial_data'; d.mkdir(parents=True)
        (d/f'{sku}.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        return stage

    def test_delisted_variants_are_dropped_from_the_package_plan(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        stage=Path(tmp.name); (stage/'errors').mkdir()
        (stage/'errors'/'2.json').write_text(json.dumps({'sku':'2','reason':'PRODUCT_UNAVAILABLE'}),encoding='utf-8')
        rows=[{'sku':'1','spec1':'A','image':'jfs/a.jpg'},{'sku':'2','spec1':'B','image':'jfs/b.jpg'}]
        self.assertEqual([r['sku'] for r in pl.active_variants(stage,rows)],['1'])

    def test_partial_price_stays_pending_without_authorization(self):
        sku='10000000000001'; stage=self.stage_with(sku,partial(sku))
        self.assertIsNone(pl.live_data(sku,stage=stage))
    def test_authorized_marker_uses_original_price(self):
        sku='10000000000001'; stage=self.stage_with(sku,partial(sku))
        marker='original_price_user_authorized_20261015'
        out=pl.live_data(sku,stage=stage,marker=marker)
        self.assertEqual(out['pp'],'37.06');self.assertEqual(out['priceSource'],marker)
    def test_authorized_marker_rejects_missing_original_price(self):
        sku='10000000000001'; stage=self.stage_with(sku,partial(sku,p=None))
        self.assertIsNone(pl.live_data(sku,stage=stage,marker='m'))
    def test_authorized_marker_rejects_identity_mismatch(self):
        sku='10000000000001'; stage=self.stage_with(sku,partial('10000000000002'))
        self.assertIsNone(pl.live_data(sku,stage=stage,marker='m'))
    def test_authorization_is_recorded_per_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp)
            marker=pl.authorize_original_price_fallback(stage)
            self.assertTrue(marker.startswith('original_price_user_authorized_'))
            self.assertEqual(pl.fallback_marker(stage),marker)
            self.assertEqual(pl.fallback_marker(stage/'absent'),None)

if __name__=='__main__':unittest.main(verbosity=2)
