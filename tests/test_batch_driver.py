"""Exercise the actual driver without any browser, product request or real cooldown."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts' / 'batch_driver'))

import contextlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import batch_driver

class BatchDriverTests(unittest.TestCase):
    def run_case(self,steps,validation,all_commands=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);stage=root/'state';stage.mkdir();skill=root/'skill';skill.mkdir()
            scope=validation.get('scope',1)
            (stage/'keyword_tasks.json').write_text(json.dumps({'kw':[{'pid':str(1000+i),'row':i+1} for i in range(scope)]}),encoding='utf-8')
            commands=[];remaining=list(steps);counter=[0]
            class FakeProcess:
                pid=987654
                def __init__(self,command,**kwargs):
                    commands.append(command);self.command=command
                def wait(self):
                    name=Path(self.command[0] if self.command[0]=='node' else self.command[-1]).name
                    if self.command[0]=='node':
                        if not remaining:raise AssertionError('Unexpected extra collection attempt')
                        step=remaining.pop(0);counter[0]+=1
                        state=dict(step,startedAt='run-'+str(counter[0]),currentProduct=step.get('currentProduct','p'),currentSku='s')
                        (stage/'runner_state.json').write_text(json.dumps(state),encoding='utf-8')
                        return 2 if step['state']=='HALTED' else 0
                    if Path(self.command[-1]).name=='verify_batch.py':
                        (stage/'independent_validation.json').write_text(json.dumps(validation),encoding='utf-8')
                    return 0
            with patch.object(batch_driver,'task_paths',return_value=(root,stage,skill)),patch.object(batch_driver.subprocess,'Popen',FakeProcess),patch.object(batch_driver.time,'sleep'),contextlib.redirect_stdout(io.StringIO()):
                batch_driver.main()
            state=json.loads((stage/'batch_driver_state.json').read_text(encoding='utf-8'))
            state['_errors']=sorted(x.name for x in (stage/'errors').glob('*.json')) if (stage/'errors').is_dir() else []
            self.assertFalse(remaining,'Not all intended phases executed')
            return state,commands if all_commands else [c for c in commands if c[0]=='node']

    def test_source_coverage_then_full_sku_prices_then_independent_acceptance(self):
        state,commands=self.run_case([{'state':'MAIN_SCAN_COMPLETE'},{'state':'DATA_COMPLETE'}],{'scope':154,'counts':{'VERIFIED':154},'complete':True})
        self.assertEqual(state['phase'],'DONE');self.assertTrue(state['complete'])
        self.assertIn('--main-only',commands[0]);self.assertNotIn('--main-only',commands[1])

    def test_each_checkpoint_stages_then_authors_then_verifies_without_extra_browser(self):
        state,commands=self.run_case([{'state':'MAIN_SCAN_COMPLETE'},{'state':'DATA_COMPLETE'}],{'scope':154,'counts':{'VERIFIED':154},'complete':True},all_commands=True)
        names=[Path(c[-1]).name for c in commands if c[0]!='node']
        expected=['stage_pending_materials.py','package_with_artifacts.py','verify_batch.py']
        self.assertEqual(names,expected*2)
        self.assertEqual(len([c for c in commands if c[0]=='node']),2)
        self.assertEqual(state['phase'],'DONE')

    def test_three_strikes_on_same_product_is_auto_isolated_and_batch_continues(self):
        stall={'state':'HALTED','reason':'REQUEST_RESULT_UNKNOWN','currentProduct':'10235419524374'}
        state,commands=self.run_case([stall,stall,stall,{'state':'DATA_COMPLETE'}],{'scope':65,'counts':{'VERIFIED':65},'complete':True})
        self.assertEqual(state['phase'],'DONE');self.assertTrue(state['complete'])
        self.assertEqual(state.get('isolatedProduct'),'10235419524374')
        self.assertEqual(state.get('stallCount'),0)
        self.assertEqual(state['_errors'],['10235419524374.json'])
    def test_missing_price_requires_real_supplement_and_is_not_completion(self):
        state,commands=self.run_case([{'state':'MAIN_SCAN_COMPLETE'},{'state':'DATA_COLLECTED_PRICE_PENDING'},{'state':'DATA_COLLECTED_PRICE_PENDING'}],{'scope':154,'counts':{'VERIFIED':8,'ARRIVAL_PRICE_PENDING':146},'complete':False})
        self.assertEqual(state['phase'],'AWAITING_PRICE_DECISION');self.assertFalse(state['complete'])
        self.assertIn('--recheck-prices',commands[-1]);self.assertNotIn('--recheck-prices',commands[1])

    def test_data_complete_does_not_override_incomplete_package_validation(self):
        state,_=self.run_case([{'state':'MAIN_SCAN_COMPLETE'},{'state':'DATA_COMPLETE'}],{'scope':154,'counts':{'VERIFIED':8,'PENDING':146},'complete':False})
        self.assertEqual(state['phase'],'BLOCKED_MATERIAL');self.assertFalse(state['complete'])

    def test_same_unresolved_sku_stops_after_three_attempts(self):
        state,commands=self.run_case([{'state':'HALTED','reason':'REQUEST_TIMEOUT'}]*3,{'scope':154,'counts':{'PENDING':154},'complete':False})
        self.assertEqual(state['phase'],'BLOCKED_STALL');self.assertEqual(state['stallCount'],3);self.assertEqual(len(commands),3)

    def test_verification_or_platform_refusal_stops_current_run_immediately(self):
        for reason in ['PAGE_FREQUENCY_LIMIT','HTTP_403_REFUSED','HTTP_429_RATE_LIMIT','VERIFICATION_REQUIRED','LOGIN_REQUIRED']:
            with self.subTest(reason=reason):
                state,commands=self.run_case([{'state':'HALTED','reason':reason}],{'scope':154,'counts':{'PENDING':154},'complete':False})
                self.assertEqual(state['phase'],'BLOCKED_PLATFORM');self.assertEqual(state['platformReason'],reason);self.assertEqual(len(commands),1)

if __name__=='__main__':unittest.main()