# PE6201 A2 — Problem A agent (Health-insurance claim first response)

Tested end to end against the shipped 15 cases **and** the 23 extended
cases from the earlier data-extension pass (38 cases, 3 trials each = 114
runs, 100% pass on the scripted backend). Nothing here has touched a
network or an API key.

## Get it running

```bash
# 1. Put the fixture data where data_io.py expects it (or set A2_DATA_DIR)
cp -r /path/to/A2_reference_data/data_A .
cp /path/to/A2_reference_data/expected_outcomes_A.json .

# 2. Run the harness -- BACKEND="scripted" is the default, no key needed
python3 eval_harness.py --verbose --trials 3

# 3. See both required D7 failures reproduce
python3 -m agent_a.failures

# 4. (Optional, needs OPENROUTER_API_KEY + real internet) the live battery
A2_BACKEND=live A2_MODEL=anthropic/claude-3-5-haiku python3 eval_harness.py --cases CLM-8850
```

## What's in `agent_a/`

| File | Deliverable | What it is |
|---|---|---|
| `data_io.py` | — | loads `data_A/*.json` into read-only indices |
| `tools.py` | D2 | the 7 tools (6 read-only + the gated write), each with a full six-field descriptor contract, 2 poka-yoke moves |
| `guardrails.py` | D3(a) | step cap, budget ceiling, action dedup, autonomy gate, narrative injection scan |
| `scripted_backend.py` | D5(a) | deterministic rule table standing in for a live model — this is what BACKEND="scripted" runs |
| `live_backend.py` | D5(b) | the one function that knows OpenRouter exists; text-based Action-block parsing for real models |
| `config.py` | — | the single BACKEND/MODEL/BASE_URL block; price tiers; reasoning cap |
| `loop.py` | D1 + D2(c) | the actual ReAct loop — Thought→Action(≥1 tool)→Observation→repeat→Final, same code path regardless of backend |
| `cost_model.py` | D6 | three-layer cost model, sensitivity table, break-even formula |
| `failures.py` | D7 | both required failure reproductions, each built as "the working agent, minus X" |
| `eval_harness.py` | D4 | multi-trial, outcome-graded, isolated evaluation runner |

## Design choices you'll want to defend in the report

- **check_coverage and get_preauthorisation key on `member_id`, not
  `policy_id`.** This removes their dependency on `lookup_policy`'s output,
  which is what lets Turn 2 batch `lookup_policy || get_hospital_status ||
  get_claim_history || check_coverage×N` as one genuinely parallel call —
  see D2(c)'s dependency rule, documented at the top of `scripted_backend.py`.
- **Autonomy = `confirm`**, gate placed inside `issue_decision_letter`
  itself (not merely "before calling it" in the loop) — see the docstring
  in `tools.py`. `run_case(..., auto_confirm=True)` stands in for the
  operator during automated eval runs; a real deployment would pause here.
- **Injection scan runs right after Turn 1**, before Turn 2 is even
  planned — the cheapest possible exit, since a hostile narrative is
  already in hand from `get_claim`. Turns for these cases are 1, not 2.
- **Turn 2's batch fires `check_coverage` even on claims that turn out to
  be policy-disqualified** (lapsed / outside dates / over limit /
  duplicate) — an honest limit, spelled out in `scripted_backend.py`'s
  docstring, worth a line in Section 4 of the report (D2c's "two honest
  limits" ask).
- **Step cap = 6**, set from the evidence in `guardrails.py`'s comment
  (median legitimate run 3–4 turns, worst legitimate run 4). `failures.py`
  shows what removing it looks like: 40 turns, no answer, on a case that
  should have stopped at 3.
- **Cost figures from `eval_harness.py`/`cost_model.estimate_tokens_for_run`
  are a MODEL** (Class 5's B·T + D·T(T−1)/2 formula), used only for the
  scripted backend's own budget-ceiling bookkeeping. For the report's D6
  numbers, use `cost_model.cost_from_measured(...)` fed with the actual
  `usage` fields `live_backend.call_model` returns from the three-model
  battery — the brief is explicit that the report must use measured
  tokens, not estimated ones.

## What's NOT done for you

- The live battery has not been run in this environment (no network
  egress here to openrouter.ai) — `live_backend.py` is written and the
  Action-block format it expects is documented in its
  `SYSTEM_PROMPT_TEMPLATE`, but you should smoke-test it yourself with
  `OPENROUTER_API_KEY` set before relying on it for D5(b).
- `TOOL_SCORING` at the bottom of `tools.py` is filled in with a first
  pass at the D2(a) three-question table — read it, don't just paste it;
  the mark is for the reasoning, not the table.
- The descriptor-rewrite measurement D2(b) asks for (tokens/pass-rate/
  guardrail-cases, v1 vs v2) is scaffolded by `failures.py`'s
  `get_claim_history_v1` vs the real `get_claim_history` — run
  `demo_failure_2()` and drop its numbers into that section; it currently
  reports token counts and one correctness case, not a full pass-rate
  sweep.
- D0 (why an agent at all) is writing, not code — nothing here does that
  for you, deliberately.
