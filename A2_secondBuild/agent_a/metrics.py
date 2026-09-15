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

MODEL_PRICES is the one thing you need to keep current yourself -- prices
move. Verify against https://openrouter.ai/models before trusting a $/task
number in your report. Anything not in this table falls back to
config.PRICE_TABLE's tier estimate (cheap/mid/frontier) and is FLAGGED as
an estimate, not measured, in the log row -- summarize() reports the two
separately so an estimate never silently blends into a "measured" figure.
"""
import json
import os
import statistics as stats
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from . import config
from . import local_settings

# USD per million tokens (input, output). Checked against openrouter.ai/models
# -- fill in / correct entries for whatever you actually run in your battery.
MODEL_PRICES = {
    "anthropic/claude-3-5-haiku": (0.80, 4.00),
    "anthropic/claude-3-haiku":   (0.25, 1.25),
    "openai/gpt-4o-mini":         (0.15, 0.60),
    "google/gemini-2.5-flash":    (0.30, 2.50),
    # add your D5(b) battery's models here, with real numbers, before
    # trusting the $/task figures in your report.
}

LOG_PATH = os.environ.get("A2_METRICS_LOG", "results/metrics_log.jsonl")
SESSION_LOG_PATH = os.environ.get("A2_SESSION_LOG", "results/run_history.jsonl")
COMPARISON_PATH = os.environ.get("A2_COMPARISON_PATH", "results/comparison_report.json")


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
    False when the model isn't in MODEL_PRICES and we fell back to a
    section-7 tier estimate -- summarize() uses this to keep guessed and
    real dollar figures from blending together."""
    if model in MODEL_PRICES:
        price_in, price_out = MODEL_PRICES[model]
        return (input_tokens * price_in + output_tokens * price_out) / 1_000_000, True
    price_in, price_out = config.PRICE_TABLE["cheap"]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000, False


@dataclass
class RunMetrics:
    case_id: str
    model: str                     # "scripted" for the scripted backend, else the live model id
    backend: str
    autonomy: str
    decision: Optional[str] = None
    trigger: Optional[str] = None
    missing: Optional[str] = None
    turns: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cost_is_measured: bool = True   # False = tier-estimated, not from a real price table entry
    wall_clock_seconds: float = 0.0
    gate_confirmed: Optional[bool] = None    # None = never reached the gate this run
    guardrail_stop: Optional[str] = None
    is_ghost_loop: bool = False
    human_handover: bool = False    # decision == "escalate" (any reason)
    label_pass: Optional[bool] = None   # filled in by the caller if a label exists
    ts: float = field(default_factory=time.time)

    def as_dict(self):
        return asdict(self)


def from_run_result(r, backend: str, model: str, label_pass: Optional[bool] = None) -> RunMetrics:
    """Builds a RunMetrics row from a loop.RunResult -- the bridge between
    what run_case() returns and what gets logged."""
    is_ghost = bool(r.guardrail_stop) and r.guardrail_stop in GHOST_LOOP_TRIGGERS
    return RunMetrics(
        case_id=r.case_id, model=model, backend=backend, autonomy=r.autonomy,
        decision=r.decision, trigger=r.trigger, missing=r.missing, turns=r.turns,
        tokens_in=r.tokens_in, tokens_out=r.tokens_out, cost_usd=r.cost_usd,
        cost_is_measured=getattr(r, "cost_is_measured", backend == "live"),
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
    trials_per_case: int
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
    case_ids: list = field(default_factory=list)

    def as_dict(self):
        return asdict(self)


def build_session_summary(rows: list, person: str, backend: str, model: str, autonomy: str,
                           cases_requested: int, trials_per_case: int) -> SessionSummary:
    """rows: the list of per-trial dicts from THIS invocation only (not the
    whole historical log) -- eval_harness.py passes its own `rows` list."""
    import uuid

    n = len(rows)
    turns = [r["turns"] for r in rows] or [0]
    costs = [r["cost_usd"] for r in rows] or [0.0]
    wall_clocks = [r.get("wall_clock_seconds", 0.0) for r in rows] or [0.0]
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
        case_ids=sorted({r["case_id"] for r in rows}),
    )


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
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
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
    print("=" * 100)
    print(f"RUN HISTORY -- {len(sessions)} session(s) logged, most recent first")
    print("=" * 100)
    header = (f"{'when':19s} {'person':10s} {'model':28s} {'cases':>6s} {'pass%':>6s} "
              f"{'med.turns':>9s} {'ghost%':>6s} {'$/task':>9s} {'avg s/case':>10s}")
    print(header)
    for s in sessions_sorted:
        pass_str = f"{s['pass_rate_pct']:.0f}" if s["pass_rate_pct"] is not None else "n/a"
        print(f"{s['ts_iso']:19s} {s['person']:10s} {s['model']:28s} {s['total_case_trials']:6d} "
              f"{pass_str:>6s} {s['median_turns']:9} {s['ghost_loop_rate_pct']:6.1f} "
              f"{s['mean_cost_usd']:9.5f} {s['mean_wall_clock_seconds']:10.2f}")

    print()
    print("-" * 100)
    print("BEST SESSION PER MODEL (highest pass rate, ties broken by lowest ghost-loop rate then lowest cost)")
    print("-" * 100)
    best = best_run_per_model(sessions)
    print(header)
    for model, s in best.items():
        pass_str = f"{s['pass_rate_pct']:.0f}" if s["pass_rate_pct"] is not None else "n/a"
        print(f"{s['ts_iso']:19s} {s['person']:10s} {s['model']:28s} {s['total_case_trials']:6d} "
              f"{pass_str:>6s} {s['median_turns']:9} {s['ghost_loop_rate_pct']:6.1f} "
              f"{s['mean_cost_usd']:9.5f} {s['mean_wall_clock_seconds']:10.2f}")
