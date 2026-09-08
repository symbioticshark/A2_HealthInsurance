# PE6201 A2 — Problem A agent

## Quick start (Terminal, any OS)

```bash
python3 main.py check          # confirm data + labels line up
python3 main.py eval           # scripted backend, 1 trial, all 38 cases
python3 main.py eval --trials 3 --verbose
python3 main.py run CLM-8888   # one case, full turn-by-turn trace
python3 main.py failures       # D7's two reproduced failures
python3 main.py live --model anthropic/claude-3-5-haiku --cases CLM-8850   # needs OPENROUTER_API_KEY
```

No install step for anything except `live` — everything else is standard
library only. `main.py` with no arguments runs `eval` with defaults.

## Double-clickable version on macOS

**`Run_A2_Agent.command`** does the same thing without opening Terminal
yourself:

1. First time only: right-click it → **Open** (macOS blocks unsigned
   scripts on first launch if you just double-click — this is normal, not
   an error in the script). Every launch after that, plain double-click works.
2. If it still refuses to open, fix the executable bit once from Terminal:
   ```bash
   chmod +x Run_A2_Agent.command
   ```
3. It opens a Terminal window with a small menu (eval / eval x3 / trace one
   case / failure demo / sanity check / custom args) and runs `main.py`
   underneath. It always operates on whatever folder it's actually sitting
   in, so you can move the whole project folder anywhere.

This is a shell script with a `.command` extension, not a compiled binary —
that's deliberate. It needs nothing installed beyond Python 3 (which ships
on modern macOS, or `brew install python3`), works identically on Intel and
Apple Silicon, and needs no code-signing to run locally. A "real" `.app`
bundle (built with `py2app` or PyInstaller) buys you a Dock icon and no
visible Terminal window, at the cost of a multi-hundred-MB bundle, an
Apple code-signing step for it to run on a Mac that isn't yours, and having
to rebuild it on an actual Mac every time the code changes (both tools
compile for the OS/architecture they run on — this can't be produced from
a Linux machine or this sandbox). For a team of 6–7 people running this
locally to check their own numbers before submission, that trade-off isn't
worth it; the `.command` script is the version worth shipping. If you
still want a real `.app` for the demo video, see the note at the bottom.

## Repo layout this expects

```
.
├── main.py
├── Run_A2_Agent.command
├── eval_harness.py
├── requirements.txt
├── agent_a/                      (the package: tools, guardrails, loop, ...)
├── data_A/                       (fixture data — extend via make_fixtures_A.py)
├── expected_outcomes_A.json      (the answer key)
└── results/                      (created on first run: run_log.json, decision_ledger.jsonl)
```

This is also exactly what should be at the root of your GitHub repo and
your NTULearn folder copy (D5(a)/section 4) — `main.py check` is a good
first thing for a marker (or a teammate) to run after cloning.

## If you want a real standalone .app (optional)

Run this **on an actual Mac**, from this folder, once `pyinstaller` is
installed (`pip install pyinstaller`):

```bash
pyinstaller --onefile --name A2Agent main.py
# binary lands in dist/A2Agent
./dist/A2Agent eval
```

Two things to know: (1) it bundles a full Python interpreter, so expect
50–100MB for one file; (2) it does **not** bundle `data_A/` or
`expected_outcomes_A.json` — those still need to sit next to the binary
(or point `A2_DATA_DIR`/`A2_LEDGER_PATH` env vars at them), same as with
`main.py` directly. It's genuinely not needed for A2 — nothing in the
rubric asks for a shippable binary — but it's there if you want one for
the demo.
