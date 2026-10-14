"""Dependency-free MCP stdio adapter. Runs trusted code, not an OS sandbox."""

import argparse
import hashlib
import json
import math
import pathlib
import re
import secrets
import sys
import sysconfig
from types import SimpleNamespace

PROTOCOL = "2025-11-25"
MAX_MESSAGE = 1024 * 1024


class ProtocolError(Exception):
    def __init__(self, message, code=-32600):
        super().__init__(message)
        self.code = code


def fields(arguments, allowed, required=()):
    if not isinstance(arguments, dict) or set(arguments) - set(allowed):
        raise ValueError("Unknown or invalid tool arguments")
    if not set(required) <= set(arguments):
        raise ValueError("Missing required tool arguments")


def number(value, minimum, maximum, integer=False):
    if type(value) not in ((int,) if integer else (int, float)):
        raise ValueError("Expected a bounded number")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("Number outside supported budget")
    return value


def text(value, limit=4096):
    if not isinstance(value, str) or len(value) > limit or "\0" in value:
        raise ValueError("Expected a bounded string")
    return value


def schema(properties, required):
    return {"type": "object", "properties": properties,
            "required": required, "additionalProperties": False}


STRING = {"type": "string", "maxLength": 4096}
TIMEOUT = {"type": "number", "minimum": .01, "maximum": 300}
TOOLS = [
    {"name": "observe_program", "description":
     "Execute a trusted workspace Python script twice; require plain/instrumented artifact byte parity. Explicit modules are workspace source paths or stdlib:NAME. This executes with your user privileges; not a sandbox.",
     "inputSchema": schema({"script": STRING,
       "modules": {"type": "object", "minProperties": 1, "maxProperties": 16, "additionalProperties": STRING},
       "inputs": {"type": "array", "maxItems": 16, "items": STRING},
       "arguments": {"type": "array", "maxItems": 64, "items": STRING,
                     "description": "@input:0 resolves the first declared input; other tokens are literal strings."},
       "artifact": STRING, "max_events": {"type": "integer", "minimum": 1, "maximum": 500000},
       "timeout": TIMEOUT}, ["script", "modules", "artifact"])},
    {"name": "find_influence", "description":
     "Test upstream return replacements against a server-owned observation. Use a JSON/literal pointer or stable HTML id with optional following sibling. Reports real trials, parent parity, collateral and fresh undo; unresolved is a valid result.",
     "inputSchema": schema({"observation": STRING,
       "selector": schema({"pointer": STRING, "encoding": {"enum": ["json", "literal"]},
           "html_id": STRING, "following_sibling": {"type": "integer", "minimum": 0, "maximum": 16}}, []),
       "max_trials": {"type": "integer", "minimum": 1, "maximum": 512},
       "seconds": {"type": "number", "minimum": .01, "maximum": 600},
       "timeout": TIMEOUT}, ["observation", "selector"])},
    {"name": "inspect_experiment", "description":
     "Read a bounded server-owned observation, search or replay receipt. Handles are local to this server session. Does not execute code.",
     "inputSchema": schema({"handle": STRING}, ["handle"])},
    {"name": "replay_experiment", "description":
     "Repeat a server-created intervention in a fresh paired process, check exact original/alternate artifact bytes and fresh undo. Does not accept foreign plans. Executes trusted code with user privileges.",
     "inputSchema": schema({"intervention": STRING, "timeout": TIMEOUT}, ["intervention"])},
]
for tool in TOOLS:
    tool["annotations"] = {"readOnlyHint": tool["name"] == "inspect_experiment",
                           "destructiveHint": tool["name"] != "inspect_experiment",
                           "idempotentHint": False, "openWorldHint": True}


class Server:
    def __init__(self, workspace, state_dir):
        self.workspace = pathlib.Path(workspace).resolve(strict=True)
        if not self.workspace.is_dir():
            raise ValueError("Workspace must be an existing directory")
        base = pathlib.Path(state_dir).absolute()
        if any(p.is_symlink() for p in [base, *base.parents]):
            raise ValueError("State directory symlinks are unsupported")
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.state = base / ("session-" + secrets.token_hex(16))
        self.state.mkdir(mode=0o700)
        self.handles = {}
        self.initialized = False
        self.ready = False

    def workspace_file(self, value):
        raw = pathlib.Path(text(value))
        path = raw if raw.is_absolute() else self.workspace / raw
        if ".." in path.parts or any(p.is_symlink() for p in [path, *path.parents]):
            raise ValueError("Workspace traversal/symlinks are unsupported")
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self.workspace) or not resolved.is_file():
            raise ValueError("Expected a regular file within the selected workspace")
        if resolved.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Workspace file exceeds 8 MiB")
        return resolved

    def module_file(self, value):
        value = text(value)
        if not value.startswith("stdlib:"):
            path = self.workspace_file(value)
        else:
            name = value[7:]
            if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", name):
                raise ValueError("Invalid standard-library module name")
            base = pathlib.Path(sysconfig.get_path("stdlib")).resolve(strict=True)
            path = base.joinpath(*name.split(".")).with_suffix(".py")
            if not path.is_file():
                path = base.joinpath(*name.split("."), "__init__.py")
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(base):
                raise ValueError("Selected standard-library module has no local Python source")
        if path.suffix != ".py":
            raise ValueError("Select a Python source file")
        return path

    def remember(self, path, kind):
        path = pathlib.Path(path)
        if not path.is_file() or not path.resolve().is_relative_to(self.state):
            raise ValueError("Expected a server-created report")
        token = secrets.token_hex(16)
        self.handles[token] = (path, kind, hashlib.sha256(path.read_bytes()).hexdigest())
        return token

    def handle(self, token, kind=None):
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token) or token not in self.handles:
            raise ValueError("Unknown handle; use a result from this server session")
        path, actual_kind, digest = self.handles[token]
        if kind is not None and kind != actual_kind:
            raise ValueError("Handle has the wrong report kind")
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Server report changed or exceeds bound")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Server report bytes changed")
        return path

    def summary(self, report):
        keys = ("schema", "kind", "status", "baseline_byte_parity", "candidate_count",
                "trial_count", "seconds", "undo_byte_identical", "limitations")
        return {k: report[k] for k in keys if k in report}

    def call(self, name, arguments):
        if name not in {t["name"] for t in TOOLS}:
            raise ValueError("Unknown tool")
        tool = next(t for t in TOOLS if t["name"] == name)
        fields(arguments, tool["inputSchema"]["properties"], tool["inputSchema"]["required"])
        if name == "inspect_experiment":
            report = json.loads(self.handle(arguments["handle"]).read_bytes())
            # Return a manageable receipt; full traces/artifacts stay on disk.
            result = self.summary(report)
            if report["kind"] == "search":
                result.update(selector=report["selector"], selected_baseline=report["selected_baseline"],
                    trials=[{k: t[k] for k in ("event_id", "selected_changed", "artifact_changed", "paired_parent_baseline_equal", "selector_error") if k in t} for t in report["trials"]])
            elif report["kind"] == "replay":
                result["counterfactual"] = report["counterfactual"]
            elif report["kind"] == "intervention":
                result.update(event=report["event"], selector=report["selector"],
                    replacement=report["replacement"], trace_evidence=report["trace_evidence"],
                    observed_effect=report["observed_effect"])
            else:
                result.update(plain=report["plain"], observed=report["observed"])
            result["report_file"] = str(self.handle(arguments["handle"]))
            return result
        # Import only after path/argument validation; no provider API is involved.
        output = self.state / secrets.token_hex(16)
        timeout = number(arguments.get("timeout", 30), .01, 300)
        if name == "observe_program":
            script = self.workspace_file(arguments["script"])
            modules = arguments["modules"]
            if not isinstance(modules, dict) or not 1 <= len(modules) <= 16:
                raise ValueError("Select 1..16 modules")
            declarations = []
            for module, path in modules.items():
                if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", module):
                    raise ValueError("Invalid module name")
                declarations.append(module + "=" + str(self.module_file(path)))
            inputs = arguments.get("inputs", [])
            if not isinstance(inputs, list) or len(inputs) > 16:
                raise ValueError("Declare at most 16 input files")
            inputs = [str(self.workspace_file(x)) for x in inputs]
            tokens = arguments.get("arguments", [])
            if not isinstance(tokens, list) or len(tokens) > 64:
                raise ValueError("Pass at most 64 argument tokens")
            resolved = []
            for value in tokens:
                value = text(value)
                if value.startswith("@input:"):
                    index = value[7:]
                    if not index.isdigit() or int(index) >= len(inputs):
                        raise ValueError("Input argument references an undeclared file")
                    value = inputs[int(index)]
                resolved.append(value)
            artifact = text(arguments["artifact"], 256)
            args = SimpleNamespace(script=str(script), module=declarations, input=inputs, arg=resolved,
                artifact=artifact, out=str(output), max_events=number(arguments.get("max_events", 300000), 1, 500000, True), timeout=timeout)
            from . import engine
            report = engine.observe(args)
            return {**self.summary(report), "observation": self.remember(output / "observation.json", "observation"), "report_file": str(output / "observation.json")}
        if name == "find_influence":
            observation = self.handle(arguments["observation"], "observation")
            selector = arguments["selector"]
            fields(selector, ("pointer", "encoding", "html_id", "following_sibling"))
            if ("pointer" in selector) == ("html_id" in selector):
                raise ValueError("Choose exactly one parsed pointer or stable HTML id")
            if "html_id" in selector and "encoding" in selector or "pointer" in selector and "following_sibling" in selector:
                raise ValueError("Selector fields do not match the selected kind")
            encoding = selector.get("encoding", "json")
            if encoding not in ("json", "literal"):
                raise ValueError("Unsupported parsed encoding")
            args = SimpleNamespace(observation=str(observation), out=str(output),
                pointer=text(selector["pointer"]) if "pointer" in selector else None,
                html_id=text(selector["html_id"], 256) if "html_id" in selector else None,
                html_next_sibling=number(selector.get("following_sibling", 0), 0, 16, True),
                start=None, end=None, encoding=encoding,
                max_trials=number(arguments.get("max_trials", 128), 1, 512, True),
                seconds=number(arguments.get("seconds", 120), .01, 600), timeout=timeout)
            from . import engine
            report = engine.search(args)
            result = {**self.summary(report), "search": self.remember(output / "search.json", "search"), "report_file": str(output / "search.json")}
            if report["status"] == "influence_confirmed":
                result["intervention"] = self.remember(output / "intervention.json", "intervention")
            return result
        plan = self.handle(arguments["intervention"], "intervention")
        from . import engine
        report = engine.replay(SimpleNamespace(plan=str(plan), out=str(output), timeout=timeout))
        return {**self.summary(report), "replay": self.remember(output / "replay.json", "replay"), "report_file": str(output / "replay.json")}

    def dispatch(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
            raise ProtocolError("Expected a JSON-RPC 2.0 method object")
        if "id" in message and (type(message["id"]) not in (str, int) or isinstance(message["id"], str) and len(message["id"]) > 256):
            raise ProtocolError("Request id must be an integer or bounded string")
        params = message.get("params", {})
        if not isinstance(params, dict):
            raise ProtocolError("Expected object parameters", -32602)
        method = message["method"]
        if "id" not in message:
            if method == "notifications/initialized":
                if not self.initialized:
                    raise ProtocolError("Initialize first")
                self.ready = True
            return None
        if method == "initialize":
            if self.initialized:
                raise ProtocolError("Already initialized")
            info = params.get("clientInfo")
            if (not isinstance(params.get("protocolVersion"), str)
                    or not isinstance(params.get("capabilities"), dict)
                    or not isinstance(info, dict)
                    or not all(isinstance(info.get(k), str) and 0 < len(info[k]) <= 256 for k in ("name", "version"))):
                raise ProtocolError("Invalid initialize parameters", -32602)
            self.initialized = True
            return {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                    "serverInfo": {"name": "aetiory", "version": "0.1.0"},
                    "instructions": "Only execute trusted workspace Python. Fork experiments do not sandbox code or roll back external effects. Tool calls are sequential and time-bounded; mid-call MCP cancellation is not supported. Handles are session-local; retained reports remain on disk."}
        if method == "ping":
            return {}
        if not self.ready:
            raise ProtocolError("Initialize and send notifications/initialized first")
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            if not isinstance(params.get("name"), str):
                raise ProtocolError("Expected a tool name", -32602)
            try:
                result = self.call(params["name"], params.get("arguments", {}))
                return {"content": [{"type": "text", "text": json.dumps(result, allow_nan=False)}], "structuredContent": result, "isError": result.get("status") in ("refused", "unresolved")}
            except (ValueError, OSError, KeyError, TypeError, RecursionError) as error:
                return {"content": [{"type": "text", "text": str(error)[:1000]}], "isError": True}
            except Exception as error:
                # Includes core refusals without emitting Python traces on stdout.
                return {"content": [{"type": "text", "text": type(error).__name__ + ": " + str(error)[:1000]}], "isError": True}
        raise ProtocolError("Method not found", -32601)


def serve(server, reader, writer):
    while True:
        line = reader.readline(MAX_MESSAGE + 1)
        if not line:
            return
        identifier = None
        notification = False
        oversized = len(line) > MAX_MESSAGE
        try:
            oversized = oversized or isinstance(line, str) and len(line.encode("utf-8")) > MAX_MESSAGE
            if oversized:
                raise ProtocolError("Message exceeds 1 MiB")
            message = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
            notification = (isinstance(message, dict) and message.get("jsonrpc") == "2.0"
                            and isinstance(message.get("method"), str) and "id" not in message)
            if isinstance(message, dict) and type(message.get("id")) in (int, str):
                identifier = message["id"]
            result = server.dispatch(message)
            if result is None:
                continue
            response = {"jsonrpc": "2.0", "id": identifier, "result": result}
        except (ValueError, UnicodeError, RecursionError) as error:
            response = {"jsonrpc": "2.0", "id": identifier, "error": {"code": -32700, "message": str(error)[:1000]}}
        except ProtocolError as error:
            response = {"jsonrpc": "2.0", "id": identifier, "error": {"code": error.code, "message": str(error)}}
        if not notification and (identifier is not None or "error" in response):
            body = json.dumps(response, allow_nan=False) + "\n"
            if len(body.encode("utf-8")) > MAX_MESSAGE:
                body = json.dumps({"jsonrpc": "2.0", "id": identifier,
                    "error": {"code": -32603, "message": "Response exceeds 1 MiB; inspect the retained report file locally"}}) + "\n"
            writer.write(body)
            writer.flush()
        if oversized:
            return  # Cannot safely resynchronize an oversized frame.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args(argv)
    serve(Server(args.workspace, args.state), sys.stdin.buffer, sys.stdout)


if __name__ == "__main__":
    main()
