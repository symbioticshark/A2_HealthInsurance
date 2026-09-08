"""
D1 + D2(c) + D3(a) -- the agent loop.

One agent, one control loop: Thought -> Action(one or more tool calls) ->
Observation -> repeat -> Final. This module is the same for every backend;
BACKEND="scripted" drives it from scripted_backend.py's rule table,
BACKEND="live" drives it from an actual model's text output via
live_backend.py. Either way, every tool call goes through the SAME
tool_registry, SAME guardrails, SAME ledger, SAME cost accounting -- so a
loop-control failure or a guardrail catch means the same thing regardless
of which backend produced the action.
"""
import time
from dataclasses import dataclass, field

from . import config
from .data_io import STORE
from . import tools as T
from . import guardrails as G
from . import scripted_backend as S
from . import cost_model as C


@dataclass
class RunResult:
    case_id: str
    decision: str = None            # "approve_in_principle" | "request_document" | "escalate"
    trigger: str = None             # for escalate
    missing: str = None             # for request_document
    dispositions: list = field(default_factory=list)
    approved_total: int = 0
    refused_total: int = 0
    evidence: list = field(default_factory=list)
    autonomy: str = None
    gate: str = None
    turns: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    guardrail_stop: str = None      # set if a guardrail, not the routing table, ended the run
    ledger_line: dict = None
    trace: list = field(default_factory=list)   # human-readable per-turn log, for D7 instrumentation

    def as_dict(self):
        return {k: v for k, v in self.__dict__.items()}


def _record_calls(result: RunResult, calls, already_called: set):
    """Guardrail pass over a batch of calls before any of them execute:
    dedup check first (cheapest, catches the loop-control failure), then
    each call is added to the seen-set. Does not execute anything -- that
    happens in the caller so a GuardrailStop here aborts the whole batch,
    not a partial batch."""
    sigs = []
    for name, kwargs in calls:
        sig = f"{name}({kwargs})"
        G.check_dedup(sig, already_called)
        sigs.append(sig)
    already_called.update(sigs)
    return sigs


def run_case(claim_id: str, autonomy: str = G.AUTONOMY_SETTING, auto_confirm: bool = True,
             backend: str = None, verbose: bool = False) -> RunResult:
    """Runs ONE trial of ONE case, start to finish, from a clean state (D4
    isolation -- nothing here reads any other run's output)."""
    backend = backend or config.BACKEND
    result = RunResult(case_id=claim_id, autonomy=autonomy)
    already_called = set()
    turn = 0
    memory = {"claim": None, "policy": None, "hospital": None, "history": None,
              "coverage": {}, "preauth": {}}

    def execute(name, kwargs):
        fn = T.TOOL_REGISTRY[name]
        try:
            out = fn(**kwargs)
        except T.ToolError as e:
            out = {"error": str(e)}
        except T.ProcedureNotFoundError as e:
            out = {"error": str(e)}
        result.evidence.append(name)
        return out

    try:
        # ---- Turn 1: get_claim, alone -----------------------------------
        turn += 1
        G.check_step_cap(turn)
        _record_calls(result, [("get_claim", {"claim_id": claim_id})], already_called)
        claim = execute("get_claim", {"claim_id": claim_id})
        if "error" in claim:
            raise G.GuardrailStop("bad_claim_id", claim["error"])
        memory["claim"] = claim
        result.trace.append(f"turn {turn}: get_claim -> {len(claim['lines'])} line(s)")

        tin, tout = C.estimate_tokens_for_run(turn)
        result.tokens_in, result.tokens_out = tin, tout
        result.cost_usd = C.price_run(tin, tout, "cheap")
        G.check_budget_ceiling(result.cost_usd)

        # ---- Injection scan happens before any further tool is even
        #      planned -- the cheapest possible exit, using only what
        #      get_claim already returned. -----------------------------
        found, patterns = S.check_injection(claim)
        if found:
            result.decision = "escalate"
            result.trigger = "instruction_in_member_narrative"
            result.turns = turn
            result.trace.append(f"turn {turn}: narrative flagged by guardrail patterns {patterns} -- stopped, no further tools called")
            return result

        # ---- Turn 2: parallel batch --------------------------------------
        turn += 1
        G.check_step_cap(turn)
        calls = S.plan_turn2(claim)
        _record_calls(result, calls, already_called)
        for name, kwargs in calls:
            out = execute(name, kwargs)
            if name == "lookup_policy":
                memory["policy"] = out
            elif name == "get_hospital_status":
                memory["hospital"] = out
            elif name == "get_claim_history":
                memory["history"] = out
            elif name == "check_coverage":
                memory["coverage"][kwargs["procedure_code"]] = out
        result.trace.append(f"turn {turn}: parallel batch of {len(calls)} calls")

        tin, tout = C.estimate_tokens_for_run(turn)
        result.tokens_in, result.tokens_out = tin, tout
        result.cost_usd = C.price_run(tin, tout, "cheap")
        G.check_budget_ceiling(result.cost_usd)

        trigger, reason = S.policy_level_verdict(claim, memory["policy"], memory["history"])
        if trigger:
            result.decision = "escalate"
            result.trigger = trigger
            result.turns = turn
            result.trace.append(f"turn {turn}: policy-level verdict -- {trigger}: {reason}")
            return result

        # ---- Turn 3 (conditional): preauth chase for lines that need one -
        preauth_calls = S.plan_turn3_preauth_calls(claim, memory["coverage"])
        if preauth_calls:
            turn += 1
            G.check_step_cap(turn)
            _record_calls(result, preauth_calls, already_called)
            for name, kwargs in preauth_calls:
                out = execute(name, kwargs)
                memory["preauth"][kwargs["procedure_code"]] = out
            result.trace.append(f"turn {turn}: {len(preauth_calls)} pre-authorisation chase(s)")

            tin, tout = C.estimate_tokens_for_run(turn)
            result.tokens_in, result.tokens_out = tin, tout
            result.cost_usd = C.price_run(tin, tout, "cheap")
            G.check_budget_ceiling(result.cost_usd)

        # ---- Resolve every line -------------------------------------------
        outcome = S.resolve_lines(claim, memory["coverage"], memory["preauth"])
        if outcome[0] == "ask":
            _, missing, resolved_so_far = outcome
            result.decision = "request_document"
            result.missing = missing
            result.turns = turn
            result.trace.append(f"turn {turn}: stopped on an ask -- {missing}")
            return result

        _, dispositions, approved_total, refused_total = outcome
        result.dispositions = dispositions
        result.approved_total = approved_total
        result.refused_total = refused_total

        # ---- Turn 4: the gate, then the write ------------------------------
        turn += 1
        G.check_step_cap(turn)
        G.check_autonomy_gate(autonomy, confirmed=auto_confirm)
        sig = f"issue_decision_letter({claim_id})"
        G.check_dedup(sig, already_called)
        already_called.add(sig)

        reason_text = (f"Policy {memory['policy']['policy_id']} status {memory['policy']['status']}. "
                        f"Hospital {'on' if memory['hospital']['panel'] else 'NOT on'} panel. "
                        f"{sum(1 for d in dispositions if d['status']=='covered')} of {len(dispositions)} "
                        f"lines payable; {sum(1 for d in dispositions if d['status']=='not_covered')} excluded. "
                        f"Approved total {approved_total} against {memory['policy']['remaining']} remaining.")
        out = execute("issue_decision_letter", {
            "case_id": claim_id, "decision": "approve_in_principle", "reason": reason_text,
            "evidence": result.evidence, "autonomy": autonomy, "confirmed": auto_confirm,
            "extra": {"lines": dispositions, "approved_total": approved_total, "refused_total": refused_total},
        })
        if "error" in out:
            raise G.GuardrailStop("gate_blocked", out["error"])

        result.decision = "approve_in_principle"
        result.gate = "operator approved" if autonomy == "confirm" else "act-autonomy"
        result.ledger_line = out["ledger_line"]
        result.turns = turn
        result.trace.append(f"turn {turn}: gate cleared, decision letter recorded")

        tin, tout = C.estimate_tokens_for_run(turn)
        result.tokens_in, result.tokens_out = tin, tout
        result.cost_usd = C.price_run(tin, tout, "cheap")

    except G.GuardrailStop as gs:
        result.decision = "escalate"
        result.trigger = gs.trigger
        result.guardrail_stop = gs.trigger
        result.turns = turn
        result.trace.append(f"turn {turn}: GUARDRAIL STOP -- {gs.trigger}: {gs.detail}")

    return result
