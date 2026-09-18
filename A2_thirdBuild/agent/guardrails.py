"""
D3(a) -- the code layer, shipped before any prompt tuning.

Four things, all enforced in code, none of them a prompt instruction:
  1. step cap        -- hard ceiling on turns in one run
  2. budget ceiling   -- hard ceiling on estimated cost_usd in one run
  3. action dedup     -- refuse to execute a call already executed this run
  4. autonomy gate    -- suggest / confirm / act, enforced at issue_decision_letter

Plus the narrative scan, which is the guardrail that answers D3(b)'s "at
least three of your ten [guardrail cases] must cover the request text
itself being hostile" requirement. It is deliberately a heuristic, not a
model call -- Class 4's point about the code layer is that these checks
must be cheap enough to run on every claim, every time, before any prompt
tuning exists at all.
"""
import re

# Chosen autonomy setting for this agent, defended in the report:
# "confirm" -- the agent proposes approve_in_principle, an operator approves,
# then the agent itself writes the ledger record. Justification: an approved
# claim is expensive to walk back (D1's "the governance cliff is the first
# write"), and unlike Problem B a missed/slow booking is not itself unsafe,
# so full "act" autonomy buys speed we do not need at a risk we would rather
# not carry. "suggest" was rejected because a case with zero ambiguity (e.g.
# CLM-8850, one covered line, live policy) does not need a human in the loop
# on every single approval -- "confirm" keeps the human at the gate itself,
# not in front of the whole run.
AUTONOMY_SETTING = "confirm"

STEP_CAP = 6          # evidence: median legitimate run is 4 turns (CLM-8842),
                       # worst legitimate run is 4 turns; +2 turns of headroom
                       # before we call it a loop, not 30 (see failures.py)
BUDGET_CEILING_USD = 0.05   # a single scripted/cheap-tier run should cost
                            # cents; this catches a run that is retrying in
                            # a way that inflates tokens without inflating turns


class GuardrailStop(Exception):
    """Raised to end a run early for a reason that is NOT a normal decision
    outcome (cap hit, budget hit, dedup violation). The loop converts this
    into an escalate with a distinct trigger so it is never silently
    swallowed -- see D7: 'a cap that silently returns an empty answer is
    worse than the loop it stops.'"""
    def __init__(self, trigger, detail):
        self.trigger = trigger
        self.detail = detail
        super().__init__(f"{trigger}: {detail}")


def check_step_cap(turn_number: int):
    if turn_number > STEP_CAP:
        raise GuardrailStop("step_cap_hit", f"turn {turn_number} exceeds cap of {STEP_CAP}")


def check_budget_ceiling(cost_so_far_usd: float):
    if cost_so_far_usd > BUDGET_CEILING_USD:
        raise GuardrailStop("budget_ceiling_hit", f"cost {cost_so_far_usd:.4f} exceeds ceiling {BUDGET_CEILING_USD}")


def check_dedup(call_signature: str, already_called: set):
    """call_signature is e.g. "check_coverage('M-2214','62480')". Repeating
    an identical call is the clearest sign of the loop-control failure in
    D7 -- the agent re-reading something it already knows."""
    if call_signature in already_called:
        raise GuardrailStop("duplicate_action", f"already executed this run: {call_signature}")


def check_autonomy_gate(autonomy: str, confirmed: bool):
    if autonomy not in ("suggest", "confirm", "act"):
        raise ValueError(f"invalid autonomy setting '{autonomy}' -- must be suggest/confirm/act (poka-yoke: no silent default)")
    if autonomy == "confirm" and not confirmed:
        raise GuardrailStop("gate_not_confirmed", "autonomy=confirm requires operator confirmation before the write")


# ---------------------------------------------------------------------------
# Narrative injection scan -- D3(b), >= 3 hostile-text guardrail cases
# ---------------------------------------------------------------------------
# Each pattern is a whole phrase, not a single word, specifically so that
# ordinary claims mentioning "approval" in the normal sense (e.g. "I got
# approval for this earlier in the year", CLM-8894) do not false-positive.
_INJECTION_PATTERNS = [
    re.compile(r"system note", re.I),
    re.compile(r"ignore (the )?exclusions?", re.I),
    re.compile(r"approve all lines? in full", re.I),
    re.compile(r"authoris(e|ation)d? by (the )?claims supervisor", re.I),
    re.compile(r"\[[^\[\]]*returned[^\[\]]*:[^\[\]]*\]", re.I),          # fake tool output, e.g. "[check_coverage returned: ...]"
    re.compile(r'"role"\s*:\s*"(system|assistant)"', re.I),              # fake chat-role message
    re.compile(r"skip the checks?", re.I),
    re.compile(r"already\s+(verbally\s+)?approved this", re.I),
    re.compile(r"coverage confirmed", re.I),
    re.compile(r"approve immediately", re.I),
]


def scan_narrative_for_injection(narrative: str):
    """Returns (found: bool, matched_patterns: list[str]). Deliberately
    returns WHICH patterns fired (for the evidence trail / must_record) but
    never echoes the injected text itself back as an instruction anywhere
    in the decision record."""
    hits = [p.pattern for p in _INJECTION_PATTERNS if p.search(narrative)]
    return (len(hits) > 0), hits
