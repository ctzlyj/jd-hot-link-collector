import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
import unittest
from resume_after_verification import result_state


class ResumeTests(unittest.TestCase):
    def test_validation_cannot_auto_repeat(self):
        self.assertEqual(result_state({'phase':'BLOCKED_PLATFORM','platformReason':'VERIFICATION_REQUIRED'})['state'],'HUMAN_REQUIRED')

    def test_frequency_cannot_reset_retry_budget(self):
        self.assertEqual(result_state({'phase':'BLOCKED_PLATFORM','platformReason':'PAGE_FREQUENCY_LIMIT'})['state'],'EXHAUSTED')

    def test_incomplete_prices_are_not_complete(self):
        self.assertEqual(result_state({'phase':'AWAITING_PRICE_DECISION'}),{'state':'STOP','reason':'AWAITING_PRICE_DECISION'})


if __name__ == '__main__':
    unittest.main()