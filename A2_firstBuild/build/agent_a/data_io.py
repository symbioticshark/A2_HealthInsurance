"""
Loads the Problem A fixture files and builds simple id -> record indices.

Nothing here is agent logic. It is the "database" the tools sit in front of.
Point DATA_DIR at wherever make_fixtures_A.py wrote data_A/ (after you have
run it with your EXTRA_* additions merged in).
"""
import json
import os

DATA_DIR = os.environ.get("A2_reference_data", os.path.join(os.path.dirname(__file__), "..", "data_A"))


def _load(name):
    path = os.path.join(DATA_DIR, name)
    with open(path, "r") as f:
        return json.load(f)


class DataStore:
    """Loaded once per process. Read-only. No tool may mutate these dicts
    directly -- the gated action writes to a separate ledger file instead."""

    def __init__(self, data_dir: str = None):
        global DATA_DIR
        if data_dir:
            DATA_DIR = data_dir

        self.claims = {c["claim_id"]: c for c in _load("claims.json")}
        self.members = {m["member_id"]: m for m in _load("members.json")}
        self.policies = {p["policy_id"]: p for p in _load("policies.json")}
        self.procedures = {p["code"]: p for p in _load("procedures.json")}
        self.hospitals = {h["hospital_id"]: h for h in _load("hospitals.json")}

        self.preauths = _load("preauthorisations.json")  # list, may have several per member
        self.required_docs = {d["procedure_code"]: d["document"] for d in _load("required_documents.json")}
        self.decided_claims = _load("decided_claims.json")  # list

    def all_case_ids(self):
        return list(self.claims.keys())


STORE = DataStore()
