"""Regression artifact for retained exporter evidence; real small native journey."""
import copy
import gzip
import html
import io
import json
import pathlib
import tempfile
import unittest
from html.parser import HTMLParser

from aetiory import engine
from aetiory.export import experiment, export_record
from aetiory.mcp import PROTOCOL, Server, serve


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.stylesheets = []
        self.embedded = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts.append(attrs)
            self.current = attrs.get("id")
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.stylesheets.append(attrs)

    def handle_endtag(self, tag):
        if tag == "script":
            self.current = None

    def handle_data(self, data):
        if self.current == "embedded-record":
            self.embedded.append(data)


class ExportBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="aetiory-export-contract-")
        cls.root = pathlib.Path(cls.temporary.name).resolve()
        cls.addClassCleanup(cls.temporary.cleanup)
        (cls.root / "target.py").write_text(
            "def start():\n    return (x for x in range(3))\n"
            "def compute(x):\n    iterator=start()\n    return next(iterator)+x*2\n"
        )
        (cls.root / "input.json").write_text('{"n":5}\n')
        (cls.root / "entry.py").write_text(
            "import json,sys,target\nfrom pathlib import Path\n"
            'x=json.loads(Path(sys.argv[1]).read_bytes())["n"]\n'
            "v=target.compute(x)\n"
            'Path("artifact.json").write_text(json.dumps({"answer":v,"untouched":29}))\n'
        )
        server = Server(cls.root, cls.root / "state")
        sequence = 0

        def rpc(method, params=None, notification=False):
            nonlocal sequence
            sequence += 1
            request = {"jsonrpc": "2.0", "method": method, "params": params or {}}
            if not notification:
                request["id"] = sequence
            output = io.StringIO()
            serve(server, io.BytesIO((json.dumps(request) + "\n").encode()), output)
            if notification:
                assert not output.getvalue()
                return None
            response = json.loads(output.getvalue())
            assert response["id"] == sequence and "error" not in response, response
            return response["result"]

        def tool(name, arguments):
            result = rpc("tools/call", {"name": name, "arguments": arguments})
            assert not result.get("isError"), result
            assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
            return result["structuredContent"]

        rpc("initialize", {"protocolVersion": PROTOCOL, "clientInfo": {"name": "export-contract", "version": "1"}, "capabilities": {}})
        rpc("notifications/initialized", notification=True)
        observation = tool("observe_program", {"script": "entry.py", "modules": {"target": "target.py"}, "inputs": ["input.json"], "arguments": ["@input:0"], "artifact": "artifact.json", "timeout": 3})
        search = tool("find_influence", {"observation": observation["observation"], "selector": {"pointer": "/answer"}, "timeout": 3, "max_trials": 8, "seconds": 20})
        assert search["status"] == "influence_confirmed"
        replay = tool("replay_experiment", {"intervention": search["intervention"], "timeout": 3})
        assert replay["status"] == "reproduced"
        cls.observation_path = pathlib.Path(observation["report_file"])
        cls.search_path = pathlib.Path(search["report_file"])
        cls.replay_path = pathlib.Path(replay["report_file"])
        cls.plan_path = cls.search_path.parent / "intervention.json"

    def exported(self):
        return experiment(self.observation_path, self.search_path, replay_path=self.replay_path)

    def reject_mutation(self, report_path, mutate):
        original = report_path.read_bytes()
        try:
            report = json.loads(original)
            mutate(report)
            report_path.write_bytes(engine.encoded(report))
            with self.assertRaises(engine.Refusal):
                self.exported()
        finally:
            report_path.write_bytes(original)

    def test_native_positive_and_noclobber(self):
        record = self.exported()
        self.assertEqual(record["changes"], [{"path": "/answer", "before": 10, "after": 11, "selected": True}])
        self.assertTrue(all(record["guards"].values()))
        output = self.root / "positive-viewer"
        export_record({"schema": "experiment-view/1", "experiments": [record]}, output)
        before = (output / "index.html").read_bytes()
        with self.assertRaises(FileExistsError):
            export_record({"schema": "experiment-view/1", "experiments": [record]}, output)
        self.assertEqual((output / "index.html").read_bytes(), before)

    def test_failure_flags_and_selectors_refused(self):
        mutations = [
            (self.replay_path, lambda d: d.update(status="refused")),
            (self.replay_path, lambda d: d.update(selected_changed=False)),
            (self.replay_path, lambda d: d["selector"].update(pointer="/untouched")),
            (self.replay_path, lambda d: d["counterfactual"].update(ok=False)),
            (self.replay_path, lambda d: d["counterfactual"]["child"].update(ok=False)),
            (self.replay_path, lambda d: d["fresh_undo"].update(ok=False)),
            (self.replay_path, lambda d: d["fresh_baseline"].update(ok=False)),
            (self.search_path, lambda d: d["fresh_undo"].update(ok=False)),
            (self.search_path, lambda d: d["selector"].update(pointer="/untouched")),
            (self.observation_path, lambda d: d["plain"].update(ok=False)),
            (self.observation_path, lambda d: d["observed"].update(ok=False)),
            (self.observation_path, lambda d: d.update(manifest_hash="0" * 64)),
            (self.replay_path, lambda d: d.update(schema="foreign")),
        ]
        for index, (report_path, mutate) in enumerate(mutations):
            with self.subTest(mutation=index):
                self.reject_mutation(report_path, mutate)

    def test_actual_artifact_source_input_tamper_refused(self):
        observation = json.loads(self.observation_path.read_bytes())
        search = json.loads(self.search_path.read_bytes())
        replay = json.loads(self.replay_path.read_bytes())
        plan = json.loads(self.plan_path.read_bytes())
        trial = next(t for t in search["trials"] if t["event_id"] == plan["event"]["id"] and t["selected_changed"])
        paths = [
            pathlib.Path(trial["run"]["child"]["directory"]) / "artifact.json",
            pathlib.Path(observation["observed"]["directory"]) / "artifact.json",
            pathlib.Path(search["fresh_undo"]["directory"]) / "artifact.json",
            pathlib.Path(replay["counterfactual"]["child"]["directory"]) / "artifact.json",
            self.root / "target.py",
            self.root / "input.json",
        ]
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b" ")
                    with self.assertRaises(engine.Refusal):
                        self.exported()
                finally:
                    path.write_bytes(original)

    def test_matching_trace_plan_values_still_bind_to_hash(self):
        observation = json.loads(self.observation_path.read_bytes())
        trace_path = pathlib.Path(observation["observed"]["directory"]) / "trace.jsonl.gz"
        trace_bytes, plan_bytes = trace_path.read_bytes(), self.plan_path.read_bytes()
        try:
            plan = json.loads(plan_bytes)
            events = [json.loads(line) for line in gzip.decompress(trace_bytes).splitlines()]
            for event in events:
                if event.get("id") == plan["event"]["id"]:
                    event["packed"] = ["int", "12345"]
            trace_path.write_bytes(gzip.compress(b"\n".join(engine.encoded(e) for e in events) + b"\n"))
            plan["trace_evidence"]["packed"] = ["int", "12345"]
            plan.pop("plan_hash")
            plan["plan_hash"] = engine.sha(engine.encoded(plan))
            self.plan_path.write_bytes(engine.encoded(plan))
            with self.assertRaises(engine.Refusal):
                self.exported()
        finally:
            trace_path.write_bytes(trace_bytes)
            self.plan_path.write_bytes(plan_bytes)

    def test_missing_or_changed_retained_trace_refused(self):
        observation = json.loads(self.observation_path.read_bytes())
        trace_path = pathlib.Path(observation["observed"]["directory"]) / "trace.jsonl.gz"
        original = trace_path.read_bytes()
        selected_id = json.loads(self.plan_path.read_bytes())["event"]["id"]
        for mutation in ("remove", "changed-packed"):
            with self.subTest(mutation=mutation):
                try:
                    events = [json.loads(line) for line in gzip.decompress(original).splitlines()]
                    if mutation == "remove":
                        events = [event for event in events if event.get("id") != selected_id]
                    else:
                        for event in events:
                            if event.get("id") == selected_id:
                                event["packed"] = ["int", "12345"]
                    trace_path.write_bytes(gzip.compress(b"\n".join(engine.encoded(e) for e in events) + b"\n"))
                    with self.assertRaises(engine.Refusal):
                        self.exported()
                finally:
                    trace_path.write_bytes(original)

    def test_portable_data_is_inert_and_licenses_embedded(self):
        from aetiory.web._make_portable import ROOT, portable_document
        record = copy.deepcopy(self.exported())
        record["title"] = '</script><template id="inert-marker">&</template>\u2028\u2029'
        payload = {"schema": "experiment-view/1", "experiments": [record]}
        text = portable_document(payload)
        parsed = Document()
        parsed.feed(text)
        self.assertEqual(len(parsed.scripts), 2)
        self.assertFalse(any("src" in script for script in parsed.scripts))
        self.assertFalse(parsed.stylesheets)
        self.assertEqual(json.loads("".join(parsed.embedded)), payload)
        self.assertNotIn('<template id="inert-marker">', text)
        notices = (ROOT / "NOTICES.txt").read_text()
        self.assertIn(html.escape(notices), text)
        for license_name in ("MIT License", "PYTHON SOFTWARE FOUNDATION LICENSE VERSION 2", "Apache License"):
            self.assertIn(license_name, notices)

    def test_unsafe_browser_integer_refuses_before_creating_output(self):
        record = copy.deepcopy(self.exported())
        record["changes"][0]["before"] = 9007199254740993
        output = self.root / "unsafe-integer"
        with self.assertRaises(engine.Refusal):
            export_record({"schema": "experiment-view/1", "experiments": [record]}, output)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
