#!/usr/bin/env python3
"""
D2(b) -- the "tokens returned per call" half of the required v1-vs-v2
measurement, across every member that actually appears in the shipped
40-case evaluation set (failures.demo_failure_2() only ever measured one
hand-picked case; this generalises it to the whole set).

No live model, no API key, no cost: get_claim_history's OUTPUT does not
depend on which model is asking for it, only on the fixture data and
which interface version is configured. This is why this half can be
measured for free. The V1/V2 evaluation pass-rate comparison is the
separate live battery; the D3 guardrail checklist remains a separate,
scripted regression test.
"""
import json
import os
import statistics as stats
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from eval import eval_harness
from tool import tools as T
from data.data_io import STORE


def _approx_tokens(obj):
    return len(json.dumps(obj)) // 4


def build_report():
    labels = eval_harness.load_labels()
    member_ids = sorted({
        STORE.claims[case_id]["member_id"]
        for case_id in labels if case_id in STORE.claims
    })

    rows = []
    for member_id in member_ids:
        v2 = T.get_claim_history(member_id)
        v1 = T.get_claim_history_v1(member_id)
        rows.append({
            "member_id": member_id,
            "v1_records_returned": len(v1["decided"]),
            "v2_records_returned": len(v2["decided"]),
            "v1_tokens": _approx_tokens(v1),
            "v2_tokens": _approx_tokens(v2),
        })

    v1_tokens = [r["v1_tokens"] for r in rows]
    v2_tokens = [r["v2_tokens"] for r in rows]
    v1_mean, v2_mean = stats.mean(v1_tokens), stats.mean(v2_tokens)

    return {
        "members_measured": len(rows), "per_member": rows,
        "mean_tokens_v1": round(v1_mean, 2), "mean_tokens_v2": round(v2_mean, 2),
        "max_tokens_v1": max(v1_tokens), "max_tokens_v2": max(v2_tokens),
        "mean_reduction_pct_v2_vs_v1": round((1 - v2_mean / v1_mean) * 100, 2),
    }


def main():
    report = build_report()
    print(f"{'member_id':<10}{'v1 records':<12}{'v2 records':<12}{'v1 tokens':<11}{'v2 tokens'}")
    for row in report["per_member"]:
        print(f"{row['member_id']:<10}{row['v1_records_returned']:<12}{row['v2_records_returned']:<12}"
              f"{row['v1_tokens']:<11}{row['v2_tokens']}")
    print()
    print(f"Members measured: {report['members_measured']}")
    print(f"Mean tokens per get_claim_history call -- v1: {report['mean_tokens_v1']:.1f}   "
          f"v2: {report['mean_tokens_v2']:.1f}")
    print(f"Max tokens per call                    -- v1: {report['max_tokens_v1']}   "
          f"v2: {report['max_tokens_v2']}")
    print(f"V2 reduces mean tool-return tokens by {report['mean_reduction_pct_v2_vs_v1']:.1f}%.")
    print("No standalone file was written; this measurement is embedded in the detailed V1/V2 comparison.")


if __name__ == "__main__":
    main()
