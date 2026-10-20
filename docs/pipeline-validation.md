# 真实 HAPT 短程端到端验收

## 验证范围

这套验收使用真实 HAPT 原始传感器数据，连接数据审计、特征缓存、客户端选择、消息下发、本地 SGD、模型更新上传、等客户端聚合、模拟时间/通信计费、开放验证集评测、检查点恢复与四人策略接口。

主运行只有 **8 个全局轮次**，包含 5 轮全覆盖预热和 3 轮策略选择；每轮 6/30 客户端，每个参与者训练 4 步。其余三种数据/系统场景各跑 6 轮，四个个人策略各跑 6 轮以确保越过预热、真正调用选择器；FedProx 也跑 6 轮。连续运行与第 4 轮暂停后恢复的结果进行精确比较。没有开启长期搜索或正式 175 次实验矩阵。

配置入口是 `configs/environment/federated_smoke.json`。模拟预算 10 秒只是此次工程验证的保护上限；研究预算 B 仍为 null。短程采集的参考计算/服务器耗时只存入验收报告与检查点，所有短程子运行共享同一快照，不会覆盖 `configs/system/cost_model.json`。

## 执行方法

```powershell
uv sync --locked
uv run --locked --exact python scripts/check_environment.py
uv run --locked --exact python scripts/validate_pipeline.py --prepare
```

`--prepare` 会下载约 75.9 MB 的 [UCI 官方 HAPT 数据](https://archive.ics.uci.edu/dataset/341/smartphone+based+recognition+of+human+activities+and+postural+transitions)，校验 ZIP、预处理并运行短程验收。已有匹配的原始 ZIP 时复用；无需网络重新审计可加 `--offline`。下载、数据和缓存不提交 Git。

只准备数据可运行 `uv run --locked --exact python scripts/prepare_data.py`；数据缓存已经存在时，直接运行 `uv run --locked --exact python scripts/validate_pipeline.py`。这些入口当前只支持 development，保留的确认/最终测试入口尚未开放。

## 已审计的数据协议

- 30 名用户，共 61 条采集记录；只保留六种基本动作，用户编号 1–30 直接作为客户端 ID。
- 每人最早的完整采集记录作训练；后续记录中每类动作的第一个完整片段作验证，其余片段作测试。未随机拆分相邻窗口。
- 标注起止值按 one-based inclusive 解释，并在两端各剔除 1 个采样点。实现保守使用 Python `[start, end-1)` 内部区间，规避两种常见索引解释的边界差异；这项约定写入 manifest。
- 各片段内部切 128 长、128 步长窗口，检查所有窗口的原始采样区间无交集。每用户的训练、验证、测试均有六类支持。
- 实际窗口数为：训练 2748、验证 1194、测试 1462；验证总数包括 30 人。训练用全部 30 人，搜索评测只读取固定 20 人的验证缓存。
- 48 维统计特征使用训练数据拟合全局 z-score；验证/测试不能参与拟合。各客户端的三个 split 分成独立 NPZ 文件，loader 不打开保留的验证/测试文件。
- 近 IID 诊断仅重分配训练数据：分层比例分配并保留每客户端样本总数与全局类别总量，验证/测试保持不变。

原始压缩包的首次实测 SHA-256 固定在 `benchmark/data.py`；这是本项目观测并锁定的摘要，不声称是作者另行发布的校验值。每个原始文件、缓存数组和数据协议都有摘要。重建结果与已审计的内容哈希不一致时停止，需审查并版本化，不能静默覆盖。

## 验收证据

运行输出保存在 `artifacts/federated-smoke/`：

- `report.json`：真实轮数、指标、通信、时间、数据/代码/环境指纹、场景与工作区结果。
- `rounds.jsonl`：主运行逐轮选择、累计模拟时间、字节、本地步数和训练损失。
- `continuous.pt`、`partial.pt`、`resumed.pt`：连续、暂停与恢复的完整状态，包含全局模型、策略、客户端采样 RNG、参与历史与全局 RNG。

验收检查连续/恢复权重、选择/时间/字节轨迹和客户端 RNG 完全一致；同时检查超小预算在任何本地更新前停止、保留评测阶段被拒绝、预热覆盖所有客户端、每条通信按实际序列化大小计费。正式共享实现的计算与通信额外开销仍需更完整 profiling，不由这次短程计时替代。

本机 Windows 的真实报告副本见 [验收报告](validation/federated-smoke-windows.json)。短程分数只用于确认数值有效与流程可运行，不证明收敛或方法优劣，**不发布为排行榜实验，不晋级 Champion**。

## 当前边界

FedAvg-U 和 FedProx-U 开发原型可运行；SCAFFOLD、Oort、轮转、Fast/Random、本地独立训练与集中训练参考尚未完成。正式成本、B、晋级阈值与完整正式矩阵没有冻结；确认/最终测试尚未启用。通过本验收意味着开发链路可用，不等于整项研究完成。
