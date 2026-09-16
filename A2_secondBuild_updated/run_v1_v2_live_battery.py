#!/usr/bin/env python3
"""
D2(b) -- the live half of the v1-vs-v2 measurement: pass rate, and the
guardrail-relevant subset, on ONE real model, held fixed across both tool
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
Reuse an existing V2 run (recommended -- avoids paying for V2 twice; use
this when the model you want already has a completed V2 battery, e.g.
results/zhangpeiqi/zhangpeiqi_run_log.json on google/gemini-2.5-flash):

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
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import eval_harness
from agent_a import live_backend, metrics


# Cases whose expected outcome is NOT approve_in_principle -- these are the
# ones a fatter, unfiltered v1 history (or any other tool-interface defect)
# would most plausibly break, so they are reported separately as the
# "guardrail cases passed" figure D2(b) asks for, without needing a second,
# separately-priced live experiment.
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
    parser.add_argument("--run-both", action="store_true",
                         help="Run V2 fresh too (use when --model has no existing V2 battery)")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt (still costs money)")
    args = parser.parse_args()

    if bool(args.reuse_v2_run_log) == bool(args.run_both):
        parser.error("pass exactly one of --reuse-v2-run-log <path> or --run-both")

    if not live_backend.get_api_key():
        print("No OPENROUTER_API_KEY found in local_config.py. Set it first (see README) before running this.")
        return 1

    negative_ids = _negative_case_ids()
    print(f"=== D2(b): live V1-vs-V2 battery on {args.model} ===")
    print(f"Tester: {metrics.get_person_name()}  (each live run below also lands in results/<tester>/ as usual)")
    n_v2_runs = "72 (fresh)" if args.run_both else "0 (reusing existing file)"
    print(f"Planned live runs: V1 = 72, V2 = {n_v2_runs}")
    if not args.yes and not _confirm("This will spend real OpenRouter credit. Continue? Y/N: "):
        print("Cancelled -- nothing was run.")
        return 0

    if args.run_both:
        print("\n--- Running V2 (live) ---")
        v2_rows = _run_live_standard_battery(args.model, "v2")
    else:
        print(f"\nReusing existing V2 run log: {args.reuse_v2_run_log}")
        v2_rows = _load_rows(args.reuse_v2_run_log)

    print("\n--- Running V1 (live) ---")
    v1_rows = _run_live_standard_battery(args.model, "v1")

    v1_summary = _summarise(v1_rows, negative_ids)
    v2_summary = _summarise(v2_rows, negative_ids)

    print()
    print(f"{'Metric':<28}{'V1':>14}{'V2':>14}")
    print(f"{'runs':<28}{v1_summary['runs']:>14}{v2_summary['runs']:>14}")
    print(f"{'overall pass rate':<28}{v1_summary['pass_rate']:>13.1%}{v2_summary['pass_rate']:>14.1%}")
    print(f"{'negative-case pass rate':<28}{v1_summary['negative_case_pass_rate']:>13.1%}"
          f"{v2_summary['negative_case_pass_rate']:>14.1%}"
          "   <- this is the 'guardrail cases passed' figure for D2(b)")
    print(f"{'total tokens':<28}{v1_summary['total_tokens']:>14,}{v2_summary['total_tokens']:>14,}")
    print(f"{'total cost':<28}${v1_summary['total_cost_usd']:>13.5f}${v2_summary['total_cost_usd']:>13.5f}")

    report = {"model": args.model, "v1": v1_summary, "v2": v2_summary}
    out_path = os.path.join(HERE, "v1_v2_live_battery_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved: {out_path}")
    print("\nNote: each live run above also overwrote results/<tester>/<tester>_run_log.json "
          "with its OWN version's data. If you need both raw run logs kept on disk separately, "
          "rename your tester (main menu F -> 1) between runs next time and re-run one version.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
