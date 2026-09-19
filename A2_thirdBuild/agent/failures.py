"""D7 deterministic failure reproductions built from the working agent.

Both experiments call ``agent.loop.run_case`` on the scripted backend. The
broken and fixed runs differ by one controlled factor only:

* Failure 1 removes the terminal exit after a complete ``ask`` outcome.
* Failure 2 selects the deliberately broad V1 claim-history interface instead
  of the corrected V2 interface.

Normal callers are unaffected: fault injection defaults to ``None`` and is
rejected for the live backend. The dedicated D7 runner stores these reports
outside normal tester history so the experiment cannot contaminate D4/D5 data.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import statistics
import tempfile

from agent import loop
from data.data_io import STORE
from eval import eval_harness
from tool import tools as T


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D7_FIXTURES_PATH = os.path.join(PROJECT_ROOT, "data", "d7_fixtures.json")
DEFAULT_RESULTS_DIR = os.path.join(PROJECT_ROOT, "results", "d7")
LOOP_CASE_ID = "CLM-8888"
INTERFACE_CASE_ID = "D7-HISTORY-001"


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _approx_tokens(value):
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True)) // 4


def _result_dict(result):
    return result.as_dict()


def _pass_for(result, expected_decision, expected_trigger=None):
    if result.decision != expected_decision:
        return False
    if expected_trigger is not None and result.trigger != expected_trigger:
        return False
    return True


def _comparison(before, after, before_pass, after_pass):
    return {
        "decision": {"before": before.decision, "after": after.decision},
        "trigger": {"before": before.trigger, "after": after.trigger},
        "pass_rate_pct": {
            "before": 100.0 if before_pass else 0.0,
            "after": 100.0 if after_pass else 0.0,
        },
        "turns": {"before": before.turns, "after": after.turns},
        "tokens_in": {"before": before.tokens_in, "after": after.tokens_in},
        "tokens_out": {"before": before.tokens_out, "after": after.tokens_out},
        "estimated_cost_usd": {
            "before": before.cost_usd,
            "after": after.cost_usd,
        },
        "guardrail_stop": {
            "before": before.guardrail_stop,
            "after": after.guardrail_stop,
        },
    }


def _working_turn_distribution():
    """Measure legitimate turns across the complete 40-case evaluation set."""
    labels = eval_harness.load_labels()
    runs = []
    for case_id, label in labels.items():
        result = loop.run_case(case_id, backend="scripted")
        runs.append((case_id, result, eval_harness.grade(result, label)))
    turn_counts = [result.turns for _, result, _ in runs]
    worst_turns = max(turn_counts)
    return {
        "case_count": len(runs),
        "median_turns": statistics.median(turn_counts),
        "worst_turns": worst_turns,
        "worst_case_ids": [
            case_id for case_id, result, _ in runs if result.turns == worst_turns
        ],
        "step_cap_hits": sum(
            result.trigger == "step_cap_hit" for _, result, _ in runs
        ),
        "passing_cases": sum(passed for _, _, passed in runs),
        "pass_rate_pct": round(
            100 * sum(passed for _, _, passed in runs) / len(runs), 2
        ),
    }


def _load_d7_fixture(case_id):
    with open(D7_FIXTURES_PATH, encoding="utf-8") as handle:
        fixtures = json.load(handle)
    for fixture in fixtures:
        if fixture["claim_id"] == case_id:
            return dict(fixture)
    raise KeyError(f"D7 fixture not found: {case_id}")


@contextmanager
def _installed_claim_fixture(fixture):
    """Install one D7-only claim in memory, then restore the shared store."""
    case_id = fixture["claim_id"]
    previous = STORE.claims.get(case_id)
    STORE.claims[case_id] = dict(fixture)
    try:
        yield
    finally:
        if previous is None:
            STORE.claims.pop(case_id, None)
        else:
            STORE.claims[case_id] = previous


@contextmanager
def _isolated_decision_ledger():
    """Keep D7 approval writes out of the normal decision ledger."""
    original_path = T.LEDGER_PATH
    with tempfile.TemporaryDirectory(prefix="a2_d7_") as temp_dir:
        T.LEDGER_PATH = os.path.join(temp_dir, "decision_ledger.jsonl")
        try:
            yield
        finally:
            T.LEDGER_PATH = original_path


def run_failure_1():
    """Reproduce and fix the required loop-control failure."""
    expected_decision = "request_document"
    with _isolated_decision_ledger():
        before = loop.run_case(
            LOOP_CASE_ID,
            backend="scripted",
            d7_fault="omit_terminal_ask_exit",
        )
        after = loop.run_case(LOOP_CASE_ID, backend="scripted")
        turn_distribution = _working_turn_distribution()

    before_pass = _pass_for(before, expected_decision)
    after_pass = _pass_for(after, expected_decision)
    return {
        "schema_version": "1.0",
        "generated_at_utc": _utc_now(),
        "failure_id": "D7-F1",
        "title": "Loop control: omitted terminal ask exit",
        "controlled_layer": "code / loop control",
        "case_id": LOOP_CASE_ID,
        "backend": "scripted",
        "expected_decision": expected_decision,
        "single_deleted_element": (
            "The terminal return after resolve_lines produces a complete ask outcome."
        ),
        "failure_mechanism": (
            "The agent keeps re-reading a complete cached outcome and never returns it. "
            "No duplicate tool action occurs, so action de-duplication cannot detect this shape."
        ),
        "actual_catcher": "step cap",
        "working_agent_turn_distribution": turn_distribution,
        "why_other_controls_do_not_fix_root_cause": {
            "action_deduplication": "No tool is called twice; the loop re-reads cached state.",
            "budget_ceiling": "It is a later financial backstop, not the earliest control for this trajectory.",
            "prompt": "The scripted failure is a missing code transition, not a model-instruction problem.",
            "tool_interface": "All required observations are already correct and complete.",
        },
        "before": _result_dict(before),
        "after": _result_dict(after),
        "comparison": _comparison(before, after, before_pass, after_pass),
        "success_criteria": {
            "failure_reproduced": before.trigger == "step_cap_hit" and not before_pass,
            "working_behaviour_recovered": after_pass,
        },
    }


def run_failure_2():
    """Reproduce and fix the tool-interface cross-member history failure."""
    fixture = _load_d7_fixture(INTERFACE_CASE_ID)
    expected_decision = "approve_in_principle"
    original_version = T.TOOL_INTERFACE_VERSION

    try:
        with _installed_claim_fixture(fixture), _isolated_decision_ledger():
            T.configure_tool_interface("v1")
            v1_history = T.TOOL_REGISTRY["get_claim_history"](fixture["member_id"])
            before = loop.run_case(INTERFACE_CASE_ID, backend="scripted")

            T.configure_tool_interface("v2")
            v2_history = T.TOOL_REGISTRY["get_claim_history"](fixture["member_id"])
            after = loop.run_case(INTERFACE_CASE_ID, backend="scripted")
    finally:
        T.configure_tool_interface(original_version)

    before_pass = _pass_for(before, expected_decision)
    after_pass = _pass_for(after, expected_decision)
    report = {
        "schema_version": "1.0",
        "generated_at_utc": _utc_now(),
        "failure_id": "D7-F2",
        "title": "Tool interface: unfiltered cross-member claim history",
        "controlled_layer": "tool interface",
        "case_id": INTERFACE_CASE_ID,
        "backend": "scripted",
        "expected_decision": expected_decision,
        "single_deleted_element": (
            "V2 member filtering and bounded minimal return shape; V1 is the working tool without that shaping."
        ),
        "failure_mechanism": (
            "V1 exposes another member's superficially identical decided claim. "
            "The downstream exact-match helper relies on the tool's member-scoped contract and therefore "
            "misclassifies the new claim as a duplicate."
        ),
        "actual_fix": "Restore the V2 member filter and bounded five-record minimal response.",
        "why_other_layers_are_wrong": {
            "prompt": "A prompt reminder cannot enforce data minimisation or prevent cross-member disclosure.",
            "loop_control": "The loop terminates normally; the observation itself is wrong for the requested member.",
            "guardrail": "Blocking the resulting escalation would hide bad evidence rather than correct its source.",
        },
        "history_observation": {
            "v1_records_returned": len(v1_history["decided"]),
            "v2_records_returned": len(v2_history["decided"]),
            "v1_approx_tokens": _approx_tokens(v1_history),
            "v2_approx_tokens": _approx_tokens(v2_history),
        },
        "before": _result_dict(before),
        "after": _result_dict(after),
        "comparison": _comparison(before, after, before_pass, after_pass),
        "success_criteria": {
            "failure_reproduced": (
                before.decision == "escalate"
                and before.trigger == "duplicate_claim"
                and not before_pass
            ),
            "working_behaviour_recovered": after_pass,
        },
    }
    v1_tokens = report["history_observation"]["v1_approx_tokens"]
    v2_tokens = report["history_observation"]["v2_approx_tokens"]
    report["history_observation"]["token_reduction_pct"] = round(
        (1 - v2_tokens / v1_tokens) * 100, 2
    ) if v1_tokens else 0.0
    return report


def write_json_atomic(path, payload):
    """Publish a complete JSON file without exposing a partial result."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="d7_", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise
