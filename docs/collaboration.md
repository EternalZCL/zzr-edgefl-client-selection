# 四人协作流程

## 工作区和分支

| 成员标识 | 个人目录 | 长期分支 |
| --- | --- | --- |
| zzr | `agents/zzr/` | `agent/zzr` |
| zzw | `agents/zzw/` | `agent/zzw` |
| ghj | `agents/ghj/` | `agent/ghj` |
| xyk | `agents/xyk/` | `agent/xyk` |

没有固定题目分配。可做新策略、复现、消融或反驳；临时任务可以协商，不能将研究方向永久绑定姓名。

以下远程命令用于**初始架构经确认、集成到远端 main 之后**的正常协作。当前本地搭建阶段不执行 push。

## 每台电脑首次开始

```powershell
git clone https://github.com/EternalZCL/zzr-edgefl-client-selection.git
cd zzr-edgefl-client-selection
git fetch origin
git switch -c agent/zzr origin/main
```

示例使用 `zzr`，其他人替换为自己的标识。如果自己的远端分支已经存在，使用 `git switch --track origin/agent/zzr`；本地分支已存在则直接 `git switch agent/zzr`。不要重复创建或覆盖现有分支。

每份 clone / worktree 都执行 `uv sync --locked` 建立独立 `.venv`，再运行 `uv run --locked --exact python scripts/check_environment.py` 与训练 smoke。所有成员使用同一 Python pin、uv 版本和锁文件，详见 [环境规范](environment.md)。

同一电脑运行多个工作区时，在干净 clone 中为每位成员创建独立 worktree：

```powershell
git worktree add ../edgefl-zzr -b agent/zzr origin/main
```

已有分支时去掉 `-b`，使用 `git worktree add ../edgefl-zzr agent/zzr`。不要让两个活动进程共享同一个检出目录。

## 每次会话开始

1. `git status` 确认本地未提交工作；先保存自己的工作，再 `git fetch origin`。
2. 在个人分支 `git merge origin/main`，再 `uv sync --locked`；遇到共享核心或依赖冲突先读对应 PR 与协议变更。
3. 读 `shared/OBJECTIVE.md`、`GLOBAL_STATUS.md`、`LEADERBOARD.md`，个人 `HANDOFF.md`，以及当前 Champion 和相关研究记录。
4. 检查协议阶段、未解决问题和最近失败经验，写出本次假设和最小验证方案。

远端个人分支不等于 main 已集成成果。可只读查看他人已推送内容：

```powershell
git show origin/agent/zzw:agents/zzw/HANDOFF.md
git log --oneline origin/main..origin/agent/zzw
```

继承策略时复制或导入一个明确 commit 的版本，记录 `parent_method` 和来源 commit；不要自动导入别人持续变化的工作文件。

## 实验与交接

在 bootstrap 先共同建设并运行受控短程工程验收；数据、基线和协议未齐备/冻结前，不启动长期算法搜索。完整实验流程见 [experiments.md](experiments.md)。单次约 12 小时是每个 Agent 的会话预算，可并行、接续和多轮开展；不是现在必须启动的任务。

结束时更新个人 `HANDOFF.md` 和 `RESEARCH.md`，保存正在运行任务的恢复命令；提交代码、配置和终态摘要。按团队授权推送个人分支并发起 PR。集成者合并所有记录后重建派生视图：

```powershell
uv run --locked --exact python scripts/sync_leaderboard.py
uv run --locked --exact python scripts/check_repo.py
uv run --locked --exact python scripts/sync_leaderboard.py --check
```

同步脚本只读当前检出的个人摘要，不会自行 fetch、merge、push，也不能看到尚未集成的其他分支。

## 冲突处理

- 个人目录：归属者优先整理；继承成果写入自己的目录并保留来源。
- 实验摘要：run ID 不可覆盖；重复 ID 是错误，禁止用“保留较高分”方式处理。
- 派生文件：先合并原始摘要，再重新运行脚本，不手工拼接排行榜。
- 协议/Champion：串行评审集成；协议变化重跑相关对照，Champion 变化复核配对参照版本。
- 失败与超时：保留终态摘要；重跑产生新 ID 并写 `supersedes`，原记录不删除。

## GitHub 端设置（待维护者配置）

本地文件不能自动启用分支保护。初次 push 后，建议为 `main` 开启 PR 合并、CI 必须通过和至少一位审阅者；邀请三位协作者并按需要设置访问权限。仓库当前不宣称这些设置已生效。
