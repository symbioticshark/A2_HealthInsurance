# DEBUG_LOG.md — failures found, and what fixed them

A running record of every real failure hit while building and running this
agent, in the order they were found. Kept for two reasons: so nobody
re-discovers the same bug twice, and because several of these are exactly
the kind of "found a defect, said what we assumed, moved on" evidence the
brief rewards (section 2's bug-report note, D0's honesty about limits).

Format per entry: **Symptom** (what we saw) → **Root cause** (why) →
**Fix** (what changed) → **Verified** (how we know it's actually fixed).

---

## 1. Fixture data — a new pre-authorisation record silently changed a shipped case's answer

**Symptom.** After merging 23 new evaluation cases into `data_A/`, the
harness's pass rate was 100% right up until a second merge pass, when
shipped case `CLM-8888` started failing — decision flipped from
`request_document` to `approve_in_principle` with no code change.

**Root cause.** A new record, `PA-6002` (member `M-6118`, procedure
`62480`, valid `2026-09-01`–`2026-12-31`), was added to satisfy a *new*
case (`CLM-9021`). Its validity window also happened to cover `CLM-8888`'s
date of service (`2026-09-08`) for the *same* member and procedure —
fixture data is a shared join graph, not case-scoped, so a record added
for one case can silently answer a different case too.

**Fix.** Moved `PA-6002`'s `valid_from` to `2026-09-10` — after
`CLM-8888`'s date of service, still before `CLM-9021`'s (`2026-09-26`).

**Verified.** Re-ran the full 38-case, 3-trial harness: 114/114 pass. This
is now standing practice — re-run the *entire* labelled set after every
fixture edit, never just the new cases, specifically to catch this class
of collision. Happened **twice** independently (once building the
extension, once re-confirming it from an uploaded copy that still had the
old value) — evidence it's an easy mistake to reintroduce, not a one-off.

---

## 2. `main.py live` silently ran the scripted backend the whole time

**Symptom.** Running `python3 main.py live --models ...` produced
plausible-looking output, but nothing was ever hitting OpenRouter — no
network activity, no key required, and the numbers matched scripted runs.

**Root cause.** `agent_a/config.py` reads `BACKEND = os.environ.get("A2_BACKEND", "scripted")`
**once**, at import time. `cmd_live` in `main.py` set
`os.environ["A2_BACKEND"] = "live"` *after* `agent_a.config` had already
been imported (imports happen once, at the top of `main.py`, before any
command dispatches) — so the assignment had no effect. `loop.run_case()`
kept defaulting to the frozen `"scripted"` value.

**Fix.** Stopped relying on the environment variable being re-read.
`eval_harness.py` gained an explicit `--backend` CLI flag; `main.py`
passes `--backend live` directly in `sys.argv` instead of mutating
`os.environ` and hoping something downstream notices.

**Verified.** Mocked `agent_a.live_backend.call_model` (no real network
available at the time) and confirmed `loop.run_case(..., backend="live")`
now actually enters `_run_case_live` and returns `result.model` set to the
real model string, with `cost_is_measured=True`. Scripted path re-tested
unaffected (114/114 pass).

---

## 3. `ModuleNotFoundError: No module named 'requests'`

**Symptom.** First real attempt at a live run crashed inside
`live_backend.call_model`.

**Root cause.** `requests` was never installed — scripted mode has zero
dependencies, so this was never hit before switching to live.

**Fix.** `python3 -m pip install requests` (later moved into a venv, see
#4).

**Verified.** Import succeeded on next run; error moved on to the next
real issue (progress, not silence).

---

## 4. `error: externally-managed-environment` on macOS

**Symptom.** Plain `pip install requests` refused to run.

**Root cause.** Homebrew's Python on macOS blocks global `pip install` by
default (PEP 668) — a deliberate safety measure, not a bug.

**Fix.** Created a project-local virtual environment instead of fighting
the system Python:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Needs `source .venv/bin/activate` at the start of every new terminal
session — easy to forget, which is exactly what caused issue #7 below.

**Verified.** `pip install` succeeded inside the venv; `python3 main.py`
ran using the venv's interpreter (confirmed via the traceback path in
later errors showing `.venv/lib/python3.14/site-packages/...`).

---

## 5. `A2_BACKEND` left set in the shell, so `eval` unexpectedly went live

**Symptom.** Running plain `python3 main.py eval` (not `live`) produced a
traceback inside `_run_case_live`.

**Root cause.** `export A2_BACKEND=live` from an earlier debugging session
persisted for the rest of that terminal tab — `export` is session-scoped,
not command-scoped, and `config.BACKEND` (see #2) reads it at import time
regardless of which subcommand you meant to run.

**Fix.** `unset A2_BACKEND`; checked with `echo $A2_BACKEND` first to
confirm the diagnosis before touching anything.

**Verified.** `python3 main.py check` reported `Backend: scripted` again.

**Lesson worth keeping:** this is a live example of exactly the "silent
misconfiguration" failure mode D3(a) is about — ambient state (an env var
set three commands ago, in a different context) silently changing
behaviour with no explicit signal. Worth a line in the report if you want
a real, observed instance rather than a hypothetical one.

---

## 6. `OPENROUTER_API_KEY` not found despite a `local_config.py` existing

**Symptom.** `main.py check` reported `OpenRouter key found: False` even
though a `local_config.py` with the key existed.

**Root cause.** The file was one directory *above* the repo root (kept
there deliberately, to keep it outside the git working tree entirely —
safer than `.gitignore`, which only stops a tracked commit, not an
accidental `git add -A`). Python's import system only searches
`sys.path`, which by default is the running script's own directory — the
parent folder was never on it.

**Fix.** `live_backend.py` and `main.py`'s key-lookup both now add the
parent directory to `sys.path` as a second search location before trying
`from local_config import OPENROUTER_API_KEY`, in addition to the repo
root.

**Verified.** `main.py check` → `OpenRouter key found: True`.

---

## 7. `404 Client Error: Not Found` from OpenRouter, with no detail

**Symptom.** First genuine network call to `/chat/completions` returned
404, and `resp.raise_for_status()` raised a bare `HTTPError` with no
indication of *why*.

**Root cause (two, stacked).** (a) `raise_for_status()` discards the
response body, which is exactly where OpenRouter puts the actual reason
(usually "model not found"); (b) the model ID string being sent was
plausible but not necessarily the exact slug OpenRouter expects — sources
disagree on `anthropic/claude-3-5-haiku` vs `anthropic/claude-3.5-haiku`
(dash vs dot), and IDs sometimes carry a date suffix.

**Fix.** Replaced the bare `raise_for_status()` call with an explicit
check that surfaces `resp.text` in the exception message. Separately,
queried OpenRouter's own `/models` endpoint directly to get exact, current
IDs rather than trusting any third-party page:
```bash
curl -s "https://openrouter.ai/api/v1/models" | python3 -c "
import json, sys
for m in json.load(sys.stdin)['data']:
    if 'claude' in m['id'].lower():
        p = m['pricing']
        print(f\"{m['id']:45s} in={float(p['prompt'])*1e6:.2f}/M out={float(p['completion'])*1e6:.2f}/M\")
"
```

**Verified.** Switched to `anthropic/claude-haiku-4.5` (confirmed via the
query above, and not on Anthropic's deprecation list unlike the two
cheaper Haiku variants); the 404 stopped, replaced by real model output.

---

## 8. `JSONDecodeError` parsing the model's `Final:` line

**Symptom.** `agent_a/live_backend.py:parse_final` crashed with
`Expecting property name enclosed in double quotes`.

**Root cause.** The model didn't emit strict JSON on the `Final:` line
(likely single quotes or a formatting deviation) — `parse_final` called
`json.loads()` directly with no tolerance for near-JSON output, which is
common from smaller/faster models even when explicitly told the exact
format.

**Fix.** Added `_extract_json()`: finds the first balanced `{...}` block
in the line, tries `json.loads`, falls back to `ast.literal_eval` (handles
single-quoted Python-style dicts), and — critically — if both fail, raises
an error that includes the *raw model text*, not just a decoder traceback.
Applied the same helper to `parse_actions`.

**Verified.** Next run got past parsing; failures after this point were
real behavioural issues (see #9, #10), not parsing crashes — confirmed by
the error messages actually showing usable content instead of stack
traces pointing into `json/decoder.py`.

---

## 9. `step_cap_hit` at 7 turns on a case that should take ~3–4 (CLM-8850)

**Symptom.** Scripted backend resolves `CLM-8850` in 3 turns; the live
model hit the step cap (6) and got force-escalated by the guardrail.

**Root cause.** The system prompt *stated* the rule ("output one or more
Action: lines per turn") but gave no worked example — the model was very
likely calling one tool per turn sequentially instead of batching
independent calls (`lookup_policy` / `get_hospital_status` /
`check_coverage`) into a single turn the way D2(c)'s dependency rule
intends. Not confirmed by a turn-by-turn trace yet (that visibility didn't
exist before this point — see fix).

**Fix.** Two changes: (a) added a worked multi-`Action:` example to the
system prompt, directly modelled on the actual dependency rule
`scripted_backend.py` already implements; (b) added `--verbose` raw-output
printing per turn in `loop.py`, and a `main.py run <case> --live` path, so
future instances of this are diagnosable in one command instead of reading
a JSON dump after the fact.

**Verified.** *Pending re-run with the fix applied* — update this entry
with turns/tokens before vs after once you've re-run `CLM-8850`.

---

## 10. `gate_bypassed` on the all-lines-excluded case (CLM-9003)

**Symptom.** Model produced `Final: {"decision": "approve_in_principle", ...}`
without ever calling `issue_decision_letter` first. The loop's own
guardrail caught it and force-escalated with trigger `gate_bypassed`.

**Root cause — most likely, not yet confirmed by a raw-output trace.**
`CLM-9003` is the case where every line is excluded and `approved_total`
is `0`. The system prompt didn't explicitly cover this edge case, and it's
plausible the model reasoned "nothing is payable, so there's nothing to
approve" and skipped the write it should still have made — this is
*exactly* the case this fixture was added to test for (see the extended
data set's `all_lines_excluded` family), so the model failing it isn't
noise, it's the test working.

**This one is arguably not a bug at all** — the gate did its job. The
`gate_bypassed` guardrail exists precisely so a model claiming an approval
it never actually wrote gets caught rather than silently trusted. Whether
to "fix" this by clarifying the prompt (so the model gets it right) or
leave it as a genuine, honestly-reported model limitation is a judgement
call worth making deliberately, not by default — the brief's D7 wants you
to be able to say which layer a fix belongs in, and "the model is being
tested is not the same as the model failing a specification bug" is worth
a sentence either way.

**Fix.** Added an explicit line to the system prompt: approval requires
calling `issue_decision_letter` first *even when approved_total is 0*.

**Verified.** *Pending re-run.* Update with the raw trace
(`main.py run CLM-9003 --live --verbose`) once re-tested — specifically
worth recording whether the model still tries to skip the gate on this
case after the prompt fix, since that distinguishes "prompt was unclear"
from "model has a systematic blind spot on zero-value approvals," which
are different findings for the report.

---

## Open items / next re-run checklist

- [ ] Re-run `CLM-8850 --live --verbose`, record turns before/after the
      batching-example fix.
- [ ] Re-run `CLM-9003 --live --verbose`, record whether `gate_bypassed`
      recurs after the prompt fix — if it does, this becomes a genuine,
      reportable model limitation rather than a prompt bug.
- [ ] Run the full labelled set once both are stable, log via
      `main.py metrics`, and paste the per-model comparison table here
      once a second/third model is added to the battery.

---

# Addendum — `A2_secondBuild_updated` 2.5

The entries below record the incremental team-testing upgrade. The original
`DEBUG_LOG.md` remains unchanged; this copy preserves the earlier history and
adds the current state.

## 11. Team members needed a safe launcher instead of command-line setup

**Symptom.** The project assumed that testers could select a Python command,
create a virtual environment, activate it, install dependencies, pass command
arguments, and choose output paths manually. This was unsuitable for team
members without a computing background and was not portable between Windows
and macOS.

**Root cause.** Environment preparation and experiment selection were separate
manual steps. A copied `.venv` is also operating-system and path specific.

**Fix.** Added `Run_A2_Agent.bat` and `Run_A2_Agent.command`. Each launcher
checks a private environment, searches common Python names and locations,
accepts a user-supplied executable path when needed, creates or repairs `.venv`,
installs `requirements.txt`, and starts the same guided menu. Neither launcher
installs Python.

**Verified.** The Windows launcher completed setup and started the menu in a
team test. The macOS launcher was checked for matching behaviour, POSIX paths,
LF line endings, Intel/Apple-Silicon locations, and shell syntax structure. A
real Mac smoke test remains recommended because macOS executable permissions
and Gatekeeper cannot be reproduced fully on Windows.

---

## 12. Testers could overwrite one another's results

**Symptom.** Shared `results/run_log.json` and metric paths made it difficult to
identify the operator and allowed one person's latest output to replace
another's.

**Root cause.** Result paths were global and the run did not have a persistent
tester identity.

**Fix.** Added a first-run tester profile and isolated result directories under
`results/<tester_name>/`. Each tester receives a concise
`<tester_name>_result.json`, a full `<tester_name>_run_log.json`, metric history,
session history, comparison output, and a decision ledger.

**Verified.** Runs under a named profile wrote only inside that tester's result
directory. The concise result contains environment, model, run mode, V1/V2,
timing, tokens, cost, accuracy, notable failures, and compact case evidence.

---

## 13. The run plan did not match the assignment's negative-case repetition rule

**Symptom.** Earlier runs showed one, two, three, or four trials depending on
the command used, and a simple three-trials-for-all plan was both expensive and
inconsistent with the brief.

**Root cause.** Trial count was global rather than case-specific. The phrase
"two extra trials" had also previously been misread as four trials in total.

**Fix.** Added a case-specific standard plan: 24 ordinary cases run once and 16
expected-negative cases run three times, for `24 × 1 + 16 × 3 = 72` total
runs. The live menu also preserves a 40-run quick validation, a 48-run
negative-only mode, and custom case/repetition selection.

**Verified.** The generated standard plan contains 40 cases and exactly 72
trials. Negative-only contains 16 cases and 48 trials. The definition of a
negative case is label based: expected decision is not
`approve_in_principle`; it is not inferred from a model's response.

---

## 14. V1/V2 selection was confused with project builds and model selection

**Symptom.** V1 and V2 were initially treated as names for separate project
builds, which did not implement the experiment required by the assignment.

**Root cause.** The actual distinction is the tool interface: V1 exposes
unfiltered, uncapped claim history, while V2 filters history to the member and
limits it to five records.

**Fix.** Added an independent V1/V2 selector before the model selector on every
live run. V1 displays a warning because it is intentionally defective; V2 is
the normal corrected interface.

**Verified.** Both versions use the same data, agent loop, model choices, run
modes, and output system. Only the claim-history interface changes.

---

## 15. Long evaluations lacked progress visibility and safe publication

**Symptom.** Testers could not tell whether a long live battery was advancing,
and interruption risked leaving files that looked like completed results.

**Root cause.** Output was saved directly to permanent result paths and there
was no clear run preview or progress counter.

**Fix.** Added a progress bar, case/trial status, a pre-run confirmation screen,
and transactional output staging. Completed files are committed together;
cancelled or failed staging data is rolled back. Environment setup is also
repairable by running the launcher again.

**Verified.** Cancellation before confirmation makes no paid case request.
Keyboard interruption returns to the menu without publishing a partial run,
and no abandoned staging directory remained after the tested paths.

---

## 16. Token-price formulas disagreed with the OpenRouter balance

**Symptom.** A Gemini run showed an observed balance change of `$0.15369` but a
calculated run cost of `$0.20647`. An older Claude Haiku 4.5 report showed an
implausibly low `$0.05679` for 40 cases.

**Root cause.** The older implementation multiplied all prompt and completion
tokens by a static listed price. It could not account for the provider selected
by OpenRouter, cache read/write prices, or reasoning charges. The Claude model
slug was absent from the old table, so it fell back to the generic cheap tier
of `$0.10/M` input and `$0.40/M` output rather than Claude Haiku 4.5's listed
price.

**Fix.** Live calls now record and sum the `usage.cost` returned by OpenRouter.
They also retain input, output, cached-input, cache-write, and reasoning token
fields. Static prices are used only for pre-run prediction or as a clearly
labelled fallback when the API does not return cost. Balance before and after
the run is retained as a reconciliation check.

**Verified.** Mocked API responses confirmed that the loop preserves the exact
OpenRouter cost instead of recomputing it. Historical cost and observed balance
data feed the prediction hierarchy. The old Claude figure was independently
reproduced algebraically from the cheap-tier formula, confirming the diagnosis.

---

## 17. Model prices in `metrics.py` caused maintenance conflicts

**Symptom.** Adding or correcting a model required editing `metrics.py`, so
teammates could conflict in a source file and model IDs or prices could become
stale.

**Root cause.** The public model list and application metrics logic were stored
in the same Python module.

**Fix.** Moved the curated list to `model_catalog.json`, containing 20 models
with separate input/output prices. The model menu reads OpenRouter's public
`/api/v1/models` catalog and refreshes matching prices in memory. It never
rewrites the project file during normal use. Offline runs retain the bundled
prices, and the existing personal custom-model workflow remains available.

**Verified.** OpenRouter returned 446 current models during verification. All 20
curated IDs were found, all advertised tool support, and all 20 prices were
refreshed. The local JSON contains no duplicates or invalid price entries.

---

## 18. OpenRouter failures again hid the useful response message

**Symptom.** A regression restored bare `raise_for_status()` calls, so errors
such as invalid model IDs, insufficient credit, rate limits, or provider
failures could appear only as generic HTTP status exceptions.

**Root cause.** The earlier response-body fix was not present consistently in
the later build's model lookup, balance lookup, and chat-completion paths.

**Fix.** Added one shared error helper that extracts OpenRouter's error message
or response body and applies it to model-catalog, account-balance, key-balance,
and chat-completion failures.

**Verified.** A simulated HTTP 404 containing an OpenRouter error object raised
an exception containing both `HTTP 404` and the original service message.

---

## 19. Team results were difficult to compare consistently

**Symptom.** Testers could inspect individual files but had no simple way to
compare their own history with other team members or the supplied baseline.

**Root cause.** Comparison functions existed at a lower level but were not
available through the non-technical workflow, and older session records did not
contain all new run-mode or V1/V2 fields.

**Fix.** Added a comparison menu for personal history and all testers plus the
shared baseline. New records include model, backend, tool-interface version,
run mode, trial count, accuracy, turns, cost, and time. Older records remain
readable through safe defaults.

**Verified.** Both personal and combined session collections load through the
menu. Old logs do not need migration, although a fresh assignment-standard run
is required for fair formal comparison with 2.5 results.

---

## Current release checklist

- [x] Windows launcher and guided menu.
- [x] macOS launcher static compatibility review.
- [ ] One macOS teammate smoke test after transfer.
- [x] Forty-case quick validation retained.
- [x] Assignment-standard 72-run plan.
- [x] Negative-only 48-run plan.
- [x] Independent V1/V2 and model selection.
- [x] Per-tester result isolation and concise result file.
- [x] Progress, preview, cancellation, and transactional result publication.
- [x] OpenRouter-reported cost and balance reconciliation.
- [x] Twenty-model separate catalog with live price refresh.
- [x] Detailed OpenRouter error messages.
- [ ] Generate fresh 2.5 live results for the final model/V1/V2 comparisons.
