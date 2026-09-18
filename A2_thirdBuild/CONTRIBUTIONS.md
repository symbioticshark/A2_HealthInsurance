# 贡献记录 / Contribution Log


## 个人贡献范围 / Individual Contribution Scopes

### Mutya Sai Surya Subrahmanya Karthikeya

- 分工：完整的 `data/` 文件夹、`agent/loop.py`、`agent/failures.py`、
  `backend/live_backend.py` 与 `run/main.py`。
- 对应代码范围：`data/` 下的全部数据、fixtures、labels 与数据校验文件，以及上述
  Agent、backend 与主运行入口文件。

- Allocated work: the complete `data/` folder, `agent/loop.py`,
  `agent/failures.py`, `backend/live_backend.py`, and `run/main.py`.
- Current code scope: all data, fixtures, labels, and data-validation files in
  `data/`, together with the listed agent, backend, and main-runner files.

### Zhang Peiqi

- 分工：完整的 `tool/` 文件夹、`run/Run_A2_Agent.bat`、
  `run/Run_A2_Agent.command`、`config/config.py`、`config/local_settings.py`
  与 `config/requirements.txt`。

- Allocated work: the complete `tool/` folder, `run/Run_A2_Agent.bat`,
  `run/Run_A2_Agent.command`, `config/config.py`,
  `config/local_settings.py`, and `config/requirements.txt`.

### Chen Yayue

- 分工：完整的 `agent/guardrails.py`、`agent/guardrail_checklist.py`、
  `eval/measure_v1_v2_tool_tokens.py`、
  `eval/measure_parallel_vs_sequential.py` 与
  `run/run_v1_v2_live_battery.py`。

- Allocated work: the complete `agent/guardrails.py`,
  `agent/guardrail_checklist.py`, `eval/measure_v1_v2_tool_tokens.py`,
  `eval/measure_parallel_vs_sequential.py`, and
  `run/run_v1_v2_live_battery.py`.

### Shao Xinrong

- 分工：完整的 `backend/scripted_backend.py`。

- Allocated work: the complete `backend/scripted_backend.py`.

### Weng Yongting

- 分工：完整的 `eval/eval_harness.py`。

- Allocated work: the complete `eval/eval_harness.py`.

### Lin Genxin

- 分工：完整的 `backend/cost_model.py`、`eval/metrics.py` 与
  `config/model_catalog.json`。
- 说明：上述文件为独立负责范围，没有其他成员参与。
- 提交证据：待确认。

- Allocated work: the complete `backend/cost_model.py`, `eval/metrics.py`,
  and `config/model_catalog.json`.

## 全员共同负责的工作 / Team-Wide Required Work

分工图将以下两项列为每位成员都必须完成的工作。待从团队记录核实后，应补入每位
成员的模型、案例、文档路径与 commit hash。

The allocation chart identifies the following as work required from every
member. Once verified from the team records, add each member's model, case IDs,
document paths, and commit hash.

| 必须完成的工作 / Required work | 当前文件或目标位置 / Current files or destination | 待补证据 / Evidence still needed |
| --- | --- | --- |
| Evaluation cases（D4） | `data/expected_outcomes_A.json`、`data/data_A/` | 每位成员的 case ID 与 commit hash / Each member's case IDs and commit hash |
| 每人一个 live-model battery（D5(b)） / One live-model battery per member | `results/<tester>/`、`run/run_v1_v2_live_battery.py` | 测试者姓名、模型 ID、结果路径与 commit hash / Tester name, model ID, result path, and commit hash |
| Report 与 demo 汇总 / Report and demo assembly | `doc/` | 每位成员的报告或 demo 文件路径与 commit hash / Each member's report or demo path and commit hash |

## 不单独分配的支持文件 / Support Files Not Individually Assigned

目录初始化文件、README、后续报告文档和 `results/` 中的运行产物不作为独立代码贡献
逐一分配。复制历史结果后，仍应保留结果中的测试者姓名、模型与运行记录。

Package-initialisation files, the README, future report documents, and run
artifacts in `results/` are not individually allocated as standalone code
contributions. After copying historical results, preserve the tester name,
model, and run record in each result.
