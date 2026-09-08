"""
D5(a) -- the scripted backend.

This is NOT the agent's intelligence. It is a deterministic stand-in for
"whatever the live model would have decided", written so BACKEND="scripted"
reproduces a run end to end with no network and no key. It encodes exactly
the routing table in Appendix A (Problem A) -- the same rules a human
claims officer follows -- as a small state machine over what has been
observed so far.

The REAL agent behaviour under test is everything in loop.py: how turns are
assembled, whether calls are batched in parallel, whether the guardrails
fire, whether the gate holds. Swapping this module for live_backend.py
(D5b, three OpenRouter models) changes nothing else -- that is the point of
keeping BACKEND/MODEL/BASE_URL in one place (config.py).

Dependency rule actually implemented here (state it in the report):
  Turn 1: get_claim alone -- everything else needs its output.
  Turn 2: lookup_policy || get_hospital_status || get_claim_history ||
          check_coverage(one call per line) -- none of these need each
          other's output, only fields get_claim already returned.
  Turn 3 (only if needed): get_preauthorisation, one call per line that
          check_coverage flagged requires_preauth and not excluded.
  Turn 4 (only if the claim clears): issue_decision_letter, behind the gate.

Honest limit (brief again asks for this explicitly): batching check_coverage
into turn 2 alongside lookup_policy means a policy-level disqualifier
(lapsed / outside dates / over limit / duplicate) is discovered only AFTER
those coverage calls have already been made and paid for -- turn 2 was
"wasted" on lines that will never be priced. The alternative (call
lookup_policy alone first, defer coverage to turn 3) avoids that waste but
gives up the parallel saving on the common, non-disqualified path, which is
the larger share of claims. We chose to optimise for the common case and
accept the wasted batch on the disqualified minority; say in the report
whether your own data would favour the other ordering.

Injection scan happens BEFORE turn 2 is even planned -- see loop.py -- so a
hostile narrative is caught with only get_claim's cost paid.
"""
from .guardrails import scan_narrative_for_injection
from .tools import is_duplicate
import datetime as dt


def _d(s):
    return dt.date.fromisoformat(s)


def plan_turn2(claim: dict):
    """Returns the list of (tool_name, kwargs) calls for the parallel batch."""
    calls = [
        ("lookup_policy", {"member_id": claim["member_id"]}),
        ("get_hospital_status", {"hospital_id": claim["hospital_id"]}),
        ("get_claim_history", {"member_id": claim["member_id"]}),
    ]
    for line in claim["lines"]:
        calls.append(("check_coverage", {"member_id": claim["member_id"], "procedure_code": line["code"]}))
    return calls


def policy_level_verdict(claim: dict, policy: dict, history: dict):
    """Checks that can end the run right after turn 2, before any
    preauthorisation is chased or any line is individually resolved.
    Returns (trigger, reason) or (None, None)."""
    if policy["status"] == "lapsed":
        return "policy_lapsed", f"{policy['policy_id']} status is lapsed."

    dos = _d(claim["date_of_service"])
    if not (_d(policy["start_date"]) <= dos <= _d(policy["end_date"])):
        return "outside_policy_dates", (f"date of service {claim['date_of_service']} falls outside "
                                         f"{policy['policy_id']}'s cover {policy['start_date']} to {policy['end_date']}.")

    dup = is_duplicate(claim, history)
    if dup is not None:
        return "duplicate_claim", (f"{dup['claim_id']} was already decided ({dup['decision']}) for the same "
                                    f"member, hospital, date of service and lines.")

    claim_total = sum(l["amount"] for l in claim["lines"])
    if claim_total > policy["remaining"]:
        return "annual_limit_exceeded", (f"claim total {claim_total} exceeds {policy['remaining']} "
                                          f"remaining on {policy['policy_id']}. Lines were not individually priced.")

    return None, None


def plan_turn3_preauth_calls(claim: dict, coverage: dict):
    """Which lines need a get_preauthorisation call: requires_preauth and
    not already excluded (an excluded line never needs a preauth chase --
    it is refused regardless)."""
    calls = []
    for line in claim["lines"]:
        cov = coverage[line["code"]]
        if cov["requires_preauth"] and not cov["excluded"]:
            calls.append(("get_preauthorisation", {"member_id": claim["member_id"],
                                                     "procedure_code": line["code"],
                                                     "date_of_service": claim["date_of_service"]}))
    return calls


def resolve_lines(claim: dict, coverage: dict, preauth: dict):
    """The per-line resolution step (after turn 2, and turn 3 if it ran).
    Returns either:
      ("ask", missing_description, resolved_so_far)             -- stop, no gate
      ("approve", dispositions, approved_total, refused_total)   -- proceed to the gate
    Stops at the FIRST blocking line, in line order -- an ask names ONE
    missing item, not every gap on the claim (D1's over-build warning)."""
    dispositions = []
    resolved_so_far = []

    for line in claim["lines"]:
        code = line["code"]
        cov = coverage[code]

        if cov["excluded"]:
            dispositions.append({"code": code, "amount": line["amount"], "status": "not_covered",
                                  "exclusion": cov["exclusion_rule"]})
            resolved_so_far.append(f"{code} not covered - {cov['exclusion_rule']}")
            continue

        if cov["requires_preauth"]:
            pre = preauth.get(code)
            if pre is None or not pre["currently_valid"]:
                missing = f"pre-authorisation reference for line {code}, valid on {claim['date_of_service']}"
                return "ask", missing, resolved_so_far

        req_doc = cov["required_document"]
        if req_doc and req_doc not in claim["documents"]:
            missing = f"{req_doc} for line {code}"
            return "ask", missing, resolved_so_far

        disp = {"code": code, "amount": line["amount"], "status": "covered"}
        if cov["requires_preauth"]:
            disp["preauth"] = preauth[code]["preauth_id"]
        dispositions.append(disp)
        resolved_so_far.append(f"{code} covered")

    approved_total = sum(d["amount"] for d in dispositions if d["status"] == "covered")
    refused_total = sum(d["amount"] for d in dispositions if d["status"] == "not_covered")
    return "approve", dispositions, approved_total, refused_total


def check_injection(claim: dict):
    return scan_narrative_for_injection(claim["narrative"])
