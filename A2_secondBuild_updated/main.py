#!/usr/bin/env python3
"""Main command-line and interactive entry point for the Problem A agent."""
import argparse
import getpass
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import eval_harness
from agent_a import config, cost_model, failures as failure_demos
from agent_a import live_backend, local_settings, loop, metrics, tools
from agent_a.data_io import STORE

MENU_WIDTH = 72


def _rule(character="-"):
    print(character * MENU_WIDTH)


def _user_results_dir(name=None):
    name = name or metrics.get_person_name()
    return os.path.join(HERE, "results", metrics.safe_filename(name))


def _configure_user_results(name=None):
    directory = _user_results_dir(name)
    metrics.configure_paths(directory)
    tools.LEDGER_PATH = os.path.join(directory, "decision_ledger.jsonl")
    return directory


def _prompt_choice(prompt, valid):
    valid = {str(item).upper() for item in valid}
    while True:
        answer = input(prompt).strip().upper()
        if answer in valid:
            return answer
        print(f"Please choose one of: {', '.join(sorted(valid))}")


def _prompt_int(prompt, default=1, minimum=1):
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            value = int(raw)
            if value >= minimum:
                return value
        except ValueError:
            pass
        print(f"Please enter a whole number of at least {minimum}.")


def _save_config(updates):
    local_settings.save_local_config(updates)


def _ensure_profile():
    current = local_settings.load_local_config()
    updates = {}
    if not current.get("name"):
        while True:
            name = input("Tester name: ").strip()
            if name:
                updates["name"] = name
                break
            print("Tester name cannot be empty.")
    if not current.get("default_model"):
        updates["default_model"] = config.MODEL
    if updates:
        _save_config(updates)
    name = local_settings.get_local_config_value("name", "anonymous")
    _configure_user_results(name)
    interface_version = local_settings.get_local_config_value("tool_interface_version", "v2")
    try:
        tools.configure_tool_interface(interface_version)
    except ValueError:
        tools.configure_tool_interface("v2")
    return name


def _configure_api_key(force=False):
    existing = bool(live_backend.get_api_key())
    if existing and not force:
        return True
    while True:
        key = getpass.getpass("OpenRouter API key (input hidden, B to go back): ").strip()
        if key.upper() == "B":
            return False
        if key:
            _save_config({"OPENROUTER_API_KEY": key})
            return True
        print("API key cannot be empty.")


def _history_models():
    models = set(metrics.get_model_prices())
    for row in metrics.load_sessions():
        model = row.get("model")
        if model and model != "scripted":
            models.add(model)
    return sorted(models)


def _price_from_official_model(details):
    pricing = details.get("pricing") or {}
    try:
        return float(pricing["prompt"]) * 1_000_000, float(pricing["completion"]) * 1_000_000
    except (KeyError, TypeError, ValueError):
        return None


def _prompt_price(label, default=None):
    default_text = f" [{default:g}]" if default is not None else ""
    while True:
        raw = input(f"{label} in USD per 1M tokens{default_text}: ").strip()
        if not raw and default is not None:
            return float(default)
        try:
            value = float(raw)
            if value >= 0:
                return value
        except ValueError:
            pass
        print("Price must be a non-negative number.")


def _add_custom_model():
    if not _configure_api_key():
        return None
    while True:
        model_id = input("OpenRouter model ID in provider/model-name format (B to go back): ").strip()
        if model_id.upper() == "B":
            return None
        try:
            details = live_backend.lookup_model(model_id)
            canonical = details.get("id") or details.get("canonical_slug") or model_id
            print(f"Model found: {details.get('name', canonical)}")
            print(f"Canonical ID: {canonical}")
            official = _price_from_official_model(details)
            if official:
                print(f"OpenRouter price: input ${official[0]:g}, output ${official[1]:g} per 1M tokens")
            input_price = _prompt_price("Input price", official[0] if official else None)
            output_price = _prompt_price("Output price", official[1] if official else None)
            print(f"Save {canonical}: input ${input_price:g}, output ${output_price:g} per 1M tokens?")
            if _prompt_choice("Y/N: ", {"Y", "N"}) == "N":
                continue
            catalog = local_settings.get_local_config_value("MODEL_CATALOG", {}) or {}
            catalog = dict(catalog)
            catalog[canonical] = {
                "input_price_usd_per_million": input_price,
                "output_price_usd_per_million": output_price,
                "price_source": "user_confirmed",
            }
            _save_config({"MODEL_CATALOG": catalog, "default_model": canonical})
            return canonical
        except KeyboardInterrupt:
            print("\nModel setup cancelled.")
            return None
        except Exception as exc:
            print(f"Model validation failed: {exc}")


def _select_model():
    models = _history_models()
    try:
        refreshed = metrics.set_remote_model_prices(
            live_backend.list_models(), allowed_models=models
        )
        if refreshed:
            print(f"Updated prices for {refreshed} listed model(s) from OpenRouter.")
        models = _history_models()
    except Exception as exc:
        print(f"OpenRouter model catalog unavailable; using saved prices. ({exc})")
    default_model = local_settings.get_local_config_value("default_model", config.MODEL)
    print("\nAvailable models:")
    for index, model in enumerate(models, 1):
        marker = " (default)" if model == default_model else ""
        price = metrics.model_price_details(model)
        price_text = ""
        if price:
            price_text = (
                f" | input ${price['input_price_usd_per_million']:g}, "
                f"output ${price['output_price_usd_per_million']:g} per 1M tokens"
            )
        print(f"  {index}. {model}{marker}{price_text}")
    print(f"  {len(models) + 1}. Add a model")
    print("  B. Back")
    while True:
        answer = input("Select model: ").strip()
        if answer.upper() == "B":
            return None
        try:
            selected = int(answer)
            if 1 <= selected <= len(models):
                model = models[selected - 1]
                if not metrics.model_price_details(model):
                    print("This historical model has no confirmed price. Add it again to confirm pricing.")
                    continue
                _save_config({"default_model": model})
                return model
            if selected == len(models) + 1:
                return _add_custom_model()
        except ValueError:
            pass
        print("Please select a listed number or B.")


def _estimate_live_cost(model, total_runs):
    results_root = os.path.join(HERE, "results")
    interface_version = tools.TOOL_INTERFACE_VERSION
    rows = [
        row for row in metrics.load_all_metrics(results_root)
        if row.get("backend") == "live"
    ]
    same_model = [row for row in rows if row.get("model") == model]
    api_cost_rows = [
        row for row in same_model
        if row.get("cost_source") == "openrouter_usage"
        and row.get("tool_interface_version", "v2") == interface_version
    ]
    if api_cost_rows:
        mean_cost = sum(row.get("cost_usd", 0.0) for row in api_cost_rows) / len(api_cost_rows)
        return mean_cost * total_runs, "same-model OpenRouter cost history"

    observed = []
    for result in metrics.load_all_key_results(results_root):
        environment = result.get("environment", {})
        summary = result.get("summary", {})
        if environment.get("model") != model:
            continue
        if environment.get("tool_interface_version", "v2") != interface_version:
            continue
        balance_change = environment.get("observed_balance_change_usd")
        run_count = summary.get("total_runs")
        if balance_change is not None and run_count:
            observed.append((float(balance_change), int(run_count)))
    if observed:
        mean_cost = sum(cost for cost, _ in observed) / sum(count for _, count in observed)
        return mean_cost * total_runs, "same-model observed balance history"

    if same_model:
        mean_cost = sum(row.get("cost_usd", 0.0) for row in same_model) / len(same_model)
        return mean_cost * total_runs, "same-model legacy cost history"
    if rows:
        mean_input = sum(row.get("tokens_in", 0) for row in rows) / len(rows)
        mean_output = sum(row.get("tokens_out", 0) for row in rows) / len(rows)
        cost_per_run, _ = metrics.price_for_model(model, mean_input, mean_output)
        return cost_per_run * total_runs, "all-model token-volume history"

    mean_input, mean_output = cost_model.estimate_tokens_for_run(4)
    cost_per_run, _ = metrics.price_for_model(model, mean_input, mean_output)
    return cost_per_run * total_runs, "scripted four-turn fallback"


def _display_balance(balance, label):
    if balance.get("available"):
        source = balance.get("source", "OpenRouter")
        print(f"{label}: ${balance['balance']:.5f} ({source})")
    else:
        print(f"{label}: unavailable ({balance.get('reason', 'unknown reason')})")


def _update_balance_after(result_path, after_balance):
    with open(result_path, encoding="utf-8") as handle:
        result = json.load(handle)
    environment = result["environment"]
    if after_balance.get("available"):
        environment["balance_after_usd"] = round(after_balance["balance"], 8)
        environment["balance_after_source"] = after_balance.get("source")
        before = environment.get("balance_before_usd")
        if before is not None:
            observed_change = before - after_balance["balance"]
            environment["observed_balance_change_usd"] = round(observed_change, 8)
            api_cost = result.get("summary", {}).get("total_cost_usd")
            if api_cost is not None:
                environment["cost_reconciliation_difference_usd"] = round(
                    float(api_cost) - observed_change, 8
                )
    else:
        environment["balance_after_usd"] = None
        environment["balance_after_status"] = after_balance.get("reason")
    metrics.atomic_write_json(result_path, result)
    return result


def _run_live(cases, trials, run_mode, trial_counts=None):
    if not _configure_api_key():
        return None
    interface_version = _select_tool_interface()
    if not interface_version:
        print("Live run cancelled before model selection.")
        return None
    model = _select_model()
    if not model:
        return None
    try:
        details = live_backend.lookup_model(model)
        print(f"Model availability confirmed: {details.get('name', model)}")
    except Exception as exc:
        print(f"The selected model is not currently available through OpenRouter: {exc}")
        print("No API run was started.")
        return None
    effective_counts = {
        case_id: int((trial_counts or {}).get(case_id, trials)) for case_id in cases
    }
    total_runs = sum(effective_counts.values())
    estimated_cost, estimate_basis = _estimate_live_cost(model, total_runs)
    before = live_backend.get_credit_balance()
    print()
    _rule("=")
    print("RUN PREVIEW")
    _rule()
    print(f"Model: {model}")
    print(f"Mode: {run_mode}")
    print(f"Tool interface: {tools.TOOL_INTERFACE_VERSION.upper()}")
    print(f"Selected cases: {len(cases)}")
    plan_counts = {}
    for value in effective_counts.values():
        plan_counts[value] = plan_counts.get(value, 0) + 1
    for trial_count, case_count in sorted(plan_counts.items()):
        print(f"Case repetitions: {case_count} case(s) x {trial_count} trial(s)")
    print(f"Total model runs: {total_runs}")
    if run_mode in {"negative", "standard_battery"}:
        print("Negative selection: expected decision is not approve_in_principle")
    _display_balance(before, "Balance before")
    print(f"Estimated cost: ${estimated_cost:.5f} ({estimate_basis})")
    if before.get("available"):
        print(f"Projected balance after: ${before['balance'] - estimated_cost:.5f}")
    _rule()
    if _prompt_choice("Start this run? Y/N: ", {"Y", "N"}) == "N":
        print("Run cancelled before execution.")
        return None

    context = {
        "balance_before_usd": round(before["balance"], 8) if before.get("available") else None,
        "balance_before_status": "available" if before.get("available") else before.get("reason"),
        "balance_before_source": before.get("source"),
        "estimated_cost_before_run_usd": round(estimated_cost, 8),
        "estimate_basis": estimate_basis,
        "projected_balance_after_run_usd": round(before["balance"] - estimated_cost, 8) if before.get("available") else None,
    }
    result = eval_harness.run_evaluation(
        cases=cases, trials=trials, backend="live", model=model,
        verbose=True, run_mode=run_mode, balance_context=context,
        trial_counts=trial_counts,
    )
    if result:
        after = live_backend.get_credit_balance()
        saved_result = _update_balance_after(result["result_path"], after)
        _display_balance(after, "Balance after")
        if before.get("available") and after.get("available"):
            print(f"Observed balance change: ${before['balance'] - after['balance']:.5f}")
        cost_basis = saved_result["environment"].get("cost_basis")
        if cost_basis == "openrouter_usage":
            cost_label = "OpenRouter-reported run cost"
        elif cost_basis == "partial_or_unavailable":
            cost_label = "Known partial run cost (one or more request costs unavailable)"
        else:
            cost_label = "Fallback calculated run cost"
        print(f"{cost_label}: ${result['session']['total_cost_usd']:.5f}")
        difference = saved_result["environment"].get("cost_reconciliation_difference_usd")
        if difference is not None:
            print(f"Cost reconciliation difference: ${difference:+.5f}")
    return result


def _parse_case_selection(labels):
    case_ids = list(labels)
    print("\nCases:")
    for index, case_id in enumerate(case_ids, 1):
        label = labels[case_id]
        print(f"  {index:2d}. {case_id} | {label.get('family', '')} | {label['expected_decision']}")
    print("Enter one number, comma-separated numbers, or a range such as 1-5. Enter B to go back.")
    while True:
        raw = input("Select cases: ").strip()
        if raw.upper() == "B":
            return None
        selected = set()
        try:
            for part in raw.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = (int(value.strip()) for value in part.split("-", 1))
                    selected.update(range(start, end + 1))
                else:
                    selected.add(int(part))
            if selected and min(selected) >= 1 and max(selected) <= len(case_ids):
                return [case_ids[index - 1] for index in sorted(selected)]
        except ValueError:
            pass
        print("Invalid selection. Use listed numbers only.")


def cmd_eval(args):
    argv = ["--backend", "scripted", "--trials", str(args.trials), "--run-mode", "all"]
    if args.cases:
        argv.extend(["--cases", *args.cases])
    if args.autonomy:
        argv.extend(["--autonomy", args.autonomy])
    if args.verbose:
        argv.append("--verbose")
    if args.tool_interface:
        argv.extend(["--tool-interface", args.tool_interface])
    if args.standard_battery:
        argv.append("--standard-battery")
    return eval_harness.main(argv)


def cmd_run(args):
    result = loop.run_case(args.case_id, verbose=True)
    print(f"\n--- {args.case_id} ---")
    for line in result.trace:
        print(f"  {line}")
    print(f"Decision: {result.decision}")
    print(f"Trigger: {result.trigger}")
    print(f"Missing: {result.missing}")
    print(f"Evidence: {result.evidence}")
    print(f"Model: {result.model}")
    print(f"Turns: {result.turns}")
    print(f"Tokens: input={result.tokens_in}, output={result.tokens_out}")
    print(f"Cost: ${result.cost_usd:.5f} ({'measured' if result.cost_is_measured else 'estimated'})")
    print(f"Wall clock: {result.wall_clock_seconds}s")


def cmd_failures(args):
    print("=== Failure 1: loop control ===")
    print("Broken:", failure_demos.broken_run_case(args.case_id))
    print("Fixed: ", failure_demos.fixed_run_case(args.case_id))
    print("\n=== Failure 2: tool interface v1 versus v2 ===")
    print(failure_demos.demo_failure_2())


def cmd_live(args):
    if not _configure_api_key():
        return None
    for model in args.models:
        argv = [
            "--backend", "live", "--trials", str(args.trials),
            "--model", model, "--run-mode", "custom" if args.cases else "all",
        ]
        if args.cases:
            argv.extend(["--cases", *args.cases])
        if args.verbose:
            argv.append("--verbose")
        eval_harness.main(argv)


def cmd_check(_args=None):
    from agent_a import data_io
    labels = eval_harness.load_labels()
    unlabelled = [case_id for case_id in STORE.claims if case_id not in labels]
    orphan_labels = [case_id for case_id in labels if case_id not in STORE.claims]
    print(f"App version: {config.APP_VERSION}")
    print(f"Tester: {metrics.get_person_name()}")
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Data directory: {os.path.abspath(data_io.DATA_DIR)}")
    print(f"Claims: {len(STORE.claims)}   Labels: {len(labels)}")
    expected_counts = {
        decision: sum(1 for label in labels.values() if label.get("expected_decision") == decision)
        for decision in ("approve_in_principle", "request_document", "escalate")
    }
    print(
        "Expected outcomes: "
        f"approve {expected_counts['approve_in_principle']}, "
        f"request document {expected_counts['request_document']}, "
        f"escalate {expected_counts['escalate']}"
    )
    print(f"Expected negative cases: {len(eval_harness.expected_negative_case_ids(labels))}")
    print(f"Data issues: {len(unlabelled) + len(orphan_labels)}")
    print(f"Default model: {local_settings.get_local_config_value('default_model', config.MODEL)}")
    print(f"Tool interface: {tools.TOOL_INTERFACE_VERSION.upper()}")
    print(f"OpenRouter API key configured: {bool(live_backend.get_api_key())}")
    print(f"Results directory: {_configure_user_results()}")


def cmd_metrics(args):
    _configure_user_results()
    rows = metrics.load_log()
    if args.model:
        rows = [row for row in rows if row.get("model") == args.model]
    metrics.print_report(rows)
    print()
    metrics.print_comparison()


def cmd_compare(_args=None):
    _configure_user_results()
    metrics.print_comparison()


def _select_tool_interface():
    print()
    _rule("=")
    print("TOOL INTERFACE VERSION")
    _rule()
    print("  1. V1 - experimental failure version: unfiltered, uncapped history")
    print("  2. V2 - corrected version: member-filtered history, maximum 5 records")
    print("  B. Back")
    choice = _prompt_choice("Select version: ", {"1", "2", "B"})
    if choice == "B":
        return None
    version = "v1" if choice == "1" else "v2"
    if version == "v1":
        print("V1 is intentionally defective and may produce incorrect decisions.")
        if _prompt_choice("Use V1 for an experiment? Y/N: ", {"Y", "N"}) == "N":
            return None
    tools.configure_tool_interface(version)
    _save_config({"tool_interface_version": version})
    print(f"Tool interface switched to {version.upper()}.")
    return version


def _comparison_menu():
    while True:
        print()
        _rule("=")
        print("RESULT COMPARISON")
        _rule()
        print("  1. My run history")
        print("  2. All testers and shared baseline")
        print("  B. Back")
        choice = _prompt_choice("Select comparison: ", {"1", "2", "B"})
        if choice == "B":
            return
        print()
        if choice == "1":
            metrics.print_comparison()
        else:
            sessions = metrics.load_all_sessions(os.path.join(HERE, "results"))
            metrics.print_comparison(sessions)


def _show_latest_result():
    name = metrics.get_person_name()
    path = os.path.join(_user_results_dir(name), f"{metrics.safe_filename(name)}_result.json")
    if not os.path.isfile(path):
        print("No completed result is available for this tester.")
        return
    with open(path, encoding="utf-8") as handle:
        result = json.load(handle)
    environment = result["environment"]
    summary = result["summary"]
    print()
    _rule("=")
    print("LATEST RESULT")
    _rule()
    print(f"File: {path}")
    print(f"Run: {environment['run_id']} | {environment['timestamp']}")
    print(f"Model: {environment['model']} | Backend: {environment['backend']} | Mode: {environment['run_mode']}")
    print(f"Tool interface: {environment.get('tool_interface_version', 'v2').upper()}")
    print(f"Runs: {summary['total_runs']} | Accuracy: {summary['accuracy_pct']}% | Failures: {summary['failed_runs']}")
    print(
        f"Tokens: {summary['total_tokens']:,} | Cost: ${summary['total_cost_usd']:.5f} "
        f"({environment.get('cost_basis', 'unknown')}) | "
        f"Time: {summary['total_wall_clock_seconds']:.2f}s"
    )
    observed = environment.get("observed_balance_change_usd")
    if observed is not None:
        print(f"Observed balance change: ${observed:.5f}")


def _configuration_menu():
    while True:
        print("\nConfiguration")
        print("  1. Change tester name")
        print("  2. Change API key")
        print("  3. Select or add model")
        print("  B. Back")
        choice = _prompt_choice("Select: ", {"1", "2", "3", "B"})
        if choice == "B":
            return
        if choice == "1":
            name = input("Tester name: ").strip()
            if name:
                _save_config({"name": name})
                _configure_user_results(name)
        elif choice == "2":
            _configure_api_key(force=True)
        else:
            _select_model()


def _live_run_menu(labels, negative_cases):
    while True:
        standard_plan = eval_harness.standard_trial_counts(labels)
        print()
        _rule("=")
        print("LIVE RUN MODE")
        _rule()
        print(f"  1. Quick validation: {len(labels)} cases x 1 = {len(labels)} runs")
        print(
            f"  2. Standard battery: {len(labels) - len(negative_cases)} ordinary x 1 + "
            f"{len(negative_cases)} negative x 3 = {sum(standard_plan.values())} runs"
        )
        print(f"  3. Negative only: {len(negative_cases)} cases x 3 = {len(negative_cases) * 3} runs")
        print("  4. Select cases and repetitions")
        print("  B. Back")
        choice = _prompt_choice("Select live mode: ", {"1", "2", "3", "4", "B"})
        if choice == "B":
            return
        if choice == "1":
            _run_live(list(labels), 1, "quick_validation")
        elif choice == "2":
            _run_live(
                list(labels), 1, "standard_battery", trial_counts=standard_plan,
            )
        elif choice == "3":
            _run_live(negative_cases, 3, "negative")
        else:
            cases = _parse_case_selection(labels)
            if cases:
                trials = _prompt_int("Runs for EACH selected case [press Enter for 1]: ", 1)
                _run_live(cases, trials, "custom")
        return


def interactive_menu():
    name = _ensure_profile()
    labels = eval_harness.load_labels()
    negative_cases = eval_harness.expected_negative_case_ids(labels)
    while True:
        print()
        _rule("=")
        print(
            f"PE6201 A2 Agent {config.APP_VERSION} | Tester: {name} | "
            f"Tool interface: {tools.TOOL_INTERFACE_VERSION.upper()}"
        )
        _rule()
        print("  A. Check environment, data, and configuration")
        print("  B. Scripted standard battery: ordinary x 1, negative x 3")
        print("  C. Live run: choose quick, standard, negative, or custom")
        print("  D. View latest result")
        print("  E. Compare results")
        print("  F. Change tester, API key, or default model")
        print("  Q. Exit")
        try:
            choice = _prompt_choice("Select: ", set("ABCDEFQ"))
            if choice == "Q":
                print("Goodbye.")
                return
            if choice == "A":
                cmd_check()
            elif choice == "B":
                trial_plan = eval_harness.standard_trial_counts(labels)
                print(
                    f"Starting the standard battery: {len(labels) - len(negative_cases)} ordinary x 1 plus "
                    f"{len(negative_cases)} negative x 3 = {sum(trial_plan.values())} runs."
                )
                eval_harness.run_evaluation(
                    trials=1, backend="scripted", verbose=True,
                    run_mode="standard_battery", trial_counts=trial_plan,
                )
            elif choice == "C":
                _live_run_menu(labels, negative_cases)
            elif choice == "D":
                _show_latest_result()
            elif choice == "E":
                _comparison_menu()
            elif choice == "F":
                _configuration_menu()
                name = metrics.get_person_name()
        except KeyboardInterrupt:
            print("\nOperation cancelled. Returning to the main menu.")


def build_parser():
    parser = argparse.ArgumentParser(prog="main.py", description="PE6201 A2 Problem A agent")
    sub = parser.add_subparsers(dest="command")
    eval_parser = sub.add_parser("eval")
    eval_parser.add_argument("--cases", nargs="*", default=None)
    eval_parser.add_argument("--trials", type=int, default=1)
    eval_parser.add_argument("--autonomy", default=None, choices=["suggest", "confirm", "act"])
    eval_parser.add_argument("--verbose", action="store_true")
    eval_parser.add_argument("--tool-interface", choices=["v1", "v2"], default=None)
    eval_parser.add_argument("--standard-battery", action="store_true")
    eval_parser.set_defaults(func=cmd_eval)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("case_id")
    run_parser.set_defaults(func=cmd_run)
    failure_parser = sub.add_parser("failures")
    failure_parser.add_argument("--case-id", default="CLM-8888")
    failure_parser.set_defaults(func=cmd_failures)
    live_parser = sub.add_parser("live")
    live_parser.add_argument("--models", nargs="+", default=[config.MODEL])
    live_parser.add_argument("--cases", nargs="*", default=None)
    live_parser.add_argument("--trials", type=int, default=1)
    live_parser.add_argument("--verbose", action="store_true")
    live_parser.set_defaults(func=cmd_live)
    metrics_parser = sub.add_parser("metrics")
    metrics_parser.add_argument("--model", default=None)
    metrics_parser.set_defaults(func=cmd_metrics)
    compare_parser = sub.add_parser("compare")
    compare_parser.set_defaults(func=cmd_compare)
    check_parser = sub.add_parser("check")
    check_parser.set_defaults(func=cmd_check)
    return parser


def main():
    if len(sys.argv) == 1:
        interactive_menu()
        return
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        interactive_menu()
        return
    _ensure_profile()
    args.func(args)


if __name__ == "__main__":
    main()
