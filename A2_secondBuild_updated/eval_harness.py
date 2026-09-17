#!/usr/bin/env python3
"""Outcome-based, multi-trial evaluation with transactional result files."""
import argparse
import json
import os
import statistics as stats
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from agent_a import config, local_settings, loop, metrics, tools
from agent_a.data_io import STORE

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS_PATH = os.path.join(HERE, "expected_outcomes_A.json")


def load_labels():
    with open(LABELS_PATH, encoding="utf-8") as handle:
        return {item["case_id"]: item for item in json.load(handle)}


def expected_negative_case_ids(labels=None):
    labels = labels or load_labels()
    return [
        case_id for case_id, label in labels.items()
        if label["expected_decision"] != "approve_in_principle"
    ]


def standard_trial_counts(labels=None):
    labels = labels or load_labels()
    return {
        case_id: 1 if label["expected_decision"] == "approve_in_principle" else 3
        for case_id, label in labels.items()
    }


def grade(run: loop.RunResult, label: dict) -> bool:
    if run.decision != label["expected_decision"]:
        return False
    if label["expected_decision"] == "escalate" and "trigger" in label:
        return run.trigger == label["trigger"]
    if label["expected_decision"] == "request_document" and "missing" in label:
        import re
        expected_code = re.search(r"\b\d{4,5}[A-Z]?\b", label["missing"])
        if expected_code and run.missing:
            return expected_code.group(0) in run.missing
    return True


def _progress_bar(completed, total, width=20):
    filled = max(1, int(width * completed / total)) if total and completed else 0
    return f"[{'#' * filled}{'-' * (width - filled)}] {completed}/{total}"


def _print_summary(rows, person, backend, model, autonomy, case_ids, trial_counts, interface_version):
    count = len(rows)
    pass_rate = sum(row["pass"] for row in rows) / count if count else 0.0
    turns = [row["turns"] for row in rows]
    input_tokens = sum(row["tokens_in"] for row in rows)
    output_tokens = sum(row["tokens_out"] for row in rows)
    costs = [row["cost_usd"] for row in rows]
    durations = [row["wall_clock_seconds"] for row in rows]

    print()
    print(
        f"Tester: {person}   Backend: {backend}   Model: {model}   "
        f"Tool interface: {interface_version.upper()}   Autonomy: {autonomy}"
    )
    plan_counts = {}
    for value in trial_counts.values():
        plan_counts[value] = plan_counts.get(value, 0) + 1
    plan_text = "; ".join(
        f"{case_count} case(s) x {trial_count} trial(s)"
        for trial_count, case_count in sorted(plan_counts.items())
    )
    print(f"Cases: {len(case_ids)}   Trial plan: {plan_text}   Total runs: {count}")
    print(f"Overall pass rate: {pass_rate:.1%}")
    if turns:
        print(f"Turns: median {stats.median(turns)}   maximum {max(turns)}")
        print(f"Tokens: input {input_tokens:,}   output {output_tokens:,}   total {input_tokens + output_tokens:,}")
        cost_sources = sorted({row.get("cost_source", "estimated") for row in rows})
        print(
            f"Cost: mean ${stats.mean(costs):.5f}   total ${sum(costs):.5f}   "
            f"source {', '.join(cost_sources)}"
        )
        print(f"Time: mean {stats.mean(durations):.3f}s   total {sum(durations):.2f}s   maximum {max(durations):.3f}s")


def run_evaluation(cases=None, trials=1, autonomy=None, model=None,
                   backend="scripted", verbose=False, run_mode="all",
                   balance_context=None, persist=True, tool_interface=None,
                   trial_counts=None):
    autonomy = autonomy or loop.G.AUTONOMY_SETTING
    interface_version = tool_interface or local_settings.get_local_config_value(
        "tool_interface_version", "v2"
    )
    interface_version = tools.configure_tool_interface(interface_version)
    labels = load_labels()
    case_ids = list(cases) if cases else list(labels.keys())
    missing = [case_id for case_id in case_ids if case_id not in STORE.claims]
    if missing:
        print(f"WARNING: cases not found in claims data and skipped: {missing}")
        case_ids = [case_id for case_id in case_ids if case_id in STORE.claims]
    unknown_labels = [case_id for case_id in case_ids if case_id not in labels]
    if unknown_labels:
        print(f"WARNING: cases without labels and skipped: {unknown_labels}")
        case_ids = [case_id for case_id in case_ids if case_id in labels]
    if not case_ids:
        raise ValueError("No valid cases were selected")
    if trials < 1:
        raise ValueError("Trials must be at least 1")
    effective_trial_counts = {
        case_id: int((trial_counts or {}).get(case_id, trials)) for case_id in case_ids
    }
    if any(value < 1 for value in effective_trial_counts.values()):
        raise ValueError("Every selected case must have at least one trial")
    total_planned_runs = sum(effective_trial_counts.values())

    person = metrics.get_person_name()
    safe_person = metrics.safe_filename(person)
    permanent_dir = os.path.join(HERE, "results", safe_person)
    run_id = f"{int(time.time())}-{os.getpid()}"
    staging_dir = metrics.begin_transaction(permanent_dir, run_id)
    original_ledger_path = tools.LEDGER_PATH
    metrics.configure_paths(staging_dir)
    tools.LEDGER_PATH = os.path.join(staging_dir, "decision_ledger.jsonl")

    rows = []
    per_case_pass = {}
    per_case_times = {}
    model_used = model or (config.MODEL if backend == "live" else "scripted")
    try:
        for case_id in case_ids:
            label = labels[case_id]
            passes = []
            durations = []
            case_trials = effective_trial_counts[case_id]
            for trial in range(case_trials):
                try:
                    run = loop.run_case(
                        case_id, autonomy=autonomy, model=model,
                        backend=backend, verbose=verbose,
                    )
                except Exception as exc:
                    # A live provider/network/format failure belongs to this
                    # trial, not to every trial after it.  Record a failed run
                    # and continue so the final report exposes instability
                    # instead of disappearing with a traceback halfway through.
                    run = loop.RunResult(
                        case_id=case_id,
                        autonomy=autonomy,
                        model=model_used,
                        decision=None,
                        trigger="run_error",
                        guardrail_stop="run_error",
                        trace=[f"unhandled {type(exc).__name__}: {exc}"],
                        cost_is_measured=False,
                        cost_source="unavailable",
                    )
                passed = grade(run, label)
                passes.append(passed)
                durations.append(run.wall_clock_seconds)
                row = {
                    "case_id": case_id,
                    "family": label.get("family"),
                    "trial": trial,
                    "expected_decision": label["expected_decision"],
                    "pass": passed,
                    "decision": run.decision,
                    "trigger": run.trigger,
                    "missing": run.missing,
                    "dispositions": run.dispositions,
                    "approved_total": run.approved_total,
                    "refused_total": run.refused_total,
                    "turns": run.turns,
                    "tokens_in": run.tokens_in,
                    "tokens_out": run.tokens_out,
                    "cached_input_tokens": run.cached_input_tokens,
                    "cache_write_tokens": run.cache_write_tokens,
                    "reasoning_tokens": run.reasoning_tokens,
                    "cost_usd": round(run.cost_usd, 8),
                    "cost_is_measured": run.cost_is_measured,
                    "cost_source": run.cost_source,
                    "guardrail_stop": run.guardrail_stop,
                    "is_ghost_loop": bool(run.guardrail_stop) and run.guardrail_stop in metrics.GHOST_LOOP_TRIGGERS,
                    "model": run.model,
                    "backend": backend,
                    "run_mode": run_mode,
                    "tool_interface_version": interface_version,
                    "tester": person,
                    "wall_clock_seconds": run.wall_clock_seconds,
                    "evidence": run.evidence,
                    "trace": run.trace,
                    "gate": run.gate,
                    "gate_confirmed": run.gate_confirmed,
                }
                rows.append(row)
                if persist:
                    metrics.log_run(metrics.from_run_result(
                        run, backend=backend, model=run.model, label_pass=passed,
                        tool_interface_version=interface_version,
                    ))
                if verbose:
                    mark = "PASS" if passed else "FAIL"
                    completed = len(rows)
                    total_runs = total_planned_runs
                    print(
                        f"{_progress_bar(completed, total_runs)} [{mark}] "
                        f"{case_id} trial {trial + 1}/{case_trials}: {run.decision} "
                        f"(trigger={run.trigger}, missing={run.missing}), turns={run.turns}, "
                        f"tokens={run.tokens_in + run.tokens_out}, cost=${run.cost_usd:.5f}, "
                        f"time={run.wall_clock_seconds:.2f}s"
                    )
            per_case_pass[case_id] = sum(passes) / len(passes)
            per_case_times[case_id] = sum(durations) / len(durations)

        run_log_filename = f"{safe_person}_run_log.json"
        metrics.atomic_write_json(os.path.join(staging_dir, run_log_filename), rows)
        unique_trial_counts = set(effective_trial_counts.values())
        uniform_trials = next(iter(unique_trial_counts)) if len(unique_trial_counts) == 1 else None
        trial_plan = {}
        for value in effective_trial_counts.values():
            trial_plan[str(value)] = trial_plan.get(str(value), 0) + 1
        session = metrics.build_session_summary(
            rows, person=person, backend=backend, model=model_used,
            autonomy=autonomy, cases_requested=len(case_ids),
            trials_per_case=uniform_trials, run_mode=run_mode,
            trial_plan=trial_plan,
        )
        if persist:
            metrics.log_session(session)
        key_result = metrics.build_key_result(
            rows, session, config.APP_VERSION, len(STORE.claims), balance_context,
        )
        result_filename = f"{safe_person}_result.json"
        metrics.atomic_write_json(os.path.join(staging_dir, result_filename), key_result)

        _print_summary(
            rows, person, backend, model_used, autonomy, case_ids,
            effective_trial_counts,
            interface_version,
        )
        print()
        print("Per-case pass rate and average time:")
        for case_id in case_ids:
            flag = "" if per_case_pass[case_id] == 1.0 else "  <-- CHECK"
            print(
                f"  {case_id:10s} {per_case_pass[case_id]:5.0%}  "
                f"{per_case_times[case_id]:7.3f}s avg  ({labels[case_id].get('family', '')}){flag}"
            )

        metrics.commit_transaction(staging_dir, permanent_dir)
        metrics.configure_paths(permanent_dir)
        if persist:
            metrics.write_comparison_report()
        print()
        print(f"Results committed to {permanent_dir}")
        print(f"Key result: {os.path.join(permanent_dir, result_filename)}")
        return {"rows": rows, "session": session.as_dict(), "result_path": os.path.join(permanent_dir, result_filename)}
    except KeyboardInterrupt:
        metrics.rollback_transaction(staging_dir, permanent_dir)
        print("\nRun cancelled. Incomplete results were rolled back.")
        return None
    except BaseException:
        metrics.rollback_transaction(staging_dir, permanent_dir)
        raise
    finally:
        tools.LEDGER_PATH = original_ledger_path
        metrics.configure_paths(permanent_dir)


def main(argv=None, context=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", nargs="*", default=None)
    parser.add_argument("--negative-only", action="store_true")
    parser.add_argument("--standard-battery", action="store_true")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--autonomy", default=loop.G.AUTONOMY_SETTING)
    parser.add_argument("--model", default=None)
    parser.add_argument("--backend", default=config.BACKEND, choices=["scripted", "live"])
    parser.add_argument("--run-mode", default="all")
    parser.add_argument("--tool-interface", choices=["v1", "v2"], default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-metrics-log", action="store_true")
    args = parser.parse_args(argv)
    labels = load_labels()
    cases = expected_negative_case_ids(labels) if args.negative_only else args.cases
    trial_counts = None
    if args.standard_battery:
        cases = args.cases or list(labels)
        full_plan = standard_trial_counts(labels)
        trial_counts = {case_id: full_plan[case_id] for case_id in cases}
    run_mode = "standard_battery" if args.standard_battery else (
        "negative" if args.negative_only else args.run_mode
    )
    return run_evaluation(
        cases=cases, trials=args.trials, autonomy=args.autonomy,
        model=args.model, backend=args.backend, verbose=args.verbose,
        run_mode=run_mode, balance_context=context,
        persist=not args.no_metrics_log, tool_interface=args.tool_interface,
        trial_counts=trial_counts,
    )


if __name__ == "__main__":
    main()
