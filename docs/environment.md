# 统一 uv 运行环境

## 强制约定

四位成员及 CI 使用同一份 Python pin、依赖锁文件和 CPU 运行配置。每份 clone / worktree 拥有自己的 `.venv`，不能共用或提交虚拟环境目录。

| 项目 | 固定值 |
| --- | --- |
| uv | 0.12.23，由 `tool.uv.required-version` 强制检查 |
| Python | uv 管理的 CPython 3.11.17，精确到补丁版本 |
| NumPy | 2.4.6 |
| PyTorch | 2.14.1；Windows/Linux 安装官方 CPU 源的 `2.14.1+cpu` |
| scikit-learn | 1.9.1 |
| 间接依赖 | `uv.lock` 中的全部解析版本与下载哈希 |
| 项目构建后端 | setuptools 80.9.0，独立于锁文件中的运行时 setuptools |
| 设备 / dtype | CPU / float32 |
| Torch intra-op / inter-op | 1 / 1 |
| OMP / MKL / OpenBLAS 线程数 | 1 / 1 / 1 |
| Torch 确定性算法 | 开启；随机种子由每次运行配置明确记录 |

主依赖不是可选 extras，所有人安装同一个项目环境。macOS 的 PyTorch 分发源由锁文件单独处理；当前本机验证是 Windows x86_64，其他系统须通过同一检查后再参与正式实验。统一软件不等于统一硬件或逐位一致的跨系统浮点运算。

## 首次建立环境

先用 `uv --version` 确认是 0.12.23；版本不符时按 [uv 官方安装说明](https://docs.astral.sh/uv/getting-started/installation/) 安装指定版本，不在项目运行中自行升级。

在仓库根目录执行：

```powershell
uv sync --locked
uv run --locked --exact python scripts/check_environment.py
uv run --locked --exact python scripts/smoke_train.py
uv run --locked --exact python scripts/validate_pipeline.py --prepare
uv run --locked --exact python scripts/check_repo.py
uv run --locked --exact python -m unittest discover -s tests -v
```

`uv sync` 会按 `.python-version` 下载所需解释器并创建 `.venv`；`--locked` 要求锁文件与配置一致，发现变化时停止；精确同步会清除不属于声明环境的额外包。[uv 锁定与同步说明](https://docs.astral.sh/uv/concepts/projects/sync/)

无需手动 activate。运行统一使用 `uv run --locked --exact ...`；不直接运行系统 Python，不用 `pip install`、`uv pip install` 临时加包，不使用 `--frozen` 忽略锁文件是否过期，也不使用 `--no-sync` 绕过同步。首次创建也可显式运行 `uv venv --python 3.11.17`，之后仍执行 `uv sync --locked`。

## 参数入口

- `.python-version` 和 `pyproject.toml`：Python 与主依赖精确版本、uv 版本和 CPU 包源。
- `uv.lock`：所有依赖的精确解析、平台分支和工件哈希，必须入 Git。
- `configs/environment/runtime.json`：全员共享的 CPU、线程数、dtype 和确定性设置。
- `configs/environment/smoke.json`：环境测试的数据种子、模型、SGD、batch size、训练步数与验收阈值。
- `configs/environment/federated_smoke.json`：真实 HAPT 联邦开发链路的短程场景、工作区、预算与恢复验收设置。
- `configs/benchmark/hapt_v1.json`：研究实验协议；时间预算 B 等尚待真实基线 profiling，不用环境 smoke 耗时代替标定。

未来训练 runner 在导入/初始化数值计算前应用线程环境变量，并调用 `flbench.environment.configure_cpu_runtime(root, seed)`。主训练运行只允许使用共享 runtime profile；smoke 的 240 步是集中式合成测试总步数，不替代协议中的每客户端 4 步。

## 环境测试验收

`smoke_train.py` 用独立生成的 600 条训练样本、180 条测试样本，运行 48→64→6 MLP、SGD、学习率 0.03、batch size 16、固定种子 20261020 和 240 步训练；第 120 步保存状态，然后比较连续训练与恢复训练的最终权重及预测。

通过条件：损失有限且降到初值的 40% 以下、合成测试 Macro-F1 至少 0.9、CPU 包正确、位于当前项目 `.venv`、恢复权重和预测完全相等。真实执行报告、checkpoint 与配置摘要保存在 `artifacts/environment-smoke/`，不进入研究排行榜。首轮验证摘要见 [Windows 验证报告](validation/environment-smoke-windows.json)。

完整开发链路另用真实 HAPT 验证，主运行仅 8 轮，覆盖 FedAvg/FedProx、四个场景、四个工作区、预算与恢复。具体命令和报告见 [短程端到端验收](pipeline-validation.md)，不会读取确认/最终测试成绩。

## 修改依赖

1. 在独立基础设施分支试验依赖调整，可用 `uv add` / `uv lock` 生成候选配置。
2. 完成环境检查、训练 smoke 和回归测试后，再锁定新的主依赖版本。
3. 一起更新 pin、pyproject、uv.lock、runtime profile 和说明；提交 PR 由团队统一升级。
4. 依赖锁文件参与协议指纹；正式实验依赖变更后，旧结果保留，受影响对照按新协议重跑。

日常实验不执行 `uv lock --upgrade`。CI 按完全相同的锁文件同步并运行检查与 smoke；当前本地验证不代表 GitHub CI 已运行。

## 本机 uv 版本链接异常的处理

如果 Windows 报 `Missing expected target directory for Python minor version link`，先检查实体解释器是否已经下载成功。本次实体解释器可运行，使用其完整路径创建 `.venv` 后，正常的 `uv sync --locked` / `uv run` 即可工作：

```powershell
$taskInterpreter = Join-Path $env:APPDATA 'uv\python\cpython-3.11.17-windows-x86_64-none\python.exe'
& $taskInterpreter --version
uv venv --python $taskInterpreter
uv sync --locked
```

仅在首次创建且确认实体解释器存在时使用此步骤，不删除全局 Python 目录或修改用户 PATH；仓库不写入任何成员的机器绝对路径。
