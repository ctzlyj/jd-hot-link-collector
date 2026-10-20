import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))
import unittest
from driver_policy import initial_phase,stall_state,recovery_decision
class DriverPolicyTests(unittest.TestCase):
    def test_old_scope_resumes_with_main_coverage_priority(self):self.assertEqual(initial_phase({'phase':'BLOCKED_PLATFORM'}),'HEADERS')
    def test_current_work_phase_survives_platform_pause(self):self.assertEqual(initial_phase({'coverageVersion':2,'workPhase':'SWEEP','phase':'BLOCKED_PLATFORM'}),'SWEEP')
    def test_json_list_key_counts_consecutive_stalls(self):
        a=stall_state({},('p','s','REQUEST_TIMEOUT'));b=stall_state(a,('p','s','REQUEST_TIMEOUT'));self.assertEqual(b['stallCount'],2);self.assertEqual(stall_state(b,('p','different','REQUEST_TIMEOUT'))['stallCount'],1)
    def test_verification_is_never_automatically_retried(self):
        for r in ['VERIFICATION_REQUIRED','LOGIN_REQUIRED','LOGIN_STATE_UNKNOWN']:
            self.assertEqual(recovery_decision({'phase':'BLOCKED_PLATFORM','platformReason':r},{},0)['action'],'HUMAN_REQUIRED')
    def test_refusals_have_finite_backoff(self):
        d={'phase':'BLOCKED_PLATFORM','platformReason':'PAGE_FREQUENCY_LIMIT'}
        self.assertEqual(recovery_decision(d,{'attempts':1},100)['notBefore'],5500)
        self.assertEqual(recovery_decision(d,{'attempts':3},100)['action'],'EXHAUSTED')
    def test_pending_prices_are_not_business_success(self):self.assertEqual(recovery_decision({'phase':'AWAITING_PRICE_DECISION'},{},0)['action'],'STOP')