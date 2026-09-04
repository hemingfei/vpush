# 全景值班台：监控总览 / 大V健康并入全景概览 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 管理员打开全景概览一屏能回答「量正不正常 / 哪条管线坏了 / 谁停更了」；数据源页只负责改管线（抓取设置、Cookie、代理、广场显示）。

**Architecture:** 不改 `/api/stats` 和 `/api/admin/dashboard` 的载荷。全景继续并行拉这两个接口；把 `renderStatsData()` 变成活块补丁（平台表、告警、Cookie 条、停更名单），30 秒只刷新这一块。数据源页删掉「监控总览」「大V健康」两个 tab；旧 `?tab=overview|health` 跳回全景。

**Tech Stack:** 现有静态 `app/static/app.js` + `style.css`；前端契约在 `tests/test_frontend_interactions.py`（字符串扫描，无 jsdom）。Python 用 `.venv/bin/python`。

**约定来源:** 2026-08-27 对话：合的是职责，不是两页原样搬家。全景已有一份更瘦的数据源表，以监控总览那张完整表为准并只留一份。

---

## File map

| File | Responsibility |
|---|---|
| `app/static/app.js` | 全景值班布局、活块补丁、数据源 tab 收缩、旧 tab 跳转、Cookie 条改 `go()` |
| `app/static/style.css` | 值班元信息行、停更名单、数据源表手机卡片 |
| `app/static/index.html` `app/static/sw.js` | `app.js?v=` / `style.css?v=` / `dav-shell-vN` +1 |
| `tests/test_frontend_interactions.py` | 页面契约、tab 列表、Cookie 深链、缓存号 |

不做：改 `/api/stats` 形状、全量大V健康表、把 Cookie 编辑/代理/抓取数字塞进全景、30 秒重建趋势和 KPI、动 Unraid、发版（发版另走 vpush-release-deploy）。

---

## 产品切法（实施时不要走样）

**全景概览（`/admin` = `/admin/dashboard`）从上到下：**

1. Cookie 告警条（有才出现）→ 按钮 `go('admin/stats?tab=cookies')`
2. 核心指标 + 14 天趋势 + 帖子来源 / 渠道成功率（已有，保留）
3. 值班活块：一行抓取元信息（最近抓取、耗时、轮询间隔、待重试）+ 完整平台表 + 最近异常事件（只 fail/warn，最多 8 条）
4. 停更名单：启用中、从未抓到或 `last_post_at` 早于 48 小时的大V，最多 10 行，点名字进大V管理并带上搜索词

**数据源（`/admin/stats`）四个 tab，顺序：**

抓取设置（默认，`/admin/stats` 无 query）→ Cookie 管理 → 代理 → 广场显示

**反目标：** 平台表出现两次；全景贴全量大V表；数据源页还留「看状态」tab。

---

### Task 1: 先写会失败的前端契约

**Files:**
- Modify: `tests/test_frontend_interactions.py`

现有会立刻被这次改动打到的断言（改代码前先改测试，让它们表达新契约）：

- `test_plaza_source_visibility_admin_and_pills` 里的 `STATS_TABS = ["overview", "health", "plaza", "config", "cookies", "proxies"]`
- `test_stats_tabs_expose_tab_aria` 里的 `id="tab-overview"`
- `test_stats_cookie_repair_deep_link` 里 banner 的 `switchStatsTab('cookies')`

- [ ] **Step 1: 改旧断言 + 追加新测试**

把 `STATS_TABS` 期望改成：

```python
assert 'STATS_TABS = ["config", "cookies", "proxies", "plaza"]' in src
```

`test_stats_tabs_expose_tab_aria` 改成默认选中抓取设置：

```python
assert 'role="tab" id="tab-config" aria-selected="true" aria-controls="st-config"' in src
assert 'id="tab-overview"' not in src
assert 'id="tab-health"' not in src
```

`test_stats_cookie_repair_deep_link` 的 banner 断言改成：

```python
banner = _fn_body("cookieRepairBanner")
assert "go('admin/stats?tab=cookies')" in banner
assert "switchStatsTab('cookies')" not in banner
```

在同一文件追加：

```python
def test_stats_tabs_are_config_workshop_only():
    """数据源页只改管线，不再承担监控总览 / 大V健康。"""
    src = APP_JS.read_text()
    load = _fn_body("loadAdminStats")
    assert "监控总览" not in load
    assert "大V健康" not in load
    assert "大V抓取健康" not in load
    assert 'id="st-overview"' not in load
    assert 'id="st-health"' not in load
    assert 'id="sources-table"' not in load
    assert 'id="kol-health"' not in load
    assert "statsTimer" not in load
    assert "setInterval" not in load
    assert 'data-tab="config"' in load
    assert 'data-tab="cookies"' in load
    assert 'data-tab="proxies"' in load
    assert 'data-tab="plaza"' in load
    hash_fn = _fn_body("statsTabFromHash")
    assert 'tab === "overview"' in hash_fn or '"overview"' in hash_fn
    assert '"health"' in hash_fn
    assert 'replaceRoute("admin/dashboard")' in hash_fn or 'go("admin/dashboard")' in load


def test_dashboard_is_duty_console():
    """全景一屏：量、管线、停更；平台表只出现一次。"""
    dash = _fn_body("loadAdminDashboard")
    live = _fn_body("renderStatsData")
    src = APP_JS.read_text()
    assert "核心指标" in dash
    assert "近 14 天推送趋势" in dash
    assert "数据源健康" in dash
    assert "停更" in dash or "kol-health" in dash
    assert dash.count("数据源健康") == 1
    assert 'id="sources-table"' in dash
    assert "ok_24h" in live
    assert "fail_24h" in live
    assert "consecutive_fails" in live
    assert "next_retry_at" in live
    assert "staleEnabledKols" in src
    assert "openAdminKolFromHealth" in src
    assert "startDashboardLiveTimer" in src or "statsTimer = setInterval" in dash
    assert "cookieRepairBanner" in dash or "cookieRepairBanner" in live


def test_stale_kols_are_exceptions_not_inventory():
    """停更名单：只启用、从未抓到或超过 48h、最多 10 个。"""
    body = _fn_body("staleEnabledKols")
    assert "enabled" in body
    assert "48" in body
    assert "10" in body
    open_fn = _fn_body("openAdminKolFromHealth")
    assert "adminKolsQ" in open_fn
    assert "admin/kols" in open_fn


def test_dashboard_live_refresh_does_not_rebuild_trends():
    """30 秒只打 /api/stats 补活块，不重拉 dashboard、不重建趋势。"""
    src = APP_JS.read_text()
    assert "function stopStatsTimer" in src
    timer = _fn_body("startDashboardLiveTimer") if "function startDashboardLiveTimer" in src else _fn_body("loadAdminDashboard")
    assert "/api/stats" in timer
    assert "/api/admin/dashboard" not in timer or timer.count("/api/admin/dashboard") == 0
    assert "renderStatsData" in timer
    assert "30000" in timer
```

`switchStatsTab` 里无 query 的默认 tab 从 `overview` 改成 `config`（实现时同步，本测试在 Task 3 才会绿）。先在 `test_stats_cookie_repair_deep_link` 旁加：

```python
def test_stats_default_tab_is_config():
    switch = _fn_body("switchStatsTab")
    assert 'name === "config" ? "/admin/stats"' in switch
    hash_fn = _fn_body("statsTabFromHash")
    assert 'routeQuery().get("tab") || "config"' in hash_fn
```

- [ ] **Step 2: 跑测试确认失败**

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k "stats_tabs or stats_cookie or stats_default or dashboard_is_duty or stale_kols or dashboard_live or plaza_source_visibility"
```

Expected: 新测试 FAIL（找不到函数 / 旧 tab 还在）；改过的旧测试 FAIL。

- [ ] **Step 3: Commit 测试契约**

```bash
git add tests/test_frontend_interactions.py
git commit -m "test: lock duty-dashboard contracts before the merge"
```

（若本仓库习惯一次功能一个提交，可把本 step 留到最后一起 commit。）

---

### Task 2: 抽出活块辅助函数

**Files:**
- Modify: `app/static/app.js`（`cookieRepairBanner` 附近、`renderStatsData` 之前）

- [ ] **Step 1: Cookie 条离开数据源页也能跳**

`cookieRepairBanner` 的按钮从 `switchStatsTab('cookies')` 改成路由跳转（全景 DOM 里没有那些 tab）：

```javascript
function cookieRepairBanner(s) {
  const items = cookieRepairItems(s);
  if (!items.length) return "";
  return `<div class="notice notice-warn" role="status">
    <div class="notice-warn-body">
      <strong>Cookie 需要更新</strong>
      <p>${items.map((i) => escapeHtml(i.label)).join("；")}。保存后即时生效，不用改配置文件、不用重启。</p>
    </div>
    <button type="button" class="btn-normal" onclick="go('admin/stats?tab=cookies')">去更新</button>
  </div>`;
}
```

- [ ] **Step 2: 停更筛选 + 进大V管理**

放在 `renderStatsData` 之前。`last_post_at` 是 SQLite UTC `YYYY-MM-DD HH:MM:SS`，解析方式与 `fmtDbTime` 同一套：

```javascript
const STALE_KOL_LIMIT = 10;
const STALE_KOL_HOURS = 48;

function parseDbUtc(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(String(s || ""));
  if (!m) return null;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
}

function staleEnabledKols(rows, nowMs) {
  const cutoff = (nowMs || Date.now()) - STALE_KOL_HOURS * 3600 * 1000;
  const live = (rows || []).filter((k) => k.enabled);
  const stale = live.filter((k) => {
    if (!k.last_post_at) return true;
    const ts = parseDbUtc(k.last_post_at);
    return ts == null || ts < cutoff;
  });
  stale.sort((a, b) => String(a.last_post_at || "").localeCompare(String(b.last_post_at || "")));
  return stale.slice(0, STALE_KOL_LIMIT);
}

function openAdminKolFromHealth(name) {
  state.adminKolsQ = String(name || "").trim();
  state.adminKolsPage = 0;
  go("admin/kols");
}
```

- [ ] **Step 3: 平台表 / 异常事件 / 元信息 HTML**

从现有 `renderStatsData` 的表格字符串抽出来，全景和 30 秒刷新共用。列用监控总览那套，不要全景现在缺列的瘦表：

```javascript
function sourceStatusCell(src) {
  if (src.ok) return '<td class="status-ok">正常</td>';
  const text = src.consecutive_fails >= 3 ? "持续失败" : "无成功记录";
  return `<td class="status-fail">${text}</td>`;
}

function sourceChannelCell(src) {
  if (src.platform !== "twitter") return '<td class="muted">—</td>';
  if (src.direct_mode === "direct") return '<td><span class="status-ok">直抓</span></td>';
  if (src.direct_mode === "fallback") {
    return `<td><span class="status-warn" title="${escapeHtml(src.direct_fallback_reason || "")}">直抓失败</span></td>`;
  }
  return '<td class="muted">—</td>';
}

function sourceRowsHtml(sources) {
  const rows = sources || [];
  if (!rows.length) return '<tr class="ak-empty"><td colspan="9" class="muted">暂无数据源</td></tr>';
  return rows.map((src) => `
    <tr>
      <td data-label="平台">${PLATFORM_LABELS[src.platform] || escapeHtml(src.platform)}</td>
      ${sourceStatusCell(src)}
      ${sourceChannelCell(src)}
      <td data-label="24h 成功率">${rateBar(src.success_rate_24h)}</td>
      <td data-label="成功 / 失败">${src.ok_24h} / ${src.fail_24h}${src.warn_24h ? ` <span class="status-warn">⚠${src.warn_24h}</span>` : ""}</td>
      <td data-label="连续失败" class="${src.consecutive_fails >= 3 ? "status-fail" : ""}">${src.consecutive_fails}</td>
      <td class="ak-hide-mobile" data-label="最近成功">${fmtTs(src.last_ok_at)}</td>
      <td class="ak-hide-mobile" data-label="下次重试">${src.next_retry_at ? fmtTs(src.next_retry_at) : "—"}</td>
      <td class="muted" data-label="最近错误" title="${escapeHtml(src.last_error || "")}">${src.last_error ? escapeHtml(src.last_error.slice(0, 40)) : "—"}</td>
    </tr>`).join("");
}

function abnormalSourceEvents(events, limit) {
  return (events || []).filter((e) => e.status !== "ok").slice(0, limit || 8);
}

function sourceEventRowsHtml(events) {
  const rows = abnormalSourceEvents(events);
  if (!rows.length) return `<p class="muted">近 24 小时无异常事件</p>`;
  return `<div class="dash-events">${rows.map((e) => `<div class="dash-event">
    <span class="dash-event-dot ${escapeHtml(e.status)}"></span>
    <span class="muted dash-event-time">${escapeHtml(fmtDbTime(e.created_at))}</span>
    <span class="dash-event-platform">${PLATFORM_LABELS[e.platform] || escapeHtml(e.platform)}</span>
    <span class="${e.status === "warn" ? "status-warn" : "status-fail"}">${e.status === "warn" ? "警告" : "失败"}</span>
    <span class="muted dash-event-detail" title="${escapeHtml(e.detail || "")}">${escapeHtml(e.detail || "")}</span>
  </div>`).join("")}</div>`;
}

function dashboardFetchMetaHtml(s) {
  const retry = s.retry_pending
    ? `<span class="status-warn">待重试 ${s.retry_pending} 条</span>`
    : `<span class="status-ok">重试队列空闲</span>`;
  const dur = s.last_poll_duration_ms ? `${(Number(s.last_poll_duration_ms) / 1000).toFixed(1)} 秒` : "—";
  const alerts = s.alerts || {};
  const chips = [];
  if (alerts.push_alert_last_at) chips.push(`推送告警 ${fmtTs(alerts.push_alert_last_at)}`);
  if (alerts.x_direct_alert_at) chips.push(`X失败告警 ${fmtTs(alerts.x_direct_alert_at)}`);
  if (alerts.cookie_keepalive_alert_at) chips.push(`cookie保活告警 ${fmtTs(alerts.cookie_keepalive_alert_at)}`);
  if (alerts.xueqiu_probe_alert_at) chips.push(`雪球探测告警 ${fmtTs(alerts.xueqiu_probe_alert_at)}`);
  return `<p class="section-meta dash-fetch-meta" id="dash-fetch-meta">
    最近抓取 ${fmtTs(s.last_poll_at)} · 耗时 ${dur} · 轮询 ${s.polling_interval_seconds || "—"} 秒 · ${retry}${chips.length ? ` · ${chips.map((c) => escapeHtml(c)).join(" · ")}` : ""}
  </p>`;
}

function staleKolsHtml(rows) {
  const stale = staleEnabledKols(rows);
  if (!stale.length) {
    return `<p class="muted" id="kol-health-empty">启用中的大V 在 ${STALE_KOL_HOURS} 小时内都抓到过新帖</p>`;
  }
  return `<div class="table-wrap"><table class="ak-table dash-stale-table">
    <thead><tr><th scope="col">大V</th><th scope="col">平台</th><th scope="col">最近抓到新帖</th></tr></thead>
    <tbody>${stale.map((h) => `
      <tr>
        <td data-label="大V"><button type="button" class="linkish" onclick="openAdminKolFromHealth(${JSON.stringify(h.name)})">${escapeHtml(h.name)}</button></td>
        <td data-label="平台">${PLATFORM_LABELS[h.platform] || escapeHtml(h.platform)}</td>
        <td class="muted" data-label="最近抓到新帖">${h.last_post_at ? escapeHtml(fmtDbTime(h.last_post_at)) : "从未抓到"}</td>
      </tr>`).join("")}</tbody>
  </table></div>`;
}
```

`openAdminKolFromHealth` 的参数必须走 `JSON.stringify(h.name)`（或 `escapeHtml` 后再进 JS 字符串），禁止 `onclick="...${h.name}"` 裸插值，否则 `test_event_handlers_do_not_interpolate_user_data` 会红。

- [ ] **Step 4: `renderStatsData` 改成按 ID 补丁**

保留「元素不在 DOM 就跳过」。删掉对 `#stats-cards` 那 8 张运维卡片的写入（轮询间隔/大V数等不再占一排 KPI）。活块 ID：

| ID | 内容 |
|---|---|
| `#dash-cookie-slot` | `cookieRepairBanner(s)` |
| `#cookie-repair-inline` | 数据源 Cookie tab 里同一条（已有） |
| `#dash-fetch-meta` | `dashboardFetchMetaHtml` 的 innerHTML |
| `#stats-poll-error` | `last_poll_error` |
| `#sources-table` | `sourceRowsHtml` |
| `#dash-source-events` | `sourceEventRowsHtml` |
| `#kol-health` | `staleKolsHtml` |

广场 / IMA 状态那几段 `if (#plaza-sources)` 原样留着。

轮询异常：

```javascript
const pollErr = $("#stats-poll-error");
if (pollErr) {
  pollErr.innerHTML = s.last_poll_error
    ? `<div class="notice">最近轮询异常：${escapeHtml(s.last_poll_error)}</div>`
    : "";
}
```

- [ ] **Step 5: 活块定时器搬到全景**

`loadAdminStats` 末尾的 `setInterval` 删掉。新增：

```javascript
function startDashboardLiveTimer() {
  stopStatsTimer();
  statsTimer = setInterval(async () => {
    try {
      const fresh = await api("/api/stats");
      renderStatsData(fresh);
    } catch {
      /* 后台刷新失败不打扰 */
    }
  }, 30000);
}
```

`router()` 里已有 `stopStatsTimer()`，离开全景会停。不要在数据源页再开定时器——Cookie 输入框不能被 30 秒整页重绘。

---

### Task 3: 全景改值班布局，数据源去掉两个看状态 tab

**Files:**
- Modify: `app/static/app.js`（`STATS_TABS`、`statsTabFromHash`、`switchStatsTab`、`loadAdminStats`、`loadAdminDashboard`）

- [ ] **Step 1: tab 常量与深链**

```javascript
const STATS_TABS = ["config", "cookies", "proxies", "plaza"];
```

```javascript
function statsTabFromHash() {
  const tab = routeQuery().get("tab") || "config";
  if (tab === "overview" || tab === "health") return "legacy-dashboard";
  return STATS_TABS.includes(tab) ? tab : "config";
}

function switchStatsTab(name) {
  if (name === "legacy-dashboard" || name === "overview" || name === "health") {
    replaceRoute("admin/dashboard");
    return;
  }
  if (!STATS_TABS.includes(name)) name = "config";
  // …现有 aria / hidden 逻辑不变…
  const next = name === "config" ? "/admin/stats" : `/admin/stats?tab=${name}`;
  if (location.pathname + location.search !== next) history.replaceState(null, "", next);
  document.getElementById(`tab-${name}`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  if (name === "proxies") loadProxyAdmin();
}
```

`loadAdminStats` 开头：

```javascript
async function loadAdminStats() {
  stopStatsTimer();
  const tab = statsTabFromHash();
  if (tab === "legacy-dashboard") {
    replaceRoute("admin/dashboard");
    return;
  }
  const s = await api("/api/stats");
  // …
}
```

- [ ] **Step 2: 删掉 `loadAdminStats` 里 overview / health 整块 HTML**

`settings-tabs` 只留四个按钮，**默认 `tab-config` `aria-selected="true"`**，其余 `false`。面板顺序：`st-config` 可见，`st-cookies` / `st-proxies` / `st-plaza` `display:none`。

删掉：

- `#st-overview`（数据源稳定性表、`#stats-cards`、`#sources-table`、数据源事件表）
- `#st-health`（`#kol-health` 全量表）
- 末尾 `statsTimer = setInterval(...)`

保留：抓取设置、IMA、Cookie、代理、广场。`renderStatsData(s); switchStatsTab(statsTabFromHash());` 仍要调用（补 Cookie 条、广场、IMA 状态）。

- [ ] **Step 3: 重写 `loadAdminDashboard` 骨架**

KPI / 趋势 / 来源分布 / 渠道成功率保留。删掉现在那张 6 列「数据源健康」瘦表和 6 条含成功事件的 `dash-event`。改成：

```javascript
async function loadAdminDashboard() {
  try {
    const [d, st] = await Promise.all([api("/api/admin/dashboard"), api("/api/stats")]);
    // …现有 u/s/p/pu、trendHtml、platformRows、channelRows 计算不变…
    if (!routeStillActive(_adminRenderSeq)) return;
    $("#admin-body").innerHTML = `
      <div id="dash-cookie-slot"></div>
      <section class="section-panel">
        <header class="section-head"><div><h2 class="section-title">核心指标</h2>
        <p class="section-meta">用户、订阅与推送的业务总览（推送统计为近 7 天）。</p></div></header>
        <div class="dash-stats">
          ${statCard("注册用户", u.total || 0)}
          ${statCard("绑定渠道用户", u.bound || 0)}
          ${statCard("订阅数", s.total || 0)}
          ${statCard("近 7 天推送", pu.total_7d || 0)}
          ${statCard("推送成功率", rate)}
          ${statCard("帖子总量", p.total || 0)}
        </div>
      </section>
      <section class="section-panel">
        <header class="section-head"><div><h2 class="section-title">近 14 天推送趋势</h2>
        <p class="section-meta">每日推送条数（绿色=成功，红色=失败）。</p></div></header>
        ${trendHtml}
      </section>
      <div class="dash-split">
        <section class="section-panel">
          <header class="section-head"><div><h2 class="section-title">帖子来源分布</h2>
          <p class="section-meta">累计抓取帖子按平台。</p></div></header>
          ${platformRows || `<p class="muted">暂无帖子</p>`}
        </section>
        <section class="section-panel">
          <header class="section-head"><div><h2 class="section-title">渠道推送成功率（7 天）</h2>
          <p class="section-meta">各渠道成功/总数与成功率。</p></div></header>
          ${channelRows || `<p class="muted">近 7 天暂无推送</p>`}
        </section>
      </div>
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">数据源健康</h2>
          ${dashboardFetchMetaHtml(st)}</div>
          <div class="toolbar"><button type="button" class="btn-ghost" onclick="refreshDashboardLive()">立即刷新</button></div>
        </header>
        <div id="stats-poll-error"></div>
        <div class="table-wrap">
          <table class="ak-table dash-source-table">
            <thead><tr>
              <th scope="col">平台</th><th scope="col">状态</th><th scope="col">通道</th>
              <th scope="col">24h 成功率</th><th scope="col">成功 / 失败</th>
              <th scope="col">连续失败</th><th scope="col">最近成功</th>
              <th scope="col">下次重试</th><th scope="col">最近错误</th>
            </tr></thead>
            <tbody id="sources-table"></tbody>
          </table>
        </div>
        <div id="dash-source-events"></div>
      </section>
      <section class="section-panel">
        <header class="section-head"><div><h2 class="section-title">停更大V</h2>
        <p class="section-meta">启用中、超过 ${STALE_KOL_HOURS} 小时没抓到新帖或从未抓到。点名字进大V管理。</p></div></header>
        <div id="kol-health"></div>
      </section>`;
    renderStatsData(st);
    startDashboardLiveTimer();
  } catch (err) {
    if (!routeStillActive(_adminRenderSeq)) return;
    $("#admin-body").innerHTML = emptyState("加载失败: " + err.message,
      `<div><button class="btn-normal" onclick="loadAdminDashboard()">重试</button></div>`);
  }
}

async function refreshDashboardLive() {
  try {
    const st = await api("/api/stats");
    renderStatsData(st);
  } catch (err) {
    flash("刷新失败: " + err.message, "error");
  }
}
```

`test_dashboard_live_refresh_does_not_rebuild_trends` 若绑在 `startDashboardLiveTimer` 上，把 30 秒逻辑只放进这个函数，不要写进 `loadAdminDashboard` 函数体。

知识库空态的 `go('admin/stats?tab=config')` 不用改。

- [ ] **Step 4: 跑 Task 1 那组测试**

```bash
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py -k "stats_tabs or stats_cookie or stats_default or dashboard_is_duty or stale_kols or dashboard_live or plaza_source_visibility or cookie_clear or cookie_save"
```

Expected: PASS。`cookie_clear` / `cookie_save` 仍从 `loadAdminStats` 找 Cookie 控件，不得误删。

---

### Task 4: 样式（值班密度 + 手机表）

**Files:**
- Modify: `app/static/style.css`（`.dash-stats` 一段附近，约 2370+）

- [ ] **Step 1: 补值班用 class，沿用现有 token**

```css
.dash-fetch-meta { margin-top: 4px; }
.dash-source-table { width: 100%; }
button.linkish {
  border: none;
  background: none;
  padding: 0;
  color: var(--color-accent-text);
  font: inherit;
  cursor: pointer;
  text-align: left;
}
button.linkish:hover { text-decoration: underline; }
```

手机：`dash-source-table` / `dash-stale-table` 走已有 `.ak-table` 卡片约定（`data-label` + `thead display:none`）。若 `@media (max-width: 768px)` 里 `.ak-table` 选择器已经覆盖，不要再复制一套。只把「最近成功 / 下次重试」用 `ak-hide-mobile` 藏掉（HTML 已加）。

不要给休息态卡片加阴影，不要第二套强调色。

- [ ] **Step 2: 缓存号 +1**

当前（写计划时）是 `style.css?v=205`、`app.js?v=288`、`dav-shell-v157`。实施时读 `tests/test_frontend_interactions.py::test_frontend_asset_urls_bust_browser_cache` 的现值为准，各 +1，三处一起改：`index.html`、`sw.js`、该测试。

---

### Task 5: 全量回归与手测

**Files:** 无新文件

- [ ] **Step 1: 相关静态测试 + 全量**

```bash
node --check app/static/app.js
.venv/bin/python -m pytest -q tests/test_frontend_interactions.py tests/test_frontend_xss.py tests/test_api.py -k "stats or dashboard or cookie or plaza or kol_health"
.venv/bin/python -m pytest -q
```

Expected: `node --check` 静默成功；`kol_health` API 测试仍 PASS（载荷不变）；全量绿。

- [ ] **Step 2: 浏览器手测（`DAV_UI_ONLY=1`，不要碰生产 Cookie）**

1. `/admin`：有核心指标和趋势；只有一张数据源表；停更区不是全目录。
2. 空提交/无 Cookie 时告警条「去更新」落到 `/admin/stats?tab=cookies`，输入框还在。
3. `/admin/stats` 默认抓取设置，没有监控总览 / 大V健康。
4. `/admin/stats?tab=overview` 和 `?tab=health` 回到全景。
5. 点停更名字 → `/admin/kols` 搜索框是该昵称。
6. 桌面 + 390px：平台表可扫，不要横向撑破。
7. 停在全景 30 秒以上，趋势数字不变、活块时间戳会变（或点「立即刷新」）。
8. 数据源 Cookie tab 停 30 秒，输入内容不被清掉。

- [ ] **Step 3: Commit**

```bash
git add app/static/app.js app/static/style.css app/static/index.html app/static/sw.js tests/test_frontend_interactions.py
git commit -m "$(cat <<'EOF'
feat: 把数据源监控收进全景值班台

监控总览和大V健康不再占数据源 tab；全景一屏看量、管线和停更，数据源只留配置。
EOF
)"
```

发到 vpush.net 等用户明确说发布，再走 `.cursor/skills/vpush-release-deploy/SKILL.md`。

---

## 风险

- **次要大V本来就几天一帖**：48 小时阈值会让它们常驻停更名单。这是值班例外，不是故障。若手测噪音太大，把 `STALE_KOL_HOURS` 改成 72，不要改回全量表。
- **`renderStatsData` 仍被 Cookie 保存后的 `loadAdminStats()` 调用**：元素缺失必须 no-op，不能假设 `#sources-table` 一定存在。
- **XSS：** 停更名单的 `onclick` 禁止拼接未转义昵称。

## 覆盖核对

| 约定 | 任务 |
|---|---|
| 量：KPI + 趋势 + 渠道 | Task 3 保留 |
| 管线：完整平台表 + 异常事件 + Cookie 条 | Task 2–3 |
| 停更：最多 10 条例外 | Task 2 `staleEnabledKols` |
| 数据源只留配置四 tab | Task 3 |
| 旧 overview/health 深链 | Task 3 `statsTabFromHash` |
| 30 秒不重建趋势 | Task 2 `startDashboardLiveTimer` |
| Cookie 条从全景能跳进管理 | Task 2 `go('admin/stats?tab=cookies')` |
| 不改 API | 全文未改 `app/api.py` |
