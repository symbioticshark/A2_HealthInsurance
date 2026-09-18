#!/usr/bin/env python3
"""View the latest result by default, or select any compatible session."""
import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import local_settings
from eval import metrics, session_results


def _tester_dir():
    name = metrics.get_person_name()
    return os.path.join(PROJECT_ROOT, "results", metrics.safe_filename(name))


def choose_session(sessions, prompt="Select run: "):
    if not sessions:
        print("No completed sessions are available.")
        return None
    for index, session in enumerate(sessions, 1):
        print(f"  {index}. {session_results.session_label(session, include_tester=True)}")
    print("  B. Back")
    while True:
        raw = input(prompt).strip().upper()
        if raw == "B":
            return None
        try:
            return sessions[int(raw) - 1]
        except (ValueError, IndexError):
            print("Please enter a listed number or B.")


def print_session(session):
    print("=" * 110)
    print("DETAILED RESULT")
    print("=" * 110)
    print(f"Session: {session.get('session_id')}")
    print(f"When: {session.get('ts_iso')}   Tester: {session.get('person')}")
    print(
        f"Model: {session.get('model')}   Backend: {session.get('backend')}   "
        f"Tool: {str(session.get('tool_interface_version', '?')).upper()}   Mode: {session.get('run_mode')}"
    )
    print(
        f"Cases: {session.get('cases_requested')}   Runs: {session.get('total_case_trials')}   "
        f"Pass: {session.get('pass_rate_pct')}%   Cost: ${session.get('total_cost_usd', 0):.5f}   "
        f"Tokens: {session.get('total_tokens', 0):,}"
    )
    print(
        f"Data: {session.get('_mapping_status')} | detail: {session.get('_detail_level')}"
    )
    rows = session.get("_rows", [])
    if not rows:
        print("\nNo case-level rows could be matched safely for this legacy session.")
        return
    print()
    print(f"{'Case':<11}{'Trial':>6}  {'Pass':<5}  {'Decision':<24}{'Trigger / missing':<42}{'Tokens':>9}{'Cost':>11}")
    print("-" * 110)
    for row in rows:
        detail = row.get("trigger") or row.get("missing") or ""
        tokens = row.get("tokens_in", 0) + row.get("tokens_out", 0)
        passed = row.get("pass")
        pass_text = "PASS" if passed is True else "FAIL" if passed is False else "n/a"
        print(
            f"{str(row.get('case_id', '')):<11}{int(row.get('trial') or 0) + 1:>6}  "
            f"{pass_text:<5}  {str(row.get('decision') or row.get('actual_decision') or ''):<24}"
            f"{str(detail)[:40]:<42}{tokens:>9,}${row.get('cost_usd', 0):>10.5f}"
        )
    if session.get("_detail_level") != "full_latest_snapshot":
        print("\nLegacy note: numeric case metrics are available; overwritten trace/evidence is unavailable.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id")
    parser.add_argument("--select", action="store_true", help="Show a numbered session list")
    args = parser.parse_args(argv)
    sessions = sorted(
        session_results.load_tester_sessions(_tester_dir()),
        key=lambda row: row.get("ts", 0), reverse=True,
    )
    if not sessions:
        print("No completed result is available for this tester.")
        return 1
    if args.session_id:
        selected = session_results.session_by_id(sessions, args.session_id)
        if not selected:
            print(f"Session not found: {args.session_id}")
            return 1
    elif args.select:
        selected = choose_session(sessions)
        if not selected:
            return 0
    else:
        selected = sessions[0]
    print_session(selected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
