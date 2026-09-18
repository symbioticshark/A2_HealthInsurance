#!/usr/bin/env python3
"""Small paid pilot to choose the D2(b) V1/V2 comparison model.

This is a MODEL-SELECTION experiment, not the formal D2(b) measurement.
It deliberately uses four history-sensitive cases only:

  CLM-8850  near miss: same member/hospital/line, different service date
  CLM-8933  true duplicate
  CLM-8960  near miss: same member/hospital/date, different line items
  CLM-9025  true duplicate built from an added decided-claim record

Default work: 2 models x 2 interfaces x 4 cases x 1 trial = 16 live runs.
Once a model is selected, run the full 40-case standard battery for V1 and
V2 with run_v1_v2_live_battery.py. Do not quote this pilot as D2(b) evidence.
"""
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from backend import live_backend
from eval import eval_harness


DEFAULT_MODELS = ["openai/gpt-4o-mini", "google/gemini-2.5-flash"]
DEFAULT_CASES = ["CLM-8850", "CLM-8933", "CLM-8960", "CLM-9025"]


def _summary(rows):
    total = len(rows)
    return {
        "runs": total,
        "pass_rate": round(sum(row["pass"] for row in rows) / total, 4) if total else 0.0,
        "total_tokens": sum(row["tokens_in"] + row["tokens_out"] for row in rows),
        "total_cost_usd": round(sum(row["cost_usd"] for row in rows), 6),
        "failed_case_ids": sorted({row["case_id"] for row in rows if not row["pass"]}),
    }


def _confirm(prompt):
    return input(prompt).strip().upper() == "Y"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--cases", nargs="+", default=DEFAULT_CASES)
    parser.add_argument("--trials", type=int, default=1, help="Trials per selected case and interface")
    parser.add_argument("--yes", action="store_true", help="Skip the paid-run confirmation prompt")
    args = parser.parse_args(argv)

    if args.trials < 1:
        parser.error("--trials must be at least 1")
    if len(args.models) < 2:
        parser.error("provide at least two models to compare")
    if not live_backend.get_api_key():
        print("No OpenRouter API key is configured. Add one in the launcher configuration first.")
        return 1

    planned = len(args.models) * 2 * len(args.cases) * args.trials
    print("=== V1/V2 MODEL-SELECTION PILOT (not formal D2(b) evidence) ===")
    print(f"Models: {', '.join(args.models)}")
    print(f"Cases:  {', '.join(args.cases)}")
    print(f"Plan:   {len(args.models)} model(s) x V1/V2 x {len(args.cases)} case(s) x "
          f"{args.trials} trial(s) = {planned} paid live runs")
    if not args.yes and not _confirm("This will spend OpenRouter credit. Continue? Y/N: "):
        print("Cancelled -- nothing was run.")
        return 0

    report = {
        "purpose": "model_selection_pilot_not_formal_d2b_evidence",
        "models": args.models,
        "cases": args.cases,
        "trials_per_case": args.trials,
        "results": {},
    }
    for model in args.models:
        report["results"][model] = {}
        for interface in ("v1", "v2"):
            print(f"\n--- {model} | {interface.upper()} ---")
            outcome = eval_harness.run_evaluation(
                cases=args.cases,
                trials=args.trials,
                backend="live",
                model=model,
                verbose=True,
                run_mode="v1_v2_model_selection_pilot",
                tool_interface=interface,
            )
            report["results"][model][interface] = _summary(outcome["rows"])

    print("\n=== PILOT SUMMARY ===")
    print(f"{'Model':<30}{'V1 pass':>10}{'V2 pass':>10}{'V1 cost':>12}{'V2 cost':>12}")
    for model in args.models:
        v1 = report["results"][model]["v1"]
        v2 = report["results"][model]["v2"]
        print(f"{model:<30}{v1['pass_rate']:>9.1%}{v2['pass_rate']:>10.1%}"
              f"${v1['total_cost_usd']:>10.5f}${v2['total_cost_usd']:>10.5f}")

    out_path = os.path.join(PROJECT_ROOT, "results", "v1_v2_model_selection_pilot.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(f"\nSaved pilot summary: {out_path}")
    print("Use this only to choose the D2(b) model. Then run the full V1/V2 battery on that one model.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
