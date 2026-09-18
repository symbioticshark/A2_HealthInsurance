#!/usr/bin/env python3
"""Detailed comparison of compatible V1 and V2 evaluation sessions."""
import argparse
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from eval import eval_harness, metrics, session_results
from eval.measure_v1_v2_tool_tokens import build_report as build_tool_token_report
from run import compare_sessions


def _pair_key(session):
    return (
        session.get("model"), session.get("backend"),
        tuple(session.get("case_ids") or []),
        tuple(sorted((session.get("trial_plan") or {}).items())),
        session.get("total_case_trials"),
    )


def compatible_pairs(sessions):
    complete = [
        s for s in sessions
        if len(s.get("_rows", [])) == int(s.get("total_case_trials") or 0)
    ]
    v1 = [s for s in complete if str(s.get("tool_interface_version", "")).lower() == "v1"]
    v2 = [s for s in complete if str(s.get("tool_interface_version", "")).lower() == "v2"]
    pairs = [(left, right) for left in v1 for right in v2 if _pair_key(left) == _pair_key(right)]
    return sorted(pairs, key=lambda pair: max(pair[0].get("ts", 0), pair[1].get("ts", 0)), reverse=True)


def _negative_summary(session):
    negative_ids = set(eval_harness.expected_negative_case_ids(eval_harness.load_labels()))
    rows = [row for row in session.get("_rows", []) if row.get("case_id") in negative_ids]
    passed = sum(row.get("pass") is True for row in rows)
    return {
        "runs": len(rows),
        "passed": passed,
        "pass_rate": round(passed / len(rows), 4) if rows else None,
    }


def build_report(v1, v2):
    report = compare_sessions.build_report(v1, v2)
    report["report_type"] = "detailed_v1_v2_comparison"
    report["v1_session_id"] = v1.get("session_id")
    report["v2_session_id"] = v2.get("session_id")
    report["v1_negative_cases"] = _negative_summary(v1)
    report["v2_negative_cases"] = _negative_summary(v2)
    report["tool_return_measurement"] = build_tool_token_report()
    report["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    report["compatibility_warnings"] = session_results.compatibility_issues(v1, v2, v1_v2=True)
    return report


def save_report(report):
    return compare_sessions.save_report(report, "v1_v2_detailed_comparison.json")


def _print_pair(index, pair):
    v1, v2 = pair
    print(f"  {index}. {v1.get('model')} | {v1.get('backend')} | "
          f"{v1.get('cases_requested')} cases/{v1.get('total_case_trials')} runs")
    print(f"     V1 {v1.get('ts_iso')} | pass {v1.get('pass_rate_pct')}% | ...{str(v1.get('session_id'))[-12:]}")
    print(f"     V2 {v2.get('ts_iso')} | pass {v2.get('pass_rate_pct')}% | ...{str(v2.get('session_id'))[-12:]}")


def choose_pair(pairs):
    if not pairs:
        print("No compatible V1/V2 session pair is available.")
        return None
    print("\nSelect a compatible V1/V2 pair:")
    for index, pair in enumerate(pairs, 1):
        _print_pair(index, pair)
    print("  B. Back")
    while True:
        raw = input("Select pair: ").strip().upper()
        if raw == "B":
            return None
        try:
            return pairs[int(raw) - 1]
        except (ValueError, IndexError):
            print("Please enter a listed number or B.")


def compare_pair(v1, v2, save=True):
    report = build_report(v1, v2)
    compare_sessions.print_report(report, "V1", "V2")
    neg1, neg2 = report["v1_negative_cases"], report["v2_negative_cases"]
    if neg1["pass_rate"] is not None and neg2["pass_rate"] is not None:
        print(f"Negative-case pass: V1 {neg1['pass_rate']:.1%} | V2 {neg2['pass_rate']:.1%}")
    tool = report["tool_return_measurement"]
    print(f"Mean get_claim_history return tokens: V1 {tool['mean_tokens_v1']:.1f} | "
          f"V2 {tool['mean_tokens_v2']:.1f} | reduction {tool['mean_reduction_pct_v2_vs_v1']:.1f}%")
    if save:
        path = save_report(report)
        print(f"\nSaved derived V1/V2 report: {path}")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-session")
    parser.add_argument("--v2-session")
    parser.add_argument("--all-testers", action="store_true")
    args = parser.parse_args(argv)
    sessions = compare_sessions.available_sessions(args.all_testers)
    pairs = compatible_pairs(sessions)
    if args.v1_session or args.v2_session:
        if not args.v1_session or not args.v2_session:
            parser.error("--v1-session and --v2-session must be supplied together")
        v1 = session_results.session_by_id(sessions, args.v1_session)
        v2 = session_results.session_by_id(sessions, args.v2_session)
        if not v1 or not v2:
            print("One or both session IDs were not found.")
            return 1
        issues = session_results.compatibility_issues(v1, v2, v1_v2=True)
        if issues:
            print("Sessions are not a valid V1/V2 pair: " + "; ".join(issues))
            return 1
        pair = (v1, v2)
    else:
        pair = choose_pair(pairs)
        if not pair:
            return 0
    compare_pair(*pair)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
