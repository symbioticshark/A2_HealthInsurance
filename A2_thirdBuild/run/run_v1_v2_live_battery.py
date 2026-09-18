#!/usr/bin/env python3
"""
D2(b) -- the live half of the v1-vs-v2 measurement: pass rate and the
business-risk negative-case subset, on ONE real model, held fixed across both tool
interface versions (holding the model fixed is what makes the difference
attributable to the descriptor rewrite rather than to the model -- see the
brief's D4 section).

COSTS REAL MONEY -- this calls OpenRouter. Nothing runs until you type Y at
this script's own confirmation prompt, in addition to whatever your
OPENROUTER_API_KEY / local_config.py already require. Estimate first: at
the cheap tier, the team's existing 72-run V2 battery on
google/gemini-2.5-flash cost $0.24; V1 usually costs a bit more per run
(it returns fatter tool output -- see v1_v2_tool_tokens_report.json) but
stays well inside the $3/member guideline.

Usage
-----
Reuse an existing V2 run (recommended -- avoids paying for V2 twice). Pass
an exact path, or use --choose-v2-run-log to select from validated candidates
for the requested model:

    python3 run_v1_v2_live_battery.py \\
        --model google/gemini-2.5-flash \\
        --reuse-v2-run-log results/zhangpeiqi/zhangpeiqi_run_log.json

Run both fresh (use for a model with no existing V2 data, e.g. testing
Qwen from scratch):

    python3 run_v1_v2_live_battery.py --model qwen/qwen3.8-flash --run-both

Either mode writes v1_v2_live_battery_report.json next to this file, and
(as always) each live run also lands in results/<your tester name>/ the
normal way -- see the "Note" printed at the end about that overwriting.
"""
import argparse
from collections import Counter
import glob
import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from eval import eval_harness, metrics
from backend import live_backend


# Cases whose expected outcome is NOT approve_in_principle -- these are the
# business-risk negative cases most plausibly affected by a fatter,
# unfiltered V1 history. They are reported separately from ordinary cases.
# They are NOT the D3 guardrail checklist: that is a separate scripted
# regression suite and must not be relabelled as a live negative-case rate.
def _negative_case_ids():
    labels = eval_harness.load_labels()
    return set(eval_harness.expected_negative_case_ids(labels))


def _run_live_standard_battery(model, tool_interface):
    labels = eval_harness.load_labels()
    trial_counts = eval_harness.standard_trial_counts(labels)
    result = eval_harness.run_evaluation(
        trials=1, backend="live", model=model, verbose=True,
        run_mode="standard_battery", trial_counts=trial_counts,
        tool_interface=tool_interface,
    )
    return result["rows"]


def _load_rows(run_log_path):
    with open(run_log_path, encoding="utf-8") as f:
        return json.load(f)


def _validate_reused_v2_rows(rows, model, source):
    """Reject a log that cannot be a fair V2 comparison baseline."""
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{source} contains no run rows")
    models = {row.get("model") for row in rows}
    versions = {str(row.get("tool_interface_version", "")).lower() for row in rows}
    trial_counts = Counter(row.get("case_id") for row in rows)
    expected_by_case = eval_harness.standard_trial_counts(eval_harness.load_labels())
    expected_counts = Counter(expected_by_case.values())
    actual_counts = Counter(trial_counts.values())
    if models != {model}:
        raise ValueError(f"{source} is for model(s) {sorted(models)}, not {model}")
    if versions != {"v2"}:
        raise ValueError(f"{source} is not a pure V2 log (versions: {sorted(versions)})")
    if set(trial_counts) != set(expected_by_case) or actual_counts != expected_counts:
        raise ValueError(
            f"{source} is not the current standard battery: expected "
            f"{sum(expected_counts.values())} rows with ordinary x1 / negative x3"
        )


def _discover_v2_candidates(model):
    pattern = os.path.join(PROJECT_ROOT, "results", "**", "*_run_log.json")
    candidates = []
    for path in glob.glob(pattern, recursive=True):
        try:
            rows = _load_rows(path)
            _validate_reused_v2_rows(rows, model, path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        candidates.append({
            "path": path,
            "rows": rows,
            "modified": os.path.getmtime(path),
            "pass_rate": sum(row.get("pass", False) for row in rows) / len(rows),
        })
    return sorted(candidates, key=lambda item: item["modified"], reverse=True)


def _choose_v2_candidate(model):
    candidates = _discover_v2_candidates(model)
    if not candidates:
        raise ValueError(
            f"No validated V2 standard-battery log was found for {model}. "
            "Use --run-both instead."
        )
    print("\nValidated V2 baselines (newest first):")
    for index, candidate in enumerate(candidates, 1):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(candidate["modified"]))
        print(f"  {index}. {stamp} | {len(candidate['rows'])} runs | "
              f"pass {candidate['pass_rate']:.1%} | {candidate['path']}")
    while True:
        choice = input("Choose a V2 baseline number, or B to cancel: ").strip().upper()
        if choice == "B":
            return None
        try:
            selected = candidates[int(choice) - 1]
            return selected["path"]
        except (ValueError, IndexError):
            print("Please enter a listed number or B.")


def _summarise(rows, negative_ids):
    total = len(rows)
    passed = sum(r["pass"] for r in rows)
    neg_rows = [r for r in rows if r["case_id"] in negative_ids]
    neg_passed = sum(r["pass"] for r in neg_rows)
    return {
        "runs": total,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "total_tokens": sum(r["tokens_in"] + r["tokens_out"] for r in rows),
        "total_cost_usd": round(sum(r["cost_usd"] for r in rows), 6),
        "negative_case_runs": len(neg_rows),
        "negative_case_pass_rate": round(neg_passed / len(neg_rows), 4) if neg_rows else 0.0,
    }


def _confirm(prompt):
    return input(prompt).strip().upper() == "Y"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="OpenRouter model id, same one for both versions")
    parser.add_argument("--reuse-v2-run-log", default=None,
                         help="Path to an existing *_run_log.json already run with V2 on --model")
    parser.add_argument("--choose-v2-run-log", action="store_true",
                         help="Interactively choose a validated existing V2 baseline for --model")
    parser.add_argument("--run-both", action="store_true",
                         help="Run V2 fresh too (use when --model has no existing V2 battery)")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt (still costs money)")
    args = parser.parse_args()

    modes_selected = sum(bool(value) for value in (
        args.reuse_v2_run_log, args.choose_v2_run_log, args.run_both,
    ))
    if modes_selected != 1:
        parser.error("pass exactly one of --reuse-v2-run-log, --choose-v2-run-log, or --run-both")

    if not live_backend.get_api_key():
        print("No OPENROUTER_API_KEY found in local_config.py. Set it first (see README) before running this.")
        return 1

    negative_ids = _negative_case_ids()
    print(f"=== D2(b): live V1-vs-V2 battery on {args.model} ===")
    print(f"Tester: {metrics.get_person_name()}  (each live run below also lands in results/<tester>/ as usual)")
    n_v2_runs = "72 (fresh)" if args.run_both else "0 (reusing a validated V2 file)"
    print(f"Planned live runs: V1 = 72, V2 = {n_v2_runs}")
    if not args.yes and not _confirm("This will spend real OpenRouter credit. Continue? Y/N: "):
        print("Cancelled -- nothing was run.")
        return 0

    v2_source = "fresh V2 battery"
    if args.run_both:
        print("\n--- Running V2 (live) ---")
        v2_rows = _run_live_standard_battery(args.model, "v2")
    else:
        reuse_path = args.reuse_v2_run_log
        if args.choose_v2_run_log:
            try:
                reuse_path = _choose_v2_candidate(args.model)
            except ValueError as exc:
                print(f"Cannot reuse a V2 baseline: {exc}")
                return 1
            if reuse_path is None:
                print("Cancelled -- no live V1 run was started.")
                return 0
        print(f"\nReusing existing V2 run log: {reuse_path}")
        try:
            v2_rows = _load_rows(reuse_path)
            _validate_reused_v2_rows(v2_rows, args.model, reuse_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Cannot use that V2 baseline: {exc}")
            return 1
        v2_source = os.path.abspath(reuse_path)

    print("\n--- Running V1 (live) ---")
    v1_rows = _run_live_standard_battery(args.model, "v1")

    v1_summary = _summarise(v1_rows, negative_ids)
    v2_summary = _summarise(v2_rows, negative_ids)

    print()
    print(f"{'Metric':<28}{'V1':>14}{'V2':>14}")
    print(f"{'runs':<28}{v1_summary['runs']:>14}{v2_summary['runs']:>14}")
    print(f"{'overall pass rate':<28}{v1_summary['pass_rate']:>13.1%}{v2_summary['pass_rate']:>14.1%}")
    print(f"{'negative-case pass rate':<28}{v1_summary['negative_case_pass_rate']:>13.1%}"
          f"{v2_summary['negative_case_pass_rate']:>14.1%}")
    print(f"{'total tokens':<28}{v1_summary['total_tokens']:>14,}{v2_summary['total_tokens']:>14,}")
    print(f"{'total cost':<28}${v1_summary['total_cost_usd']:>13.5f}${v2_summary['total_cost_usd']:>13.5f}")

    report = {
        "model": args.model, "v2_source": v2_source,
        "v1": v1_summary, "v2": v2_summary,
    }
    out_path = os.path.join(PROJECT_ROOT, "results", "v1_v2_live_battery_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved: {out_path}")
    print("\nNote: each live run above also overwrote results/<tester>/<tester>_run_log.json "
          "with its OWN version's data. If you need both raw run logs kept on disk separately, "
          "rename your tester (main menu F -> 1) between runs next time and re-run one version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
