import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from package_contract import decode_detail_payload,ordered_detail_urls
class DetailEncodingTests(unittest.TestCase):
    def sample(self):
        text='\u690d\u7269\u6807\u672c\u6750\u6599'
        image='<img src='+chr(39)+'https://img10.360buyimg.com/image.jpg'+chr(39)+'>'
        return 'showdesc('+json.dumps({'content':'<div>'+text+'</div>'+image},ensure_ascii=False)+')'
    def test_utf8_preserves_source_text(self):
        self.assertEqual(decode_detail_payload(self.sample().encode('utf-8')),self.sample())
    def test_actual_legacy_encoding_preserves_source_text(self):
        self.assertEqual(decode_detail_payload(self.sample().encode('gb18030')),self.sample())
    def test_both_encodings_produce_same_document_image_order(self):
        a=ordered_detail_urls(decode_detail_payload(self.sample().encode('utf-8')))
        b=ordered_detail_urls(decode_detail_payload(self.sample().encode('gb18030')))
        self.assertEqual(a,b);self.assertEqual(len(a),1)
    def test_invalid_bytes_are_not_silently_replaced(self):
        with self.assertRaises(UnicodeDecodeError):decode_detail_payload(bytes([255,255]))
