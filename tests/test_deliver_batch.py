import sys, unittest, json, tempfile, zipfile, subprocess, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from deliver_batch import (verified_items, delivered_keys, incremental_items, keyword_bins,
                           write_manifest, write_zip, HEADERS)
from openpyxl import load_workbook

def make_batch(tmp, products):
    root = Path(tmp); stage = root / '.collector_state'
    results = []
    for spec in products:
        kw, title, pid = spec['kw'], spec['title'], spec['pid']
        folder = root / kw / title; (folder / '主图').mkdir(parents=True)
        (folder / '主图' / '主图_1.jpg').write_bytes(b'jpeg-bytes-' + pid.encode())
        if spec.get('size'):
            (folder / '主图' / 'blob.bin').write_bytes(b'x' * spec['size'])
        meta = {'title': title, 'variants': [{'sku': pid}],
                'arrivalPrices': {pid: spec.get('price', '9.9')},
                'priceSources': {pid: ('original_price_user_authorized_20261015' if spec.get('fallback') else 'warePriceGatherVO.finalPrice')}}
        pdir = stage / 'packages' / pid; pdir.mkdir(parents=True)
        (pdir / 'package_metadata.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
        results.append({'keyword': kw, 'sourceSku': pid, 'state': 'VERIFIED', 'folder': str(folder), 'images': 1, 'videos': 0})
    (stage / 'independent_validation.json').write_text(json.dumps({'results': results}, ensure_ascii=False), encoding='utf-8')
    return root, stage

class DeliverTests(unittest.TestCase):
    def batch(self, products):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        return make_batch(tmp.name, products)

    def cli(self, root, *extra):
        return subprocess.run([sys.executable, '-X', 'utf8', str(Path(__file__).resolve().parents[1] / 'scripts' / 'deliver_batch.py'),
                               '--root', str(root), '--date', '20261015', *extra],
                              capture_output=True, text=True, encoding='utf-8')

    def test_verified_items_and_manifest(self):
        root, stage = self.batch([{'kw': '香薰', 'title': '商品A', 'pid': '1001', 'fallback': True, 'price': '19.9'},
                                  {'kw': '香薰', 'title': '商品B', 'pid': '1002', 'price': '9.9'}])
        items = verified_items(json.loads((stage / 'independent_validation.json').read_text(encoding='utf-8-sig')), stage, root)
        self.assertEqual([x['pid'] for x in items], ['1001', '1002'])
        self.assertEqual(items[0]['fallback'], 1); self.assertEqual(items[1]['fallback'], 0)
        manifest = root / 'm.xlsx'; write_manifest(items, manifest)
        wb = load_workbook(manifest); ws = wb.active; rows = list(ws.values); wb.close()
        self.assertEqual(list(rows[0]), HEADERS)
        self.assertEqual(rows[1][6], 1); self.assertEqual(rows[1][7], '19.90-19.90')
        self.assertEqual(rows[2][7], '9.90-9.90')

    def test_zip_structure_and_crc(self):
        root, stage = self.batch([{'kw': '香薰', 'title': '商品A', 'pid': '1001'}])
        items = verified_items(json.loads((stage / 'independent_validation.json').read_text(encoding='utf-8-sig')), stage, root)
        manifest = root / 'm.xlsx'; write_manifest(items, manifest)
        out = write_zip(items, root / 'out.zip', manifest, '上架清单.xlsx')
        with zipfile.ZipFile(root / 'out.zip') as zf:
            names = zf.namelist()
            self.assertIn('上架清单.xlsx', names)
            self.assertIn('香薰/商品A/主图/主图_1.jpg', names)
            self.assertIsNone(zf.testzip())
        self.assertEqual(out['files'], 2)

    def test_split_keeps_whole_keywords_under_cap(self):
        root, stage = self.batch([{'kw': 'kwA', 'title': 'a1', 'pid': '1001', 'size': 400 * 1024},
                                  {'kw': 'kwA', 'title': 'a2', 'pid': '1002', 'size': 500 * 1024},
                                  {'kw': 'kwB', 'title': 'b1', 'pid': '1003', 'size': 900 * 1024}])
        items = verified_items(json.loads((stage / 'independent_validation.json').read_text(encoding='utf-8-sig')), stage, root)
        bins = keyword_bins(items, 1)
        self.assertEqual(len(bins), 2)
        for b in bins:
            self.assertLessEqual(sum(x['size'] for x in b['items']), 1024 * 1024)
        kw_sets = [set(b['keywords']) for b in bins]
        self.assertTrue(all(len(k) > 0 for k in kw_sets))
        self.assertFalse(kw_sets[0] & kw_sets[1])

    def test_incremental_diff_normalizes_zip_separators(self):
        root, stage = self.batch([{'kw': 'kwA', 'title': 'a1', 'pid': '1001'},
                                  {'kw': 'kwB', 'title': 'b1', 'pid': '1002'}])
        prev = root / 'prev.zip'
        with zipfile.ZipFile(prev, 'w') as zf:
            zf.writestr('kwA/a1/主图/主图_1.jpg', b'old')
            zf.writestr('kwB\\b1\\主图\\主图_1.jpg', b'old')
        self.assertEqual(delivered_keys([prev]), {'kwA/a1', 'kwB/b1'})
        items = verified_items(json.loads((stage / 'independent_validation.json').read_text(encoding='utf-8-sig')), stage, root)
        remaining = incremental_items(items, [prev])
        self.assertEqual([x['pid'] for x in remaining], [])

    def test_cli_end_to_end_and_overwrite_guard(self):
        root, stage = self.batch([{'kw': '香薰', 'title': '商品A', 'pid': '1001'},
                                  {'kw': '墙纸', 'title': '商品B', 'pid': '1002'}])
        r = self.cli(root, '--name', '测试批')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((root / '测试批上架清单-2个-20261015.xlsx').exists())
        self.assertTrue((root / '测试批完整商品包-2个-20261015.zip').exists())
        r2 = self.cli(root, '--name', '测试批')
        self.assertNotEqual(r2.returncode, 0); self.assertIn('OUTPUT_EXISTS', r2.stderr + r2.stdout)
        r3 = self.cli(root, '--name', '测试批', '--overwrite')
        self.assertEqual(r3.returncode, 0, r3.stderr)

    def test_cli_incremental_excludes_delivered(self):
        root, stage = self.batch([{'kw': '香薰', 'title': '商品A', 'pid': '1001'}])
        r = self.cli(root, '--name', '全批')
        self.assertEqual(r.returncode, 0, r.stderr)
        full_zip = root / '全批完整商品包-1个-20261015.zip'
        make_batch(root, [{'kw': '香薰', 'title': '商品C', 'pid': '1003'}])
        r2 = self.cli(root, '--name', '后续', '--previous-zip', str(full_zip))
        self.assertEqual(r2.returncode, 0, r2.stderr)
        with zipfile.ZipFile(root / '后续增量完整商品包-1个-20261015.zip') as zf:
            names = zf.namelist()
            self.assertIn('增量上架清单.xlsx', names)
            self.assertTrue(any(n.startswith('香薰/商品C/') for n in names))
            self.assertFalse(any(n.startswith('香薰/商品A/') for n in names))

if __name__ == '__main__': unittest.main(verbosity=2)

