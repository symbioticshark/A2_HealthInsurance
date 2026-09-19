# PE6201 A2 Health Insurance Agent

This repository contains the complete development history of our Problem A health-insurance claim decision agent. The system supports deterministic scripted evaluation, live LLM evaluation, safety guardrails, cost tracking, and reproducible result analysis.

The current release is **Version 3.0** in `A2_thirdBuild/`. Earlier builds are retained for traceability and should not be used for new test runs.

## Team and Contributions

| Team member | Main contribution |
|---|---|
| Mutya Sai Surya Subrahmanya Karthikeya | Agent loop and insurance tools |
| Zhang Peiqi | Agent loop and insurance tools |
| Chen Yayue | Tool descriptors, V1/V2 refinement, and guardrails |
| Shao Xinrong | Evaluation harness and scripted evaluation |
| Weng Yongting | Evaluation harness and scripted evaluation |
| Lin Genxin | Cost model, decision ledger, and sensitivity analysis |

All members contributed test cases, ran a live model, and supported the report and video demonstration. See the [full contribution record](A2_thirdBuild/CONTRIBUTIONS.md).

## Build History

| Build | Purpose and main changes |
|---|---|
| `A2_firstBuild/` | Original scaffold, reference data, and early implementation work. |
| `A2_secondBuild/` | First complete runnable agent with scripted and live evaluation. |
| `A2_secondBuild_updated/` | Version 2.5: stabilized team testing, launchers, per-tester results, V1/V2 selection, progress display, and live cost reporting. |
| `A2_thirdBuild/` | **Version 3.0:** layered architecture, session-based history and comparison, Version 2.5 result compatibility, safer configuration, transactional result writing, improved guardrails, and reproducible D7 failure tests. |

## Repository Structure

```text
A2_HealthInsurance/
├── A2_firstBuild/            # Initial scaffold and reference material
├── A2_secondBuild/           # First complete evaluation build
├── A2_secondBuild_updated/   # Version 2.5
└── A2_thirdBuild/            # Current Version 3.0
    ├── agent/                # Agent loop and orchestration
    ├── backend/              # Scripted and live model backends
    ├── config/               # Local configuration and environment
    ├── data/                 # Evaluation and guardrail cases
    ├── eval/                 # Metrics, history, and comparison logic
    ├── results/              # Per-tester outputs
    ├── run/                  # Entry points and launchers
    ├── tool/                 # V1/V2 tools and guardrails
    └── doc/                  # User and technical documentation
```

## Requirements and Configuration

- Python **3.9 or newer**
- Windows or macOS
- An API key is required only for live-model runs; scripted, guardrail, and D7 tests do not require one
- The managed virtual environment is created under `A2_thirdBuild/config/.venv`
- API-key priority: environment variable, current-process setting, then local configuration

Local keys, virtual environments, result locks, and operating-system metadata are excluded from Git.

## Start Version 3.0

Enter the current build first:

```powershell
cd A2_thirdBuild
```

Windows launcher:

```powershell
.\run\Run_A2_Agent.bat
```

macOS launcher:

```bash
chmod +x run/Run_A2_Agent.command
./run/Run_A2_Agent.command
```

Direct Python entry:

```bash
python run/main.py setup --name "Tester Name" --api-key
python run/main.py
```

The setup command requests the API key through masked input. If no tester name is configured before a run, Version 3.0 assigns a unique name automatically.

## Documentation

- [Version 3.0 overview](A2_thirdBuild/README.md)
- [English run guide](A2_thirdBuild/doc/RUN_GUIDE.md)
- [Chinese run guide](A2_thirdBuild/doc/RUN_GUIDE_ZH.md)
- [D7 reproduced-failure guide](A2_thirdBuild/doc/D7_REPRODUCED_FAILURES.md)
- [Version 3.0 debug and upgrade log](A2_thirdBuild/doc/DEBUG_LOG_v3.0.md)
- [Detailed team contributions](A2_thirdBuild/CONTRIBUTIONS.md)

## Common Problems

- **macOS reports permission denied:** run `chmod +x run/Run_A2_Agent.command` and try again.
- **Python is not found:** install Python 3.9+ and ensure it is available from the terminal.
- **A saved API key is not being used:** check the environment variable first because it has the highest priority.
- **A tester name already exists:** use a different name, or deliberately reuse it with the documented existing-tester option.
- **Live evaluation is unavailable:** verify the key and network connection; scripted evaluation remains available without either.
- **The interface does not show Version 3.0:** confirm that the current directory is `A2_thirdBuild` before starting the program.
