"""Outcome execution protocol tests; genuine workflow probes are retained separately."""
import argparse,json,tempfile,unittest,hashlib
from unittest import mock
from pathlib import Path
from aetiory import engine as e

class FailureChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='aetiory-outcome-');self.root=Path(self.temp.name);self.entry=self.root/'entry.py'
    def tearDown(self):self.temp.cleanup()
    def observe(self,source,name='observe',max_events=1000):
        self.entry.write_text(source)
        return e.observe(argparse.Namespace(script=str(self.entry),module=[],input=[],arg=[],artifact=None,capture_outcome=True,out=str(self.root/name),max_events=max_events,timeout=3))
    def search(self,name='search',stdout_pointer=None,stdout_equals=None):
        return e.search(argparse.Namespace(observation=str(self.root/'observe/observation.json'),out=str(self.root/name),successful_exit=True,stdout_pointer=stdout_pointer,stdout_equals=stdout_equals,pointer=None,html_id=None,html_next_sibling=0,start=None,end=None,encoding='json',max_trials=16,seconds=20,timeout=3))
    def outcome(self,observation):return json.loads((Path(observation['observed']['directory'])/'outcome.json').read_bytes())
    def plan(self):return json.loads((self.root/'search/intervention.json').read_bytes())
    def replay(self,plan,name='replay'):
        plan.pop('plan_hash',None);plan['plan_hash']=e.sha(e.encoded(plan));file=self.root/(name+'.json');file.write_bytes(e.encoded(plan))
        return e.replay(argparse.Namespace(plan=str(file),out=str(self.root/name),timeout=3))
    def test_failure_is_observation_and_real_main_namespace(self):
        o=self.observe('import __main__\nassert __main__.__dict__ is globals()\nassert __main__.__file__==__file__\ndef decide():\n    return False\nif not decide():\n    raise ValueError("requested workflow failed")\nprint("done")\n')
        self.assertTrue(o['baseline_byte_parity']);self.assertEqual(o['status'],'observed');self.assertEqual(self.outcome(o)['kind'],'exception');self.assertEqual(self.outcome(o)['exception']['type'],'builtins.ValueError')
        self.assertEqual(o['manifest']['modules']['__main__'],o['manifest']['script'])
        r=self.search();self.assertEqual(r['status'],'influence_confirmed');p=self.plan();self.assertEqual(p['event']['module'],'__main__');self.assertEqual(self.replay(p)['status'],'reproduced')
    def test_exit_string_semantics(self):
        o=self.observe('import sys\nsys.exit("operator message")\n');out=self.outcome(o)
        self.assertEqual(out['kind'],'exit');self.assertEqual(out['exit_code'],1);self.assertEqual(out['stderr'],'operator message\n')
    def test_exit_normalization(self):
        for index,code in enumerate(['None','True','257','-1']):
            o=self.observe('import sys\nsys.exit('+code+')\n',name='exit-'+str(index));self.assertEqual(self.outcome(o)['exit_code'],[0,1,1,255][index])
        o=self.observe('import sys\nsys.exit(object())\n',name='opaque-exit');self.assertEqual(o['status'],'refused');self.assertIn('Opaque SystemExit',o['plain']['error']['message'])
    def test_oversized_system_exit_cannot_become_false_success(self):
        for index,code in enumerate(['2**100','-2**100','2**63']):
            o=self.observe('import sys\nsys.exit('+code+')\n',name='large-exit-'+str(index));self.assertEqual(o['status'],'refused');self.assertIn('signed-long',o['plain']['error']['message'])
    def test_stream_prefix_both_branches_and_predicate(self):
        o=self.observe('import sys,json\nprint("prefix",file=sys.stderr)\ndef decide():\n    return False\nif not decide():\n    raise ValueError("failed")\nprint(json.dumps({"done":True}))\n')
        r=self.search(stdout_pointer='/done',stdout_equals='true');self.assertEqual(r['status'],'influence_confirmed')
        trial=r['trials'][-1];child=json.loads((Path(trial['run']['child']['directory'])/'outcome.json').read_bytes());self.assertEqual(child['stderr'],'prefix\n')
        replay=self.replay(self.plan());self.assertEqual(replay['status'],'reproduced');self.assertTrue(replay['selected_changed'])
        bad=self.plan();bad['selector']['stdout_expected']=['bool',False];result=self.replay(bad,'forged-predicate');self.assertEqual(result['status'],'refused');self.assertFalse(result['selected_changed'])
    def test_stream_bounds_and_non_utf8_refuse(self):
        for name,source in [('large','print("x"*131073)\n'),('binary','import os\nos.write(1,b"\\xff")\n')]:
            o=self.observe(source,name=name);self.assertEqual(o['status'],'refused');self.assertFalse(o['plain']['ok'])
    def test_budget_refusal_not_target_exception(self):
        o=self.observe('def f():\n    return False\nf();f()\n',max_events=1);self.assertEqual(o['status'],'refused');self.assertFalse(o['observed']['ok']);self.assertFalse((Path(o['observed']['directory'])/'outcome.json').exists())
    def test_caught_engine_guards_cannot_become_target_outcomes(self):
        quota='def f():\n    return False\ntry:\n    f();f()\nexcept Exception:\n    pass\nraise ValueError("actual target failure")\n'
        o=self.observe(quota,max_events=1);self.assertEqual(o['status'],'refused');self.assertFalse(o['observed']['ok']);self.assertIn('caught by target',o['observed']['error']['message'])
        denied=self.root/'undeclared.txt';denied.write_text('owned synthetic fixture')
        o=self.observe('try:\n    open('+repr(str(denied))+').read()\nexcept Exception:\n    pass\nraise ValueError("actual target failure")\n',name='caught-read')
        self.assertEqual(o['status'],'refused');self.assertFalse(o['plain']['ok']);self.assertIn('caught by target',o['plain']['error']['message'])
    def test_caught_guard_before_target_cannot_fork(self):
        denied=self.root/'undeclared-before-split.txt';denied.write_text('owned synthetic fixture')
        source='from pathlib import Path\nif Path.cwd().name.startswith("trial-"):\n    try:\n        open('+repr(str(denied))+').read()\n    except Exception:\n        pass\ndef decide():\n    return False\nif not decide():\n    raise ValueError("failure")\n'
        self.observe(source);r=self.search();self.assertEqual(r['status'],'unresolved');self.assertTrue(r['trials'])
        self.assertTrue(all(not trial['run']['ok'] and 'child_pid' not in trial['run'] for trial in r['trials']))
    def test_expected_nonportable_check_is_not_a_guard_failure(self):
        o=self.observe('from collections import namedtuple\nT=namedtuple("T","value")\ndef f():\n    return T(3)\nf()\nraise ValueError("ordinary failure")\n');self.assertEqual(o['status'],'observed');self.assertEqual(self.outcome(o)['kind'],'exception')
    def test_successful_baseline_and_wrong_predicate_refusal(self):
        self.observe('print("success")\n')
        with self.assertRaises(e.Refusal):self.search()
        selector={'kind':'outcome','stdout_pointer':'/done','stdout_expected':['bool',True]}
        value={'schema':'target-outcome/1','kind':'exit','exit_code':0,'exception':None,'stdout':'not-json','stderr':''}
        self.assertFalse(e.outcome_goal(value,selector))
        with self.assertRaises(e.Refusal):e.validate_selector({'kind':'outcome','stdout_pointer':None,'stdout_expected':['none']})
    def test_stdout_object_predicate_is_key_order_independent_and_type_strict(self):
        selector={'kind':'outcome','stdout_pointer':'','stdout_expected':e.packed({'records':9,'batches':9})}
        value={'schema':'target-outcome/1','kind':'exit','exit_code':0,'exception':None,'stdout':'{"batches":9,"records":9}','stderr':''}
        self.assertTrue(e.outcome_goal(value,selector))
        value['stdout']='{"batches":9,"records":9.0}'
        self.assertFalse(e.outcome_goal(value,selector))
    def test_stdout_prefix_is_copied_before_child_continuation(self):
        self.observe('import sys\nprint(\'{"prefix":1,\',end="",flush=True)\ndef decide():\n    return False\nif not decide():\n    raise ValueError("failed")\nprint(\'"done":true}\')\n')
        r=self.search(stdout_pointer='/done',stdout_equals='true');self.assertEqual(r['status'],'influence_confirmed')
        child=json.loads((Path(r['trials'][-1]['run']['child']['directory'])/'outcome.json').read_bytes());self.assertEqual(json.loads(child['stdout']),{'prefix':1,'done':True})
    def test_interpreter_identity_bound_does_not_expand_source_bound(self):
        file=self.root/'large-binary-fixture'
        with file.open('wb') as output:
            for _ in range(9):output.write(b'x'*(1024*1024))
        with self.assertRaises(e.Refusal):e.identity(file)
        pinned=e.identity(file,128*1024*1024);self.assertEqual(pinned['bytes'],9*1024*1024);self.assertEqual(pinned['sha256'],hashlib.sha256(b'x'*(9*1024*1024)).hexdigest())
        with self.assertRaises(e.Refusal):e.validate_identity(pinned)
        e.validate_identity(pinned,128*1024*1024)
        oversized=dict(pinned,bytes=128*1024*1024+1)
        with self.assertRaises(e.Refusal):e.validate_identity(oversized,128*1024*1024)
        o=self.observe('pass\n');manifest=json.loads(json.dumps(o['manifest']));manifest['interpreter']['executable']=pinned;e.validate_manifest(manifest)
        manifest['inputs'].append(pinned)
        with self.assertRaises(e.Refusal):e.validate_manifest(manifest)
    def test_identity_stream_detects_actual_mid_hash_file_change(self):
        file=self.root/'changing-input';file.write_bytes(b'a'*(2*1024*1024));real=hashlib.sha256
        class ChangedDigest:
            def __init__(self):self.digest=real();self.changed=False
            def update(self,block):
                self.digest.update(block)
                if not self.changed:
                    self.changed=True
                    with file.open('ab') as output:output.write(b'changed')
            def hexdigest(self):return self.digest.hexdigest()
        with mock.patch.object(e.hashlib,'sha256',ChangedDigest):
            with self.assertRaisesRegex(e.Refusal,'changed during hashing'):e.identity(file)
    def test_execution_manifest_refusals(self):
        o=self.observe('print("ordinary")\n');m=o['manifest']
        for change in [{'stream_limit':131073},{'instrument_entry':False},{'schema':'unknown'}]:
            bad=json.loads(json.dumps(m));bad['execution'].update(change)
            with self.assertRaises(e.Refusal):e.validate_manifest(bad)
        bad=json.loads(json.dumps(m));bad['modules']['__main__']['sha256']='0'*64
        with self.assertRaises(e.Refusal):e.validate_manifest(bad)
        bad=json.loads(json.dumps(m));bad.pop('execution')
        with self.assertRaises(e.Refusal):e.validate_manifest(bad)
    def test_outcome_type_policy(self):
        source='import json\ndef optional():\n    return [(None,"-3e12",None,None)]\nvalue=optional()\nif value is not None:\n    raise ValueError("unknown option")\nprint(json.dumps({"accepted":True}))\n'
        self.observe(source);self.assertEqual(self.search(stdout_pointer='/accepted',stdout_equals='true')['status'],'influence_confirmed');self.assertEqual(self.plan()['replacement'],['none'])
        p=self.plan();m=json.loads(json.dumps(p['manifest']));m.pop('execution');m['modules']={'target':m['script']};m['artifact']='artifact.json';p['event']['module']='target';p['trace_evidence']['ancestry'][0]['module']='target';p['event']['ancestry_hash']=e.sha(e.encoded(p['trace_evidence']['ancestry']))
        with self.assertRaises(e.Refusal):e.validate_patch(p,m)

if __name__=='__main__':unittest.main()
