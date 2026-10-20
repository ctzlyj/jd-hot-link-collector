"""Actual keeper control flow with an offline process fixture; never touch the browser."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))

import contextlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import driver_keeper

class KeeperTests(unittest.TestCase):
    def run_case(self,initial,results,attempts=1):
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp);(stage/'batch_driver_state.json').write_text(json.dumps(initial),encoding='utf-8')
            keeper={'attempts':attempts,'nextRetryAt':'1970-01-01T00:01:40+00:00'}
            (stage/'keeper_state.json').write_text(json.dumps(keeper),encoding='utf-8')
            clock=[50];sleeps=[];children=[];remaining=list(results)
            def sleep(seconds):sleeps.append(seconds);clock[0]+=seconds
            class FakeProcess:
                pid=12345
                def __init__(self,command,**kwargs):children.append(command)
                def wait(self):
                    if not remaining:raise AssertionError('Unexpected extra retry')
                    state=remaining.pop(0);(stage/'batch_driver_state.json').write_text(json.dumps(state),encoding='utf-8');return 0
            with patch.dict(driver_keeper.os.environ,{'JD_BATCH_STATE_DIR':str(stage)}),patch.object(driver_keeper.time,'time',lambda:clock[0]),patch.object(driver_keeper.time,'sleep',sleep),patch.object(driver_keeper.subprocess,'Popen',FakeProcess),contextlib.redirect_stdout(io.StringIO()):
                driver_keeper.main()
            output=json.loads((stage/'keeper_state.json').read_text(encoding='utf-8'))
            return output,sleeps,children,remaining

    def refused(self):return {'phase':'BLOCKED_PLATFORM','platformReason':'PAGE_FREQUENCY_LIMIT'}

    def test_idle_restart_preserves_promised_deadline_and_remaining_attempt_budget(self):
        result,sleeps,children,remaining=self.run_case(self.refused(),[self.refused(),self.refused()])
        self.assertEqual(sleeps,[50,7200]);self.assertEqual(len(children),2)
        self.assertEqual(result['state'],'EXHAUSTED');self.assertEqual(result['attempts'],3);self.assertFalse(remaining)

    def test_verification_stops_without_new_request_or_cooldown_reset(self):
        for reason in ['VERIFICATION_REQUIRED','LOGIN_REQUIRED']:
            result,sleeps,children,_=self.run_case({'phase':'BLOCKED_PLATFORM','platformReason':reason},[])
            self.assertEqual(result['state'],'HUMAN_REQUIRED');self.assertFalse(children);self.assertFalse(sleeps)

    def test_new_verification_does_not_retry_or_forget_attempt_count(self):
        result,sleeps,children,_=self.run_case(self.refused(),[{'phase':'BLOCKED_PLATFORM','platformReason':'VERIFICATION_REQUIRED'}])
        self.assertEqual(result['state'],'HUMAN_REQUIRED');self.assertEqual(result['attempts'],2);self.assertEqual(len(children),1)

    def test_done_requires_driver_verified_terminal_state_and_no_extra_child(self):
        result,sleeps,children,_=self.run_case(self.refused(),[{'phase':'DONE','complete':True}])
        self.assertEqual(result['state'],'STOP');self.assertEqual(result['reason'],'DONE');self.assertEqual(len(children),1)

    def test_pending_prices_terminate_for_user_decision_not_success(self):
        result,sleeps,children,_=self.run_case(self.refused(),[{'phase':'AWAITING_PRICE_DECISION','complete':False}])
        self.assertEqual(result['reason'],'AWAITING_PRICE_DECISION');self.assertEqual(len(children),1)

if __name__=='__main__':unittest.main()