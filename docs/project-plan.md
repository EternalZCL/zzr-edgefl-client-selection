# 面向异构云边感知的联邦学习客户端调度：课程研究项目总体设计

> **项目类型**：联邦学习（Federated Learning）× 云边协同 × AI Systems × 多 Agent 实验搜索\
> **最终选择**：方案 A——感知任务中的客户端调度（Client Selection / Scheduling）\
> **参与者**：`zzr`、`zzw`、`ghj`、`xyk`（四个独立 Agent 工作区，不设固定分工）\
> **文档版本**：v1.0（研究设计草案，2026-10-20）\
> **当前状态**：尚未构建数据与训练框架、运行 Baseline、测量真实 CPU 时间；全部性能假设和耗时估算均待实测校准。

---

## 0. 项目总览：先明确最终要做什么

### 项目名称

- **中文**：异构云边协同感知中的客户端选择：时间预算、参与覆盖与模型质量的权衡
- **英文**：*Client Selection for Heterogeneous Cloud–Edge Sensing: Trade-offs among Time Budget, Participation Coverage, and Model Quality*

### 一句话目标

在真实手机传感器数据和模拟异构设备上，研究**固定模拟训练时间预算下，速度偏好、客户端参与覆盖和全局模型质量之间的关系**；通过可解释的轻量选择策略，争取优于成熟 Baseline 的性能—效率权衡，并找到改进的有效条件与失效边界。

### 最重要的设计决定

1. **只选一个主矛盾**：客户端选择的训练吞吐与数据覆盖权衡，而不是把个性化、压缩、可变本地训练、掉线和网络优化全部叠加。
2. **唯一共同优化目标**：固定模拟系统时间预算 `B` 下的**客户端平均 Macro-F1**；其他指标解释机制或充当预注册约束，不临时凑加权分数。
3. **先 Benchmark，后算法**：先完成固定数据拆分、FedAvg/FedProx/SCAFFOLD/Oort 等基线、成本模型、完整性测试，再允许 Agent 大规模搜索。
4. **四个工作区并行**：`agents/zzr`、`agents/zzw`、`agents/ghj`、`agents/xyk` 独立修改候选算法、保存记录；读取统一排行榜和他人的成果。
5. **共享 Champion**：每个 Agent 都可继承任何人的已验证方法，以当前最强开发候选为共同参照；晋级必须通过同一评测协议。
6. **12 小时是每次 Agent 自主会话预算，不是四个人合计 12 小时**：四人可并行、交错或多轮接续；完整正式测试在搜索结束后统一开展。
7. **允许负结果**：如果 Oort/轮转已经足够好，结论可聚焦适用边界和成本权衡，不得编造 Novelty 或通过改造测试集制造收益。

### 默认配置快照

| 维度 | 默认方案 |
|---|---|
| 场景 | 手机/可穿戴传感器协同活动识别；每名受试者是一个逻辑边缘客户端 |
| 数据 | UCI HAPT 原始传感器记录；保留六个基本动作 |
| 客户端 | 30 个；全员在线；同步 FedAvg 风格训练 |
| 轮次选择 | 每轮 6 个客户端 |
| 模型 | 48→64→6 小型 MLP（3,526 参数，float32） |
| 本地训练 | SGD，学习率初始 0.03，batch size 16，每次参与固定 4 个 step |
| 系统异构 | 计算耗时倍率 `{1, 4, 16}`，各 10 人；匹配总额定计算能力的同构对照 |
| 主要目标 | 固定模拟时间 `B` 下的每客户端 Macro-F1 平均值 |
| 开发评测 | 20 个搜索验证客户端与公共开发随机种子 |
| 受限确认 | 10 个确认验证客户端；不得反复参与日常搜索 |
| 正式测试 | 冻结算法后评测全部 30 个客户端的独立测试窗口 |
| 主比较 | FedAvg-U、FedProx-U、SCAFFOLD、轮转、Fast/Random、Oort、候选方法 |
| 核心正式矩阵 | 175 次完整运行；可选增强至 235 次 |

---

## 1. 课程要求与研究方向选择

### 1.1 与官方课程选题的对应关系

**官方中文选题**：面向云边协同场景的分布式人工智能感知与决策关键技术研究\
**官方英文选题**：*Research on Key Technologies for Distributed Artificial Intelligence Perception and Decision-Making in Cloud–Edge Collaborative Scenarios*

官方给出的三类方向为：

1. 分布式人工智能与多智能体协同决策。
2. **联邦学习与分布式协同模型训练技术**（本项目选择）。
3. 云边协同推理与动态任务调度。

本项目在“云端服务器—边缘客户端—终端传感器”逻辑架构上，模拟**模型下发—本地训练—更新上传—全局聚合**的联邦训练流程。研究内容属于第（2）项，并以客户端选择作为资源受限的系统协同优化问题。单机模拟即可满足课程研究原型，不要求实际设备集群。

**官方评价维度与本项目映射**：感知准确率→Accuracy/Macro-F1；效率→固定系统时间达到的质量、收敛曲线；资源→通信字节、客户端计算与同步等待；可靠性→异构强度、重复种子、失败情形。任务完成率/推理实时性不是本项目主指标。

### 1.2 曾考虑的三个候选方向

| 方向 | 核心科学/系统问题 | 合适数据 | 现有方法 | CPU 与实现成本 | 结论 |
|---|---|---|---|---|---|
| **A. 感知任务中的客户端调度** | 快客户端带来的吞吐收益是否被参与覆盖不足抵消？ | HAPT：真实手机传感器、自然用户划分 | FedAvg、FedProx、SCAFFOLD、Oort、轮转 | **低—中**；小 MLP、选择器接口清晰 | **最终选定** |
| B. 用电预测中的个性化 FL | 异质用户应该共享多少参数、保留多少本地适应？ | ElectricityLoadDiagrams：真实客户时间序列 | FedAvg、Local-only、FedAvg 微调、Ditto | 中等；时间序列拆分和个性化评价更复杂 | 不作为主线 |
| C. 设备故障任务中的本地工作量分配 | 算力差异造成的不同本地步数如何影响全局目标？ | AI4I 2020（合成预测维护数据）或合成优化问题 | FedAvg、FedProx、FedNova | 低—中；但已有方法直接覆盖核心机制 | 不作为主线 |

**选择 A 的原因**：数据真实、工作量可控、Baseline 成熟、算法搜索只需改动“本轮选谁”，并且可以通过同时间／同轮数／同更新数的对照解释收益。相比 B 减少评价与建模的多重自由度；相比 C 更符合“低开销长期 Agent 搜索”的目标。

**明确不做**：本阶段不联合优化个性化模型、压缩量化、知识蒸馏、异步联邦、客户端掉线处理、训练步数分配和聚合权重学习。后续若拓展，必须声明为新实验阶段并补相应 Baseline（例如可变本地步数需 FedNova）。

---

## 2. 完整科研叙事

### 2.1 Motivation：训练速度与数据代表性之间存在潜在矛盾

云边感知设备具有不同的计算速度。同步训练时，某轮耗时往往受被选中客户端中的最慢者影响；因此偏向快客户端可能在固定时间内完成更多全局更新。

但各用户传感器数据存在不同程度的分布偏移。如果长期选择有限的一组快客户端，全局模型持续接触的数据可能偏离原来希望服务的全部客户端群体。**训练更新更多，不必然等价于目标群体模型更好。**

这只是合理的研究动机，不能预先断言在 HAPT 上一定会出现显著损害。如果快客户端已经充分代表总体，速度优先可能完全占优。

### 2.2 Existing Gap：不夸大研究空白

已知研究事实：

- **FedAvg**：经典联邦平均训练框架。
- **FedProx**：对统计/系统异构中的本地优化引入近端约束。
- **SCAFFOLD**：以控制变量缓解客户端漂移（Client Drift）。
- **Oort（OSDI 2021）**：联合数据效用与系统效用开展参与者选择，直接优化 time-to-accuracy。
- **Power-of-Choice（AISTATS 2022）**：分析有偏选择的优化收益与选择偏差。
- **FedAU（ICLR 2024）**、**HiCS-FL（NeurIPS 2024）**和**相关参与去偏工作（ICLR 2025）**：进一步研究非均匀参与、历史与异构性。

所以**不能**声称“过去的联邦学习从未考虑速度和数据覆盖”。本项目希望补齐的是一个**明确、低成本、可复现设置下的证据图谱**：在真实自然客户端划分下，客户端速度偏好什么时候值得采用、什么时候需要覆盖约束、简单规则是否已经足够、成熟选择器是否仍是更好的选择。

### 2.3 Research Question（核心研究问题）

> **在固定模拟系统训练时间预算下，利用历史参与信息约束速度偏好的客户端选择，能否提升目标客户端群体上的全局模型平均预测质量？这项收益取决于哪些统计异构和系统异构条件？**

主要自变量：**客户端选择策略**。\
主要因变量：**固定模拟时间 `B` 下的客户端平均 Macro-F1**。\
辅助机制量：客户端参与分布、历史等待时间、更新量、训练步数、通信字节、尾部客户端表现。

### 2.4 文献支持的观察 vs. 项目待检验假设

| 表述 | 状态 |
|---|---|
| 数据 Non-IID 可能导致本地更新漂移 | 已有经典研究支持 |
| 客户端选择会影响训练速度与优化结果 | 已有 Oort / Power-of-Choice 等研究支持 |
| 本项目 HAPT 自然划分下，速度优先会损害全体用户平均分 | **H1：待实验验证** |
| 简单参与覆盖保护可以以较小时间代价改善模型质量 | **H2：待实验验证** |
| 覆盖保护收益取决于数据异构与速度—数据关联程度，在近 IID 场景中可能减弱 | **H3：待实验验证** |
| 新候选方法可以击败 Oort | **待验证，不能预先承诺** |

### 2.5 Core Insight（机制直觉）

考虑两个同等重要的客户端：

\[
F_1(w)=\tfrac12(w-1)^2,\qquad F_2(w)=\tfrac12(w+1)^2.
\]

等权全局目标 \((F_1+F_2)/2\) 的最优点为 \(w=0\)。如果简单 SGD 长期以概率 90% 采样客户端 1、10% 采样客户端 2，期望随机梯度对应的目标则为 \(0.9F_1+0.1F_2\)，最优点为 \(w=0.8\)。

这只解释“偏向部分客户端可能改变优化方向”的机制，**不是 HAPT 的实验结论**；非凸多步本地训练和基于历史反馈的动态选择需要实证确认。

### 2.6 Method Principle（候选机制原则）

优先搜索**轻量、可解释、线上信息可用的客户端选择器**，其余训练流水线固定。

基础候选：每轮为长期未参与的客户端保留少量参与名额，其余名额根据已有成熟选择器的历史效用与成本选择。

\[
S_r=S_r^{\mathrm{coverage}}\cup S_r^{\mathrm{utility}},\qquad |S_r|=6.
\]

可搜索三个小空间：

| 候选族 | 初始范围 | 希望验证的机制 |
|---|---|---|
| 固定覆盖配额 | 每轮额外 1 或 2 个覆盖名额 | 少量覆盖能否恢复有价值数据，而不过多牺牲速度 |
| 等待阈值触发 | 超过 `0.05B / 0.1B / 0.2B` 等待时触发 | 避免无必要的持续覆盖成本 |
| 有界历史参与奖励 | 少量预注册离散奖励强度 | 平滑修正是否优于硬配额 |

所有方法必须提供可反驳的假设，禁止把已有方法简单改名宣称原创。

### 2.7 Key Experiments（机制验证）

1. **速度优先 vs 随机选择**：同时间预算得到什么质量；相同已执行更新数下又如何？
2. **覆盖规则 vs 随机探索**：是否是等待历史本身有价值，而非单纯加了随机性？
3. **近 IID vs 自然 Non-IID**：覆盖收益是否与统计异构相对应？
4. **设备速度分配置换**：效果是否依赖某些用户恰好被设为慢客户端？
5. **候选 vs Oort 与轮转**：若成熟方法已达到同样效果，要如实说明额外复杂度是否值得。

---

## 3. 数据与云—边—端模拟

### 3.1 数据集：HAPT 原始记录

选择 **UCI Smartphone-Based Recognition of Human Activities and Postural Transitions（HAPT）**。采用原始三轴加速度、三轴陀螺仪和动作标注，只保留六个基本动作：Walking、Walking Upstairs、Walking Downstairs、Sitting、Standing、Laying。

- 数据入口：<https://archive.ics.uci.edu/dataset/341/smartphone+based+recognition+of+human+activities+and+postural+transitions>
- 每名受试者对应一个逻辑客户端：预期 30 个。
- HAPT 与经典 UCI HAR 存在数据来源关系；**不得**把它们作为两个独立数据集来宣称跨数据集泛化。

### 3.2 数据划分：先划记录，再切窗口

**严格禁止**：把已经切好的、可能 50% 重叠的窗口逐条随机分到 train / validation / test。

默认拟采用：

1. 按完整实验记录／完整动作片段划分，同一原始采样点不得进入两个集合。
2. 每名受试者最早一次完整实验记录用于训练。
3. 后续记录中，每个基本动作的第一个完整片段用于验证，其余完整片段用于测试。
4. 对每个集合内部的动作片段单独切窗：`window_length=128`、`stride=128`（无重叠），不得跨片段拼接。
5. 额外检查片段边界的采样交集和需要隔离的缓冲区。
6. 窗口统计特征、标准化等只使用许可集合；全局归一化参数仅从训练数据统计。

**这是待数据文件审计后冻结的协议**。必须先验证 HAPT 实际实验记录是否完整满足上述条件、各受试者六类是否足够、每人训练/验证/测试有效窗口数是否足以计算宏平均；如果不能满足，必须在算法搜索开始前统一修订并版本化，不能搜索后删除困难受试者。

基于原采集时长估计、非实际清点的数据量级：每人 Train 约 64、Validation 约 28、Test 约 36 个窗口；全体约 1,920 / 840 / 1,080。最终一律以 `data/manifests/` 生成的真实数量为准。

### 3.3 开发、确认和最终测试三道边界

- **搜索验证集**：用固定种子 `20261017` 将 30 个客户端的验证部分按受试者分为 20 人，日常 Agent 只能用这 20 人的验证分数作为排名依据。
- **确认验证集**：另外 10 人的验证部分只在全局候选锁定后、以有限次数检查；不作为每个 Agent 的无限反馈接口。
- **最终测试集**：全部 30 个客户端的独立 Test 窗口，只在算法和正式对照全部冻结后统一访问。
- **训练参与者**：30 人均可参与 Train；验证集的 20/10 仅指评价时开放哪部分客户端标签，不是训练客户端划分。

最终问题是**已参与客户端在留出采集记录上的测试质量**，不是“从未见过的用户”的泛化。由于同一用户的验证/测试片段样本较少，报告每人支持量，必要时将高方差作为局限性；Macro-F1 的六类标签、缺失类别处理、`zero_division` 必须固定。

### 3.4 构造统计异构

| 条件 | 构造 | 用途 |
|---|---|---|
| Natural Non-IID（主条件） | 保留每个受试者自己的训练数据 | 真实客户端分布差异 |
| Near-IID（诊断） | 仅对训练池进行类别尽量均衡的重分配，保持总数据与客户端训练量；验证、测试不变 | 近 IID 对照，不以人为数据替换最终测试 |
| 额外标签偏斜（可选） | 只重分配训练数据，固定 Dirichlet \(\alpha=0.3\) 并报告分配实现 | 压力测试，不可据此选择有利偏置 |

自然数据未必表现为极端的标签缺失；不能预先假设“慢客户端拥有独有动作类别”。

### 3.5 云—边—端架构

```text
       云端协调服务器 (Cloud Server)
       ├── 全局模型 w
       ├── 客户端选择器 π
       ├── 全局聚合与历史账本
       ├── 模拟时间、通信计费
       └── 评测 / 实验记录
                   │ 模型下载、更新上传
         ┌─────────┼─────────┐
         ▼         ▼         ▼
      边客户端1  边客户端2  ... 边客户端30
         │         │                │
         ▼         ▼                ▼
       各自本地手机传感器训练窗口（数据不上传）
```

采用**单进程顺序执行逻辑客户端**，模拟多设备并行的系统时钟；主要实验同步、全员在线、无掉线、无异步更新。

这个原型提供联邦数据访问边界，但**不提供**差分隐私、安全聚合或真实公网部署保证。

---

## 4. 模型、优化与系统成本的默认协议

### 4.1 特征与轻量模型

对六条传感器通道各提取八个统计量：均值、标准差、最小值、最大值、中位数、四分位距、相邻采样差分绝对值均值、均方根（RMS），共 **48 维**。

模型：

```text
Input(48) → Linear(48,64) → ReLU → Linear(64,6)
```

参数量：\(48\times64+64+64\times6+6=3526\)；float32 权重载荷 **14,104 bytes**。

训练默认值：

| 项目 | 值 |
|---|---|
| Local optimizer | SGD；默认无 momentum、无 weight decay |
| 起始学习率 | 0.03（在冻结的调参预算内调节） |
| Mini-batch | 16 |
| 每次参与的本地训练 | 固定 4 gradient steps |
| 每轮客户端数 | 6 / 30 |
| 数据载入 | 一次性预计算特征；客户端训练张量缓存；`DataLoader workers=0` |
| CPU 设置 | 单次训练默认 `torch.set_num_threads(1)` |
| 初始化 | 同一条件、种子下使用相同模型初始化 |

本地步数固定是为了把主要自由度限制在选择策略。若后续开放可变本地步数，则当前所有选择器结果不能直接比较，需要新阶段的控制实验。

### 4.2 共享训练目标

按每个客户端等权定义目标：

\[
F(w)=\frac1N\sum_{i=1}^{N}\frac1{n_i}\sum_{z\in D_i}\ell(w;z).
\]

主线相应采用等客户端权重聚合，命名为 `FedAvg-U`、`FedProx-U`，以免与经典按客户端数据量加权的 FedAvg 混淆。正式矩阵另保留经典样本量加权 FedAvg 对照。

**注意**：最小化交叉熵是训练目标，不等于严格最大化 Macro-F1。Macro-F1 是冻结的外部评价指标。

### 4.3 系统计算异构

三个计算**耗时倍率**（不是算力倍率）：

\[
s_i\in\{1,4,16\},\quad\text{每档各 10 人}.
\]

主设置中速度档位独立随机映射到受试者，种子单独记录。为了让同构对照和异构组有相同总额定计算能力，同构耗时倍率取：

\[
s_{\text{hom}}=\frac{3}{1+1/4+1/16}=\frac{16}{7}.
\]

这样两组的 \(\sum_i1/s_i\) 相同，避免只因为总资源不同而误判异构性作用。

可选敏感性分析同时测试“训练数据差异较大的用户更慢”和“相反映射”，必须在搜索前按训练统计预注册两种映射，不能只展示有利的一种。

### 4.4 网络与模拟时钟

网络默认：客户端下行 50 Mbps、上行 10 Mbps、固定 RTT 10 ms、客户端独立链路、服务器链路足以并发传输；主实验不模拟重传掉线。这些是**仿真设定，不是 HAPT 测量到的网络数据**。

令模型/策略在参考硬件上的每步训练成本为 \(c_a\)，第 \(r\) 轮某客户端的训练成本：

\[
t^{\text{train}}_{i,r}=4c_a s_i.
\]

同步轮次模拟时长：

\[
\Delta t_r=t_{\mathrm{server},r}+\max_{i\in S_r}\big(t^{\mathrm{down}}_{i,r}+t^{\mathrm{train}}_{i,r}+t^{\mathrm{up}}_{i,r}\big).
\]

服务器选择器额外计算、聚合、控制变量或探测通信计入账本。仅做**数值时钟推进**，不调用 `sleep`。

必须分别保存：

- **Simulated system time（模拟时间）**：主要优化约束。
- **Actual experiment wall-clock（笔记本实际运行时间）**：证明实验 CPU 可负担，不参与模拟排行榜排序。
- **Client compute steps、参与率、等待、上下行 bytes**。

### 4.5 通信计量

一次完整模型的 float32 权重载荷约为 `14,104 bytes`。假设 200 轮，每轮 6 人，每人模型下发与等规模更新上传各一次，基本逻辑载荷：

\[
200\times6\times2\times14104=33,849,600\text{ bytes}\approx33.85\text{ MB}.
\]

这是**示例估算**，还未包含初始化、选择器信息、消息元数据、序列化开销等。真实计费以实际序列化的应用层消息大小为准，上行与下行分别记录。SCAFFOLD 控制变量以及额外状态传输不能免费。

### 4.6 时间预算 `B` 的冻结

先运行 Uniform FedAvg 的少量校准，考察参考轮数 `{100,200,400}` 的模型质量与 CPU 成本；初始建议把“异构条件下 Uniform FedAvg 约 200 轮累计模拟时间”作为 `B` 的候选基准。

**必须在候选算法搜索前固定**：

- 绝对模拟预算 `B`；
- 主要评价点 `B/4, B/2, 3B/4, B`；
- 是否以最后一个**预算内已完成轮次**作为结果；
- 预算内额外传输和服务器计算的计费方法。

在模型达到 `B` 前，不能先执行超预算更新再将其计为预算内结果。

---

## 5. Baseline 与科学公平性

### 5.1 必须认真考虑的 Baseline

| 名称 | 定位 | 主要比较意义 |
|---|---|---|
| Local-only | 每客户端单独训练、各自测试 | 协同训练是否真正有收益 |
| Centralized | 集中训练参考 | 数据集中时的能力参考；**不是同隐私约束的公平 FL 竞争者，也不是严格数学上界** |
| **FedAvg-U + Uniform** | 核心初始基线 | 随机均匀参与的联邦训练 |
| **FedProx-U + Uniform** | 近端优化基线 | 是否仅靠抑制本地偏移就改善质量 |
| **SCAFFOLD + Uniform** | 强优化基线 | 正确控制变量实现，额外通信必须计费 |
| **FedAvg-U + Randomized Round-Robin** | 强简化覆盖基线 | 参与均衡本身是否已足够 |
| **FedAvg-U + Fast/Random 混合** | 速度偏好基线 | 速度收益和探索比例如何权衡 |
| **FedAvg-U + Oort selector** | 最重要的成熟调度基线 | 不应只与弱随机选择比较 |
| **FedAvg-U + Candidate** | Agent 搜索结果 | 只替换客户端选择器，保持其余设置固定 |

Oort 应尽量适配作者逻辑（探索、历史效用、系统成本、pacer 等），不可只把 `loss/time` 起个 Oort 名字。根据等客户端目标，可以预先比较原始效用和目标一致的归一化效用版本，验证选择更强者，保留适配细节。

### 5.2 Baseline 初始调参范围

| 参数 | 起始范围 |
|---|---|
| SGD 学习率 | `{0.01, 0.03, 0.1, 0.3}` |
| FedProx 正则系数 `mu` | `{0, 0.001, 0.01, 0.1, 1}` |
| SCAFFOLD 服务器学习率 | `{0.5,1}` |
| Fast/Random 探索比例 | `{0,0.2,0.5,1}` |
| Oort 探索比例 | `{0.1,0.3}` |
| 小规模 Oort pacer 窗口 | `{5,10}` 轮（说明相对原实现的适配） |
| 候选固定覆盖名额 | `{1,2}` |
| 候选等待阈值 | `{0.05B,0.1B,0.2B}` |

每条可调 Baseline 最多预先安排约 8 组配置的同级筛选，不必笛卡尔积穷举；完整记录调参预算。4 个 Agent 合计的研发搜索成本也必须披露，不能宣称所有方法研发成本相同。

### 5.3 公共预热与目标一致性

所有联邦方法最初执行**5 轮轮转预热**：每轮 6 人、5 轮覆盖全部 30 人。这样历史效用方法具备基础信息；全部预热训练、时间、通信成本计入预算。每个算法仍保留自己应有的优化器状态。

Centralized / Local-only 是解释性参考。若对齐 200 轮 × 6 客户端 × 4 step，则联邦的总本地 step 约 4,800；可给集中训练 4,800 step、本地各 160 step 的等曝光参考，明确其系统资源约束不同。

### 5.4 公平性红线

- 同一实验条件使用**同一模型结构和同一初始化规则**。
- 固定数据 manifest、客户端数量、参与上限、物理/模拟成本、随机种子及核心本地训练。
- 将初始化 RNG、客户端数据采样 RNG、系统速度 RNG、选择器 RNG 拆分，避免策略改变调用顺序导致“换了另一个实验”。
- 选择器只能用**当前在线可获得且已付费的训练历史统计**；未选客户端当前训练损失与验证集 Macro-F1 不能免费查询。
- 区分**同模拟时间**、**同轮数/同更新数**、**同字节**三种对照；主排行榜仅固定模拟时间，其他作为机制分析。
- 超时、训练异常、失败尝试全部保留；不能只留成功的一半种子。
- 数据和参数选择只能依据规定的验证集；最终测试集不得反复用于 Agent 搜索。
- 任何正式协议修改必须升级版本、重新运行受影响基线；不同协议版本不进入同一排行榜。

---

## 6. 唯一共同优化目标、评价与结果设计

### 6.1 共同目标函数（四个 Agent 都优化它）

设 \(\pi\) 为客户端选择策略、\(w_{\pi,s}(B)\) 为随机种子 \(s\) 下预算 `B` 结束时的全局模型，\(V\) 为当前阶段允许的验证客户端集合：

\[
\boxed{J(\pi)=\frac{1}{|\mathcal S|}\sum_{s\in\mathcal S}\frac1{|V|}\sum_{i\in V}\operatorname{MacroF1}_{i}(w_{\pi,s}(B))}
\]

**搜索排行榜**：`V=20` 个搜索验证客户端，种子取预注册开发种子；`J` 越高越好。\
**受限确认**：另外 10 个确认验证客户端及其锁定种子用于最终候选筛选，不做持续在线反馈。\
**正式报告**：冻结后的 `w(B)` 在全部 30 个客户端的独立测试窗口上评价，报告每人得分与客户端平均。

若不同方法在主指标差异低于可辨认的波动水平，按近似持平处理，优先保留更简单的方法，不随意创造加权总分。

### 6.2 辅助指标

| 类别 | 指标 | 用途 |
|---|---|---|
| 质量 | Accuracy、pooled Macro-F1、每客户端 Macro-F1 | 解释平均指标 |
| 公平性 | 最差 20% 客户端（6 人）平均分、分数分布、每人测试支持量 | 防止平均值掩盖尾部 |
| 效率 | 模拟时间—质量曲线、达到阈值所需时间、同轮数质量 | 分离训练吞吐与更新质量 |
| 系统 | 上行 bytes、下行 bytes、额外控制消息、等待时长 | 评估代价 |
| 计算 | 实际 Wall-clock、总训练 steps、峰值内存 | CPU 可复现性 |
| 选择行为 | 参与次数、最长连续缺席模拟时长、累计聚合权重 | 验证覆盖机制 |
| 稳健性 | 多种子配对差、近 IID / Non-IID、速度映射 | 检查是否靠偶然条件胜出 |

### 6.3 核心正式实验矩阵

| 条件 | 数据 | 系统 | 研究作用 |
|---|---|---|---|
| C1 | 近 IID | 同构（总额定计算能力匹配） | 基础对照 |
| C2 | 近 IID | 异构 | 独立考察速度差异 |
| C3 | Natural Non-IID | 同构 | 独立考察数据差异 |
| **C4** | **Natural Non-IID** | **异构** | **主研究条件** |

预注册 5 个正式种子，建议 `101,102,103,104,105`（数据划分种子、速度种子、模型种子可分别固定并记录）。

| 正式项目 | 运行数 |
|---|---:|
| 7 条联邦配置 × 4 条件 × 5 种子 | 140 |
| Local-only 与 Centralized × 2 数据条件 × 5 种子 | 20 |
| 2 项关键候选消融 × C4 × 5 种子 | 10 |
| 经典样本量加权 FedAvg × C4 × 5 种子 | 5 |
| **核心合计** | **175** |

其中 7 条联邦配置为：Uniform FedAvg-U、FedProx-U、SCAFFOLD、轮转、Fast/Random、Oort、冻结后的一个最佳 Candidate。**不能把开发阶段几十个实验也算成这个正式矩阵。**

### 6.4 关键消融

1. **去掉等待历史信息**：将覆盖名额改为同速度档内的随机名额，尽可能保持成本分布。
2. **去掉速度效用偏好**：测试覆盖机制本身是否是主要来源。
3. **去掉覆盖模块**：对应强 Oort / 速度效用基线，可复用相同配置结果，不必重复无意义运行。

### 6.5 可选增强实验（仅在实测吞吐允许时）

- 速度与训练数据异质性相关、反向相关两个映射：`3方法 × 2条件 × 5种子=30`。
- 额外标签偏斜：`3方法 × 5种子=15`。
- 另一套设备速度倍率：`3方法 × 5种子=15`。

合计可再加 60 次，达到 **235 次**。不能通过只选有利映射提升排名。

### 6.6 结果图表与统计

报告建议包含六类主图：

1. 四条件下的 **Macro-F1—模拟时间** 曲线。
2. 主条件候选方法与最强基线的逐种子**配对差值**。
3. 客户端参与次数、等待历史与客户端性能变化。
4. **同模拟时间 vs 同训练更新数** 的对照。
5. 覆盖配额/等待阈值的消融。
6. 数据异构、设备速度映射与其他成本假设的敏感性。

至少报告 5 个预注册重复、均值、标准差和配对差值。**5 个种子不保证统计显著性**：精确双侧符号翻转检验在 5 个配对样本下最小 p 值为 0.0625；若需显著性结论，需预先增加重复数。动作窗口属于相关样本，不能把每个窗口当作独立受试者来人为缩窄置信区间。

---

## 7. 四人并行 Agent 搜索：总体架构

### 7.1 四个独立工作区

工作区名称**固定**为：`zzr`、`zzw`、`ghj`、`xyk`。

```text
federated-learning-research/
├── README.md
├── PROTOCOL.md                  # 冻结的正式评测协议
├── pyproject.toml / requirements.txt
│
├── benchmark/                   # 固定训练、模拟、评测核心
│   ├── data.py
│   ├── model.py
│   ├── trainer.py
│   ├── simulator.py
│   ├── evaluator.py
│   └── accounting.py
├── configs/
│   ├── benchmark/hapt_v1.yaml   # 数据、模型、时间与资源预算
│   ├── baselines/
│   ├── sweeps/
│   └── final/
├── data/
│   └── manifests/              # 原始文件、划分与客户端映射哈希
├── baselines/                   # FedAvg、FedProx、SCAFFOLD、Oort 等
│
├── agents/
│   ├── zzr/
│   │   ├── policy.py
│   │   ├── configs/
│   │   ├── runs/                 # 小型摘要可入 Git；大日志放共享产物目录
│   │   ├── HANDOFF.md
│   │   └── RESEARCH.md
│   ├── zzw/
│   │   ├── policy.py
│   │   ├── configs/
│   │   ├── runs/
│   │   ├── HANDOFF.md
│   │   └── RESEARCH.md
│   ├── ghj/
│   │   ├── policy.py
│   │   ├── configs/
│   │   ├── runs/
│   │   ├── HANDOFF.md
│   │   └── RESEARCH.md
│   └── xyk/
│       ├── policy.py
│       ├── configs/
│       ├── runs/
│       ├── HANDOFF.md
│       └── RESEARCH.md
│
├── shared/                      # 全局共享；脚本/受控晋级流程写入
│   ├── OBJECTIVE.md             # 唯一主目标、约束与晋级规则
│   ├── GLOBAL_STATUS.md         # 所有 Agent 的最新进度
│   ├── LEADERBOARD.md           # 自动生成，不手动编辑
│   ├── CHAMPION_DEV.json        # 当前开发期最佳候选
│   ├── CHAMPION_FINAL.json      # 冻结确认后才生成
│   ├── HYPOTHESES.md            # 可继承的研究假设索引
│   ├── EXPERIMENT_INDEX.jsonl   # 不可变实验摘要索引
│   └── champions/              # 历代 Champion 的 commit/config/run 引用
│
├── artifacts/                   # 大型日志、checkpoint，默认不全部提交 Git
│   └── <run_id>/
└── scripts/
    ├── prepare.py
    ├── run.py
    ├── batch.py
    ├── resume.py
    ├── sync_leaderboard.py
    ├── propose_champion.py
    └── finalize.py
```

**写入权限原则**：日常每个 Agent 只修改自己的 `agents/<name>/` 内候选；`benchmark/`、`PROTOCOL.md`、`data/manifests/` 在搜索期冻结。`shared/` 的排行榜和 Champion 由统一工具根据实验记录生成／更新，不能四个人同时手改。

### 7.2 Git 并行与成果可见

推荐：

```text
main                  # 已验证的共享框架、正式协议和索引
agent/zzr             # zzr 的独立实验分支
agent/zzw             # zzw 的独立实验分支
agent/ghj             # ghj 的独立实验分支
agent/xyk             # xyk 的独立实验分支
```

若各自电脑运行，使用独立 clone；如果共享一台机器，使用独立 `git worktree`。不能让四个进程同时直接修改同一个工作树。

**可见性的真实条件**：未推送的本地文件其他人看不到。每完成有意义的实验批次，需要 push，其他 Agent fetch；统一 `sync_leaderboard` 脚本从已发布的分支结果中聚合，并在合并到 `main` 后更新全局可见视图。需要更接近实时的共享，可使用简单共享产物目录+原子写入，但仍记录 Git commit 和 run ID。

建议使用轻量 PR/合并请求或一个受控的集成者工作流解决共享文件冲突。避免 4 个 Agent 对 `LEADERBOARD.md` / `CHAMPION*.json` 并发写入。

### 7.3 每个人的共同目标完全相同

四个工作区不是固定分工。任何人都可以：

- 设计新选择器；
- 对别人方法增加一项机制；
- 复现或反驳别人观察；
- 对当前 Champion 做消融；
- 发现成熟 Baseline 有缺陷时按新协议重新公平对比。

**共同任务**：提出可证伪假设 → 在自己的工作区改 `policy.py` → 与当前最强开发候选在固定 `J` 上比较 → 公布完整证据 → 申请晋级 → 读取他人新结果后继续。

例如四个人同时进行四种临时假设完全可行，但不能把这些假设永久绑定给某人。

### 7.4 候选选择器接口

```python
selected = policy.select(
    available_clients,
    budget_state,
    history,
    num_clients=6,
)

policy.observe(round_feedback)
state = policy.state_dict()
policy.load_state_dict(state)
```

选择器可读取：已知设备档位、历史训练反馈、客户端参与次数、上次参与模拟时间、剩余预算。不可读取：未参与客户端的实时训练损失、隐藏验证/测试标签、任意未来数据。所有需要主动探测的信息都应计费。

主阶段不允许候选修改本地步数、模型、优化器底层规则或聚合权重；否则必须进入独立研究分支及新的比较协议。

---

## 8. 全局排行榜与 Champion–Challenger 机制

### 8.1 两个“最佳”概念，防止验证集被耗尽

- **Development Champion（`CHAMPION_DEV`）**：在**开放的搜索验证集**和公共开发种子上通过 L2 严格对照，目前最强的**开发期方案**。可频繁更新，可供所有 Agent 继承；不能声称已通过独立确认。
- **Final Champion（`CHAMPION_FINAL`）**：搜索冻结后，从少量预注册入围者中，经受限确认协议选择并锁定的**最终方案**。确认验证/最终测试不能作为长期迭代的反馈源。

这里比“每出现一个 L2 胜出者都跑一次隐藏确认”更严格：**若四个 Agent 反复查询确认集，确认集也会被集体过拟合。**

### 8.2 统一排行榜字段

排行榜由完整记录自动计算，而不是 Agent 的文字自评。建议字段：

| 字段 | 含义 |
|---|---|
| `rank`、`method_id`、`owner` | 排名、方法名、所属工作区 |
| `parent_method` | 基于哪个 Champion 或别人的方法开发 |
| `protocol_hash`、`data_hash` | 确保同协议、同数据 |
| `sim_budget_B`、`seeds` | 相同成本口径与完整重复 |
| `J_dev_mean`、`J_dev_sd` | 主指标均值与标准差 |
| `paired_delta_to_champion` | 相对于当时 Champion 的配对差值 |
| `sim_time`、`up_bytes`、`down_bytes` | 真实记账而非虚构开销 |
| `status` | Smoke / L2 complete / failed / timeout / frozen |
| `git_commit`、`config_hash`、`run_ids` | 完整可复现入口 |

未跑齐规定矩阵、成本未校验、协议不匹配的结果，不进入正式排名，但可以保留在探索记录中。

### 8.3 晋级规则

1. 与当前 `CHAMPION_DEV` 在同一数据、预算、种子与成本设置下进行配对实验。
2. 按 `J_dev` 决定排序，保存完整分布而非单个最高分。
3. 改进必须超过**在 Baseline profiling 阶段预先确定**的最小有意义差异，或至少呈现足以进一步核实的机制信号；没有可辨认优势则标记持平。
4. 所有工程正确性和成本计费检查通过，支持断点恢复。
5. 提交方法 commit、配置、运行记录、失败条件和可复现命令后才能晋级。
6. 受限确认和最终测试仅在最后少量候选冻结后执行，不由任何 Agent 在每轮搜索里自由调用。

并行情况下可能出现“同时挑战过时 Champion”：候选发布时必须标明参照的 Champion 版本；晋级工具若发现它已经更新，需要先对新 Champion 做相同协议的重新比较。

### 8.4 共享假设池

`shared/HYPOTHESES.md` 只保存简要索引，详细实验仍在个人 `RESEARCH.md` 与 JSONL 记录中。

| 假设 ID | 内容 | 目前尝试者 | 状态 |
|---|---|---|---|
| H001 | 固定覆盖名额能否改善欠参与客户端 | 任意 Agent | 待实验 |
| H002 | 历史效用奖励是否过度偏向快客户端 | 任意 Agent | 待实验 |
| H003 | 覆盖名额随预算进度变化是否更好 | 任意 Agent | 待实验 |

每个 Agent 都能继承、独立复现、组合或否定已有假设，不设专属题目。

---

## 9. Agent 自主实验流程与三级预算

### 9.1 科研式循环

```text
同步共享状态与最新开发 Champion
           ↓
检查已失败假设与当前研究瓶颈
           ↓
提出一个可证伪假设 + 最小对照
           ↓
在自己的工作区实现候选 policy
           ↓
L1 Smoke：接口、成本、收敛与稳定性
           ↓
L2：固定预算、公共开发种子、配对基线
           ↓
结果是否可靠？机制是否成立？
       ↙                 ↘
   失败/无信号          值得保留
   登记失败原因         发布候选结果
       ↓                 ↓
   换下一个假设      申请开发 Champion 晋级
           ↘         ↙
    再次 fetch 他人结果、继续迭代
```

每个候选至少记录：**观察→假设→仅改变的因素→可观测预测→反证条件→实验配置→结果→保留/否定**。

示例：如果长期未参与客户端被系统性忽视，加入等待阈值触发的一个覆盖名额可能改善其验证 Macro-F1；若参与率提升而分数不提升、或者同速度档随机探索已经达到相同效果，就不支持“历史等待信息带来额外预测收益”。

### 9.2 三级实验（建议初始值，必须经 Profiling 校准）

| 级别 | 推荐规模 | 目标运行时间/次 | 晋级与停止条件 |
|---|---|---|---|
| **L1 Smoke** | 10 客户端、每轮 2 人、约 20 轮、1 开发种子 | 10–30 s；90 s 超时 | 不 NaN、不越权读取、状态恢复正确、存在机制信号；不是凭一次高分晋级 |
| **L2 中级** | 30 客户端、每轮 6 人、约 `B/2`，3 个代表条件 × 3 开发种子 | 30–90 s/次；180 s 超时 | 逐种子配对对照与机制验证；最多保留少量研究候选 |
| **L3 正式** | 完整 `B`、冻结 5 种子与全部正式条件 | 约 30–120 s/次；300 s 超时 | **全局搜索冻结之后**统一运行，不让每个 Agent 无限查询正式结果 |

注意：L2 使用 `B/2` 是筛选，不是终局证明；覆盖机制可能在中后期才发挥作用，应允许少量具有合理长期机制的候选进入完整 `B` 开发评测。具体筛选规则需预注册。

### 9.3 自动停止与防重复

- 一个假设最多尝试约 4 个小变体；失败两批后无机制信号则停止该分支。
- 连续约 6 个中级候选没有改善 `CHAMPION_DEV`、也没有带来有用新发现时，转向解释与验证，而非不断微调。
- Batch Runner 自动跳过相同 `protocol_hash + method/config_hash + seed` 的已完成实验。
- 每条失败原因 `exception/timeout/nan/invalid_budget/no_signal` 入库，不得删除。
- 若模型趋于饱和、Oort 与轮转已给出近似最优表现，停止纯追分，集中完成异构敏感性、消融与局限分析。

### 9.4 实验记录最低 Schema（JSONL）

```json
{
  "run_id": "zzr-20261020-0001",
  "owner": "zzr",
  "method_id": "age_quota_v1",
  "parent_method": "oort_dev_v1",
  "hypothesis_id": "H001",
  "git_commit": "<commit_sha>",
  "protocol_hash": "<sha256>",
  "data_hash": "<sha256>",
  "config_hash": "<sha256>",
  "scenario": "natural_heterogeneous",
  "seed": 101,
  "budget_sim_seconds": null,
  "status": "complete|failed|timeout|invalid",
  "j_dev": null,
  "sim_seconds_used": null,
  "wall_seconds": null,
  "up_bytes": null,
  "down_bytes": null,
  "completed_rounds": null,
  "artifact_uri": "artifacts/<run_id>/"
}
```

字段中 `null` 表示该次记录尚未产生真实测量值，不能为占位示例填入虚构成绩。

---

## 10. 12 小时与四人接力：新版时间组织

### 10.1 关键澄清

**12 小时是某次 Agent 自主运行的可用预算，而不是整个团队的一次统一时间表。**

- `zzr` 可以先开始搜索；`zzw` 可以同时或者之后读取 `zzr` 的已发布结果继续研究。
- `ghj` 可以在别人的结果基础上做机制消融；`xyk` 也可独立探索全新策略。
- 四人都可以各自开展一次或多次不超过约 12 小时的会话。
- 四个 Agent 同时运行 12 小时，相当于最多 **48 Agent-hours**，但实际 CPU-core-hours 取决于硬件和并发限制，不能混为一谈。
- **不设固定人员分工**，只有每个人自己的代码与运行记录隔离。

### 10.2 单次 Agent 会话预算（参考比例）

| 用途 | 建议占比 | 12 小时量级 | 具体目标 |
|---|---:|---:|---|
| 同步共享进度、诊断研究瓶颈 | 5% | 0.6 h | 不重复跑已有高质量实验 |
| L1 假设搜索与快速筛选 | 45% | 5.4 h | 聚焦可解释的小改动 |
| L2 多条件中级比较 | 25% | 3.0 h | 与当前 Champion 公平配对 |
| 本会话优胜候选复核 | 20% | 2.4 h | 确认失败边界、保存可运行版本 |
| 更新交接、提交和清理 | 5% | 0.6 h | 让其他 Agent 可以立即继承 |

这是**每个 Agent 自己的滚动循环**，不是四个人共同按时段做不同任务。某人如果遇到重大错误或候选明显无效，应提前停止该会话分支。

### 10.3 并行资源与协作周期

- 每个 Agent 在不同电脑或不同 CPU 配额上运行，彼此实验吞吐独立。
- 同一台 8 核/16GB 内存笔记本可先尝试同时 2–4 个单线程实验，但并发上限应依实测吞吐决定。
- 不让“某人电脑更快”改变冻结的**模拟时间成本表**；不同硬件的真实 wall-clock 作为资源记录。
- 每次完成一个实验批次或发生 Champion 变化就 push/fetch，定期生成共享排行榜。
- 团队进入最终正式实验阶段后，**停止对已冻结算法的进一步搜索**；必要时可由四台机器分摊确定好的正式矩阵，每项结果必须带环境与协议哈希。

### 10.4 正式评测成本估算

主核心矩阵共 **175 次**完整运行。若在目标硬件上完成一个完整 `B` run 的实际 p90 耗时约为 60 秒，则顺序运行约 175 分钟；在 4 小时确认窗口内还有约 65 分钟缓冲。若 235 次运行、p90 为 45 秒，顺序运行约 176 分钟。

**这是条件估算，不是已验证的性能承诺**。必须以实际完整 `B`、包括策略带来不同轮数的真实计时校准。不能用固定 200 轮结果代替“在 `B` 内能跑多少轮”。

正式评估可以不受某一次 12 小时搜索会话的限制，必要时由多人接力补跑；必须保证同一公开协议下的完整矩阵，而非只留下有利的完成项。

---

## 11. 实现入口、检查点和共享结果发布

> 以下是**建议实现的 CLI 契约**，当前尚未提供这些可执行命令。

### 11.1 运行命令示例

```bash
# 构建固定数据 manifest / 特征缓存（搜索前运行）
python -m flbench.prepare --config configs/benchmark/hapt_v1.yaml

# 单个 Baseline
python -m flbench.run \
  --config configs/baselines/fedavg_uniform.yaml \
  --scenario natural_heterogeneous --seed 101

# 以 zzr 为例，运行自己的候选选择器
python -m flbench.batch \
  --policy agents/zzr/policy.py \
  --manifest agents/zzr/configs/search.yaml \
  --output agents/zzr/runs --jobs 1 --resume

# 断点恢复
python -m flbench.resume --run-id <run_id>

# 获取各分支结果、生成统一排行榜
python scripts/sync_leaderboard.py --fetch-all

# 发起晋级请求：只提交验证材料，不直接覆盖 Champion
python scripts/propose_champion.py --agent zzr --run-id <run_id>

# 搜索结束后，按冻结矩阵运行最终确认/正式结果
python -m flbench.finalize --manifest configs/final/frozen_campaign.yaml
```

### 11.2 每个 run 必须保存

- 完整配置、代码 commit、依赖环境、硬件及协议/数据/成本哈希。
- 模型、优化器、完整 RNG 状态。
- 每客户端持久状态；SCAFFOLD 的客户端和服务器控制变量；选择器内部状态。
- 已完成轮次、模拟时间、上下行累计字节、训练 step 数。
- 逐轮日志、评测指标、异常日志、checkpoint 和复现命令。

建议每 **10 个完整轮次**自动检查点一次。超时后只从完整轮次继续；错误实验按新 run ID 重试，保留原失败记录。

### 11.3 全局最佳保留策略

- `best_runnable`：已通过工程测试、可从检查点运行的算法。
- `CHAMPION_DEV`：当前共享开发验证协议上最强的完整候选。
- `CHAMPION_FINAL`：最终搜索冻结、受限确认结束后选定且不再修改的方法。

Champion 文件只保存不可变 `commit + config_hash + run_ids + objective + eligibility/status` 引用，不通过覆盖其他工作区的 `policy.py` 来“同步最佳算法”。继承方法时由新 Agent 复制/导入对应版本并记录 `parent_method`。

---

## 12. 接力规范：每个人的 HANDOFF 和全局状态

### 12.1 每个 Agent 启动时必须执行

1. 拉取 `main` 和四个 Agent 分支中的最新**已发布**记录。
2. 阅读 `PROTOCOL.md`、`shared/OBJECTIVE.md`、`shared/GLOBAL_STATUS.md`、`shared/LEADERBOARD.md`。
3. 阅读自己 `HANDOFF.md`、当前 `CHAMPION_DEV` 的代码/config，以及最相关的其他 Agent 的 `RESEARCH.md`。
4. 确认当前协议版本、剩余实验预算、最新 Champion 和最近被否定的假设。
5. 再提出自己的下一组实验；不自动沿用已落后的旧 Champion 作为唯一对照。

### 12.2 每个 Agent 结束时必须执行

1. 保存最新可运行算法与恢复点。
2. 把完整运行、失败、重试和超时写入 append-only 实验记录。
3. 更新自己 `HANDOFF.md`、`RESEARCH.md` 中的观察与下一步建议。
4. 提交本工作区代码和配置，push 到自己的分支。
5. 发布实验摘要供 `sync_leaderboard` 读取；有足够证据时申请 Champion 晋级。

### 12.3 `agents/<name>/HANDOFF.md` 标准模板

```markdown
# Agent Handoff

## Identity
- Agent workspace: zzr / zzw / ghj / xyk
- Current branch:
- Latest commit:
- Session stage: profiling / exploration / verification / done
- Wall-clock budget used / remaining:

## Frozen Protocol
- Protocol version / hash:
- Data manifest / hash:
- Simulation cost version / hash:
- Shared metric J and budget B:
- Current Development Champion commit + run IDs:

## My Best Work
- best runnable method / commit:
- best validated method / commit:
- Parent method and key modification:
- Paired delta vs current Champion:
- Completed scenarios / seeds:
- Full reproduce command:

## Research Evidence
- Observation:
- Hypothesis:
- Positive results and run IDs:
- Failed/negative results and run IDs:
- Known limitations:
- Suspected measurement issues:

## Active Jobs / Resume
- In-progress run IDs:
- Checkpoint paths:
- Resume commands:
- Timeout/resource limits:

## Recommended Next Step
1. Next falsifiable hypothesis:
2. Smallest decisive experiment:
3. Stop condition / estimated budget:

## Compliance Checklist
- [ ] Did not edit frozen Benchmark or test data
- [ ] All run results and failures recorded
- [ ] Committed and pushed reproducible code
- [ ] Updated handoff and research log
```

### 12.4 `shared/GLOBAL_STATUS.md` 的作用

全局只回答六件事：

1. 当前固定研究目标、协议哈希与模拟预算 `B`。
2. 当前 `CHAMPION_DEV` 的方法、版本与客观分数。
3. `zzr / zzw / ghj / xyk` 各自正在做什么、运行到哪里。
4. 已被支持、否定和仍不确定的机制性假设。
5. 当前全局最值得解决的研究瓶颈。
6. 正式评测是否已冻结、是否允许进入受限确认或测试阶段。

文件可由各 Agent 的最新发布记录自动汇总，不依赖任何人事后凭记忆手写成绩。

---

## 13. 搜索有效性、验证集保护与风险处理

### 13.1 不要让四个 Agent 集体过拟合验证集

四个 Agent 共同试验数百种选择器时，即便不读最终测试，也可能过拟合开放验证集。因此：

- 主排行榜只开放**搜索验证 20 客户端**与公共开发种子。
- 开发 Champion 晋级可以频繁发生，但始终属于**开发结果**。
- 搜索后锁定少数（建议至多 2 个）最终候选，再有限次数检查**确认验证 10 客户端**。
- 一旦确认结果反馈引发修改，必须明确其从“未见确认”变为“已看过的开发证据”；不能反复当作独立确认。
- 最终 Test 全部 30 客户端只在方法完全冻结时统一跑一套预注册活动，之后不能再把同一测试集视为新算法的未见测试。

若课程时间许可，可增加真正独立的第二数据来源；但 HAPT 与 UCI HAR 不能承担相互独立验证的角色。

### 13.2 科研叙事失败时怎么办

如果速度优先并未损害质量、覆盖策略没有收益、或 Oort 已有明显优势，不要人为增加数据偏差。转向可报告的负结论：

- 在自然异构下速度偏好已经足够好；
- 覆盖修正只在特定系统成本或标签偏斜条件下有效；
- 参与次数增加并不自动改善未参与者质量；
- 状态更复杂的策略收益不足以覆盖实现/通信/稳定性成本。

这仍然是有价值的课程研究，只要对照严谨、边界清楚。

### 13.3 初期最可能遇到的阻碍

| 风险 | 应对 |
|---|---|
| HAPT 原始记录/动作片段不满足预计拆分 | 搜索前完成数据审计、修订并冻结协议，不盲目沿用估算样本数 |
| 每客户端测试样本少，Macro-F1 波动大 | 记录支持量、各客户端分数、成对差异；必要时重新评估研究检测能力 |
| 快慢客户端数据分布差异不明显 | 先报告自然独立速度映射下的事实，不构造有利条件来掩盖 |
| Oort 实现过于复杂 | 适配 selector、保留核心机制与完整计费，不整套引入重型集群系统；明确适配局限 |
| Python 开销大于模型 FLOPs 开销 | 预计算特征、持久张量、减少 DataLoader/进程重建、适当降低评测频率 |
| 四人并行改坏共享框架 | 主核心冻结、独立分支/工作树、PR/CI 协议校验、不可变记录 |
| 共享排行榜写入冲突 | 通过脚本从已发布记录派生、串行/原子更新，不并发编辑 |
| Agent 为排名私自更改预算/测试 | 固定协议哈希、验收脚本拒绝不同配置、隐藏测试隔离、完整审计 |
| 12 小时搜索结束未完成正式实证 | 正式矩阵独立于搜索会话预算安排；预留确认期并支持跨人接力 |

---

## 14. 项目验收标准

### 14.1 最低可交付（即使算法搜索无收益）

- 完成 HAPT 原始数据清点、文件校验、训练/验证/测试隔离、窗口交集为零的审计。
- 实现 FedAvg-U 与至少一条强优化基线、一条调度 Baseline。
- 完成云边端联邦闭环、模拟时钟、上下行通信与实际 CPU 耗时账本。
- 至少覆盖四个主条件、每个方法至少 3 个重复。
- 给出速度偏好、数据覆盖与质量的观察，以及失败案例。
- 一条命令复现指定结果，支持 checkpoint 恢复；四人工作区与记录可持续交接。

### 14.2 合格研究版本

- 核心强基线完整，包含适当的 Oort（或明确记录为何受限）。
- 完成 175 次核心正式矩阵，使用 5 个预注册重复。
- 实现一个简单且机制明确的候选规则；或者给出完整负结果。
- 完成两项关键消融及异构条件比较，给出配对分数、效率和通信成本。
- 每个最终结论能从固定 commit/config/run IDs 复现。
- 最终报告包含 Motivation、Gap、Observation、Hypothesis、Method、Evaluation、Analysis、Limitations。

### 14.3 理想研究版本

- 在预注册主条件下，相对强基线呈现稳定配对优势，**或者**得到清楚的质量—时间 Pareto 权衡。
- 覆盖参与行为、客户端质量变化、成本变化共同支持机制解释。
- 在独立速度映射及至少一种额外敏感性设置下报告其适用边界。
- 不依赖免费在线探测、更多隐藏本地计算、测试后挑选数据划分。
- 若需要显著性主张，提前增加重复数；否则如实报告有限证据。
- 时间允许时使用真正独立的第二数据集检验，不强制增加重型任务。

**不得提前承诺提升 X%**。必须通过 Baseline profiling 估计可改进空间、波动与最小可辨别差异，之后在搜索前冻结“值得继续投入”的阈值。

---

## 15. 推荐执行顺序与第一组关键验证

### 阶段 0：框架建立（不计入算法搜索）

1. 创建四人命名工作区与共享目录，统一依赖、格式、CI 和运行记录契约。
2. 完成 HAPT 数据审计、原始记录拆分、窗口切分、48 维特征缓存。
3. 实现 Local-only、Centralized、FedAvg-U，并验证任务确实可以学到有效模式。
4. 实现固定模拟成本账本、通信计量、完整轮次停止、checkpoint 恢复。
5. 通过单客户端/同构退化测试，确保联邦训练实现正确。

### 阶段 1：建立完整 Baseline Profiling

加入 FedProx、SCAFFOLD、轮转、Fast/Random 和 Oort；测试初始学习率，冻结 `B` 和正式指标。第一组决定性实验优先运行：

> **自然 Non-IID + 独立随机速度映射，3 个开发种子：Uniform FedAvg、Fastest FedAvg、轮转 FedAvg、Oort-FedAvg。**

同时观察：

- 固定模拟时间下哪个方法 Macro-F1 更好；
- 相同训练更新数下结论是否改变；
- 哪些客户端长期未参与；
- 覆盖与尾部客户端质量有无关系；
- 基线质量差异是否超过随机波动。

### 阶段 2：决定是否开启完整 12 小时搜索

开启条件：

1. 数据与评测正确，核心 Baseline 可以复现。
2. 不同选择策略带来可测的效率与覆盖差异。
3. 存在尚未被 Oort/轮转共同完全解决的有效权衡，或有明确待检验的机制。
4. 单次 run 的真实 p90 时间、内存和完整正式矩阵预算可接受。

如果不满足，直接做完整负结果、敏感性分析和报告，不强行寻找算法收益。

### 阶段 3：`zzr / zzw / ghj / xyk` 并行与接续探索

- 各人在自己的工作区开始一次最多约 12 小时的独立科研循环。
- 每个阶段发布完整摘要、失败记录与可运行版本；其他人随时 fetch、继承、对照。
- 共享开发 Champion 根据客观 `J_dev` 更新，不按照谁的描述更好晋级。
- 出现过拟合、统计波动或协议异常时暂停晋级。

### 阶段 4：停止搜索、冻结最终候选

- 选择少量完整候选（建议不超过 2 个），完成受限确认。
- 根据预注册规则锁定最终 Candidate 和必要消融。
- 冻结完整正式矩阵、所有 seeds、模型与成本规则；不再改算法。

### 阶段 5：正式实验与科研报告

- 分布式分摊或接续运行 175 次核心矩阵；吞吐允许才增加增强矩阵。
- 统一汇总预测质量、模拟时钟、真实 CPU 时间、通信、参与覆盖和统计波动。
- 按八段式组织报告：Motivation → Existing Gap → Observation → Hypothesis → Method → Evaluation → Analysis → Limitations。
- 保留正负结果与可重现实验入口。

---

## 16. 重要资料与代表性论文

> 下列工作用于准确定位研究问题与 Baseline；本项目不能凭空宣称“首次提出速度与覆盖的权衡”。正式论文中应按最终使用的版本重新整理标准引文。

1. **HAPT / UCI 数据集**：<https://archive.ics.uci.edu/dataset/341/smartphone+based+recognition+of+human+activities+and+postural+transitions>
2. **ElectricityLoadDiagrams（备选 B）**：<https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014>
3. **AI4I 2020（备选 C，为合成数据）**：<https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset>
4. **FedAvg** — McMahan et al., *Communication-Efficient Learning of Deep Networks from Decentralized Data*, AISTATS 2017：<https://proceedings.mlr.press/v54/mcmahan17a.html>
5. **FedProx** — Li et al., *Federated Optimization in Heterogeneous Networks*, MLSys 2020：<https://proceedings.mlsys.org/paper_files/paper/2020/hash/1f5fe83998a09396ebe6477d9475ba0c-Abstract.html>
6. **SCAFFOLD** — Karimireddy et al., *SCAFFOLD: Stochastic Controlled Averaging for Federated Learning*, ICML 2020：<https://proceedings.mlr.press/v119/karimireddy20a.html>
7. **FedNova** — Wang et al., *Tackling the Objective Inconsistency Problem in Heterogeneous Federated Optimization*, NeurIPS 2020：<https://papers.neurips.cc/paper/2020/hash/564127c03caab942e503ee6f810f54fd-Abstract.html>
8. **Oort** — Lai et al., *Oort: Efficient Federated Learning via Guided Participant Selection*, OSDI 2021：<https://www.usenix.org/conference/osdi21/presentation/lai>
9. **Oort / FedScale 源码入口**：<https://github.com/SymbioticLab/Oort>
10. **Power-of-Choice** — *Towards Understanding Biased Client Selection in Federated Learning*, AISTATS 2022：<https://proceedings.mlr.press/v151/jee-cho22a.html>
11. **FedAU**, ICLR 2024：<https://proceedings.iclr.cc/paper_files/paper/2024/hash/03a9a9c1e15850439653bb971a4ad4b3-Abstract-Conference.html>
12. **HiCS-FL**, NeurIPS 2024：<https://papers.nips.cc/paper_files/paper/2024/hash/7886b9bafe76c52fd568db10ff9772df-Abstract-Conference.html>
13. **Debiasing Federated Learning with Correlated Client Participation**, ICLR 2025：<https://proceedings.iclr.cc/paper_files/paper/2025/hash/464917b6103e074e1f9df7a2bf3bf6ba-Abstract-Conference.html>
14. **Ditto（备选个性化方向）** — Li et al., ICML 2021：<https://proceedings.mlr.press/v139/li21h.html>

---

## 17. 最终定位与需要坚持的原则

本项目希望交付的不是“若干 Agent 自动调参后碰巧更高的准确率”，而是一个**低 CPU 成本、规范可重复、可由四个人长期协作推进的联邦学习实验研究项目**：

- **科研问题可辩护**：系统异构下提高更新吞吐，是否会牺牲客户端代表性？
- **科学目标唯一**：固定模拟时间预算下的客户端平均 Macro-F1。
- **Benchmark 先行**：固定数据、模型、成本、Baseline 与统计协议后再搜索。
- **协作边界清晰**：四个独立目录 `zzr/zzw/ghj/xyk`，共享只读实验规则与自动排行榜。
- **Agent 真正自主**：观察、假设、最小对照、实现、实验、否定/保留、继续。
- **成果可继承**：开发 Champion、假设池、失败记录、完整 checkpoint 与 Git 哈希随时供其他人继续。
- **不偷看答案**：受限确认和最终测试不作为无穷的搜索反馈。
- **负结果可交付**：即使简单基线全面占优，只要机制分析和边界测量可靠，仍构成完整课程研究报告。

> **第一件需要实际做的事**：建立仓库和 HAPT 数据审计脚本，验证训练/验证/测试切分与真实窗口数；随后实现 `FedAvg-U + Uniform` 并跑通模拟时间、通信账本和断点恢复。此时再启动后续 Baseline Profiling，而不是立刻开启 4 个 Agent 的 12 小时搜索。
