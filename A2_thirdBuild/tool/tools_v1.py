"""D2(b) measurement interface: the deliberately broad V1 history tool."""
from data.data_io import STORE


def get_claim_history(member_id: str) -> dict:
    """
    NAME+SIGNATURE  get_claim_history(member_id: str) -> ClaimHistoryV1
    WHAT            V1 measurement interface. Returns every decided claim in
                    the fixture, regardless of which member is being
                    assessed. This makes duplicate evidence broad, costly,
                    and easy to misuse.
    INPUT           member_id: str. It is echoed in the response but does not
                    constrain the records returned.
    RETURNS         {member_id, decided: [...]} containing every decided
                    claim in its original record shape. SIZE BOUND: none;
                    payload grows with the whole decided-claims store.
    FAILS WHEN      Never raises; an empty store returns "decided": [].
    IRREVERSIBLE?   No. Read-only.
    """
    return {"member_id": member_id, "decided": list(STORE.decided_claims)}
