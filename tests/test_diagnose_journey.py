"""A direct-entry native diagnostic journey and agent result contract."""
import json
from pathlib import Path
import tempfile
import unittest
from aetiory import engine
from aetiory.diagnose import diagnose, parser
from aetiory.mcp import Server


class DiagnosisJourney(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.entry = self.root / 'job.py'
        self.entry.write_text('import json,sys\ndef capacity():\n    return 0\nn=capacity()\nif n<1:\n    raise ValueError("zero capacity")\nprint(json.dumps({"result":{"count":9,"checksum":45}},sort_keys=True))\n')

    def args(self, out='diagnosis', expected='{"checksum":45,"count":9}'):
        tokens = ['--script', str(self.entry), '--out', str(self.root/out),
            '--stdout-pointer','/result','--stdout-equals',expected,'--max-trials','8',
            '--seconds','10','--timeout','3']
        return parser().parse_args(tokens)

    def test_native_command_capture_replay_export_and_no_clobber(self):
        original=self.entry.read_bytes()
        result=diagnose(self.args())
        self.assertEqual(result['status'],'diagnosed',result)
        self.assertFalse(result['source_repair'])
        self.assertEqual(self.entry.read_bytes(),original)
        record=json.loads(Path(result['experiment_file']).read_bytes())['experiments'][0]
        self.assertEqual(record['selector']['kind'],'successful-exit')
        self.assertEqual(json.loads(record['artifacts']['before']['text'])['kind'],'exception')
        self.assertEqual(json.loads(record['artifacts']['after']['text'])['exit_code'],0)
        self.assertTrue(all(record['guards'].values()))
        with self.assertRaises(FileExistsError):
            diagnose(self.args())

    def test_wrong_stdout_goal_does_not_export_success(self):
        result=diagnose(self.args(expected='{"count":10,"checksum":45}'))
        self.assertEqual(result['status'],'unresolved',result)
        self.assertFalse((self.root/'diagnosis/viewer').exists())
        self.assertIsNone(json.loads(Path(result['search_file']).read_bytes())['intervention_file'])

    def test_resource_refusal_is_not_a_target_failure(self):
        self.entry.write_text('import socket\nsocket.socket().bind(("127.0.0.1",0))\n')
        result=diagnose(self.args())
        self.assertEqual(result['status'],'refused')
        self.assertNotIn('intervention_file',result)
        observation=json.loads(Path(result['observation_file']).read_bytes())
        self.assertFalse(observation['plain']['ok'])

    def test_native_agent_diagnosis_inspection_and_replay(self):
        server=Server(self.root,self.root/'state')
        result=server.call('diagnose_program',{'script':'job.py','stdout_pointer':'/result',
            'stdout_equals':'{"checksum":45,"count":9}','max_trials':8,'seconds':10,'timeout':3})
        self.assertEqual(result['status'],'diagnosed',result)
        inspected=server.call('inspect_experiment',{'handle':result['diagnosis']})
        self.assertEqual(inspected['kind'],'diagnosis')
        self.assertFalse(inspected['source_repair'])
        replay=server.call('replay_experiment',{'intervention':result['intervention'],'timeout':3})
        self.assertEqual(replay['status'],'reproduced')
        for arguments in [ {'script':'../escape.py'}, {'script':'job.py','modules':{'__main__':'job.py'}},
                           {'script':'job.py','stdout_pointer':'/result'}, {'script':'job.py','seconds':float('nan')} ]:
            with self.subTest(arguments=arguments),self.assertRaises((ValueError,engine.Refusal,FileNotFoundError)):
                server.call('diagnose_program',arguments)

if __name__=='__main__':
    unittest.main()
