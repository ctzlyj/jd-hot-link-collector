"""Drive the shop SKU counter from a table without a browser."""
import sys, tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
from openpyxl import Workbook, load_workbook
import shop_sku_driver


def make_workbook(path):
    wb = Workbook(); ws = wb.active
    ws.append(['标题', '店铺'])
    ws.append(['A', 60407178]); ws.append(['B', 230456174])
    wb.save(path); return path


class ShopSkuDriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.stage = self.dir / 'state'; self.stage.mkdir()
        (self.stage / 'browser_context.json').write_text('{}', encoding='utf-8')
        self.source = make_workbook(self.dir / 'ops.xlsx')

    def run_driver(self):
        argv = ['shop_sku_driver.py', '--input', str(self.source),
                '--state-dir', str(self.stage), '--chunk-shops', '1']
        with patch.object(sys, 'argv', argv):
            shop_sku_driver.main()
        return json.loads((self.stage / 'shop_sku_driver_state.json').read_text(encoding='utf-8-sig'))

    def test_chunks_run_and_results_are_written_back(self):
        calls = []
        def fake_run(command, **kwargs):
            calls.append(command)
            sid = command[command.index('--shops') + 1]
            output = Path(command[command.index('--output') + 1])
            data = json.loads(output.read_text(encoding='utf-8-sig')) if output.exists() else {'shops': {}}
            data['shops'][sid] = {'productCount': 1, 'skuCount': 5, 'missing': [], 'done': True}
            output.write_text(json.dumps(data), encoding='utf-8')
            return Mock(returncode=0, stderr='')
        with patch.object(shop_sku_driver.subprocess, 'run', fake_run), \
             patch.object(shop_sku_driver.time, 'sleep'):
            state = self.run_driver()
        self.assertEqual(state['phase'], 'DONE')
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][calls[0].index('--shops') + 1], '60407178')
        result = self.dir / 'ops_SKU结果.xlsx'
        found = [p for p in self.dir.glob('ops_SKU结果_*.xlsx')]
        self.assertTrue(found)
        wb = load_workbook(found[0], read_only=True); rows = list(wb.active.values); wb.close()
        self.assertEqual(list(rows[0])[2:], ['在售SKU数', '在售商品数', '待补商品数', '店铺采集时间'])
        self.assertEqual(rows[1][2], 5)

    def test_already_completed_shops_are_not_rerun(self):
        output = self.stage / 'shop_sku_count.json'
        output.write_text(json.dumps({'shops': {'60407178': {'done': True, 'missing': [], 'skuCount': 5}}}), encoding='utf-8')
        calls = []
        def fake_run(command, **kwargs):
            calls.append(command)
            sid = command[command.index('--shops') + 1]
            output = Path(command[command.index('--output') + 1])
            data = json.loads(output.read_text(encoding='utf-8-sig'))
            data['shops'][sid] = {'productCount': 1, 'skuCount': 5, 'missing': [], 'done': True}
            output.write_text(json.dumps(data), encoding='utf-8')
            return Mock(returncode=0, stderr='')
        with patch.object(shop_sku_driver.subprocess, 'run', fake_run), \
             patch.object(shop_sku_driver.time, 'sleep'):
            state = self.run_driver()
        self.assertEqual(state['phase'], 'DONE')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][calls[0].index('--shops') + 1], '230456174')

    def test_platform_marker_stops_the_driver_immediately(self):
        def fake_run(command, **kwargs):
            return Mock(returncode=1, stderr='Error: VERIFICATION_REQUIRED')
        with patch.object(shop_sku_driver.subprocess, 'run', fake_run), \
             patch.object(shop_sku_driver.time, 'sleep'):
            with self.assertRaises(SystemExit):
                self.run_driver()
        state = json.loads((self.stage / 'shop_sku_driver_state.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(state['phase'], 'BLOCKED_PLATFORM')
        self.assertEqual(state['reason'], 'VERIFICATION_REQUIRED')

    def test_transient_chunk_failure_retries_then_finishes(self):
        attempts = []
        def fake_run(command, **kwargs):
            attempts.append(command)
            if len(attempts) == 1:
                return Mock(returncode=1, stderr='LOCAL_OR_TRANSPORT_ERROR')
            sid = command[command.index('--shops') + 1]
            output = Path(command[command.index('--output') + 1])
            data = json.loads(output.read_text(encoding='utf-8-sig')) if output.exists() else {'shops': {}}
            data['shops'][sid] = {'done': True, 'missing': [], 'skuCount': 1, 'productCount': 1}
            output.write_text(json.dumps(data), encoding='utf-8')
            return Mock(returncode=0, stderr='')
        with patch.object(shop_sku_driver.subprocess, 'run', fake_run), \
             patch.object(shop_sku_driver.time, 'sleep'):
            state = self.run_driver()
        self.assertEqual(state['phase'], 'DONE')
        self.assertEqual(len(attempts), 3)

    def test_repeated_chunk_failures_stop_as_blocked(self):
        def fake_run(command, **kwargs):
            return Mock(returncode=1, stderr='something else')
        with patch.object(shop_sku_driver.subprocess, 'run', fake_run), \
             patch.object(shop_sku_driver.time, 'sleep'):
            with self.assertRaises(SystemExit):
                self.run_driver()
        state = json.loads((self.stage / 'shop_sku_driver_state.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(state['phase'], 'BLOCKED_UNKNOWN')
        self.assertEqual(state['reason'], 'SHOP_CHUNK_FAILED')

    def test_state_dir_requires_browser_context(self):
        (self.stage / 'browser_context.json').unlink()
        argv = ['shop_sku_driver.py', '--input', str(self.source), '--state-dir', str(self.stage)]
        with patch.object(sys, 'argv', argv):
            with self.assertRaises(SystemExit):
                shop_sku_driver.main()


if __name__ == '__main__':
    unittest.main()
