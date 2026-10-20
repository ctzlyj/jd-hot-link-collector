import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
import unittest
from resume_after_local_recovery import result_state


class LocalRecoveryTests(unittest.TestCase):
    def test_local_transport_stops_as_plain_stop(self):
        self.assertEqual(
            result_state({'phase': 'BLOCKED_UNKNOWN', 'reason': 'LOCAL_OR_TRANSPORT_ERROR'}),
            {'state': 'STOP', 'reason': 'BLOCKED_UNKNOWN'},
        )

    def test_platform_verification_still_requires_human(self):
        self.assertEqual(
            result_state({'phase': 'BLOCKED_PLATFORM', 'platformReason': 'VERIFICATION_REQUIRED'})['state'],
            'HUMAN_REQUIRED',
        )

    def test_refusal_does_not_become_local_recovery(self):
        self.assertEqual(
            result_state({'phase': 'BLOCKED_PLATFORM', 'platformReason': 'HTTP_429_RATE_LIMIT'})['state'],
            'EXHAUSTED',
        )


if __name__ == '__main__':
    unittest.main()