import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import struct,unittest
from media_guard import inspect_mp4
box=lambda k,b:struct.pack('>I4s',len(b)+8,k)+b
class MediaTests(unittest.TestCase):
 def data(self):
  mvhd=bytes(12)+struct.pack('>II',1000,32040)
  return box(b'ftyp',b'isom')+box(b'moov',box(b'mvhd',mvhd))+box(b'mdat',b'media')
 def test_real_structure(self):self.assertEqual(inspect_mp4(self.data())['durationSeconds'],32.04)
 def test_truncated_refused(self):
  with self.assertRaises(ValueError):inspect_mp4(self.data()[:-1])
 def test_html_is_not_video(self):
  with self.assertRaises(ValueError):inspect_mp4('<html>京东验证</html>'.encode('utf-8'))
if __name__=='__main__':unittest.main(verbosity=2)
