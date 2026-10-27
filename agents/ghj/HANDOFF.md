# ghj 工作交接

## 当前状态

- 成员：ghj；本地分支：codex/ghj-research-completion。
- 科研源代码commit：51b2cec（完整SHA在configs/final/dev-search-v2.json）。
- 协议：hapt-v3-ghj-costs；配置中的phase=development随协议哈希冻结，活动状态以本交接和完成记录为准。
- B=9.836224400模拟秒；共享LR=.1；最小实际意义差异=.005。
- 目前已完成81次修订协议完整B开发搜索，候选已锁定，正在做另外三条件验证。确认与测试尚未执行。

## 本人的成果与来源

- 继承fc61c15的真实HAPT审计、FedAvg/FedProx、消息计量和协作记录工具。
- 补齐SCAFFOLD option II、轮转、Fast/Random、有限Oort适配、Local-only/Centralized、全预算runner、显式阶段清单、每50轮原子恢复、分析与报告。
- Oort来源：Lai et al. OSDI2021及作者SymbioticLab/Oort/oort/oort.py；独立有限适配，不声称作者代码精确复现。
- ghj候选：Fast/Random加等待触发覆盖；6组参数预注册，未改其他成员策略。

## 当前证据

- 候选coverage-1-0.2，开发均值.8985929061；开放验证预选最强基线SCAFFOLD(server LR=1)均值.9016038042，差-.0030108981，未证实收益。
- 保留所有21组基线/6组候选及三种子，不只保留最佳。
- 初版成本审计发现FedProx近端计算/SCAFFOLD额外序列化未充分标定，已修订并重跑。旧37complete+1invalid记录完整保留，未触碰确认/测试标签。
- 41项回归检查通过；真实HAPT开发16项检查及合成训练/恢复通过。最终交付前将重验。

## 活动与恢复

- 当前活动：configs/final/dev-conditions-v2.json，63次其他条件开发验证。
- 后续：scripts/run_mechanism.py（9次100轮partial）、confirmation-v2（6次一次性确认）、core-final-v2（175次正式）。
- 核心命令：uv run --locked --exact python scripts/research.py campaign configs/final/dev-conditions-v2.json。
- 相同活动命令可恢复：跳过已发布终态，未完成run从artifacts/<run-id>/checkpoint.pt恢复。失败终态另开版本，不覆盖。
- 候选已冻结，不可根据确认/测试结果再调参。Champion仍待人工审阅，没有自动晋级。

## 团队可见性与外部动作

本机gh auth status显示未登录，尚未push本分支、创建PR、邀请成员或修改保护规则。不能把本地提交当作远端成果。完成后提供Git bundle、源代码与工件包；远端操作需实际登录/权限及成员用户名。
