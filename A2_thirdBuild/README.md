# PE6201 A2 Agent 3.0

This is the updated team-testing version of the Problem A health-insurance
agent. Normal use does not require typing Python commands. Windows and macOS
launchers prepare the private environment, install the required dependency,
open the menu, run the selected evaluation, and save the results.

Use this folder, `A2_thirdBuild`. It keeps the same application behaviour as
the updated build, with files reorganised into explicit data, tool, agent,
backend, evaluation, run, configuration, results, and documentation layers.

## What the updated version provides

- One guided launcher for Windows and one for macOS.
- Automatic Python detection, with an option to enter an existing Python
  executable path when automatic detection fails.
- Automatic creation or repair of the private `.venv` environment.
- Separate result folders for each tester.
- Independent selection of the V1 or V2 tool interface and the model.
- Quick, assignment-standard, negative-only, and custom live runs.
- A visible progress bar and case-by-case status during an evaluation.
- A run preview showing the model, mode, repetitions, balance, and estimated
  cost before any paid request starts.
- OpenRouter-reported token and cost accounting, including cache and reasoning
  token fields when OpenRouter provides them.
- A local list of 20 suitable models whose prices are refreshed from
  OpenRouter when the model menu opens.
- Personal history and comparison with other testers and the shared baseline.
- Safe cancellation: an interrupted evaluation does not publish a partial
  result as a completed run.
- A per-tester writer lock prevents two concurrent evaluations from merging
  into the same history, while different testers remain independent.

## Before starting

You need:

1. The complete `A2_thirdBuild` folder. Keep its files and subfolders
   together.
2. An internet connection for first-time dependency setup and live runs.
3. Python 3.9 or newer already available somewhere on the computer.
4. An OpenRouter API key for live runs. Scripted runs do not use an API key or
   spend OpenRouter credit.

The launcher never installs Python. If it cannot find Python automatically, it
asks for the full path to a Python executable that is already installed.

After the launcher has prepared the private environment, developers may also
run `run/main.py` with that environment's Python. This starts the same program
but skips launcher checks, environment repair, and dependency installation.

## Windows: step-by-step

1. Open the `A2_thirdBuild/run` folder in File Explorer.
2. Double-click `Run_A2_Agent.bat`.
3. Wait while the launcher checks Python and the private project environment.
4. If Python is not found, enter the full path to `python.exe`. You may enter
   `B` to exit without changing the project.
5. On the first successful launch, enter your tester name. Use the same name
   for later runs if you want them kept in the same personal history.
6. Select an option from the main menu by typing its number and pressing Enter.
7. When finished, select `6` to exit.

The first launch can take longer because the private environment and dependency
must be prepared. Later launches normally reuse that environment.

## macOS: step-by-step

1. Open the `A2_thirdBuild/run` folder in Finder.
2. Right-click `Run_A2_Agent.command` and choose **Open** the first time.
3. Wait while the launcher checks Python and prepares the private environment.
4. If Python is not found, enter the full path to an existing Python 3.9 or
   newer executable. You may enter `B` to exit.
5. Enter your tester name when requested.
6. Use the numbered menus described below.
7. Select `6` when finished.

If macOS says the command file is not executable, open Terminal in the `run`
folder
and run this once:

```bash
chmod +x Run_A2_Agent.command
```

Then right-click the command file and choose **Open** again. The launcher works
on both Apple Silicon and Intel Macs; it creates a Mac-compatible private
environment rather than trying to use a Windows `.venv` copied with the folder.

## Main menu

### 1. Environment check

Use this first. It displays the app version, Python environment, configured
model, backend, number of cases, number of negative cases, and personal result
directory. When a key is configured, it also validates that key through a
no-inference API request. It does not call a model or spend model credit.

### 2. Run

The Run menu contains scripted evaluation, the separate guardrail checklist,
live evaluation, and the V1/V2 live comparison.

#### Scripted evaluation

Runs the deterministic local agent without OpenRouter. It follows the
assignment repetition rule: 24 ordinary cases once and 16 negative cases three
times, for 72 runs in total. This is useful for checking the data and local
logic without spending credit.

#### Guardrail checklist

Runs the separate D3 checklist without OpenRouter. This is not the 40-case
business evaluation set.

#### Live evaluation

Opens four choices:

1. **Quick validation** — all 40 cases once, for 40 paid model runs.
2. **Standard battery** — 24 ordinary cases once plus 16 negative cases three
   times, for 72 paid model runs. This is the assignment-aligned option.
3. **Negative only** — the 16 negative cases three times, for 48 paid model
   runs.
4. **Select cases and repetitions** — choose particular case IDs and how many
   times each selected case should run.

Before a live run starts, the program validates the configured API key without
calling a model. If validation fails, the user can retry, enter and atomically
save a replacement key, or cancel. The program then asks for the tool version
and model, displays a complete preview, and asks `Start this run? Y/N`. No paid
case request is made if you answer `N`.

#### V1/V2 live comparison

Runs one normal V1 standard battery and one normal V2 standard battery with the
same model. Both runs enter the ordinary tester history, after which the shared
V1/V2 comparison engine writes `v1_v2_detailed_comparison.json` in that
tester's folder.

### 3. Results

One compact screen groups six actions under individual details, history, and
comparison:

1. Latest detailed result.
2. Select a session to view.
3. Run-history overview.
4. Compare any two sessions, including the existing across-tester comparison.
5. Compare matching personal V1/V2 sessions.
6. All-testers overview.

Legacy 2.5 history is read without rewriting its source files.

For a fair model comparison, compare runs made with the same tool-interface
version and the same run mode. A 40-run quick validation should not be presented
as equivalent to a 72-run standard battery.

### 4. Settings

Use this to change the tester name, replace the OpenRouter API key, or select a
different default model, set the default tool interface, or check API
connectivity. API-key input is represented by `*` characters on screen.

### 5. Help

Shows the quick start, menu structure, trial rules, session/result model,
API/cost safety notes, and direct command-line usage.

### 6. Exit

Closes the program normally.

## V1 and V2

V1 and V2 are tool-interface versions, not models.

- **V1** is the intentionally defective experimental version. Its claim-history
  tool is unfiltered and uncapped. Use it only when you deliberately want to
  demonstrate the failure.
- **V2** is the corrected version. Claim history is filtered to the relevant
  member and limited to five records.

The program asks for V1 or V2 separately on every live run. Choose V2 for normal
testing. Choose V1 only for a controlled comparison and confirm the warning.

## Choosing a model

The model menu contains 20 team-ready models with input and output prices. When
the menu opens, the program reads OpenRouter's public model catalog and refreshes
the listed prices for the current session. If OpenRouter cannot be reached, the
saved local prices remain available.

To use a model that is not listed, choose **Add a model**, enter the exact
OpenRouter model ID, review its input and output prices, and confirm. The model
is then available in that tester's configuration without editing source code.

## Cost and balance information

Before a live run, the program displays:

- Current OpenRouter balance when available.
- Estimated cost and the basis of that estimate.
- Projected balance after the run.

After the run, it displays:

- Balance after the run.
- Observed balance change.
- The sum of OpenRouter-reported request costs.

The final cost uses the `usage.cost` returned by OpenRouter for each model call.
The model prices in `model_catalog.json` are prediction fallbacks, not a
replacement for OpenRouter's actual charged cost. Small differences between
the run cost and balance change can occur if the account is used elsewhere at
the same time or the balance service updates at a different moment.

## Where results are saved

Every tester receives a separate folder:

```text
results/<tester_name>/
```

The latest-result convenience files are:

- `<tester_name>_result.json` — the distilled result containing the environment,
  configuration, totals, accuracy, cost, important failures, and compact
  per-case evidence. Use this first for the report and demonstration video.
- `<tester_name>_run_log.json` — full details for every case trial.

The historical source of truth is append-only:

- `run_history.jsonl` — one row per completed evaluation session.
- `metrics_log.jsonl` — one row per case trial.
- `decision_ledger.jsonl` — one row per emitted decision action.

A newly completed run replaces the latest convenience files, but not this
history. `comparison_report.json` remains the multi-session overview. The two
overwriteable derived two-session reports are `detailed_comparison.json` and
`v1_v2_detailed_comparison.json`, both inside the tester folder.

## Stopping safely

- Before execution begins, answer `N` at the run preview.
- During an evaluation, press `Ctrl+C`. The current operation is cancelled and
  the menu returns without publishing a partial run as completed.
- During environment preparation, close the window if necessary. Run the
  launcher again later and it will repair the private environment.
- Use main-menu option `6` for a normal exit.

## Common problems

### Python was not detected

Enter the full path to an existing Python 3.9 or newer executable. The launcher
will validate it before creating the private environment. It will not ask you
to install Python.

### Dependency setup did not complete

Check the internet connection and run the launcher again. It repairs the
private environment safely.

### Model is unavailable

Return to the model menu and choose another model. OpenRouter model availability
can change over time.

### OpenRouter reports an authentication error

Use main-menu option `4`, choose **Change API key**, and enter the correct key.
The program immediately rechecks the replacement without calling a model.

### Old prices or old screen layout appear

Check that the launcher came from `A2_thirdBuild/run` and that the main
menu shows `PE6201 A2 Agent 3.0`. Results produced by the old `A2_secondBuild`
version used an earlier estimated-cost system and should not be used as new
measured-cost evidence.
