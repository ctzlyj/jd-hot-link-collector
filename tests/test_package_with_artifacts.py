import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from openpyxl import load_workbook
from package_with_artifacts import write_artifact


class ArtifactAdapterTests(unittest.TestCase):
    def spec(self, stage):
        output = stage / 'packages' / '1' / 'product.xlsx'
        output.parent.mkdir(parents=True, exist_ok=True)
        headers = ['*标题', '货号', '商品属性', '类目', '品牌', '规格1', '规格2', '*价格', '库存']
        row = ['Product', '', '', '', '', '', '', 9.5, 999]
        return {'headers': headers, 'rows': [row], 'output': str(output)}, output

    def test_spec_is_authored_with_readback_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            spec, output = self.spec(stage)
            with patch.dict(os.environ, {'JD_COLLECTOR_STATE_DIR': str(stage)}):
                self.assertEqual(write_artifact(spec), str(output))
            saved = json.loads((output.parent / 'artifact_workbook_spec.json').read_text(encoding='utf-8'))
            self.assertEqual(saved, [spec])
            wb = load_workbook(output)
            rows = list(wb.active.values)
            wb.close()
            self.assertEqual(rows[0][0], '*标题'); self.assertEqual(rows[0][7], '*价格')
            self.assertEqual(rows[1][0], 'Product'); self.assertEqual(rows[1][7], 9.5); self.assertEqual(rows[1][8], 999)

    def test_outputs_outside_owned_packages_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'JD_COLLECTOR_STATE_DIR': tmp}):
                with self.assertRaisesRegex(ValueError, 'OUTSIDE_TASK_PACKAGE'):
                    write_artifact({'headers': ['a'], 'rows': [['b']], 'output': str(Path(tmp) / 'source.xlsx')})
            self.assertFalse((Path(tmp) / 'source.xlsx').exists())

    def test_author_failure_propagates_before_any_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            spec, output = self.spec(stage)
            with patch.dict(os.environ, {'JD_COLLECTOR_STATE_DIR': str(stage)}), \
                 patch('workbook_author_openpyxl.write_artifact', side_effect=RuntimeError('author down')):
                with self.assertRaisesRegex(RuntimeError, 'author down'):
                    write_artifact(spec)


if __name__ == '__main__':
    unittest.main()
