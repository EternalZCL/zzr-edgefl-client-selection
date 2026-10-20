# 仓库架构

## 职责与依赖

```text
agents/<name>/policy.py   个人候选选择器
              ↓ 实现共同接口
benchmark/interfaces.py  允许暴露的客户端、预算与历史信息
              ↑ 未来由统一训练/仿真驱动调用
benchmark/               data → model/trainer → simulator → evaluator/accounting
baselines/               共享基线实现
configs/                 唯一配置入口
              ↓ 真实测量记录
artifacts/<run_id>/       本地日志、检查点与记录草稿（Git 忽略）
              ↓ 校验后发布
agents/<name>/runs/*.json 互不覆盖的小型终态摘要
              ↓ 本地派生，不访问网络
shared/                  索引、开发排行榜、状态
```

## 四个区间

- **共享核心**：`benchmark/`、`baselines/`、`flbench/`、共享配置和协议。bootstrap 可协作实现，搜索时冻结。
- **个人工作区**：`agents/zzr`、`agents/zzw`、`agents/ghj`、`agents/xyk`。保存各自策略、配置、研究日志、交接与摘要；所有人均可阅读并继承已发布版本。
- **派生视图**：排行榜、全局状态、实验索引。脚本从本地已检出的已发布摘要重建；并不自动拉取其他分支。
- **本地大文件**：数据、缓存、权重、逐轮日志。由外部存储或本机保存；摘要中的 artifact URI 与 SHA-256 指向持久存档。

## 模块当前能力

| 模块 | 当前内容 | 后续职责 |
| --- | --- | --- |
| `benchmark/interfaces.py` | 可运行的数据类型和选择器 Protocol | 维持共同接口，限制反馈信息 |
| `baselines/uniform.py` | 可复现随机选择器与状态恢复 | 作为最小接口参考；不等于 FedAvg 训练实现 |
| `benchmark/data.py` | 真实 HAPT 审计、隔离划分、48 维特征缓存与 train-only 归一化 | 后续数据协议变更需版本化 |
| `benchmark/model.py` / `trainer.py` | MLP、FedAvg/FedProx 本地 SGD、等客户端聚合 | 继续补齐强基线 |
| `benchmark/simulator.py` / `accounting.py` | 同步联邦闭环、消息序列化、预算停止、数值时钟、状态恢复 | 正式计费/预算仍需校准 |
| `benchmark/evaluator.py` | 固定六类 Macro-F1、仅开放 20 人开发验证集 | 确认/最终阶段 runner 待受控实现 |
| `flbench/` / `scripts/` | 可运行的仓库校验、摘要发布、派生视图工具 | 在此基础上逐步添加真实实验 CLI |
| `flbench/environment.py` / `configs/environment/` | 统一 CPU 配置、uv 环境校验、依赖记录和合成训练 smoke | 未来 runner 复用同一初始化函数 |

## 共享修改的影响

任何训练/数据/计费/评价逻辑变更先进入独立基础设施 PR。明确旧记录仍对应哪个指纹，保留历史记录；不要把新协议结果与旧协议混排。只改个人选择器时，不改变共享协议，但必须记录准确的实现 commit。

当前不提供 GPU/集群部署、权限沙箱、自动搜索、自动晋级或远程自动同步。真实联邦训练已能短程运行；正式方法对比和最终测试仍是后续阶段。
