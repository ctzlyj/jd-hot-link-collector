import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_batch import parse_rows
HEADER = ['h1','h2','h3','h4','h5','h6','h7','h8','h9','h10','h11','h12','h13']
def product(pid, link, title='t'):
    return ['img','title-'+pid if title=='t' else title,pid,None,None,None,None,None,None,None,None,None,link]
class PrepareTests(unittest.TestCase):
    def test_sections_duplicates_and_links(self):
        rows=[['kw1']+[None]*12,HEADER,product('100000001','https://item.jd.com/100000001.html'),product('100000001','https://item.jd.com/100000001.html')]
        tasks,shifted=parse_rows(rows)
        self.assertEqual(list(tasks),['kw1']);self.assertEqual(len(tasks['kw1']),1)
        self.assertEqual(tasks['kw1'][0]['rows'],[3,4])
    def test_shifted_rows_and_link_only_rows_keep_identity_set(self):
        rows=[['kw']+[None]*12,
              product('100000001','https://item.jd.com/100000002.html'),
              product('100000002','https://item.jd.com/100000001.html'),
              [None]*12+['https://item.jd.com/100000001.html']]
        tasks,shifted=parse_rows(rows)
        self.assertEqual(len(tasks['kw']),2)
        self.assertEqual(shifted,[
            {'row':2,'productId':'100000001','linkProductId':'100000002'},
            {'row':3,'productId':'100000002','linkProductId':'100000001'}])
    def test_id_link_set_disagreement_rejected(self):
        with self.assertRaises(ValueError):parse_rows([['kw']+[None]*12,product('100000001','header')])
    def test_product_before_keyword_rejected(self):
        with self.assertRaises(ValueError):parse_rows([HEADER,product('100000001','https://item.jd.com/100000001.html')])
    def test_invalid_product_id_rejected(self):
        with self.assertRaises(ValueError):parse_rows([['kw']+[None]*12,['img','title','abc',None,None,None,None,None,None,None,None,None,'https://item.jd.com/100000001.html']])
if __name__=='__main__':unittest.main()
