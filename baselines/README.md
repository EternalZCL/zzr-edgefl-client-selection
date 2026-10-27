# 基线

全部实现使用共享 HAPT、模型、训练曝光和计费规则：Uniform FedAvg-U、FedProx-U、SCAFFOLD option II、随机轮转、Fast/Random、Oort 有限适配。Local-only 与 Centralized 是等总训练 step 的解释性参考。

参数清单由 `flbench.planning initialize` 在首次校准前写入 `configs/baselines/presets/`；搜索时不重新初始化。完整设置、Oort 偏离作者实现的地方、控制变量公式和额外成本见根目录 PROTOCOL.md。

数学与恢复测试：`uv run --locked --exact python -m unittest discover -s tests -v`。
