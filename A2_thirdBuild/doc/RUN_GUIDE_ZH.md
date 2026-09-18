# PE6201 A2 Agent 3.0——运行指南（中文版）

本文档介绍受支持的启动脚本、手动环境配置、交互式操作、纯命令运行、
结果查看以及异常恢复行为。

## 1. 运行要求

- 保持完整的 `A2_thirdBuild` 目录及其子目录结构不变。
- 使用 Python 3.9 或更高版本。
- 只有安装依赖和执行 Live 测试时需要网络连接。
- 只有执行 Live 测试时需要 OpenRouter API key。
- 除非某节另有说明，所有命令都应在 `A2_thirdBuild` 根目录运行。

Scripted 评估、Guardrail 检查、结果查看和结果比较都不会产生付费模型请求。

## 2. 推荐启动方式：启动脚本

对于日常使用，启动脚本是最安全的入口。它们会自动：

1. 查找兼容的 Python 安装。
2. 在 `config/.venv` 创建或修复项目私有环境。
3. 安装 `config/requirements.txt` 中的依赖。
4. 通过 `run/main.py` 启动交互式菜单。

### Windows

双击：

```text
run\Run_A2_Agent.bat
```

也可以在 `A2_thirdBuild` 目录中打开 PowerShell，然后运行：

```powershell
.\run\Run_A2_Agent.bat
```

### macOS

第一次启动时，在 Finder 中右键单击 `run/Run_A2_Agent.command`，然后选择
**Open（打开）**。

也可以使用 Terminal：

```bash
chmod +x run/Run_A2_Agent.command
./run/Run_A2_Agent.command
```

Windows 和 macOS 启动器会分别创建适用于本平台的虚拟环境。不要把 Windows
生成的 `config/.venv` 复制到 Mac，也不要反向复制。

## 3. 交互式菜单

不带任何命令启动 `run/main.py` 时，会打开以下菜单：

```text
1. Environment check
2. Run
3. Results
4. Settings
5. Help
6. Exit
```

第一次启动时需要输入测试者姓名。API key 是可选项，可以跳过。测试结果会存放在
`results/` 下该测试者专属的目录中。

### Run 菜单

- **Scripted evaluation**——确定性、本地运行且免费。
- **Guardrail checklist**——单独执行 D3 安全检查；它不是 40-case 评估集。
- **Live evaluation**——通过 OpenRouter 模型进行付费测试，运行前会检查 API 并显示
  成本预览。
- **V1/V2 live comparison**——使用同一模型分别运行一套标准 V1 battery 和一套标准
  V2 battery，然后比较两个已完成的 Session。

V1 是有意保留缺陷的实验基线，只应用于对照实验。V2 是修正后的工具接口。

### Results 菜单

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

## 4. 手动配置环境

只有在无法使用启动脚本时才需要执行本节操作。

### Windows PowerShell

```powershell
py -3 -m venv config\.venv
.\config\.venv\Scripts\python.exe -m pip install -r config\requirements.txt
.\config\.venv\Scripts\python.exe .\run\main.py
```

如果系统没有 `py`，请用 Python 3.9 或更高版本解释器的完整路径替换 `py -3`。

### macOS Terminal

```bash
python3 -m venv config/.venv
./config/.venv/bin/python -m pip install -r config/requirements.txt
./config/.venv/bin/python run/main.py
```

## 5. 纯命令运行约定

下面使用 `PYTHON` 代表项目私有环境中的 Python 解释器。

Windows：

```powershell
$PYTHON = ".\config\.venv\Scripts\python.exe"
```

macOS：

```bash
PYTHON="./config/.venv/bin/python"
```

PowerShell 使用 `& $PYTHON` 执行命令；macOS 使用 `$PYTHON`。

示例：

```powershell
& $PYTHON .\run\main.py check
```

```bash
$PYTHON run/main.py check
```

以下示例请根据所用平台选择对应的路径分隔符。

## 6. 环境检查

```text
PYTHON run/main.py check
```

该命令会显示程序版本、测试者、Python 解释器、数据集数量、默认模型、工具接口、
API key 状态和结果目录。如果已经配置 API key，还会进行一次不调用模型的连通性
检查。该检查不会产生模型费用。

## 7. Scripted 命令

### 运行一个 case 并打印执行轨迹

```text
PYTHON run/main.py run CLM-8850
```

### 使用 V2 将所有评估 case 各运行一次

```text
PYTHON run/main.py eval --tool-interface v2 --verbose
```

### 运行符合课程要求的标准 battery

```text
PYTHON run/main.py eval --standard-battery --tool-interface v2 --verbose
```

标准 battery 会将每个预期 ordinary case 运行一次，将每个预期 negative case 运行
三次。对于当前数据集，总计为 72 个 case trial。

### 运行指定 case

```text
PYTHON run/main.py eval --cases CLM-8850 CLM-8888 --trials 1 --tool-interface v2 --verbose
```

### 将指定 case 各运行三次

```text
PYTHON run/main.py eval --cases CLM-8850 CLM-8888 --trials 3 --tool-interface v2 --verbose
```

### 选择 autonomy 设置

```text
PYTHON run/main.py eval --cases CLM-8850 --autonomy confirm --tool-interface v2
```

有效的 autonomy 值为 `suggest`、`confirm` 和 `act`。

### 运行 D3 Guardrail Checklist

```text
PYTHON agent/guardrail_checklist.py --tool-interface v2
```

如果需要证明代码 Guardrail 在实验接口下仍然有效，可以运行：

```text
PYTHON agent/guardrail_checklist.py --tool-interface v1
```

### 运行失败演示

```text
PYTHON run/main.py failures --case-id CLM-8888
```

### 运行 parallel 与 sequential 的 D2(c) 实验

```text
PYTHON eval/measure_parallel_vs_sequential.py
```

该实验使用 scripted backend，不会消耗 API 余额。

## 8. Live 命令

Live 命令可能消耗 OpenRouter 余额。程序会先通过不调用模型的请求验证 API key。
如果验证失败，用户可以重试、输入并保存新的 key，或者取消运行。

如果希望获得最清晰的成本预览和确认流程，建议使用交互式菜单。纯命令 `live` 在
API 检查成功后会立即开始付费 case，不会再次显示最终成本确认页面。

### 使用一个模型运行指定 case

```text
PYTHON run/main.py live --models openai/gpt-4o-mini --cases CLM-8850 CLM-8888 --trials 1 --verbose
```

### 使用一个模型将所有评估 case 各运行一次

```text
PYTHON run/main.py live --models openai/gpt-4o-mini --trials 1 --verbose
```

### 使用多个模型运行相同 case

```text
PYTHON run/main.py live --models openai/gpt-4o-mini google/gemini-2.5-flash --cases CLM-8850 CLM-8888 --trials 1 --verbose
```

纯命令 `live` 会使用 Settings 中保存的工具接口版本。运行前请通过交互式 Settings
菜单修改默认版本。

### 运行完整的 V1/V2 Live 对比

```text
PYTHON run/run_v1_v2_live_battery.py --model openai/gpt-4o-mini --run-both
```

该命令会：

1. 在不调用模型的情况下检查 API key。
2. 显示付费运行次数和当前可用的成本估算。
3. 请求用户确认。
4. 运行正常的 V1 标准 battery。
5. 运行正常的 V2 标准 battery。
6. 只有在两个 Session 都完成后才生成详细的 V1/V2 对比。

如果 V1 已完成但 V2 被中断，有效的 V1 Session 会保留在正常历史中，同时不会生成
错误的“完整对比”报告。

`--yes` 会跳过最后的付费运行确认，只应在明确的自动化流程中使用：

```text
PYTHON run/run_v1_v2_live_battery.py --model openai/gpt-4o-mini --run-both --yes
```

## 9. 结果和历史命令

### 查看最新一次详细结果

```text
PYTHON run/main.py view-result
```

### 从编号列表选择 Session

```text
PYTHON run/main.py view-result --select
```

### 查看指定的 Session ID

```text
PYTHON run/main.py view-result --session-id SESSION_ID
```

详细结果查看仅限当前测试者。如果 Session ID 属于其他测试者，该命令会显示未找到。

### 查看当前测试者的运行历史概览

```text
PYTHON run/main.py compare
```

### 查看指标和运行历史

```text
PYTHON run/main.py metrics
```

只查看指定模型的指标：

```text
PYTHON run/main.py metrics --model openai/gpt-4o-mini
```

### 交互式比较当前测试者的任意两个 Session

```text
PYTHON run/main.py compare-detailed
```

### 跨测试者比较任意两个 Session

```text
PYTHON run/main.py compare-detailed --all-testers
```

### 直接比较两个已知 Session ID

当前测试者的 Session：

```text
PYTHON run/compare_sessions.py --left-session SESSION_ID_1 --right-session SESSION_ID_2
```

跨测试者：

```text
PYTHON run/compare_sessions.py --left-session SESSION_ID_1 --right-session SESSION_ID_2 --all-testers
```

### 选择一对兼容的个人 V1/V2 Session

```text
PYTHON run/main.py compare-v1-v2
```

包含跨测试者的兼容组合：

```text
PYTHON run/main.py compare-v1-v2 --all-testers
```

### 直接比较两个已知的 V1/V2 Session ID

```text
PYTHON run/compare_v1_v2.py --v1-session V1_SESSION_ID --v2-session V2_SESSION_ID
```

只有当所选 ID 属于不同测试者目录时，才需要添加 `--all-testers`。

## 10. 输出文件

每个测试者都在以下位置拥有独立目录：

```text
results/<tester_name>/
```

长期历史数据源为：

```text
run_history.jsonl       每行代表一个已完成的 Session
metrics_log.jsonl       每行代表一个 case trial
decision_ledger.jsonl   每行代表一次实际决策动作
```

最近一次结果 JSON 和各类比较 JSON 都是派生视图。现有 2.5 结果无需转换即可继续读取。

## 11. 安全中断和并发

- 在评估过程中按 `Ctrl+C` 可以取消运行。未完成的 Session 会回滚，而不会被发布为
  已完成结果。
- 如果进程在提交阶段被强制关闭，程序会在下次启动时先恢复未完成事务，再显示结果。
- 两个写入进程不能同时更新同一测试者的历史。
- 不同测试者可以相互独立地运行。
- 比较报告是派生文件，并通过原子替换更新；它们不会替换 append-only 历史。

## 12. API key 安全

- 建议通过 Settings 或 Live 运行提示输入 key。输入内容会用 `*` 表示。
- key 只保存在被 Git 忽略的本地配置中。
- 不要把真实 key 写入源代码、截图、报告或会提交到仓库的命令记录中。
- Provider 错误和评估 trace 会对 API key 与 Bearer token 进行脱敏。
- 如果环境中设置了 `OPENROUTER_API_KEY`，它通常具有更高优先级。在当前程序会话中
  输入的新 key 会立即生效；如果下次启动前还需要更新环境变量，程序会给出提醒。

## 13. 帮助和命令查询

列出所有顶层纯命令：

```text
PYTHON run/main.py --help
```

查看某个命令的参数：

```text
PYTHON run/main.py eval --help
PYTHON run/main.py live --help
PYTHON run/main.py view-result --help
```

如果不确定应该使用哪个命令，请使用启动脚本和交互式菜单。它们提供最安全的环境
配置、API 检查、付费运行预览和结果选择流程。
