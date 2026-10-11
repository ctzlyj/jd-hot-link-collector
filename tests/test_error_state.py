import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from package_contract import error_state
class ErrorStateTests(unittest.TestCase):
    def test_price_pending_not_unavailable(self):self.assertEqual(error_state({'reason':'ARRIVAL_PRICE_MISSING'}),'ARRIVAL_PRICE_PENDING')
    def test_only_explicit_unavailable(self):self.assertEqual(error_state({'reason':'PRODUCT_UNAVAILABLE'}),'PRODUCT_UNAVAILABLE')
    def test_unknown_stays_unresolved(self):self.assertEqual(error_state({'reason':'HTTP_403_REFUSED'}),'ACCESS_REFUSED')
if __name__=='__main__':unittest.main()
