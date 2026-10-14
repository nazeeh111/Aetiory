"""Observe and replay trusted Python scripts. This is an experiment runner, not a sandbox."""
from __future__ import annotations
import argparse
import ast
import gzip
import hashlib
import importlib.abc
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import runpy
import signal
import subprocess
import sys
import time
import types
import threading
from html.parser import HTMLParser

SCHEMA = "causal-engine/1"
START = hashlib.sha256(b"causal-engine/1 prior observed returns").hexdigest()
MAX_VALUE_BYTES = 2 * 1024 * 1024
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
MAX_TRACE_BYTES = 512 * 1024 * 1024
PACK_SELECTED = {}

class Refusal(Exception):
    pass

class Unsupported(Refusal):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def packed(value, active=None, depth=0):
    if depth > 100:
        raise Unsupported("Return value nesting exceeds 100")
    active = set() if active is None else active
    t = type(value)
    if value is None:
        return ["none"]
    if t is bool:
        return ["bool", value]
    if t is int:
        if value.bit_length() > 13000:
            raise Unsupported("Integer exceeds portable bound")
        return ["int", str(value)]
    if t is float:
        if not math.isfinite(value):
            raise Unsupported("Non-finite return")
        return ["float", value.hex()]
    if t is str:
        if len(value) > MAX_VALUE_BYTES:
            raise Unsupported("String exceeds portable bound")
        result = ["str", value]
        if len(encoded(result)) > MAX_VALUE_BYTES:
            raise Unsupported("String exceeds canonical byte bound")
        return result
    named = isinstance(value, tuple) and t is not tuple and type(getattr(t, "_fields", None)) is tuple
    if t not in (tuple, list, dict, set, frozenset) and not named:
        raise Unsupported("Opaque return type: " + t.__module__ + "." + t.__qualname__)
    if id(value) in active:
        raise Unsupported("Cyclic return value")
    active.add(id(value))
    try:
        if t is dict:
            result = ["dict", [[packed(k, active, depth + 1), packed(v, active, depth + 1)] for k, v in value.items()]]
        elif t in (set, frozenset):
            members = [packed(v, active, depth + 1) for v in value]
            members.sort(key=encoded)
            result = [t.__name__, members]
        elif named:
            result = ["namedtuple", t.__module__, t.__qualname__, list(t._fields), [packed(v, active, depth + 1) for v in tuple.__iter__(value)]]
        else:
            result = [t.__name__, [packed(v, active, depth + 1) for v in value]]
    finally:
        active.remove(id(value))
    if len(encoded(result)) > MAX_VALUE_BYTES:
        raise Unsupported("Return value exceeds canonical byte bound")
    return result


def unpacked(p):
    if type(p) is not list or not p:
        raise Refusal("Invalid packed return")
    kind = p[0]
    if kind == "none" and len(p) == 1:
        return None
    if kind == "bool" and len(p) == 2 and type(p[1]) is bool:
        return p[1]
    if kind == "int" and len(p) == 2 and type(p[1]) is str and re.fullmatch(r"-?(0|[1-9][0-9]*)", p[1]) and len(p[1]) <= 4096:
        return int(p[1])
    if kind == "float" and len(p) == 2 and type(p[1]) is str:
        try:
            v = float.fromhex(p[1])
        except ValueError as e:
            raise Refusal("Invalid packed float") from e
        if math.isfinite(v):
            return v
    if kind == "str" and len(p) == 2 and type(p[1]) is str and len(p[1]) <= MAX_VALUE_BYTES:
        return p[1]
    if kind in ("list", "tuple", "set", "frozenset") and len(p) == 2 and type(p[1]) is list:
        values = [unpacked(x) for x in p[1]]
        return {"list": list, "tuple": tuple, "set": set, "frozenset": frozenset}[kind](values)
    if kind == "dict" and len(p) == 2 and type(p[1]) is list:
        try:
            return {unpacked(k): unpacked(v) for k, v in p[1]}
        except (ValueError, TypeError) as e:
            raise Refusal("Invalid packed dictionary") from e
    raise Refusal("Return type is not portable for intervention")


def portable(p):
    try:
        v = unpacked(p)
        return packed(v) == p
    except (Refusal, TypeError, ValueError, RecursionError):
        return False


def preview(value, depth=0):
    t = type(value)
    if value is None or t in (bool, int):
        if t is int and value.bit_length() > 512:
            return {"type": "int", "truncated": True}
        return value
    if t is float:
        return value if math.isfinite(value) else {"type": "float", "nonfinite": True}
    if t is str:
        return {"type": "str", "value": value[:80], "length": len(value), "complete": len(value) <= 30}
    if t in (list, tuple) and depth < 1:
        return {"type": t.__name__, "items": [preview(v, depth + 1) for v in value[:4]], "length": len(value), "complete": len(value) <= 4}
    if t is dict and depth < 1:
        items = list(value.items())[:3]
        return {"type": "dict", "items": [[preview(k, depth + 1), preview(v, depth + 1)] for k, v in items], "length": len(value), "complete": len(value) <= 3}
    return {"type": t.__module__ + "." + t.__qualname__, "opaque": True}


def identity(path):
    original = Path(path)
    if original.is_symlink():
        raise Refusal("Source/input symlinks are not supported")
    p = original.resolve(strict=True)
    if not p.is_file():
        raise Refusal("Expected an ordinary source/input file")
    if p.stat().st_size > 8 * 1024 * 1024:
        raise Refusal("Source/input exceeds 8 MiB")
    with p.open("rb") as f:
        b = f.read(8 * 1024 * 1024 + 1)
    if len(b) > 8 * 1024 * 1024:
        raise Refusal("Source/input exceeds 8 MiB")
    return {"path": str(p), "bytes": len(b), "sha256": sha(b)}


def validate_identity(item):
    if type(item) is not dict or set(item) != {"path", "bytes", "sha256"} or type(item["path"]) is not str or not Path(item["path"]).is_absolute() or len(item["path"]) > 4096 or type(item["bytes"]) is not int or not 0 <= item["bytes"] <= 8 * 1024 * 1024 or type(item["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
        raise Refusal("Invalid pinned file identity")


def validate_manifest(m):
    fields = {"schema", "interpreter", "engine", "script", "modules", "inputs", "arguments", "artifact", "max_events"}
    if type(m) is not dict or set(m) != fields or m["schema"] != SCHEMA:
        raise Refusal("Invalid manifest schema")
    modules = m["modules"]
    if type(modules) is not dict or not 1 <= len(modules) <= 16:
        raise Refusal("Select between one and sixteen source modules")
    for name, item in modules.items():
        if type(name) is not str or len(name) > 256 or not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", name) or name in ("__main__", "sys", "builtins"):
            raise Refusal("Invalid selected module name")
        validate_identity(item)
    if type(m["inputs"]) is not list or type(m["arguments"]) is not list or len(m["arguments"]) > 64 or any(type(x) is not str or len(x) > 4096 for x in m["arguments"]):
        raise Refusal("Invalid entry inputs or argument bound")
    for item in [m["engine"], m["script"], *m["inputs"]]:
        validate_identity(item)
    i = m["interpreter"]
    if type(i) is not dict or set(i) != {"version", "implementation", "cache_tag", "executable"} or any(type(i[k]) is not str or not 1 <= len(i[k]) <= 4096 for k in ("version", "implementation", "cache_tag")):
        raise Refusal("Invalid interpreter identity")
    validate_identity(i["executable"])
    if type(m["max_events"]) is not int or not 1 <= m["max_events"] <= 500000:
        raise Refusal("Invalid return event budget")
    a = m["artifact"]
    if type(a) is not str or not 1 <= len(a) <= 256:
        raise Refusal("Artifact must be a bounded relative path")
    path = Path(a)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] in {"child", "worker-config.json", "receipt.json", "trace.jsonl.gz", "stdout.txt", "stderr.txt"}:
        raise Refusal("Artifact must be a bounded relative path")
    return m


def validate_selector(selector):
    if type(selector) is not dict:
        raise Refusal("Invalid selector schema")
    kind = selector.get("kind")
    if kind == "jsonpath" and set(selector) == {"kind", "pointer", "encoding"}:
        if type(selector["pointer"]) is not str or selector["encoding"] not in ("json", "literal"):
            raise Refusal("Invalid JSON selector")
        pointer_tokens(selector["pointer"])
    elif kind == "html" and set(selector) == {"kind", "id", "following_element_sibling"}:
        if type(selector["id"]) is not str or not 1 <= len(selector["id"]) <= 256 or type(selector["following_element_sibling"]) is not int or not 0 <= selector["following_element_sibling"] <= 16:
            raise Refusal("Invalid HTML selector")
    elif kind == "text" and set(selector) == {"kind", "start", "end"}:
        if type(selector["start"]) is not int or type(selector["end"]) is not int or not 0 <= selector["start"] < selector["end"] <= MAX_ARTIFACT_BYTES:
            raise Refusal("Invalid text selector")
    else:
        raise Refusal("Invalid selector schema")


def validate_patch(patch, manifest):
    if type(patch) is not dict or type(patch.get("event")) is not dict:
        raise Refusal("Invalid intervention event")
    event = patch["event"]
    if set(event) != {"id", "module", "site", "function", "value_hash", "prefix_before", "ancestry_hash"} or type(event["id"]) is not int or not 1 <= event["id"] <= manifest["max_events"] or type(event["module"]) is not str or event["module"] not in manifest["modules"] or type(event["site"]) is not str or not re.fullmatch(r"[1-9][0-9]*:[0-9]+", event["site"]) or type(event["function"]) is not str or not 1 <= len(event["function"]) <= 4096:
        raise Refusal("Invalid intervention event fields")
    for key in ("value_hash", "prefix_before", "ancestry_hash"):
        if type(event[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", event[key]):
            raise Refusal("Invalid intervention event hash: " + key)
    evidence = patch.get("trace_evidence")
    if type(evidence) is not dict or set(evidence) != {"packed", "ancestry", "prefix_scope", "opaque_prior_count"} or evidence["prefix_scope"] != "portable-values-and-opaque-markers" or type(evidence["opaque_prior_count"]) is not int or not 0 <= evidence["opaque_prior_count"] < event["id"]:
        raise Refusal("Invalid trace evidence schema or scope")
    value = evidence["packed"]
    if not portable(value) or len(encoded(value)) > 2048 or sha(encoded(value)) != event["value_hash"]:
        raise Refusal("Trace evidence packed value_hash mismatch or opaque target")
    ancestry = evidence["ancestry"]
    if type(ancestry) is not list or not 1 <= len(ancestry) <= 16:
        raise Refusal("Invalid trace evidence ancestry")
    for frame in ancestry:
        if type(frame) is not dict or set(frame) != {"module", "function", "first_line", "line"} or type(frame["module"]) is not str or frame["module"] not in manifest["modules"] or type(frame["function"]) is not str or not 1 <= len(frame["function"]) <= 4096 or any(type(frame[k]) is not int or frame[k] < 1 for k in ("first_line", "line")):
            raise Refusal("Invalid trace evidence ancestry frame")
    if sha(encoded(ancestry)) != event["ancestry_hash"]:
        raise Refusal("Trace evidence ancestry_hash mismatch")
    replacement = patch.get("replacement")
    if not portable(replacement) or len(encoded(replacement)) > 2048 or replacement[0] != value[0]:
        raise Refusal("Replacement return type differs or is nonportable")


def verify_identities(manifest):
    validate_manifest(manifest)
    if manifest.get("interpreter") != interpreter_identity():
        raise Refusal("Interpreter version or executable changed")
    if manifest.get("engine") != identity(__file__):
        raise Refusal("Observation/replay engine bytes changed")
    for item in [manifest["script"], *manifest["modules"].values(), *manifest["inputs"]]:
        if identity(item["path"]) != item:
            raise Refusal("Source or declared input changed: " + item["path"])


def interpreter_identity():
    return {"version": sys.version, "implementation": sys.implementation.name, "cache_tag": sys.implementation.cache_tag, "executable": identity(Path(sys.executable).resolve())}


class WrapReturns(ast.NodeTransformer):
    def __init__(self, module, hook):
        self.module, self.hook, self.sites = module, hook, {}

    def visit_Return(self, node):
        self.generic_visit(node)
        if node.value is not None:
            site = str(node.lineno) + ":" + str(node.col_offset)
            self.sites[site] = {"line": node.lineno, "column": node.col_offset, "end_line": node.end_lineno, "end_column": node.end_col_offset}
            node.value = ast.copy_location(ast.Call(func=ast.Name(id=self.hook, ctx=ast.Load()), args=[ast.Constant(self.module), ast.Constant(site), node.value], keywords=[]), node.value)
        return node


class SourceLoader(importlib.abc.Loader):
    def __init__(self, fullname, item, capture, instrument):
        self.fullname, self.item, self.capture, self.instrument = fullname, item, capture, instrument

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        if identity(self.item["path"]) != self.item:
            raise Refusal("Selected module changed before loading")
        source = Path(self.item["path"]).read_bytes()
        tree = ast.parse(source, filename=self.item["path"])
        hook = "_causal_return_" + self.item["sha256"][:16]
        if any(isinstance(n, ast.Name) and n.id == hook for n in ast.walk(tree)):
            raise Refusal("Instrumentation name collision")
        if self.instrument:
            tree = WrapReturns(self.fullname, hook).visit(tree)
            ast.fix_missing_locations(tree)
            module.__dict__[hook] = self.capture
        module.__file__ = self.item["path"]
        module.__cached__ = None
        exec(compile(tree, self.item["path"], "exec"), module.__dict__)


class SelectedFinder(importlib.abc.MetaPathFinder):
    def __init__(self, manifest, capture, instrument):
        self.manifest, self.capture, self.instrument = manifest, capture, instrument

    def find_spec(self, fullname, path=None, target=None):
        item = self.manifest["modules"].get(fullname)
        if item is None:
            return None
        package = Path(item["path"]).name == "__init__.py"
        return importlib.util.spec_from_file_location(fullname, item["path"], loader=SourceLoader(fullname, item, self.capture, self.instrument), submodule_search_locations=[str(Path(item["path"]).parent)] if package else None)


def argument_ancestry(frame, selected_paths):
    result = []
    remaining = 512
    while frame is not None and len(result) < 8:
        code = frame.f_code
        if code.co_filename in selected_paths:
            names = code.co_varnames[:code.co_argcount + code.co_kwonlyargcount]
            args = {}
            for n in names[:16]:
                if n not in frame.f_locals:
                    continue
                item = preview(frame.f_locals[n])
                size = len(encoded(item)) + len(n)
                if size <= remaining:
                    args[n] = item; remaining -= size
                else:
                    args[n] = {"type": type(frame.f_locals[n]).__name__, "snapshot_budget_omitted": True}
            result.append({"module": selected_paths[code.co_filename], "function": code.co_qualname, "first_line": code.co_firstlineno, "line": frame.f_lineno, "arguments": args})
        frame = frame.f_back
    return result


def nearby_containers(frame, selected_paths):
    hints = []
    for _ in range(12):
        if frame is None:
            break
        if frame.f_code.co_filename in selected_paths:
            code = frame.f_code
            for name in code.co_varnames[:code.co_argcount + code.co_kwonlyargcount]:
                v = frame.f_locals.get(name)
                if type(v) in (list, tuple) and 1 <= len(v) <= 8 and all(type(x) in (str, int, float, bool, type(None)) for x in v):
                    try:
                        q = packed(v)
                        if len(encoded(q)) <= 2048:
                            h = sha(encoded(q))
                            if h not in hints:
                                hints.append(h)
                    except Refusal:
                        pass
        if len(hints) >= 4:
            break
        frame = frame.f_back
    return hints


def path_ancestry(frame, selected_paths):
    result = []
    while frame is not None and len(result) < 16:
        c = frame.f_code
        if c.co_filename in selected_paths:
            result.append({"module": selected_paths[c.co_filename], "function": c.co_qualname, "first_line": c.co_firstlineno, "line": frame.f_lineno})
        frame = frame.f_back
    return result


def nonstandard_fds():
    result = []
    for name in os.listdir("/dev/fd"):
        if name.isdigit() and int(name) >= 3:
            try:
                os.fstat(int(name)); result.append(int(name))
            except OSError:
                pass
    return result


def bounded_bytes(path, limit):
    p = Path(path)
    if p.stat().st_size > limit:
        raise Refusal("File exceeds byte limit")
    with p.open("rb") as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise Refusal("File grew beyond byte limit")
    return data


def worker(config_path):
    config = json.loads(bounded_bytes(config_path, 16 * 1024 * 1024))
    m = config["manifest"]
    base_run = Path(config["run_dir"]).resolve()
    active_run = base_run
    verify_identities(m)
    selected = {v["path"]: k for k, v in m["modules"].items()}
    state = {"count": 0, "prefix": START, "applied": False, "trace_bytes": 0, "branch": "baseline", "child_pid": None, "child_wait_status": None, "fork_permission": False, "opaque_count": 0, "opaque_examples": [], "split": None}
    patch = config.get("patch")
    paired = config["mode"] == "paired"
    if paired:
        validate_patch(patch, m)
    sys.dont_write_bytecode = True
    trace = gzip.open(base_run / "trace.jsonl.gz", "wb", compresslevel=1) if config.get("trace") else None
    ancestry_seen = set()
    observed = config["mode"] in ("observed", "paired")

    def capture(module, site, value):
        nonlocal active_run
        state["count"] += 1
        if state["count"] > m["max_events"]:
            raise Refusal("Observed return-event budget exhausted")
        if state["split"] is not None:
            return value
        frame = sys._getframe(1)
        ancestry = path_ancestry(frame, selected)
        path_hash = sha(encoded(ancestry))
        opaque = None
        try:
            q = packed(value)
            value_hash = sha(encoded(q))
            retained = len(encoded(q)) <= 2048
        except (Unsupported, RecursionError):
            q, retained = None, False
            opaque = {"type": type(value).__module__ + "." + type(value).__qualname__}
            if type(value) is types.GeneratorType:
                opaque["generator_function"] = value.gi_code.co_qualname
            value_hash = sha(encoded({"opaque_marker": opaque}))
            state["opaque_count"] += 1
            if len(state["opaque_examples"]) < 32:
                state["opaque_examples"].append({"id": state["count"], "module": module, "site": site, **opaque})
        event = {"id": state["count"], "module": module, "site": site, "function": frame.f_code.co_qualname,
                 "value_hash": value_hash, "packed": q if retained else None, "portable": retained and portable(q),
                 "prefix_before": state["prefix"], "prefix_scope": "portable-values-and-opaque-markers", "opaque_marker": opaque,
                 "opaque_prior_count": state["opaque_count"] - (1 if opaque else 0), "ancestry_hash": path_hash}
        if event["portable"] and replacement_values(q):
            event["container_hints"] = nearby_containers(frame, selected)
        if paired and state["count"] == patch["event"]["id"]:
            expected = patch["event"]
            for key in ("id", "module", "site", "function", "value_hash", "prefix_before", "ancestry_hash"):
                if event[key] != expected[key]:
                    raise Refusal("Intervention replay guard failed: " + key)
            if event["opaque_prior_count"] != patch["trace_evidence"]["opaque_prior_count"]:
                raise Refusal("Intervention replay guard failed: opaque_prior_count")
            if ancestry != patch["trace_evidence"]["ancestry"] or q != patch["trace_evidence"]["packed"]:
                raise Refusal("Intervention trace evidence differs at actual split")
            if opaque is not None or not event["portable"]:
                raise Refusal("Intervention target is opaque or not retained as a portable value")
            replacement = unpacked(patch["replacement"])
            if packed(replacement)[0] != q[0] or not portable(patch["replacement"]):
                raise Refusal("Replacement return type differs or is nonportable")
            if threading.active_count() != 1 or nonstandard_fds():
                raise Refusal("Paired split requires one Python thread and no nonstandard open streams")
            verify_identities(m)
            split = {"event": {k: event[k] for k in ("id", "module", "site", "function", "value_hash", "prefix_before", "ancestry_hash")},
                     "path_ancestry": ancestry, "actual_arguments": argument_ancestry(frame, selected), "opaque_prior_count": event["opaque_prior_count"], "opaque_prior_examples": state["opaque_examples"],
                     "guards": "source/input/interpreter/engine/event/value/path/portable-prefix matched", "thread_count": threading.active_count(), "nonstandard_fds": []}
            state["split"] = split
            sys.stdout.flush(); sys.stderr.flush()
            state["fork_permission"] = True
            try:
                pid = os.fork()
            finally:
                state["fork_permission"] = False
            if pid == 0:
                state["branch"] = "counterfactual"
                state["applied"] = True
                active_run = base_run / "child"
                os.chdir(active_run)
                for fd, name in ((1, "stdout.txt"), (2, "stderr.txt")):
                    child_fd = os.open(active_run / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    os.dup2(child_fd, fd); os.close(child_fd)
                return replacement
            state["child_pid"] = pid
            return value
        digest_item = {k: event[k] for k in ("id", "module", "site", "function", "value_hash", "ancestry_hash")}
        state["prefix"] = sha(bytes.fromhex(state["prefix"]) + encoded(digest_item))
        if trace:
            if path_hash not in ancestry_seen:
                row = encoded({"record": "ancestry", "hash": path_hash, "frames": ancestry}) + b"\n"
                state["trace_bytes"] += len(row); trace.write(row); ancestry_seen.add(path_hash)
            event["ancestry_record_hash"] = path_hash
            row = encoded(event) + b"\n"; state["trace_bytes"] += len(row)
            if state["trace_bytes"] > MAX_TRACE_BYTES:
                raise Refusal("Portable trace byte budget exhausted")
            trace.write(row)
        return value

    permitted_reads = {x["path"] for x in [m["script"], m["engine"], m["interpreter"]["executable"], *m["modules"].values(), *m["inputs"]]}
    standard_library = Path(os.__file__).resolve().parent
    def inside(path, directory):
        return path == directory or directory in path.parents
    def audit(event, args):
        if event in ("socket.connect", "socket.connect_ex", "socket.bind", "socket.getaddrinfo", "socket.sendto", "urllib.Request", "http.client.connect", "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "ctypes.dlopen"):
            raise Refusal("Network or external child-process activity is unavailable")
        if event == "os.fork" and not state["fork_permission"]:
            raise Refusal("Only the engine's controlled paired split is permitted")
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(args[0])).resolve()
            flags = args[2] if len(args) > 2 and type(args[2]) is int else 0
            writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC))
            if writing:
                if not inside(path, active_run):
                    raise Refusal("File writes must stay inside the current owned branch directory")
                if paired and state["split"] is None:
                    raise Refusal("Entry wrote before the paired split; pure computation contract required")
            elif str(path) not in permitted_reads and not inside(path, standard_library) and not inside(path, active_run):
                raise Refusal("File read is not a declared input/source or standard-library resource")
        if event in ("os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.link", "os.symlink", "os.chmod", "os.utime", "os.truncate"):
            if paired and state["split"] is None:
                raise Refusal("Filesystem mutation before paired split is unsupported")
            count = 2 if event in ("os.rename", "os.link", "os.symlink") else 1
            for arg in args[:count]:
                if isinstance(arg, (str, bytes, os.PathLike)) and not inside(Path(os.fsdecode(arg)).resolve(), active_run):
                    raise Refusal("Filesystem mutation outside owned branch is unsupported")
    sys.addaudithook(audit)
    sys.meta_path.insert(0, SelectedFinder(m, capture, observed))
    for name in m["modules"]:
        if name in sys.modules:
            del sys.modules[name]

    def cancelled(signum, frame):
        child = state["child_pid"]
        if child:
            try:
                os.kill(child, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                _, status = os.waitpid(child, 0); state["child_wait_status"] = status
            except ChildProcessError:
                pass
        raise Refusal("Owned paired worker cancelled")
    signal.signal(signal.SIGTERM, cancelled)
    original_argv = sys.argv
    sys.argv = [m["script"]["path"], *m["arguments"]]
    error, artifact_info = None, None
    try:
        os.chdir(active_run)
        try:
            runpy.run_path(m["script"]["path"], run_name="__main__")
        except SystemExit as e:
            if e.code not in (None, 0):
                raise
        if paired and state["split"] is None:
            raise Refusal("Intervention target event was not encountered")
        verify_identities(m)
        artifact = active_run / m["artifact"]
        if artifact.is_symlink() or not artifact.is_file() or not inside(artifact.resolve(), active_run):
            raise Refusal("Entry did not produce an ordinary declared artifact")
        artifact_data = bounded_bytes(artifact, MAX_ARTIFACT_BYTES)
        artifact_info = {"bytes": len(artifact_data), "sha256": sha(artifact_data)}
    except BaseException as e:
        error = {"type": type(e).__name__, "message": str(e)[:1000]}
    finally:
        sys.argv = original_argv
        if trace:
            trace.close()
    # Protocol receipt writes are owned engine effects after entry completion, even for refused pre-split entries.
    state["split"] = state["split"] or ({"refused_before_split": True} if paired else None)
    receipt = {"schema": SCHEMA, "backend": "paired-os-fork" if paired else "return-observation", "ok": error is None, "error": error, "mode": config["mode"], "branch": state["branch"],
               "artifact": artifact_info, "events": state["count"], "prefix": state["prefix"], "prefix_scope": "portable-values-and-opaque-markers", "opaque_returns": state["opaque_count"],
               "opaque_examples": state["opaque_examples"], "applied": state["applied"], "split": state["split"], "trace_uncompressed_bytes": state["trace_bytes"], "directory": str(active_run)}
    if state["branch"] == "counterfactual":
        (active_run / "receipt.json").write_bytes(encoded(receipt) + b"\n")
        sys.stdout.flush(); sys.stderr.flush(); os._exit(0 if receipt["ok"] else 3)
    if state["child_pid"] is not None:
        if state["child_wait_status"] is None:
            try:
                _, state["child_wait_status"] = os.waitpid(state["child_pid"], 0)
            except ChildProcessError:
                state["child_wait_status"] = -1
            except Refusal as e:
                receipt["ok"] = False
                receipt["error"] = {"type": "Refusal", "message": str(e)}
        receipt["child_pid"] = state["child_pid"]
        receipt["child_wait_status"] = state["child_wait_status"]
        receipt["child_reaped"] = True
        child_file = base_run / "child" / "receipt.json"
        if child_file.is_file():
            try:
                receipt["child"] = json.loads(bounded_bytes(child_file, 1024 * 1024))
            except (Refusal, OSError, ValueError) as e:
                receipt["child"] = {"ok": False, "error": {"type": "InvalidReceipt", "message": str(e)[:500]}}
        else:
            receipt["child"] = {"ok": False, "error": {"type": "MissingReceipt", "message": "Counterfactual child did not finish"}}
        if not receipt["child"].get("ok") or state["child_wait_status"] != 0:
            receipt["ok"] = False
    (base_run / "receipt.json").write_bytes(encoded(receipt) + b"\n")
    return 0 if receipt["ok"] else 3


def create_dir(path):
    p = Path(path).absolute()
    p.mkdir(parents=True, exist_ok=False)
    return p.resolve()


def stop_owned_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)


def run_once(manifest, root, name, mode, timeout, trace=False, patch=None):
    verify_identities(manifest)
    if mode == "paired":
        validate_patch(patch, manifest)
    directory = create_dir(root / name)
    if mode == "paired":
        create_dir(directory / "child")
    config = {"manifest": manifest, "run_dir": str(directory), "mode": mode, "trace": trace, "patch": patch}
    config_path = directory / "worker-config.json"
    config_path.write_bytes(encoded(config) + b"\n")
    started = time.monotonic()
    with (directory / "stdout.txt").open("wb") as stdout, (directory / "stderr.txt").open("wb") as stderr:
        process = subprocess.Popen([sys.executable, "-I", "-S", str(Path(__file__).resolve()), "_worker", str(config_path)], cwd=directory, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}, start_new_session=True, close_fds=True)
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_owned_group(process)
        except BaseException:
            stop_owned_group(process)
            raise
    verify_identities(manifest)
    if timed_out:
        result = {"schema": SCHEMA, "ok": False, "error": {"type": "Timeout", "message": "Owned process group terminated"}, "exit": process.returncode, "seconds": time.monotonic() - started}
        if (directory / "receipt.json").is_file():
            try:
                result["worker_cleanup"] = json.loads(bounded_bytes(directory / "receipt.json", 2 * 1024 * 1024))
            except (Refusal, OSError, ValueError):
                result["worker_cleanup"] = {"ok": False, "error": "Incomplete cleanup receipt"}
    elif (directory / "receipt.json").is_file():
        result = json.loads((directory / "receipt.json").read_bytes())
        result.update(exit=process.returncode, seconds=time.monotonic() - started)
        if process.returncode != 0:
            result["ok"] = False
    else:
        result = {"schema": SCHEMA, "ok": False, "error": {"type": "WorkerFailure", "message": "Worker exited without receipt"}, "exit": process.returncode, "seconds": time.monotonic() - started}
    result["directory"] = str(directory)
    return result


def manifest_from_args(args):
    modules = {}
    for declaration in args.module:
        if "=" not in declaration:
            raise Refusal("Module declaration must be name=source.py")
        name, path = declaration.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", name) or name in modules:
            raise Refusal("Invalid or duplicate selected module")
        if name in ("__main__", "sys", "builtins"):
            raise Refusal("Cannot replace a core runtime module")
        modules[name] = identity(path)
    if not modules or len(modules) > 16:
        raise Refusal("Select between one and sixteen source modules")
    artifact = Path(args.artifact)
    if artifact.is_absolute() or ".." in artifact.parts or not artifact.parts or artifact.parts[0] in {"child", "worker-config.json", "receipt.json", "trace.jsonl.gz", "stdout.txt", "stderr.txt"} or len(str(artifact)) > 256:
        raise Refusal("Artifact must be a bounded relative path")
    if len(args.arg) > 64 or any(len(x) > 4096 for x in args.arg):
        raise Refusal("Entry argument bound exceeded")
    if not 1 <= args.max_events <= 500000:
        raise Refusal("Invalid return event budget")
    m = {"schema": SCHEMA, "interpreter": interpreter_identity(), "engine": identity(__file__), "script": identity(args.script), "modules": modules, "inputs": [identity(x) for x in args.input], "arguments": args.arg, "artifact": str(artifact), "max_events": args.max_events}
    return validate_manifest(m)


def validate_api(args, search_mode=False):
    if type(args.timeout) not in (int, float) or not math.isfinite(args.timeout) or not .01 <= args.timeout <= 300:
        raise Refusal("Whole-process timeout must be finite and .01..300 seconds")
    if search_mode:
        if type(args.max_trials) is not int or not 1 <= args.max_trials <= 512 or type(args.seconds) not in (int, float) or not math.isfinite(args.seconds) or not .01 <= args.seconds <= 600:
            raise Refusal("Invalid bounded search configuration")
        if type(args.html_next_sibling) is not int or not 0 <= args.html_next_sibling <= 16 or args.start is not None and args.end is None:
            raise Refusal("Invalid selector configuration")


def observe(args):
    validate_api(args)
    root = create_dir(args.out)
    m = manifest_from_args(args)
    (root / "manifest.json").write_bytes(encoded(m) + b"\n")
    plain = run_once(m, root, "plain", "plain", args.timeout)
    observed = run_once(m, root, "observed", "observed", args.timeout, trace=True) if plain["ok"] else None
    parity = bool(observed and observed["ok"] and plain["artifact"] == observed["artifact"])
    report = {"schema": SCHEMA, "kind": "observation", "manifest_hash": sha(encoded(m)), "manifest": m, "plain": plain, "observed": observed, "baseline_byte_parity": parity, "status": "observed" if parity else "refused", "limitations": ["Trusted entry execution, not a sandbox or arbitrary uploaded-code service.", "Returns and real call/argument ancestry are observations, not complete dynamic dataflow.", "Observed prefix hashes complete portable return values and explicit opaque type/location markers; it is not a serialization of opaque heap state. Paired runs copy the actual live state by os.fork and must match the parent baseline.", "Actual argument previews are captured only at the chosen split; compact container hashes are candidate-ranking hints, not causality or replay guards.", "Canonical returns above 2 KiB are completely hashed for the prefix but not retained as intervention candidates; output selection never authorizes completed-artifact replacement."]}
    (root / "observation.json").write_bytes(encoded(report) + b"\n")
    return report


def pointer_tokens(pointer):
    if pointer == "":
        return []
    if not pointer.startswith("/") or len(pointer) > 1024:
        raise Refusal("JSON path must be an RFC6901 pointer")
    result = []
    for token in pointer[1:].split("/"):
        if re.search(r"~(?![01])", token):
            raise Refusal("Invalid JSON pointer escape")
        result.append(token.replace("~1", "/").replace("~0", "~"))
    return result


def decode_artifact(data, encoding):
    if len(data) > MAX_ARTIFACT_BYTES:
        raise Refusal("Artifact exceeds parser budget")
    try:
        text = data.decode("utf-8", errors="strict")
        if encoding == "json":
            return json.loads(text, parse_constant=lambda x: (_ for _ in ()).throw(Refusal("Non-finite JSON artifact")))
        if encoding == "literal":
            tree = ast.parse(text, mode="eval")
            if sum(1 for _ in ast.walk(tree)) > 400000:
                raise Refusal("Literal artifact AST budget exceeded")
            return ast.literal_eval(tree)
    except (ValueError, SyntaxError, UnicodeError, RecursionError) as e:
        raise Refusal("Artifact parser refused: " + type(e).__name__) from e
    raise Refusal("Unsupported artifact encoding")


class ElementTree(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "#document", "attrs": [], "content": []}
        self.stack = [self.root]
        self.ids = {}
        self.elements = 0
    def handle_starttag(self, tag, attrs):
        self.elements += 1
        if self.elements > 100000 or len(self.stack) > 128:
            raise Refusal("HTML structural parser budget exceeded")
        node = {"tag": tag, "attrs": sorted(attrs), "content": [], "parent": self.stack[-1]}
        self.stack[-1]["content"].append(node)
        ids = [v for k, v in attrs if k == "id"]
        for value in ids:
            self.ids.setdefault(value, []).append(node)
        if len(ids) > 1:
            raise Refusal("Duplicate id attributes on HTML element")
        if tag not in self.VOID:
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)
    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if len(self.stack) <= 1 or self.stack[-1]["tag"] != tag:
            raise Refusal("Malformed HTML nesting is unsupported")
        self.stack.pop()
    def handle_data(self, data):
        self.stack[-1]["content"].append(data)
    def snapshot(self, node):
        return {"tag": node["tag"], "attrs": node["attrs"], "content": [self.snapshot(x) if type(x) is dict else x for x in node["content"]]}
    def selected(self, element_id, sibling):
        matches = self.ids.get(element_id, [])
        if len(matches) != 1:
            raise Refusal("HTML id must resolve to exactly one observed element")
        node = matches[0]
        if sibling:
            parent = node["parent"]
            children = [x for x in parent["content"] if type(x) is dict]
            index = next(i for i, x in enumerate(children) if x is node) + sibling
            if not 0 <= index < len(children):
                raise Refusal("Selected HTML sibling is missing")
            node = children[index]
        return self.snapshot(node)


def html_tree(data):
    if len(data) > MAX_ARTIFACT_BYTES:
        raise Refusal("HTML exceeds parser budget")
    p = ElementTree()
    p.feed(data.decode("utf-8", errors="strict")); p.close()
    if len(p.stack) != 1:
        raise Refusal("Unclosed HTML elements are unsupported")
    return p


def html_collateral(before, after):
    a, b = html_tree(before), html_tree(after)
    differences = []
    for key in sorted(set(a.ids) | set(b.ids)):
        for offset in (0, 1):
            try:
                x = a.selected(key, offset)
            except Refusal:
                x = None
            try:
                y = b.selected(key, offset)
            except Refusal:
                y = None
            if x != y:
                differences.append({"id": key, "following_element_sibling": offset, "before": preview(x), "after": preview(y)})
    return {"anchored_subtrees_changed": differences[:10000], "truncated": len(differences) > 10000}


def selected_value(data, selector):
    validate_selector(selector)
    if selector["kind"] == "html":
        return html_tree(data).selected(selector["id"], selector["following_element_sibling"]), None
    if selector["kind"] == "text":
        text = data.decode("utf-8", errors="strict")
        start, end = selector["start"], selector["end"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise Refusal("Invalid selected UTF-8 text character span")
        return text[start:end], None
    root = decode_artifact(data, selector["encoding"])
    value, parent = root, None
    for token in pointer_tokens(selector["pointer"]):
        parent = value
        if type(value) is list:
            if not re.fullmatch(r"0|[1-9][0-9]*", token) or int(token) >= len(value):
                raise Refusal("JSON path array index missing")
            value = value[int(token)]
        elif type(value) is dict and token in value:
            value = value[token]
        else:
            raise Refusal("JSON path does not resolve exactly")
    return value, parent


def changes(a, b, path="", limit=10000):
    result = []
    stack = [(a, b, path)]
    while stack and len(result) < limit:
        x, y, p = stack.pop()
        if type(x) != type(y):
            result.append({"path": p, "before": preview(x), "after": preview(y)})
        elif type(x) is dict and set(x) == set(y):
            for k in reversed(list(x)):
                stack.append((x[k], y[k], p + "/" + str(k).replace("~", "~0").replace("/", "~1")))
        elif type(x) is list and len(x) == len(y):
            for i in range(len(x) - 1, -1, -1):
                stack.append((x[i], y[i], p + "/" + str(i)))
        elif x != y:
            result.append({"path": p, "before": preview(x), "after": preview(y)})
    return {"differences": result, "truncated": bool(stack)}


def primitive_members(p, limit=16):
    if not p:
        return []
    if p[0] in ("none", "bool", "int", "float", "str"):
        return [unpacked(p)]
    if p[0] in ("tuple", "list") and len(p[1]) <= limit:
        result = []
        for q in p[1]:
            result.extend(primitive_members(q, limit))
        return result[:limit]
    return []


def replacement_values(p):
    v = unpacked(p)
    t = type(v)
    if t is bool:
        return [packed(not v)]
    if t is int:
        return [packed(v + 1), packed(0)] if v != -1 else [packed(0)]
    if t is float:
        return [packed(0.0 if v != 0.0 else 1.0)]
    if t is str and re.fullmatch(r"-?(0|[1-9][0-9]*)", v) and len(v) < 100:
        return [packed(str(int(v) + 1))]
    if t is tuple and 1 <= len(v) <= 16:
        for i, x in enumerate(v):
            if type(x) is str and re.fullmatch(r"-?(0|[1-9][0-9]*)", x) and len(x) < 100:
                copy = list(v); copy[i] = str(int(x) + 1)
                return [packed(tuple(copy))]
    return []


def load_events(path):
    total = 0
    ancestry = {}
    with gzip.open(path, "rb") as f:
        while True:
            line = f.readline(4 * MAX_VALUE_BYTES + 1)
            if not line:
                break
            total += len(line)
            if total > MAX_TRACE_BYTES or len(line) > 4 * MAX_VALUE_BYTES:
                raise Refusal("Trace read budget exceeded")
            event = json.loads(line)
            if event.get("record") == "ancestry":
                if sha(encoded(event["frames"])) != event["hash"]:
                    raise Refusal("Trace navigation hash mismatch")
                ancestry[event["hash"]] = event["frames"]
                continue
            key = event.get("ancestry_record_hash")
            if key not in ancestry:
                raise Refusal("Trace ancestry record missing")
            event["ancestry"] = ancestry[key]
            yield event


def candidate_priority(event, selected, parent, text_mode):
    p = event["packed"]
    members = primitive_members(p)
    if not text_mode:
        matches = any(type(x) is type(selected) and x == selected or type(x) is str and x == str(selected) for x in members)
        if not matches:
            return None
        try:
            parent_hash = sha(encoded(packed(parent))) if parent is not None else None
        except Refusal:
            parent_hash = None
        near_parent = parent_hash in event.get("container_hints", [])
        return (0 if near_parent else 1, len(encoded(p)), event["id"])
    if p[0] not in ("float", "bool", "int"):
        return None
    # Earlier scalar decisions are tested first. This is a search heuristic, not inferred causality.
    return (0 if p[0] == "float" else 1 if p[0] == "bool" else 2, event["id"])


def search(args):
    validate_api(args, search_mode=True)
    observation_path = Path(args.observation).resolve(strict=True)
    observation = json.loads(bounded_bytes(observation_path, 16 * 1024 * 1024))
    if observation.get("schema") != SCHEMA or not observation.get("baseline_byte_parity"):
        raise Refusal("A fresh plain/observed byte-identical baseline is required")
    m = observation["manifest"]
    if sha(encoded(m)) != observation["manifest_hash"]:
        raise Refusal("Observation manifest hash mismatch")
    verify_identities(m)
    artifact_path = Path(observation["observed"]["directory"]) / m["artifact"]
    original = bounded_bytes(artifact_path, MAX_ARTIFACT_BYTES)
    if sha(original) != observation["observed"]["artifact"]["sha256"]:
        raise Refusal("Observed artifact changed")
    if sum(x is not None for x in (args.html_id, args.pointer, args.start)) != 1:
        raise Refusal("Exactly one output selector is required")
    if args.html_id is not None:
        selector = {"kind": "html", "id": args.html_id, "following_element_sibling": args.html_next_sibling}
    elif args.pointer is not None:
        selector = {"kind": "jsonpath", "pointer": args.pointer, "encoding": args.encoding}
    else:
        selector = {"kind": "text", "start": args.start, "end": args.end}
    target, parent = selected_value(original, selector)
    root = create_dir(args.out)
    candidates = []
    for event in load_events(Path(observation["observed"]["directory"]) / "trace.jsonl.gz"):
        if not event["portable"]:
            continue
        replacements = replacement_values(event["packed"])
        if not replacements:
            continue
        priority = candidate_priority(event, target, parent, selector["kind"] in ("text", "html"))
        if priority is not None:
            candidates.append((priority, event, replacements))
    candidates.sort(key=lambda x: x[0])
    start = time.monotonic()
    trials, discovered = [], None
    for _, event, replacements in candidates:
        for replacement in replacements:
            if len(trials) >= args.max_trials or time.monotonic() - start >= args.seconds:
                break
            guard = {k: event[k] for k in ("id", "module", "site", "function", "value_hash", "prefix_before", "ancestry_hash")}
            plan = {"schema": SCHEMA, "kind": "intervention", "backend": "paired-os-fork", "prefix_scope": "portable-values-and-opaque-markers", "manifest": m, "manifest_hash": sha(encoded(m)), "event": guard, "replacement": replacement, "selector": selector, "baseline_artifact": observation["observed"]["artifact"], "trace_evidence": {"packed": event["packed"], "ancestry": event["ancestry"], "prefix_scope": event["prefix_scope"], "opaque_prior_count": event["opaque_prior_count"]}}
            result = run_once(m, root, "trial-" + str(len(trials) + 1).zfill(4), "paired", min(args.timeout, max(0.01, args.seconds - (time.monotonic() - start))), patch=plan)
            trial = {"event_id": event["id"], "replacement": replacement, "run": result, "selected_changed": False, "artifact_changed": False}
            trial["paired_parent_baseline_equal"] = bool(result.get("artifact") == observation["plain"]["artifact"])
            if result["ok"] and trial["paired_parent_baseline_equal"] and result.get("child", {}).get("ok"):
                child = result["child"]
                after = bounded_bytes(Path(child["directory"]) / m["artifact"], MAX_ARTIFACT_BYTES)
                trial["artifact_changed"] = after != original
                try:
                    new_target, _ = selected_value(after, selector)
                    trial["selected_changed"] = type(new_target) is not type(target) or new_target != target
                    if selector["kind"] == "html":
                        trial["collateral"] = html_collateral(original, after)
                    elif selector["kind"] == "jsonpath":
                        trial["collateral"] = changes(decode_artifact(original, selector["encoding"]), decode_artifact(after, selector["encoding"]))
                    else:
                        before_text, after_text = original.decode(), after.decode()
                        trial["collateral"] = {"original_characters": len(before_text), "counterfactual_characters": len(after_text), "whole_artifact_changed": before_text != after_text, "selected_span_before": preview(target), "selected_span_after": preview(new_target), "note": "Fixed character offsets can shift when earlier output length changes; inspect the captured complete artifacts."}
                except (Refusal, UnicodeError) as e:
                    trial["selector_error"] = str(e)
            trials.append(trial)
            if trial["selected_changed"]:
                plan["observed_effect"] = {"counterfactual_artifact": result["child"]["artifact"], "paired_parent_artifact": result["artifact"], "selected_changed": True, "collateral": trial.get("collateral")}
                plan["plan_hash"] = sha(encoded(plan))
                (root / "intervention.json").write_bytes(encoded(plan) + b"\n")
                discovered = plan
                break
        if discovered or len(trials) >= args.max_trials or time.monotonic() - start >= args.seconds:
            break
    undo = run_once(m, root, "fresh-undo", "plain", args.timeout)
    undo_equal = bool(undo["ok"] and undo["artifact"] == observation["plain"]["artifact"])
    report = {"schema": SCHEMA, "kind": "search", "status": "influence_confirmed" if discovered and undo_equal else "unresolved", "selector": selector, "selected_baseline": preview(target), "candidate_count": len(candidates), "trial_count": len(trials), "seconds": time.monotonic() - start, "trials": trials, "intervention_file": str(root / "intervention.json") if discovered else None, "fresh_undo": undo, "undo_byte_identical": undo_equal, "limitations": ["Candidate priority is not inferred dataflow; only selected-output changes confirmed by guarded fresh replay establish influence on this run.", "Temporary return replacement is a counterfactual experiment, not a source-level repair.", "Recorded call ancestry and bounded argument previews are not complete causal dataflow."]}
    (root / "search.json").write_bytes(encoded(report) + b"\n")
    return report


def replay(args):
    validate_api(args)
    plan = json.loads(bounded_bytes(args.plan, 16 * 1024 * 1024))
    if type(plan) is not dict or plan.get("schema") != SCHEMA or plan.get("kind") != "intervention" or plan.get("backend") != "paired-os-fork" or plan.get("prefix_scope") != "portable-values-and-opaque-markers":
        raise Refusal("Invalid intervention plan schema")
    checksum = plan.pop("plan_hash", None)
    if not checksum or checksum != sha(encoded(plan)):
        raise Refusal("Intervention plan checksum mismatch")
    plan["plan_hash"] = checksum
    m = plan["manifest"]
    if sha(encoded(m)) != plan["manifest_hash"]:
        raise Refusal("Plan manifest hash mismatch")
    verify_identities(m)
    validate_selector(plan.get("selector"))
    validate_patch(plan, m)
    root = create_dir(args.out)
    baseline = run_once(m, root, "fresh-baseline", "plain", args.timeout)
    if not baseline["ok"] or baseline.get("artifact") != plan["baseline_artifact"]:
        raise Refusal("Fresh baseline differs from recorded experiment")
    before = bounded_bytes(Path(baseline["directory"]) / m["artifact"], MAX_ARTIFACT_BYTES)
    target, _ = selected_value(before, plan["selector"])
    result = run_once(m, root, "paired-experiment", "paired", args.timeout, patch=plan)
    selected_changed, collateral = False, None
    if result["ok"]:
        try:
            if result.get("artifact") != plan["baseline_artifact"] or result.get("child", {}).get("artifact") != plan["observed_effect"]["counterfactual_artifact"]:
                raise Refusal("Counterfactual artifact differs from recorded experiment")
            parent = bounded_bytes(Path(result["directory"]) / m["artifact"], MAX_ARTIFACT_BYTES)
            after = bounded_bytes(Path(result["child"]["directory"]) / m["artifact"], MAX_ARTIFACT_BYTES)
            parent_target, _ = selected_value(parent, plan["selector"])
            new_target, _ = selected_value(after, plan["selector"])
            selected_changed = type(new_target) is not type(parent_target) or new_target != parent_target
            if parent != before or type(parent_target) is not type(target) or parent_target != target or not selected_changed:
                raise Refusal("Actual paired selector did not change from the verified baseline")
            if plan["selector"]["kind"] == "html":
                collateral = html_collateral(parent, after)
            elif plan["selector"]["kind"] == "jsonpath":
                collateral = changes(decode_artifact(parent, plan["selector"]["encoding"]), decode_artifact(after, plan["selector"]["encoding"]))
            else:
                collateral = {"selected_span_before": preview(parent_target), "selected_span_after": preview(new_target), "note": "Text spans use positional character offsets."}
        except (Refusal, UnicodeError) as exc:
            result["ok"] = False
            result["error"] = {"type": "Refusal", "message": str(exc)}
    undo = run_once(m, root, "fresh-undo", "plain", args.timeout)
    equal = bool(undo["ok"] and undo["artifact"] == plan["baseline_artifact"])
    report = {"schema": SCHEMA, "kind": "replay", "status": "reproduced" if result["ok"] and equal and selected_changed else "refused", "selector": plan["selector"], "selected_changed": selected_changed, "collateral": collateral, "fresh_baseline": baseline, "counterfactual": result, "fresh_undo": undo, "undo_byte_identical": equal}
    (root / "replay.json").write_bytes(encoded(report) + b"\n")
    return report


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    o = sub.add_parser("observe")
    o.add_argument("--script", required=True); o.add_argument("--module", action="append", default=[])
    o.add_argument("--input", action="append", default=[]); o.add_argument("--arg", action="append", default=[])
    o.add_argument("--artifact", required=True); o.add_argument("--out", required=True)
    o.add_argument("--max-events", type=int, default=300000); o.add_argument("--timeout", type=float, default=30)
    s = sub.add_parser("search")
    s.add_argument("--observation", required=True); s.add_argument("--out", required=True)
    g = s.add_mutually_exclusive_group(required=True); g.add_argument("--pointer"); g.add_argument("--start", type=int); g.add_argument("--html-id")
    s.add_argument("--html-next-sibling", type=int, default=0)
    s.add_argument("--end", type=int); s.add_argument("--encoding", choices=("json", "literal"), default="json")
    s.add_argument("--max-trials", type=int, default=128); s.add_argument("--seconds", type=float, default=120); s.add_argument("--timeout", type=float, default=30)
    r = sub.add_parser("replay"); r.add_argument("--plan", required=True); r.add_argument("--out", required=True); r.add_argument("--timeout", type=float, default=30)
    return p


def main(argv=None):
    if sys.argv[1:2] == ["_worker"]:
        return worker(sys.argv[2])
    args = parser().parse_args(argv)
    if not 0.01 <= args.timeout <= 300:
        raise Refusal("Whole-process timeout must be .01..300 seconds")
    if args.command == "search" and (not 1 <= args.max_trials <= 512 or not 0.01 <= args.seconds <= 600 or args.start is not None and args.end is None or not 0 <= args.html_next_sibling <= 16):
        raise Refusal("Invalid bounded search configuration")
    result = {"observe": observe, "search": search, "replay": replay}[args.command](args)
    summary = {k: result[k] for k in ("schema", "kind", "status")}
    for k in ("baseline_byte_parity", "candidate_count", "trial_count", "undo_byte_identical", "intervention_file"):
        if k in result:
            summary[k] = result[k]
    print(json.dumps(summary))
    return 0 if result["status"] in ("observed", "influence_confirmed", "reproduced") else 3

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Refusal, OSError, ValueError, KeyError, TypeError, RecursionError) as e:
        print(json.dumps({"schema": SCHEMA, "status": "refused", "error": type(e).__name__, "message": str(e)[:1000]}))
        raise SystemExit(3)
