# EdgeFL Client Selection

面向异构云边感知的联邦学习客户端选择课程研究项目。四位成员使用 `zzr / zzw / ghj / xyk` 独立工作区，共享评测规则、实验记录与可继承成果，不设固定研究分工。

**当前阶段：bootstrap。** 已有统一 uv 环境、真实 HAPT 数据审计、FedAvg-U/FedProx-U 短程联邦训练、计费、开发验证和完整恢复流程。研究时间预算尚未校准，SCAFFOLD/Oort 等强基线和正式实验仍待完成，排行榜与 Champion 保持为空。

## 从这里开始

1. 阅读 [协作流程](docs/collaboration.md)，确定自己的工作区和分支。
2. 阅读 [共同目标](shared/OBJECTIVE.md)、[当前状态](shared/GLOBAL_STATUS.md) 和 [评测协议](PROTOCOL.md)。
3. 人工开发遵循 [CONTRIBUTING.md](CONTRIBUTING.md)；AI 助手同时遵循 [AGENTS.md](AGENTS.md) 和个人工作区的 `AGENTS.md`。
4. 按 [首阶段任务清单](docs/roadmap.md) 完成基础建设，再开展算法搜索。

## 统一环境与本地检查

全员使用 **uv 0.12.23 + CPython 3.11.17 + 仓库自己的 `.venv`**。主依赖与间接依赖由已提交的 `uv.lock` 对齐；Windows/Linux 使用 CPU 版 PyTorch。首次 clone 或依赖变更后，在仓库根目录执行：

```powershell
uv sync --locked
uv run --locked --exact python scripts/check_environment.py
uv run --locked --exact python scripts/smoke_train.py
uv run --locked --exact python scripts/validate_pipeline.py --prepare
uv run --locked --exact python scripts/check_repo.py
uv run --locked --exact python -m unittest discover -s tests -v
uv run --locked --exact python scripts/sync_leaderboard.py --check
```

`uv sync --locked` 自动创建项目虚拟环境并按锁文件同步；运行统一使用 `uv run --locked --exact`，不使用系统 Python 或手工 pip 安装。详见 [环境规范](docs/environment.md)。

`smoke_train.py` 是合成数据环境检查；`validate_pipeline.py --prepare` 下载/审计真实 HAPT 并验证完整开发链路，主运行只跑 8 轮，另做短程场景、工作区和恢复检查。两种 smoke 的成绩均不进入项目排行榜。流程说明见 [真实数据短程验证](docs/pipeline-validation.md)。

## 目录用途

| 路径 | 用途 | 搜索阶段的修改方式 |
| --- | --- | --- |
| `benchmark/` | 已有真实 HAPT + FedAvg/FedProx 开发链路、消息计费和恢复 | 共享核心，变更须统一评审和版本化 |
| `baselines/` | 当前提供随机选择器；FedAvg/FedProx 优化实现在共享 trainer 中 | 其余强基线按同一协议补齐 |
| `configs/` | 评测、成本、基线与最终实验配置 | 校准后冻结；禁止候选私自改变 |
| `agents/<name>/` | 个人策略、配置、研究日志、交接与已发布摘要 | 每人主要在自己的目录内工作 |
| `shared/` | 共同目标、派生排行榜、假设索引与 Champion 引用 | 派生文件由脚本更新，其余经合并集成 |
| `artifacts/` | 本地日志、检查点、草稿记录和大文件 | Git 忽略；外部保存后记录位置 |
| `data/` | 原始数据、缓存与数据清单 | 原始数据和缓存不提交 Git |
| `flbench/`、`scripts/` | 可运行的协作工具 | 共享工具，经测试后集成 |
| `docs/` | 架构、实验、协作规范与原始项目材料 | 所有人可提出修订 |

完整说明见 [架构](docs/architecture.md) 与 [实验记录指南](docs/experiments.md)。

## Benchmark、Baseline 与成绩

- **Benchmark**：已可短程运行的开发流程，基于真实 HAPT 的 30 个逻辑客户端，每轮选择 6 个；正式固定 B 比较仍待校准。
- **Baseline**：随机 FedAvg-U、FedProx-U、SCAFFOLD、轮转、Fast/Random、Oort；另有本地训练与集中训练参考。实现状态见 [基线清单](baselines/README.md)。
- **主指标**：相同模拟时间预算下的客户端等权平均 Macro-F1。开发阶段只读开放验证集；最终测试在算法冻结后统一执行。
- **当前限制**：模拟预算 `B`、成本标定、真实数据清单和晋级阈值均为空，排行榜不得用占位数值填充。

## 四人协作

```text
main             已集成的共享代码、协议和已发布记录
agent/zzr        zzr 的独立研究分支
agent/zzw        zzw 的独立研究分支
agent/ghj        ghj 的独立研究分支
agent/xyk        xyk 的独立研究分支
```

每人先同步 `main` 与已发布成果，再读自己的 `HANDOFF.md`，提出假设、开展实验、记录正负结果、提交 PR。不同电脑使用独立 clone；同一电脑多工作区使用 Git worktree。未提交、未推送的本地文件不会自动共享。

`setup/collaboration-scaffold` 是本次本地搭建分支；初次上传待仓库创建者审阅确认。仓库不预设某个人担任长期集成者，由每次合并的负责人检查共享文件和记录。

## 原始依据

- [项目总体规划](docs/project-plan.md)
- [课程要求](docs/course-requirements.md)

原始规划保留为研究背景；当前可执行命令以 README 和 `--help` 为准。已提供准备数据与短程端到端验收命令，尚未实现原规划的完整批量搜索和最终评测 CLI。
