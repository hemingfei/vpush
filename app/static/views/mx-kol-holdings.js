// MX 大V预估持仓页（/mx-kol/{id}）：按历史观点回放推演的仓位——顶部当前持仓汇总
// （权重条），下方操作时间线（买入建仓/买入加仓/卖出减仓/卖出清仓/翻空减仓/持仓表态）。
// 视觉与持股研判页同一套 .hd- token（holdings.css），样式全部 .mxc- 前缀
export function createMxKolHoldingsView(dependencies) {
  const {
    $, state, api, escapeHtml, setPageTitle, go, routeStillActive, emptyState, flash,
  } = dependencies;

  const _mxc = { seq: 0, data: null, days: 30, expanded: new Set(), view: "all" };
  const MXC_VIEWS = { all: "全部", open: "建仓", add: "加仓", trim: "减仓", clear: "清仓" };

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
    Object.assign(_mxc, { data: null, expanded: new Set(), view: "all" });
  }

  async function renderMxKolHoldings(kolId, seq) {
    mxcTeardown();
    _mxc.seq = seq;
    _mxc.kolId = kolId;
    setPageTitle("预估持仓");
    $("#main").innerHTML = `<div class="mxc-root hd-root"><div class="mxv-empty">加载中…</div></div>`;
    try {
      const data = await api(`/api/kols/${kolId}/mx-holdings?days=${_mxc.days}`);
      if (!routeStillActive(seq)) return;
      _mxc.data = data;
      mxcRenderAll();
    } catch (err) {
      if (!routeStillActive(seq)) return;
      $("#main").innerHTML = `<div class="mxc-root hd-root"><div class="mxv-empty">加载失败: ${escapeHtml(err.message)}</div></div>`;
    }
  }

  async function mxcChangeDays(days) {
    _mxc.days = days;
    const seq = _mxc.seq;
    const feed = $("#mxc-timeline");
    if (feed) feed.innerHTML = `<div class="mxv-empty">加载中…</div>`;
    try {
      const data = await api(`/api/kols/${_mxc.kolId}/mx-holdings?days=${days}`);
      if (!routeStillActive(seq)) return;
      _mxc.data = data;
      mxcRenderAll();
    } catch (err) {
      flash(`刷新失败: ${err.message}`, "error");
      mxcRenderAll();
    }
  }

  function mxcRenderAll() {
    const d = _mxc.data;
    if (!d) return;
    const kol = d.kol || {};
    $("#main").innerHTML = `
      <div class="mxc-root hd-root">
        <section class="mxc-head">
          <button type="button" class="hd-btn sm" onclick="go('/kol/${Number(kol.kol_id || 0)}')" aria-label="返回大V动态">‹ 动态</button>
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
        <section class="hd-feed" id="mxc-timeline"></section>
      </div>`;
    mxcRenderSummary();
    mxcRenderTimeline();
  }

  function mxcWeightBar(w) {
    return `<div class="mxc-bar"><div class="fill" style="width:${Math.max(2, Math.min(100, w))}%"></div></div>`;
  }

  function mxcRenderSummary() {
    const el = document.getElementById("mxc-summary");
    if (!el) return;
    const d = _mxc.data;
    const holdings = d.holdings || [];
    const topics = d.topics || [];
    if (!holdings.length && !topics.length) {
      el.innerHTML = `
        <div class="hd-panel-head"><b>当前预估持仓</b>
          <span class="hd-hint">${d.opinion_count ? "窗口内无在持标的" : "暂无观点"}</span></div>
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
        <span class="hd-hint">${holdings.length} 只个股${topics.length ? ` · ${topics.length} 个板块` : ""} · 合计 ${Math.round(holdings.reduce((s, h) => s + h.weight, 0))}%</span></div>
      ${stockRows}${topicRows}
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

  return { renderMxKolHoldings, mxcSetView, mxcChangeDays };
}
