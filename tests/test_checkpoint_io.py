import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from checkpoint_io import atomic_state


class CheckpointIOTests(unittest.TestCase):
    def test_temporary_windows_lock_retries_only_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            calls = []
            original = Path.replace
            def replace(source, destination):
                calls.append(destination)
                if len(calls) < 3:
                    raise PermissionError('Temporary local file lock')
                return original(source, destination)
            waits = []
            with patch.object(Path, 'replace', replace):
                atomic_state(path, {'state': 'HALTED'}, sleep=waits.append)
            self.assertEqual(json.loads(path.read_text()), {'state': 'HALTED'})
            self.assertEqual(len(calls), 3)
            self.assertEqual(len(waits), 2)

    def test_persistent_lock_is_bounded_and_preserves_old_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'state.json'
            path.write_text('{"state":"OLD"}')
            with patch.object(Path, 'replace', side_effect=PermissionError('Lock')) as replace:
                with self.assertRaises(PermissionError):
                    atomic_state(path, {'state': 'NEW'}, sleep=lambda _: None)
            self.assertEqual(replace.call_count, 8)
            self.assertEqual(json.loads(path.read_text()), {'state': 'OLD'})
            self.assertTrue(path.with_suffix('.json.pending').exists())

    def test_other_filesystem_error_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(Path, 'replace', side_effect=OSError('Disk error')) as replace:
                with self.assertRaises(OSError):
                    atomic_state(Path(tmp) / 'state.json', {}, sleep=lambda _: None)
            self.assertEqual(replace.call_count, 1)


if __name__ == '__main__':
    unittest.main()