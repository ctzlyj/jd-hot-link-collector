"""Shop table extraction and result write-back; no network."""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from openpyxl import Workbook, load_workbook
from shop_table import (extract_shops, extract_shops_from_workbook, write_back,
                        normalize_shop_cell, shop_column_index, RESULT_HEADERS)


def make_workbook(rows, path):
    wb = Workbook(); ws = wb.active
    for row in rows: ws.append(list(row))
    wb.save(path); return path


class ShopTableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_normalize_accepts_ids_and_homepage_urls_only(self):
        self.assertEqual(normalize_shop_cell(60407178), '60407178')
        self.assertEqual(normalize_shop_cell(' 230456174 '), '230456174')
        self.assertEqual(normalize_shop_cell('https://mall.jd.com/index-1000123456.html'), '1000123456')
        self.assertEqual(normalize_shop_cell('https://shop.m.jd.com/?shopId=60407178&entry=m'), '60407178')
        self.assertIsNone(normalize_shop_cell('熙染厨具企业店'))
        self.assertIsNone(normalize_shop_cell('https://item.jd.com/101.html'))
        self.assertIsNone(normalize_shop_cell(''))

    def test_shop_column_extraction_with_ids_urls_names_and_duplicates(self):
        rows = [['洗衣袋', '主图', '标题', '商品ID', '类型', '价格', '到手价', '原价', '补贴金额', '商品标签', '评价数', '总销量', '店铺', '商品链接'],
                ['洗衣袋', None, '商品A', '101', None, None, None, None, None, None, None, None, 60407178, None],
                ['洗衣袋', None, '商品B', '102', None, None, None, None, None, None, None, None, 'https://mall.jd.com/index-230456174.html', None],
                ['洗衣袋', None, '商品C', '103', None, None, None, None, None, None, None, None, '熙染厨具企业店', None],
                ['洗衣袋', None, '商品D', '104', None, None, None, None, None, None, None, None, '60407178', None]]
        result = extract_shops(rows)
        self.assertEqual([s['shopId'] for s in result['shops']], ['60407178', '230456174'])
        self.assertEqual(result['columnIndex'], 12)
        reasons = {a['reason'] for a in result['audit']}
        self.assertIn('SHOP_ID_UNRESOLVED', reasons)
        self.assertIn('DUPLICATE_SHOP', reasons)

    def test_without_shop_header_only_url_cells_are_trusted(self):
        rows = [['链接'], ['https://mall.jd.com/index-1000001.html'],
                ['https://item.jd.com/100.html'], ['1000002']]
        result = extract_shops(rows)
        self.assertEqual([s['shopId'] for s in result['shops']], ['1000001'])
        self.assertEqual(result['columnIndex'], None)

    def test_repeated_header_rows_are_ignored(self):
        rows = [['店铺', '商品ID'], ['60407178', '101'], ['店铺', '商品ID'], ['230456174', '102']]
        result = extract_shops(rows)
        self.assertEqual([s['shopId'] for s in result['shops']], ['60407178', '230456174'])
        self.assertEqual(result['audit'], [])

    def test_workbook_round_trip(self):
        src = make_workbook([['标题', '店铺'], ['A', 60407178], ['B', '熙染厨具企业店']],
                            self.dir / 'ops.xlsx')
        table = extract_shops_from_workbook(src)
        self.assertEqual([s['shopId'] for s in table['shops']], ['60407178'])

    def test_write_back_appends_columns_to_a_copy(self):
        src = make_workbook([['标题', '店铺'], ['A', 60407178], ['B', 230456174]],
                            self.dir / 'ops.xlsx')
        out = self.dir / 'ops_result.xlsx'
        records = {'60407178': {'skuCount': 88, 'productCount': 12, 'missing': []},
                   '230456174': {'skuCount': 30, 'productCount': 5, 'missing': ['101']}}
        result = write_back(src, out, records, collected_at='2026-11-25T00:00:00+00:00')
        self.assertEqual(result['shopsMatched'], 2)
        self.assertEqual(result['shopsWritten'], 2)
        wb = load_workbook(out, read_only=True); rows = list(wb.active.values); wb.close()
        self.assertEqual(list(rows[0]), ['标题', '店铺'] + list(RESULT_HEADERS))
        self.assertEqual(rows[1][2:], (88, 12, 0, '2026-11-25T00:00:00+00:00'))
        self.assertEqual(rows[2][2:], (30, 5, 1, '2026-11-25T00:00:00+00:00'))
        original = load_workbook(src, read_only=True); self.assertEqual(list(original.active.values)[0], ('标题', '店铺')); original.close()
        with self.assertRaises(ValueError): write_back(src, src, records)

    def test_write_back_leaves_uncollected_shops_blank(self):
        src = make_workbook([['店铺'], [60407178], [230456174]], self.dir / 'ops.xlsx')
        out = self.dir / 'ops_result.xlsx'
        result = write_back(src, out, {'60407178': {'skuCount': 1, 'productCount': 1, 'missing': []}})
        self.assertEqual(result['shopsMatched'], 2)
        self.assertEqual(result['shopsWritten'], 1)
        wb = load_workbook(out, read_only=True); rows = list(wb.active.values); wb.close()
        self.assertEqual(rows[2][1:], (None, None, None, None))


if __name__ == '__main__':
    unittest.main()
