#!/usr/bin/env python3
"""Run either or both deterministic D7 failure reproductions."""
import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from agent import failures


def _metric(report, name):
    values = report["comparison"][name]
    return values["before"], values["after"]


def _print_trace(label, result):
    print(f"\n{label} trace:")
    for item in result["trace"]:
        print(f"  - {item}")


def _print_report(report, path):
    print("\n" + "=" * 78)
    print(f"{report['failure_id']} | {report['title']}")
    print("=" * 78)
    print(f"Controlled layer : {report['controlled_layer']}")
    print(f"Case             : {report['case_id']}")
    print(f"Backend          : {report['backend']} (no API key, no live cost)")
    print(f"Expected decision: {report['expected_decision']}")
    print(f"Single deletion  : {report['single_deleted_element']}")
    print(f"Failure mechanism: {report['failure_mechanism']}")

    print("\nBefore vs after:")
    print(f"  {'Metric':<24}{'Broken':<22}{'Fixed'}")
    print(f"  {'-' * 66}")
    for key, label in (
        ("decision", "Decision"),
        ("trigger", "Trigger"),
        ("pass_rate_pct", "Pass rate (%)"),
        ("turns", "Turns"),
        ("tokens_in", "Input tokens"),
        ("tokens_out", "Output tokens"),
        ("estimated_cost_usd", "Estimated cost (USD)"),
        ("guardrail_stop", "Guardrail stop"),
    ):
        before, after = _metric(report, key)
        print(f"  {label:<24}{str(before):<22}{after}")

    if "history_observation" in report:
        obs = report["history_observation"]
        print("\nTool observation evidence:")
        print(f"  V1 records / approx tokens: {obs['v1_records_returned']} / {obs['v1_approx_tokens']}")
        print(f"  V2 records / approx tokens: {obs['v2_records_returned']} / {obs['v2_approx_tokens']}")
        print(f"  Approximate token reduction: {obs['token_reduction_pct']}%")

    if "working_agent_turn_distribution" in report:
        dist = report["working_agent_turn_distribution"]
        print("\nWorking-agent turn distribution across the evaluation set:")
        print(f"  Cases / passing cases: {dist['case_count']} / {dist['passing_cases']}")
        print(f"  Median / worst turns : {dist['median_turns']} / {dist['worst_turns']}")
        print(f"  Runs hitting step cap: {dist['step_cap_hits']}")
        print(f"  Worst-case IDs       : {', '.join(dist['worst_case_ids'])}")

    _print_trace("Broken", report["before"])
    _print_trace("Fixed", report["after"])
    criteria = report["success_criteria"]
    print("\nChecks:")
    print(f"  Failure reproduced         : {'PASS' if criteria['failure_reproduced'] else 'FAIL'}")
    print(f"  Working behaviour recovered: {'PASS' if criteria['working_behaviour_recovered'] else 'FAIL'}")
    print(f"\nSaved detailed result: {path}")


def _run_one(number, output_dir):
    if number == "1":
        report = failures.run_failure_1()
        filename = "failure_1_loop_control.json"
    else:
        report = failures.run_failure_2()
        filename = "failure_2_tool_interface.json"
    path = os.path.join(output_dir, filename)
    failures.write_json_atomic(path, report)
    _print_report(report, path)
    if not all(report["success_criteria"].values()):
        raise RuntimeError(f"{report['failure_id']} did not meet its success criteria")
    return report, path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run deterministic D7 broken/fixed experiments on the scripted backend."
    )
    parser.add_argument(
        "--failure", choices=("1", "2", "all"), default="all",
        help="run loop failure 1, tool-interface failure 2, or both (default: all)",
    )
    parser.add_argument(
        "--output-dir", default=failures.DEFAULT_RESULTS_DIR,
        help="directory for atomic JSON reports",
    )
    args = parser.parse_args(argv)
    output_dir = os.path.abspath(args.output_dir)

    selected = ("1", "2") if args.failure == "all" else (args.failure,)
    completed = []
    for number in selected:
        report, path = _run_one(number, output_dir)
        completed.append(report)

    if args.failure == "all":
        summary = {
            "schema_version": "1.0",
            "purpose": "D7 two deterministic reproduced failures",
            "experiments": completed,
        }
        summary_path = os.path.join(output_dir, "d7_summary.json")
        failures.write_json_atomic(summary_path, summary)
        print("\n" + "=" * 78)
        print("D7 COMPLETE")
        print("=" * 78)
        print("Both failures reproduced and both working behaviours recovered.")
        print(f"Combined atomic report: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
