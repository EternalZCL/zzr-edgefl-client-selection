# ghj完整核心研究交付（待团队审阅）

已完成175/175预注册正式测试、144次完整预算开发、9次等轮诊断、6次一次性确认，另保留36次搜索前校准。全部372个已发布终态工件（含旧协议37 complete和1 invalid）均校验SHA-256。

主条件候选Macro-F1=.867327，预选SCAFFOLD=.874314，五种子配对差=-.0069866733，精确双侧符号翻转p=.4375。未证实候选优势，负结果和失败完整保留，无测试后调参。

下载ghj-complete-delivery.zip并解压，依照交付说明.md执行restore-project.ps1。完整包包含Git历史、源码、处理后缓存、逐轮日志、检查点、报告和六组图表。不能只用源码ZIP替代Git bundle；恢复后安装锁定uv环境。数据缓存无需重新下载HAPT，首次安装依赖可能需要网络。

SHA256SUMS.txt提供主交付件校验，delivery-manifest.json逐文件校验。恢复脚本已在新目录执行；恢复后的精确环境、仓库ready、共享视图、372工件校验/报告及真实SCAFFOLD恢复均通过。

研究源码51b2cec2e529a2ceb2ba0ba8f8b4664a3ca5015b；正式矩阵在7c13a26预注册；协议hapt-v3-ghj-costs。41项回归和16项真实数据工程检查通过。CI状态见PR #1；本Release保持草稿供团队接收工件并审阅。

草稿PR：https://github.com/EternalZCL/zzr-edgefl-client-selection/pull/1 。未合并main、未晋级Champion，保留团队人工审阅。成员邀请与仓库管理按用户指示排除。
