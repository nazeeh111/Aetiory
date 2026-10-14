"""Build a portable, read-only investigation from retained paired artifacts."""

import json
from pathlib import Path
from . import engine
from .web._make_portable import portable_document


def read_report(path):
    report = json.loads(engine.bounded_bytes(Path(path), 16 * 1024 * 1024))
    if type(report) is not dict or report.get("schema") != engine.SCHEMA:
        raise engine.Refusal("Unsupported retained report schema")
    return report


def artifact(directory, name, expected):
    data = engine.bounded_bytes(Path(directory) / name, 1024 * 1024)
    if {"bytes": len(data), "sha256": engine.sha(data)} != expected:
        raise engine.Refusal("Retained artifact bytes do not match the receipt")
    return data


def full_changes(before, after):
    result, stack = [], [(before, after, "")]
    while stack:
        a, b, path = stack.pop()
        if type(a) is type(b) is dict and set(a) == set(b):
            for key in reversed(list(a)):
                stack.append((a[key], b[key], path + "/" + str(key).replace("~", "~0").replace("/", "~1")))
        elif type(a) is type(b) is list and len(a) == len(b):
            for index in range(len(a) - 1, -1, -1):
                stack.append((a[index], b[index], path + "/" + str(index)))
        elif type(a) is not type(b) or a != b:
            result.append({"path": path, "before": a, "after": b})
            if len(result) > 512:
                raise engine.Refusal("Portable view supports at most 512 changed fields")
    return result


def experiment(observation_path, search_path, title="A paired return experiment", replay_path=None):
    if not isinstance(title, str) or not 1 <= len(title) <= 256:
        raise engine.Refusal("Choose a title of 1..256 characters")
    observation, search = read_report(observation_path), read_report(search_path)
    if (observation.get("kind") != "observation" or observation.get("status") != "observed"
            or observation.get("baseline_byte_parity") is not True
            or observation["plain"].get("ok") is not True or observation["observed"].get("ok") is not True
            or search.get("kind") != "search" or search.get("status") != "influence_confirmed"
            or search.get("undo_byte_identical") is not True or search["fresh_undo"].get("ok") is not True):
        raise engine.Refusal("Export requires a confirmed influence and exact fresh undo")
    plan = read_report(Path(search_path).parent / "intervention.json")
    digest = plan.pop("plan_hash", None)
    if not digest or digest != engine.sha(engine.encoded(plan)):
        raise engine.Refusal("Plan checksum mismatch")
    manifest = plan["manifest"]
    engine.validate_manifest(manifest)
    engine.validate_patch(plan, manifest)
    engine.validate_selector(plan["selector"])
    if (plan.get("kind") != "intervention" or search["selector"] != plan["selector"]
            or manifest != observation["manifest"]
            or engine.sha(engine.encoded(manifest)) != plan["manifest_hash"]
            or observation["manifest_hash"] != plan["manifest_hash"]):
        raise engine.Refusal("Observation and plan do not describe the same run")
    # This only verifies retained files. It neither runs code nor authenticates an author.
    for item in [manifest["script"], *manifest["modules"].values(), *manifest["inputs"]]:
        if engine.identity(item["path"]) != item:
            raise engine.Refusal("Declared source/input changed before export")
    trial = next((t for t in search["trials"] if t["selected_changed"] and t["event_id"] == plan["event"]["id"]), None)
    if (not trial or not trial["paired_parent_baseline_equal"]
            or trial["replacement"] != plan["replacement"]
            or plan["baseline_artifact"] != observation["plain"]["artifact"]):
        raise engine.Refusal("Missing accepted parent/child trial")
    run = trial["run"]
    if (run.get("ok") is not True or run["child"].get("ok") is not True
            or run.get("split", {}).get("event") != plan["event"]
            or run["child"]["artifact"] != plan["observed_effect"]["counterfactual_artifact"]
            or run["artifact"] != plan["observed_effect"]["paired_parent_artifact"]):
        raise engine.Refusal("Trial and plan do not bind the same paired effect")
    before = artifact(observation["plain"]["directory"], manifest["artifact"], observation["plain"]["artifact"])
    observed = artifact(observation["observed"]["directory"], manifest["artifact"], observation["observed"]["artifact"])
    parent = artifact(run["directory"], manifest["artifact"], run["artifact"])
    after = artifact(run["child"]["directory"], manifest["artifact"], run["child"]["artifact"])
    undo = artifact(search["fresh_undo"]["directory"], manifest["artifact"], search["fresh_undo"]["artifact"])
    if not before == observed == parent == undo or run.get("child_reaped") is not True:
        raise engine.Refusal("Export guards do not pass against actual retained bytes")
    replay_note = "Fresh intervention replay was not supplied to this export; the recorded search trial and fresh unchanged run were checked."
    if replay_path is not None:
        replay = read_report(replay_path)
        if (replay.get("kind") != "replay" or replay.get("status") != "reproduced" or replay.get("selected_changed") is not True
                or replay.get("selector") != plan["selector"]
                or replay.get("undo_byte_identical") is not True or replay["counterfactual"].get("child_reaped") is not True
                or replay["counterfactual"].get("ok") is not True or replay["counterfactual"]["child"].get("ok") is not True
                or replay["fresh_undo"].get("ok") is not True or replay["fresh_baseline"].get("ok") is not True
                or replay["counterfactual"].get("split", {}).get("event") != plan["event"]):
            raise engine.Refusal("Fresh intervention replay checks are missing or contradictory")
        repeated = replay["counterfactual"]
        if (artifact(repeated["directory"], manifest["artifact"], repeated["artifact"]) != before
                or artifact(repeated["child"]["directory"], manifest["artifact"], repeated["child"]["artifact"]) != after
                or artifact(replay["fresh_undo"]["directory"], manifest["artifact"], replay["fresh_undo"]["artifact"]) != before):
            raise engine.Refusal("Fresh replay artifact bytes do not reproduce the search")
        replay_note = "Fresh native intervention replay independently resolved the selector and reproduced both artifacts; its child was reaped and fresh unchanged output matched exactly."
    selector = plan["selector"]
    selected_before, _ = engine.selected_value(before, selector)
    selected_after, _ = engine.selected_value(after, selector)
    if type(selected_before) is type(selected_after) and selected_before == selected_after:
        raise engine.Refusal("Selected value did not change")
    if selector["kind"] == "html":
        view_selector = {"kind": "html-id-following-element-sibling", "id": selector["id"], "sibling": selector["following_element_sibling"]}
        trees = engine.html_tree(before), engine.html_tree(after)
        changes = []
        for key in sorted(set(trees[0].ids) | set(trees[1].ids)):
            for sibling in (0, 1):
                values = []
                for tree in trees:
                    try:
                        values.append(tree.selected(key, sibling))
                    except engine.Refusal:
                        values.append(None)
                if values[0] != values[1]:
                    changes.append({"path": "#" + key + " → element sibling " + str(sibling), "before": values[0], "after": values[1], "selected": key == selector["id"] and sibling == selector["following_element_sibling"]})
        media = "text/html"
    elif selector["kind"] == "jsonpath":
        view_selector = {"kind": "literal-json-pointer" if selector["encoding"] == "literal" else "json-pointer", "pointer": selector["pointer"]}
        changes = full_changes(engine.decode_artifact(before, selector["encoding"]), engine.decode_artifact(after, selector["encoding"]))
        for change in changes:
            change["selected"] = change["path"] == selector["pointer"]
        if not any(c["selected"] for c in changes):
            # A changed selected container may contain several changed leaves.
            changes.insert(0, {"path": selector["pointer"], "before": selected_before, "after": selected_after, "selected": True})
        media = "application/json" if selector["encoding"] == "json" else "text/x-python-literal"
    else:
        raise engine.Refusal("Portable view needs a stable HTML selector or parsed pointer")
    changes.sort(key=lambda c: (not c["selected"], isinstance(c["before"], dict) and c["before"].get("tag") == "table"))
    if len(changes) > 512 or not any(c["selected"] for c in changes):
        raise engine.Refusal("Selected semantic change is unavailable or exceeds the view bound")
    event = plan["event"]
    occurrence, recorded_event = 0, None
    for observed_event in engine.load_events(Path(observation["observed"]["directory"]) / "trace.jsonl.gz"):
        if all(observed_event[k] == event[k] for k in ("module", "site", "function")):
            occurrence += 1
        if observed_event["id"] == event["id"]:
            recorded_event = observed_event
            break
    if (recorded_event is None
            or any(recorded_event[k] != event[k] for k in ("module", "site", "function", "value_hash", "prefix_before", "ancestry_hash"))
            or recorded_event["packed"] != plan["trace_evidence"]["packed"]
            or recorded_event["ancestry"] != plan["trace_evidence"]["ancestry"]):
        raise engine.Refusal("Return description does not match the retained observed trace")
    source = manifest["modules"][event["module"]]
    source_text = engine.bounded_bytes(source["path"], 8 * 1024 * 1024).decode()
    line = int(event["site"].split(":")[0])
    start = max(1, line - 5)
    expected = engine.unpacked(plan["trace_evidence"]["packed"])
    replacement = engine.unpacked(plan["replacement"])
    return {"id": plan["event"]["module"] + "-" + str(event["id"]), "title": title,
        "summary": f"Automatic search tested {search['trial_count']} paired trials from {search['candidate_count']} eligible return candidates. The original parent and fresh undo matched the baseline bytes.",
        "mode": "recorded", "status": "accepted", "selector": view_selector,
        "artifacts": {side: {"text": body.decode("utf-8", errors="strict"), "media_type": media, "sha256": engine.sha(body)} for side, body in (("before", before), ("after", after))},
        "event": {"id": event["id"], "site": event["site"], "occurrence": occurrence,
            "ancestry": plan["trace_evidence"]["ancestry"], "portable_expected": expected,
            "portable_replacement": replacement, "prefix_before": event["prefix_before"],
            "value_hash": event["value_hash"], "args_preview": run["split"].get("actual_arguments")},
        "source": {"name": event["module"] + ".py", "sha256": source["sha256"], "start_line": start, "text": "\n".join(source_text.splitlines()[start-1:line+10])},
        "changes": changes, "guards": {"plain_observed_equal": True, "parent_matches_original": True, "selected_changed": True, "source_inputs_preserved": True, "fresh_undo_equal": True, "child_reaped": True},
        "limitations": observation["limitations"] + search["limitations"] + ["Recorded, unauthenticated receipts and local-byte checks do not establish a causal theorem or source repair. Native fork does not roll back external state. Fresh replay remains local to the pinned source, engine and interpreter environment."],
        "provenance": ["Generated from actual retained automatic search and paired artifacts; no target-function or fixture-hash dispatch.", replay_note, "Engine SHA256 " + manifest["engine"]["sha256"], "Intervention checksum " + digest,
            *["Declared input " + Path(i["path"]).name + " SHA256 " + i["sha256"] for i in manifest["inputs"]]]}


def export_record(payload, output):
    def exact_browser_values(value, depth=0):
        if depth > 40:
            raise engine.Refusal("Portable view nesting exceeds 40 levels")
        if type(value) is int and abs(value) > 9007199254740991:
            raise engine.Refusal("Integer exceeds the browser's exact numeric range; inspect the native typed plan instead")
        if isinstance(value, (list, tuple, dict)):
            values = value.values() if isinstance(value, dict) else value
            if len(value) > 4096:
                raise engine.Refusal("Portable view collection exceeds 4096 items")
            for item in values:
                exact_browser_values(item, depth + 1)
    exact_browser_values(payload)
    body = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
    if len(body.encode()) > 8 * 1024 * 1024:
        raise engine.Refusal("Portable record exceeds 8 MiB")
    html = portable_document(payload)
    root = engine.create_dir(output)
    (root / "experiment.json").write_text(body, encoding="utf-8", newline="\n")
    (root / "index.html").write_text(html, encoding="utf-8", newline="\n")
    return {"schema": "experiment-view/1", "status": "exported", "directory": str(root), "cases": len(payload["experiments"])}
