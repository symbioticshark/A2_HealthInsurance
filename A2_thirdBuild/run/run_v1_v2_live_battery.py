#!/usr/bin/env python3
"""Run one normal V1 battery and one normal V2 battery, then compare them.

This compatibility command now uses the normal evaluation/session history for
both runs and delegates reporting to compare_v1_v2.py. It never writes a
root-level V1/V2 report.
"""
import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from eval import eval_harness, metrics, session_results
from run import api_key_flow, compare_sessions, compare_v1_v2


def _confirm(prompt):
    return input(prompt).strip().upper() == "Y"


def _run_standard_battery(model, version):
    labels = eval_harness.load_labels()
    return eval_harness.run_evaluation(
        trials=1,
        backend="live",
        model=model,
        verbose=True,
        run_mode="standard_battery",
        trial_counts=eval_harness.standard_trial_counts(labels),
        tool_interface=version,
    )


def _estimate_cost(model, total_runs):
    rows = [
        row for row in metrics.load_all_metrics(os.path.join(PROJECT_ROOT, "results"))
        if row.get("model") == model and row.get("cost_is_measured")
    ]
    if not rows:
        return None
    return sum(float(row.get("cost_usd", 0.0)) for row in rows) / len(rows) * total_runs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="OpenRouter model ID used for both versions")
    parser.add_argument("--run-both", action="store_true", help="Accepted for compatibility; both are always run")
    parser.add_argument("--yes", action="store_true", help="Skip the paid-run confirmation")
    parser.add_argument("--api-prechecked", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--reuse-v2-run-log", help=argparse.SUPPRESS)
    parser.add_argument("--choose-v2-run-log", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.reuse_v2_run_log or args.choose_v2_run_log:
        print("Raw run-log reuse has been retired because it bypasses session history.")
        print("Use run/compare_v1_v2.py to compare existing sessions without spending API credit.")
        return 1
    if not args.api_prechecked and not api_key_flow.ensure_api_ready():
        print("V1/V2 live comparison cancelled before any paid request.")
        return 1

    labels = eval_harness.load_labels()
    runs_per_version = sum(eval_harness.standard_trial_counts(labels).values())
    print(f"=== V1/V2 live comparison on {args.model} ===")
    print(f"Tester: {metrics.get_person_name()}")
    print(f"Plan: V1 {runs_per_version} runs + V2 {runs_per_version} runs = "
          f"{runs_per_version * 2} paid live runs")
    estimated_cost = _estimate_cost(args.model, runs_per_version * 2)
    if estimated_cost is not None:
        print(f"Estimated combined cost from same-model history: ${estimated_cost:.5f}")
    else:
        print("Estimated combined cost: unavailable (no measured same-model history)")
    print("Both batteries use the normal evaluator and normal tester history.")
    if not args.yes and not _confirm("This will spend OpenRouter credit. Continue? Y/N: "):
        print("Cancelled -- nothing was run.")
        return 0

    print("\n--- Running normal V1 standard battery ---")
    v1_result = _run_standard_battery(args.model, "v1")
    if not v1_result:
        print("V1 did not complete; V2 was not started.")
        return 1

    print("\n--- Running normal V2 standard battery ---")
    v2_result = _run_standard_battery(args.model, "v2")
    if not v2_result:
        print("V2 did not complete. The completed V1 session remains in normal history.")
        return 1

    sessions = compare_sessions.available_sessions(False)
    v1 = session_results.session_by_id(sessions, v1_result["session"]["session_id"])
    v2 = session_results.session_by_id(sessions, v2_result["session"]["session_id"])
    if not v1 or not v2:
        print("Both runs completed, but their sessions could not be reloaded safely for comparison.")
        return 1
    compare_v1_v2.compare_pair(v1, v2, save=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
