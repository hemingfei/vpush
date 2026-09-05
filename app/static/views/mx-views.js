// MX 平台大V实时观点页（/mx-views）——页面级暗色终端，样式全部 .mxv- 前缀
// 与其他视图一致走工厂注入；内联 onclick 用到的函数由 app.js 解构后挂进 INLINE_HANDLERS
export function createMxViewsView(dependencies) {
  const {
    $,
    state,
    api,
    escapeHtml,
    setPageTitle,
    go,
    routeQuery,
    routeStillActive,
    currentAdminSeq,
    emptyState,
    flash,
  } = dependencies;

  window._mxvPosts = []; // 证据原帖缓存，供 app.js openRawModal 查找
  window._mxvTargets = []; // 标的索引，供 onclick 按下标打开（避免外部名称注入 JS 字符串）
  const _mxv = { seq: 0, day: null, days: [], snapshots: [], at: null, payload: null,
    atLatest: true, hasNew: false, es: null, sseOk: false, pollTimer: null, clockTimer: null, drawer: null };

  function mxvTeardown() {
    if (_mxv.es) { try { _mxv.es.close(); } catch (e) {} _mxv.es = null; }
    if (_mxv.pollTimer) { clearInterval(_mxv.pollTimer); _mxv.pollTimer = null; }
    if (_mxv.clockTimer) { clearInterval(_mxv.clockTimer); _mxv.clockTimer = null; }
    const d = document.querySelector(".mxv-drawer-mask"); if (d) d.remove();
    const dr = document.querySelector(".mxv-drawer"); if (dr) dr.remove();
    Object.assign(_mxv, { day: null, payload: null, at: null, drawer: null, hasNew: false, sseOk: false });
  }

  async function renderMxViews(seq) {
    mxvTeardown();
    _mxv.seq = seq;
    setPageTitle("MX观点");
    $("#main").innerHTML = `<div class="mxv-root"><div class="mxv-empty">加载中…</div></div>`;
    try {
      const daysData = await api("/api/mx-views/days");
      if (!routeStillActive(seq)) return;
      _mxv.days = (daysData.days || []).map((d) => d.trading_day);
      const qday = routeQuery().get("day");
      await mxvLoadDay(qday && _mxv.days.includes(qday) ? qday : (_mxv.days[0] || null), seq);
      if (!routeStillActive(seq)) return;
      mxvEnsureSSE();
    } catch (err) {
      if (!routeStillActive(seq)) return;
      $("#main").innerHTML = `<div class="mxv-root"><div class="mxv-empty">加载失败: ${escapeHtml(err.message)}</div></div>`;
    }
  }

  async function mxvLoadDay(day, seq) {
    if (!day) {
      $("#main").innerHTML = `<div class="mxv-root"><div class="mxv-empty">暂无快照数据：请管理员在后台开启「MX观点」并等待快照，或使用「回填」生成历史。</div></div>`;
      return;
    }
    const dayData = await api(`/api/mx-views/day?day=${encodeURIComponent(day)}`);
    if (seq !== undefined && !routeStillActive(seq)) return;
    _mxv.day = day;
    _mxv.snapshots = dayData.snapshots || [];
    const target = dayData.latest_at;
    if (target) { await mxvApplySnapshot(target); } else { mxvRenderShell(); }
  }

  async function mxvApplySnapshot(at) {
    if (!routeStillActive(_mxv.seq)) return;
    const data = await api(`/api/mx-views/snapshot?day=${encodeURIComponent(_mxv.day)}&at=${encodeURIComponent(at)}`);
    if (!routeStillActive(_mxv.seq)) return;
    _mxv.at = at;
    _mxv.payload = data.payload || {};
    _mxv.atLatest = _mxv.snapshots.length > 0 && at === _mxv.snapshots[_mxv.snapshots.length - 1].snapshot_at;
    if (_mxv.atLatest) _mxv.hasNew = false;
    window._mxvPosts = []; // 换快照清证据缓存
    window._mxvTargets = []; // 换快照清标的索引
    mxvRenderShell();
  }

  function mxvGoLatest() {
    if (!_mxv.snapshots.length) return;
    mxvApplySnapshot(_mxv.snapshots[_mxv.snapshots.length - 1].snapshot_at);
  }

  function mxvStep(dir) {
    const idx = _mxv.snapshots.findIndex((s) => s.snapshot_at === _mxv.at);
    const next = _mxv.snapshots[idx + dir];
    if (next) mxvApplySnapshot(next.snapshot_at);
  }

  function mxvSseDotSync() {
    document.querySelectorAll(".mxv-dot.sse").forEach((d) => d.classList.toggle("on", !!_mxv.sseOk));
  }

  function mxvEnsureSSE() {
    if (!state.token || _mxv.es) return;
    try {
      const es = new EventSource(`/api/mx-views/stream?token=${encodeURIComponent(state.token)}`);
      es.addEventListener("version", () => {
        if (_mxv.atLatest) { mxvRefreshLatest(); }
        else {
          _mxv.hasNew = true;
          const btn = document.querySelector(".mxv-btn.latest");
          if (btn) btn.classList.add("has-new");
        }
      });
      es.onerror = () => { // EventSource 自动重连；兜底轮询 60s
        _mxv.sseOk = false;
        mxvSseDotSync();
        if (!_mxv.pollTimer) _mxv.pollTimer = setInterval(() => { if (_mxv.atLatest) mxvRefreshLatest(); }, 60000);
      };
      es.onopen = () => {
        _mxv.sseOk = true;
        mxvSseDotSync();
        if (_mxv.pollTimer) { clearInterval(_mxv.pollTimer); _mxv.pollTimer = null; }
      };
      _mxv.es = es;
    } catch (e) { /* SSE 不可用时静默，靠手动刷新 */ }
  }

  async function mxvRefreshLatest() {
    if (!routeStillActive(_mxv.seq)) return;
    if (!_mxv.day) { // 空态停留：live 首个快照落库后自动恢复
      try {
        const daysData = await api("/api/mx-views/days");
        if (!routeStillActive(_mxv.seq)) return;
        _mxv.days = (daysData.days || []).map((d) => d.trading_day);
        if (_mxv.days.length) await mxvLoadDay(_mxv.days[0], _mxv.seq);
      } catch (e) { /* 无数据保持空态 */ }
      return;
    }
    const dayData = await api(`/api/mx-views/day?day=${encodeURIComponent(_mxv.day)}`).catch(() => null);
    if (!dayData || !routeStillActive(_mxv.seq)) return;
    _mxv.snapshots = dayData.snapshots || [];
    if (dayData.latest_at && dayData.latest_at !== _mxv.at) await mxvApplySnapshot(dayData.latest_at);
  }

  function mxvPickDay(day) { go(`/mx-views?day=${encodeURIComponent(day)}`); }

  function mxvRenderShell() {
    const root = $("#main").querySelector(".mxv-root") || $("#main");
    root.outerHTML = mxvRootHtml();
    mxvStartClock();
    mxvRenderBoards();
    mxvRenderDrawer();
  }

  function mxvRootHtml() {
    const p = _mxv.payload || {};
    const dayOpts = _mxv.days.map((d) =>
      `<option value="${d}" ${d === _mxv.day ? "selected" : ""}>${d}</option>`).join("");
    return `
    <div class="mxv-root">
      <div class="mxv-statusbar">
        <span class="mxv-pill" id="mxv-market"><span class="mxv-dot off"></span>—</span>
        <span class="mxv-pill" id="mxv-clock">--:--:--</span>
        <span class="mxv-pill">数据 ${escapeHtml(_mxv.at || "—")}${p.message_count != null ? ` · ${p.message_count} 条消息` : ""}</span>
        <span class="mxv-pill"><span class="mxv-dot sse${_mxv.sseOk ? " on" : ""}"></span>SSE</span>
        <select class="mxv-pill" style="color:var(--mxv-text)" onchange="mxvPickDay(this.value)" aria-label="选择交易日">${dayOpts}</select>
        <button class="mxv-btn" onclick="mxvRefreshLatest()" style="margin-left:auto">刷新</button>
      </div>
      ${mxvTimelineHtml()}
      <div id="mxv-banner"></div>
      <div id="mxv-boards"></div>
      <div id="mxv-feed"></div>
      <div id="mxv-kols"></div>
    </div>
    <div id="mxv-drawer-slot"></div>`;
  }

  function mxvTimelineHtml() {
    const snaps = _mxv.snapshots;
    if (!snaps.length) return `<div class="mxv-timeline mxv-empty">当日暂无快照</div>`;
    const n = snaps.length;
    const ticks = snaps.map((s, i) => {
      const left = n === 1 ? 50 : (i / (n - 1)) * 100;
      const active = s.snapshot_at === _mxv.at;
      const special = ["12:00", "16:00"].includes(s.snapshot_at) || i === 0;
      return `<div class="mxv-tl-tick ${special ? "special" : ""}" style="left:${left}%"
        title="${s.snapshot_at} · ${s.message_count}条消息" onclick="mxvApplySnapshot('${s.snapshot_at}')"></div>
        <div class="mxv-tl-head" style="left:${left}%;${active ? "" : "display:none"}">
          <div class="t">${s.snapshot_at}</div><div class="s"></div></div>`;
    }).join("");
    const idx = Math.max(0, snaps.findIndex((s) => s.snapshot_at === _mxv.at));
    const doneW = n <= 1 ? 100 : (idx / (n - 1)) * 100;
    const diff = mxvDiffText();
    return `
    <div class="mxv-timeline">
      <div style="display:flex;align-items:center;gap:8px">
        <button class="mxv-btn" onclick="mxvStep(-1)" aria-label="上一快照">◀</button>
        <div class="mxv-tl-track"><div class="mxv-tl-rail"></div>
          <div class="mxv-tl-done" style="left:0;width:${doneW}%"></div>${ticks}</div>
        <button class="mxv-btn" onclick="mxvStep(1)" aria-label="下一快照">▶</button>
        <button class="mxv-btn latest ${_mxv.atLatest ? "" : "has-new"}" onclick="mxvGoLatest()">回最新 ▸▸</button>
      </div>
      <div class="mxv-tl-meta">
        <span>快照 ${idx + 1}/${n}</span>
        ${_mxv.hasNew && !_mxv.atLatest ? `<span style="color:var(--mxv-gold)">有新快照</span>` : ""}
        ${diff ? `<span>较上版：${diff}</span>` : ""}
      </div>
    </div>`;
  }

  function mxvDiffText() {
    // momentum = net - 上一快照 net，反推上一版数值即可，不必再拉上一份 payload
    if (!_mxv.payload) return "";
    const parts = [];
    (_mxv.payload.topics || []).slice(0, 3).forEach((t) => {
      if (t.momentum) parts.push(`${escapeHtml(t.name)} 净多空 ${t.net - t.momentum}→${t.net}`);
    });
    return parts.join(" · ");
  }

  function mxvMarketState() {
    // 状态点：9:15-11:30 / 13:00-15:00 盘中；周末休市；开关决定显示
    const now = new Date();
    const day = now.getDay();
    const hm = now.getHours() * 60 + now.getMinutes();
    const am = hm >= 555 && hm <= 690; // 9:15-11:30
    const pm = hm >= 780 && hm <= 900; // 13:00-15:00
    const live = day >= 1 && day <= 5 && (am || pm);
    return live
      ? `<span class="mxv-dot live"></span>盘中`
      : (day === 0 || day === 6 ? `<span class="mxv-dot off"></span>周末休市` : `<span class="mxv-dot off"></span>休市`);
  }

  function mxvStartClock() {
    const el = document.getElementById("mxv-clock");
    const mk = document.getElementById("mxv-market");
    if (!el) return;
    const tick = () => {
      const n = new Date();
      const p = (x) => String(x).padStart(2, "0");
      el.textContent = `${p(n.getHours())}:${p(n.getMinutes())}:${p(n.getSeconds())}`;
      if (mk) mk.innerHTML = mxvMarketState();
    };
    tick();
    if (_mxv.clockTimer) clearInterval(_mxv.clockTimer);
    _mxv.clockTimer = setInterval(tick, 1000);
  }

  function mxvChipsHtml(items) {
    return (items || []).map((it) => {
      const cnt = it.count != null ? ` ×${it.count}` : "";
      const label = it.action ? `${it.name} ${it.action}${cnt}` : `${it.name}${cnt}`;
      const cls = it.direction === "bear" ? "bear" : it.direction === "neutral" ? "neutral" : "bull";
      const target = it.type === "stock" ? "stock" : "topic";
      window._mxvTargets.push({ type: target, name: it.name });
      const idx = window._mxvTargets.length - 1;
      return `<span class="mxv-chip ${cls}" onclick="mxvOpenTargetAt(${idx})">${escapeHtml(label)}</span>`;
    }).join("");
  }

  function mxvMomo(m) {
    if (m > 0) return `<span class="mxv-momo up">↑${m}</span>`;
    if (m < 0) return `<span class="mxv-momo down">↓${-m}</span>`;
    return `<span class="mxv-momo flat">→</span>`;
  }

  function mxvRatioHtml(bull, bear) {
    const total = Math.max(bull + bear, 1);
    const bp = Math.round((bull / total) * 100), sp = Math.round((bear / total) * 100);
    return `<div class="mxv-ratio" role="img" aria-label="看多${bull} 看空${bear}">
      ${bull ? `<div class="b" style="width:${bp}%"></div>` : ""}
      ${bear ? `<div class="s" style="width:${sp}%"></div>` : ""}</div>`;
  }

  function mxvRenderBoards() {
    if (!_mxv.payload) return;
    window._mxvTargets = []; // 重新渲染双榜前清空标的索引
    const p = _mxv.payload;
    const banner = $("#mxv-banner");
    if (banner) {
      const s = p.summary || {};
      banner.innerHTML = s && s.text ? `
        <div class="mxv-banner">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
            <b style="color:#fff">⚡ 今日操作</b>
            <span style="margin-left:auto;color:var(--mxv-faint);font-size:11px">第 ${(_mxv.snapshots.find((x) => x.snapshot_at === _mxv.at) || {}).seq || "—"} 版 · ${escapeHtml(_mxv.at || "")} 生成</span>
          </div>
          <div class="text">${escapeHtml(s.text || "")}</div>
          <div class="mxv-chips">${mxvChipsHtml(s.items)}</div>
        </div>` : "";
    }
    const boards = $("#mxv-boards");
    if (boards) {
      const topicRows = (p.topics || []).map((t, i) => {
        window._mxvTargets.push({ type: "topic", name: t.name });
        const ti = window._mxvTargets.length - 1;
        return `
        <div class="mxv-row" onclick="mxvOpenTargetAt(${ti})">
          <span class="rank">${i + 1}</span><span class="name">${escapeHtml(t.name)}</span>
          ${mxvRatioHtml(t.bull, t.bear)}
          <span class="mxv-net ${t.net > 0 ? "bull" : t.net < 0 ? "bear" : "flat"}">${t.bull}多/${t.bear}空</span>
          ${mxvMomo(t.momentum)}
          <span class="mxv-latest-time">${escapeHtml((t.latest_at || "").slice(11, 16))}</span>
        </div>`; }).join("");
      const stockRows = (p.stocks || []).map((s, i) => {
        const actions = Object.entries(s.actions || {}).map(([k, v]) => `${k}×${v}`).join(" ");
        window._mxvTargets.push({ type: "stock", name: s.name });
        const si = window._mxvTargets.length - 1;
        return `
        <div class="mxv-row" onclick="mxvOpenTargetAt(${si})">
          <span class="rank">${i + 1}</span><span class="name">${escapeHtml(s.name)}</span>
          ${mxvRatioHtml(s.bull, s.bear)}
          <span class="mxv-net ${s.net > 0 ? "bull" : s.net < 0 ? "bear" : "flat"}">${s.strength}</span>
          ${mxvMomo(s.momentum)}
          <span class="mxv-actions">${escapeHtml(actions)}</span>
        </div>`;
      }).join("");
      boards.innerHTML = `
        <div class="mxv-boards">
          <div class="mxv-board"><h3>题材多空榜</h3>${topicRows || `<div class="mxv-empty">暂无题材观点</div>`}</div>
          <div class="mxv-board"><h3>个股强度榜</h3>${stockRows || `<div class="mxv-empty">暂无个股观点</div>`}</div>
        </div>`;
    }
    const feed = $("#mxv-feed");
    if (feed) {
      const items = (p.new_opinions || []).map((o, i) => `
        <div class="mxv-feed-item ${_mxv.atLatest && i === 0 ? "fresh" : ""}">
          <span style="color:var(--mxv-accent)">${escapeHtml((o.occurred_at || "").slice(11, 16))}</span>
          <span class="mxv-badge ${o.direction}">${o.direction === "bull" ? "↑看多" : o.direction === "bear" ? "↓看空" : "中性"}</span>
          ${o.action ? `<span class="mxv-badge act">${escapeHtml(o.action)}</span>` : ""}
          <span style="color:var(--mxv-text)">${escapeHtml(o.target_name)}</span>
          <span style="color:var(--mxv-muted)">· ${escapeHtml(o.kol_name)}</span>
          <span style="color:var(--mxv-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(o.summary || "")}</span>
        </div>`).join("");
      feed.innerHTML = `<h3 style="margin:0 0 6px;color:var(--mxv-accent);font-size:14px">实时观点流（${escapeHtml(_mxv.at || "")} 批次）</h3>` +
        (items || `<div class="mxv-empty">本批次无新增观点</div>`);
    }
    const kols = $("#mxv-kols");
    if (kols) {
      const cards = (p.kols || []).map((k) => {
        const b = (k.bull_names || []).length, s = (k.bear_names || []).length;
        const tot = Math.max(b + s, 1);
        return `
        <div class="mxv-kolcard" onclick="mxvOpenKol(${k.kol_id})">
          ${k.avatar ? `<img src="${escapeHtml(k.avatar)}" alt="" loading="lazy">` : `<div class="ava"></div>`}
          <div style="flex:1;min-width:0">
            <div class="n">${escapeHtml(k.name)} <span style="color:var(--mxv-faint);font-size:11px">${k.opinion_count} 观点</span></div>
            <div class="mini"><div class="b" style="width:${Math.round((b / tot) * 100)}%"></div>
              <div class="s" style="width:${Math.round((s / tot) * 100)}%"></div></div>
            <div class="tags">${k.bull_names && k.bull_names.length ? `<span style="color:var(--mxv-bull)">▲</span> ${escapeHtml(k.bull_names.slice(0, 4).join("、"))}` : ""}
              ${k.bear_names && k.bear_names.length ? `<br><span style="color:var(--mxv-bear)">▼</span> ${escapeHtml(k.bear_names.slice(0, 4).join("、"))}` : ""}</div>
          </div>
        </div>`;
      }).join("");
      kols.innerHTML = `<h3 style="margin:0 0 8px;color:var(--mxv-accent);font-size:14px">大V观点总览</h3>` +
        `<div class="mxv-kols">${cards || `<div class="mxv-empty">暂无大V观点</div>`}</div>`;
    }
  }

  function mxvCloseDrawer() {
    const mask = document.querySelector(".mxv-drawer-mask");
    const drawer = document.querySelector(".mxv-drawer");
    if (mask) mask.remove();
    if (drawer) drawer.remove();
    _mxv.drawer = null;
  }

  function mxvBadge(direction, action) {
    const d = direction === "bull" ? `<span class="mxv-badge bull">↑看多</span>`
      : direction === "bear" ? `<span class="mxv-badge bear">↓看空</span>`
      : `<span class="mxv-badge neutral">中性</span>`;
    return d + (action ? ` <span class="mxv-badge act">${escapeHtml(action)}</span>` : "");
  }

  function mxvEvidenceHtml(ev) {
    return (ev || []).map((e) => {
      window._mxvPosts.push({ id: e.post_id, kol_name: e.author, published_at: e.time,
        content: e.content, detail: "", tags: [] });
      return `<div class="ev">
        <div>${escapeHtml(e.author)} · ${escapeHtml((e.time || "").slice(5, 16))}</div>
        <div class="c">${escapeHtml(e.content)}</div>
        <button class="raw" onclick="openRawModal(${e.post_id}, 'MX原始消息')">查看原始消息</button>
      </div>`;
    }).join("");
  }

  function mxvDrawerShell(title, subHtml) {
    return `
      <div class="mxv-drawer-mask" onclick="mxvCloseDrawer()"></div>
      <aside class="mxv-drawer" role="dialog" aria-label="${escapeHtml(title)}">
        <button class="close" onclick="mxvCloseDrawer()" aria-label="关闭">✕</button>
        <h3 id="mxv-drawer-title">${escapeHtml(title)}</h3>
        <div id="mxv-drawer-body">${subHtml || `<div class="mxv-empty">加载中…</div>`}</div>
      </aside>`;
  }

  function mxvTimelineListHtml(timeline) {
    return (timeline || []).map((op) => `
      <div class="mxv-op">
        <div class="head">
          ${op.avatar ? `<img class="ava" src="${escapeHtml(op.avatar)}" alt="">` : `<div class="ava"></div>`}
          <span class="who">${escapeHtml(op.kol_name)}</span>
          ${mxvBadge(op.direction, op.action)}
          ${(_mxv.drawer && _mxv.drawer.mode === "kol" && op.target_name) ? `<span style="color:var(--mxv-text);font-size:12px">${escapeHtml(op.target_name)}</span>` : ""}
          <span class="when">快照 ${escapeHtml(op.snapshot_at)} · ${escapeHtml((op.occurred_at || "").slice(11, 16))}</span>
        </div>
        ${op.summary ? `<p class="sum">${escapeHtml(op.summary)}</p>` : ""}
        ${op.evidence && op.evidence.length ? `<details class="mxv-op-evidence">
          <summary>依据消息（${op.evidence.length}）</summary>${mxvEvidenceHtml(op.evidence)}</details>` : ""}
      </div>`).join("") || `<div class="mxv-empty">该快照前暂无观点</div>`;
  }

  async function mxvOpenTarget(type, name) {
    _mxv.drawer = { mode: "target", type, name, title: name };
    const slot = document.getElementById("mxv-drawer-slot");
    if (!slot) return;
    slot.innerHTML = mxvDrawerShell(name);
    try {
      const data = await api(`/api/mx-views/target?type=${type}&name=${encodeURIComponent(name)}&day=${encodeURIComponent(_mxv.day)}&at=${encodeURIComponent(_mxv.at || "")}`);
      if (_mxv.drawer && _mxv.drawer.name !== name) return;
      const body = document.getElementById("mxv-drawer-body");
      if (!body) return;
      const net = data.bull.count - data.bear.count;
      body.innerHTML = `
        <div style="margin:6px 0 10px">
          <span class="mxv-net ${net > 0 ? "bull" : net < 0 ? "bear" : "flat"}" style="font-size:15px">净多空 ${net > 0 ? "+" : ""}${net}</span>
          <span style="color:var(--mxv-faint);font-size:12px;margin-left:8px">${data.bull.count} 多 / ${data.bear.count} 空 · 截至 ${escapeHtml(_mxv.at || "")}</span>
        </div>
        <div style="display:flex;gap:12px;margin-bottom:8px;font-size:13px">
          <div><span style="color:var(--mxv-bull)">▲ 看多 ${data.bull.count}</span>
            <span style="color:var(--mxv-muted)">　${escapeHtml(data.bull.kols.map((k) => k.name).slice(0, 8).join("、"))}</span></div>
        </div>
        <div style="display:flex;gap:12px;margin-bottom:8px;font-size:13px">
          <div><span style="color:var(--mxv-bear)">▼ 看空 ${data.bear.count}</span>
            <span style="color:var(--mxv-muted)">　${escapeHtml(data.bear.kols.map((k) => k.name).slice(0, 8).join("、"))}</span></div>
        </div>
        <div style="color:var(--mxv-accent);font-size:13px;margin:10px 0 4px">观点时间线（操作时间点已标金）</div>
        ${mxvTimelineListHtml(data.timeline)}`;
    } catch (err) {
      const body = document.getElementById("mxv-drawer-body");
      if (body) body.innerHTML = `<div class="mxv-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  async function mxvOpenKol(kolId) {
    _mxv.drawer = { mode: "kol", kolId, title: `大V #${kolId}` };
    const slot = document.getElementById("mxv-drawer-slot");
    if (!slot) return;
    slot.innerHTML = mxvDrawerShell("大V观点");
    try {
      const data = await api(`/api/mx-views/kol/${kolId}?day=${encodeURIComponent(_mxv.day)}&at=${encodeURIComponent(_mxv.at || "")}`);
      if (!_mxv.drawer || _mxv.drawer.kolId !== kolId) return;
      const body = document.getElementById("mxv-drawer-body");
      if (!body) return;
      _mxv.drawer.title = data.kol.name;
      const h = document.getElementById("mxv-drawer-title");
      if (h) h.textContent = data.kol.name;
      body.innerHTML = `
        <div style="margin:6px 0 10px;display:flex;gap:10px;align-items:center">
          ${data.kol.avatar ? `<img src="${escapeHtml(data.kol.avatar)}" style="width:34px;height:34px;border-radius:50%" alt="">` : ""}
          <b style="color:#fff">${escapeHtml(data.kol.name)}</b>
          <span style="color:var(--mxv-faint);font-size:12px">${data.timeline.length} 条观点 · 截至 ${escapeHtml(_mxv.at || "")}</span>
        </div>
        ${mxvTimelineListHtml(data.timeline)}`;
    } catch (err) {
      const body = document.getElementById("mxv-drawer-body");
      if (body) body.innerHTML = `<div class="mxv-empty">${escapeHtml(err.message)}</div>`;
    }
  }

  function mxvOpenTargetAt(i) { const t = window._mxvTargets[i]; if (t) mxvOpenTarget(t.type, t.name); }

  function mxvRenderDrawer() { /* 抽屉按需打开；换快照时若开着则原位刷新 */
    if (!_mxv.drawer) return;
    if (_mxv.drawer.mode === "target") mxvOpenTarget(_mxv.drawer.type, _mxv.drawer.name);
    else if (_mxv.drawer.mode === "kol") mxvOpenKol(_mxv.drawer.kolId);
  }

  // ---------- 管理端：admin/mx-views ----------
  let _mxvAdmin = { pollTimer: null, docClick: null, dirty: false };

  const MXVA_INTERVALS = [1, 2, 3, 5, 10, 15, 20, 30, 60];

  function mxvHhmmToMin(t) {
    const m = /^(\d{1,2}):(\d{2})$/.exec(String(t || "").trim());
    return m ? Number(m[1]) * 60 + Number(m[2]) : null;
  }

  // 与后端 resolve_schedule 同规则：段起止都生成 + extra_times，升序去重；bad = 未填完整的段下标
  function mxvResolveScheduleLocal(cfg) {
    const set = new Set();
    const bad = [];
    (cfg.segments || []).forEach((seg, i) => {
      const s = mxvHhmmToMin(seg.start), e = mxvHhmmToMin(seg.end);
      const itv = Math.floor(Number(seg.interval_min) || 0);
      if (s == null || e == null || itv <= 0) { bad.push(i + 1); return; }
      for (let t = s; t <= e; t += itv) {
        set.add(`${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`);
      }
    });
    (cfg.extra_times || []).forEach((t) => { if (mxvHhmmToMin(t) != null) set.add(String(t).trim()); });
    return { times: [...set].sort(), bad };
  }

  function mxvAdminMarkDirty() {
    _mxvAdmin.dirty = true;
    const hint = $("#mxva-save-hint"), discard = $("#mxva-discard"), save = $("#mxva-save");
    if (hint) { hint.textContent = "有未保存的更改"; hint.classList.add("dirty"); }
    if (discard) discard.hidden = false;
    if (save) save.disabled = false;
  }

  function mxvAdminMarkClean() {
    _mxvAdmin.dirty = false;
    const hint = $("#mxva-save-hint"), discard = $("#mxva-discard"), save = $("#mxva-save");
    if (hint) { hint.textContent = "更改保存后生效"; hint.classList.remove("dirty"); }
    if (discard) discard.hidden = true;
    if (save) save.disabled = true;
  }

  // ---- 快照时刻表（结构化编辑器） ----
  function mxvAdminExtraChipsHtml() {
    return (_mxvAdmin.schedule.extra_times || []).map((t, i) =>
      `<span class="mxva-tag">${escapeHtml(t)}<button type="button" class="mxva-tag-x"
        data-extra-remove="${i}" aria-label="删除 ${escapeHtml(t)}">×</button></span>`).join("")
      || `<span class="muted">无</span>`;
  }

  function mxvAdminPreviewHtml() {
    const { times, bad } = mxvResolveScheduleLocal(_mxvAdmin.schedule);
    const chips = times.map((t) =>
      `<span class="mxva-time-chip${["12:00", "16:00"].includes(t) ? " gold" : ""}">${t}</span>`).join("");
    return `
      <div class="mxva-preview-count">${times.length
        ? `共 <b>${times.length}</b> 个快照/天`
        : `<span class="mxva-warn">⚠ 无法解析出任何快照时刻，保存前请修正</span>`}</div>
      ${bad.length ? `<div class="mxva-warn">⚠ 第 ${bad.join("、")} 段时间未填完整，已忽略</div>` : ""}
      <div class="mxva-time-chips">${chips || `<span class="muted">—</span>`}</div>`;
  }

  function mxvAdminScheduleCardHtml() {
    const segs = _mxvAdmin.schedule.segments || [];
    const rows = segs.map((seg, i) => {
      const itv = Math.floor(Number(seg.interval_min) || 0);
      const itvList = MXVA_INTERVALS.includes(itv) ? MXVA_INTERVALS : [...MXVA_INTERVALS, itv].sort((a, b) => a - b);
      return `
      <div class="mxva-seg-row">
        <input type="time" class="form-control" value="${escapeHtml(seg.start)}" data-seg="${i}" data-field="start" aria-label="时段${i + 1}开始">
        <span class="mxva-seg-arrow">→</span>
        <input type="time" class="form-control" value="${escapeHtml(seg.end)}" data-seg="${i}" data-field="end" aria-label="时段${i + 1}结束">
        <span class="mxva-seg-every">每</span>
        <select class="form-control" data-seg="${i}" data-field="interval_min" aria-label="时段${i + 1}快照间隔">
          ${itvList.map((m) => `<option value="${m}" ${m === itv ? "selected" : ""}>${m} 分钟</option>`).join("")}
        </select>
        <button type="button" class="btn-sm danger" data-seg-remove="${i}" title="删除该时段" aria-label="删除时段${i + 1}">✕</button>
      </div>`;
    }).join("");
    return `
      <div class="mxva-sub"><b>交易时段</b><span class="muted">段起点与终点都会生成快照</span></div>
      <div id="mxva-seg-list">${rows || `<div class="muted">暂无时段，点「＋ 添加时段」。</div>`}</div>
      <div class="mxva-row-gap"><button type="button" class="btn-sm" onclick="mxvAdminSegAdd()">＋ 添加时段</button></div>
      <div class="mxva-sub"><b>固定时刻</b><span class="muted">午休 / 收盘总结等额外快照点</span></div>
      <div class="mxva-extra-row">
        <div class="mxva-chips" id="mxva-extra-list">${mxvAdminExtraChipsHtml()}</div>
        <input type="time" id="mxva-extra-time" class="form-control" aria-label="新增固定时刻">
        <button type="button" class="btn-sm" onclick="mxvAdminExtraAdd()">添加</button>
      </div>
      <div class="mxva-sub"><b>解析结果</b><span class="muted">实时预览，改完即见</span></div>
      <div id="mxva-preview-box">${mxvAdminPreviewHtml()}</div>
      <p class="mxva-note">每日首个快照的消息窗口固定从 09:15（集合竞价）开始，不可修改；跨午休时段会照常生成快照。</p>`;
  }

  function mxvAdminRefreshSchedule() {
    const box = $("#mxva-schedule-body");
    if (!box) return;
    box.innerHTML = mxvAdminScheduleCardHtml();
    mxvAdminBindSchedule();
  }

  function mxvAdminSegAdd() {
    if (!_mxvAdmin.schedule.segments) _mxvAdmin.schedule.segments = [];
    _mxvAdmin.schedule.segments.push({ start: "13:00", end: "15:00", interval_min: 10 });
    mxvAdminMarkDirty();
    mxvAdminRefreshSchedule();
  }

  function mxvAdminSegRemove(i) {
    _mxvAdmin.schedule.segments.splice(i, 1);
    mxvAdminMarkDirty();
    mxvAdminRefreshSchedule();
  }

  function mxvAdminExtraAdd() {
    const input = $("#mxva-extra-time");
    const t = (input && input.value || "").trim();
    if (!t) { flash("请先选一个时刻", "error"); return; }
    if (!_mxvAdmin.schedule.extra_times) _mxvAdmin.schedule.extra_times = [];
    if (_mxvAdmin.schedule.extra_times.includes(t)) { flash("该时刻已存在", "error"); return; }
    _mxvAdmin.schedule.extra_times.push(t);
    _mxvAdmin.schedule.extra_times.sort();
    mxvAdminMarkDirty();
    mxvAdminRefreshSchedule();
  }

  function mxvAdminScheduleReset() {
    _mxvAdmin.schedule = JSON.parse(JSON.stringify(_mxvAdmin.scheduleDefault || { segments: [], extra_times: [] }));
    mxvAdminMarkDirty();
    mxvAdminRefreshSchedule();
  }

  function mxvAdminBindSchedule() {
    const list = $("#mxva-seg-list");
    if (list) {
      list.oninput = (e) => {
        const el = e.target;
        if (el.dataset.seg === undefined) return;
        const seg = _mxvAdmin.schedule.segments[Number(el.dataset.seg)];
        if (!seg) return;
        seg[el.dataset.field] = el.dataset.field === "interval_min" ? Number(el.value) || 0 : el.value;
        mxvAdminMarkDirty();
        const pv = $("#mxva-preview-box");
        if (pv) pv.innerHTML = mxvAdminPreviewHtml();
      };
      list.onclick = (e) => {
        const btn = e.target.closest("[data-seg-remove]");
        if (btn) mxvAdminSegRemove(Number(btn.dataset.segRemove));
      };
    }
    const extra = $("#mxva-extra-list");
    if (extra) {
      extra.onclick = (e) => {
        const btn = e.target.closest("[data-extra-remove]");
        if (btn) {
          _mxvAdmin.schedule.extra_times.splice(Number(btn.dataset.extraRemove), 1);
          mxvAdminMarkDirty();
          mxvAdminRefreshSchedule();
        }
      };
    }
  }

  // ---- 分析大V范围（AI分析同款下拉多选） ----
  function mxvAdminKolCurrentIds() {
    return _mxvAdmin.selected ? Array.from(_mxvAdmin.selected) : (_mxvAdmin.cfg.kol_ids || []);
  }

  function mxvAdminKolName(id) {
    const k = (_mxvAdmin.kols || []).find((x) => x.id === id);
    return k ? k.name : `#${id}`;
  }

  function mxvAdminKolTriggerText() {
    const ids = mxvAdminKolCurrentIds();
    if (!ids.length) return "全部启用的大V（默认）";
    if (ids.length <= 3 && _mxvAdmin.kols.length) return ids.map((id) => mxvAdminKolName(id)).join("、");
    return `已选 ${ids.length} 个大V`;
  }

  function mxvAdminKolSync() {
    const t = $("#mxva-kol-selected-text"), note = $("#mxva-kol-note");
    if (t) t.textContent = mxvAdminKolTriggerText();
    if (note) {
      const n = mxvAdminKolCurrentIds().length;
      note.textContent = n
        ? `已指定 ${n} 个大V，只研判所选范围的发言`
        : "未指定范围：研判全部启用中的 MX 大V";
    }
  }

  function mxvAdminKolItemsHtml() {
    const q = (_mxvAdmin.kolSearch || "").trim().toLowerCase();
    const chosen = new Set(mxvAdminKolCurrentIds());
    const sorted = [...(_mxvAdmin.kols || [])].sort((a, b) => {
      const as = chosen.has(a.id), bs = chosen.has(b.id);
      if (as !== bs) return as ? -1 : 1;
      return 0;
    });
    const list = q ? sorted.filter((k) => String(k.name).toLowerCase().includes(q)) : sorted;
    return list.map((k) => {
      const checked = chosen.has(k.id);
      return `
      <div class="ai-kol-item${checked ? " checked" : ""}${k.enabled ? "" : " disabled"}" data-kol-id="${k.id}"
        role="checkbox" aria-checked="${checked}" tabindex="0">
        <input type="checkbox" class="ai-kol-checkbox" ${checked ? "checked" : ""} tabindex="-1">
        <div class="ai-kol-content">
          <span class="ai-kol-name">${escapeHtml(k.name)}</span>
          <span class="ai-kol-platform">${k.enabled ? "启用中" : "已停用"}</span>
        </div>
      </div>`;
    }).join("") || `<div class="mxva-kol-empty">无匹配的大V</div>`;
  }

  function mxvAdminKolRefreshItems() {
    const box = $("#mxva-kol-items");
    if (box) box.innerHTML = mxvAdminKolItemsHtml();
  }

  async function mxvAdminKolToggle() {
    const menu = $("#mxva-kol-menu");
    if (!menu) return;
    if (menu.classList.contains("open")) { menu.classList.remove("open"); return; }
    if (!_mxvAdmin.kols.length) {
      const data = await api("/api/admin/kols?platform=mx&limit=500").catch(() => ({ items: [] }));
      _mxvAdmin.kols = data.items || data.kols || [];
      mxvAdminKolSync();
    }
    mxvAdminKolRefreshItems();
    menu.classList.add("open");
    const search = $("#mxva-kol-search");
    if (search) search.focus();
  }

  function mxvAdminKolToggleItem(id) {
    if (!_mxvAdmin.selected) _mxvAdmin.selected = new Set(_mxvAdmin.cfg.kol_ids || []);
    if (_mxvAdmin.selected.has(id)) _mxvAdmin.selected.delete(id);
    else _mxvAdmin.selected.add(id);
    mxvAdminMarkDirty();
    mxvAdminKolSync();
    mxvAdminKolRefreshItems();
  }

  function mxvAdminKolAll() {
    const q = (_mxvAdmin.kolSearch || "").trim().toLowerCase();
    const list = q ? _mxvAdmin.kols.filter((k) => String(k.name).toLowerCase().includes(q)) : _mxvAdmin.kols;
    if (!_mxvAdmin.selected) _mxvAdmin.selected = new Set(_mxvAdmin.cfg.kol_ids || []);
    list.forEach((k) => _mxvAdmin.selected.add(k.id));
    mxvAdminMarkDirty();
    mxvAdminKolSync();
    mxvAdminKolRefreshItems();
  }

  function mxvAdminKolNone() {
    _mxvAdmin.selected = new Set();
    mxvAdminMarkDirty();
    mxvAdminKolSync();
    mxvAdminKolRefreshItems();
  }

  // ---- 题材参考表（标签式编辑） ----
  function mxvAdminHintsHtml() {
    return (_mxvAdmin.hints || []).map((h, i) =>
      `<span class="mxva-tag">${escapeHtml(h)}<button type="button" class="mxva-tag-x"
        data-hint-remove="${i}" aria-label="删除 ${escapeHtml(h)}">×</button></span>`).join("")
      || `<span class="muted">暂无题材；LLM 将自由输出并产生候选。</span>`;
  }

  function mxvAdminHintsRefresh() {
    const box = $("#mxva-hints-box");
    if (box) box.innerHTML = mxvAdminHintsHtml();
    const cnt = $("#mxva-hints-count");
    if (cnt) cnt.textContent = String((_mxvAdmin.hints || []).length);
  }

  function mxvAdminHintAdd() {
    const input = $("#mxva-hint-input");
    const v = (input && input.value || "").trim();
    if (!v) return;
    if ((_mxvAdmin.hints || []).includes(v)) { flash("该题材已在参考表", "error"); return; }
    _mxvAdmin.hints.push(v);
    if (input) input.value = "";
    mxvAdminMarkDirty();
    mxvAdminHintsRefresh();
  }

  function mxvAdminHintRemove(i) {
    _mxvAdmin.hints.splice(i, 1);
    mxvAdminMarkDirty();
    mxvAdminHintsRefresh();
  }

  function mxvAdminHintsReset() {
    _mxvAdmin.hints = [...(_mxvAdmin.hintsDefault || [])];
    mxvAdminMarkDirty();
    mxvAdminHintsRefresh();
  }

  // ---- 状态卡 ----
  function mxvAdminStatusHtml(s) {
    const last = s.last_batch;
    const bf = s.backfill || {};
    const stats = [
      ["游标", s.cursor || "—"],
      ["版本", s.version ?? "—"],
      ["今日 live 批次", s.batches_today ?? "—"],
      ["连续失败", s.fail_count ?? 0, Number(s.fail_count) > 0],
    ];
    return `
      <div class="mxva-stats">
        ${stats.map(([k, v, warn]) => `
          <div class="mxva-stat${warn ? " warn" : ""}">
            <span class="k">${escapeHtml(String(k))}</span><span class="v">${escapeHtml(String(v))}</span>
          </div>`).join("")}
      </div>
      <div class="mxva-lastbatch${last && last.status === "failed" ? " warn" : ""}">
        ${last ? `上批 ${escapeHtml(String(last.trading_day))} ${escapeHtml(String(last.snapshot_at))} ·
          <b>${escapeHtml(String(last.status))}</b>${last.error ? `<span class="mxva-err">${escapeHtml(String(last.error).slice(0, 160))}</span>` : ""}`
          : "尚无批次记录"}
      </div>
      ${bf.running ? `
        <div class="mxva-bf-run">
          <div class="row"><span>回填中 ${bf.done_windows}/${bf.total_windows}${bf.current_day ? `（${escapeHtml(String(bf.current_day))}）` : ""}</span>
            <button type="button" class="btn-sm danger" onclick="mxvAdminCancelBackfill()">取消回填</button></div>
          <div class="mxva-bf-bar"><div style="width:${bf.total_windows ? Math.round((bf.done_windows / bf.total_windows) * 100) : 0}%"></div></div>
          ${bf.error ? `<div class="mxva-err">${escapeHtml(String(bf.error))}</div>` : ""}
        </div>` : ""}`;
  }

  async function loadAdminMxViews() {
    let cfg, status;
    try {
      [cfg, status] = await Promise.all([
        api("/api/admin/mx-views/config"),
        api("/api/admin/mx-views/status"),
      ]);
    } catch (err) {
      if (!routeStillActive(currentAdminSeq())) return;
      $("#admin-body").innerHTML = emptyState("加载失败: " + err.message);
      return;
    }
    if (!routeStillActive(currentAdminSeq())) return;
    _mxvAdmin = {
      cfg,
      schedule: JSON.parse(JSON.stringify(cfg.schedule.config)),
      scheduleDefault: cfg.schedule_default || {},
      hints: [...cfg.topic_hints],
      hintsDefault: cfg.topic_hints_default || [],
      kols: [], selected: null, kolSearch: "",
      pollTimer: _mxvAdmin.pollTimer, docClick: _mxvAdmin.docClick, dirty: false,
    };
    $("#admin-body").innerHTML = `
    <section class="section-panel">
      <header class="section-head mxva-head">
        <div>
          <h2 class="section-title">MX 观点</h2>
          <p class="section-meta">交易时段按快照表批量研判 MX 大V消息，产出题材/个股多空观点与每日操作总结（页面 /mx-views）。</p>
        </div>
        <label class="mxva-switch" title="关闭即停止研判">
          <input type="checkbox" id="mxva-enabled" ${cfg.enabled ? "checked" : ""}>
          <span class="mxva-switch-ui"></span><span class="mxva-switch-text">启用研判</span>
        </label>
      </header>
      <div class="mxva-grid">
        <div class="mxva-card">
          <div class="mxva-card-head">
            <b>运行状态</b>
            <button type="button" class="btn-sm" onclick="mxvAdminRun()">手动跑一批</button>
          </div>
          <div id="mxva-status">${mxvAdminStatusHtml(status)}</div>
        </div>
        <div class="mxva-card">
          <div class="mxva-card-head">
            <b>快照时刻表</b>
            <button type="button" class="btn-sm" onclick="mxvAdminScheduleReset()">恢复默认</button>
          </div>
          <div id="mxva-schedule-body">${mxvAdminScheduleCardHtml()}</div>
        </div>
        <div class="mxva-card">
          <div class="mxva-card-head"><b>研判参数</b></div>
          <div class="mxva-param-grid">
            <label class="mxva-param">
              <span>单批消息上限</span>
              <input id="mxva-batch" class="form-control" type="number" min="1" value="${cfg.batch_size}">
              <span class="muted">每个快照窗口最多送研的消息条数</span>
            </label>
            <label class="mxva-param">
              <span>总结最小间隔（分钟）</span>
              <input id="mxva-interval" class="form-control" type="number" min="0" value="${cfg.summary_min_interval}">
              <span class="muted">0 = 每个快照都出一版「今日操作」总结</span>
            </label>
          </div>
        </div>
        <div class="mxva-card">
          <div class="mxva-card-head"><b>分析大V范围</b></div>
          <div class="mxva-kol-wrap ai-kol-dropdown">
            <div id="mxva-kol-trigger" class="ai-kol-dropdown-trigger" onclick="mxvAdminKolToggle()"
              role="button" aria-haspopup="listbox" tabindex="0">
              <span id="mxva-kol-selected-text" class="ai-kol-selected-text">${escapeHtml(mxvAdminKolTriggerText())}</span>
              <svg class="ai-kol-dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
            <div id="mxva-kol-menu" class="ai-kol-dropdown-menu mxva-kol-menu">
              <div class="mxva-kol-toolbar">
                <input id="mxva-kol-search" class="form-control" placeholder="搜索大V名称" aria-label="搜索大V">
                <button type="button" class="btn-sm" onclick="mxvAdminKolAll()" title="选中当前搜索结果里的大V">全选</button>
                <button type="button" class="btn-sm" onclick="mxvAdminKolNone()">清空</button>
              </div>
              <div id="mxva-kol-items" class="mxva-kol-items"><div class="mxva-kol-empty">展开时加载 MX 大V列表…</div></div>
            </div>
          </div>
          <p class="mxva-note" id="mxva-kol-note"></p>
        </div>
        <div class="mxva-card">
          <div class="mxva-card-head">
            <b>题材参考表</b><span class="muted">当前 <span id="mxva-hints-count">${_mxvAdmin.hints.length}</span> 个</span>
            <button type="button" class="btn-sm" onclick="mxvAdminHintsReset()">恢复默认</button>
          </div>
          <div class="mxva-chips mxva-chips-wrap" id="mxva-hints-box">${mxvAdminHintsHtml()}</div>
          <div class="mxva-chip-add">
            <input id="mxva-hint-input" class="form-control" placeholder="输入题材名后回车，如：固态电池" aria-label="新增题材">
            <button type="button" class="btn-sm" onclick="mxvAdminHintAdd()">添加</button>
          </div>
          <p class="mxva-note">LLM 优先输出这些名称；表外新题材会进「新题材候选」待你审核。</p>
        </div>
        <div class="mxva-card">
          <div class="mxva-card-head">
            <b>新题材候选</b>
            ${cfg.topic_candidates.length ? `
              <span class="mxva-head-ops">
                <button type="button" class="btn-sm" onclick="mxvAdminAdoptAll()">全部采纳</button>
                <button type="button" class="btn-sm" onclick="mxvAdminDismissAll()">全部忽略</button>
              </span>` : ""}
          </div>
          <div class="mxva-chips" id="mxva-cands">${cfg.topic_candidates.length ? cfg.topic_candidates.map((c) =>
            `<span class="mxva-tag">${escapeHtml(c)}
              <button type="button" class="btn-sm" onclick="mxvAdminAdopt('${escapeHtml(c)}')">采纳</button>
              <button type="button" class="btn-sm" onclick="mxvAdminDismiss('${escapeHtml(c)}')">忽略</button></span>`).join(" ")
            : `<span class="muted">暂无候选</span>`}</div>
        </div>
        <div class="mxva-card">
          <div class="mxva-card-head"><b>历史回填</b></div>
          <div class="mxva-toolbar-wrap">
            <input id="mxva-bf-from" class="form-control" type="date" aria-label="回填开始日期">
            <span class="muted">至</span>
            <input id="mxva-bf-to" class="form-control" type="date" aria-label="回填结束日期">
            <button type="button" class="btn-normal" onclick="mxvAdminStartBackfill()">开始回填</button>
          </div>
          <div class="mxva-row-gap">
            <span class="muted">快捷：</span>
            <button type="button" class="btn-sm" onclick="mxvAdminBfPreset(1)">昨天</button>
            <button type="button" class="btn-sm" onclick="mxvAdminBfPreset(3)">近3天</button>
            <button type="button" class="btn-sm" onclick="mxvAdminBfPreset(7)">近7天</button>
          </div>
          <p class="mxva-note">按当前快照时刻表把历史消息重新研判成快照（最多 30 天，进行中可取消）。</p>
        </div>
      </div>
      <div class="mxva-savebar">
        <span id="mxva-save-hint" class="mxva-save-hint">更改保存后生效</span>
        <button type="button" class="btn-sm" id="mxva-discard" onclick="mxvAdminResetConfig()" hidden>放弃更改</button>
        <button type="button" class="btn-normal" id="mxva-save" onclick="mxvAdminSaveConfig()" disabled>保存全部配置</button>
      </div>
    </section>`;
    mxvAdminKolSync();
    mxvAdminBind();
    mxvAdminStartProgressPoll();
  }

  function mxvAdminBind() {
    mxvAdminBindSchedule();
    // 大V下拉：点条目切换、搜索过滤、点外部收起
    const items = $("#mxva-kol-items");
    if (items) {
      items.onclick = (e) => {
        const it = e.target.closest(".ai-kol-item");
        if (it && it.dataset.kolId) mxvAdminKolToggleItem(Number(it.dataset.kolId));
      };
    }
    const search = $("#mxva-kol-search");
    if (search) {
      search.oninput = () => { _mxvAdmin.kolSearch = search.value; mxvAdminKolRefreshItems(); };
      search.onkeydown = (e) => { if (e.key === "Enter") e.preventDefault(); };
    }
    if (_mxvAdmin.docClick) document.removeEventListener("click", _mxvAdmin.docClick);
    _mxvAdmin.docClick = (e) => {
      if (!e.target.closest(".mxva-kol-wrap")) {
        const menu = document.querySelector(".mxva-kol-menu");
        if (menu) menu.classList.remove("open");
      }
    };
    document.addEventListener("click", _mxvAdmin.docClick);
    // 题材 chips：删除走委托
    const hintsBox = $("#mxva-hints-box");
    if (hintsBox) {
      hintsBox.onclick = (e) => {
        const btn = e.target.closest("[data-hint-remove]");
        if (btn) mxvAdminHintRemove(Number(btn.dataset.hintRemove));
      };
    }
    const hintInput = $("#mxva-hint-input");
    if (hintInput) {
      hintInput.onkeydown = (e) => {
        if (e.key === "Enter") { e.preventDefault(); mxvAdminHintAdd(); }
      };
    }
    ["mxva-batch", "mxva-interval", "mxva-enabled"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.oninput = () => mxvAdminMarkDirty();
    });
  }

  async function mxvAdminSaveConfig() {
    const { times } = mxvResolveScheduleLocal(_mxvAdmin.schedule);
    if (!times.length) { flash("快照时刻表无法解析出任何时刻，请先修正", "error"); return; }
    const body = {
      enabled: $("#mxva-enabled") ? $("#mxva-enabled").checked : false,
      schedule: _mxvAdmin.schedule,
      batch_size: Number($("#mxva-batch") && $("#mxva-batch").value) || 600,
      summary_min_interval: Number($("#mxva-interval") && $("#mxva-interval").value) || 0,
      topic_hints: _mxvAdmin.hints,
    };
    if (_mxvAdmin.selected) body.kol_ids = Array.from(_mxvAdmin.selected);
    try {
      await api("/api/admin/mx-views/config", { method: "PUT", body: JSON.stringify(body) });
      flash("配置已保存");
      loadAdminMxViews();
    } catch (err) {
      flash(err.message, "error");
    }
  }

  function mxvAdminResetConfig() {
    loadAdminMxViews(); // 重拉配置即放弃未保存更改
  }

  async function mxvAdminAdopt(name) {
    try {
      await api("/api/admin/mx-views/topic-candidates/adopt", { method: "POST", body: JSON.stringify({ name }) });
      flash(`已采纳「${name}」`);
      loadAdminMxViews();
    } catch (err) { flash(err.message, "error"); }
  }

  async function mxvAdminDismiss(name) {
    await api("/api/admin/mx-views/topic-candidates/dismiss", { method: "POST", body: JSON.stringify({ name }) }).catch(() => {});
    loadAdminMxViews();
  }

  async function mxvAdminAdoptAll() {
    const cands = [...(_mxvAdmin.cfg.topic_candidates || [])];
    if (!cands.length) return;
    try {
      await Promise.all(cands.map((name) =>
        api("/api/admin/mx-views/topic-candidates/adopt", { method: "POST", body: JSON.stringify({ name }) })));
      flash(`已采纳 ${cands.length} 个候选题材`);
      loadAdminMxViews();
    } catch (err) { flash(err.message, "error"); }
  }

  async function mxvAdminDismissAll() {
    const cands = [...(_mxvAdmin.cfg.topic_candidates || [])];
    if (!cands.length) return;
    await Promise.all(cands.map((name) =>
      api("/api/admin/mx-views/topic-candidates/dismiss", { method: "POST", body: JSON.stringify({ name }) }).catch(() => {})));
    flash("已忽略全部候选");
    loadAdminMxViews();
  }

  function mxvAdminStartBackfill() {
    const dayFrom = $("#mxva-bf-from") && $("#mxva-bf-from").value;
    const dayTo = $("#mxva-bf-to") && $("#mxva-bf-to").value;
    if (!dayFrom || !dayTo) { flash("请选择回填日期范围", "error"); return; }
    api("/api/admin/mx-views/backfill", { method: "POST", body: JSON.stringify({ day_from: dayFrom, day_to: dayTo }) })
      .then(() => { flash("回填已启动"); })
      .catch((err) => flash(err.message, "error"));
  }

  function mxvAdminCancelBackfill() {
    api("/api/admin/mx-views/backfill/cancel", { method: "POST" }).then(() => flash("已请求取消")).catch(() => {});
  }

  function mxvAdminRun() {
    api("/api/admin/mx-views/run", { method: "POST" })
      .then(() => flash("已触发手动跑批"))
      .catch((err) => flash(err.message, "error"));
  }

  function mxvAdminBfPreset(days) {
    const fmt = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - days);
    const f = $("#mxva-bf-from"), t = $("#mxva-bf-to");
    if (f) f.value = fmt(from);
    if (t) t.value = fmt(to);
  }

  let _mxvProgressTimer = null;
  function mxvAdminStartProgressPoll() {
    if (_mxvProgressTimer) clearInterval(_mxvProgressTimer);
    _mxvProgressTimer = setInterval(async () => {
      const el = $("#mxva-status");
      if (!el) { clearInterval(_mxvProgressTimer); _mxvProgressTimer = null; return; }
      const s = await api("/api/admin/mx-views/status").catch(() => null);
      if (s) el.innerHTML = mxvAdminStatusHtml(s);
    }, 3000);
  }

  return {
    mxvTeardown,
    renderMxViews,
    mxvPickDay,
    mxvRefreshLatest,
    mxvStep,
    mxvApplySnapshot,
    mxvGoLatest,
    mxvOpenTargetAt,
    mxvOpenKol,
    mxvCloseDrawer,
    loadAdminMxViews,
    mxvAdminKolToggle,
    mxvAdminKolAll,
    mxvAdminKolNone,
    mxvAdminSegAdd,
    mxvAdminScheduleReset,
    mxvAdminExtraAdd,
    mxvAdminHintAdd,
    mxvAdminHintsReset,
    mxvAdminAdopt,
    mxvAdminDismiss,
    mxvAdminAdoptAll,
    mxvAdminDismissAll,
    mxvAdminRun,
    mxvAdminBfPreset,
    mxvAdminStartBackfill,
    mxvAdminCancelBackfill,
    mxvAdminSaveConfig,
    mxvAdminResetConfig,
  };
}
