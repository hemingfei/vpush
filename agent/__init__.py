"""行为器（Agent）：本地常驻 Python 进程，MX 在线行为的唯一决策者（ADR-0001）。

职责（spec #14 / 票 #17）：
- 打开/关闭干净启动的专用 Chrome（CDPExecutor，connect-over-CDP）；
- 全自动登录：profile seed 免登 → 掉登录态 → AI 视觉识码重登（复用 mx_login）；
- 三段随机窗口调度 + 当日计划本地持久化（语义搬运自 app.services.mx_window）；
- 每 5-10 分钟真点击切房间（间隔与抖动搬运自原 app.services.mx_activity）；
- 接力（Relay）：账号注册表 + 失效切换，两账号不并行在线。

架构红线：行为器不感知采集器（互不感知，ADR-0001）；不做云端兜底拉取
（Q4）；不新增拟人动作（Q6）；行为调度语义从 mx_window/原 mx_activity 搬运
（后者已随 ADR-0001 分层删除退役，常量落地 agent/cadence.py），不重写。
"""
