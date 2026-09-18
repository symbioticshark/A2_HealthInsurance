"""Compatibility-first session views over 2.5 and 3.0 result files.

The three JSONL files remain the historical source of truth.  This module
never rewrites them.  New 3.0 metric rows carry a session_id directly; legacy
2.5 rows are associated with run_history sessions by their append order and
validated row counts/model/interface metadata.
"""
import json
import os
from collections import Counter, defaultdict


def _load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def _load_jsonl(path):
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    rows.append({"_load_error": f"invalid JSON on line {line_number}"})
                    continue
                row["_source_line"] = line_number
                rows.append(row)
    except OSError:
        pass
    return rows


def _infer_trials(rows):
    counts = defaultdict(int)
    inferred = []
    for original in rows:
        row = dict(original)
        case_id = row.get("case_id")
        if row.get("trial") is None and case_id:
            row["trial"] = counts[case_id]
        if case_id:
            counts[case_id] += 1
        if "pass" not in row:
            row["pass"] = row.get("label_pass")
        if "actual_decision" not in row:
            row["actual_decision"] = row.get("decision")
        inferred.append(row)
    return inferred


def _chunk_matches_session(rows, session):
    if len(rows) != int(session.get("total_case_trials") or 0):
        return False
    checks = (
        ("model", session.get("model")),
        ("backend", session.get("backend")),
        ("tool_interface_version", session.get("tool_interface_version")),
    )
    for field, expected in checks:
        observed = {row.get(field) for row in rows if row.get(field) is not None}
        if expected is not None and observed and observed != {expected}:
            return False
    expected_cases = set(session.get("case_ids") or [])
    observed_cases = {row.get("case_id") for row in rows if row.get("case_id")}
    return not expected_cases or observed_cases == expected_cases


def _merge_detailed_rows(metric_rows, detailed_rows, session_id):
    detailed_rows = _infer_trials(detailed_rows or [])
    details = {(row.get("case_id"), row.get("trial")): row for row in detailed_rows}
    merged = []
    for metric in _infer_trials(metric_rows):
        key = (metric.get("case_id"), metric.get("trial"))
        row = dict(metric)
        row.update(details.get(key, {}))
        row["session_id"] = session_id
        merged.append(row)
    return merged


def load_tester_sessions(tester_dir):
    """Return sessions oldest-first, with private _rows/_result metadata.

    Legacy source files are read only.  A failed legacy association is exposed
    through _mapping_status instead of being guessed.
    """
    history_path = os.path.join(tester_dir, "run_history.jsonl")
    metrics_path = os.path.join(tester_dir, "metrics_log.jsonl")
    sessions = [row for row in _load_jsonl(history_path) if not row.get("_load_error")]
    metric_rows = [row for row in _load_jsonl(metrics_path) if not row.get("_load_error")]

    exact = defaultdict(list)
    legacy = []
    for row in metric_rows:
        if row.get("session_id"):
            exact[row["session_id"]].append(row)
        else:
            legacy.append(row)

    legacy_cursor = 0
    mapped = []
    for original in sessions:
        session = dict(original)
        session_id = session.get("session_id")
        direct_rows = exact.get(session_id, [])
        if direct_rows:
            rows = _infer_trials(direct_rows)
            status = "exact_session_id"
        else:
            count = int(session.get("total_case_trials") or 0)
            candidate = legacy[legacy_cursor:legacy_cursor + count]
            if count and _chunk_matches_session(candidate, session):
                rows = _infer_trials(candidate)
                for row in rows:
                    row["session_id"] = session_id
                    row["session_id_source"] = "legacy_order_validated"
                status = "legacy_order_validated"
                legacy_cursor += count
            else:
                rows = []
                status = "incomplete_unmatched"
        session["_rows"] = rows
        session["_mapping_status"] = status
        session["_tester_dir"] = tester_dir
        mapped.append(session)

    # Attach the latest detailed snapshot by its explicit result run_id.
    result_files = [
        os.path.join(tester_dir, name) for name in os.listdir(tester_dir)
        if name.endswith("_result.json")
    ] if os.path.isdir(tester_dir) else []
    by_id = {session.get("session_id"): session for session in mapped}
    for result_path in result_files:
        result = _load_json(result_path, {}) or {}
        run_id = (result.get("environment") or {}).get("run_id")
        session = by_id.get(run_id)
        if not session:
            continue
        supporting = result.get("supporting_files") or {}
        run_log_name = supporting.get("full_case_details")
        if not run_log_name:
            stem = os.path.basename(result_path).replace("_result.json", "")
            run_log_name = f"{stem}_run_log.json"
        detailed = _load_json(os.path.join(tester_dir, run_log_name), []) or []
        if len(detailed) == int(session.get("total_case_trials") or -1):
            session["_rows"] = _merge_detailed_rows(session["_rows"], detailed, run_id)
            session["_detail_level"] = "full_latest_snapshot"
        else:
            session["_detail_level"] = "metrics_only"
        session["_result"] = result
        session["_result_path"] = result_path

    for session in mapped:
        session.setdefault("_detail_level", "metrics_only" if session["_rows"] else "summary_only")
    return mapped


def load_all_sessions(results_root):
    sessions = []
    if not os.path.isdir(results_root):
        return sessions
    for entry in os.scandir(results_root):
        if not entry.is_dir():
            continue
        for session in load_tester_sessions(entry.path):
            session["_tester_slug"] = entry.name
            sessions.append(session)
    return sorted(sessions, key=lambda row: row.get("ts", 0), reverse=True)


def session_label(session, include_tester=True):
    tester = f"{session.get('person', session.get('_tester_slug', '?'))} | " if include_tester else ""
    model = session.get("model", "unknown")
    version = str(session.get("tool_interface_version", "?")).upper()
    timestamp = session.get("ts_iso", "unknown time")
    runs = session.get("total_case_trials", 0)
    cases = session.get("cases_requested", 0)
    pass_rate = session.get("pass_rate_pct")
    pass_text = "n/a" if pass_rate is None else f"{pass_rate:.1f}%"
    short_id = str(session.get("session_id", "unknown"))[-12:]
    return (
        f"{timestamp} | {tester}{model} | {version} | "
        f"{cases} cases/{runs} runs | pass {pass_text} | ...{short_id}"
    )


def session_by_id(sessions, session_id):
    for session in sessions:
        if session.get("session_id") == session_id:
            return session
    return None


def compatibility_issues(left, right, v1_v2=False):
    issues = []
    if len(left.get("_rows", [])) != int(left.get("total_case_trials") or 0):
        issues.append("left session has incomplete case metrics")
    if len(right.get("_rows", [])) != int(right.get("total_case_trials") or 0):
        issues.append("right session has incomplete case metrics")
    for field, label in (
        ("model", "model"),
        ("backend", "backend"),
        ("case_ids", "case set"),
        ("trial_plan", "trial plan"),
        ("total_case_trials", "run count"),
    ):
        if left.get(field) != right.get(field):
            issues.append(f"different {label}")
    if v1_v2:
        versions = {
            str(left.get("tool_interface_version", "")).lower(),
            str(right.get("tool_interface_version", "")).lower(),
        }
        if versions != {"v1", "v2"}:
            issues.append("sessions are not one V1 and one V2")
    return issues


def compare_sessions(left, right):
    left_rows = {(row.get("case_id"), row.get("trial")): row for row in left.get("_rows", [])}
    right_rows = {(row.get("case_id"), row.get("trial")): row for row in right.get("_rows", [])}
    keys = sorted(set(left_rows) | set(right_rows), key=lambda key: (str(key[0]), key[1] or 0))
    comparisons = []
    changes = Counter()
    for key in keys:
        a = left_rows.get(key)
        b = right_rows.get(key)
        if a is None:
            outcome = "only_in_right"
        elif b is None:
            outcome = "only_in_left"
        elif not a.get("pass") and b.get("pass"):
            outcome = "fail_to_pass"
        elif a.get("pass") and not b.get("pass"):
            outcome = "pass_to_fail"
        elif a.get("pass") and b.get("pass"):
            outcome = "both_pass"
        else:
            outcome = "both_fail"
        changes[outcome] += 1
        comparisons.append({
            "case_id": key[0], "trial": key[1], "outcome": outcome,
            "left": a, "right": b,
            "token_delta_right_minus_left": (
                (b.get("tokens_in", 0) + b.get("tokens_out", 0))
                - (a.get("tokens_in", 0) + a.get("tokens_out", 0))
                if a is not None and b is not None else None
            ),
            "cost_delta_right_minus_left": (
                round(b.get("cost_usd", 0.0) - a.get("cost_usd", 0.0), 8)
                if a is not None and b is not None else None
            ),
            "time_delta_right_minus_left": (
                round(b.get("wall_clock_seconds", 0.0) - a.get("wall_clock_seconds", 0.0), 4)
                if a is not None and b is not None else None
            ),
        })
    return {
        "left_session_id": left.get("session_id"),
        "right_session_id": right.get("session_id"),
        "compatibility_warnings": compatibility_issues(left, right),
        "changes": dict(changes),
        "case_comparisons": comparisons,
    }
