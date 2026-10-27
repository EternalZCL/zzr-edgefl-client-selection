# EdgeFL Client Selection

面向异构云边感知的联邦学习客户端选择课程研究项目。成员为 `zzr / zzw / ghj / xyk`，各自独立工作区；本分支是 **ghj 的完整研究与基础设施补齐成果**，不代表其他成员已开展实验。

共享实现已包含真实 HAPT 数据审计、完整基线、实测成本校准、全预算开发/确认/正式矩阵、等更新数诊断、不可变记录和检查点恢复。实际完成数量、冻结候选、结论和远端协作状态以 [ghj 交接](agents/ghj/HANDOFF.md)、[研究日志](agents/ghj/RESEARCH.md) 与生成的共享状态为准。

## 开始与复现

全员使用 uv **0.12.23**、CPython **3.11.17**、checkout 独立 `.venv`，不改变已提交依赖锁。首次 clone：

```powershell
uv sync --locked
uv run --locked --exact python scripts/check_environment.py
uv run --locked --exact python scripts/smoke_train.py
uv run --locked --exact python scripts/validate_pipeline.py --prepare
uv run --locked --exact python scripts/check_repo.py --require-ready
uv run --locked --exact python -m unittest discover -s tests -v
uv run --locked --exact python scripts/sync_leaderboard.py --check
```

正式矩阵的一条复现命令：

```powershell
uv run --locked --exact python scripts/research.py campaign configs/final/core-final-v2.json
```

已发布终态不覆盖；重复执行会跳过现有终态，未完成运行从原子检查点恢复。新机器使用冻结配置与原参考成本；重新实测成本意味着新协议。详细阶段顺序、单次运行与恢复见 [执行说明](docs/ghj-execution.md)。

## 科学协议

- 真实 UCI HAPT，30 位用户、6 类，训练/验证/测试原始采样区间零重叠；48维特征、48→64→6 MLP。
- 每轮6人，每人4步SGD，等客户端聚合；固定模拟预算下最后一个完整轮次的客户端平均 Macro-F1。
- 开发仅20人开放验证，确认另10人；算法冻结后才在30人独立测试片段上执行175行矩阵。
- Uniform、FedProx、SCAFFOLD option II、随机轮转、Fast/Random、Oort有限适配，以及ghj等待覆盖候选。Local-only、Centralized为曝光匹配参考。
- 预注册开发种子11/22/33，正式种子101..105；全部基线调参、候选、消融、负结果、修订与中断记录保留。
- 研究代码 commit、配置/成本/数据/协议哈希、逐轮日志与模型检查点可审计。smoke和partial不混入完整B主榜；确认/测试的j_dev永远为空。

完整固定条件、成本修订、Oort适配局限和统计边界见 [PROTOCOL](PROTOCOL.md)。工程通过不等于团队人工评审；Champion不会自动晋级。

## 导出报告

全部矩阵完成后，生成已核验工件的中文报告、原始CSV和JSON：

```powershell
uv run --locked --exact python scripts/report_research.py --output artifacts/report
```

绘图使用独立工具环境，避免修改实验依赖：

```powershell
uv tool run --from matplotlib==3.10.7 python scripts/plot_research.py artifacts/report
```

PDF导出脚本 `scripts/export_report_pdf.py` 使用独立的 reportlab 环境及中文 TrueType 字体；图表同时输出PNG/SVG/PDF。生成后的PDF需渲染检查，不能只以成功写文件作为排版验收。

## 协作与目录

个人策略/配置只改 `agents/ghj/`；本分支在bootstrap补齐共享核心，需团队审阅后集成。没有修改其他成员的策略与交接。共享派生文件由 `scripts/sync_leaderboard.py` 生成。

- [共同目标](shared/OBJECTIVE.md)、[全局状态](shared/GLOBAL_STATUS.md)、[开发榜](shared/LEADERBOARD.md)
- [贡献规范](CONTRIBUTING.md)、[协作](docs/collaboration.md)、[环境](docs/environment.md)、[记录](docs/experiments.md)
- [任务验收](docs/roadmap.md)、[原始规划](docs/project-plan.md)、[课程要求](docs/course-requirements.md)

原始规划保留为历史依据；本README与当前CLI说明可执行能力。仓库邀请、分支保护、外部上传及人工审阅需实际GitHub账号和权限，不把本地完成冒称远端已集成。
