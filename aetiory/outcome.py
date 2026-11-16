"""Classification of bounded retained trials; no causal completeness claim."""


def trial_classification(trial):
    run = trial.get("run") or {}
    child = run.get("child") or {}
    errors = [e for e in (run.get("error"), child.get("error")) if isinstance(e, dict)]
    types = {e.get("type") for e in errors}
    if "Refusal" in types:
        return "refused"
    if "Timeout" in types:
        return "timed_out"
    if run.get("ok") is not True or child.get("ok") is not True or run.get("child_reaped") is not True:
        return "failed"
    if not trial.get("paired_parent_baseline_equal"):
        return "parent_mismatch"
    if "selector_error" in trial:
        return "selector_error"
    return "changed" if trial.get("selected_changed") else "unchanged"


def outcome(trials, candidate_count, opportunities, stop_trigger, discovered, undo_equal, scan_complete=True):
    counts = {name: 0 for name in ("changed", "unchanged", "refused", "timed_out", "failed", "parent_mismatch", "selector_error")}
    for trial in trials:
        counts[trial_classification(trial)] += 1
    completed = counts["changed"] + counts["unchanged"]
    coverage = {"eligible_candidates": candidate_count, "planned_trials": opportunities if scan_complete else None,
                "attempted_trials": len(trials), "completed_trials": completed,
                "remaining_trials": max(0, opportunities - len(trials)) if scan_complete else None,
                **counts}
    if stop_trigger == "permission_denied":
        reason = "permission_denied"
    elif not undo_equal:
        reason = "fresh_undo_failed"
    elif discovered:
        reason = "influence_confirmed"
    elif stop_trigger:
        reason = stop_trigger
    elif not candidate_count:
        reason = "no_candidates"
    else:
        incomplete = {k for k in ("refused", "timed_out", "failed", "parent_mismatch", "selector_error") if counts[k]}
        reason = ({"refused": "trials_refused", "timed_out": "trials_timed_out", "failed": "trials_failed"}.get(next(iter(incomplete))) if len(incomplete) == 1 else None) if incomplete else "candidates_exhausted"
        reason = reason or "trials_incomplete"
    actions = {
        "permission_denied": "Inspect the recorded permission denial before taking further action.",
        "influence_confirmed": "Run guarded replay before drawing a final conclusion.",
        "trial_limit": "Retry with a larger trial limit; the search starts from the beginning.",
        "time_limit": "Retry with a larger time budget; the search starts from the beginning.",
        "no_candidates": "Inspect the selector and observation for relevant candidates.",
        "candidates_exhausted": "Inspect the completed trials and consider another observation or selector.",
        "fresh_undo_failed": "Inspect the fresh undo and retained trial evidence before retrying.",
        "candidate_scan_refused": "Inspect the candidate scan error and retained observation before retrying.",
        "trial_error": "Inspect the stopped trial error and retained evidence before retrying.",
        "outcome_code_changed": "Restore a stable outcome classifier and repeat the search.",
    }
    return {"termination_reason": reason, "coverage": coverage,
            "next_action": actions.get(reason, "Inspect the incomplete trial receipts before retrying.")}
