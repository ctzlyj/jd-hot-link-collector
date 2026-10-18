import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import os
os.environ.setdefault('JD_COLLECTOR_ROOT', tempfile.mkdtemp())
import package_live as pl

class FakeResponse:
    def __init__(self, status): self.status_code = status
class Fake404(Exception):
    def __init__(self): super().__init__('404'); self.response = FakeResponse(404)
class Fake500(Exception):
    def __init__(self): super().__init__('500'); self.response = FakeResponse(500)

class DetailJobTests(unittest.TestCase):
    def test_404_detail_links_are_skipped_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'详情图'; folder.mkdir()
            def save(u, dest):
                if u.endswith('dead.jpg'): raise Fake404()
                dest.write_bytes(b'ok')
            jobs, dead = pl._detail_jobs(['a.jpg','dead.jpg','b.jpg'], folder, save)
            self.assertEqual([u for u,_ in jobs], ['a.jpg','b.jpg'])
            self.assertEqual(dead, ['dead.jpg'])
            self.assertEqual(len(list(folder.glob('*.jpg'))), 2)
    def test_other_download_failures_still_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'详情图'; folder.mkdir()
            def save(u, dest): raise Fake500()
            with self.assertRaises(Fake500): pl._detail_jobs(['a.jpg'], folder, save)

if __name__=='__main__':unittest.main(verbosity=2)
