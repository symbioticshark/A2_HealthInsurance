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
