"""
D2 -- the tool layer (the ACI).

Every tool below is documented with the six required fields:
NAME+SIGNATURE, WHAT, INPUT, RETURNS, FAILS WHEN, IRREVERSIBLE.
The docstring IS the descriptor contract -- it is also printed by
describe_tools() so it can be pasted straight into the report/repo.

Design choice worth stating in the report: check_coverage and
get_preauthorisation both key on member_id rather than policy_id. This
removes an artificial dependency (you would otherwise need lookup_policy's
result before you could call check_coverage), which is what lets Turn 2
in D2(c) run lookup_policy / get_hospital_status / get_claim_history /
check_coverage(x N lines) as one true parallel batch -- none of them need
each other's output, only fields already returned by get_claim in Turn 1.

Poka-yoke moves (D2b), both real (make an error class impossible, not just
discouraged):
  1. procedure_code is validated against the procedure catalog inside
     check_coverage and get_preauthorisation. A typo'd code raises
     ProcedureNotFoundError instead of silently returning "not covered" --
     the earlier measurement interface did the latter.
  2. issue_decision_letter's `confirmed` parameter has no default, and the
     autonomy setting is a Literal["suggest","confirm","act"], not a free
     string -- a typo'd autonomy value fails loudly instead of silently
     falling back to the most permissive behaviour.
"""
from dataclasses import dataclass, field
from typing import Literal, Optional
import datetime as dt
import json
import os

from .data_io import STORE

LEDGER_PATH = os.environ.get("A2_LEDGER_PATH", os.path.join(os.path.dirname(__file__), "..", "results", "decision_ledger.jsonl"))


class ProcedureNotFoundError(Exception):
    pass


class ToolError(Exception):
    """Raised for FAILS WHEN conditions. The loop catches this and turns it
    into an Observation, it never crashes the run."""


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


# ---------------------------------------------------------------------------
# 1. get_claim
# ---------------------------------------------------------------------------
def get_claim(claim_id: str) -> dict:
    """
    NAME+SIGNATURE  get_claim(claim_id: str) -> ClaimRecord
    WHAT            The entry point. Returns the claim as submitted: member,
                    hospital, date of service, free-text narrative, attached
                    documents, and every line item with its procedure code
                    and amount.
    INPUT           claim_id: str. An id not in the queue raises ToolError
                    rather than returning an empty/partial record.
    RETURNS         One record, all fields, all line items. At most ~6 lines
                    in practice, so no size bound is enforced.
    FAILS WHEN      claim_id is not a known claim.
    IRREVERSIBLE?   No. Read-only.
    """
    c = STORE.claims.get(claim_id)
    if c is None:
        raise ToolError(f"get_claim: no such claim_id '{claim_id}'")
    return dict(c)


# ---------------------------------------------------------------------------
# 2. lookup_policy
# ---------------------------------------------------------------------------
def lookup_policy(member_id: str) -> dict:
    """
    NAME+SIGNATURE  lookup_policy(member_id: str) -> PolicyStatus
    WHAT            Resolves a member to their policy and returns everything
                    needed to decide if the POLICY (not any one line) blocks
                    the claim: status, cover dates, annual limit, amount
                    already used, and the remaining headroom (computed here,
                    not left for the model to subtract).
    INPUT           member_id: str. Unknown id raises ToolError.
    RETURNS         {member_id, policy_id, status, start_date, end_date,
                     annual_limit, used_to_date, remaining, exclusions}
                    -- one record, under 20 tokens' worth of fields.
    FAILS WHEN      member_id is not a known member.
    IRREVERSIBLE?   No. Read-only.
    """
    m = STORE.members.get(member_id)
    if m is None:
        raise ToolError(f"lookup_policy: no such member_id '{member_id}'")
    p = STORE.policies.get(m["policy_id"])
    if p is None:
        raise ToolError(f"lookup_policy: member '{member_id}' has no resolvable policy")
    return {
        "member_id": member_id,
        "policy_id": p["policy_id"],
        "status": p["status"],
        "start_date": p["start_date"],
        "end_date": p["end_date"],
        "annual_limit": p["annual_limit"],
        "used_to_date": p["used_to_date"],
        "remaining": p["annual_limit"] - p["used_to_date"],
        "exclusions": p["exclusions"],
    }


# ---------------------------------------------------------------------------
# 3. check_coverage
# ---------------------------------------------------------------------------
def check_coverage(member_id: str, procedure_code: str) -> dict:
    """
    NAME+SIGNATURE  check_coverage(member_id: str, procedure_code: str) -> CoverageResult
    WHAT            The one call that answers everything about a SINGLE
                    line: is it excluded under this member's policy, does it
                    require pre-authorisation, and does it require a
                    specific supporting document. Answers what nothing else
                    answers -- do not also call lookup_policy to get this.
    INPUT           member_id: str, resolved internally to the policy so
                    this call has no dependency on lookup_policy's output.
                    procedure_code: str, validated against the procedure
                    catalog -- see ProcedureNotFoundError below.
    RETURNS         {procedure_code, excluded, exclusion_rule,
                     requires_preauth, required_document}
                    -- one record, 5 fields, under 20 tokens.
    FAILS WHEN      member_id unknown -> ToolError.
                    procedure_code not in the catalog -> ProcedureNotFoundError
                    (poka-yoke: a typo'd code fails loudly rather than
                    silently returning "not covered", which is what an
                    unvalidated free-string version does).
    IRREVERSIBLE?   No. Read-only.
    """
    m = STORE.members.get(member_id)
    if m is None:
        raise ToolError(f"check_coverage: no such member_id '{member_id}'")
    proc = STORE.procedures.get(procedure_code)
    if proc is None:
        raise ProcedureNotFoundError(f"check_coverage: unknown procedure_code '{procedure_code}'")

    policy = STORE.policies[m["policy_id"]]
    excluded, rule = False, None
    for ex in policy["exclusions"]:
        if ex["code"] == procedure_code:
            excluded, rule = True, ex["rule"]
            break

    return {
        "procedure_code": procedure_code,
        "excluded": excluded,
        "exclusion_rule": rule,
        "requires_preauth": proc["requires_preauth"],
        "required_document": STORE.required_docs.get(procedure_code),
    }


# ---------------------------------------------------------------------------
# 4. get_preauthorisation
# ---------------------------------------------------------------------------
def get_preauthorisation(member_id: str, procedure_code: str, date_of_service: str) -> dict:
    """
    NAME+SIGNATURE  get_preauthorisation(member_id: str, procedure_code: str,
                                          date_of_service: str) -> PreauthResult
    WHAT            Answers "does a pre-authorisation exist for THIS member,
                    THIS procedure, valid on THIS date" -- all three, not
                    just whether a record with this member_id exists.
    INPUT           date_of_service: str, ISO date. Validity is inclusive
                    of both valid_from and valid_to.
    RETURNS         {found, preauth_id, valid_from, valid_to, currently_valid,
                     note}. `found` distinguishes "no record at all" from
                    "record exists but for a different procedure" (both are
                    also reported in `note`) from "record exists, expired".
    FAILS WHEN      procedure_code not in the catalog -> ProcedureNotFoundError.
    IRREVERSIBLE?   No. Read-only.
    """
    if procedure_code not in STORE.procedures:
        raise ProcedureNotFoundError(f"get_preauthorisation: unknown procedure_code '{procedure_code}'")

    matches_member = [p for p in STORE.preauths if p["member_id"] == member_id]
    exact = [p for p in matches_member if p["procedure_code"] == procedure_code]

    if not exact:
        note = ("no pre-authorisation record for this member at all" if not matches_member
                else f"member has {len(matches_member)} pre-authorisation record(s), none for procedure {procedure_code}")
        return {"found": False, "preauth_id": None, "valid_from": None, "valid_to": None,
                "currently_valid": False, "note": note}

    d = _date(date_of_service)
    # A member can genuinely have more than one preauth record for the same
    # procedure over time (e.g. an old expired one and a freshly re-issued
    # one) -- picking exact[0] unconditionally means list ORDER, not the
    # actual date, decides the outcome. Check every matching record for one
    # that is actually valid on this date; only if none are, fall back to
    # the most recently-issued record (highest valid_to) so the "expired"
    # message is at least the most relevant one, not an arbitrary older hit.
    valid_matches = [r for r in exact if _date(r["valid_from"]) <= d <= _date(r["valid_to"])]
    if valid_matches:
        rec, valid = valid_matches[0], True
    else:
        rec, valid = max(exact, key=lambda r: r["valid_to"]), False
    note = "valid on this date" if valid else f"record found but expired/not yet valid for {date_of_service}"
    return {"found": True, "preauth_id": rec["preauth_id"], "valid_from": rec["valid_from"],
            "valid_to": rec["valid_to"], "currently_valid": valid, "note": note}


# ---------------------------------------------------------------------------
# 5. get_hospital_status
# ---------------------------------------------------------------------------
def get_hospital_status(hospital_id: str) -> dict:
    """
    NAME+SIGNATURE  get_hospital_status(hospital_id: str) -> HospitalStatus
    WHAT            Whether the treating hospital is on the panel, and its
                    country -- needed only for what the record must SAY, it
                    never changes the decision itself.
    INPUT           hospital_id: str. Unknown id raises ToolError.
    RETURNS         {hospital_id, name, panel, country} -- one record.
    FAILS WHEN      hospital_id is not a known hospital.
    IRREVERSIBLE?   No. Read-only.
    """
    h = STORE.hospitals.get(hospital_id)
    if h is None:
        raise ToolError(f"get_hospital_status: no such hospital_id '{hospital_id}'")
    return dict(h)


# ---------------------------------------------------------------------------
# 6. get_claim_history
# ---------------------------------------------------------------------------
def get_claim_history(member_id: str) -> dict:
    """
    NAME+SIGNATURE  get_claim_history(member_id: str) -> ClaimHistory
    WHAT            Returns this member's already-decided claims, so the
                    agent can check for a duplicate. Fails without it: a
                    duplicate can only be caught by comparing against
                    history the model does not otherwise see.
    INPUT           member_id: str.
    RETURNS         {member_id, decided: [...]} at most 5 records, each
                    {claim_id, hospital_id, date_of_service, lines,
                     decision}. SIZE BOUND: <= 5 records, ~40 tokens each.
    FAILS WHEN      Never raises -- an empty history is a valid, common
                    answer ("decided": []), not an error.
    IRREVERSIBLE?   No. Read-only.
    """
    decided = [d for d in STORE.decided_claims if d["member_id"] == member_id][:5]
    return {"member_id": member_id, "decided": decided}


def get_claim_history_v1(member_id: str) -> dict:
    """
    NAME+SIGNATURE  get_claim_history(member_id: str) -> ClaimHistory
    WHAT            V1 measurement interface. Returns every decided claim
                    without member filtering or a size bound.
    INPUT           member_id: str. Retained in the response but not used
                    to filter the records.
    RETURNS         {member_id, decided: [...]} with all decided claims.
    FAILS WHEN      Never raises.
    IRREVERSIBLE?   No. Read-only.
    """
    return {"member_id": member_id, "decided": list(STORE.decided_claims)}


def is_duplicate(claim: dict, history: dict) -> Optional[dict]:
    """Code-layer helper (not a tool the model calls): exact 4-way match on
    member, hospital, date_of_service and lines. Matching on fewer than all
    four is exactly the shortcut the near-miss cases in the eval set are
    designed to catch."""
    for d in history["decided"]:
        if (d["hospital_id"] == claim["hospital_id"]
                and d["date_of_service"] == claim["date_of_service"]
                and d["lines"] == claim["lines"]):
            return d
    return None


# ---------------------------------------------------------------------------
# 7. issue_decision_letter -- THE GATED ACTION
# ---------------------------------------------------------------------------
def issue_decision_letter(case_id: str, decision: str, reason: str, evidence: list,
                           autonomy: Literal["suggest", "confirm", "act"],
                           confirmed: bool, extra: dict = None) -> dict:
    """
    NAME+SIGNATURE  issue_decision_letter(case_id: str, decision: str,
                        reason: str, evidence: list[str],
                        autonomy: Literal["suggest","confirm","act"],
                        confirmed: bool, extra: dict = None) -> Confirmation
    WHAT            The ONE write in this agent. It does not compose a
                    letter, address an envelope or send anything -- it
                    appends one structured record to a local ledger file
                    and returns a confirmation string. See D1 "the gated
                    action is a log entry, not the thing it stands for".
    INPUT           decision must be "approve_in_principle" here (ask/escalate
                    outcomes never reach this tool -- see loop.py). confirmed
                    has NO default: a caller must pass it explicitly, so the
                    irreversible step cannot fire on an omitted argument.
    RETURNS         {"status": "recorded", "ledger_line": <the record written>}
    FAILS WHEN      autonomy == "confirm" and confirmed is not True -- the
                    gate blocks the write and raises ToolError; the caller
                    (loop.py) is responsible for having actually obtained
                    that confirmation before setting confirmed=True.
    IRREVERSIBLE?   YES. This is the gated action. The gate is enforced
                    here, in the tool itself, not merely hoped for upstream.
    """
    if autonomy == "confirm" and not confirmed:
        raise ToolError("issue_decision_letter: autonomy=confirm requires operator confirmation before writing")
    if autonomy == "suggest":
        raise ToolError("issue_decision_letter: autonomy=suggest never calls this tool -- it stops one step earlier")

    record = {
        "ts": dt.datetime.utcnow().isoformat(),
        "case_id": case_id,
        "decision": decision,
        "reason": reason,
        "evidence": evidence,
        "autonomy": autonomy,
        "gate": "operator approved" if autonomy == "confirm" else "act-autonomy, no operator step",
    }
    if extra:
        record.update(extra)

    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")

    return {"status": "recorded", "ledger_line": record}


# ---------------------------------------------------------------------------
"""
Builds the tool-documentation text handed to a live model's system prompt,
straight from each tool's own docstring -- the descriptor contract IS the
manual, so there is exactly one place these six fields are written.
"""
def build_tool_docs() -> str:
    import inspect
    parts = []
    for name, fn in TOOL_REGISTRY.items():
        doc = inspect.getdoc(fn) or ""
        parts.append(doc.strip())
    return "\n\n".join(parts)


TOOL_REGISTRY = {
    "get_claim": get_claim,
    "lookup_policy": lookup_policy,
    "check_coverage": check_coverage,
    "get_preauthorisation": get_preauthorisation,
    "get_hospital_status": get_hospital_status,
    "get_claim_history": get_claim_history,
    "issue_decision_letter": issue_decision_letter,
}

# D2(a) scoring table -- fill this in for your report; kept here so it ships
# with the code it describes rather than living only in prose.
TOOL_SCORING = {
    "get_claim":            {"fails_without": True,  "confusable_with": None,   "kept_because": "entry point; everything else needs its output"},
    "lookup_policy":        {"fails_without": True,  "confusable_with": None,   "kept_because": "only source of policy status/dates/limit"},
    "check_coverage":       {"fails_without": True,  "confusable_with": "get_preauthorisation (both gate a line)", "kept_because": "only source of exclusion + preauth-required + doc-required per line"},
    "get_preauthorisation": {"fails_without": True,  "confusable_with": "check_coverage", "kept_because": "only source of whether a specific preauth is currently valid"},
    "get_hospital_status":  {"fails_without": True,  "confusable_with": None,   "kept_because": "the record must state panel/country even though it never changes the decision"},
    "get_claim_history":    {"fails_without": True,  "confusable_with": None,   "kept_because": "only source that can catch a duplicate"},
    "issue_decision_letter": {"fails_without": True, "confusable_with": None,   "kept_because": "the only write; one gate covers the whole agent"},
}

TOOL_INTERFACE_VERSION = "v2"


def configure_tool_interface(version: str):
    """Select the measured V1 history interface or the corrected V2 interface."""
    global TOOL_INTERFACE_VERSION
    normalized = str(version).strip().lower()
    if normalized not in {"v1", "v2"}:
        raise ValueError("Tool interface version must be v1 or v2")
    TOOL_INTERFACE_VERSION = normalized
    TOOL_REGISTRY["get_claim_history"] = (
        get_claim_history_v1 if normalized == "v1" else get_claim_history
    )
    return TOOL_INTERFACE_VERSION
