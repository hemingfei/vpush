// MX 大V预估持仓——两种宿主共用一套渲染：
// ① 独立页 /mx-kol/{id}；② /mx-views 大V头像旁「持仓」按钮弹出的右侧抽屉。
// 顶部当前持仓汇总（权重条），下方操作时间线（建仓/加仓/减仓/清仓/翻空减仓/持仓表态）。
// 视觉与持股研判页同一套 .hd- token（holdings.css），样式全部 .mxc- 前缀；
// 抽屉外壳自带 .hd-root 变量作用域，挂进 #mxv-drawer-slot（与智囊团抽屉同位，同一时刻只留一个）
export function createMxKolHoldingsView(dependencies) {
  const {
    $, state, api, escapeHtml, setPageTitle, go, routeStillActive, emptyState, flash,
    closeViewsDrawer,
  } = dependencies;

  const _mxc = { seq: 0, data: null, pnl: null, days: 30, view: "all", recent: 3, sort: "weight",
    kolId: 0, drawerEl: null, drawerBody: null, token: 0, closedExpanded: false, actsOpen: {} };
  // 已了结列表默认只露前 5 条：窗口拉长后清仓票会累积一大串，
  // 挤压在持浮动；超出部分折叠进「更多」，点击展开全部
  const MXC_CLOSED_LIMIT = 5;
  const MXC_VIEWS = { all: "全部", open: "建仓", add: "加仓", trim: "减仓", clear: "清仓" };
  // 最近观点天数筛选：只看最近 N 天内还被大V提及的在持标的（0=不筛选）。
  // 部分票太老、没识别出清仓但大V其实早清了——限近期提及至少保证展示的票基本还在仓
  const MXC_RECENT_KEY = "mxc_recent_days";
  // 持仓排序：weight=按仓位权重（后端默认序），time=按最近观点时间最新在前
  const MXC_SORT_KEY = "mxc_sort";

  // 操作事件 → 徽章文案与色彩语义；文案不带买卖前缀（方向由颜色承担：
  // A股口径红=买、绿=卖），与筛选按钮 MXC_VIEWS 的短文案同口径
  const MXC_KINDS = {
    open: { label: "建仓", cls: "buy" },
    add: { label: "加仓", cls: "buy" },
    trim: { label: "减仓", cls: "sell" },
    clear: { label: "清仓", cls: "sell" },
    flip: { label: "翻空减仓", cls: "sell" },
    hold: { label: "持仓", cls: "hold" },
  };

  function mxcTeardown() {
    Object.assign(_mxc, { data: null, pnl: null, view: "all", drawerEl: null, drawerBody: null, actsOpen: {} });
    // closedExpanded 不重置：换大V/换窗口回来时保持用户上次的展开选择
    // recent（最近观点天数）跨路由保留：回来时还是用户上次调的口径；
    // days 不保留——每个大V/宿主入口都按默认 30 天开（按钮 title 的承诺）
  }

  // 竞态守卫：token 拦截同宿主内的旧响应（快速换天数/换大V重开）；
  // 抽屉宿主看 DOM 连通性（路由切换由 mxvTeardown 摘除节点），页面宿主沿用路由 seq
  function mxcStale(token, seq) {
    if (token !== _mxc.token) return true;
    if (_mxc.drawerEl) return !_mxc.drawerEl.isConnected;
    return seq != null && !routeStillActive(seq);
  }

  // 统一取数+落盘：初次加载失败出整屏错误；换窗口失败只 flash 并回显旧数据。
  // 持仓与盈亏并行拉取、各自落盘：盈亏链路带行情查询可能慢/失败，
  // 不能让它阻塞持仓渲染（渐进展示，谁先到谁先画）。盈亏后到时补刷一次
  // 汇总——持仓行内嵌的浮动盈亏徽章吃 pnl 数据，不刷会一直缺席
  async function mxcLoad(kolId, token, seq) {
    const pnlPromise = api(`/api/kols/${kolId}/mx-pnl?days=${_mxc.days}`)
      .then((pnl) => {
        if (!mxcStale(token, seq)) { _mxc.pnl = pnl; mxcRenderPnl(); mxcRenderSummary(); }
      })
      .catch(() => { if (!mxcStale(token, seq)) { _mxc.pnl = null; mxcRenderPnl(); } });
    try {
      const data = await api(`/api/kols/${kolId}/mx-holdings?days=${_mxc.days}`);
      if (mxcStale(token, seq)) return;
      _mxc.data = data;
      _mxc.kolId = kolId;
      mxcRenderAll();
    } catch (err) {
      if (mxcStale(token, seq)) return;
      if (!_mxc.data) {
        mxcRenderError(err);
        return;
      }
      flash(`刷新失败: ${err.message}`, "error");
      mxcRenderAll();
    } finally {
      await pnlPromise;  // 竞态守卫兜底：面板渲染完才允许本次 token 结束
    }
  }

  function mxcRenderError(err) {
    if (_mxc.drawerEl) {
      if (_mxc.drawerBody) _mxc.drawerBody.innerHTML =
        `<div class="mxv-empty">加载失败: ${escapeHtml(err.message)}</div>`;
      return;
    }
    $("#main").innerHTML = `<div class="mxc-root hd-root"><div class="mxv-empty">加载失败: ${escapeHtml(err.message)}</div></div>`;
  }

  // 挂载时恢复本地口径：最近观点天数 + 排序方式（都只影响前端展示，不过服务端）
  function mxcLoadPrefs() {
    try {
      // 从未存过（null）或存成空串都不覆盖默认：Number(null/""())=0 会把默认天数顶成「0=不筛选」
      const raw = localStorage.getItem(MXC_RECENT_KEY);
      if (raw != null && raw !== "") {
        const v = Number(raw);
        if (Number.isInteger(v) && v >= 0 && v <= 20) _mxc.recent = v;
      }
      const s = localStorage.getItem(MXC_SORT_KEY);
      if (s === "weight" || s === "time") _mxc.sort = s;
    } catch (e) { /* 存储不可用：用默认值 */ }
  }

  function mxcSaveRecent() {
    try { localStorage.setItem(MXC_RECENT_KEY, String(_mxc.recent)); } catch (e) { /* 本页生效即可 */ }
  }

  function mxcSaveSort() {
    try { localStorage.setItem(MXC_SORT_KEY, _mxc.sort); } catch (e) { /* 本页生效即可 */ }
  }

  // last_day（YYYY-MM-DD）距今是否超过 n 天（北京时区口径，与后端交易日对齐）
  function mxcRecentCutoff(n) {
    const bj = new Date(Date.now() + (480 + new Date().getTimezoneOffset()) * 60000);
    bj.setDate(bj.getDate() - n);
    const p = (x) => String(x).padStart(2, "0");
    return `${bj.getFullYear()}-${p(bj.getMonth() + 1)}-${p(bj.getDate())}`;
  }

  async function renderMxKolHoldings(kolId, seq) {
    mxcTeardown(); // 页面宿主接管：清掉抽屉宿主残留引用（其 DOM 已由路由 teardown 移除）
    _mxc.seq = seq;
    _mxc.kolId = kolId;
    _mxc.days = 30; // 换大V/重新进页：天窗回默认，不带上一个大V的残留口径
    mxcLoadPrefs();
    setPageTitle("预估持仓");
    $("#main").innerHTML = `<div class="mxc-root hd-root"><div class="mxv-empty">加载中…</div></div>`;
    await mxcLoad(kolId, ++_mxc.token, seq);
  }

  // 右侧持仓抽屉：/mx-views 大V卡片头像旁/大V抽屉头部的「持仓」按钮打开。
  // 从大V抽屉进入时先收起原抽屉（同一时刻只留一个）；抽屉数据按天窗实时取，不随快照刷新
  function mxcOpenDrawer(kolId) {
    kolId = Number(kolId);
    if (!Number.isInteger(kolId) || kolId <= 0) return;
    if (typeof closeViewsDrawer === "function") closeViewsDrawer();
    mxcTeardown();
    const slot = document.getElementById("mxv-drawer-slot") || $("#main");
    if (!slot) return;
    _mxc.kolId = kolId;
    _mxc.days = 30; // 每个大V的抽屉入口都承诺近 30 天：不带其他大V/页面的残留口径
    mxcLoadPrefs();
    const shell = document.createElement("div");
    shell.innerHTML = `
      <div class="mxc-drawer-mask" onclick="mxcCloseDrawer()"></div>
      <aside class="mxc-drawer hd-root" role="dialog" aria-label="预估持仓">
        <div class="mxc-drawer-top">
          <b>预估持仓</b>
          <button type="button" class="full" onclick="go('/mx-kol/${kolId}')" title="打开独立持仓页">完整页</button>
          <button type="button" class="close" onclick="mxcCloseDrawer()" aria-label="关闭">✕</button>
        </div>
        <div class="mxc-root mxc-drawer-body"><div class="mxv-empty">加载中…</div></div>
      </aside>`;
    const mask = shell.querySelector(".mxc-drawer-mask");
    const aside = shell.querySelector(".mxc-drawer");
    _mxc.drawerEl = aside;
    _mxc.drawerBody = aside.querySelector(".mxc-drawer-body");
    slot.appendChild(mask);
    slot.appendChild(aside);
    mxcLoad(kolId, ++_mxc.token, null);
  }

  function mxcCloseDrawer() {
    const mask = document.querySelector(".mxc-drawer-mask");
    const drawer = document.querySelector(".mxc-drawer");
    if (mask) mask.remove();
    if (drawer) drawer.remove();
    mxcTeardown();
  }

  async function mxcChangeDays(days) {
    _mxc.days = days;
    const seq = _mxc.drawerEl ? null : _mxc.seq;
    const feed = document.getElementById("mxc-timeline");
    if (feed) feed.innerHTML = `<div class="mxv-empty">加载中…</div>`;
    await mxcLoad(_mxc.kolId, ++_mxc.token, seq);
  }

  function mxcRenderAll() {
    const d = _mxc.data;
    if (!d) return;
    if (_mxc.drawerEl) {
      if (!_mxc.drawerEl.isConnected || !_mxc.drawerBody) return;
      _mxc.drawerBody.innerHTML = mxcInnerHtml(d);
    } else {
      $("#main").innerHTML = `<div class="mxc-root hd-root">${mxcInnerHtml(d)}</div>`;
    }
    mxcRenderSummary();
    mxcRenderPnl();
    mxcRenderTimeline();
  }

  // 页面/抽屉共用主体：页头（抽屉宿主不出「‹ 动态」返回钮，关闭走外壳 ✕）+ 汇总 + 盈亏 + 时间线
  function mxcInnerHtml(d) {
    const kol = d.kol || {};
    return `
      <section class="mxc-head">
        ${_mxc.drawerEl ? "" : `<button type="button" class="hd-btn sm" onclick="go('/kol/${Number(kol.kol_id || 0)}')" aria-label="返回大V动态">‹ 动态</button>`}
        ${kol.avatar ? `<img class="mxc-ava" src="${escapeHtml(kol.avatar)}" alt="" loading="lazy"
          onerror="this.style.display='none'">` : ""}
        <div class="mxc-head-main">
          <h2>${escapeHtml(kol.name || "")}</h2>
          <span class="mxc-sub">预估持仓 · 近 ${d.window_days} 天观点回放 · 生成于 ${escapeHtml(d.generated_at || "")}</span>
        </div>
        <span class="mxc-days">
          ${[30, 60, 90].map((n) => `<button type="button" class="hd-seg-btn${d.window_days === n ? " on" : ""}"
            onclick="mxcChangeDays(${n})">${n}天</button>`).join("")}
        </span>
      </section>
      <section class="hd-panel" id="mxc-summary"></section>
      <section class="hd-panel" id="mxc-pnl"></section>
      <section class="hd-feed" id="mxc-timeline"></section>`;
  }

  function mxcWeightBar(w) {
    return `<div class="mxc-bar"><div class="fill" style="width:${Math.max(2, Math.min(100, w))}%"></div></div>`;
  }

  // 最近观点天数滑动栏 + 排序切换共用一条控制带。
  // 拖动中（input）只同步数值/提示文案——此处若重绘汇总会连带替换 range 元素自身，
  // 按住拖动即被打断；松手（change）才刷新汇总并持久化
  function mxcRecentHtml() {
    return `
    <div class="mxc-recent">
      <span class="lab">最近观点</span>
      <input type="range" min="0" max="20" step="1" value="${_mxc.recent}"
        id="mxc-recent-range" aria-label="最近观点天数，0 为不筛选"
        oninput="mxcRecentInput(this.value)" onchange="mxcRecentChange(this.value)">
      <span class="val"><b id="mxc-recent-val">${_mxc.recent}</b> 天</span>
      <span class="tip">${mxcRecentTip(_mxc.recent)}</span>
      <span class="hd-seg mxc-sort" role="tablist" aria-label="持仓排序">
        ${[["weight", "按仓位", "按预估仓位权重从高到低"], ["time", "按时间", "按最近观点时间新→旧"]]
          .map(([k, label, tip]) => `<button type="button" title="${tip}"
            class="hd-seg-btn${_mxc.sort === k ? " on" : ""}" onclick="mxcSetSort('${k}')">${label}</button>`).join("")}
      </span>
    </div>`;
  }

  function mxcRecentTip(v) {
    return v ? `仅显示 ${v} 天内被提及的标的` : "不筛选（显示全部在持标的）";
  }

  function mxcRecentInput(value) {
    const v = Math.max(0, Math.min(20, Math.round(Number(value))));
    if (v === _mxc.recent) return;
    _mxc.recent = v;
    mxcRecentText(v);
  }

  // 松手/键盘步进（change）才落地：刷新持仓汇总 + 盈亏面板（两者共用过滤口径）并持久化
  // （拖动全程写存储太密）
  function mxcRecentChange(value) {
    const v = Math.max(0, Math.min(20, Math.round(Number(value))));
    _mxc.recent = v;
    mxcSaveRecent();
    mxcRecentText(v);
    mxcRenderSummary();
    mxcRenderPnl();
  }

  function mxcRecentText(v) {
    const valEl = document.getElementById("mxc-recent-val");
    if (valEl) valEl.textContent = String(v);
    const tipEl = document.querySelector(".mxc-recent .tip");
    if (tipEl) tipEl.textContent = mxcRecentTip(v);
  }

  // 时间线筛选条件共享：最近 N 天内无任何事件的标的不参与持仓汇总
  function mxcFilterByRecent(list) {
    if (!_mxc.recent) return list;
    const cutoff = mxcRecentCutoff(_mxc.recent);
    return (list || []).filter((x) => String(x.last_day || "") >= cutoff);
  }

  // 排序：按仓位=后端权重降序原序；按时间=最近提及（last_at 为 YYYY-MM-DD HH:MM，字典序可比）
  // 新→旧。同刻并列时 sort 稳定，回落到仓位序
  function mxcSortRows(rows) {
    if (_mxc.sort !== "time") return rows;
    return [...(rows || [])].sort((a, b) => String(b.last_at || "").localeCompare(String(a.last_at || "")));
  }

  function mxcSetSort(s) {
    if (_mxc.sort === s) return;
    _mxc.sort = s === "time" ? "time" : "weight";
    mxcSaveSort();
    mxcRenderSummary();
    mxcRenderPnl();
  }

  // 已了结「更多/收起」：只重画盈亏面板（汇总与时间线不受影响）
  function mxcToggleClosed() {
    _mxc.closedExpanded = !_mxc.closedExpanded;
    mxcRenderPnl();
  }

  // 盈亏百分比徽章：A股口径盈=红、亏=绿，0 走中性灰。null/undefined 返回空串
  function mxcPctBadge(pct, title) {
    if (pct == null || !Number.isFinite(Number(pct))) return "";
    const v = Number(pct);
    const cls = v > 0 ? "up" : v < 0 ? "down" : "flat";
    const label = `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
    return `<span class="mxc-pnl-pct ${cls}"${title ? ` title="${escapeHtml(title)}"` : ""}>${label}</span>`;
  }

  function mxcPnlByStock() {
    const map = {};
    (_mxc.pnl && _mxc.pnl.stocks || []).forEach((s) => { map[s.target_name] = s; });
    return map;
  }

  // 盈亏行内操作时间线徽章：后端 actions=[{kind,at}]（早→晚），文案/配色与时间线
  // 徽章同源（MXC_KINDS）。建仓/加仓/减仓/清仓/翻空各带发生时间；长窗口下同一票
  // 可累积几十笔，全铺开会盖过其他票——默认每类只露最近一次（保持时间线原序），
  // 其余折叠进「更多」，展开状态按票名记录（盈亏接口后到补刷时不丢）。
  // 人工标注产生的操作带 manual:true，追加「人工」角标
  function mxcPnlActs(p) {
    const acts = (p && p.actions) || [];
    if (!acts.length) return "";
    const latest = {};
    acts.forEach((a) => {
      if (!latest[a.kind] || String(a.at || "") > String(latest[a.kind].at || "")) latest[a.kind] = a;
    });
    const collapsed = acts.length - acts.filter((a) => latest[a.kind] === a).length;
    const expanded = !!(p.target_name && _mxc.actsOpen[p.target_name]);
    const list = expanded ? acts : acts.filter((a) => latest[a.kind] === a);
    const badges = list.map((a) => {
      const k = MXC_KINDS[a.kind] || MXC_KINDS.hold;
      return `<span class="mxc-kind ${k.cls}" title="${escapeHtml(k.label)} ${escapeHtml((a.at || "").slice(5, 16))}">${k.label} ${(a.at || "").slice(5, 16)}${a.manual ? '<i class="mxc-manual-badge">人工</i>' : ""}</span>`;
    }).join("");
    // 收起态才有「还有 N 笔」；展开后按钮文案换「收起」，计数仍按折叠差额算
    // 票名经 JSON.stringify 后是双引号串，直接嵌双引号 onclick 属性会被截断，
    // 先替换成 &quot;（HTML 解析时还原为 "，JS 收到完整字符串）
    const more = collapsed > 0
      ? `<button type="button" class="mxc-more mxc-acts-more"
          onclick="mxcToggleActs(${JSON.stringify(String(p.target_name || "")).replace(/"/g, "&quot;")})">${expanded ? "收起 ▴" : `更多 ▾（还有 ${collapsed} 笔）`}</button>`
      : "";
    return `<div class="mxc-pnl-acts">${badges}${more}</div>`;
  }

  // 行内操作「更多/收起」：按票名翻转展开态，只重画盈亏面板（汇总与时间线不受影响）
  function mxcToggleActs(name) {
    if (!name) return;
    if (_mxc.actsOpen[name]) delete _mxc.actsOpen[name];
    else _mxc.actsOpen[name] = true;
    mxcRenderPnl();
  }

  // 预估盈亏面板：浮动（在持）+ 已了结分开两列；行情未接入出低调占位。
  // 独立渲染入口——盈亏接口比持仓慢时不等它，谁先到谁先画
  function mxcRenderPnl() {
    const el = document.getElementById("mxc-pnl");
    if (!el) return;
    const pnl = _mxc.pnl;
    if (!pnl || !pnl.available) {
      // 桩阶段/接口失败：单行提示，不占版面不报错（持仓功能照常）
      el.innerHTML = `
        <div class="hd-panel-head"><b>预估盈亏</b>
          <span class="hd-hint">待行情接入</span></div>
        <p class="mxc-pnl-note">行情数据未接入，预估盈亏暂不可用；接入后自动展示每只票的浮动/已了结收益。</p>`;
      return;
    }
    const s = pnl.summary || {};
    // 窗口内无个股操作（空态）：不是行情问题，给中性空态文案
    if (!pnl.stocks || !pnl.stocks.length) {
      el.innerHTML = `
        <div class="hd-panel-head"><b>预估盈亏</b></div>
        <div class="mxv-empty">窗口内无个股操作，暂无盈亏记录。</div>`;
      return;
    }
    const head = `
      <div class="hd-panel-head"><b>预估盈亏</b>
        <span class="hd-hint">${s.holding_count ? `在持 ${s.holding_count}` : ""}${s.closed_count ? ` · 已了结 ${s.closed_count}` : ""}${(s.total_return_pct != null) ? ` · 平均 ${s.total_return_pct > 0 ? "+" : ""}${s.total_return_pct}%` : ""}${(s.winners || s.losers) ? ` · ${s.winners}盈${s.losers}亏` : ""}</span></div>`;
    const byName = mxcPnlByStock();
    const cov = (s.coverage != null && s.coverage < 1)
      ? `<span class="hd-hint" title="部分操作事件未取到行情，涉及票的盈亏按可得价格估算或留空">行情覆盖 ${Math.round(s.coverage * 100)}%</span>` : "";
    // 在持浮动列表：按持仓汇总同口径过滤（最近观点天数）与排序
    const holdings = mxcSortRows(mxcFilterByRecent(_mxc.data ? _mxc.data.holdings || [] : []));
    const liveRows = holdings.map((h) => {
      const p = byName[h.target_name] || {};
      return `
      <div class="mxc-pnl-row">
        <span class="mxc-pnl-name" title="${escapeHtml(h.target_name)}">${escapeHtml(h.target_name)}</span>
        <span class="mxc-pnl-cost">${p.avg_cost != null ? `成本 ${Number(p.avg_cost).toFixed(2)}` : ""}
          ${p.last_price != null ? ` → 现价 ${Number(p.last_price).toFixed(2)}` : ""}</span>
        ${p.floating_pnl_pct != null ? mxcPctBadge(p.floating_pnl_pct)
          : `<span class="mxc-pnl-na" title="该票行情不全，无法估算">—</span>`}
        ${mxcPnlActs(p)}
      </div>`;
    }).join("");
    // 已了结列表：清仓/翻空出仓/超时未提及，按了结时间新→旧。
    // 默认只露前 MXC_CLOSED_LIMIT 条，其余折叠进「更多」——长了会盖过在持浮动
    const closed = (pnl.stocks || []).filter((x) => x.state !== "holding")
      .sort((a, b) => String(b.closed_at || "").localeCompare(String(a.closed_at || "")));
    const closedShown = _mxc.closedExpanded ? closed : closed.slice(0, MXC_CLOSED_LIMIT);
    const closedRows = closed.length ? closedShown.map((p) => `
      <div class="mxc-pnl-row closed">
        <span class="mxc-pnl-name" title="${escapeHtml(p.target_name)}">${escapeHtml(p.target_name)}</span>
        <span class="mxc-pnl-cost">${p.realized_pnl_pct != null
          ? `了结收益 ${p.realized_pnl_pct > 0 ? "+" : ""}${p.realized_pnl_pct}%`
          : (p.events_priced != null && p.events_priced < p.events_total ? "行情不全" : "无卖出事件")}</span>
        ${p.realized_pnl_pct != null ? mxcPctBadge(p.realized_pnl_pct) : `<span class="mxc-pnl-na">—</span>`}
        ${p.exit_note ? `<span class="mxc-pnl-exit" title="${escapeHtml(p.exit_note)}">${escapeHtml(p.state === "stale" ? "超时" : "出仓")}</span>` : ""}
        ${mxcPnlActs(p)}
      </div>`).join("") : "";
    const closedMore = closed.length > MXC_CLOSED_LIMIT
      ? `<button type="button" class="mxc-more" onclick="mxcToggleClosed()">${_mxc.closedExpanded ? "收起 ▴" : `更多 ▾（还有 ${closed.length - MXC_CLOSED_LIMIT} 个）`}</button>`
      : "";
    el.innerHTML = `
      ${head}
      ${cov}
      ${liveRows ? `<div class="mxc-pnl-sub">在持浮动</div>${liveRows}` : ""}
      ${closedRows ? `<div class="mxc-pnl-sub">已了结</div>${closedRows}${closedMore}` : ""}
      ${(!liveRows && !closedRows) ? `<div class="mxv-empty">窗口内无个股操作，暂无盈亏记录。</div>` : ""}
      <p class="mxc-pnl-note">盈亏以操作事件时刻股价为成本/卖价回放估算，非真实持仓收益；仅供参考。</p>`;
  }

  function mxcRenderSummary() {
    const el = document.getElementById("mxc-summary");
    if (!el) return;
    const d = _mxc.data;
    const allHoldings = d.holdings || [];
    const allTopics = d.topics || [];
    const holdings = mxcSortRows(mxcFilterByRecent(allHoldings));
    const topics = mxcSortRows(mxcFilterByRecent(allTopics));
    const headRight = `${holdings.length} 只个股${topics.length ? ` · ${topics.length} 个板块` : ""}`
      + (holdings.length ? ` · 合计 ${Math.round(holdings.reduce((s, h) => s + h.weight, 0))}%` : "");
    const filteredNote = _mxc.recent && (holdings.length < allHoldings.length || topics.length < allTopics.length)
      ? `<span class="hd-hint" title="滑动栏筛掉了更久未被提及的标的">已滤 ${allHoldings.length - holdings.length + allTopics.length - topics.length} 个超 ${_mxc.recent} 天未提及</span>`
      : "";
    if (!allHoldings.length && !allTopics.length) {
      el.innerHTML = `
        <div class="hd-panel-head"><b>当前预估持仓</b>
          <span class="hd-hint">${d.opinion_count ? "窗口内无在持标的" : "暂无观点"}</span></div>
        ${mxcRecentHtml()}
        <div class="mxv-empty">${d.opinion_count
          ? `近 ${d.window_days} 天有 ${d.opinion_count} 条观点，但按回放规则当前无在持标的（均已清仓/翻空/超 ${d.stale_days || 10} 天未再提及）。`
          : `近 ${d.window_days} 天内没有可研判的观点，暂无法推演持仓。`}</div>`;
      return;
    }
    const pnlByName = mxcPnlByStock();
    const stockRows = holdings.map((h) => {
      const p = pnlByName[h.target_name];
      return `
      <div class="mxc-holding">
        <span class="mxc-h-name">${escapeHtml(h.target_name)}</span>
        <span class="mxc-h-dir ${h.direction === "bull" ? "bull" : h.direction === "bear" ? "bear" : ""}">${h.direction === "bull" ? "看多" : h.direction === "bear" ? "看空" : "中性"}</span>
        ${mxcWeightBar(h.weight)}
        <span class="mxc-h-weight">${h.weight}%</span>
        ${p && p.floating_pnl_pct != null ? mxcPctBadge(p.floating_pnl_pct, `预估浮动盈亏（成本 ${p.avg_cost != null ? Number(p.avg_cost).toFixed(2) : "?"}）`) : ""}
        <span class="mxc-h-meta" title="首次建仓 ${escapeHtml(h.since || "")}">建仓 ${escapeHtml((h.since || "").slice(5, 10))} · 最近 ${escapeHtml((h.last_at || "").slice(5, 16))}</span>
      </div>`;
    }).join("");
    const topicRows = topics.length ? `
      <div class="mxc-topics-head">关注板块（不计入仓位占比）</div>
      <div class="mxc-topics">${topics.map((t) =>
        `<span class="mxc-topic" title="最近提及 ${escapeHtml((t.last_at || "").slice(5, 16))}">${escapeHtml(t.target_name)}</span>`).join("")}</div>` : "";
    el.innerHTML = `
      <div class="hd-panel-head"><b>当前预估持仓</b>
        <span class="hd-hint">${headRight}</span>${filteredNote}</div>
      ${mxcRecentHtml()}
      ${holdings.length || topics.length ? stockRows + topicRows
        : `<div class="mxv-empty">最近 ${_mxc.recent} 天内没有大V提及的在持标的——可能早已清仓但未被识别，试着调大天数或设为 0 看全部。</div>`}
      <p class="mxc-note">持仓由大V公开观点（方向 + 操作词）回放估算，非真实仓位；仅供参考，不构成投资建议。</p>`;
  }

  function mxcKindBadge(kind, action) {
    const k = MXC_KINDS[kind] || MXC_KINDS.hold;
    return `<span class="mxc-kind ${k.cls}">${k.label}${action ? ` · ${escapeHtml(action)}` : ""}</span>`;
  }

  function mxcRenderTimeline() {
    const el = document.getElementById("mxc-timeline");
    if (!el) return;
    const d = _mxc.data;
    const all = d.timeline || [];
    const rows = _mxc.view === "all" ? all : all.filter((e) => {
      if (_mxc.view === "open") return e.kind === "open";
      if (_mxc.view === "add") return e.kind === "add";
      if (_mxc.view === "trim") return e.kind === "trim" || e.kind === "flip";
      if (_mxc.view === "clear") return e.kind === "clear";
      return true;
    });
    const head = `
    <div class="mxv-kol-head">
      <h3>操作时间线</h3>
      <div class="hd-seg" role="tablist" aria-label="操作筛选">
        ${Object.entries(MXC_VIEWS).map(([k, label]) => `<button type="button"
          class="hd-seg-btn${_mxc.view === k ? " on" : ""}" onclick="mxcSetView('${k}')">${label}</button>`).join("")}
      </div>
      <span class="hd-hint">${rows.length ? `${rows.length} 条` : ""}</span>
    </div>`;
    if (!all.length) {
      el.innerHTML = head + `<div class="mxv-empty">近 ${d.window_days} 天暂无可研判观点。</div>`;
      return;
    }
    if (!rows.length) {
      el.innerHTML = head + `<div class="mxv-empty">当前筛选无操作记录。</div>`;
      return;
    }
    // 按交易日分段（最新在前），行内展示 时间/操作徽章/方向/标的/摘要
    const groups = new Map();
    rows.forEach((e) => {
      const day = e.trading_day || (e.occurred_at || "").slice(0, 10);
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day).push(e);
    });
    const dayLabel = (day) => {
      const s = String(day || "");
      // 今天/昨天按北京时间判（与后端交易日同口径；海外浏览器本地时区会差一天）
      const bj = new Date(Date.now() + (480 + new Date().getTimezoneOffset()) * 60000);
      const p = (n) => String(n).padStart(2, "0");
      const today = `${bj.getFullYear()}-${p(bj.getMonth() + 1)}-${p(bj.getDate())}`;
      if (s === today) return "今天";
      bj.setDate(bj.getDate() - 1);
      const yesterday = `${bj.getFullYear()}-${p(bj.getMonth() + 1)}-${p(bj.getDate())}`;
      if (s === yesterday) return "昨天";
      return s.slice(5) || "—";
    };
    const body = [...groups.entries()].map(([day, evs]) => `
      <div class="mxv-feed-sep"><span>${escapeHtml(dayLabel(day))} · ${evs.length} 条</span></div>
      <div class="mxv-feed-cols single"><div class="mxv-feed-col">${evs.map(mxcRowHtml).join("")}</div></div>`
    ).join("") + `<div class="mxv-feed-sep"><span>共 ${rows.length} 条</span></div>`;
    el.innerHTML = head + body;
  }

  function mxcRowHtml(e) {
    const dir = e.direction === "bull" ? `<span class="mxv-badge bull">↑看多</span>`
      : e.direction === "bear" ? `<span class="mxv-badge bear">↓看空</span>`
      : `<span class="mxv-badge neutral">中性</span>`;
    const at = (_mxc.pnl && _mxc.pnl.event_prices || {})[`${e.target_name}|${e.occurred_at || ""}`] || "";
    // 人工标注事件出「人工」徽章；可标注用户可在行内就地对证据消息标注
    // （预填该行标的，postId 取首条证据帖）
    const manualBadge = e.source === "manual"
      ? `<span class="mxc-src mxc-src-manual" title="该操作来自人工标注（管理员直判或多人一致生效），非自动解析">人工</span>` : "";
    const markBtn = (e.evidence && e.evidence.length && state.user?.can_mx_action_mark)
      ? `<button type="button" class="mxc-mark-btn" title="人工标注该消息的个股操作（修正/确认此操作）"
          aria-label="标注${escapeHtml(e.target_name)}的操作"
          onclick="openActionMarkModal(${Number(e.evidence[0])}, ${JSON.stringify(String(e.target_name)).replace(/"/g, "&quot;")})">标注</button>`
      : "";
    return `
    <div class="mxv-feed-item mxc-row">
      <span class="t" style="color:var(--mxv-accent)">${escapeHtml((e.occurred_at || "").slice(11, 16))}</span>
      ${mxcKindBadge(e.kind, e.action)}
      ${dir}
      <span class="target" style="color:var(--mxv-text)" title="${escapeHtml(e.target_name)}">${escapeHtml(e.target_name)}</span>
      ${at ? `<span class="mxc-price">${escapeHtml(at)}</span>` : ""}
      ${e.source === "tag" ? `<span class="mxc-src" title="操作来自消息标签（观点研判未覆盖该条），仅供参考">标签</span>` : ""}
      ${manualBadge}
      ${markBtn}
      <span class="sum" style="color:var(--mxv-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(e.summary || "")}">${escapeHtml(e.summary || "")}</span>
    </div>`;
  }

  function mxcSetView(v) {
    _mxc.view = MXC_VIEWS[v] ? v : "all";
    mxcRenderTimeline();
  }

  return { renderMxKolHoldings, mxcOpenDrawer, mxcCloseDrawer, mxcSetView, mxcChangeDays, mxcRecentInput,
    mxcRecentChange, mxcSetSort, mxcToggleClosed, mxcToggleActs };
}
