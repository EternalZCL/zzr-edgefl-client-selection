# ghj 实验执行说明

所有命令在仓库根目录，先安装 uv 0.12.23，再 `uv sync --locked`。项目不改变依赖锁。数据准备：

```powershell
uv run --locked --exact python scripts/validate_pipeline.py --prepare
uv run --locked --exact python scripts/smoke_train.py
uv run --locked --exact python -m unittest discover -s tests -v
```

首次建立研究协议的顺序如下。所有初始代码和方法配置提交后才能 profile；profile 改变成本和协议，须通过检查并提交，再预注册开发矩阵。已冻结的交付版本禁止重做 initialize/profile；直接按保存的 manifest 复现。

```powershell
uv run --locked --exact python -m flbench.planning initialize
# 提交初始代码和预注册参数
uv run --locked --exact python -m flbench.planning profile
uv run --locked --exact python scripts/sync_leaderboard.py
uv run --locked --exact python scripts/check_repo.py --require-ready
# 提交校准后的冻结协议和全部研究代码
uv run --locked --exact python -m flbench.planning register-search
uv run --locked --exact python scripts/research.py campaign configs/final/dev-search-v1.json
uv run --locked --exact python -m flbench.planning select
uv run --locked --exact python scripts/research.py campaign configs/final/dev-conditions-v1.json
uv run --locked --exact python scripts/research.py campaign configs/final/confirmation-v1.json
uv run --locked --exact python -m flbench.planning freeze-final
uv run --locked --exact python scripts/research.py campaign configs/final/core-final-v1.json
```

开发搜索 81 次：21 组基线和 6 组候选，各 3 个种子；选中 7 个方法的另外 3 条件验证 63 次；确认 6 次；正式 175 次。另保留 36 次校准，不把它们混算正式结果。开发搜索的基线调参最多 8 组/方法，所有正负结果同等保留。

恢复执行同一个 campaign 命令会跳过已发布记录，未终态 run 从每 50 轮保存的 checkpoint 恢复。失败终态不会覆盖，应诊断后用新活动/记录并保留原失败。单次结果可运行：

```powershell
uv run --locked --exact python scripts/research.py run --config configs/baselines/presets/uniform.json --scenario natural_heterogeneous --seed 11 --run-id ghj-independent-reproduction-001
```

此命令是新的开发复现，会新增记录；不要将同配置重复种子误当独立证据，重复组不入排行榜。最终保留集只经冻结 campaign 运行，不能使用单 run 命令临时试参。

每个 `artifacts/ghj-*/artifacts.zip` 含实际配置/成本/代码 commit、summary、逐轮 JSONL 和完整 checkpoint，外部交付时必须一起携带工件或可取回副本。摘要中 SHA-256 可核验 zip。路径是仓库相对路径，换电脑可重新下载数据并按完全相同协议运行。参考硬件成本仍使用冻结值，重新实测成本是新协议。

`agents/ghj/SELECTION.json` 是开放验证决定的不可变候选快照。Champion 不自动晋级；团队需复核完整配对证据。最终测试后禁止根据测试结果再调参，新增方法需新的独立验证设计。
