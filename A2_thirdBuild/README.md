# PE6201 A2 Agent 3.0

A single-agent health-insurance claim assessment system for PE6201 Assignment
2, Problem A. The project supports deterministic scripted evaluation, live
OpenRouter model testing, a separate guardrail checklist, V1/V2 tool-interface
comparison, cost instrumentation, and reproducible D7 failure experiments.

Python 3.9 or newer is required. An OpenRouter API key is required only for
live runs; scripted evaluation, guardrail checks, and D7 experiments are free.

## Project structure

```text
A2_thirdBuild/
├── agent/      agent loop, guardrails, checklist, and D7 failures
├── backend/    scripted/live backends, API checks, and cost model
├── config/     application settings, local settings, and model catalog
├── data/       Problem A fixtures, labels, and validation utilities
├── eval/       evaluation harness, metrics, sessions, and measurements
├── run/        program entry point, launchers, result views, and comparisons
├── tool/       versioned V1/V2 tool interfaces and shared registry
├── results/    tester histories and derived reports
└── doc/        operating guides, debug logs, and D7 documentation
```

## Quick start

### Windows

Open `run/Run_A2_Agent.bat`. The launcher prepares the private environment and
opens the numbered menu.

### macOS

Open `run/Run_A2_Agent.command`. If macOS blocks it, run:

```bash
chmod +x run/Run_A2_Agent.command
./run/Run_A2_Agent.command
```

### Direct Python entry

After activating the project environment:

```bash
python run/main.py setup --name "Tester Name" --api-key
python run/main.py
```

The `--api-key` flag opens masked input; it does not accept a literal key on
the command line. If a tester name already owns a result directory, setup
stops with a warning unless `--allow-existing-tester` is deliberately added.
When a run starts without a configured tester, the system assigns a unique
name automatically. `OPENROUTER_API_KEY` in the environment always has the
highest key priority.

Use **Environment check** before a live run. The menu performs a no-inference
API connectivity check and asks for confirmation before paid evaluation.

## Help and documentation

- [English run guide](doc/RUN_GUIDE.md)
- [中文运行指南](doc/RUN_GUIDE_ZH.md)
- [D7 reproduced-failure method and results](doc/D7_REPRODUCED_FAILURES.md)
- [Version 3.0 debug log](doc/DEBUG_LOG_v3.0.md)
- [Version 2.5 debug log](doc/DEBUG_LOG_v2.5.md)
- [Original debug log](doc/DEBUG_LOG.md)
- [Contribution record](CONTRIBUTIONS.md)

For command discovery:

```bash
python run/main.py --help
python run/run_d7_failures.py --help
```
