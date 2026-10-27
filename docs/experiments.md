# 实验记录与结果发布

## 当前可做的事

仓库工具可以创建记录草稿、验证终态摘要、保留失败和重建派生索引。真实 HAPT/FedAvg/FedProx 已有短程验收入口 `scripts/validate_pipeline.py`，但正式 B、强基线和批量实验入口尚未齐备。空白值 `null` 表示尚未测量；工程 smoke 不写入排行榜记录。

## 记录生命周期

1. 写个人策略和配置，提交研究代码，保留准确 commit。
2. 创建草稿，草稿位于 Git 忽略的 `artifacts/<run_id>/record.json`：

```powershell
uv run --locked --exact python scripts/new_run.py --owner zzr --method coverage-v1 --config agents/zzr/configs/search.json --hypothesis H001
```

可用 `--parent-method` 记录继承对象。工具会生成唯一 ID，保存当前 commit、协议/成本指纹和精确配置哈希；真实数据未就绪时数据哈希仍为 `null`。新建草稿不代表已运行实验。

3. 未来的 runner 运行实验并补齐草稿字段。成功应填真实成绩、耗时、通信、轮数、实现/环境证据、存档 URI 与摘要；失败应填 `status=failed/timeout/invalid` 和原因。`status=planned/running` 不可发布。
4. 发布前将工件保存到可复取的位置，记录 artifact SHA-256。摘要可以写相对路径，但如果工件只在个人电脑，必须明确他人暂时无法复现，不能晋级。
5. 使用真实草稿路径发布：

```powershell
uv run --locked --exact python scripts/publish_run.py artifacts/<run_id>/record.json
uv run --locked --exact python scripts/sync_leaderboard.py
```

`<run_id>` 是说明占位符，执行时替换为第一步打印的真实 ID。发布采用独占创建，不覆盖已存在记录。发布本身不 commit、不 push、不晋级 Champion。纠错保留原摘要，新运行填写 `supersedes`；当前版本不自动注销被替代记录，有多条同种子完整结果时会阻止该组入榜，待审核后以新的方法/配置版本重新开展完整组。

## Schema 与等级

字段定义见 `schemas/run.schema.json`，运行时语义检查由 `flbench/records.py` 执行。成功的真实实验需要：commit、协议/数据/配置/成本哈希、budget、seed、stage/scope/fidelity、全部计费数值、环境信息和工件摘要。失败允许尚未产生的测量字段为空，但不能缺少失败原因。

创建草稿前自动验证当前 uv `.venv`、Python/uv 版本、CPU 构建和锁文件同步状态。环境字段自动保存实际解释器、依赖版本、锁文件与 runtime profile 的 SHA-256；依赖或环境不符时停止创建，避免实验之后才发现设置不一致。

- `stage`：`development / confirmation / test`。
- `evaluation_scope`：分别是 `search_validation / confirmation_validation / final_test`。
- `fidelity`：`smoke / partial / full`；低保真结果不冒充完整 B。
- `status`：发布只接受 `complete / failed / timeout / invalid`。

`mean_client_macro_f1` 保存当前评价阶段的真实成绩；`j_dev` 只允许保存开发验证分数，确认或测试记录中必须为空，不能回流为开发反馈。

新建草稿默认 `development + search_validation + smoke`。只有真实完成实验后据实修改。工具不执行训练，也不能代替检查日志真伪。

## 派生文件与开发主榜

`sync_leaderboard.py` 在写入任何派生文件前先验证所有个人摘要。遇到非法 JSON、错误成绩、重复 run ID、owner 与目录不一致等会报错，不跳过坏记录。

它生成：

- `shared/EXPERIMENT_INDEX.jsonl`：所有已发布终态摘要，含失败。
- `shared/LEADERBOARD.md`：仅当前冻结协议下，主场景、完整 B、完整开发种子集合的同一方法实现/配置组合。
- `shared/GLOBAL_STATUS.md`：当前工程就绪情况、各成员已发布记录数量与未解决条件。

同组出现某种子的多条成功结果时，不挑最高分，也不将种子当作独立重复追加。必须通过版本化配置区分新实验组。共享实现 commit 需要相同，因此补交摘要不影响运行代码 commit，改变代码则开始新组。

`--check` 只比较磁盘文件是否与应生成内容一致，不修改文件；CI 使用此模式。所有派生结果当前都是空榜，不含演示成绩。

## Champion

`CHAMPION_DEV.json` 当前为 `uninitialized`。晋级 PR 必须附不可变 commit、配置、所有 run ID、当前 Champion 引用、同协议配对差、失败边界和复现入口。集成者复核后保存历史引用到 `shared/champions/`，再修改 Champion 指针。

`CHAMPION_FINAL.json` 在搜索冻结、少量候选受限确认之后才产生。此版本未提供自动晋级/最终测试入口，避免脚手架绕过尚未确定的预注册规则。
## 当前ghj研究分支的可执行训练

原有new-run/publish-run命令仍可用于手工摘要；实际训练另有 `scripts/research.py run` 和 `campaign`。新runner在运行前检查代码/配置commit和当前协议，结束后通过同一不可变发布函数保存摘要，工件含exact configuration、costs、summary、rounds与checkpoint。它不会覆盖既有发布文件。

修订后的开发清单为 `configs/final/dev-search-v2.json`；旧v1开发有37次完成和一次中断invalid，均保留但不混入新协议。选定方法的其余条件、受限确认、最终175行分别由不同冻结清单驱动。确认/测试j_dev始终为null；100轮机制诊断标为partial。

`agents/ghj/SELECTION.json`仅是按开放验证规则锁定候选，不能替代人工Champion晋级。协议配置的phase字段随哈希冻结，实际活动进度以HANDOFF、COMPLETION和已发布矩阵记录为准，不能仅凭phase字段判断正式实验是否完成。
