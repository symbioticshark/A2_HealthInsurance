#!/usr/bin/env python3
"""Detailed two-session comparison using existing result history only."""
import argparse
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from eval import metrics, session_results
from run.view_result import choose_session


def _tester_dir():
    return os.path.join(PROJECT_ROOT, "results", metrics.safe_filename(metrics.get_person_name()))


def _public_session(session):
    return {key: value for key, value in session.items() if not key.startswith("_")}


def available_sessions(all_testers=False):
    if all_testers:
        return session_results.load_all_sessions(os.path.join(PROJECT_ROOT, "results"))
    return sorted(
        session_results.load_tester_sessions(_tester_dir()),
        key=lambda row: row.get("ts", 0), reverse=True,
    )


def build_report(left, right):
    comparison = session_results.compare_sessions(left, right)
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "report_type": "detailed_two_session_comparison",
        "left_session": _public_session(left),
        "right_session": _public_session(right),
        **comparison,
    }


def save_report(report, filename="detailed_comparison.json"):
    output_dir = _tester_dir()
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, filename)
    metrics.atomic_write_json(path, report)
    return path


def print_report(report, left_label="LEFT", right_label="RIGHT"):
    left = report["left_session"]
    right = report["right_session"]
    print("=" * 106)
    print("DETAILED TWO-SESSION COMPARISON")
    print("=" * 106)
    print(f"{left_label}:  {session_results.session_label(left)}")
    print(f"{right_label}: {session_results.session_label(right)}")
    warnings = report.get("compatibility_warnings") or []
    if warnings:
        print("Warnings: " + "; ".join(warnings))
    changes = report.get("changes", {})
    print(
        "Changes: "
        f"fail->pass {changes.get('fail_to_pass', 0)}, "
        f"pass->fail {changes.get('pass_to_fail', 0)}, "
        f"both pass {changes.get('both_pass', 0)}, "
        f"both fail {changes.get('both_fail', 0)}"
    )
    print()
    print(f"{'Case':<11}{'Trial':>6}  {'Outcome':<14}{left_label + ' result':<29}{right_label + ' result':<29}{'Token Δ':>10}")
    print("-" * 106)
    for item in report.get("case_comparisons", []):
        left_row = item.get("left") or {}
        right_row = item.get("right") or {}
        left_text = f"{left_row.get('decision') or left_row.get('actual_decision') or '-'} ({left_row.get('pass')})"
        right_text = f"{right_row.get('decision') or right_row.get('actual_decision') or '-'} ({right_row.get('pass')})"
        delta = item.get("token_delta_right_minus_left")
        delta_text = "n/a" if delta is None else f"{delta:+,}"
        print(
            f"{str(item.get('case_id', '')):<11}{int(item.get('trial') or 0) + 1:>6}  "
            f"{item.get('outcome', ''):<14}{left_text[:27]:<29}{right_text[:27]:<29}{delta_text:>10}"
        )


def _resolve_selection(sessions, session_id, prompt):
    if session_id:
        selected = session_results.session_by_id(sessions, session_id)
        if not selected:
            raise ValueError(f"session not found: {session_id}")
        return selected
    print(prompt)
    return choose_session(sessions)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-session")
    parser.add_argument("--right-session")
    parser.add_argument("--all-testers", action="store_true")
    args = parser.parse_args(argv)
    sessions = available_sessions(args.all_testers)
    if len(sessions) < 2:
        print("At least two completed sessions are required.")
        return 1
    try:
        left = _resolve_selection(sessions, args.left_session, "\nSelect the first run:")
        if not left:
            return 0
        remaining = [item for item in sessions if item.get("session_id") != left.get("session_id")]
        right = _resolve_selection(remaining, args.right_session, "\nSelect the second run:")
        if not right:
            return 0
    except ValueError as exc:
        print(exc)
        return 1
    report = build_report(left, right)
    print_report(report)
    path = save_report(report)
    print(f"\nSaved derived report: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
