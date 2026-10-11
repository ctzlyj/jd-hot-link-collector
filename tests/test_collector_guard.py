import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from collector_guard import CollectionError, Checkpoint, ordered_variants, validate_main, signed_response_projection

class GuardTests(unittest.TestCase):
    def main(self):
        return {'ok': True, 'login': True, 'responseSku':'10000000000001', 'title': '商品', 'p': '10', 'pp': '8',
                'realSpuId': '10000000000001', 'carousel': [{'u': 'jfs/main.jpg', 'v': []}],
                'colorSize': [{'dim': 1, 'buttons': [{'no': '2', 'text': 'B', 'skuId': '10000000000002', 'skuList': ['10000000000002']}, {'no': '1', 'text': 'A', 'skuId': '10000000000001', 'skuList': ['10000000000001']}]}]}
    def test_no_original_price_fallback(self):
        d=self.main(); d['pp']=None
        with self.assertRaisesRegex(CollectionError,'ARRIVAL_PRICE_MISSING'): validate_main('10000000000001',d)
    def test_login_required(self):
        d=self.main();d['login']=False
        with self.assertRaisesRegex(CollectionError,'LOGIN_REQUIRED'):validate_main('10000000000001',d)
    def test_order_by_frontend_no(self):
        rows=ordered_variants('10000000000001',self.main()['colorSize'])
        self.assertEqual([r['spec1'] for r in rows],['A','B'])
    def test_two_dimension_real_intersection(self):
        dims=[{'dim':1,'buttons':[{'no':'1','text':'红','skuList':['a','b']},{'no':'2','text':'蓝','skuList':['c']}]},
              {'dim':2,'buttons':[{'no':'1','text':'大','skuList':['b','c']},{'no':'2','text':'小','skuList':['a']}]}]
        rows=ordered_variants('a',dims)
        self.assertEqual([(r['sku'],r['spec1'],r['spec2']) for r in rows],[('b','红','大'),('a','红','小'),('c','蓝','大')])
    def test_ambiguous_combination_rejected(self):
        dims=[{'dim':1,'buttons':[{'no':'1','text':'A','skuList':['a','b']}]},{'dim':2,'buttons':[{'no':'1','text':'X','skuList':['a','b']}]}]
        with self.assertRaisesRegex(CollectionError,'AMBIGUOUS_SKU'): ordered_variants('a',dims)
    def test_cache_reuses_success_only(self):
        with TemporaryDirectory() as folder:
            c=Checkpoint(Path(folder));self.assertFalse(c.has('10000000000001'))
            c.put('10000000000001',self.main());self.assertTrue(c.has('10000000000001'))
            c.halt('VERIFICATION_REQUIRED');self.assertEqual(c.load_state()['state'],'HALTED')
    def test_projection_never_retains_credentials(self):
        raw={'isLogin':True,'skuHeadVO':{'skuTitle':'商品'},'price':{'p':'10'},'bestPromotion':{'purchasePrice':'8'},'wareInfoReadMap':{'realSpuId':'10000000000001'},'mainImageVO':{'carouselArea':[{'imageUrl':'jfs/main.jpg','videos':[]}]},'token':'secret','userInfo':{'pin':'secret'},'tracerId':'secret'}
        out=signed_response_projection(raw)
        self.assertNotIn('token',out);self.assertNotIn('userInfo',out);self.assertNotIn('tracerId',out)
    def test_missing_images_rejected(self):
        d=self.main();d['carousel']=[]
        with self.assertRaisesRegex(CollectionError,'MAIN_IMAGES_MISSING'): validate_main('10000000000001',d)
    def test_missing_response_identity_is_not_valid_cache(self):
        d=self.main();d.pop('responseSku')
        with self.assertRaisesRegex(CollectionError,'SKU_ID_MISSING'): validate_main('10000000000001',d)

if __name__=='__main__':unittest.main(verbosity=2)
