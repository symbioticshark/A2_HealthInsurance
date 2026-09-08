"""
D7 -- two reproduced failures, each built as "the working agent, minus X",
not as a separately written bad agent. Putting X back recovers the good
behaviour -- run the __main__ block below and check it.
"""
from . import guardrails as G
from . import tools as T
from .data_io import STORE
from . import scripted_backend as S


# ===========================================================================
# FAILURE 1 (required) -- a loop-control failure.
# ===========================================================================
# X = the dedup guard AND the step cap, both removed. What is left is a
# "buggy" scripted planner that, after reaching an ask outcome, does not
# stop -- it re-runs the turn-2 batch again, as if it had forgotten it
# already knew the answer. This is Class 4's exact failure shape: no
# exception is raised, nothing crashes, it just burns turns in a circle.
class _RunawayStop(Exception):
    pass


def broken_run_case(claim_id: str, hard_safety_ceiling: int = 40):
    """X removed: no G.check_dedup, no G.check_step_cap. hard_safety_ceiling
    is NOT the guardrail under test -- it only stops this demo function from
    actually hanging forever; a real deployment without D3(a)'s guardrails
    would not have even this."""
    claim = T.get_claim(claim_id)
    turns = 0
    tokens_in_total = 0
    already_seen_ask = False

    while turns < hard_safety_ceiling:
        turns += 1
        policy = T.lookup_policy(claim["member_id"])
        hospital = T.get_hospital_status(claim["hospital_id"])
        history = T.get_claim_history(claim["member_id"])
        coverage = {l["code"]: T.check_coverage(claim["member_id"], l["code"]) for l in claim["lines"]}
        tokens_in_total += 1200 + 400 * turns   # same growth shape as the real cost model

        trigger, _ = S.policy_level_verdict(claim, policy, history)
        if trigger:
            return {"turns": turns, "tokens_in": tokens_in_total, "outcome": "escalate", "trigger": trigger}

        preauth = {}
        for l in claim["lines"]:
            cov = coverage[l["code"]]
            if cov["requires_preauth"] and not cov["excluded"]:
                preauth[l["code"]] = T.get_preauthorisation(claim["member_id"], l["code"], claim["date_of_service"])

        outcome = S.resolve_lines(claim, coverage, preauth)
        if outcome[0] == "ask":
            # THE BUG: a correct agent stops here and returns the ask.
            # This one, missing the guards, "re-checks" instead -- exactly
            # the re-reading-what-it-already-knows failure Class 4 built.
            already_seen_ask = True
            continue   # <-- loops back to the top of `while` instead of returning
        else:
            return {"turns": turns, "tokens_in": tokens_in_total, "outcome": "approve_in_principle"}

    return {"turns": turns, "tokens_in": tokens_in_total, "outcome": "NO ANSWER -- hit hard_safety_ceiling",
            "note": "8 turns in, and every turn after the first ask was pure repetition of turn 2+3."}


def fixed_run_case(claim_id: str):
    """X put back: dedup + step cap, i.e. just call the real loop.run_case."""
    from . import loop
    r = loop.run_case(claim_id)
    return {"turns": r.turns, "tokens_in": r.tokens_in, "outcome": r.decision or r.trigger}


# ===========================================================================
# FAILURE 2 -- a tool-interface failure (not loop control again).
# ===========================================================================
# X = get_claim_history's filtering and size bound. v1 below is what the
# tool looks like if you forget both: it returns EVERY decided claim in the
# system, not just this member's, uncapped. Two consequences, both real:
#   (a) it is fat -- linear in the size of decided_claims.json, re-sent on
#       every later turn because the loop is stateless (D2c).
#   (b) it is a landmine -- a naive duplicate check that only compares
#       hospital/date/lines (forgetting to also check member_id, which v1's
#       shape invites since the member_id filtering used to happen INSIDE
#       the tool) can now match another member's superficially identical
#       claim and wrongly escalate someone who has no duplicate at all.
def get_claim_history_v1(member_id: str) -> dict:
    """BROKEN. Kept only for this demonstration -- do not import from
    tools.py, this is intentionally not registered as a real tool."""
    return {"member_id": member_id, "decided": list(STORE.decided_claims)}  # unfiltered, uncapped


def demo_failure_2():
    # A member with NO decided claims of their own, who happens to submit a
    # claim whose hospital/date/lines coincide with a DIFFERENT member's
    # (M-5502's) real decided claim CLM-8702. A correct history lookup for
    # this member returns nothing to compare against; v1's unfiltered
    # return hands the comparator every member's history, including the
    # coincidental match, with no member_id check to stop it.
    new_claim = {"member_id": "M-9999", "hospital_id": "H-207", "date_of_service": "2026-09-02",
                 "lines": [{"code": "99213", "amount": 180}]}

    v2 = T.get_claim_history("M-9999")          # correctly filtered: no records for this member
    v1 = get_claim_history_v1("M-9999")         # BROKEN: every member's decided claims, unfiltered

    import json
    v1_tokens = len(json.dumps(v1)) // 4
    v2_tokens = len(json.dumps(v2)) // 4

    match_via_v1 = T.is_duplicate(new_claim, v1)
    match_via_v2 = T.is_duplicate(new_claim, v2)

    return {
        "v1_tokens_returned": v1_tokens,
        "v2_tokens_returned": v2_tokens,
        "v1_wrongly_flagged_duplicate_of": match_via_v1["claim_id"] if match_via_v1 else None,
        "v2_correctly_found_no_duplicate": match_via_v2 is None,
        "note": ("v1 is both fatter (every member's history, uncapped, vs one member's, capped at 5) AND "
                 "wrong: with no member_id filtering, a new member's claim can be mis-matched against a "
                 "DIFFERENT member's coincidentally-similar decided claim and wrongly escalated. "
                 "Fixed at the interface -- filtering by member_id and capping the return -- not by adding "
                 "a sentence to a prompt telling the model to 'only consider this member's claims.'"),
    }


if __name__ == "__main__":
    print("=== Failure 1: loop-control (broken vs fixed) ===")
    # CLM-8888 needs an ask (preauth missing) -- the case the bug targets.
    print("broken:", broken_run_case("CLM-8888"))
    print("fixed: ", fixed_run_case("CLM-8888"))
    print()
    print("=== Failure 2: tool-interface (get_claim_history v1 vs v2) ===")
    print(demo_failure_2())
