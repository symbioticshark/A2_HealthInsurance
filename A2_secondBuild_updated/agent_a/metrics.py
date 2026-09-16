"""
Telemetry for every run, scripted or live -- the numbers you actually want
out of D4/D5/D6/D7, not just a pass/fail per case.

One JSONL row per RUN (one trial of one case), append-only, at
results/metrics_log.jsonl by default. Reading it back with summarize()
gives you:

  loops (turns)          -- median / mean / p90 / max, overall and per model
  ghost infinite loops    -- runs that hit the step cap or the dedup guard
                             without ever reaching a decision (NOT the same
                             as a genuine business-rule escalate -- see
                             is_ghost_loop below)
  human agency            -- how many runs needed operator confirmation
                             (autonomy=confirm) vs ran unattended (act),
                             and how many of those confirmations actually
                             happened (gate_confirmed)
  human handovers          -- escalate rate: the fraction of runs that ended
                             up with a person, genuine business reason or
                             guardrail catch, either way
  accuracy / hit rate      -- pass rate against expected_outcomes_A.json,
                             only computable when a label is supplied
  $/task                   -- mean cost_usd per run, and the three-layer
                             D6 breakdown if you pass a failure_cost_usd
  per-model comparison     -- turns/cost/pass-rate/ghost-loop-rate side by
                             side, which is exactly what D5(b) asks the
                             report to contain

The bundled model list and its offline fallback prices live in
model_catalog.json. The interactive runner refreshes those prices from
OpenRouter's official model catalog when available. Anything not in the
catalog falls back to
config.PRICE_TABLE's tier estimate (cheap/mid/frontier) and is FLAGGED as
an estimate, not measured, in the log row -- summarize() reports the two
separately so an estimate never silently blends into a "measured" figure.
"""
import json
import os
import platform
import shutil
import signal
import statistics as stats
import tempfile
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from . import config
from . import local_settings

MODEL_CATALOG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model_catalog.json"
)
_REMOTE_MODEL_PRICES = {}

LOG_PATH = os.environ.get("A2_METRICS_LOG", "results/metrics_log.jsonl")
SESSION_LOG_PATH = os.environ.get("A2_SESSION_LOG", "results/run_history.jsonl")
COMPARISON_PATH = os.environ.get("A2_COMPARISON_PATH", "results/comparison_report.json")


def configure_paths(output_dir: str):
    global LOG_PATH, SESSION_LOG_PATH, COMPARISON_PATH
    LOG_PATH = os.path.join(output_dir, "metrics_log.jsonl")
    SESSION_LOG_PATH = os.path.join(output_dir, "run_history.jsonl")
    COMPARISON_PATH = os.path.join(output_dir, "comparison_report.json")


def _load_bundled_model_prices():
    prices = {}
    try:
        with open(MODEL_CATALOG_PATH, encoding="utf-8") as handle:
            entries = json.load(handle).get("models", [])
    except (OSError, ValueError, AttributeError):
        return prices
    for entry in entries:
        try:
            prices[entry["id"]] = (
                float(entry["input_price_usd_per_million"]),
                float(entry["output_price_usd_per_million"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return prices


def set_remote_model_prices(entries, allowed_models=None):
    """Cache current OpenRouter prices in memory; never rewrite project files."""
    global _REMOTE_MODEL_PRICES
    allowed = set(allowed_models) if allowed_models is not None else None
    refreshed = {}
    for entry in entries:
        model = entry.get("id") or entry.get("canonical_slug")
        if not model or (allowed is not None and model not in allowed):
            continue
        pricing = entry.get("pricing") or {}
        try:
            refreshed[model] = (
                float(pricing["prompt"]) * 1_000_000,
                float(pricing["completion"]) * 1_000_000,
            )
        except (KeyError, TypeError, ValueError):
            continue
    _REMOTE_MODEL_PRICES = refreshed
    return len(refreshed)


def get_model_prices():
    prices = _load_bundled_model_prices()
    prices.update(_REMOTE_MODEL_PRICES)
    custom = local_settings.get_local_config_value("MODEL_CATALOG", {}) or {}
    for model, entry in custom.items():
        if isinstance(entry, dict):
            price_in = entry.get("input_price_usd_per_million")
            price_out = entry.get("output_price_usd_per_million")
        else:
            try:
                price_in, price_out = entry
            except (TypeError, ValueError):
                continue
        try:
            prices[model] = (float(price_in), float(price_out))
        except (TypeError, ValueError):
            continue
    return prices


def get_person_name(default: str = "anonymous") -> str:
    """Reads `name` from local_config.py (repo root, then parent dir --
    same search as the OpenRouter key). Used to namespace per-person
    result files so teammates running the same repo don't overwrite each
    other's results/*_run_log.json."""
    return local_settings.get_local_config_value("name", default=default)


def safe_filename(name: str) -> str:
    """Turns a person's name into a safe filename fragment -- lowercased,
    spaces to underscores, anything not alphanumeric/underscore stripped."""
    import re
    slug = re.sub(r"\s+", "_", name.strip().lower())
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    return slug or "anonymous"

# Which guardrail_stop values represent the loop genuinely failing to
# converge (a "ghost" run: it never produced a real decision, it just
# spun/blew its budget) as opposed to a legitimate, intentional early exit.
GHOST_LOOP_TRIGGERS = {"step_cap_hit", "duplicate_action", "budget_ceiling_hit", "no_action_no_final"}


def price_for_model(model: str, input_tokens: float, output_tokens: float):
    """Returns (cost_usd, is_measured_price: bool). is_measured_price is
    False when the model isn't in the model catalog and we fell back to a
    section-7 tier estimate -- summarize() uses this to keep guessed and
    real dollar figures from blending together."""
    prices = get_model_prices()
    if model in prices:
        price_in, price_out = prices[model]
        return (input_tokens * price_in + output_tokens * price_out) / 1_000_000, True
    price_in, price_out = config.PRICE_TABLE["cheap"]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000, False


def model_price_details(model: str):
    prices = get_model_prices()
    if model not in prices:
        return None
    price_in, price_out = prices[model]
    custom = local_settings.get_local_config_value("MODEL_CATALOG", {}) or {}
    if model in custom:
        source = "user_confirmed"
    elif model in _REMOTE_MODEL_PRICES:
        source = "openrouter_catalog"
    else:
        source = "bundled_catalog"
    return {
        "input_price_usd_per_million": price_in,
        "output_price_usd_per_million": price_out,
        "price_source": source,
    }


def atomic_write_json(path: str, value):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="a2_write_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def _safe_remove_tree(path: str, allowed_parent: str):
    resolved = os.path.abspath(path)
    parent = os.path.abspath(allowed_parent)
    if os.path.commonpath([resolved, parent]) != parent or resolved == parent:
        raise ValueError("Refusing to remove a path outside the transaction directory")
    if os.path.isdir(resolved):
        shutil.rmtree(resolved)


def begin_transaction(permanent_dir: str, run_id: str):
    in_progress = os.path.join(permanent_dir, ".in_progress")
    os.makedirs(in_progress, exist_ok=True)
    for name in os.listdir(in_progress):
        candidate = os.path.join(in_progress, name)
        if os.path.isdir(candidate):
            _safe_remove_tree(candidate, in_progress)
        else:
            os.unlink(candidate)
    staging = os.path.join(in_progress, run_id)
    os.makedirs(staging, exist_ok=False)
    return staging


def rollback_transaction(staging_dir: str, permanent_dir: str):
    in_progress = os.path.join(permanent_dir, ".in_progress")
    if os.path.isdir(staging_dir):
        _safe_remove_tree(staging_dir, in_progress)
    if os.path.isdir(in_progress) and not os.listdir(in_progress):
        os.rmdir(in_progress)


def _atomic_merge_text(source: str, destination: str):
    if not os.path.isfile(source):
        return
    old_text = ""
    if os.path.isfile(destination):
        with open(destination, encoding="utf-8") as handle:
            old_text = handle.read()
    with open(source, encoding="utf-8") as handle:
        new_text = handle.read()
    directory = os.path.dirname(destination) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="a2_merge_", suffix=".tmp", dir=directory, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(old_text)
            if old_text and not old_text.endswith("\n"):
                handle.write("\n")
            handle.write(new_text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def commit_transaction(staging_dir: str, permanent_dir: str):
    previous_handlers = {}
    for signal_name in ("SIGINT", "SIGBREAK"):
        sig = getattr(signal, signal_name, None)
        if sig is not None:
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, signal.SIG_IGN)
    try:
        os.makedirs(permanent_dir, exist_ok=True)
        for name in ("metrics_log.jsonl", "run_history.jsonl", "decision_ledger.jsonl"):
            _atomic_merge_text(os.path.join(staging_dir, name), os.path.join(permanent_dir, name))
        replace_names = [name for name in os.listdir(staging_dir) if name.endswith("_run_log.json")]
        replace_names.extend(name for name in os.listdir(staging_dir) if name.endswith("_result.json"))
        for name in replace_names:
            source = os.path.join(staging_dir, name)
            if os.path.isfile(source):
                destination = os.path.join(permanent_dir, name)
                with open(source, encoding="utf-8") as handle:
                    atomic_write_json(destination, json.load(handle))
        rollback_transaction(staging_dir, permanent_dir)
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


@dataclass
class RunMetrics:
    case_id: str
    model: str                     # "scripted" for the scripted backend, else the live model id
    backend: str
    autonomy: str
    tool_interface_version: str = "v2"
    decision: Optional[str] = None
    trigger: Optional[str] = None
    missing: Optional[str] = None
    turns: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    cost_is_measured: bool = True   # False = tier-estimated, not from a real price table entry
    cost_source: str = "estimated"
    wall_clock_seconds: float = 0.0
    gate_confirmed: Optional[bool] = None    # None = never reached the gate this run
    guardrail_stop: Optional[str] = None
    is_ghost_loop: bool = False
    human_handover: bool = False    # decision == "escalate" (any reason)
    label_pass: Optional[bool] = None   # filled in by the caller if a label exists
    ts: float = field(default_factory=time.time)

    def as_dict(self):
        return asdict(self)


def from_run_result(r, backend: str, model: str, label_pass: Optional[bool] = None,
                    tool_interface_version: str = "v2") -> RunMetrics:
    """Builds a RunMetrics row from a loop.RunResult -- the bridge between
    what run_case() returns and what gets logged."""
    is_ghost = bool(r.guardrail_stop) and r.guardrail_stop in GHOST_LOOP_TRIGGERS
    return RunMetrics(
        case_id=r.case_id, model=model, backend=backend, autonomy=r.autonomy,
        tool_interface_version=tool_interface_version,
        decision=r.decision, trigger=r.trigger, missing=r.missing, turns=r.turns,
        tokens_in=r.tokens_in, tokens_out=r.tokens_out, cost_usd=r.cost_usd,
        cached_input_tokens=getattr(r, "cached_input_tokens", 0),
        cache_write_tokens=getattr(r, "cache_write_tokens", 0),
        reasoning_tokens=getattr(r, "reasoning_tokens", 0),
        cost_is_measured=getattr(r, "cost_is_measured", backend == "live"),
        cost_source=getattr(r, "cost_source", "estimated"),
        wall_clock_seconds=getattr(r, "wall_clock_seconds", 0.0),
        gate_confirmed=getattr(r, "gate_confirmed", None),
        guardrail_stop=r.guardrail_stop, is_ghost_loop=is_ghost,
        human_handover=(r.decision == "escalate"), label_pass=label_pass,
    )


def log_run(m: RunMetrics, path: str = None):
    path = path or LOG_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(m.as_dict()) + "\n")


def load_log(path: str = None):
    path = path or LOG_PATH
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _pct(n, d):
    return (n / d * 100) if d else 0.0


def summarize(rows=None, path: str = None, model: str = None):
    """The dashboard. Pass `model` to filter to one model's rows only
    (used by the per-model comparison table below)."""
    rows = rows if rows is not None else load_log(path)
    if model:
        rows = [r for r in rows if r["model"] == model]
    n = len(rows)
    if n == 0:
        return {"runs": 0}

    turns = [r["turns"] for r in rows]
    costs = [r["cost_usd"] for r in rows]
    measured_costs = [r["cost_usd"] for r in rows if r.get("cost_is_measured")]
    ghost = [r for r in rows if r["is_ghost_loop"]]
    handovers = [r for r in rows if r["human_handover"]]
    asks = [r for r in rows if r["decision"] == "request_document"]
    approves = [r for r in rows if r["decision"] == "approve_in_principle"]
    confirm_needed = [r for r in rows if r["autonomy"] == "confirm" and r.get("gate_confirmed") is not None]
    confirmed = [r for r in confirm_needed if r.get("gate_confirmed")]
    labelled = [r for r in rows if r.get("label_pass") is not None]
    passed = [r for r in labelled if r["label_pass"]]

    def q(vals, p):
        if not vals:
            return None
        vals = sorted(vals)
        idx = min(len(vals) - 1, int(len(vals) * p))
        return vals[idx]

    return {
        "runs": n,
        "model": model or "ALL",
        "loops": {
            "mean": round(stats.mean(turns), 2), "median": stats.median(turns),
            "p90": q(turns, 0.90), "max": max(turns),
        },
        "ghost_infinite_loops": {
            "count": len(ghost), "rate_pct": round(_pct(len(ghost), n), 1),
            "triggers": sorted({r["guardrail_stop"] for r in ghost}),
        },
        "human_agency": {
            "runs_requiring_confirm_autonomy": len(confirm_needed),
            "confirmed_count": len(confirmed),
            "confirm_rate_pct": round(_pct(len(confirmed), len(confirm_needed)), 1) if confirm_needed else None,
        },
        "human_handovers": {
            "escalate_count": len(handovers), "escalate_rate_pct": round(_pct(len(handovers), n), 1),
            "ask_count": len(asks), "ask_rate_pct": round(_pct(len(asks), n), 1),
            "approve_count": len(approves), "approve_rate_pct": round(_pct(len(approves), n), 1),
        },
        "accuracy": {
            "labelled_runs": len(labelled),
            "hit_rate_pct": round(_pct(len(passed), len(labelled)), 1) if labelled else None,
        },
        "cost": {
            "mean_usd_per_task": round(stats.mean(costs), 5),
            "total_usd": round(sum(costs), 5),
            "measured_rows": len(measured_costs), "estimated_rows": n - len(measured_costs),
            "note": ("all costs are tier ESTIMATES (scripted backend) -- do not quote these "
                     "in the D6 report" if not measured_costs else
                     f"{len(measured_costs)}/{n} rows are real measured API costs"),
        },
        "wall_clock": {
            "mean_seconds_per_run": round(stats.mean([r.get("wall_clock_seconds", 0) for r in rows]), 3),
        },
    }


def print_report(rows=None, path: str = None):
    rows = rows if rows is not None else load_log(path)
    if not rows:
        print("No runs logged yet.")
        return

    overall = summarize(rows)
    print("=" * 70)
    print(f"METRICS REPORT -- {overall['runs']} run(s) logged")
    print("=" * 70)
    _print_block(overall)

    models = sorted({r["model"] for r in rows})
    if len(models) > 1:
        print()
        print("-" * 70)
        print("PER-MODEL COMPARISON")
        print("-" * 70)
        header = f"{'model':32s} {'runs':>5s} {'med turns':>10s} {'ghost%':>7s} {'hit%':>6s} {'$/task':>9s} {'escal%':>7s}"
        print(header)
        for m in models:
            s = summarize(rows, model=m)
            hit = s["accuracy"]["hit_rate_pct"]
            hit_str = f"{hit:.0f}" if hit is not None else "n/a"
            print(f"{m:32s} {s['runs']:5d} {s['loops']['median']:10} "
                  f"{s['ghost_infinite_loops']['rate_pct']:7.1f} {hit_str:>6s} "
                  f"{s['cost']['mean_usd_per_task']:9.5f} {s['human_handovers']['escalate_rate_pct']:7.1f}")


def _print_block(s):
    print(f"Model:                  {s['model']}")
    print(f"Loops (turns)           mean {s['loops']['mean']}  median {s['loops']['median']}  "
          f"p90 {s['loops']['p90']}  max {s['loops']['max']}")
    print(f"Ghost infinite loops    {s['ghost_infinite_loops']['count']} / {s['runs']} "
          f"({s['ghost_infinite_loops']['rate_pct']}%)  triggers: {s['ghost_infinite_loops']['triggers']}")
    ha = s["human_agency"]
    print(f"Human agency            {ha['confirmed_count']}/{ha['runs_requiring_confirm_autonomy']} "
          f"runs that reached the gate under confirm-autonomy were actually confirmed ({ha['confirm_rate_pct']}%)" if ha["runs_requiring_confirm_autonomy"]
          else "Human agency            no runs reached the gate under confirm-autonomy")
    hh = s["human_handovers"]
    print(f"Human handovers         escalate {hh['escalate_count']} ({hh['escalate_rate_pct']}%)  "
          f"ask {hh['ask_count']} ({hh['ask_rate_pct']}%)  approve {hh['approve_count']} ({hh['approve_rate_pct']}%)")
    acc = s["accuracy"]
    hit_str = f"{acc['hit_rate_pct']}%" if acc["hit_rate_pct"] is not None else "n/a (no labels)"
    print(f"Accuracy / hit rate     {hit_str}  ({acc['labelled_runs']} labelled run(s))")
    c = s["cost"]
    print(f"$/task                  mean ${c['mean_usd_per_task']:.5f}   total ${c['total_usd']:.5f}   {c['note']}")
    print(f"Wall clock              mean {s['wall_clock']['mean_seconds_per_run']}s/run")


# ===========================================================================
# SESSIONS -- one row per INVOCATION of eval_harness.main()/main.py
# (as opposed to RunMetrics above, which is one row per CASE TRIAL).
# A "run" in the sense the person running this means it: could be one
# case, could be all 38 -- every invocation gets logged here regardless,
# specifically so separate sessions (even on the same model) can be
# compared against each other, e.g. before/after a prompt fix.
# ===========================================================================
@dataclass
class SessionSummary:
    session_id: str
    person: str
    ts: float
    ts_iso: str
    backend: str
    model: str
    autonomy: str
    cases_requested: int
    trials_per_case: Optional[int]
    total_case_trials: int
    pass_rate_pct: Optional[float]
    labelled_trials: int
    mean_turns: float
    median_turns: float
    max_turns: int
    ghost_loop_rate_pct: float
    escalate_rate_pct: float
    ask_rate_pct: float
    approve_rate_pct: float
    mean_cost_usd: float
    total_cost_usd: float
    cost_is_measured: bool          # True only if every row this session was a real measured price
    mean_wall_clock_seconds: float
    total_wall_clock_seconds: float
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    python_version: str
    operating_system: str
    run_mode: str
    tool_interface_version: str
    trial_plan: dict = field(default_factory=dict)
    case_ids: list = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def build_session_summary(rows: list, person: str, backend: str, model: str, autonomy: str,
                           cases_requested: int, trials_per_case: Optional[int],
                           run_mode: str = "all", trial_plan: dict = None) -> SessionSummary:
    """rows: the list of per-trial dicts from THIS invocation only (not the
    whole historical log) -- eval_harness.py passes its own `rows` list."""
    import uuid

    n = len(rows)
    turns = [r["turns"] for r in rows] or [0]
    costs = [r["cost_usd"] for r in rows] or [0.0]
    wall_clocks = [r.get("wall_clock_seconds", 0.0) for r in rows] or [0.0]
    total_input_tokens = sum(r.get("tokens_in", 0) for r in rows)
    total_output_tokens = sum(r.get("tokens_out", 0) for r in rows)
    ghost = [r for r in rows if r.get("is_ghost_loop") or (r.get("guardrail_stop") in GHOST_LOOP_TRIGGERS)]
    escalates = [r for r in rows if r.get("decision") == "escalate"]
    asks = [r for r in rows if r.get("decision") == "request_document"]
    approves = [r for r in rows if r.get("decision") == "approve_in_principle"]
    labelled = [r for r in rows if r.get("pass") is not None]
    passed = [r for r in labelled if r.get("pass")]
    measured = [r for r in rows if r.get("cost_is_measured")]

    now = time.time()
    return SessionSummary(
        session_id=f"{int(now)}-{uuid.uuid4().hex[:8]}",
        person=person, ts=now, ts_iso=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
        backend=backend, model=model, autonomy=autonomy,
        cases_requested=cases_requested, trials_per_case=trials_per_case, total_case_trials=n,
        pass_rate_pct=round(_pct(len(passed), len(labelled)), 1) if labelled else None,
        labelled_trials=len(labelled),
        mean_turns=round(stats.mean(turns), 2), median_turns=stats.median(turns), max_turns=max(turns),
        ghost_loop_rate_pct=round(_pct(len(ghost), n), 1) if n else 0.0,
        escalate_rate_pct=round(_pct(len(escalates), n), 1) if n else 0.0,
        ask_rate_pct=round(_pct(len(asks), n), 1) if n else 0.0,
        approve_rate_pct=round(_pct(len(approves), n), 1) if n else 0.0,
        mean_cost_usd=round(stats.mean(costs), 5), total_cost_usd=round(sum(costs), 5),
        cost_is_measured=(len(measured) == n and n > 0),
        mean_wall_clock_seconds=round(stats.mean(wall_clocks), 3),
        total_wall_clock_seconds=round(sum(wall_clocks), 3),
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_tokens=total_input_tokens + total_output_tokens,
        python_version=platform.python_version(),
        operating_system=f"{platform.system()} {platform.release()}",
        run_mode=run_mode,
        tool_interface_version=(
            rows[0].get("tool_interface_version", "v2") if rows else "v2"
        ),
        trial_plan=trial_plan or {},
        case_ids=sorted({r["case_id"] for r in rows}),
    )


def build_key_result(rows: list, session: SessionSummary, app_version: str,
                     dataset_case_count: int, balance_context: dict = None):
    balance_context = balance_context or {}
    price = model_price_details(session.model) or {
        "input_price_usd_per_million": None,
        "output_price_usd_per_million": None,
        "price_source": "fallback_estimate",
    }
    failures = []
    cases = []
    expected_by_case = {
        row["case_id"]: row.get("expected_decision") for row in rows
    }
    has_unknown_request_cost = any(
        str(row.get("cost_source", "")).startswith("partial_")
        or row.get("cost_source") == "unavailable"
        for row in rows
    )
    for row in rows:
        compact = {
            "case_id": row["case_id"],
            "family": row.get("family"),
            "trial": row.get("trial"),
            "expected_decision": row.get("expected_decision"),
            "actual_decision": row.get("decision"),
            "pass": row.get("pass"),
            "trigger": row.get("trigger"),
            "missing": row.get("missing"),
            "turns": row.get("turns"),
            "wall_clock_seconds": row.get("wall_clock_seconds"),
            "input_tokens": row.get("tokens_in"),
            "output_tokens": row.get("tokens_out"),
            "cached_input_tokens": row.get("cached_input_tokens", 0),
            "cache_write_tokens": row.get("cache_write_tokens", 0),
            "reasoning_tokens": row.get("reasoning_tokens", 0),
            "cost_usd": row.get("cost_usd"),
            "cost_is_measured": row.get("cost_is_measured"),
            "cost_source": row.get("cost_source", "estimated"),
            "guardrail_stop": row.get("guardrail_stop"),
            "evidence": row.get("evidence", []),
        }
        cases.append(compact)
        if not row.get("pass") or row.get("guardrail_stop"):
            failures.append({key: compact[key] for key in (
                "case_id", "trial", "expected_decision", "actual_decision", "pass",
                "trigger", "guardrail_stop", "turns", "wall_clock_seconds",
                "input_tokens", "output_tokens", "cost_usd",
            )})

    summary = {
        "total_runs": session.total_case_trials,
        "passed_runs": sum(1 for row in rows if row.get("pass")),
        "failed_runs": sum(1 for row in rows if not row.get("pass")),
        "accuracy_pct": session.pass_rate_pct,
        "total_wall_clock_seconds": session.total_wall_clock_seconds,
        "mean_seconds_per_run": session.mean_wall_clock_seconds,
        "total_input_tokens": session.total_input_tokens,
        "total_output_tokens": session.total_output_tokens,
        "total_tokens": session.total_tokens,
        "total_cached_input_tokens": sum(row.get("cached_input_tokens", 0) for row in rows),
        "total_cache_write_tokens": sum(row.get("cache_write_tokens", 0) for row in rows),
        "total_reasoning_tokens": sum(row.get("reasoning_tokens", 0) for row in rows),
        "total_cost_usd": session.total_cost_usd,
        "mean_cost_usd": session.mean_cost_usd,
        "api_reported_cost_runs": sum(
            1 for row in rows if row.get("cost_source") == "openrouter_usage"
        ),
        "fallback_cost_runs": sum(
            1 for row in rows if row.get("cost_source") == "token_price_fallback"
        ),
        "partial_or_unavailable_cost_runs": sum(
            1 for row in rows
            if str(row.get("cost_source", "")).startswith("partial_")
            or row.get("cost_source") == "unavailable"
        ),
        "approve_count": sum(1 for row in rows if row.get("decision") == "approve_in_principle"),
        "request_document_count": sum(1 for row in rows if row.get("decision") == "request_document"),
        "escalate_count": sum(1 for row in rows if row.get("decision") == "escalate"),
        "guardrail_stop_count": sum(1 for row in rows if row.get("guardrail_stop")),
        "ghost_loop_count": sum(1 for row in rows if row.get("is_ghost_loop")),
        "expected_approve_count": sum(1 for row in rows if row.get("expected_decision") == "approve_in_principle"),
        "expected_request_document_count": sum(1 for row in rows if row.get("expected_decision") == "request_document"),
        "expected_escalate_count": sum(1 for row in rows if row.get("expected_decision") == "escalate"),
        "unique_case_count": len(expected_by_case),
        "expected_approve_case_count": sum(
            1 for value in expected_by_case.values() if value == "approve_in_principle"
        ),
        "expected_request_document_case_count": sum(
            1 for value in expected_by_case.values() if value == "request_document"
        ),
        "expected_escalate_case_count": sum(
            1 for value in expected_by_case.values() if value == "escalate"
        ),
    }
    environment = {
        "run_id": session.session_id,
        "timestamp": session.ts_iso,
        "tester": session.person,
        "app_version": app_version,
        "python_version": session.python_version,
        "operating_system": session.operating_system,
        "backend": session.backend,
        "model": session.model,
        "run_mode": session.run_mode,
        "tool_interface_version": session.tool_interface_version,
        "autonomy": session.autonomy,
        "dataset_case_count": dataset_case_count,
        "selected_case_count": session.cases_requested,
        "trials_per_case": session.trials_per_case,
        "trial_plan": session.trial_plan,
        "cost_basis": (
            "partial_or_unavailable" if session.backend == "live" and has_unknown_request_cost
            else "openrouter_usage" if session.backend == "live" and session.cost_is_measured
            else "token_price_fallback" if session.backend == "live"
            else "scripted_estimate"
        ),
        **price,
        **balance_context,
    }
    return {
        "environment": environment,
        "summary": summary,
        "case_results": cases,
        "notable_failures": failures,
        "supporting_files": {
            "full_case_details": f"{safe_filename(session.person)}_run_log.json",
            "run_history": "run_history.jsonl",
            "model_comparison": "comparison_report.json",
            "decision_ledger": "decision_ledger.jsonl",
        },
    }


def log_session(s: SessionSummary, path: str = None):
    path = path or SESSION_LOG_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(s.as_dict()) + "\n")


def load_sessions(path: str = None):
    path = path or SESSION_LOG_PATH
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_all_metrics(results_root: str):
    """Load per-run metrics from the shared baseline and tester folders."""
    paths = [os.path.join(results_root, "metrics_log.jsonl")]
    if os.path.isdir(results_root):
        paths.extend(
            os.path.join(entry.path, "metrics_log.jsonl")
            for entry in os.scandir(results_root) if entry.is_dir()
        )
    rows = []
    for path in paths:
        rows.extend(load_log(path))
    return rows


def load_all_key_results(results_root: str):
    """Load the latest distilled result for every tester."""
    results = []
    if not os.path.isdir(results_root):
        return results
    for entry in os.scandir(results_root):
        if not entry.is_dir():
            continue
        for name in os.listdir(entry.path):
            if not name.endswith("_result.json"):
                continue
            path = os.path.join(entry.path, name)
            try:
                with open(path, encoding="utf-8") as handle:
                    results.append(json.load(handle))
            except (OSError, ValueError):
                continue
    return results


def load_all_sessions(results_root: str):
    """Load the shared baseline plus each tester's run history."""
    paths = [os.path.join(results_root, "run_history.jsonl")]
    if os.path.isdir(results_root):
        paths.extend(
            os.path.join(entry.path, "run_history.jsonl")
            for entry in os.scandir(results_root) if entry.is_dir()
        )
    sessions = []
    for path in paths:
        sessions.extend(load_sessions(path))
    return sessions


def _session_sort_key(s):
    """Higher pass rate first; unlabelled sessions (pass_rate_pct is None)
    sort after every labelled one. Ties broken by lower ghost-loop rate,
    then lower mean cost."""
    pass_rate = s["pass_rate_pct"] if s["pass_rate_pct"] is not None else -1
    return (-pass_rate, s["ghost_loop_rate_pct"], s["mean_cost_usd"])


def best_run_per_model(sessions: list = None):
    """One SessionSummary dict per model -- the best-scoring session that
    model has logged, by pass rate first, ghost-loop rate and cost as
    tie-breakers. This is what `main.py metrics` uses for its headline
    per-model comparison."""
    sessions = sessions if sessions is not None else load_sessions()
    by_model = {}
    for s in sessions:
        m = s["model"]
        if m not in by_model or _session_sort_key(s) < _session_sort_key(by_model[m]):
            by_model[m] = s
    return by_model


def write_comparison_report(path: str = None):
    """Regenerates results/comparison_report.json from the FULL session
    history -- every session ever logged, most recent first, plus the
    best-per-model summary. Called automatically at the end of every
    eval_harness.py run, so it's always current."""
    path = path or COMPARISON_PATH
    sessions = load_sessions()
    sessions_sorted = sorted(sessions, key=lambda s: s["ts"], reverse=True)
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_sessions_logged": len(sessions),
        "best_run_per_model": best_run_per_model(sessions),
        "all_sessions_most_recent_first": sessions_sorted,
    }
    atomic_write_json(path, report)
    return report


def print_comparison(sessions: list = None):
    """Console view of results/run_history.jsonl -- every session, most
    recent first, so you can see run-over-run change even on the same
    model (e.g. before/after a prompt fix)."""
    sessions = sessions if sessions is not None else load_sessions()
    if not sessions:
        print("No sessions logged yet -- run `python3 main.py eval` or `live` at least once.")
        return

    sessions_sorted = sorted(sessions, key=lambda s: s["ts"], reverse=True)
    print("=" * 108)
    print(f"RUN HISTORY -- {len(sessions)} session(s) logged, most recent first")
    print("=" * 108)
    header = (f"{'when':19s} {'person':10s} {'tool':>4s} {'model':28s} {'runs':>6s} {'pass%':>6s} "
              f"{'med.turns':>9s} {'ghost%':>6s} {'$/task':>9s} {'avg s/case':>10s}")
    print(header)
    for s in sessions_sorted:
        pass_str = f"{s['pass_rate_pct']:.0f}" if s["pass_rate_pct"] is not None else "n/a"
        tool_version = str(s.get("tool_interface_version", "v2")).upper()
        print(f"{s['ts_iso']:19s} {s['person']:10s} {tool_version:>4s} {s['model']:28s} {s['total_case_trials']:6d} "
              f"{pass_str:>6s} {s['median_turns']:9} {s['ghost_loop_rate_pct']:6.1f} "
              f"{s['mean_cost_usd']:9.5f} {s['mean_wall_clock_seconds']:10.2f}")

    print()
    print("-" * 108)
    print("BEST SESSION PER MODEL (highest pass rate, ties broken by lowest ghost-loop rate then lowest cost)")
    print("-" * 108)
    best = best_run_per_model(sessions)
    print(header)
    for model, s in best.items():
        pass_str = f"{s['pass_rate_pct']:.0f}" if s["pass_rate_pct"] is not None else "n/a"
        tool_version = str(s.get("tool_interface_version", "v2")).upper()
        print(f"{s['ts_iso']:19s} {s['person']:10s} {tool_version:>4s} {s['model']:28s} {s['total_case_trials']:6d} "
              f"{pass_str:>6s} {s['median_turns']:9} {s['ghost_loop_rate_pct']:6.1f} "
              f"{s['mean_cost_usd']:9.5f} {s['mean_wall_clock_seconds']:10.2f}")
