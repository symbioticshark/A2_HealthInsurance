#!/usr/bin/env python3
"""
D2(c) -- measures what NOT batching Turn 2's independent calls (and Turn
3's preauth chase) actually costs, on our own 40-case evaluation set.

Runs the full standard battery (24 ordinary x1, 16 negative x3 = 72 runs)
on the scripted backend three times -- no network, no key, all free:

  1. PARALLEL           -- the current default. Independent calls batched
                            into one turn each, under the real STEP_CAP.
  2. SEQUENTIAL (fair)   -- the exact same calls, same order, one call per
                            turn, with the step cap temporarily raised so
                            the run can finish. This is the honest
                            turns/tokens/cost comparison D2(c) asks for --
                            decision, trigger and missing must come out
                            IDENTICAL to the parallel run, because nothing
                            about the decision logic reads the turn number.
  3. SEQUENTIAL (as shipped) -- same one-call-per-turn spreading, but under
                            our REAL STEP_CAP. Reports how many cases would
                            be wrongly escalated (step_cap_hit) simply
                            because they were never parallelised -- this is
                            a finding in its own right, not a bug in this
                            script.

Usage:
    python3 measure_parallel_vs_sequential.py

Writes parallel_vs_sequential_report.json alongside this file.
"""
import json
import os
import statistics as stats
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from eval import eval_harness, metrics
from agent import guardrails as G
from agent import loop
from tool import tools as T

# Comfortably above the worst-case sequential turn count on this data set
# (get_claim + up to ~4 independent Turn-2 calls per line + preauth calls +
# the gate) -- only used for the "fair" comparison run, never for "as
# shipped". See RunResult.trace if you need to confirm no run is silently
# truncated below its natural turn count.
_UNCAPPED_STEP_CAP = 40


def _run_battery(parallel: bool):
    labels = eval_harness.load_labels()
    trial_counts = eval_harness.standard_trial_counts(labels)
    rows = []
    for case_id, label in labels.items():
        for trial in range(trial_counts[case_id]):
            result = loop.run_case(case_id, backend="scripted", parallel=parallel)
            rows.append({
                "case_id": case_id,
                "trial": trial,
                "pass": eval_harness.grade(result, label),
                "turns": result.turns,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "cost_usd": result.cost_usd,
                "decision": result.decision,
                "trigger": result.trigger,
                "missing": result.missing,
                "guardrail_stop": result.guardrail_stop,
            })
    return rows


def _summarise(rows, label):
    turns = [r["turns"] for r in rows]
    tokens_in = sum(r["tokens_in"] for r in rows)
    tokens_out = sum(r["tokens_out"] for r in rows)
    cost = sum(r["cost_usd"] for r in rows)
    passed = sum(r["pass"] for r in rows)
    step_cap_hits = sum(1 for r in rows if r["guardrail_stop"] == "step_cap_hit")
    return {
        "label": label,
        "total_runs": len(rows),
        "median_turns": stats.median(turns),
        "max_turns": max(turns),
        "total_tokens_in": tokens_in,
        "total_tokens_out": tokens_out,
        "total_tokens": tokens_in + tokens_out,
        "total_cost_usd": round(cost, 6),
        "passed": passed,
        "pass_rate_pct": round(100 * passed / len(rows), 1),
        "step_cap_hits": step_cap_hits,
    }


def _correctness_diff(rows_a, rows_b):
    """Pairs rows by (case_id, trial) and reports any (decision, trigger,
    missing) mismatch. Both batteries iterate cases/trials in the same
    load_labels() order, so zipping directly is safe."""
    mismatches = []
    for a, b in zip(rows_a, rows_b):
        key_a = (a["decision"], a["trigger"], a["missing"])
        key_b = (b["decision"], b["trigger"], b["missing"])
        if key_a != key_b:
            mismatches.append({
                "case_id": a["case_id"], "trial": a["trial"],
                "a": key_a, "b": key_b,
            })
    return mismatches


def _print_row(metric, seq_val, par_val, fmt):
    if isinstance(seq_val, (int, float)) and isinstance(par_val, (int, float)) and seq_val:
        saving = f"{(1 - par_val / seq_val) * 100:+.1f}%"
    else:
        saving = "-"
    print(f"{metric:<16}{fmt.format(seq_val):>16}{fmt.format(par_val):>16}{saving:>12}")


def main():
    # This script calls loop.run_case() directly (not eval_harness's
    # transactional run_evaluation()), so any "approve_in_principle"
    # outcome here would otherwise write real ledger lines straight into
    # the SHARED results/decision_ledger.jsonl -- three full batteries'
    # worth of noise, every time this script runs. Redirect it to a
    # throwaway temp file for the duration instead.
    original_ledger_path = T.LEDGER_PATH
    scratch_dir = tempfile.mkdtemp(prefix="parallel_vs_sequential_")
    T.LEDGER_PATH = os.path.join(scratch_dir, "decision_ledger.jsonl")

    try:
        return _main()
    finally:
        T.LEDGER_PATH = original_ledger_path


def _main():
    print("Running PARALLEL (current default, real STEP_CAP) ...")
    parallel_rows = _run_battery(parallel=True)

    print("Running SEQUENTIAL, fair comparison (STEP_CAP temporarily raised) ...")
    original_cap = G.STEP_CAP
    G.STEP_CAP = _UNCAPPED_STEP_CAP
    try:
        sequential_fair_rows = _run_battery(parallel=False)
    finally:
        G.STEP_CAP = original_cap

    print("Running SEQUENTIAL, as shipped (real STEP_CAP) ...")
    sequential_shipped_rows = _run_battery(parallel=False)

    parallel_summary = _summarise(parallel_rows, "parallel")
    sequential_fair_summary = _summarise(sequential_fair_rows, "sequential_fair")
    sequential_shipped_summary = _summarise(sequential_shipped_rows, "sequential_as_shipped")

    print()
    print("=== D2(c): sequential (fair) vs parallel -- same STEP_CAP-free comparison ===")
    print(f"{'Metric':<16}{'Sequential':>16}{'Parallel':>16}{'Saving':>12}")
    _print_row("median turns", sequential_fair_summary["median_turns"], parallel_summary["median_turns"], "{:.1f}")
    _print_row("max turns", sequential_fair_summary["max_turns"], parallel_summary["max_turns"], "{:d}")
    _print_row("total tokens", sequential_fair_summary["total_tokens"], parallel_summary["total_tokens"], "{:,}")
    _print_row("total cost", sequential_fair_summary["total_cost_usd"], parallel_summary["total_cost_usd"], "${:.5f}")
    print(f"{'pass rate':<16}{sequential_fair_summary['pass_rate_pct']:>15.1f}%{parallel_summary['pass_rate_pct']:>15.1f}%{'-':>12}")

    mismatches = _correctness_diff(parallel_rows, sequential_fair_rows)
    if mismatches:
        print(f"\nCorrectness check: DIFFERS on {len(mismatches)} run(s) -- investigate before reporting:")
        for m in mismatches[:10]:
            print(f"  {m['case_id']} trial {m['trial']}: parallel={m['a']} sequential={m['b']}")
    else:
        print("\nCorrectness check: IDENTICAL on every run -- correctness did not move.")

    print()
    print(f"=== Bonus finding: sequential execution under our REAL STEP_CAP={G.STEP_CAP} ===")
    print(f"Runs wrongly escalated as step_cap_hit: {sequential_shipped_summary['step_cap_hits']} "
          f"/ {sequential_shipped_summary['total_runs']}")
    print(f"Pass rate collapses to: {sequential_shipped_summary['pass_rate_pct']}% "
          f"(vs {parallel_summary['pass_rate_pct']}% parallel)")
    print("This is not a bug in this script -- it is the real behaviour our shipped guardrail")
    print("would show if Turn 2/3 were never batched: cases needing more than 6 calls simply")
    print("cannot finish before the step cap fires, and get escalated for the wrong reason.")

    report = {
        "parallel": parallel_summary,
        "sequential_fair_comparison": sequential_fair_summary,
        "sequential_as_shipped": sequential_shipped_summary,
        "correctness_mismatches": mismatches,
    }
    out_path = os.path.join(PROJECT_ROOT, "results", "parallel_vs_sequential_report.json")
    metrics.atomic_write_json(out_path, report)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
