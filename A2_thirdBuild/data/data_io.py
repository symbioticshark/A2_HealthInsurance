"""Load the read-only Problem A fixture data used by the tool layer.

The third-build package is organised by responsibility, so the fixture files
live in ``data/data_A``.  Tools use the indexes below rather than reading JSON
directly; this keeps every backend on the same system of record.
"""
import json
import os


DATA_DIR = os.environ.get(
    "A2_DATA_DIR", os.path.join(os.path.dirname(__file__), "data_A")
)


def _load(name: str):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as handle:
        return json.load(handle)


class DataStore:
    """Immutable-by-convention fixture indexes for the Problem A tools."""

    def __init__(self, data_dir: str = None):
        global DATA_DIR
        if data_dir:
            DATA_DIR = data_dir

        self.claims = {row["claim_id"]: row for row in _load("claims.json")}
        self.members = {row["member_id"]: row for row in _load("members.json")}
        self.policies = {row["policy_id"]: row for row in _load("policies.json")}
        self.procedures = {row["code"]: row for row in _load("procedures.json")}
        self.hospitals = {row["hospital_id"]: row for row in _load("hospitals.json")}
        self.preauths = _load("preauthorisations.json")
        self.required_docs = {
            row["procedure_code"]: row["document"]
            for row in _load("required_documents.json")
        }
        self.decided_claims = _load("decided_claims.json")

    def all_case_ids(self):
        return list(self.claims)


STORE = DataStore()
