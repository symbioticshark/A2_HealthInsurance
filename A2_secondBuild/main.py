#!/usr/bin/env python3
"""
main.py -- the one entry point for the Problem A agent.

    python3 main.py eval                      # scripted backend, 1 trial, all cases
    python3 main.py eval --trials 3 --verbose
    python3 main.py eval --cases CLM-8888 CLM-8933
    python3 main.py run CLM-8888               # one case, full turn-by-turn trace
    python3 main.py failures                   # D7's two reproduced failures
    python3 main.py live --model anthropic/claude-3-5-haiku --cases CLM-8850
    python3 main.py check                      # sanity-check the data + code line up

Run with no arguments for the same thing as `eval` with defaults.

This does not replace eval_harness.py -- it wraps it, plus the two other
things you actually run by hand during A2 (a single traced case, and the
D7 failure demo), behind one command so nobody on the team needs to
remember three different invocations or where results/ ends up.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from local_config import OPENROUTER_API_KEY

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eval_harness
from agent_a import loop, config, failures as failure_demos
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
    print(f"decision:   {r.decision}")
    if r.trigger:
        print(f"trigger:    {r.trigger}")
    if r.missing:
        print(f"missing:    {r.missing}")
    if r.dispositions:
        print(f"lines:      {json.dumps(r.dispositions)}")
        print(f"approved:   {r.approved_total}   refused: {r.refused_total}")
    print(f"evidence:   {r.evidence}")
    print(f"turns:      {r.turns}    cost: ${r.cost_usd:.5f}")
    if r.ledger_line:
        print(f"ledger:     {json.dumps(r.ledger_line)}")


def cmd_failures(args):
    print("=== Failure 1: loop-control (broken vs fixed) ===")
    print("broken:", failure_demos.broken_run_case(args.case_id))
    print("fixed: ", failure_demos.fixed_run_case(args.case_id))
    print()
    print("=== Failure 2: tool-interface (get_claim_history v1 vs v2) ===")
    print(failure_demos.demo_failure_2())


def cmd_live(args):
    os.environ["A2_BACKEND"] = "live"
    os.environ["A2_MODEL"] = args.model
    has_key = os.environ.get("OPENROUTER_API_KEY")
    if not has_key:
        
        try:
            has_key = OPENROUTER_API_KEY
            
        except ImportError:
            pass
    if not has_key:
        print("ERROR: set OPENROUTER_API_KEY first, e.g.:")
        print("  export OPENROUTER_API_KEY=sk-or-...")
        sys.exit(1)


def cmd_check(args):
    from agent_a import data_io
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

    p_live = sub.add_parser("live", help="D5(b) -- run the harness against a live OpenRouter model")
    p_live.add_argument("--model", default="anthropic/claude-3-5-haiku")
    p_live.add_argument("--cases", nargs="*", default=None)
    p_live.add_argument("--trials", type=int, default=1)
    p_live.add_argument("--verbose", action="store_true")
    p_live.set_defaults(func=cmd_live)

    p_check = sub.add_parser("check", help="sanity-check that data and labels line up")
    p_check.set_defaults(func=cmd_check)

    args = ap.parse_args()
    if not args.command:
        args = ap.parse_args(["eval"])
    args.func(args)


if __name__ == "__main__":
    main()
