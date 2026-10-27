# ghj交付与恢复

本次完成ghj工作区的核心研究和公共基础设施。正式矩阵175/175完成，当前协议144次完整B开发、9次等轮诊断、6次确认全部保留；另含旧成本协议37次完成和1次中断invalid，共372个终态，及36次搜索前校准。

主条件候选Macro-F1为.867327，开发阶段预选SCAFFOLD为.874314，配对差-.0069866733，精确双侧符号翻转p=.4375。结论为未证实候选优势，完整报告保留负结果。

## 交付文件

- 研究报告.pdf：8页中文报告，已渲染并检查全部页面和图表。
- 研究报告.html / 研究报告.md：可阅读/编辑版本；figures含六组PNG/SVG/PDF。
- results.csv / results.json：全部终态分数、正式组均值/SD、配对差、配置及校验信息。
- ghj-complete-delivery.zip：完整恢复包，含Git bundle、源码ZIP、372个运行目录（日志/检查点/原工件ZIP）、处理后数据缓存、报告及恢复脚本。
- ghj-project.bundle：完整Git历史和分支，保留实验源码51b2cec及预注册7c13a26。
- source.zip：便于查阅的源码快照；单独使用它缺少Git历史，不能替代bundle运行研究校验。
- delivery-manifest.json / SHA256SUMS.txt：逐文件/主要交付件SHA-256。
- restore-project.ps1：先校验全部文件，再恢复到一个不存在的新目录；不覆盖已有项目。
- github-submit.ps1 / PR说明.md：登录后提交个人分支及草稿PR的具体材料，不会合并main。

工件摘要使用仓库相对路径。通过恢复脚本复制到原结构后即可解析，无需原电脑的绝对路径。raw数据与.venv不入包；处理后缓存允许在不重新下载HAPT的情况下读入实验数据，首次安装锁定依赖仍可能需要网络。

## 恢复步骤（PowerShell）

先解压ghj-complete-delivery.zip，进入解压后的目录，然后指定一个尚不存在的目标：

```powershell
powershell -ExecutionPolicy Bypass -File .\restore-project.ps1 -Destination 'D:\Projects\ghj-edgefl'
Set-Location 'D:\Projects\ghj-edgefl'
uv tool run --from uv==0.12.23 uv sync --locked
uv tool run --from uv==0.12.23 uv run --locked --exact python scripts/check_environment.py
uv tool run --from uv==0.12.23 uv run --locked --exact python scripts/check_repo.py --require-ready
uv tool run --from uv==0.12.23 uv run --locked --exact python scripts/report_research.py --output artifacts/restored-report
```

源Git bundle是本次交付的权威版本。不要重新initialize/profile，也不要改变数值核心、成本或最终配置，否则必须修订协议并重跑相关比较。

原campaign命令跳过已发布终态，只恢复未完成活动。要实际重训全部175行并保留原证据：

```powershell
uv tool run --from uv==0.12.23 uv run --locked --exact python scripts/replay_campaign.py --replicate-id core-final-replay-v1
```

相同种子复现不能作为更多独立样本。要复核真实SCAFFOLD中途恢复：

```powershell
uv tool run --from uv==0.12.23 uv run --locked --exact python scripts/verify_research.py
```

## GitHub登录与提交

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth status
```

复制终端的一次性验证码，按提示在浏览器登录GitHub并授权。Git认证询问选Y。无需向聊天提供密码或令牌。登录成功且账号有仓库写权限后，在解压交付目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\github-submit.ps1 -RepositoryPath 'D:\Projects\ghj-edgefl'
```

脚本只推送codex/ghj-research-completion并复用/建立草稿PR；无权限时保留本地成果并报错。远端上传、PR链接及权限必须以真实执行结果为准，本次打包时账号尚未登录。

成员邀请需维护者获得三位成员的真实GitHub用户名，在仓库Settings → Collaborators中发送邀请。main保护规则由有管理权限的维护者在Settings → Rules/Branches中设置：要求PR、至少一位审阅者、通过本仓库CI任务、禁止强制推送。先检查现有规则，避免覆盖团队已有设置。未登录、未收到成员用户名时不能假称这些动作已经完成。

Champion仍为空；共享核心、科学证据、最终合并和晋级均留给真实团队审阅。其他成员的独立科研会话、235次可选增强及第二数据集没有冒称执行。
