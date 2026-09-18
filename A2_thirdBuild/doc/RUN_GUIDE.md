# PE6201 A2 Agent 3.0 — Run Guide

This guide covers the supported launcher scripts, manual environment setup,
interactive use, direct commands, result inspection, and recovery behaviour.

## 1. Requirements

- Keep the complete `A2_thirdBuild` directory together.
- Use Python 3.9 or newer.
- Internet access is required only for dependency installation and live runs.
- An OpenRouter API key is required only for live runs.
- Run commands from the `A2_thirdBuild` root directory unless a section says
  otherwise.

Scripted evaluations, guardrail checks, result viewing, and comparisons do not
make paid model requests.

## 2. Recommended startup: launcher scripts

The launcher scripts are the safest entry point for ordinary use. They:

1. Find a compatible Python installation.
2. Create or repair the private environment at `config/.venv`.
3. Install `config/requirements.txt`.
4. Start the interactive menu through `run/main.py`.

### Windows

Double-click:

```text
run\Run_A2_Agent.bat
```

Alternatively, open PowerShell in the `A2_thirdBuild` directory and run:

```powershell
.\run\Run_A2_Agent.bat
```

### macOS

On the first launch, right-click `run/Run_A2_Agent.command` in Finder and
select **Open**.

Alternatively, use Terminal:

```bash
chmod +x run/Run_A2_Agent.command
./run/Run_A2_Agent.command
```

The Windows and macOS launchers create separate platform-compatible virtual
environments. Do not copy a Windows `config/.venv` to a Mac or vice versa.

## 3. Interactive menu

Starting `run/main.py` without a command opens:

```text
1. Environment check
2. Run
3. Results
4. Settings
5. Help
6. Exit
```

On the first launch, enter a tester name. The API key is optional and may be
skipped. Results are stored under a tester-specific directory in `results/`.

### Run menu

- **Scripted evaluation** — deterministic, local, and free.
- **Guardrail checklist** — separate D3 safety checks; not the 40-case
  evaluation set.
- **Live evaluation** — paid OpenRouter model runs with an API preflight and
  cost preview.
- **V1/V2 live comparison** — runs one standard V1 battery and one standard V2
  battery on the same model, then compares the two completed sessions.

V1 is intentionally defective and exists only as an experimental baseline.
V2 is the corrected tool interface.

### Results menu

```text
Individual details
  1. Latest detailed result
  2. Select a session to view
History
  3. Run-history overview
Comparison
  4. Compare any two sessions
  5. Compare matching V1/V2 sessions
  6. All-testers overview
```

## 4. Manual environment setup

Use this section only if the launcher scripts cannot be used.

### Windows PowerShell

```powershell
py -3 -m venv config\.venv
.\config\.venv\Scripts\python.exe -m pip install -r config\requirements.txt
.\config\.venv\Scripts\python.exe .\run\main.py
```

If `py` is unavailable, replace `py -3` with the full path to a Python 3.9+
executable.

### macOS Terminal

```bash
python3 -m venv config/.venv
./config/.venv/bin/python -m pip install -r config/requirements.txt
./config/.venv/bin/python run/main.py
```

## 5. Direct command convention

The examples below use `PYTHON` as shorthand for the private interpreter.

Windows:

```powershell
$PYTHON = ".\config\.venv\Scripts\python.exe"
```

macOS:

```bash
PYTHON="./config/.venv/bin/python"
```

PowerShell runs a command with `& $PYTHON`; macOS runs it with `$PYTHON`.

Examples:

```powershell
& $PYTHON .\run\main.py check
```

```bash
$PYTHON run/main.py check
```

Use the platform-appropriate path separators in the remaining examples.

## 6. Environment check

```text
PYTHON run/main.py check
```

This shows the app version, tester, Python executable, dataset counts, default
model, tool interface, API-key status, and result directory. If an API key is
configured, it also performs a no-inference connectivity check. This check does
not call a model.

## 7. Scripted commands

### Run one case and print its trace

```text
PYTHON run/main.py run CLM-8850
```

### Run all evaluation cases once on V2

```text
PYTHON run/main.py eval --tool-interface v2 --verbose
```

### Run the assignment-standard battery

```text
PYTHON run/main.py eval --standard-battery --tool-interface v2 --verbose
```

The standard battery runs each expected-ordinary case once and each
expected-negative case three times. With the current dataset, this is 72 total
case trials.

### Run selected cases

```text
PYTHON run/main.py eval --cases CLM-8850 CLM-8888 --trials 1 --tool-interface v2 --verbose
```

### Run the same selected cases three times each

```text
PYTHON run/main.py eval --cases CLM-8850 CLM-8888 --trials 3 --tool-interface v2 --verbose
```

### Select an autonomy setting

```text
PYTHON run/main.py eval --cases CLM-8850 --autonomy confirm --tool-interface v2
```

Valid autonomy values are `suggest`, `confirm`, and `act`.

### Run the D3 guardrail checklist

```text
PYTHON agent/guardrail_checklist.py --tool-interface v2
```

To demonstrate that the code guardrails still behave under the experimental
interface:

```text
PYTHON agent/guardrail_checklist.py --tool-interface v1
```

### Run the failure demonstrations

```text
PYTHON run/main.py failures --case-id CLM-8888
```

### Run the parallel-versus-sequential D2(c) experiment

```text
PYTHON eval/measure_parallel_vs_sequential.py
```

This experiment uses the scripted backend and does not spend API credit.

## 8. Live commands

Live commands can spend OpenRouter credit. The program first validates the API
key through a no-inference request. If validation fails, it allows retrying,
entering and saving a replacement key, or cancelling.

For the clearest cost preview and confirmation flow, prefer the interactive
menu. The direct `live` command begins its paid case runs immediately after a
successful API check.

### Run selected cases on one model

```text
PYTHON run/main.py live --models openai/gpt-4o-mini --cases CLM-8850 CLM-8888 --trials 1 --verbose
```

### Run all evaluation cases once on one model

```text
PYTHON run/main.py live --models openai/gpt-4o-mini --trials 1 --verbose
```

### Run the same cases on multiple models

```text
PYTHON run/main.py live --models openai/gpt-4o-mini google/gemini-2.5-flash --cases CLM-8850 CLM-8888 --trials 1 --verbose
```

The direct `live` command uses the tool-interface version saved in Settings.
Use the interactive Settings menu to change the default before running it.

### Run a complete V1/V2 live comparison

```text
PYTHON run/run_v1_v2_live_battery.py --model openai/gpt-4o-mini --run-both
```

This command:

1. Checks the API key without calling a model.
2. Shows the number of paid runs and any available estimate.
3. Requests confirmation.
4. Runs the normal V1 standard battery.
5. Runs the normal V2 standard battery.
6. Generates the detailed V1/V2 comparison only when both sessions complete.

If V1 completes but V2 is interrupted, the valid V1 session remains in normal
history and no false completed comparison is written.

`--yes` skips the final paid-run confirmation and should be used only in
deliberate automation:

```text
PYTHON run/run_v1_v2_live_battery.py --model openai/gpt-4o-mini --run-both --yes
```

## 9. Result and history commands

### View the latest detailed result

```text
PYTHON run/main.py view-result
```

### Select a session from a numbered list

```text
PYTHON run/main.py view-result --select
```

### View a known session ID

```text
PYTHON run/main.py view-result --session-id SESSION_ID
```

Detailed viewing is scoped to the current tester. A session ID belonging to a
different tester is not found through this command.

### Show the current tester's run-history overview

```text
PYTHON run/main.py compare
```

### Show metrics and run history

```text
PYTHON run/main.py metrics
```

Filter metrics to one model:

```text
PYTHON run/main.py metrics --model openai/gpt-4o-mini
```

### Compare any two personal sessions interactively

```text
PYTHON run/main.py compare-detailed
```

### Compare any two sessions across testers

```text
PYTHON run/main.py compare-detailed --all-testers
```

### Compare two known session IDs directly

Personal sessions:

```text
PYTHON run/compare_sessions.py --left-session SESSION_ID_1 --right-session SESSION_ID_2
```

Across testers:

```text
PYTHON run/compare_sessions.py --left-session SESSION_ID_1 --right-session SESSION_ID_2 --all-testers
```

### Select a compatible personal V1/V2 pair

```text
PYTHON run/main.py compare-v1-v2
```

Include compatible pairs across testers:

```text
PYTHON run/main.py compare-v1-v2 --all-testers
```

### Compare two known V1/V2 session IDs directly

```text
PYTHON run/compare_v1_v2.py --v1-session V1_SESSION_ID --v2-session V2_SESSION_ID
```

Add `--all-testers` only when the selected IDs belong to different tester
directories.

## 10. Output files

Each tester has a directory under:

```text
results/<tester_name>/
```

The long-term historical sources are:

```text
run_history.jsonl       one completed session per line
metrics_log.jsonl       one case trial per line
decision_ledger.jsonl   one actual decision action per line
```

Latest-result JSON files and comparison JSON files are derived views. Existing
2.5 result files remain readable without conversion.

## 11. Safe interruption and concurrency

- Press `Ctrl+C` during an evaluation to cancel it. An incomplete session is
  rolled back rather than published as completed.
- If the process is forcibly closed during commit, the next application start
  restores the interrupted transaction before showing results.
- Two writers cannot update the same tester history at the same time.
- Different testers can run independently.
- Comparison reports are derived and atomically replaced; they do not replace
  the append-only history.

## 12. API-key safety

- Prefer entering the key through Settings or the live-run prompt. Input is
  represented by `*` characters.
- The key is saved only in the gitignored local configuration.
- Do not place a real key in source code, screenshots, reports, or commands
  committed to the repository.
- Provider errors and evaluation traces redact API keys and bearer tokens.
- If `OPENROUTER_API_KEY` is set in the environment, it normally takes
  precedence. A replacement entered during the current application session is
  used immediately, and the program warns if the environment variable should
  be updated before the next launch.

## 13. Help and command discovery

List all top-level direct commands:

```text
PYTHON run/main.py --help
```

Show options for a particular command:

```text
PYTHON run/main.py eval --help
PYTHON run/main.py live --help
PYTHON run/main.py view-result --help
```

When in doubt, use the launcher script and the interactive menu. It provides
the safest path for environment setup, API checking, paid-run previews, and
result selection.
