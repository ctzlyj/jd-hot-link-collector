import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import unittest
from unittest.mock import patch
from datetime import datetime,timezone
from resume_policy import next_action
class ResumeTests(unittest.TestCase):
 def test_validation_never_auto_retried(self):self.assertEqual(next_action('VERIFICATION_REQUIRED',0,0)['action'],'HUMAN_REQUIRED')
 def test_login_denial_never_retried(self):self.assertEqual(next_action('LOGIN_REQUIRED',0,0)['action'],'HUMAN_REQUIRED')
 def test_uncertain_never_replayed(self):self.assertEqual(next_action('REQUEST_RESULT_UNKNOWN',0,0)['action'],'RECONCILE_REQUIRED')
 def test_refusal_uses_increasing_backoff(self):
  a=next_action('HTTP_403_REFUSED',1,100);self.assertEqual(a['action'],'WAIT_AND_PROBE');self.assertEqual(a['notBefore'],1900)
 def test_repeated_refusal_has_bound(self):self.assertEqual(next_action('HTTP_403_REFUSED',3,100)['action'],'STOP_REFUSED')
 def test_deliberate_throttle_is_not_failure(self):self.assertEqual(next_action('COOLDOWN_REQUIRED',0,100)['action'],'WAIT_AND_RESUME')
 def test_server_cooldown_is_respected(self):self.assertEqual(next_action('HTTP_429_RATE_LIMIT',0,100,'2400')['notBefore'],2500)
 def test_server_http_date_is_respected(self):self.assertEqual(next_action('HTTP_429_RATE_LIMIT',0,0,'Thu, 01 Jan 1970 01:00:00 GMT')['notBefore'],3600)
 def test_bad_retry_after_keeps_local_backoff(self):self.assertEqual(next_action('HTTP_429_RATE_LIMIT',0,0,'bad')['notBefore'],900)
