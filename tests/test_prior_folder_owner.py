import sys, unittest, tempfile, json, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
os.environ.setdefault('JD_COLLECTOR_ROOT', tempfile.mkdtemp())
import package_live as pl

class PriorOwnerTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get('JD_COLLECTOR_PRIOR_RECEIPTS')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.idx = Path(self.tmp.name)/'prior.json'
        self.idx.write_text(json.dumps([
            {'sourceSku':'1001','folder':r'D:\root\kw\title A'},
            {'sourceSku':'1002','folder':r'D:\root\kw\title B'}]), encoding='utf-8')
        os.environ['JD_COLLECTOR_PRIOR_RECEIPTS'] = str(self.idx)
    def tearDown(self):
        if self._old is None: os.environ.pop('JD_COLLECTOR_PRIOR_RECEIPTS', None)
        else: os.environ['JD_COLLECTOR_PRIOR_RECEIPTS'] = self._old
    def test_same_pid_prior_package_is_replaceable(self):
        self.assertTrue(pl.prior_folder_owner(r'D:\root\kw\title A', '1001'))
    def test_different_pid_folder_is_not_replaceable(self):
        self.assertFalse(pl.prior_folder_owner(r'D:\root\kw\title A', '1002'))
    def test_unknown_folder_is_not_replaceable(self):
        self.assertFalse(pl.prior_folder_owner(r'D:\root\kw\title C', '1001'))
    def test_no_registry_means_never_replaceable(self):
        os.environ.pop('JD_COLLECTOR_PRIOR_RECEIPTS', None)
        self.assertFalse(pl.prior_folder_owner(r'D:\root\kw\title A', '1001'))
    def test_corrupt_registry_fails_closed(self):
        self.idx.write_text('not json', encoding='utf-8')
        self.assertFalse(pl.prior_folder_owner(r'D:\root\kw\title A', '1001'))

class DetailImageTests(unittest.TestCase):
    def test_parsed_document_with_zero_images_is_cached_and_allowed(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp)
            doc = 'showdesc(' + json.dumps({'content': '<p class="shop-editor-floor"></p><br/>'}) + ')'
            with patch.object(pl, 'STAGE', stage), patch.object(pl, 'get_public', return_value=doc.encode('utf-8')):
                self.assertEqual(pl.details('10036249167890'), [])
            self.assertTrue((stage/'details_ordered'/'10036249167890.json').exists())
            with patch.object(pl, 'STAGE', stage), patch.object(pl, 'get_public', side_effect=AssertionError('network touched again')):
                self.assertEqual(pl.details('10036249167890'), [])

if __name__=='__main__':unittest.main(verbosity=2)
