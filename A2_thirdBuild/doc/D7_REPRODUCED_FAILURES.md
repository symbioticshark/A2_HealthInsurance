# D7 - Two Reproduced Failures

## Purpose

This document describes the two deterministic D7 failure reproductions for the
Problem A health-insurance agent. Each experiment follows the required
"working agent, minus X" method:

1. run the normal agent with one controlled element removed;
2. reproduce the failure on the scripted backend;
3. restore that single element;
4. rerun the same case through the same agent entry point; and
5. compare outcome, turns, tokens, estimated cost, trace, and pass status.

Both experiments call `agent.loop.run_case`. There is no separately written bad
agent. They require no API key and make no live-model request. D7 results are
kept outside tester histories, and approval writes are redirected to a temporary
ledger so neither the normal run history nor `decision_ledger.jsonl` is
contaminated.

Line references in this document refer to the repository version that generated
the results below. If the referenced source files are edited later, update the
line numbers before submission.

## How to run

From the `A2_thirdBuild` directory with the project environment activated:

```bash
# Run both experiments and write the combined report.
python run/run_d7_failures.py --failure all

# Run only the required loop-control failure.
python run/run_d7_failures.py --failure 1

# Run only the tool-interface failure.
python run/run_d7_failures.py --failure 2
```

The command-line entry point and selection logic are in
`run/run_d7_failures.py:75-128`. Detailed terminal explanation, before/after
metrics, full traces, and success checks are printed by
`run/run_d7_failures.py:24-73`.

Results are published atomically: the complete JSON is flushed to a temporary
file in the destination directory and then moved into place. An interruption
cannot replace a valid report with a partially written JSON document. This is
implemented in `agent/failures.py:255-272`.

The output files are:

```text
results/d7/failure_1_loop_control.json
results/d7/failure_2_tool_interface.json
results/d7/d7_summary.json
```

Running one failure overwrites only that failure's derived report. Running
`--failure all` also overwrites the combined derived summary. These reports are
reproducible outputs, not append-only tester history.

## Isolation and safety controls

The normal `run_case` signature keeps `d7_fault=None`, so ordinary scripted and
live calls retain the existing behaviour. The only registered fault is declared
at `agent/loop.py:85-90`. Unknown fault names are rejected, and any attempt to
use fault injection with the live backend raises `ValueError` before a model is
called (`agent/loop.py:101-113`).

The D7-only claim is loaded from `data/d7_fixtures.json:1-20`. It is installed
in the in-memory data store only for the duration of Failure 2 and is restored
in a `finally` block (`agent/failures.py:112-123`). The temporary decision
ledger is installed and restored by `agent/failures.py:126-135`.

These controls mean that D7 does not alter:

- the 40-case evaluation set;
- any tester's `run_history.jsonl` or `metrics_log.jsonl`;
- the shared decision ledger;
- the selected tool interface after the experiment; or
- any live-model result.

## Failure 1 - Loop control

### Layer

**Code layer - loop control.**

The failure is not caused by a bad tool observation or an ambiguous prompt. The
agent has already reached a complete `request_document` outcome. The deleted
element is the terminal exit that returns that outcome to the caller.

### Case and expected behaviour

- Case: `CLM-8888`
- Backend: scripted
- Expected decision: `request_document`
- Missing item: a valid pre-authorisation reference for procedure `62480`

### Controlled deletion

The normal terminal handling is at `agent/loop.py:228-257`. Once
`resolve_lines` returns an `ask`, lines 253-257 record and return the final
decision.

The D7 switch at `agent/loop.py:232-252` omits that exit and repeatedly
re-evaluates the already-complete cached outcome. It does not make another tool
call. This is a useful loop shape because action de-duplication cannot detect
it: there is no duplicate action signature. The agent simply fails to conclude.

The broken and fixed executions are invoked through the same `run_case` entry
point in `agent/failures.py:138-181`. The only difference is that the broken
call supplies `d7_fault="omit_terminal_ask_exit"`; the fixed call uses the
default `None`.

### Control that catches it

The step cap is the effective backstop. `check_step_cap` raises a loud
`step_cap_hit` stop at `agent/guardrails.py:51-53`. The configured cap is six
turns; the broken trajectory attempts turn seven and is stopped.

The other layers are not the right fix:

- **Action de-duplication:** no tool action is repeated; cached state is being
  re-read.
- **Budget ceiling:** this is a later financial backstop and does not restore
  the missing terminal transition.
- **Tool interface:** all observations are already sufficient and correct.
- **Prompt:** the scripted failure is a missing code transition, not an
  instruction-following problem.

### Measured before/after result

| Metric | Broken - terminal exit omitted | Fixed - terminal exit restored |
| --- | ---: | ---: |
| Decision | `escalate` | `request_document` |
| Trigger | `step_cap_hit` | none |
| D7 trial pass rate | 0/1 (0%) | 1/1 (100%) |
| Turns | 7 | 3 |
| Input tokens | 13,200 | 4,800 |
| Output tokens | 360 | 180 |
| Estimated cost | US$0.001464 | US$0.000552 |
| Guardrail stop | `step_cap_hit` | none |

The fixed run reduces input tokens by 8,400 (63.64%) and estimated cost by
US$0.000912 (62.30%) while recovering the correct decision.

These are scripted cost-model estimates, not charged API costs.

### Turn-distribution evidence

The working-agent distribution is recalculated across the complete 40-case
evaluation set by `agent/failures.py:76-103` whenever Failure 1 runs.

| Distribution metric | Measured value |
| --- | ---: |
| Evaluation cases | 40 |
| Passing cases | 40 |
| Pass rate | 100% |
| Median turns | 3.0 |
| Worst legitimate run | 4 turns |
| Runs hitting the step cap | 0 |
| Configured step cap | 6 turns |

The cap therefore provides two turns of headroom above the worst legitimate
scripted run. It stops the reproduced loop without truncating any working case.

## Failure 2 - Tool interface

### Layer

**Tool-interface layer - observation filtering and size bounding.**

The deleted element is the V2 claim-history shaping boundary as a unit: member
filtering, minimum-field projection, and a five-record return cap. Removing that
boundary produces V1, which exposes the entire decided-claims store.

### Case and expected behaviour

- Case: `D7-HISTORY-001`
- Backend: scripted
- Expected decision: `approve_in_principle`
- Controlled fixture: `data/d7_fixtures.json:1-20`

The fixture belongs to member `M-2214`, but its hospital, service date, and line
item deliberately match decided claim `CLM-8702`, which belongs to member
`M-5502`. The case is not a duplicate because the members differ.

### Controlled deletion

The two versions preserve the same public tool name and signature:

- V1 at `tool/tools_v1.py:5-20` returns every decided claim, regardless of the
  requested member, with no size bound.
- V2 at `tool/tools_v2.py:22-51` filters by `member_id`, projects only the
  fields required for duplicate detection, and returns at most five records.

The downstream comparison at `tool/tools.py:246-256` intentionally relies on
the tool contract for the member scope, then compares hospital, service date,
and lines inside that already-scoped history. V1 violates the upstream member
scope, so the otherwise valid downstream comparison sees `CLM-8702` and emits
the wrong `duplicate_claim` trigger.

The complete broken and fixed runs are executed at
`agent/failures.py:186-252`. The same fixture, scripted backend, loop, prompt
equivalent, and expected outcome are held constant. Only the configured history
tool changes from V1 to V2. The original interface is restored in a `finally`
block.

### Why this is an interface fix

- **Prompt is wrong:** a reminder to consider only the current member cannot
  enforce data minimisation and still discloses unrelated members' claims.
- **Loop control is wrong:** the broken run terminates normally in two turns;
  it terminates on bad evidence.
- **A new guardrail is wrong:** blocking the escalation would hide the faulty
  observation instead of correcting its source.
- **Tool interface is correct:** filtering at the source makes cross-member
  records unavailable and makes the downstream assumption true by
  construction.

### Measured before/after result

| Metric | Broken - V1 | Fixed - V2 |
| --- | ---: | ---: |
| Decision | `escalate` | `approve_in_principle` |
| Trigger | `duplicate_claim` | none |
| D7 trial pass rate | 0/1 (0%) | 1/1 (100%) |
| Turns | 2 | 3 |
| Input tokens | 2,800 | 4,800 |
| Output tokens | 120 | 180 |
| Estimated cost | US$0.000328 | US$0.000552 |
| History records returned | 5 | 1 |
| Approximate history-observation tokens | 275 | 60 |

V2 reduces the measured history observation from approximately 275 to 60
tokens, a 78.18% reduction, and removes the cross-member false duplicate.

The correct run takes one additional turn and has a higher total scripted cost
than the wrong early escalation. This is an important result rather than a
defect in the experiment: the cheap run was cheap because it stopped early on
an incorrect decision. D6 must price success, not token cost alone.

## Result interpretation

The 0% and 100% values above are pass rates for one deterministic D7 trial on
each side of an ablation. They are not substitutes for the multi-case D4/D5
evaluation pass rates. Their purpose is causal reproduction: removing one
element reproduces the failure every time, and restoring it recovers the
working behaviour every time.

The detailed JSON files contain:

- complete broken and fixed `RunResult` records;
- ordered traces;
- decisions and triggers;
- turns, tokens, and estimated costs;
- explicit failure and recovery checks;
- layer justification; and
- the evaluation-set turn distribution or tool-observation measurement.

## Verification performed

After implementing the experiments, the following regression checks passed:

1. all 40 ordinary scripted evaluation cases passed with the normal V2 agent;
2. fault injection was rejected on the live backend before any API call;
3. the D7 fixture was removed from the in-memory store after the experiment;
4. the original tool-interface selection was restored;
5. all three D7 result files parsed as valid JSON; and
6. both failure-reproduced and working-behaviour-recovered checks passed for
   both experiments.

