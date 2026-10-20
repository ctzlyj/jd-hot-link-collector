import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
import unittest
from resume_after_platform_cooldown import cooldown_elapsed, result_state


class PlatformCooldownTests(unittest.TestCase):
    def test_frequency_stop_maps_to_exhausted(self):
        self.assertEqual(
            result_state({'phase': 'BLOCKED_PLATFORM', 'platformReason': 'PAGE_FREQUENCY_LIMIT'}),
            {'state': 'EXHAUSTED', 'reason': 'PAGE_FREQUENCY_LIMIT'},
        )

    def test_verification_still_requires_human(self):
        self.assertEqual(
            result_state({'phase': 'BLOCKED_PLATFORM', 'platformReason': 'VERIFICATION_REQUIRED'})['state'],
            'HUMAN_REQUIRED',
        )

    def test_cooldown_gate_blocks_early_resume(self):
        ok, why = cooldown_elapsed({'updatedAt': '2026-10-13T16:34:56.072552+00:00'}, now=1791909296.0)
        self.assertFalse(ok)
        self.assertEqual(why, 'COOLDOWN_NOT_ELAPSED')

    def test_cooldown_gate_allows_after_wait(self):
        ok, why = cooldown_elapsed({'updatedAt': '2026-10-13T16:34:56.072552+00:00'}, now=1791914896.0)
        self.assertTrue(ok)
        self.assertIsNone(why)


if __name__ == '__main__':
    unittest.main()