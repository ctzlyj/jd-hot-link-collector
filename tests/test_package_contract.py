import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
from package_contract import ordered_detail_urls,table_matrix
class PackageTests(unittest.TestCase):
 def test_detail_mixed_markup_keeps_document_order(self):
  data='showdesc({"content":"<div style=\"background:url(https://img10.360buyimg.com/a.jpg)\"></div><img src=\"https://img10.360buyimg.com/b.jpg\"><img src=\"https://img10.360buyimg.com/a.jpg\">"})'
  # Use JSON encoder so HTML quotes are valid JSON.
  import json
  data='showdesc('+json.dumps({'content':'<div style="background:url(https://img10.360buyimg.com/a.jpg)"></div><img src="https://img10.360buyimg.com/b.jpg"><img src="https://img10.360buyimg.com/a.jpg">'})+')'
  self.assertEqual(ordered_detail_urls(data),['https://img10.360buyimg.com/a.jpg','https://img10.360buyimg.com/b.jpg'])
 def test_malformed_nested_img_urls_are_rejected(self):
  import json as _json
  data='showdesc('+_json.dumps({'content':'<p><img style="max-width:790px;" data-lazyload="http://<div><img style=\\"width:auto;\\" data-lazyload=\\"//img10.360buyimg.com/imgzone/jfs/x.jpg\\">" data-lazyload="//img10.360buyimg.com/imgzone/jfs/ok.jpg"> '})+')'
  assert 'img10.360buyimg.com/imgzone/jfs/ok.jpg' in data
  self.assertEqual(ordered_detail_urls(data),['https://img10.360buyimg.com/imgzone/jfs/ok.jpg'])
 def test_price_rows_follow_frontend_order_and_only_first_title(self):
  data={'title':'商品','attrs':[],'crumbs':[{'text':'类目'}],'colorSize':[]}
  rows=[{'sku':'b','spec1':'主推','spec2':'','image':''},{'sku':'a','spec1':'其次','spec2':'','image':''}]
  prices={'a':{'pp':'20'},'b':{'pp':'10'}}
  matrix=table_matrix(data,rows,prices)
  self.assertEqual([x[7] for x in matrix],[10,20]);self.assertEqual(matrix[0][0],'商品');self.assertIsNone(matrix[1][0]);self.assertEqual(len(matrix[0]),22)
 def test_missing_price_refused(self):
  with self.assertRaises(ValueError):table_matrix({'title':'商品','attrs':[],'crumbs':[]},[{'sku':'a','spec1':'A','spec2':''}],{})
if __name__=='__main__':unittest.main(verbosity=2)

class CategoryTests(unittest.TestCase):
 def test_breadcrumb_brand_not_category(self):
  data={'title':'商品','attrs':[{'labelName':'品牌','labelValue':'品牌名'}],'crumbs':[{'text':'一级'},{'text':'二级'},{'text':'三级'},{'text':'品牌名'}]}
  rows=[{'sku':'a','spec1':'A','spec2':''}]
  self.assertEqual(table_matrix(data,rows,{'a':{'pp':'10'}})[0][3],'一级>二级>三级')
