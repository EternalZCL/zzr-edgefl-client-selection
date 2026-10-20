# 开发与贡献规范

## 贡献范围

四人目标一致，不按姓名固定分配方向。基础建设阶段任何人可承担共享模块；算法搜索阶段每人主要修改自己的工作区。共享训练核心、成本模型、数据划分和评价规则的修改单独提交 PR，说明会影响哪些已有结果。

## 提交与合并

1. 同步 `main`，阅读共享状态与个人交接；在自己的分支或临时基础建设分支开发。
2. 做一件范围明确的事；提交前检查 `git diff`、`git status` 和待提交文件列表。
3. 提交信息建议使用 `docs:`、`feat:`、`fix:`、`test:`、`infra:`，后面描述具体变化。
4. 发起 PR，说明问题、最终行为、验证结果、是否改变协议，以及实验记录与复现入口。
5. 共享核心和协议 PR 建议至少由另一位成员审阅。合并负责人检查 CI、冲突和派生文件。
6. 实验摘要 PR 在集成所有个人记录后，重新生成排行榜再合并，避免覆盖他人的记录。

不 force-push 共享 `main`，不把多位成员的活动进程放在同一工作树中，不把尚未推送的本地结果当作团队已知事实。完整操作见 [协作指南](docs/collaboration.md)。

## 运行记录

使用 `scripts/new_run.py` 创建本地草稿；实验结束后补全真实字段，再用 `scripts/publish_run.py` 发布终态摘要。所有状态、必填字段和命令见 [实验指南](docs/experiments.md)。失败记录同样保留。

研究代码必须先提交成不可变 commit，再运行要正式发布的实验；记录该 commit。运行之后发布摘要可产生后续 commit。这样不会出现“记录要求引用包含自身的提交”的循环。`config_hash` 是精确运行配置文件的 SHA-256；更改个人策略必须产生新的 commit 和新 run。

## 检查

```powershell
uv run --locked --exact python scripts/check_repo.py
uv run --locked --exact python -m unittest discover -s tests -v
uv run --locked --exact python scripts/sync_leaderboard.py --check
```

测试覆盖协作记录约束，以及特征、数据隔离、SGD/聚合、消息计费、预算停止和联邦状态恢复。CI 另执行真实 HAPT 的短程端到端验收；这不代表强基线比较、收敛和正式实验已完成。

## 依赖与数据

所有成员强制使用 uv 0.12.23 创建各自 checkout 的 `.venv`，CPython 固定为 3.11.17。执行 `uv sync --locked` 安装已通过训练测试的统一 CPU 环境，再用 `uv run --locked --exact` 执行命令。不要另建 conda/系统 Python 环境、直接 pip 安装、随意加 extras 或让运行命令改写锁文件。

版本入口为 `.python-version`、`pyproject.toml`、`uv.lock` 与 `configs/environment/runtime.json`。依赖调整必须在独立 PR 中更新锁文件、通过环境检查、训练 smoke 和回归测试，并由团队共同升级。`uv.lock` 提交 Git，`.venv` 不提交。完整步骤见 [环境规范](docs/environment.md)。

不新增项目许可证作为成员共识的替代；代码正式对外分发前，由仓库维护者决定许可证，并检查数据集和复用基线的授权条件。
