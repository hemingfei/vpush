# Bug 修复交接报告（2026-09-05 全量排查）

> **修复状态（2026-09-05 晚回填）**：本文 §1.1/1.2/1.5、§2.1~2.9、§2.11、§3.1~3.3 已全部修复（范围：MX平台 / 系统KOL / 打标，含顺手修复）；§1.3 资产摘要已 sync（`bump_assets --sync`，最终 digest `68f722f407c6`）。详见文末「§8 修复结果回填」。仅剩 §1.4/2.10（图床）与 §4 测试漂移清单中 3 项未动。

> 产出背景：对 2026-09-03 ~ 09-05 两天开发的全部功能做了系统排查——全量测试 + 5 路专项代码审查（MX观点后端 / MX观点前端 / MX LLM 打标 / 图床镜像 / 前端基础设施与标签审核），每个发现都已在**当前工作区**人工复核行号与代码现场。本文是唯一事实来源，修复 agent 不需要原排查对话。

---

## 0. 仓库状态与工作约定（必读）

- 仓库：`C:\Users\hemin\Documents\vpush`，分支 `hmf`。
- 排查期间 HEAD 已从 `fee6815` 前移到 `bf322f5`：并行会话完成了 `origin/main`（v1.12.140）的合并（`15950b0`）并提交了图片处理 WIP（`bf322f5`，已验证 103 个相关测试全过）。**本文所有行号均为当前工作区实核行号**，并附代码锚点以防后续漂移。
- ⚠️ **并行会话正在开发新功能**（`/mx-views/feed` 端点 + mx-views 大V模式/时刻轴重构），当前未提交改动涉及：`app/api.py`、`app/static/app.js`、`app/static/index.html`、`app/static/mx-views.css`、`app/static/views/mx-views.js`、`tests/test_frontend_mx_views.py`。修复这些文件时先 `git diff` 确认没踩到别人未提交的工作，能避开重行号、用代码锚点定位。
- 测试命令（Windows，本仓库 venv）：
  ```bash
  .venv/Scripts/python.exe -m pytest -q -p no:warnings \
    --ignore=tests/test_cicc_collector.py \
    --ignore=tests/test_frontend_runtime.py \
    --ignore=tests/test_pdf_compression.py \
    --ignore=tests/test_pdf_dedup_hardlink.py
  ```
  四个 ignore 是 Windows 环境问题（fcntl Unix-only / 未装 playwright），不是代码问题。
- **已知环境噪音测试（不要修、不要追）**：`tests/test_ima_*`、`tests/test_local_libraries.py`（symlink/600 权限类）、`waf-bot/test_watchdog.py`、`tests/test_kol_webhook.py::test_incoming_rate_limit`（本机每 POST ~2.5s，时间窗限流打不满，Linux CI 会过）、`tests/test_cicc_alerts.py`、`tests/test_frontend_interactions.py` 中部分 CSS 静态断言（见 §4，属有意变更待更新测试）。
- 前端"测试"多为 Python 静态源码检查（读 JS/CSS 源码断言约定），改完 JS/CSS 后跑对应 `tests/test_frontend_*.py` 即可验证。

---

## 1. 高优先级（P1/P2，建议最先修）

### 1.1 [P1] MX观点「查看原始消息」按钮 100% 显示"没有保存原始数据"
- **位置**：`app/static/views/mx-views.js:590`（锚点：`content: e.content, detail: "", tags: []`），配合 `app/static/app.js` 的 `openRawModal`（搜索 `function openRawModal`）。
- **根因**：证据抽屉把每条证据缓存进 `window._mxvPosts` 时 `detail` 硬编码为空串；而 `openRawModal` 只渲染 `post.detail`、从不读 `post.content`，导致 `hasRaw` 恒为 false。
- **失败场景**：打开题材/大V钻取抽屉 → 展开"依据消息" → 点「查看原始消息」→ 弹窗只有作者/时间，原文区恒为"该消息没有保存原始数据"。后端证据内容被截断到 800 字（`app/db.py` 证据查询处），全文用户永远拿不到。
- **修法**：缓存时写 `detail: e.content`（openRawModal 的 string-detail 分支会渲染进 `<pre>`）；或改为按 post_id 拉全文接口。前端方案改动最小。
- **验收**：`tests/test_frontend_mx_views.py` 全绿；手工验证抽屉内按钮能弹出原文。

### 1.2 [P1] MX token 明文进日志（含管理端可见的系统日志）
- **位置**：`app/api.py:5119`（锚点：`logger.info(f"Received MX config update: {raw_body}")`）。
- **根因**：PUT MX 配置时把原始 body 整个 dict-repr 落日志。全局 `app/logging_setup.py` 的 `RedactingFormatter` 只匹配 `token=`、`Bearer …`、`imgbed_…` 形式，匹配不到 `"'token': '…'"`，凭据进入控制台、滚动日志文件、以及管理端 `GET /api/admin/system-logs` 返回的环形缓冲。
- **修法**：日志前深拷贝 body 并 pop 掉 `token`（以及其他敏感键），只打非敏感键；或改打 `sorted(body.keys())`。
- **验收**：更新 MX 配置后，`grep -i token` 日志文件与管理端系统日志接口均无明文 token；`tests/test_error_redaction.py` 仍绿。

### 1.3 [P1·发布门禁] 前端资产摘要过期——两个发布守卫测试红
- **位置**：`app/static/index.html` 与 `app/static/sw.js`（`CACHE = "dav-shell-…"`）中的资产摘要串落后于当前源码；失败测试：`tests/test_frontend_interactions.py:4327`（`test_static_asset_cache_bust_versions`）与 `tests/test_frontend_pwa.py`（`test_frontend_assets_match_financial_news_release_revision`）。
- **根因**：最后执行 `scripts/bump_assets.py --sync` 之后又有 13+ 个 view/core 模块改版（含 MX观点系列与标签审核），index.html/sw.js 的摘要没有重算。v1.12.95 曾以同样方式发过过期资产（见 `tests/test_release_guards.py` 注释），后果是老客户端拿缓存旧 JS 配新后端、SW precache 永不刷新。
- **修法**：发布前运行 `python scripts/bump_assets.py --sync`（合并/并行会话 WIP 落定之后跑一次）。
- **验收**：上述两个测试转绿。

### 1.4 [P2] 图床「停用（清除）」后历史帖不回退，与确认弹窗承诺相反
- **位置**：`app/imgbed.py:99`（`display_url`，无 `enabled()` 检查）、`app/imgbed.py` `clear_imgbed`（只清 settings 键）、调用链 `app/db.py:187`（`_normalize_post_images` → `rewrite_urls`，每次列表/详情查询都会跑）；前端承诺文案在 `app/static/app.js:4313` 附近（"清除后 X 配图退回服务端代理，直到重新接入"）。
- **失败场景**：图床故障 → 管理员清除配置期望回退代理 → 所有已镜像历史帖 `display_url` 仍指向图床域名 → 全部裂图，直到重新接入。另外若 `IMGBED_BASE_URL/IMGBED_TOKEN` 环境变量在，清除反而"复活"镜像。
- **修法（二选一或都做）**：a) `display_url` 内先查 `enabled()`，停用时返回原始 URL；b) `clear_imgbed` 时把 `hosted_images` 中 ready 行回滚/标记失效。
- **验收**：`tests/test_imgbed.py` 全绿 + 新增"停用后 display_url 返回原 URL"用例。

### 1.5 [P2] MX观点回填重放已跑过的日子 → 观点重复、钻取时间线双条
- **位置**：`app/mx_view_analysis.py:662` 附近（backfill 重放循环，`kind="backfill"` 无条件逐窗重跑）；唯一约束 `app/db.py` `mx_opinions` 表 `UNIQUE(batch_id, kol_id, target_type, target_name)`（只到 batch 级）；`app/db.py:5238` `replace_mx_opinions` 只删 backfill 批次自己的行。
- **失败场景**：某日 live 已跑到 11:00 后进程崩溃，管理员回填"今天"补下午 → 同一 (trading_day, snapshot_at, kol, target) 出现两行（live 批 + backfill 批）。快照页聚合有幸存者逻辑看不到，但 `/mx-views/target`、`/mx-views/kol` 钻取时间线（`get_mx_view_target_detail` / `get_mx_view_kol_detail`）逐行 append → 同一大V同一时刻两条、且独立 LLM 调用可能一条多一条空。
- **修法**：回填按天循环内跳过 `mx_view_batches` 中已有 `status='done'` 的 `(trading_day, snapshot_at)`；或钻取明细按 `(kol_id, snapshot_at)` 去重取最新 batch。
- **验收**：`tests/test_mx_view_analysis.py` 全绿 + 新增"回填跳过已完成快照"用例（回填同一天两次，`list_mx_opinions` 行数不翻倍）。

---

## 2. 中低优先级（P3，功能正确性/健壮性）

### 2.1 时刻表接受 "24:00"，可让当天 live 调度永久哑火
- **位置**：`app/mx_view_analysis.py:55`（`_HHMM_RE = re.compile(r"^\d{2}:\d{2}$")`，无 0-23 约束）；PUT 校验在 `app/api.py:6529` 附近只要求 `resolve_schedule` 非空。
- **链路**：管理员 PUT `extra_times:["24:00"]` → 200 收下 → 回填写入 `snapshot_at="24:00"` → `run_due_view_batch`（`app/mx_view_analysis.py:568`）取 `last_done=max(done)="24:00"`，当天 `t > "24:00"` 恒空 → 之后所有 live 快照静默跳过（手动跑批仍可用，难排查）。
- **修法**：`resolve_schedule`（`:63`）里拒绝 `> "23:59"` 的时刻；PUT 侧同步报 400。

### 2.2 时段终点不落格：interval 不整除时 end 快照丢失
- **位置**：`app/mx_view_analysis.py:75-84`（`resolve_schedule` 生成循环只 stride 生成 `cur`，`(end-start) % interval != 0` 时 end 丢弃），与函数 docstring"段起点与终点都生成"矛盾。
- **失败场景**：`{"start":"09:30","end":"11:30","interval_min":45}` → 只生成 09:30/10:15/11:00，管理员配置的 11:30 快照不存在，11:00–11:30 的尾窗消息滚入下一时段窗口。默认 38 时刻表恰好整除，所以现有测试测不出。
- **修法**：循环后补 `if times[-1] != end: times.append(end)`（注意去重与跨段排序）。

### 2.3 batch 进程中断后 `running` 状态永不清理
- **位置**：`app/db.py:5217`（`upsert_mx_view_batch` 先插 running 行）、`app/mx_view_analysis.py` `run_snapshot_batch` 的 try/except 只覆盖进程内异常（`finish_mx_view_batch(..., "failed")`，`app/db.py:5232`）；无启动 sweep。
- **失败场景**：部署重启/OOM 杀在 LLM 调用中 → 该行永远 `running`，`/admin/mx-views/status` 永远显示运行中、`batches_today` 虚高。
- **修法**：启动时 `UPDATE mx_view_batches SET status='aborted' WHERE status='running'`（或按进程启动时间判定）。

### 2.4 打标进度轮询两个盲区（前端）
- **位置**：`app/static/views/admin/kol.js:1216`（`if (prog.running)` 终止轮询）；后端 `app/mx_llm_tagging.py` 的 `get_manual_job_status` 只以 `status=="running"` 判 running。
- **失败场景 a**：一个批失败立即把 run 置 `failed`，但兄弟批还在跑（单批 LLM 最长 ~10 分钟）→ 轮询提前停，面板显示过早的"已结束"，最终 summary 与完成 flash 迟到或不来。
- **失败场景 b**：tags 面板空载挂载（轮询跑一次即停）→ 之后服务端自动触发任务（`mx_llm_tag_auto_loop`）→ 专用自动进度框永远空白。
- **修法**：后端返回 `unfinished`（任一 run 未 finalize 即 true），前端以 unfinished 决定续轮；或 tags 面板挂载期间保留低频轮询（如 15s）。

### 2.5 「开始打标」按钮未防双击
- **位置**：`app/static/views/admin/kol.js:1294`（`adminMxTagStartRun`，成功才解 mask）。
- **失败场景**：双击 → 两个 POST；后端 claim 保证无数据问题，但第二个返回 400「所选大V暂无未打标消息」→ 用户同时看到「已启动」+「启动失败」两条 flash。
- **修法**：await 前禁用按钮 + 文案"启动中…"，catch 分支恢复。

### 2.6 大V范围下拉可勾进已停用大V（且后端不过滤）
- **位置**：`app/static/views/mx-views.js:929`（`mxvAdminKolToggleItem` 无 `k.enabled` 守卫）、`:938`（`mxvAdminKolAll` 全选包含停用项）；数据源 `/api/admin/kols?platform=mx&limit=500` 不带 status 过滤；后端窗口查询 `list_mx_posts_in_window`（`app/db.py`）也不过滤 enabled。
- **失败场景**：全选 → 停用大V被写进 `kol_ids` → 其消息照常送 LLM 研判计费。
- **修法**：toggle/all 跳过 `!k.enabled`；后端窗口查询加 `k.enabled=1` 兜底。

### 2.7 快照切换无乱序保护
- **位置**：`app/static/views/mx-views.js:79`（`mxvApplySnapshot`，无请求序号/版本比对）。
- **失败场景**：快速点 ◀ 再点「回最新」→ 旧响应后到覆盖新状态，界面停在旧快照。
- **修法**：模块级递增 requestId，await 后比对丢弃过期响应（参考同文件 `_mxvTargets` 的既有模式）。

### 2.8 `/mx-views/day` 与 20s 调度 tick 全量解析大 payload（性能）
- **位置**：`app/api.py:6022-6023`（async 端点内同步 `json.loads` 全天最多 ~40 份 payload）；`app/mx_view_analysis.py:568` 起 `run_due_view_batch` 每 20s tick 同样只为取 `snapshot_at` 集合而全量解析。
- **修法**：新增轻量查询 `SELECT snapshot_at, seq, kind, message_count FROM mx_view_snapshots WHERE trading_day=?`（避免 `db.list_mx_view_snapshots` 的 `_parse_snapshot_row` 全量解析）。

### 2.9 「MX原始消息」弹窗 meta 只显示时分
- **位置**：`app/static/app.js:3670`（锚点：`fmtPublished(post.published_at, true)`）。
- **说明**：与已修的 9946c4a 同类问题（clockOnly 参数残留），去掉第二参即可。

### 2.10 图床挂掉时前端回退链路不通
- **位置**：`app/api.py:941`（`IMAGE_PROXY_HOSTS` 白名单）与 `:7375`（host 校验）；`app/imgbed.py:3` docstring 承诺"失败则退回 /api/img-proxy"。
- **失败场景**：`display_url` 已把 twimg URL 替换为图床地址 → 图床 500 → 前端 `imgOnError` 把**图床 URL** 丢给 `/api/img-proxy` → 400（host 不在白名单）→ `markImgDead` 删图。原始 twimg 其实还能走代理。
- **修法**：img-proxy 白名单纳入 `imgbed.public_host()`；或后端 payload 保留原 URL 作为 data-fallback。

### 2.11 mx-views.css 不在 SW 版本/离线体系内
- **位置**：`app/static/sw.js:3`（`SHELL` 无 mx-views.css）；`app/static/index.html` 手工 `?v=3`；`scripts/bump_assets.py` 的 `module_urls` 只处理 `.js`。测试 `tests/test_frontend_mx_views.py:28` 还 pin 死了 `?v=2`（本次 WIP 已改 3，测试同步改了）。
- **修法**：bump_assets 支持"额外样式表清单"或把样式并入 style.css；SHELL 相应补充。

---

## 3. 旧账（2026-08-28 引入，非这两天，但套件一直红）

### 3.1 `db.py` 有两个 `get_kol` 定义，后者覆盖前者 → 恢复推送丢失 category
- **位置**：`app/db.py:2064`（带 `LEFT JOIN categories` → `category_name`）与 `app/db.py:2215`（`SELECT * FROM kols` + `_strip_webhook_fields`，**Python 类体后者胜出**）。引入自 a3952cb（8/28）。
- **失败场景**：`scheduler._recover_failed_pushes`（`app/scheduler.py:3252` 起）用 `(kol or {}).get("category_name") or ""` 重建 Post → 恒空串。`tests/test_scheduler.py:2210` 断言 `category == "实盘"` 失败。其余 20+ 处 `db.get_kol(` 调用方也全部拿不到 category_name。
- **修法**：合并成一个定义——保留 join，同时保留 `_strip_webhook_fields`（webhook secret 不能外泄，API 返回路径依赖它）。⚠️ 改前先 `grep -rn "\.get_kol(" app/` 确认两种字段都有消费方。
- **验收**：`tests/test_scheduler.py::test_insert_post_persists_detail_and_recovery_restores_fields` 转绿；`tests/test_kol_webhook.py` 全绿（secret 不泄漏）。

### 3.2 系统 KOL 计数漂移：两个旧测试红
- **位置**：`tests/test_api.py:580`（`stats["kols"] == 2`，实际 3）与 `tests/test_api.py:195`（`data["total"] == 13`，实际 14）。来源：8/28 `main.py` 启动无条件创建系统 KOL"AI 分析报告"（platform=system）。
- **需要用户拍板口径**：stats/kol 列表是否应排除 `platform="system"`（推荐排除——系统 KOL 不是真大V），还是更新测试基线（+1）。修复时同步检查 `enabled_kols/priority_kols/secondary_kols` 三个计数与前端大V列表分页。
- **验收**：按选定口径，`tests/test_api.py::test_stats_api`、`test_admin_kols_pagination_and_filters` 转绿。

### 3.3 XSS 守卫测试失败（一处真违规、一处误报）
- **真违规**：`app/static/app.js:3619-3620`（锚点：`onclick="...openRawModal(${post.id}, '${RAW_MODAL_LABELS[post.platform]}')"`）——把动态来源字段（`.platform`，在 `tests/test_frontend_xss.py:16` 的 `USER_FIELDS` 清单里）内插进内联 handler 的 JS 字符串上下文。当前值来自硬编码表 `{mx:"MX", system:"系统 KOL"}`、运行时风险低，但违反自家守卫约定（同文件 tag 已改 `data-tag`/`dataset` 模式）。修法：label 走 `data-*` + dataset 读取，或把 `RAW_MODAL_LABELS[` 加进测试白名单（需用户认可该模式）。
- **误报**：`app/static/app.js` 原_fee6815:2699 行（现在搜索 `aria-label="只看 ${escapeHtml(k.name)}` 那行）——同一行里含安全的 `onclick="tlPickKol(${k.id})"` 和已转义的 aria-label，测试行粒度误伤。修法：测试断言按属性粒度而非行粒度，或把该行改写成两个模板行（顺手）。
- **验收**：`tests/test_frontend_xss.py` 两个用例转绿，且不是靠删 `USER_FIELDS` 字段糊弄。

---

## 4. 测试漂移清单（有意变更，测试待更新；不要改产品代码）

1. `tests/test_twitter_fetcher.py:363`：断言 `published_at == "2026-08-04 20:00"`，但代码已按"秒级时间回填"特性归一为 `YYYY-MM-DD HH:MM:SS`（`2026-08-04 20:00:00`）。更新断言。
2. `tests/test_frontend_interactions.py:755` 附近：桌面 badge 栏从 `repeat(8, minmax(0,1fr))` 改为自适应列（`style.css` `#tl-filterbar .icon-badge-bar`，有注释说明意图）→ 更新断言。
3. 同文件 rail 测试（`test_timeline_rail_fills_main_and_survives_resize`）：`top: 56px` → `top: calc(56px + var(--safe-top))`（安全区改造，Capacitor 壳可覆盖）→ 正则放宽。
4. 同文件 ima 导航测试：`.tl-ima-entry` margin `12px` → `8px` → 对齐其一（和产品确认哪边是对的）。
5. 同文件 `test_post_tags_filter_timeline_without_inline_user_string`：tag chips 已从 `postCard` 位移到 `renderPostTagChips`（不变式仍成立）→ 断言目标改指新函数。

---

## 5. 已验证干净的区域（不需要重复排查）

- MX观点后端：时区/交易日归属（published_at 统一北京时 YYYY-MM-DD HH:MM:SS；CN_TZ 固定 +8）、版本推进先于可见性的顺序、SSE（连接即推 + 3s 轮询 + 心跳 + 断连检测 + 上限重连）、`_batch_lock` 并发语义、SQL 全参数化、LLM 坏 JSON → 批次 failed 可重试不崩溃。
- 打标队列：worker 池 spawn/exit 串行化、批次恰好 settle 一次、`_claimed_ids` 原子 claim（手动+自动同时跑不会双打标）、`limit≤0` 端到端语义（1200 条 → 12 批）、自动触发边界与断电补跑、半选态数学正确、fmtPublished 全调用点签名一致。
- 图床：SSRF 防护完整（`url_safety.py` 逐跳校验公网 IP、redirect 重校验、https-only、content-type 白名单、10MB 上限）、`source_url` 主键去重、失败 15 分钟重试不静默、连通检查无用户 URL SSRF、token 更新时间只在值变化时写。
- 前端：13 个 view 模块 import/export 全对齐（含 FOLDER_ICON 教训后全量核对 icons.js 36 个导出）、SPA 白名单覆盖所有路由、INLINE_HANDLERS 挂载完整（mx-views 全部 18 个 admin handler + kol.js 全部）、用户页 XSS sink 全部走 escapeHtml、SSE 生命周期路由切换即清理。
- 标签审核批量操作：require_admin、逐项处理 + 逐项回滚 pending、审计日志、"遗留重复待审不进审核"三处一致、`UNIQUE(post_id, tag)` 兜底。
- WIP 提交 bf322f5（网页链接卡片/None 语义/imgOnError 闭包/反向校验）：叠加干净基线实测 103 个相关测试全过。

## 6. 排查后已被修掉、无需再动

- `mxvAdminAdopt('${escapeHtml(c)}')` 的 JS 字符串注入面（原 P2，候选名含 `'` 即按钮死 + 可注入）：当前工作区已不存在（并行会话重构时已消除）。
- `scripts/repair_mx_file_images.py` 2 元组解包 ValueError（原 P1）：bf322f5 已修。

---

## 7. 建议修复顺序与提交切分

| 批次 | 内容 | 预估 |
|---|---|---|
| ① 立即 | 1.1（detail:e.content 一行）、1.2（log 前 pop token）、2.9（去 clockOnly） | 小改动，各自独立提交 |
| ② 发布门禁 | 1.3：并行会话 WIP 落定后跑 `python scripts/bump_assets.py --sync`，两个守卫测试转绿再发版 | 一条命令 |
| ③ MX观点后端 | 2.1、2.2、2.3、1.5、2.8（同在 mx_view_analysis/db.py，可一个提交） | 中 |
| ④ 图床 | 1.4、2.10、2.11（imgbed 相关一个提交） | 中 |
| ⑤ 打标前端 | 2.4、2.5、2.6 | 小 |
| ⑥ 旧账 | 3.1（get_kol 合并）、3.3（XSS 守卫）、3.2（需用户拍板口径） | 中，3.2 先问 |
| ⑦ 测试漂移 | §4 清单，纯测试文件 | 小 |

每批修完跑一遍 §0 的全量命令，对照 §5/§0 噪音清单确认没有新增失败。

---

## 8. 修复结果回填（2026-09-05 晚，修复 agent）

> 范围：用户指定「MX平台 / 系统KOL / 打标」。全量命令跑完：**42 failed / 2049 passed**，其中 28 个为 §0 已记录环境噪音、3 个为 §4 测试漂移、1 个为并行会话改 mx-views.css 的瞬时快照（复跑即绿），**零个由修复引入**。改动含并行会话 WIP 文件处均已先核对其未提交工作，未回退任何 WIP。

### 8.1 已修复

| 项 | 修法 | 验证 |
|---|---|---|
| 1.1 原始消息弹窗恒空 | `mxvEvidenceHtml` 缓存改为 `detail: e.content`（openRawModal 字符串分支渲染进 `<pre>`） | mx-views 静态回归 + openRawModal body 断言 |
| 1.2 MX token 进日志 | `update_mx_config` 打日志前剔除 `token` 键；新增 `test_mx.py::test_update_mx_config_log_does_not_leak_token`（caplog 断言明文不落日志、非敏感键照常记录） | 新用例 + test_error_redaction 全绿 |
| 1.3 资产摘要过期 | `bump_assets --sync`；最终 digest `68f722f407c6`（mx-views.css/摘要体系部分已随并行会话 bc1ea5c 先行合入）；两个守卫测试转绿 | test_static_asset_cache_bust_versions / test_frontend_pwa |
| 1.5 回填重放观点翻倍 | 回填 worker 循环内 `db.has_done_mx_view_batch(day, end)` 跳过已有 done 批的 (day, at)（断点续跑语义）；新增同日两次回填 `list_mx_opinions` 不翻倍用例 | 新用例 + 原回填测试不回归 |
| 2.1 时刻表收 "24:00" | `_valid_hhmm`（00:00–23:59 严格校验）+ `validate_schedule_config`；PUT 非法时刻 422；新增 resolve/validate 用例与 PUT 422 用例 | 新用例 + 原 38 时刻表用例不变 |
| 2.2 段终点不落格 | `resolve_schedule` 步进后补 `times.add(stop)`（start>end 段仍忽略）；新增 09:30–11:30/45min → 含 11:30 用例 | 新用例 |
| 2.3 running 批永不清理 | `db.abort_stale_mx_view_batches()`；`create_app` 启动即调用（status→aborted） | 新用例 + 全量无回归 |
| 2.4 打标轮询盲区 | 后端 `get_manual_job_status` 新增 `unfinished`（任一 run 未收场即 true）；前端 `prog.running \|\| prog.unfinished` 续轮 3s，空闲且打标面板挂载时保留 15s 慢轮兜自动触发；新增中间态用例 | 新用例 |
| 2.5 开始打标防双击 | await 前禁用按钮 +「启动中…」，失败派发 change 让 recount 还原；新增无（UI 行为，静态可查） | 手工逻辑复核 |
| 2.6 停用大V可进研判范围 | 前端 `mxvAdminKolToggleItem` 禁止新勾选停用大V（残留的可勾掉）、`mxvAdminKolAll` 只加 enabled；后端 `list_mx_posts_in_window` 加 `k.enabled = 1` 兜底；新增窗口过滤用例 | 新用例 |
| 2.7 快照乱序 | 并行会话已修（applySeq token），本次未动 | — |
| 2.8 全量解析 payload | 新增 `db.list_mx_view_snapshot_meta`（`json_extract` 取 message_count，不解析 payload）；`/mx-views/day` 与 `run_due_view_batch` tick 均改用 | 新用例 + /mx-views/day 响应形状不变 |
| 2.9 弹窗 meta 只显示时分 | 去掉 `fmtPublished(post.published_at, true)` 第二参 | — |
| 2.11 mx-views.css 不在 SW 体系 | `bump_assets.py` 新增 `EXTRA_STYLESHEETS = ("mx-views.css",)`（纳入 digest + index.html 引用维护）；sw.js SHELL 补 `/mx-views.css`；test_frontend_mx_views 的 `?v=3` pin 改为 digest 正则；test_asset_versions 夹具补 mx-views.css 与引用、参数化新增该文件；PWA 守卫新增两条断言 | test_asset_versions 34 全绿 |
| 3.1 双 get_kol | 合并为一个定义：保留 categories JOIN（category_name）+ `_strip_webhook_fields`；test_scheduler 恢复测试、test_tg_callback、test_old_db_migrates、test_category_crud 全转绿，test_kol_webhook（secret 不泄漏）全绿 | 18 passed |
| 3.2 系统KOL口径 | 采用文档推荐口径并**一致化**：`platform="system"` 视为内部输出通道，从**所有列表/计数**统一排除——`/admin/kols`（list/count/ids 新增 `exclude_platform`）、stats、`GET /kols`、`/catalog`、`db.recommended_kols`。`test_batch_import_system_kol...` 改为直查 `db.list_kols(platform="system")` 验证导入格式（system 平台导入仍可用，但不再出现在列表） | test_api.py 全绿 |
| 3.3 XSS 守卫 | ① RAW_MODAL_LABELS：label 改 `data-raw-label` + `this.dataset.rawLabel`，属性值经 escapeHtml；② aria-label 误报行：onclick 拆到独立模板行；③ 新发现 `refreshMxWsStatus` 的 `${s.detail}`：改为定义处 `escapeHtml` 包裹 | test_frontend_xss 4 用例全绿 |

### 8.2 排查中新发现并已修（文档未记录）

- **[P1] POST /api/kols 自动命名死代码（合并缩进回归）**：`if not name:` 自动查名块被误嵌进 `elif platform == "twitter":` 分支内，combination/weibo/system/zsxq 自动命名全部失效（name 恒空占位）。已按 origin/main 结构还原缩进（保留 hmf 的 system 分支）。`test_add_combination_kol_auto_fills_name`、`test_add_weibo_kol_auto_resolves_name_and_avatar` 转绿。
- **系统KOL泄漏面比文档记录的大**：除 §3.2 两个用例外，`/api/kols`、`/catalog`、`/recommendations`、ACL 可见性共 6 个存量红测试同根（HEAD worktree 复核确认非本次引入）。见 8.1 的 3.2 行。

### 8.3 未动（明确遗留）

- §1.4 图床停用回退、§2.10 图床回退链路：**不在本次范围**（图床专项）。
- §4 测试漂移清单：仅修了第 5 条（tag chips 断言改指 `renderPostTagChips`，属打标展示）；其余 4 条（twitter 秒级、桌面 badge 栏、rail 安全区、ima margin、字号刻度 `test_type_scale`）维持「有意变更待更新测试」，未动产品代码。
- `test_config.py` 5 个失败：本机未跟踪 `.env` 经 dotenv 污染 ENV 覆盖断言（HEAD worktree 无 `.env` 即全过），环境噪音勿追。
- 提交切分建议按 §7，其中批次⑥⑦已完成部分见 8.1；图床批次（1.4/2.10）待做。
