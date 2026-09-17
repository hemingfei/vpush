// MX 大V预估持仓——两种宿主共用一套渲染：
// ① 独立页 /mx-kol/{id}；② /mx-views 大V头像旁「持仓」按钮弹出的右侧抽屉。
// 顶部当前持仓汇总（权重条），下方操作时间线（买入建仓/买入加仓/卖出减仓/卖出清仓/翻空减仓/持仓表态）。
// 视觉与持股研判页同一套 .hd- token（holdings.css），样式全部 .mxc- 前缀；
// 抽屉外壳自带 .hd-root 变量作用域，挂进 #mxv-drawer-slot（与智囊团抽屉同位，同一时刻只留一个）
export function createMxKolHoldingsView(dependencies) {
  const {
    $, state, api, escapeHtml, setPageTitle, go, routeStillActive, emptyState, flash,
    closeViewsDrawer,
  } = dependencies;

  const _mxc = { seq: 0, data: null, days: 30, expanded: new Set(), view: "all", recent: 3, sort: "weight",
    kolId: 0, drawerEl: null, drawerBody: null, token: 0 };
  const MXC_VIEWS = { all: "全部", open: "建仓", add: "加仓", trim: "减仓", clear: "清仓" };
  // 最近观点天数筛选：只看最近 N 天内还被大V提及的在持标的（0=不筛选）。
  // 部分票太老、没识别出清仓但大V其实早清了——限近期提及至少保证展示的票基本还在仓
  const MXC_RECENT_KEY = "mxc_recent_days";
  // 持仓排序：weight=按仓位权重（后端默认序），time=按最近观点时间最新在前
  const MXC_SORT_KEY = "mxc_sort";

  // 操作事件 → 徽章文案与色彩语义（A股口径：买入=红、卖出=绿）
  const MXC_KINDS = {
    open: { label: "买入建仓", cls: "buy" },
    add: { label: "买入加仓", cls: "buy" },
    trim: { label: "卖出减仓", cls: "sell" },
    clear: { label: "卖出清仓", cls: "sell" },
    flip: { label: "翻空减仓", cls: "sell" },
    hold: { label: "持仓", cls: "hold" },
  };

  function mxcTeardown() {
    Object.assign(_mxc, { data: null, expanded: new Set(), view: "all", drawerEl: null, drawerBody: null });
    // recent（最近观点天数）跨路由保留：回来时还是用户上次调的口径
  }

  // 竞态守卫：token 拦截同宿主内的旧响应（快速换天数/换大V重开）；
  // 抽屉宿主看 DOM 连通性（路由切换由 mxvTeardown 摘除节点），页面宿主沿用路由 seq
  function mxcStale(token, seq) {
    if (token !== _mxc.token) return true;
    if (_mxc.drawerEl) return !_mxc.drawerEl.isConnected;
    return seq != null && !routeStillActive(seq);
  }

  // 统一取数+落盘：初次加载失败出整屏错误；换窗口失败只 flash 并回显旧数据
  async function mxcLoad(kolId, token, seq) {
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
      // 从未存过（null）不覆盖默认：Number(null)=0 会把默认天数顶成“0=不筛选”
      const raw = localStorage.getItem(MXC_RECENT_KEY);
      if (raw != null) {
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
    mxcRenderTimeline();
  }

  // 页面/抽屉共用主体：页头（抽屉宿主不出「‹ 动态」返回钮，关闭走外壳 ✕）+ 汇总 + 时间线
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

  // 松手/键盘步进（change）才落地：刷新持仓汇总 + 持久化（拖动全程写存储太密）
  function mxcRecentChange(value) {
    const v = Math.max(0, Math.min(20, Math.round(Number(value))));
    _mxc.recent = v;
    mxcSaveRecent();
    mxcRecentText(v);
    mxcRenderSummary();
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
          ? `近 ${d.window_days} 天有 ${d.opinion_count} 条观点，但按回放规则当前无在持标的（均已清仓/翻空/超 ${10} 天未再提及）。`
          : `近 ${d.window_days} 天内没有可研判的观点，暂无法推演持仓。`}</div>`;
      return;
    }
    const stockRows = holdings.map((h) => `
      <div class="mxc-holding">
        <span class="mxc-h-name">${escapeHtml(h.target_name)}</span>
        <span class="mxc-h-dir ${h.direction === "bull" ? "bull" : h.direction === "bear" ? "bear" : ""}">${h.direction === "bull" ? "看多" : h.direction === "bear" ? "看空" : "中性"}</span>
        ${mxcWeightBar(h.weight)}
        <span class="mxc-h-weight">${h.weight}%</span>
        <span class="mxc-h-meta" title="首次建仓 ${escapeHtml(h.since || "")}">建仓 ${escapeHtml((h.since || "").slice(5, 10))} · 最近 ${escapeHtml((h.last_at || "").slice(5, 16))}</span>
      </div>`).join("");
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
      const now = new Date();
      const p = (n) => String(n).padStart(2, "0");
      if (s === `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}`) return "今天";
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
    return `
    <div class="mxv-feed-item mxc-row">
      <span class="t" style="color:var(--mxv-accent)">${escapeHtml((e.occurred_at || "").slice(11, 16))}</span>
      ${mxcKindBadge(e.kind, e.action)}
      ${dir}
      <span class="target" style="color:var(--mxv-text)" title="${escapeHtml(e.target_name)}">${escapeHtml(e.target_name)}</span>
      ${e.source === "tag" ? `<span class="mxc-src" title="操作来自消息标签（观点研判未覆盖该条），仅供参考">标签</span>` : ""}
      <span class="sum" style="color:var(--mxv-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(e.summary || "")}">${escapeHtml(e.summary || "")}</span>
    </div>`;
  }

  function mxcSetView(v) {
    _mxc.view = MXC_VIEWS[v] ? v : "all";
    mxcRenderTimeline();
  }

  return { renderMxKolHoldings, mxcOpenDrawer, mxcCloseDrawer, mxcSetView, mxcChangeDays, mxcRecentInput,
    mxcRecentChange, mxcSetSort };
}
