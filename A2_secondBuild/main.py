#!/usr/bin/env python3
"""
main.py -- the one entry point for the Problem A agent.

    python3 main.py eval                      # scripted backend, 1 trial, all cases
    python3 main.py eval --trials 3 --verbose
    python3 main.py eval --cases CLM-8888 CLM-8933
    python3 main.py run CLM-8888               # one case, full turn-by-turn trace
    python3 main.py failures                   # D7's two reproduced failures
    python3 main.py live --models anthropic/claude-3-5-haiku openai/gpt-4o-mini --cases CLM-8850
    python3 main.py metrics                    # the full logging/telemetry report (see below)
    python3 main.py check                      # sanity-check the data + code line up

Run with no arguments for the same thing as `eval` with defaults.

Every `eval` and `live` run -- scripted or real -- is appended to
results/metrics_log.jsonl (agent_a/metrics.py): number of loops (turns),
whether it was a ghost infinite loop (hit the step cap or the dedup guard
without ever reaching a decision), human agency (autonomy setting + whether
the gate was actually confirmed), human handovers (escalate/ask/approve
rates), accuracy against the label, $/task with model name and whether the
price is a real measured API cost or a tier estimate, and wall-clock time.
`python3 main.py metrics` prints the aggregate report and, once more than
one model has runs logged, a side-by-side per-model comparison table --
exactly the shape D5(b)'s "which model does your job at what cost, and
where they diverge" asks for.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eval_harness
from agent_a import loop, config, metrics, failures as failure_demos
from agent_a.data_io import STORE


def cmd_eval(args):
    if args.autonomy:
        loop.G.AUTONOMY_SETTING = args.autonomy
    sys.argv = ["eval_harness.py"]
    if args.cases:
        sys.argv += ["--cases", *args.cases]
    sys.argv += ["--trials", str(args.trials)]
    if args.verbose:
        sys.argv += ["--verbose"]
    eval_harness.main()


def cmd_run(args):
    r = loop.run_case(args.case_id, verbose=True)
    print(f"\n--- {args.case_id} ---")
    for line in r.trace:
        print(" ", line)
    print()
    print(f"decision:      {r.decision}")
    if r.trigger:
        print(f"trigger:       {r.trigger}")
    if r.missing:
        print(f"missing:       {r.missing}")
    if r.dispositions:
        print(f"lines:         {json.dumps(r.dispositions)}")
        print(f"approved:      {r.approved_total}   refused: {r.refused_total}")
    print(f"evidence:      {r.evidence}")
    print(f"model:         {r.model}")
    print(f"turns:         {r.turns}    ghost_loop: {bool(r.guardrail_stop) and r.guardrail_stop in metrics.GHOST_LOOP_TRIGGERS}")
    print(f"tokens:        in={r.tokens_in} out={r.tokens_out}   "
          f"cost: ${r.cost_usd:.5f} ({'measured' if r.cost_is_measured else 'estimate'})")
    print(f"wall clock:    {r.wall_clock_seconds}s")
    print(f"autonomy:      {r.autonomy}   gate_confirmed: {r.gate_confirmed}")
    if r.guardrail_stop:
        print(f"guardrail:     {r.guardrail_stop}")
    if r.ledger_line:
        print(f"ledger:        {json.dumps(r.ledger_line)}")


def cmd_failures(args):
    print("=== Failure 1: loop-control (broken vs fixed) ===")
    print("broken:", failure_demos.broken_run_case(args.case_id))
    print("fixed: ", failure_demos.fixed_run_case(args.case_id))
    print()
    print("=== Failure 2: tool-interface (get_claim_history v1 vs v2) ===")
    print(failure_demos.demo_failure_2())


def _have_openrouter_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return True
    this_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(this_dir)
    for candidate_dir in (this_dir, parent_dir):
        if candidate_dir not in sys.path:
            sys.path.insert(0, candidate_dir)
        try:
            import local_config
            if getattr(local_config, "OPENROUTER_API_KEY", None):
                return True
        except ImportError:
            continue
    return False


def cmd_live(args):
    if not _have_openrouter_key():
        print("ERROR: no OpenRouter key found. Either:")
        print("  export OPENROUTER_API_KEY=sk-or-...")
        print("or create a gitignored local_config.py with:")
        print('  OPENROUTER_API_KEY = "sk-or-..."')
        sys.exit(1)

    os.environ["A2_BACKEND"] = "live"   # harmless to keep set, but the real fix is passing --backend explicitly below
    for model in args.models:
        print(f"\n{'='*70}\nMODEL: {model}\n{'='*70}")
        sys.argv = ["eval_harness.py", "--backend", "live", "--trials", str(args.trials), "--model", model]
        if args.cases:
            sys.argv += ["--cases", *args.cases]
        if args.verbose:
            sys.argv += ["--verbose"]
        eval_harness.main()

    if len(args.models) > 1:
        print("\nRan multiple models -- see the per-model comparison below.")
        metrics.print_report()


def cmd_compare(args):
    metrics.print_comparison()


def cmd_metrics(args):
    rows = metrics.load_log()
    if args.model:
        rows = [r for r in rows if r["model"] == args.model]
    metrics.print_report(rows)
    print()
    metrics.print_comparison()


def cmd_check(args):
    from agent_a import data_io
    print(f"Person (from local_config.py 'name'): {metrics.get_person_name()}")
    print(f"Data dir:      {os.path.abspath(data_io.DATA_DIR)}")
    print(f"Claims loaded: {len(STORE.claims)}")
    labels = eval_harness.load_labels()
    print(f"Labels loaded: {len(labels)}")
    unlabelled = [c for c in STORE.claims if c not in labels]
    orphan_labels = [c for c in labels if c not in STORE.claims]
    if unlabelled:
        print(f"WARNING: {len(unlabelled)} claim(s) with no label: {unlabelled}")
    if orphan_labels:
        print(f"WARNING: {len(orphan_labels)} label(s) with no matching claim: {orphan_labels}")
    if not unlabelled and not orphan_labels:
        print("Every claim has a label and every label has a claim. Good to go.")
    print(f"Backend: {config.BACKEND}   Autonomy: {loop.G.AUTONOMY_SETTING}")
    print(f"OpenRouter key found: {_have_openrouter_key()}")
    n_logged = len(metrics.load_log())
    n_sessions = len(metrics.load_sessions())
    print(f"Metrics log rows so far: {n_logged}  ({metrics.LOG_PATH})")
    print(f"Sessions logged so far: {n_sessions}  ({metrics.SESSION_LOG_PATH})")


def main():
    ap = argparse.ArgumentParser(prog="main.py", description="PE6201 A2 -- Problem A agent")
    sub = ap.add_subparsers(dest="command")

    p_eval = sub.add_parser("eval", help="run the scripted evaluation harness (D4)")
    p_eval.add_argument("--cases", nargs="*", default=None)
    p_eval.add_argument("--trials", type=int, default=1)
    p_eval.add_argument("--autonomy", default=None, choices=["suggest", "confirm", "act"])
    p_eval.add_argument("--verbose", action="store_true")
    p_eval.set_defaults(func=cmd_eval)

    p_run = sub.add_parser("run", help="run and trace ONE case, turn by turn")
    p_run.add_argument("case_id")
    p_run.set_defaults(func=cmd_run)

    p_fail = sub.add_parser("failures", help="D7 -- reproduce both required failures")
    p_fail.add_argument("--case-id", dest="case_id", default="CLM-8888",
                         help="which case the loop-control demo targets (default: CLM-8888, an ask case)")
    p_fail.set_defaults(func=cmd_failures)

    p_live = sub.add_parser("live", help="D5(b) -- run the harness against one or more live OpenRouter models")
    p_live.add_argument("--models", nargs="+", default=["anthropic/claude-3-5-haiku"],
                         help="one or more OpenRouter model ids -- pass several for a real side-by-side battery")
    p_live.add_argument("--cases", nargs="*", default=None)
    p_live.add_argument("--trials", type=int, default=1)
    p_live.add_argument("--verbose", action="store_true")
    p_live.set_defaults(func=cmd_live)

    p_metrics = sub.add_parser("metrics", help="print the full metrics/telemetry report from results/metrics_log.jsonl")
    p_metrics.add_argument("--model", default=None, help="filter to one model's rows")
    p_metrics.set_defaults(func=cmd_metrics)

    p_compare = sub.add_parser("compare", help="print the run-history comparison (every session logged, and the best session per model)")
    p_compare.set_defaults(func=cmd_compare)

    p_check = sub.add_parser("check", help="sanity-check that data, labels and key setup line up")
    p_check.set_defaults(func=cmd_check)

    args = ap.parse_args()
    if not args.command:
        args = ap.parse_args(["eval"])
    args.func(args)


if __name__ == "__main__":
    main()
