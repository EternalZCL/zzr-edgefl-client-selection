# 基线实现清单

| 方法 | 当前状态 |
| --- | --- |
| FedAvg-U + Uniform | `uniform.py` + `benchmark/trainer.py` / `simulator.py` 已接入真实数据开发链路 |
| FedProx-U + Uniform | 共享 trainer 实现近端项；可短程运行，正式调参与对比待做 |
| SCAFFOLD + Uniform | 待实现；控制变量计算与通信须计费 |
| FedAvg-U + Randomized Round-Robin | 待实现 |
| FedAvg-U + Fast/Random | 待实现 |
| FedAvg-U + Oort | 待实现；保留原方法核心机制，记录适配差异 |
| Local-only / Centralized | 待实现，作为解释性参考 |

配置索引为 `configs/baselines/catalog.json`。候选只修改选择器，其他训练规则固定。
当前只完成随机选择的 FedAvg/FedProx 开发原型。短程 smoke 证明工程链路可用，不构成收敛质量、成熟方法对比或算法提升的证据。
