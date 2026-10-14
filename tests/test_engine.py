import argparse, json, sys, tempfile, unittest, os, signal, subprocess, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aetiory import engine as e

class EngineChecks(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='causal-engine-checks-');self.root=Path(self.t.name)
        self.module=self.root/'target.py';self.input=self.root/'input.json';self.script=self.root/'entry.py'
        self.module.write_text('def opaque():\n    return (x for x in range(2))\ndef compute(x):\n    iterator=opaque()\n    return next(iterator)+x*2\n')
        self.input.write_text('{"n":3}\n');self.entry('normal')
    def tearDown(self):self.t.cleanup()
    def entry(self,kind):
        head='import target,json,sys\nfrom pathlib import Path\n'
        if kind=='threads':body='import threading\nev=threading.Event();thread=threading.Thread(target=ev.wait);thread.start()\ntry:\n    n=json.loads(Path(sys.argv[1]).read_bytes())["n"]\n    result=target.compute(n)\n    Path("artifact.json").write_text(json.dumps({"answer":result,"untouched":13}))\nfinally:\n    ev.set();thread.join()\n'
        elif kind=='stream':body='with Path(sys.argv[1]).open() as stream:\n    n=json.load(stream)["n"]\n    result=target.compute(n)\n    Path("artifact.json").write_text(json.dumps({"answer":result,"untouched":13}))\n'
        elif kind=='loop-child':body='n=json.loads(Path(sys.argv[1]).read_bytes())["n"]\nresult=target.compute(n)\nif result==7:\n    while True:pass\nPath("artifact.json").write_text(json.dumps({"answer":result,"untouched":13}))\n'
        else:body='n=json.loads(Path(sys.argv[1]).read_bytes())["n"]\nresult=target.compute(n)\nPath("artifact.json").write_text(json.dumps({"answer":result,"untouched":13}))\n'
        self.script.write_text(head+body)
    def observation(self,name='observation'):
        return e.observe(argparse.Namespace(script=str(self.script),module=['target='+str(self.module)],input=[str(self.input)],arg=[str(self.input)],artifact='artifact.json',out=str(self.root/name),max_events=1000,timeout=3))
    def search(self,name='search',observation='observation'):
        return e.search(argparse.Namespace(observation=str(self.root/observation/'observation.json'),out=str(self.root/name),pointer='/answer',html_id=None,html_next_sibling=0,start=None,end=None,encoding='json',max_trials=8,seconds=20,timeout=3))
    def plan(self):
        self.observation();r=self.search();self.assertEqual(r['status'],'influence_confirmed')
        return json.loads((self.root/'search/intervention.json').read_bytes())
    def run_plan(self,plan,name='replay'):
        p=self.root/(name+'.json');p.write_bytes(e.encoded(plan)+b'\n')
        return e.replay(argparse.Namespace(plan=str(p),out=str(self.root/name),timeout=3))
    def seal(self,plan):
        plan.pop('plan_hash',None);plan['plan_hash']=e.sha(e.encoded(plan));return plan
    def test_paired_generator_and_roundtrip(self):
        plan=self.plan();self.assertEqual(plan['backend'],'paired-os-fork');self.assertGreater(plan['trace_evidence']['opaque_prior_count'],0)
        r=self.run_plan(plan);self.assertEqual(r['status'],'reproduced');self.assertTrue(r['counterfactual']['child_reaped']);self.assertTrue(r['undo_byte_identical'])
    def test_planhash_refusal(self):
        plan=self.plan();plan['replacement']=['int','12']
        with self.assertRaises(e.Refusal):self.run_plan(plan)
    def test_event_value_ancestry_prefix_refusals(self):
        plan=self.plan()
        for field,value in [('site','999:9'),('value_hash','0'*64),('ancestry_hash','0'*64),('prefix_before','0'*64)]:
            with self.subTest(field=field):
                p=json.loads(json.dumps(plan));p['event'][field]=value;self.seal(p)
                if field in ('value_hash','ancestry_hash'):
                    with self.assertRaises(e.Refusal):self.run_plan(p,'bad-'+field)
                    continue
                r=self.run_plan(p,'bad-'+field)
                self.assertEqual(r['status'],'refused');self.assertIn(field,r['counterfactual']['error']['message']);self.assertNotIn('child_pid',r['counterfactual'])
    def test_source_input_interpreter_refusal(self):
        plan=self.plan()
        for filename,change in [(self.module,b'\n# changed source\n'),(self.input,b' '),(self.script,b'\n# changed entry\n')]:
            original=filename.read_bytes();filename.write_bytes(original+change)
            try:
                with self.assertRaises(e.Refusal):self.run_plan(plan,'changed-'+filename.stem)
            finally:filename.write_bytes(original)
        p=json.loads(json.dumps(plan));p['manifest']['interpreter']['version']='different';p['manifest_hash']=e.sha(e.encoded(p['manifest']));self.seal(p)
        with self.assertRaises(e.Refusal):self.run_plan(p,'bad-interpreter')
    def test_opaque_return_target_refusal(self):
        plan=self.plan();events=list(e.load_events(self.root/'observation/observed/trace.jsonl.gz'));opaque=next(x for x in events if x['opaque_marker'])
        plan['event']={k:opaque[k] for k in ['id','module','site','function','value_hash','prefix_before','ancestry_hash']};plan['replacement']=['int','12'];self.seal(plan)
        with self.assertRaises(e.Refusal):self.run_plan(plan)
    def test_thread_and_open_stream_refusals(self):
        for kind in ['threads','stream']:
            with self.subTest(kind=kind):
                self.entry(kind);o=self.observation(kind+'-obs');self.assertTrue(o['baseline_byte_parity']);r=self.search(kind+'-search',kind+'-obs')
                self.assertEqual(r['status'],'unresolved');self.assertTrue(r['undo_byte_identical']);self.assertGreater(r['trial_count'],0)
                self.assertTrue(all('nonstandard open streams' in x['run']['error']['message'] for x in r['trials']))
                self.assertTrue(all('child_pid' not in x['run'] for x in r['trials']))
    def test_paired_timeout(self):
        self.entry('loop-child');self.observation();m=json.loads((self.root/'observation/manifest.json').read_bytes());events=list(e.load_events(self.root/'observation/observed/trace.jsonl.gz'));target=next(x for x in events if x['portable'] and x['packed']==['int','6'])
        plan={'event':{k:target[k] for k in ['id','module','site','function','value_hash','prefix_before','ancestry_hash']},'replacement':['int','7'],'trace_evidence':{k:target[k] for k in ['packed','ancestry','prefix_scope','opaque_prior_count']}}
        r=e.run_once(m,self.root,'timeout-pair','paired',.3,patch=plan);self.assertFalse(r['ok']);self.assertEqual(r['error']['type'],'Timeout')
        receipt=self.root/'timeout-pair/receipt.json'
        self.assertTrue(receipt.is_file(), 'Timeout must retain the native child-reap receipt')
        actual=json.loads(receipt.read_bytes());self.assertTrue(actual.get('child_reaped'))
    def test_no_clobber_and_parser_bounds(self):
        out=self.root/'existing';out.mkdir();sentinel=out/'keep';sentinel.write_bytes(b'untouched')
        with self.assertRaises(FileExistsError):self.observation('existing')
        self.assertEqual(sentinel.read_bytes(),b'untouched')
        with self.assertRaises(e.Refusal):e.pointer_tokens('/a~2b')
        with self.assertRaises(e.Refusal):e.html_tree(b'<div id="x"></div><div id="x"></div>').selected('x',0)
        before=e.html_tree(b'<p>before</p><div id="x">same</div>');after=e.html_tree(b'<p>long changed preceding text</p><div id="x">same</div>');self.assertEqual(before.selected('x',0),after.selected('x',0))
    def test_api_budget_refusal(self):
        with self.assertRaises(e.Refusal):e.validate_api(argparse.Namespace(timeout=float('nan')))
        with self.assertRaises(e.Refusal):e.validate_api(argparse.Namespace(timeout=3,max_trials=1,seconds=float('inf'),html_next_sibling=0,start=None,end=None),search_mode=True)
    def test_selector_semantics_and_trace_binding(self):
        plan=self.plan()
        unchanged=json.loads(json.dumps(plan));unchanged['selector']['pointer']='/untouched';self.seal(unchanged)
        r=self.run_plan(unchanged,'unchanged');self.assertEqual(r['status'],'refused');self.assertFalse(r['selected_changed'])
        for field,value in [('selector',{'kind':'jsonpath','encoding':'json','pointer':'/absent'}),('selector',{'kind':'unrecognized'}),('trace_evidence',{}),('trace_evidence',dict(plan['trace_evidence'],packed=['int','999999'])),('trace_evidence',dict(plan['trace_evidence'],ancestry=[]))]:
            with self.subTest(value=value):
                bad=json.loads(json.dumps(plan));bad[field]=value;self.seal(bad)
                with self.assertRaises(e.Refusal):self.run_plan(bad,'invalid-'+str(len(list(self.root.glob('invalid-*')))))
        bad=json.loads(json.dumps(plan));bad['trace_evidence']['opaque_prior_count']=0;self.seal(bad)
        r=self.run_plan(bad,'bad-opaque-count');self.assertEqual(r['status'],'refused');self.assertIn('opaque_prior_count',r['counterfactual']['error']['message']);self.assertNotIn('child_pid',r['counterfactual'])
    def test_imported_manifest_bounds(self):
        plan=self.plan()
        for field,value in [('max_events',500001),('max_events',True),('arguments',['a']*65),('arguments',['a'*4097]),('modules',[]),('modules',{}),('artifact','receipt.json'),('inputs',{}),('script',{})]:
            with self.subTest(field=field,value=value):
                bad=json.loads(json.dumps(plan));bad['manifest'][field]=value;bad['manifest_hash']=e.sha(e.encoded(bad['manifest']));self.seal(bad)
                with self.assertRaises(e.Refusal):self.run_plan(bad,'bound-'+field)
    def test_host_cancellation_reaps_child(self):
        self.entry('loop-child');self.observation();m=json.loads((self.root/'observation/manifest.json').read_bytes());events=list(e.load_events(self.root/'observation/observed/trace.jsonl.gz'));target=next(x for x in events if x['portable'] and x['packed']==['int','6'])
        patch={'event':{k:target[k] for k in ['id','module','site','function','value_hash','prefix_before','ancestry_hash']},'replacement':['int','7'],'trace_evidence':{k:target[k] for k in ['packed','ancestry','prefix_scope','opaque_prior_count']}}
        config=self.root/'cancel.json';config.write_bytes(e.encoded({'manifest':m,'patch':patch}))
        host=self.root/'host.py';host.write_text('import sys,json\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(Path(e.__file__).parent.parent))+')\nfrom aetiory import engine as e\nc=json.loads(Path(sys.argv[1]).read_bytes())\ntry:e.run_once(c["manifest"],Path(sys.argv[1]).parent,"cancel-pair","paired",30,patch=c["patch"])\nexcept KeyboardInterrupt:raise SystemExit(42)\n')
        process=subprocess.Popen([sys.executable,str(host),str(config)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+5
            while not (self.root/'cancel-pair/child/stdout.txt').is_file() and process.poll() is None and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue((self.root/'cancel-pair/child/stdout.txt').is_file(),'Actual fork must precede host cancellation')
            os.kill(process.pid,signal.SIGINT);stdout,stderr=process.communicate(timeout=5);self.assertEqual(process.returncode,42,stderr.decode())
            receipt=json.loads((self.root/'cancel-pair/receipt.json').read_bytes());self.assertTrue(receipt['child_reaped']);self.assertIsNotNone(receipt['child_wait_status'])
        finally:
            if process.poll() is None:process.kill();process.wait()
            process.communicate()
    def test_portable_types(self):
        for v in [None,False,3,-0.0,1.2,'text',[1,2],('a',True),{'x':[3]}]:self.assertEqual(e.packed(e.unpacked(e.packed(v))),e.packed(v))
        with self.assertRaises(e.Refusal):e.packed(float('nan'))
        with self.assertRaises(e.Refusal):e.unpacked(['generator-state','invented'])
        x=[];x.append(x)
        with self.assertRaises(e.Refusal):e.packed(x)

if __name__=='__main__':unittest.main()
