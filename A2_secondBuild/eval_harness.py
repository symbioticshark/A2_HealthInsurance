#!/usr/bin/env python3
"""
D4 -- the evaluation harness.

    python3 eval_harness.py                 # all cases, 1 trial, scripted backend
    python3 eval_harness.py --trials 3
    python3 eval_harness.py --cases CLM-8888 CLM-8933
    A2_BACKEND=live A2_MODEL=... python3 eval_harness.py

Grading is OUTCOME-based (D4): a run passes only if BOTH the decision type
matches (approve_in_principle / request_document / escalate) AND, where the
label specifies one, the trigger (for escalate) or the missing item's
procedure code (for request_document) matches -- reaching the right
decision by the wrong route is not a pass (the brief's own words).

Each case is graded fresh from a clean data store -- D4's isolation
requirement -- there is no shared mutable state between trials besides the
append-only decision ledger, which no grading logic reads back from.
"""
import argparse
import json
import os
import statistics as stats
import sys

sys.path.insert(0, os.path.dirname(__file__))
from agent_a import loop, config
from agent_a.data_io import STORE

LABELS_PATH = os.path.join(os.path.dirname(__file__), "expected_outcomes_A.json")


def load_labels():
    with open(LABELS_PATH) as f:
        return {c["case_id"]: c for c in json.load(f)}


def grade(run: loop.RunResult, label: dict) -> bool:
    if run.decision != label["expected_decision"]:
        return False
    if label["expected_decision"] == "escalate" and "trigger" in label:
        return run.trigger == label["trigger"]
    if label["expected_decision"] == "request_document" and "missing" in label:
        # loose match: the same procedure code must appear in both strings
        import re
        code_in_label = re.search(r"\b\d{4,5}[A-Z]?\b", label["missing"])
        if code_in_label and run.missing:
            return code_in_label.group(0) in run.missing
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="*", default=None, help="subset of case ids; default = all labelled cases")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--autonomy", default=loop.G.AUTONOMY_SETTING)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    labels = load_labels()
    case_ids = args.cases or list(labels.keys())
    missing = [c for c in case_ids if c not in STORE.claims]
    if missing:
        print(f"WARNING: not in claims.json (skipping): {missing}")
        case_ids = [c for c in case_ids if c in STORE.claims]

    rows = []
    per_case_pass = {}
    for cid in case_ids:
        label = labels.get(cid)
        if label is None:
            print(f"WARNING: {cid} has no label in expected_outcomes_A.json -- skipping")
            continue
        passes = []
        for t in range(args.trials):
            run = loop.run_case(cid, autonomy=args.autonomy)
            ok = grade(run, label)
            passes.append(ok)
            rows.append({
                "case_id": cid, "trial": t, "pass": ok, "decision": run.decision,
                "trigger": run.trigger, "missing": run.missing, "turns": run.turns,
                "tokens_in": run.tokens_in, "tokens_out": run.tokens_out,
                "cost_usd": round(run.cost_usd, 5), "guardrail_stop": run.guardrail_stop,
                "family": label.get("family"),
            })
            if args.verbose:
                mark = "PASS" if ok else "FAIL"
                print(f"[{mark}] {cid} trial {t}: {run.decision} (trigger={run.trigger}, missing={run.missing}), "
                      f"turns={run.turns}, cost=${run.cost_usd:.5f}")
        per_case_pass[cid] = sum(passes) / len(passes)

    os.makedirs("results", exist_ok=True)
    with open("results/run_log.json", "w") as f:
        json.dump(rows, f, indent=2)

    n = len(rows)
    overall_pass = sum(r["pass"] for r in rows) / n if n else 0.0
    turns_list = [r["turns"] for r in rows]
    tokens_list = [r["tokens_in"] for r in rows]
    cost_list = [r["cost_usd"] for r in rows]

    print()
    print(f"Backend: {config.BACKEND}  Model: {config.MODEL if config.BACKEND=='live' else 'n/a'}  "
          f"Autonomy: {args.autonomy}")
    print(f"Cases: {len(case_ids)}  Trials/case: {args.trials}  Total runs: {n}")
    print(f"Overall pass rate: {overall_pass:.1%}")
    if turns_list:
        print(f"Turns   -- median: {stats.median(turns_list)}  max: {max(turns_list)}")
        print(f"Tokens  -- mean input: {stats.mean(tokens_list):.0f}")
        print(f"Cost    -- mean: ${stats.mean(cost_list):.5f}  total: ${sum(cost_list):.5f}")

    print()
    print("Per-case pass rate:")
    for cid, rate in per_case_pass.items():
        fam = labels[cid].get("family", "")
        flag = "" if rate == 1.0 else "  <-- CHECK"
        print(f"  {cid:10s} {rate:5.0%}  ({fam}){flag}")

    print()
    print("Full run log written to results/run_log.json")


if __name__ == "__main__":
    main()
