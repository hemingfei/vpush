# 2026-09-06 两周开发回顾批量修复排期

> **状态：已全部完成（同日）。** 51 项修复全部落地（含 4 条并行线 + 集成收尾），未提交，工作区待审。
> 集成验证：全量 pytest 2200 passed；70 个失败经 `git stash` 基线对照证实为 HEAD 预存
> （Windows 环境断言/合并漂移/顺序性 flake，域：cicc/ima/config/twitter/mx 热应用 flake），本次修复引入 0 个新失败。
> 新增回归测试 40+；资产摘要同步至 c017557a01ab；check_inline_handlers 与 node --check 全过。

来源：对 2026-08-23 ~ 09-06 hemingfei 144 个提交的四路审查（MX 实时接入 / MX观点后端 / 前端 / AI分析+移动壳），
共 51 项发现，全部修复。按「文件所有权」拆 4 条并行工作线，同文件只归一条线改，避免并行冲突。

## 线 1：MX 实时接入层

| # | 级别 | 位置 | 问题与修法 |
|---|------|------|-----------|
| A1 | P1 | scheduler.py:2624+2444 | 晚间强关后 `_mx_armed[idx]` 仍 True，窗口循环同窗口内重新拉起会话 → 强关同时 disarm 当前窗口，补回归测试 |
| A2 | P2 | client.py/ws.py/scheduler.py:2826+2872 | 熔断误判面宽、唯一解锁=改 token → 收窄判定（状态码/业务码优先）；手动「登录」时允许半开重探（先清熔断再试，复发再置位）；重存配置也复位 |
| A3 | P2 | ws.py:216+253-290 | `_parse_message` 含解密仍在事件循环线程 → 与帖子解析同池 to_thread |
| A4 | P2 | ws.py:253-285 | socket.io 原生 list 载荷落 `{"raw":...}` 被丢 → 增加 isinstance(data, list) 直通分支 |
| A5 | P3 | scheduler.py:2337 | `_mx_abort_ws` 无条件置 None 可能清掉新会话引用 → 仅 `is task` 时置 None |
| A6 | P3 | scheduler.py:2909 | 窗口内手动登录部分失败后 30s 自动重跑整段登录 → 手动尝试后记录「本窗口已尝试」 |
| A7 | P3 | mx_window.py:64 | 兜底预约槽从未武装窗口里选 → 只从 `_mx_armed` 窗口挑（入参传入武装态） |
| A8 | P3 | fetcher.py:336 | 兜底去重键混入 `_receivedAt`，同消息两次到达键不同 → 摘要前剔除注入字段 |
| A9 | P3 | scheduler.py:2604 | 强关只覆盖 23:30-23:55，之后手动登录可整夜在线 → 增加会话最长时长滚动兜底（如 4h） |
| A10 | P3 | crypto.py:158 | 密钥循环内重复 lzstring 解压 → 解压提到循环外 |
| A11 | P3 | 多处注释 | 「12 秒重连」旧口径残留 → 统一改 16-36s 随机 |
| A12 | P3 | avatar_cache.py:120 | 头像非原子写 + `.part` 残留 → tmp+os.replace、启动清扫超龄 .part |

测试：tests/test_mx.py（A1、A8 必须新增回归用例）。

## 线 2：MX观点后端 + 共享 api/db/llm 层

| # | 级别 | 位置 | 问题与修法 |
|---|------|------|-----------|
| B1 | P1 | mx_view_analysis.py:855+db.py:5445 | 迁移崩溃窗口：replace 非原子 + dirty 天按拆分后数据检测 → replace 包单事务（executemany）；迁移两阶段：先持久化受影响日清单（settings JSON），再改写，重跑可从清单续跑重算 |
| B2 | P2 | mx_view_analysis.py:743-752 | 静默期每分钟造空批次行 → tick 先比对游标与最大帖子 id，无新消息直接返回；批次表按天清理 |
| B3 | P2 | llm.py:148+mx_view_analysis.py:662 | 截断只告警不降载 → `_chat` 暴露 finish_reason；解析失败/截断时半减小区块重试一次 |
| B4 | P2 | 回填 worker | 回填独占批次锁致 live 停摆 → 每个历史窗前检查有无到期 live 快照，有则先跑 live |
| B5 | P2 | db.py:5285-5711 | posts.tags 读-合并-写三方法非原子 → `with self._lock:` 包全程 |
| B6 | P2 | mx_view_analysis.py:276 | 跨作者证据观点记错人 → 校验证据帖 kol_id 唯一，不满足拆分或丢弃 |
| B7 | P3 | mx_view_analysis.py:301/674/891 | 撞名去重方向三处不一 → 统一「更晚胜」，同步改锁定旧行为的测试 |
| B8 | P3 | api.py:5911 | /mx-views/feed 全量无分页 → 增加可选 after_id 增量参数（默认全量，向后兼容） |
| B9 | P3 | api.py:5965 | SSE 每客户端 3s 一次 to_thread+DB 读 → 进程内版本 TTL 缓存（约 2s），N 客户端共享一次读 |
| B10 | P3 | api.py:6458 | 手动跑批 0 消息仍 ok、job 线程无限期阻塞 `_batch_lock` → acquire(timeout)，返回 ran/messages 语义 |
| B11 | P3 | api.py:6384 | batch_size/hints 无上限 → batch_size≤2000、hints≤500 校验 |
| B12 | P3 | mx_view_analysis.py:58 | split_target_name 补全角「．」与「·」分隔符 |
| B13 | P3 | api.py(AI 任务区) | /admin/ai-tasks 补 `^\d{1,2}:\d{2}$`+时分范围校验（并校验窗口 start<end） |
| B14 | P3 | api.py 两套 AI 端点 | 两套端点/模型类重复且语义分叉 → 收敛为一份实现：/admin/ai-analysis 委托 /admin/ai-tasks 同一函数；去重 Pydantic 模型；删死代码 run_due_analysis_tasks、改过时注释（先 grep 前端实际调用的 URL，两组路径都保留） |
| B15 | P3 | api.py:5715+1169 | webhook 签名不覆盖请求体、token 进访问日志 → 代码注释+文档标注「日志含 token，泄露走 regenerate 轮换」 |
| B16 | P3 | llm.py:119 | 管理端 LLM 响应无字节上限 → 加宽松上限（如 20MB 截断） |

测试：test_mx_view_analysis.py / test_mx_views_api.py / test_mx_llm_tagging.py / test_mx_view_tagging.py / test_db.py / test_api.py（B1/B2/B3/B5/B6/B7/B13 新增或更新用例）。

## 线 3：前端

| # | 级别 | 位置 | 问题与修法 |
|---|------|------|-----------|
| C1 | P0 | mx-views.js:1495 | 题材候选 onclick 拼 JS 字符串可注入 → 改 data-idx + 事件委托（对齐 kol.js 黑话候选下标模式） |
| C2 | P1 | kol.js:1192+app.js:6523 | `admin-modal-mask` 不被安卓返回钩子消费 → 钩子遮罩选择器覆盖；该弹窗补 Esc |
| C3 | P1 | app.js:2461 | 提示音每次新建 AudioContext 不 close、不 resume → 模块级复用 + suspended 时 resume |
| C4 | P1 | kol.js:1273-1547 | 打标完成/审核整页重载标签 Tab 清掉未保存词表 → 记服务端快照，dirty 时跳过自动重载并提示 |
| C5 | P2 | mx-views.js:181+324 | 拖动时间轴中 SSE 刷新顶掉选择 → version 处理器 `if (_mxv.tlDrag) return` |
| C6 | P2 | app.js:6919 | AI 弹窗每次开挂 document click 不摘 → 摘旧挂新（对齐 mxvAdminBind） |
| C7 | P3 | mx-views.js:921 | window._mxvPosts 反复追加不去重 → 按 post_id 去重 |
| C8 | P3 | mx-views.js:994 | 抽屉竞态守卫只比 name → 加 type 比对 |
| C9 | P3 | mx-views.js:250+css:65 | 月历「今天」按本地时区 → 改北京时区口径；弹层改锚定按钮定位避免盖状态栏 |
| C10 | P3 | app.js:6520 | 返回键消费链补月历弹层与大V范围下拉收起 |
| C11 | P3 | kol.js:1369 | 「试打 10 条」无防重 → await 期间禁用按钮 |
| C12 | P3 | mx-views.js:336/824 | snapshot_at/direction 等属性插值补 escapeHtml |
| C13 | P3 | mx-views.js:775 | 折叠测量早于懒加载头像完成 → 头像 onload 后重测一次 |
| C14 | P3 | mx-views.js:147+597 | feed 到达后观点流渲染两次 → mxvRenderBoards 加 rerenderFeed 参数 |

测试：test_frontend_mx_views.py / test_frontend_interactions.py / test_frontend_pwa.py（C1/C2/C3/C4/C5 必须有回归断言）。

## 线 4：AI 分析核心 + 安卓壳

| # | 级别 | 位置 | 问题与修法 |
|---|------|------|-----------|
| D1 | P1 | scheduler.py+api.py | 手动「立即运行」与调度无共享互斥 → scheduler.py 提供模块级 `try_begin_ai_task_run(task_id) -> bool` / `end_ai_task_run(task_id)`（内部复用现有 `_ai_task_running` 集合），调度路径改用同函数；api.py 两个 run 端点先 try 再起线程，占用中返回「正在运行中」 |
| D2 | P2 | ai_analysis.py:242 | 运行中任务被禁用仍发报告 → LLM 返回后、插入报告前重读 enabled |
| D3 | P2 | ai_analysis.py:266 | 0 条消息仍调 LLM 发空报告 → 空集合短路落 success/post_count=0 日志跳过 |
| D4 | P2 | ai_analysis.py:107 | prompt 无总量上限 → 总字符预算（~24000），超限按时间新到旧截帖 |
| D5 | P2 | ai_analysis.py:55 | 时区双轨 → `_local_wall_time` 改固定 CN_TZ(+8)，与 published_at 硬绑定 |
| D6 | P3 | ai_analysis.py:280 | 窗口边界字符串比较不对称（含头不含尾）→ 解析为 datetime 比较 |
| D7 | P2 | MainActivity.java:88 | 返回键探针异步竞态 → 探针在飞时 `isEnabled=false`，回调裁决后恢复；退出框先判 isShowing |
| D8 | P3 | AppLinkWebViewClient.java:52 | 壳页任意主机应用内加载 → 非当前服务器主机的外链甩系统浏览器（同主机不变）；cleartext 保持（局域网 http 需要） |
| D9 | P3 | mobile/www/index.html:180 | 探测错误详情截断 + 常见异常归类翻译（内网 IP 不整段裸奔） |

测试：test_ai_analysis.py（D2/D3/D4/D5/D6 更新或新增用例）。

## 跨线契约（唯一共享点）

- **D1 互斥**：scheduler.py 由线 4 实现 `try_begin_ai_task_run` / `end_ai_task_run`；api.py 由线 2 按上述签名调用。集成时由主线跑全量测试验证接线。
- **scheduler.py 分区**：线 1 只改 MX 区块（~2300-3000 行区间），线 4 只改 AI 区块，禁止重排/格式化其他区块。
- **llm.py / db.py / api.py** 归线 2 独占；**app.js / kol.js / mx-views.js / mx-views.css** 归线 3 独占；**ai_analysis.py / mobile/** 归线 4 独占；**fetchers/mx / services/mx_* / avatar_cache** 归线 1 独占。

## 验证

1. 每条线完成后跑各自测试文件，新行为补回归测试，锁定旧行为的测试同步更新。
2. 全部合并后主线跑全量 `python -m pytest tests/ -q`，重点核对 D1 两端接线。
3. 不自动 commit，完成后按线分组汇报，由作者确认后提交。
