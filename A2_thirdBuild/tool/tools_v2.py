"""D2(b) measurement interface: the corrected, bounded V2 history tool."""
from data.data_io import STORE


_DUPLICATE_FIELDS = (
    "claim_id", "hospital_id", "date_of_service", "lines", "decision",
)
_MAX_HISTORY_RECORDS = 5


def _duplicate_record(record: dict) -> dict:
    """Return only fields needed for a duplicate comparison.

    `member_id` is intentionally omitted from each nested record: the outer
    response identifies the requested member and V2 enforces that all nested
    records belong to that member. `decided_on` is not evidence for whether a
    claim is a duplicate, so it is not exposed to the model either.
    """
    return {field: record[field] for field in _DUPLICATE_FIELDS}


def get_claim_history(member_id: str) -> dict:
    """
    NAME+SIGNATURE  get_claim_history(member_id: str) -> ClaimHistoryV2
    WHAT            Returns only the requested member's already-decided
                    claims, in the minimum record shape needed to check an
                    exact duplicate. It does not disclose other members'
                    claims or unrelated administrative fields.
    INPUT           member_id: str. Unknown members are treated like a member
                    with no decided history: this is a normal "no duplicate"
                    result, not an error.
    RETURNS         {member_id, history_count, truncated, decided: [...]},
                    where each decided record is {claim_id, hospital_id,
                    date_of_service, lines, decision}. SIZE BOUND: at most
                    5 records; `truncated` says whether additional matching
                    records were withheld.
    FAILS WHEN      Never raises; an empty history returns history_count: 0
                    and "decided": [].
    IRREVERSIBLE?   No. Read-only.
    """
    matching = [
        record for record in STORE.decided_claims
        if record["member_id"] == member_id
    ]
    returned = matching[:_MAX_HISTORY_RECORDS]
    return {
        "member_id": member_id,
        "history_count": len(matching),
        "truncated": len(matching) > _MAX_HISTORY_RECORDS,
        "decided": [_duplicate_record(record) for record in returned],
    }
