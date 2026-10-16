import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_batch import parse_rows,parse_batch,detect_layout
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

    def test_alternate_layout_keyword_a_pid_d(self):
        rows=[['檀香熏香家用室内持久留香']+[None]*12,
              [None,'主图','标题','商品ID','类型','价格','到手价','原价',None,None,None,None,None],
              [None,'https://img14.360buyimg.com/x.jpg','盘香天然沉香家用熏香','10207064571450','官方暂无数据',None,None,None,None,None,None,None,None],
              [None,'主图','标题','商品ID',None,None,None,None,None,None,None,None,None],
              [None,'https://img14.360buyimg.com/y.jpg','线香礼盒','10126680668843',None,None,None,None,None,None,None,None,None],
              ['安神助眠香薰','主图','标题','商品ID','类型',None,None,None,None,None,None,None,None],
              [None,'https://img14.360buyimg.com/z.jpg','助眠香薰','10215683358378',None,None,None,None,None,None,None,None,None]]
        tasks,shifted=parse_rows(rows)
        self.assertEqual(list(tasks),['檀香熏香家用室内持久留香','安神助眠香薰'])
        self.assertEqual([x['pid'] for x in tasks['檀香熏香家用室内持久留香']],['10207064571450','10126680668843'])
        self.assertEqual(tasks['安神助眠香薰'][0]['title'],'助眠香薰')
        self.assertEqual(shifted,[])
    def test_alternate_layout_header_and_blank_rows_are_not_keywords(self):
        rows=[[None]*13,
              [None,'主图','标题','商品ID',None,None,None,None,None,None,None,None,None],
              [None,None,None,'10207064571450',None,None,None,None,None,None,None,None,None],
              [None]*13]
        with self.assertRaises(ValueError):parse_rows(rows)
    def test_alternate_layout_cross_keyword_duplicate_keeps_first(self):
        rows=[['kw1']+[None]*12,
              [None,None,'t1','100000000001',None,None,None,None,None,None,None,None,None],
              ['kw2']+[None]*12,
              [None,None,'t2','100000000001',None,None,None,None,None,None,None,None,None],
              [None,None,'t3','100000000002',None,None,None,None,None,None,None,None,None]]
        tasks,shifted,layout,duplicates,_=parse_batch(rows)
        self.assertEqual(layout,'alternate')
        self.assertEqual(list(tasks),['kw1','kw2'])
        self.assertEqual([x['pid'] for x in tasks['kw2']],['100000000002'])
        self.assertEqual(duplicates,[{'productId':'100000000001','rows':[4],'keptKeyword':'kw1'}])
    def test_standard_layout_is_not_misdetected(self):
        rows=[['kw']+[None]*12,product('100000001','https://item.jd.com/100000001.html')]
        self.assertEqual(detect_layout(rows),'standard')
        tasks,shifted,layout,duplicates,_=parse_batch(rows)
        self.assertEqual(layout,'standard');self.assertEqual(duplicates,[])
        self.assertEqual(len(tasks['kw']),1)


    def test_listing_layout_url_title_pid(self):
        rows=[['磨砂玻璃贴膜']+[None]*12,
              ['主图','标题','商品ID','类型',None,None,None,None,None,None,None,None,None],
              ['https://img14.360buyimg.com/n1/jfs/x.jpg','防窥膜','10215516291374','官方暂无数据',None,None,None,None,None,None,None,None,None],
              ['主图','标题','商品ID',None,None,None,None,None,None,None,None,None,None],
              ['https://img14.360buyimg.com/n1/jfs/y.jpg','磨砂贴','10137594710934',None,None,None,None,None,None,None,None,None,None],
              ['身高尺墙贴']+[None]*12,
              ['https://img14.360buyimg.com/n1/jfs/z.jpg','身高尺','10099331401834',None,None,None,None,None,None,None,None,None,None]]
        tasks,shifted=parse_rows(rows)
        self.assertEqual(list(tasks),['磨砂玻璃贴膜','身高尺墙贴'])
        self.assertEqual([x['pid'] for x in tasks['磨砂玻璃贴膜']],['10215516291374','10137594710934'])
        self.assertEqual(tasks['磨砂玻璃贴膜'][0]['title'],'防窥膜')
        self.assertEqual(shifted,[])
    def test_listing_layout_header_row_is_not_keyword(self):
        rows=[['主图','标题','商品ID',None,None,None,None,None,None,None,None,None,None],
              ['https://img14.360buyimg.com/n1/jfs/x.jpg','t','10215516291374',None,None,None,None,None,None,None,None,None,None]]
        with self.assertRaises(ValueError):parse_rows(rows)
    def test_standard_without_links_parses_as_listing(self):
        rows=[['kw']+[None]*12,
              ['https://img14.360buyimg.com/n1/jfs/x.jpg','t','100000000001',None,None,None,None,None,None,None,None,None,None]]
        self.assertEqual(detect_layout(rows),'listing')
        tasks,shifted=parse_rows(rows)
        self.assertEqual(list(tasks),['kw'])
        self.assertEqual(tasks['kw'][0]['pid'],'100000000001')

    def test_keyword_surrounding_spaces_are_stripped(self):
        rows=[[' 吸盘式毛巾架 ']+[None]*12,product('100000001','https://item.jd.com/100000001.html')]
        tasks,shifted=parse_rows(rows)
        self.assertEqual(list(tasks),['吸盘式毛巾架'])

if __name__=='__main__':unittest.main()

