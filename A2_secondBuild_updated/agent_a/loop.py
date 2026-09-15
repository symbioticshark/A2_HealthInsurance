"""
D1 + D2(c) + D3(a) -- the agent loop.

One agent, one control loop: Thought -> Action(one or more tool calls) ->
Observation -> repeat -> Final. Every tool call, on EITHER backend, goes
through the SAME tool_registry, SAME guardrails, SAME ledger, SAME cost
accounting -- so a loop-control failure or a guardrail catch means the same
thing regardless of which backend produced the action.

Two real execution paths, dispatched by `backend`:
  * "scripted" -- driven by scripted_backend.py's deterministic rule table.
    No network, no key, reproduces identically every time. This is what
    D5(a) requires as the default.
  * "live" -- driven by an actual model via live_backend.py: a real system
    prompt built from the tools' own descriptor contracts, a real
    Thought/Action/Observation text loop, real per-call token usage and
    wall-clock time from the API response. This is D5(b).

Both paths populate the same RunResult shape, including the fields
metrics.py needs: model, wall_clock_seconds, gate_confirmed,
cost_is_measured -- so scripted and live runs land in the same log and are
directly comparable, with the estimated/measured distinction preserved
per row rather than silently blended.
"""
import time
from dataclasses import dataclass, field

from . import config
from .data_io import STORE
from . import tools as T
from . import guardrails as G
from . import scripted_backend as S
from . import cost_model as C
from . import live_backend as L
from . import metrics as M


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
    gate_confirmed: bool = None     # None = the run never reached the gate
    turns: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    cost_is_measured: bool = False  # True only for live runs priced from real API usage
    cost_source: str = "estimated"
    model: str = "scripted"         # "scripted", or the live model id actually used
    wall_clock_seconds: float = 0.0
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
             backend: str = None, model: str = None, verbose: bool = False) -> RunResult:
    """Runs ONE trial of ONE case, start to finish, from a clean state (D4
    isolation -- nothing here reads any other run's output). Dispatches to
    the scripted or live path based on `backend` (defaults to config.BACKEND)."""
    backend = backend or config.BACKEND
    t_start = time.perf_counter()
    if backend == "live":
        result = _run_case_live(claim_id, autonomy, auto_confirm, model or config.MODEL, verbose)
    else:
        result = _run_case_scripted(claim_id, autonomy, auto_confirm, verbose)
    # Single source of truth for wall clock: the whole run, API latency and
    # tool/guardrail overhead together -- not just the sum of individual
    # API call latencies, which undercounts the loop's own cost.
    result.wall_clock_seconds = round(time.perf_counter() - t_start, 4)
    return result


# ===========================================================================
# SCRIPTED PATH -- deterministic, no network, D5(a)
# ===========================================================================
def _run_case_scripted(claim_id: str, autonomy: str, auto_confirm: bool, verbose: bool) -> RunResult:
    result = RunResult(case_id=claim_id, autonomy=autonomy, model="scripted", cost_is_measured=False)
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
        result.gate_confirmed = auto_confirm
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


# ===========================================================================
# LIVE PATH -- a real model, via OpenRouter, D5(b)
# ===========================================================================
def _run_case_live(claim_id: str, autonomy: str, auto_confirm: bool, model: str, verbose: bool) -> RunResult:
    result = RunResult(case_id=claim_id, autonomy=autonomy, model=model, cost_is_measured=True)
    already_called = set()
    turn = 0

    system_prompt = L.build_system_prompt(T.build_tool_docs())
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Process claim_id={claim_id}."},
    ]

    def execute(name, kwargs):
        fn = T.TOOL_REGISTRY[name]
        if name == "issue_decision_letter":
            # The gate is enforced HERE, in code -- not by trusting whatever
            # autonomy/confirmed values the model happened to pass. This is
            # the same principle as tools.py's own docstring: the model
            # proposes, the code layer decides whether the write happens.
            kwargs = dict(kwargs)
            kwargs["autonomy"] = autonomy
            kwargs["confirmed"] = auto_confirm
            kwargs["evidence"] = result.evidence
            result.gate_confirmed = auto_confirm
        try:
            out = fn(**kwargs)
        except T.ToolError as e:
            out = {"error": str(e)}
        except T.ProcedureNotFoundError as e:
            out = {"error": str(e)}
        except TypeError as e:
            out = {"error": f"bad arguments for {name}: {e}"}
        if name == "issue_decision_letter" and "error" not in out:
            result.ledger_line = out.get("ledger_line")
        result.evidence.append(name)
        return out

    try:
        while True:
            turn += 1
            G.check_step_cap(turn)

            text, usage = L.call_model(messages, model=model)
            result.tokens_in += usage["input_tokens"]
            result.tokens_out += usage["output_tokens"]
            result.cached_input_tokens += usage.get("cached_input_tokens", 0)
            result.cache_write_tokens += usage.get("cache_write_tokens", 0)
            result.reasoning_tokens += usage.get("reasoning_tokens", 0)
            if usage.get("cost_usd") is not None:
                cost = usage["cost_usd"]
                is_measured = True
            else:
                cost, _ = M.price_for_model(
                    model, usage["input_tokens"], usage["output_tokens"]
                )
                is_measured = False
            result.cost_usd += cost
            result.cost_is_measured = result.cost_is_measured and is_measured
            result.cost_source = (
                "openrouter_usage" if result.cost_is_measured else "token_price_fallback"
            )
            G.check_budget_ceiling(result.cost_usd)
            messages.append({"role": "assistant", "content": text})

            # Execute any Action calls in THIS turn's text first, before
            # ever looking at a Final in the same text. A model very
            # naturally writes "Action: issue_decision_letter(...)" and
            # "Final: {...}" in the same single response -- checking Final
            # first (the old order) meant the gate check saw
            # issue_decision_letter as "not yet called" even though it was
            # sitting right there in the same message, and force-escalated
            # every case that concluded this way. Executing first means the
            # gate check below sees the real, current evidence.
            calls = L.parse_actions(text)
            if calls:
                _record_calls(result, calls, already_called)
                observations = []
                for name, kwargs in calls:
                    if name not in T.TOOL_REGISTRY:
                        observations.append(f"Observation: ERROR -- unknown tool '{name}'")
                        continue
                    out = execute(name, kwargs)
                    observations.append(f"Observation ({name}): {out}")
                result.trace.append(f"turn {turn}: {len(calls)} call(s) -- {[c[0] for c in calls]}")

            final = L.parse_final(text)
            if final is not None:
                decision = final.get("decision")
                if decision not in ("approve_in_principle", "request_document", "escalate"):
                    raise G.GuardrailStop("invalid_decision", f"model returned an unrecognized decision value: {decision!r}")
                if decision == "approve_in_principle" and "issue_decision_letter" not in result.evidence:
                    # A model claiming approval without ever calling the
                    # gated tool -- even in an earlier turn -- is exactly
                    # the failure mode the gate exists to prevent.
                    raise G.GuardrailStop("gate_bypassed", "model claimed approve_in_principle without calling issue_decision_letter")
                result.decision = decision
                result.trigger = final.get("trigger")
                result.missing = final.get("missing")
                result.dispositions = final.get("lines", [])
                result.approved_total = final.get("approved_total", 0)
                result.refused_total = final.get("refused_total", 0)
                if decision == "approve_in_principle":
                    result.gate = "operator approved" if autonomy == "confirm" else "act-autonomy"
                result.turns = turn
                result.trace.append(f"turn {turn}: Final -- {decision}")
                return result

            if not calls:
                result.trace.append(f"turn {turn}: model produced neither Action nor Final -- treating as a stall")
                raise G.GuardrailStop("no_action_no_final", "model turn had no parseable Action or Final")

            messages.append({"role": "user", "content": "\n".join(observations)})

    except G.GuardrailStop as gs:
        result.decision = "escalate"
        result.trigger = gs.trigger
        result.guardrail_stop = gs.trigger
        result.turns = turn
        result.trace.append(f"turn {turn}: GUARDRAIL STOP -- {gs.trigger}: {gs.detail}")

    return result
