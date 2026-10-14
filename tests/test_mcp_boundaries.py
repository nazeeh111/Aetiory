import io
import json
import pathlib
import tempfile
import unittest
from aetiory.mcp import Server, ProtocolError, serve


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name).resolve()
        self.server = Server(self.root, self.root / 'state')

    def test_initialization_precedes_tools(self):
        with self.assertRaises(ProtocolError):
            self.server.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
        response = self.server.dispatch({'jsonrpc':'2.0','id':2,'method':'initialize','params':{'protocolVersion':'2025-11-25','clientInfo':{'name':'test','version':'1'},'capabilities':{}}})
        self.assertEqual(response['protocolVersion'], '2025-11-25')
        with self.assertRaises(ProtocolError):
            self.server.dispatch({'jsonrpc':'2.0','id':3,'method':'tools/list'})
        self.server.dispatch({'jsonrpc':'2.0','method':'notifications/initialized'})
        self.assertEqual(len(self.server.dispatch({'jsonrpc':'2.0','id':4,'method':'tools/list'})['tools']), 5)

    def test_workspace_escape_and_symlinks_refused(self):
        outside = self.root.parent / ('outside-' + self.root.name)
        outside.write_text('not a program')
        self.addCleanup(outside.unlink)
        (self.root/'shortcut.py').symlink_to(outside)
        for path in ['../'+outside.name, str(outside), 'shortcut.py']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.server.workspace_file(path)
        (self.root/'input.txt').write_text('data')
        self.assertEqual(self.server.workspace_file('input.txt'), self.root/'input.txt')

    def test_foreign_report_handles_refused(self):
        for token in ['../../file', 'a'*31, 'g'*32, 'a'*32]:
            with self.subTest(token=token), self.assertRaises(ValueError):
                self.server.handle(token, 'observation')

    def test_no_unknown_tool_or_extra_observe_fields(self):
        with self.assertRaises(ValueError):
            self.server.call('run_shell', {})
        with self.assertRaises(ValueError):
            self.server.call('observe_program', {'script':'x.py','modules':{'x':'x.py'},'artifact':'x.json','command':'rm'})

    def test_only_local_source_stdlib_modules(self):
        with self.assertRaises(ValueError):
            self.server.module_file('stdlib:sys')
        with self.assertRaises(ValueError):
            self.server.module_file('stdlib:../path')
        path = self.server.module_file('stdlib:difflib')
        self.assertEqual(path.name, 'difflib.py')

    def test_malformed_messages_and_notifications(self):
        for message in [[], {'id':1,'method':'initialize'}, {'jsonrpc':'2.0','id':True,'method':'initialize'}]:
            with self.subTest(message=message), self.assertRaises(ProtocolError):
                self.server.dispatch(message)
        self.assertIsNone(self.server.dispatch({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':99}}))

    def test_transport_byte_budget_and_notification_silence(self):
        frame = json.dumps({'jsonrpc':'2.0','id':1,'method':'ping','params':{'note':'é'*600000}}, ensure_ascii=False)+'\n'
        output = io.StringIO()
        serve(self.server, io.BytesIO(frame.encode()), output)
        self.assertIn('error', json.loads(output.getvalue()))
        output = io.StringIO()
        serve(self.server, io.StringIO(frame), output)
        self.assertIn('error', json.loads(output.getvalue()))
        output = io.StringIO()
        serve(self.server, io.StringIO(json.dumps({'jsonrpc':'2.0','method':'notifications/cancelled','params':[]})+'\n'), output)
        self.assertEqual(output.getvalue(), '')

    def test_initialize_client_identity_required(self):
        for identity in [{}, {'name':'x'}, {'name':'x','version':1}]:
            with self.subTest(identity=identity), self.assertRaises(ProtocolError):
                self.server.dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':identity}})

    def test_synthetic_retained_receipt_cannot_expand_response_unbounded(self):
        self.server.initialized = self.server.ready = True
        receipt = self.server.state/'synthetic-observation.json'
        receipt.write_text(json.dumps({'schema':'causal-engine/1','kind':'observation','status':'observed','plain':{'note':'x'*600000},'observed':{}}))
        token = self.server.remember(receipt, 'observation')
        output = io.StringIO()
        frame = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'inspect_experiment','arguments':{'handle':token}}}
        serve(self.server, io.StringIO(json.dumps(frame)+'\n'), output)
        self.assertLess(len(output.getvalue().encode()), 1024*1024)
        self.assertEqual(json.loads(output.getvalue())['error']['code'], -32603)

if __name__ == '__main__':
    unittest.main()
