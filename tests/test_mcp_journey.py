"""Actual native engine through MCP framing, not engine doubles."""
import io
import json
import pathlib
import tempfile
import unittest
from aetiory.mcp import Server, serve


class NativeToolJourney(unittest.TestCase):
    def test_observe_search_inspect_replay_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory).resolve()
            (root/'target.py').write_text('def start():\n    return (x for x in range(2))\ndef compute(x):\n    iterator=start()\n    return next(iterator)+x*2\n')
            (root/'input.json').write_text('{"n":3}\n')
            (root/'entry.py').write_text('import json,sys,target\nfrom pathlib import Path\nx=json.loads(Path(sys.argv[1]).read_bytes())["n"]\nv=target.compute(x)\nPath("artifact.json").write_text(json.dumps({"answer":v,"untouched":13}))\n')
            server = Server(root, root/'state')
            sequence = 0
            def rpc(method, params):
                nonlocal sequence
                sequence += 1
                output = io.StringIO()
                request = {'jsonrpc':'2.0','id':sequence,'method':method,'params':params}
                serve(server, io.BytesIO((json.dumps(request)+'\n').encode()), output)
                response = json.loads(output.getvalue())
                self.assertEqual(response['id'], sequence)
                self.assertNotIn('error', response)
                return response['result']
            rpc('initialize', {'protocolVersion':'2025-11-25','clientInfo':{'name':'native-contract','version':'1'},'capabilities':{}})
            serve(server, io.BytesIO(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'), io.StringIO())
            def tool(name, arguments):
                response = rpc('tools/call', {'name':name,'arguments':arguments})
                self.assertFalse(response.get('isError'), response)
                self.assertEqual(json.loads(response['content'][0]['text']), response['structuredContent'])
                return response['structuredContent']
            observation = tool('observe_program', {'script':'entry.py','modules':{'target':'target.py'},'inputs':['input.json'],'arguments':['@input:0'],'artifact':'artifact.json','timeout':3})
            self.assertTrue(observation['baseline_byte_parity'])
            search = tool('find_influence', {'observation':observation['observation'],'selector':{'pointer':'/answer'},'timeout':3,'max_trials':8,'seconds':20})
            self.assertEqual(search['status'], 'influence_confirmed')
            inspected = tool('inspect_experiment', {'handle':search['intervention']})
            self.assertEqual(inspected['kind'], 'intervention')
            replay = tool('replay_experiment', {'intervention':search['intervention'],'timeout':3})
            self.assertEqual(replay['status'], 'reproduced')
            from aetiory.export import experiment, export_record
            payload = {'schema':'experiment-view/1','experiments':[experiment(observation['report_file'],search['report_file'],replay_path=replay['report_file'])]}
            exported = export_record(payload, root/'viewer')
            self.assertEqual(exported['status'], 'exported')
            record = json.loads((root/'viewer/experiment.json').read_bytes())['experiments'][0]
            self.assertEqual(record['changes'], [{'path':'/answer','before':6,'after':7,'selected':True}])
            self.assertTrue(all(record['guards'].values()))
            html = (root/'viewer/index.html').read_text()
            self.assertIn('id="embedded-record"', html)
            self.assertNotIn('src="app.js"', html)
            with self.assertRaises(FileExistsError):
                export_record(payload, root/'viewer')
            from aetiory.engine import Refusal
            # Contradictory success flags and selector descriptions must never
            # acquire accepted export provenance, even when artifact bytes exist.
            for report_path, trail, value in [
                (replay['report_file'], ('counterfactual','ok'), False),
                (replay['report_file'], ('counterfactual','child','ok'), False),
                (replay['report_file'], ('fresh_undo','ok'), False),
                (replay['report_file'], ('fresh_baseline','ok'), False),
                (search['report_file'], ('fresh_undo','ok'), False),
                (search['report_file'], ('selector','pointer'), '/untouched'),
                (observation['report_file'], ('plain','ok'), False),
            ]:
                report_path = pathlib.Path(report_path)
                original = report_path.read_bytes()
                altered = json.loads(original)
                parent = altered
                for key in trail[:-1]:
                    parent = parent[key]
                parent[trail[-1]] = value
                report_path.write_text(json.dumps(altered))
                try:
                    with self.subTest(trail=trail), self.assertRaises(Refusal):
                        experiment(observation['report_file'],search['report_file'],replay_path=replay['report_file'])
                finally:
                    report_path.write_bytes(original)
            after_path = pathlib.Path(json.loads(pathlib.Path(search['report_file']).read_bytes())['trials'][-1]['run']['child']['directory'])/'artifact.json'
            after_path.write_bytes(b'{"forged":true}')
            from aetiory.engine import Refusal
            with self.assertRaises(Refusal):
                experiment(observation['report_file'],search['report_file'])


if __name__ == '__main__':
    unittest.main()
