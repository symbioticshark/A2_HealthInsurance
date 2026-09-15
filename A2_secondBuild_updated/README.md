# PE6201 A2 Agent 2.5

This is the updated team-testing version of the Problem A health-insurance
agent. Normal use does not require typing Python commands. Windows and macOS
launchers prepare the private environment, install the required dependency,
open the menu, run the selected evaluation, and save the results.

Use this folder, `A2_secondBuild_updated`. Do not use the older
`A2_secondBuild` folder for new experiments because its cost reporting and
user interface are from an earlier version.

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

## Before starting

You need:

1. The complete `A2_secondBuild_updated` folder. Keep its files and subfolders
   together.
2. An internet connection for first-time dependency setup and live runs.
3. Python 3.9 or newer already available somewhere on the computer.
4. An OpenRouter API key for live runs. Scripted runs do not use an API key or
   spend OpenRouter credit.

The launcher never installs Python. If it cannot find Python automatically, it
asks for the full path to a Python executable that is already installed.

## Windows: step-by-step

1. Open the `A2_secondBuild_updated` folder in File Explorer.
2. Double-click `Run_A2_Agent.bat`.
3. Wait while the launcher checks Python and the private project environment.
4. If Python is not found, enter the full path to `python.exe`. You may enter
   `B` to exit without changing the project.
5. On the first successful launch, enter your tester name. Use the same name
   for later runs if you want them kept in the same personal history.
6. Select an option from the main menu by typing its letter and pressing Enter.
7. When finished, select `Q` to exit.

The first launch can take longer because the private environment and dependency
must be prepared. Later launches normally reuse that environment.

## macOS: step-by-step

1. Open the `A2_secondBuild_updated` folder in Finder.
2. Right-click `Run_A2_Agent.command` and choose **Open** the first time.
3. Wait while the launcher checks Python and prepares the private environment.
4. If Python is not found, enter the full path to an existing Python 3.9 or
   newer executable. You may enter `B` to exit.
5. Enter your tester name when requested.
6. Use the same letter-and-number menus described below.
7. Select `Q` when finished.

If macOS says the command file is not executable, open Terminal in this folder
and run this once:

```bash
chmod +x Run_A2_Agent.command
```

Then right-click the command file and choose **Open** again. The launcher works
on both Apple Silicon and Intel Macs; it creates a Mac-compatible private
environment rather than trying to use a Windows `.venv` copied with the folder.

## Main menu

### A. Check environment, data, and configuration

Use this first. It displays the app version, Python environment, configured
model, backend, number of cases, number of negative cases, and personal result
directory. It does not call a model or spend credit.

### B. Scripted standard battery

Runs the deterministic local agent without OpenRouter. It follows the
assignment repetition rule: 24 ordinary cases once and 16 negative cases three
times, for 72 runs in total. This is useful for checking the data and local
logic without spending credit.

### C. Live run

Opens four choices:

1. **Quick validation** — all 40 cases once, for 40 paid model runs.
2. **Standard battery** — 24 ordinary cases once plus 16 negative cases three
   times, for 72 paid model runs. This is the assignment-aligned option.
3. **Negative only** — the 16 negative cases three times, for 48 paid model
   runs.
4. **Select cases and repetitions** — choose particular case IDs and how many
   times each selected case should run.

Before a live run starts, the program asks you to choose V1 or V2 and then
choose the model. It displays a complete preview and asks `Start this run? Y/N`.
No paid case request is made if you answer `N`.

### D. View latest result

Shows the most recent completed result for the current tester, including model,
mode, V1/V2, number of runs, accuracy, tokens, cost, time, and observed balance
change when available.

### E. Compare results

Choose either:

1. Your own run history.
2. All testers and the shared baseline.

For a fair model comparison, compare runs made with the same tool-interface
version and the same run mode. A 40-run quick validation should not be presented
as equivalent to a 72-run standard battery.

### F. Change tester, API key, or default model

Use this to change the tester name, replace the OpenRouter API key, or select a
different default model. API-key input is hidden on screen.

### Q. Exit

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

The two most useful files are:

- `<tester_name>_result.json` — the distilled result containing the environment,
  configuration, totals, accuracy, cost, important failures, and compact
  per-case evidence. Use this first for the report and demonstration video.
- `<tester_name>_run_log.json` — full details for every case trial.

The folder also contains append-only metric and session history used by the
comparison menu, plus the decision ledger. A newly completed run replaces that
tester's latest distilled result and full run log, while the history files keep
earlier completed sessions for comparison.

## Stopping safely

- Before execution begins, answer `N` at the run preview.
- During an evaluation, press `Ctrl+C`. The current operation is cancelled and
  the menu returns without publishing a partial run as completed.
- During environment preparation, close the window if necessary. Run the
  launcher again later and it will repair the private environment.
- Use `Q` for a normal exit.

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

Use main-menu option `F`, choose **Change API key**, and enter the correct key.
The updated error message includes OpenRouter's response explanation.

### Old prices or old screen layout appear

Check that the launcher came from `A2_secondBuild_updated` and that the main
menu shows `PE6201 A2 Agent 2.5`. Results produced by the old `A2_secondBuild`
version used an earlier estimated-cost system and should not be used as new
measured-cost evidence.
