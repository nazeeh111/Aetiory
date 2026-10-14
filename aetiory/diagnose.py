"""Run a complete trusted failing-script investigation with retained evidence."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from . import engine


def diagnose(args):
    engine.validate_api(SimpleNamespace(timeout=args.timeout, max_trials=args.max_trials,
        seconds=args.seconds, html_next_sibling=0, start=None, end=None), search_mode=True)
    if type(args.title) is not str or not 1 <= len(args.title) <= 256:
        raise engine.Refusal("Choose a title of1..256 characters")
    if (args.stdout_pointer is None) != (args.stdout_equals is None):
        raise engine.Refusal("Pass both stdout pointer and expected JSON value, or neither")
    if args.stdout_pointer is not None:
        engine.pointer_tokens(args.stdout_pointer)
        value = engine.decode_artifact(args.stdout_equals.encode("utf-8"), "json")
        if not engine.portable(engine.packed(value)) or len(engine.encoded(engine.packed(value))) > 2048:
            raise engine.Refusal("Expected stdout value must be portable and at most 2 KiB")
    root = engine.create_dir(args.out)
    result = {"schema": engine.SCHEMA, "kind": "diagnosis", "status": "refused",
              "directory": str(root), "source_repair": False}
    try:
        observation = engine.observe(SimpleNamespace(script=args.script, module=args.module,
            input=args.input, arg=args.arg, artifact=None, capture_outcome=True,
            out=str(root / "observed"), max_events=args.max_events, timeout=args.timeout))
        result["observation_file"] = str(root / "observed/observation.json")
        if observation["status"] != "observed":
            result["reason"] = "The unchanged and observed target outcomes did not pass capture/parity checks"
            return result
        search = engine.search(SimpleNamespace(observation=result["observation_file"],
            out=str(root / "searched"), successful_exit=True,
            stdout_pointer=args.stdout_pointer, stdout_equals=args.stdout_equals,
            pointer=None, html_id=None, html_next_sibling=0, start=None, end=None,
            encoding="json", max_trials=args.max_trials, seconds=args.seconds, timeout=args.timeout))
        result.update(search_file=str(root / "searched/search.json"), trial_count=search["trial_count"])
        if search["status"] != "influence_confirmed":
            result.update(status="unresolved", reason="No guarded return trial reached the requested exit/stdout outcome")
            return result
        plan = root / "searched/intervention.json"
        result["intervention_file"] = str(plan)
        replay = engine.replay(SimpleNamespace(plan=str(plan), out=str(root / "replayed"), timeout=args.timeout))
        result["replay_file"] = str(root / "replayed/replay.json")
        if replay["status"] != "reproduced":
            result["reason"] = "The discovered outcome did not reproduce with fresh native replay"
            return result
        from .export import experiment, export_record
        export_record({"schema": "experiment-view/1", "experiments": [experiment(
            result["observation_file"], result["search_file"], args.title, result["replay_file"])]}, root / "viewer")
        result.update(status="diagnosed", viewer_file=str(root / "viewer/index.html"),
            experiment_file=str(root / "viewer/experiment.json"),
            meaning="A temporary return reached the requested outcome; this does not repair the source")
        return result
    except (engine.Refusal, OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)[:1000]}
        return result
    finally:
        (root / "diagnosis.json").write_bytes(engine.encoded(result) + b"\n")


def parser():
    p = argparse.ArgumentParser(description="Find an earlier return that lets a trusted failing script finish successfully. Does not edit source.")
    p.add_argument("--script", required=True)
    p.add_argument("--module", action="append", default=[])
    p.add_argument("--input", action="append", default=[])
    p.add_argument("--arg", action="append", default=[])
    p.add_argument("--out", required=True)
    p.add_argument("--stdout-pointer", help="JSON pointer into the complete captured stdout")
    p.add_argument("--stdout-equals", help="Exact expected JSON value; use = before a negative number")
    p.add_argument("--max-events", type=int, default=300000)
    p.add_argument("--max-trials", type=int, default=128)
    p.add_argument("--seconds", type=float, default=120)
    p.add_argument("--timeout", type=float, default=30)
    p.add_argument("--title", default="Why did this script fail?")
    return p


def main(argv):
    result = diagnose(parser().parse_args(argv))
    print(json.dumps(result))
    return 0 if result["status"] == "diagnosed" else 2 if result["status"] == "unresolved" else 3
