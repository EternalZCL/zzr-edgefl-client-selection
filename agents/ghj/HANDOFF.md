# ghj 工作交接

## 当前状态

- 成员：ghj；本地分支：codex/ghj-research-completion。
- 科研源代码commit：51b2cec（完整SHA在configs/final/dev-search-v2.json）。
- 协议：hapt-v3-ghj-costs；配置中的phase=development随协议哈希冻结，活动状态以本交接和完成记录为准。
- B=9.836224400模拟秒；共享LR=.1；最小实际意义差异=.005。
- 已完成144次完整B开发、9次等100轮诊断、6次一次性确认、175/175次正式测试；没有仍在运行的活动。
- 全372个终态（371 complete、1旧协议invalid）工件SHA-256已核验；另有36次搜索前校准。

## 本人的成果与来源

- 继承fc61c15的真实HAPT审计、FedAvg/FedProx、消息计量和协作记录工具。
- 补齐SCAFFOLD option II、轮转、Fast/Random、有限Oort适配、Local-only/Centralized、全预算runner、显式阶段清单、每50轮原子恢复、分析与报告。
- Oort来源：Lai et al. OSDI2021及作者SymbioticLab/Oort/oort/oort.py；独立有限适配，不声称作者代码精确复现。
- ghj候选：Fast/Random加等待触发覆盖；6组参数预注册，未改其他成员策略。

## 当前证据

- 候选coverage-1-0.2，开发均值.8985929061；开放验证预选最强基线SCAFFOLD(server LR=1)均值.9016038042，差-.0030108981，未证实收益。
- 保留所有21组基线/6组候选及三种子，不只保留最佳。
- 初版成本审计发现FedProx近端计算/SCAFFOLD额外序列化未充分标定，已修订并重跑。旧37complete+1invalid记录完整保留，未触碰确认/测试标签。
- 最终主条件：候选.867327、SCAFFOLD .874314；五种子配对均值差-.0069866733，SD .0140294957，精确双侧符号翻转p=.4375。未证实优势，不按测试结果重选对照。
- 确认平均配对差-.022186，未据此修改候选。完整四条件、消融和参考见docs/ghj-study/研究报告.md及交付results.json。
- 最终41项回归检查、真实HAPT开发16项检查、精确环境、仓库ready及派生视图检查通过。
- 真实SCAFFOLD run056第70轮恢复至145轮，模型、所有控制变量、RNG、历史、轨迹、预算和消息完全一致，见docs/validation/ghj-final-recovery.json。

## 活动与恢复

- 全部核心活动已完成；正式矩阵在7c13a26预注册后才打开测试集。
- 原活动检查/恢复：uv run --locked --exact python scripts/research.py campaign configs/final/core-final-v2.json。
- 实际重新训练全部175行并保留原证据：uv run --locked --exact python scripts/replay_campaign.py --replicate-id core-final-replay-v1。
- 相同种子复现不能增加独立重复数；不得重新initialize/profile或根据最终测试调参。
- 相同活动命令可恢复：跳过已发布终态，未完成run从artifacts/<run-id>/checkpoint.pt恢复。失败终态另开版本，不覆盖。
- 候选已冻结，不可根据确认/测试结果再调参。Champion仍待人工审阅，没有自动晋级。

## 团队可见性与外部动作

本机gh auth status显示未登录，尚未push本分支、创建PR、邀请成员或修改保护规则。不能把本地提交当作远端成果。PR草稿和维护者设置说明随交付提供；远端操作需实际登录/权限及成员用户名。Champion未晋级，团队人工审阅及合并仍待真实成员处理。

本地交付含八部分中文PDF/HTML/Markdown、六组PNG/SVG/PDF、CSV/JSON、全部逐轮工件和检查点、处理后缓存、完整Git bundle、源码ZIP及安全恢复脚本。仓库docs/ghj-study保留可审阅的报告/PNG；大工件不入Git。报告命令要求先取回全部artifacts：uv run --locked --exact python scripts/report_research.py --output artifacts/report。

可选235次增强、第二独立数据集和其他成员独立科研会话未执行，也不冒称完成。完成数量与证据摘要见COMPLETION.json。
