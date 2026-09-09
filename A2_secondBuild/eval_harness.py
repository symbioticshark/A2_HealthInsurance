#!/usr/bin/env python3
"""
D4 -- the evaluation harness.

    python3 eval_harness.py                 # all cases, 1 trial, scripted backend
    python3 eval_harness.py --trials 3
    python3 eval_harness.py --cases CLM-8888 CLM-8933
    A2_BACKEND=live python3 eval_harness.py --model anthropic/claude-3-5-haiku

Grading is OUTCOME-based (D4): a run passes only if BOTH the decision type
matches (approve_in_principle / request_document / escalate) AND, where the
label specifies one, the trigger (for escalate) or the missing item's
procedure code (for request_document) matches -- reaching the right
decision by the wrong route is not a pass (the brief's own words).

Each case is graded fresh from a clean data store -- D4's isolation
requirement -- there is no shared mutable state between trials besides the
append-only decision ledger, which no grading logic reads back from.

EVERY invocation of this script is logged twice (agent_a/metrics.py):
  - one row per case trial, appended to results/metrics_log.jsonl
  - one row for the WHOLE invocation (however many cases/trials that was),
    appended to results/run_history.jsonl, and results/comparison_report.json
    is regenerated from the full history so `python3 main.py metrics` can
    show run-over-run comparisons -- even across sessions on the same model.

The detailed per-trial log for THIS invocation is written to
results/{name}_run_log.json, where {name} comes from local_config.py's
`name` value (falls back to "anonymous" if not set -- see README).
"""
import argparse
import json
import os
import statistics as stats
import sys

sys.path.insert(0, os.path.dirname(__file__))
from agent_a import loop, config, metrics
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
    ap.add_argument("--model", default=None, help="override config.MODEL for this run (BACKEND=live only)")
    ap.add_argument("--backend", default=config.BACKEND, choices=["scripted", "live"],
                     help="explicit backend for this run -- do not rely on the A2_BACKEND env var, "
                          "config.BACKEND is only read once at import time")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-metrics-log", action="store_true", help="skip all metrics/session logging for this run")
    args = ap.parse_args()

    person = metrics.get_person_name()

    labels = load_labels()
    case_ids = args.cases or list(labels.keys())
    missing = [c for c in case_ids if c not in STORE.claims]
    if missing:
        print(f"WARNING: not in claims.json (skipping): {missing}")
        case_ids = [c for c in case_ids if c in STORE.claims]

    rows = []
    per_case_pass = {}
    per_case_times = {}
    for cid in case_ids:
        label = labels.get(cid)
        if label is None:
            print(f"WARNING: {cid} has no label in expected_outcomes_A.json -- skipping")
            continue
        passes = []
        times = []
        for t in range(args.trials):
            run = loop.run_case(cid, autonomy=args.autonomy, model=args.model, backend=args.backend)
            ok = grade(run, label)
            passes.append(ok)
            times.append(run.wall_clock_seconds)
            rows.append({
                "case_id": cid, "trial": t, "pass": ok, "decision": run.decision,
                "trigger": run.trigger, "missing": run.missing, "turns": run.turns,
                "tokens_in": run.tokens_in, "tokens_out": run.tokens_out,
                "cost_usd": round(run.cost_usd, 5), "cost_is_measured": run.cost_is_measured,
                "guardrail_stop": run.guardrail_stop, "is_ghost_loop": bool(run.guardrail_stop) and run.guardrail_stop in metrics.GHOST_LOOP_TRIGGERS,
                "model": run.model, "wall_clock_seconds": run.wall_clock_seconds,
                "family": label.get("family"),
            })
            if not args.no_metrics_log:
                metrics.log_run(metrics.from_run_result(run, backend=args.backend, model=run.model, label_pass=ok))
            if args.verbose:
                mark = "PASS" if ok else "FAIL"
                print(f"[{mark}] {cid} trial {t}: {run.decision} (trigger={run.trigger}, missing={run.missing}), "
                      f"turns={run.turns}, cost=${run.cost_usd:.5f}, time={run.wall_clock_seconds:.2f}s")
        per_case_pass[cid] = sum(passes) / len(passes)
        per_case_times[cid] = sum(times) / len(times)

    os.makedirs("results", exist_ok=True)
    run_log_path = f"results/{metrics.safe_filename(person)}_run_log.json"
    with open(run_log_path, "w") as f:
        json.dump(rows, f, indent=2)

    n = len(rows)
    overall_pass = sum(r["pass"] for r in rows) / n if n else 0.0
    turns_list = [r["turns"] for r in rows]
    tokens_list = [r["tokens_in"] for r in rows]
    cost_list = [r["cost_usd"] for r in rows]
    time_list = [r["wall_clock_seconds"] for r in rows]

    model_used = args.model or (config.MODEL if args.backend == "live" else "scripted")

    print()
    print(f"Person: {person}   Backend: {args.backend}  Model: {model_used}  Autonomy: {args.autonomy}")
    print(f"Cases: {len(case_ids)}  Trials/case: {args.trials}  Total runs: {n}")
    print(f"Overall pass rate: {overall_pass:.1%}")
    if turns_list:
        print(f"Turns   -- median: {stats.median(turns_list)}  max: {max(turns_list)}")
        print(f"Tokens  -- mean input: {stats.mean(tokens_list):.0f}")
        print(f"Cost    -- mean: ${stats.mean(cost_list):.5f}  total: ${sum(cost_list):.5f}")
    if time_list:
        print(f"Time    -- mean per case-trial: {stats.mean(time_list):.3f}s   "
              f"total: {sum(time_list):.2f}s   max: {max(time_list):.3f}s")

    print()
    print("Per-case pass rate and average time:")
    for cid, rate in per_case_pass.items():
        fam = labels[cid].get("family", "")
        flag = "" if rate == 1.0 else "  <-- CHECK"
        print(f"  {cid:10s} {rate:5.0%}  {per_case_times[cid]:7.3f}s avg  ({fam}){flag}")

    print()
    print(f"Full run log written to {run_log_path}")

    if not args.no_metrics_log:
        session = metrics.build_session_summary(
            rows, person=person, backend=args.backend, model=model_used, autonomy=args.autonomy,
            cases_requested=len(case_ids), trials_per_case=args.trials,
        )
        metrics.log_session(session)
        metrics.write_comparison_report()
        print("Metrics appended to results/metrics_log.jsonl")
        print("Session logged to results/run_history.jsonl -- run `python3 main.py metrics` for the comparison report.")


if __name__ == "__main__":
    main()
