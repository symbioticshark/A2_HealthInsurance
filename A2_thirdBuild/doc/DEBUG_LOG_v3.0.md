# DEBUG LOG - Version 3.0

## Scope

This log records the integration, safety, compatibility, and reporting work
completed for `A2_thirdBuild` version 3.0. It does not replace
`DEBUG_LOG.md` or `DEBUG_LOG_v2.5.md`; those files remain the record of earlier
faults and fixes.

Version 3.0 was treated as a compatibility-preserving architecture revision.
The normal agent behaviour and the existing 2.5 evidence were retained while
the user interface, result model, comparison workflow, API handling, and D7
reproduction path were made explicit and safer.

## 1. Program entry point carried too many responsibilities

**Problem.** The main program previously mixed dispatch, interactive prompts,
configuration, and direct-command handling. This made changes to the menu more
likely to affect scripted automation.

**Resolution.** `run/main.py` is now a thin dispatcher. Interactive behaviour
lives in `run/interactive_cli.py`, direct-command dispatch lives in
`run/command_cli.py`, masked input lives in `run/cli_input.py`, and the shared
API-key workflow lives in `run/api_key_flow.py`.

**Compatibility.** Running `python run/main.py` still opens the interactive
menu. Supplying a command still uses the same top-level entry point.

## 2. The interactive home screen had become difficult to navigate

**Problem.** Build terminology and detailed run descriptions appeared too
early, while result viewing, history, and comparison were mixed together.

**Resolution.** The 3.0 home screen is organised into six stable entries:
Environment check, Run, Results, Settings, Help, and Exit. The Results screen
keeps six operations: latest detail, session selection, history overview,
arbitrary two-session comparison, matching V1/V2 comparison, and all-testers
overview.

**Compatibility.** The underlying scripted, guardrail, live, comparison, and
result-view functions remain available through direct commands.

## 3. Windows and macOS startup needed one supported path

**Problem.** Manual environment creation and platform-specific activation were
easy to perform inconsistently. A copied Windows virtual environment could not
be reused on macOS, and executable permission on `.command` files could not be
assumed.

**Resolution.** `run/Run_A2_Agent.bat` and `run/Run_A2_Agent.command` now detect
an installed Python, create or repair the private environment, install the
required dependency, and launch the same menu. The macOS guide explicitly
documents `chmod +x` because repository delivery cannot guarantee executable
permission on every machine.

**Compatibility.** Direct execution remains supported after manual activation;
the launchers add preparation and repair rather than a different application
path.

## 4. Live runs needed a free readiness check and safer key entry

**Problem.** Authentication and connection problems were otherwise discovered
only after entering the paid execution path. Plain-text key entry also exposed
secrets on screen.

**Resolution.** `backend/api_preflight.py` performs a no-inference OpenRouter
connectivity check. Interactive live runs call it before execution and allow the
user to retry, replace the key, or cancel. Key entry echoes `*` characters
instead of the secret. Local configuration updates are written atomically.

**Security hardening.** Provider errors pass through central redaction before
being displayed or logged. API keys and bearer tokens are removed from error
text. `.gitignore` excludes `local_config.py`.

## 4A. Tester registration could silently reuse another member's history

**Problem.** Tester names determine the result directory. Registering a name
that normalises to an existing directory could unintentionally merge work with
another member. Conversely, a direct evaluation with no configured name needed
a non-blocking, collision-safe identity.

**Resolution.** The direct setup command registers a name and optionally opens
masked API-key input:

```text
python run/main.py setup --name "Tester Name" --api-key
```

Existing tester directories produce a warning and no configuration change.
Deliberate reuse requires `--allow-existing-tester`. Normal commands with no
configured name receive a timestamped name plus a random suffix. Interactive
first launch offers the same automatic assignment when Enter is pressed.

**Key precedence.** `OPENROUTER_API_KEY` in the environment is authoritative,
followed by the current-process key and then the gitignored local key. A newly
entered local key therefore cannot silently override an environment policy.
Literal keys are not accepted as command arguments, keeping them out of shell
history and process listings.

## 5. Parsing, timeout, and provider-error behaviour was inconsistent

**Problem.** Permissive fallback parsing made malformed model output difficult
to classify, network operations used inconsistent timeout assumptions, and
some provider failures hid the useful response detail.

**Resolution.** Model actions and finals use bounded JSON extraction and strict
`json.loads`; the previous `ast.literal_eval` fallback is not used in 3.0.
Connection, ordinary HTTP-read, and paid model-read timeouts are defined
centrally in `config/config.py`. Timeout and request failures return explicit
invalid-run evidence, retaining known earlier charges while labelling the
current request cost as unknown when necessary.

## 6. V1 and V2 needed to be real, separately inspectable interfaces

**Problem.** A single tool file and ambiguous version wording made it difficult
to show exactly what changed between experiments.

**Resolution.** Claim-history V1 and V2 now live in `tool/tools_v1.py` and
`tool/tools_v2.py`. `tool/tools.py` retains the stable registry and selects the
requested implementation. V1 returns unfiltered, unbounded history; V2 filters
to the requested member, projects only duplicate-check fields, and caps the
response at five records.

**Compatibility.** Existing callers continue to use the same public tool name.
V2 remains the normal default; V1 requires deliberate selection.

## 7. Live run modes did not clearly encode the assignment trial plan

**Problem.** A single generic trial count could not express ordinary cases once
and negative cases three times. It also encouraged quick validation results to
be compared with full standard batteries.

**Resolution.** The run layer now distinguishes quick validation, standard
battery, negative-only, and custom selections. A preview shows the model, tool
version, case/trial count, balance information, and cost basis before paid
execution. Standard battery trial counts are recorded per case.

**Reporting rule.** Comparison views retain the run mode and trial counts so a
40-run quick validation is not presented as equivalent to a 72-run standard
battery.

## 8. The previous result view was based too heavily on latest files

**Problem.** Latest-result files are convenient but overwrite earlier detail.
They cannot establish that the newest session is the best session, and they do
not support case-level comparison across historical runs.

**Resolution.** The append-only sources remain:

```text
run_history.jsonl       one completed session per line
metrics_log.jsonl       one case trial per line
decision_ledger.jsonl   one emitted decision action per line
```

New rows carry a `session_id` and trial number. Latest-result JSON files remain
convenience views, while detailed viewing can select a historical session.
`comparison_report.json`, `detailed_comparison.json`, and
`v1_v2_detailed_comparison.json` are explicitly derived reports.

## 9. Existing 2.5 evidence had to remain usable without rewriting it

**Problem.** Version 2.5 metric rows do not always contain a session ID. A
destructive migration would risk changing already completed evidence, while
ignoring legacy detail would make it impossible to compare old runs.

**Resolution.** `eval/session_results.py` associates legacy metric rows with
history entries by validated order and expected trial count. It exposes the
source as `legacy_order_validated` and refuses unsafe matches. Legacy files are
read without being rewritten.

**Compatibility.** Copied 2.5 tester directories remain readable. New 3.0
sessions use native IDs, while latest views and comparisons can derive detail
from both formats when the association is safe.

## 10. Standalone V1/V2 scripts had created a parallel result system

**Problem.** Earlier V1/V2 scripts wrote special-purpose files independent of
normal tester history. Multiple testers could overwrite them, and case-level
evidence was disconnected from the canonical history.

**Resolution.** A V1/V2 live comparison now performs one normal V1 evaluation
and one normal V2 evaluation on the same model. Both are committed as ordinary
sessions. The shared comparison engine then derives the detailed pair report
from their session IDs. Arbitrary two-session and V1/V2 comparison use the same
session-selection model.

**Safety.** If one half is interrupted, the completed session remains valid but
no false complete pair report is published.

## 11. Concurrent or interrupted runs could corrupt published state

**Problem.** Long evaluations must not publish partial sessions, and two
processes using the same tester name must not merge their output.

**Resolution.** Evaluations write to a per-session staging area and publish
only after every required artifact is complete. Transaction manifests support
recovery after interruption. Atomic replacement is used for JSON views. A
per-tester `.run.lock` prevents concurrent writers to the same history while
allowing different testers to work independently.

**Repository hygiene.** `.run.lock`, `.in_progress/`, temporary transaction
files, Python caches, virtual environments, and `.DS_Store` are ignored by Git.

## 12. Cost evidence needed provider-reported detail without losing fallbacks

**Problem.** Catalog prices are estimates and can diverge from the amount
reported by OpenRouter. Cache and reasoning tokens were also absent from older
result shapes.

**Resolution.** Live calls record OpenRouter `usage.cost` when present and mark
its source. Token-price calculation remains a labelled fallback. Results also
retain cached-input, cache-write, and reasoning-token fields when supplied by
the provider. Balance before/after and observed balance change are kept
separate from summed request cost.

**Compatibility.** Missing fields in legacy rows are treated as unavailable or
zero where appropriate; old estimated costs are not relabelled as measured
costs.

## 13. D7 prototypes did not yet prove "working agent, minus X"

**Problem.** The earlier failure prototype used a separately implemented bad
runner and changed more than one loop mechanism. The tool-interface example did
not complete an end-to-end agent run or save full before/after evidence.

**Resolution.** Version 3.0 adds `run/run_d7_failures.py` and a fault-injection
argument restricted to the scripted backend. Both broken and fixed executions
call the normal `agent.loop.run_case`:

- Failure 1 removes only the terminal exit after a complete ask outcome. The
  loop re-reads cached state until the step cap stops it.
- Failure 2 holds the agent and fixture constant while selecting the unfiltered
  V1 history interface or corrected V2 interface.

The runner prints the mechanism, layer, complete traces, before/after metrics,
and explicit reproduction/recovery checks. It atomically writes isolated
reports under `results/d7/`. Full method and code-line references are in
`D7_REPRODUCED_FAILURES.md`.

**Measured result.** Failure 1 changed from 7 turns and `step_cap_hit` to the
correct 3-turn `request_document` result. Failure 2 changed from an incorrect
cross-member duplicate escalation to the correct approval; V2 reduced the
history observation from approximately 275 to 60 tokens (78.18%).

## Verification summary

The final 3.0 checks relevant to these changes include:

- normal 40-case scripted regression: 40/40 passed;
- working-agent median turns: 3.0; worst legitimate run: 4;
- working runs hitting the six-turn step cap: 0;
- both D7 failures reproduced and both fixed behaviours recovered;
- live fault injection rejected before any API request;
- D7 fixture, ledger path, and selected tool version restored after each run;
- D7 result files parsed as valid JSON; and
- English and Chinese run guides validated after command updates.

## Documentation map

- `RUN_GUIDE.md` - complete English operating instructions.
- `RUN_GUIDE_ZH.md` - complete Chinese operating instructions.
- `D7_REPRODUCED_FAILURES.md` - D7 method, code locations, and measured tables.
- `DEBUG_LOG_v2.5.md` - earlier 2.5 fixes and migration context.
- `DEBUG_LOG.md` - original failure and repair record.
