// MX 平台大V实时观点页（/mx-views）——页面级暗色终端，样式全部 .mxv- 前缀
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
let _mxvAdmin = {};

async function loadAdminMxViews() {
  let cfg, status;
  try {
    [cfg, status] = await Promise.all([
      api("/api/admin/mx-views/config"),
      api("/api/admin/mx-views/status"),
    ]);
  } catch (err) {
    if (!routeStillActive(_adminRenderSeq)) return;
    $("#admin-body").innerHTML = emptyState("加载失败: " + err.message);
    return;
  }
  if (!routeStillActive(_adminRenderSeq)) return;
  _mxvAdmin = { cfg, kols: [] };
  $("#admin-body").innerHTML = `
  <section class="section-panel">
    <header class="section-head"><div>
      <h2 class="section-title">MX 观点</h2>
      <p class="section-meta">交易时段按快照表批量研判 MX 大V消息，产出题材/个股多空观点与每日操作总结（页面 /mx-views）。</p>
    </div></header>
    <div style="display:grid;gap:14px">
      <div class="settings-panel">
        <label style="display:flex;gap:8px;align-items:center">
          <input type="checkbox" id="mxv-enabled" ${cfg.enabled ? "checked" : ""}>
          <b>启用研判</b><span class="muted">（仅周一~周五，节假日不判；关闭即停）</span>
        </label>
      </div>
      <div class="settings-panel">
        <b>快照时刻表</b>
        <p class="muted" style="margin:4px 0">JSON：segments（时段+间隔分钟，起止都生成）+ extra_times；首窗固定 09:15→09:20。当前解析：</p>
        <textarea id="mxv-schedule" class="form-control" rows="6">${escapeHtml(JSON.stringify(cfg.schedule.config, null, 1))}</textarea>
        <p class="muted">解析结果（${cfg.schedule.resolved_times.length} 个）：${cfg.schedule.resolved_times.join(" ")}</p>
      </div>
      <div class="settings-panel">
        <b>批参数</b>
        <label>单批消息上限 <input id="mxv-batch" class="form-control" type="number" min="1" value="${cfg.batch_size}" style="width:110px"></label>
        <label>总结最小间隔（分钟，0=每快照一版） <input id="mxv-interval" class="form-control" type="number" min="0" value="${cfg.summary_min_interval}" style="width:110px"></label>
      </div>
      <div class="settings-panel">
        <b>分析大V范围</b>
        <p class="muted">已选 ${cfg.kol_ids.length} 个；<b>空 = 全部启用的 MX 房间</b>。<button class="btn-sm" onclick="mxvAdminToggleKols()">展开/收起选择</button></p>
        <div id="mxv-kols" style="display:none"></div>
      </div>
      <div class="settings-panel">
        <b>题材参考表</b>
        <p class="muted">每行一个题材；LLM 优先输出这些名称，表外新题材会进下方候选。</p>
        <textarea id="mxv-hints" class="form-control" rows="6">${escapeHtml(cfg.topic_hints.join("\n"))}</textarea>
      </div>
      <div class="settings-panel">
        <b>新题材候选</b>
        <div id="mxv-cands">${cfg.topic_candidates.length ? cfg.topic_candidates.map((c) =>
          `<span class="cat-chip">${escapeHtml(c)}
            <button class="btn-sm" onclick="mxvAdminAdopt('${escapeHtml(c)}')">采纳</button>
            <button class="btn-sm" onclick="mxvAdminDismiss('${escapeHtml(c)}')">忽略</button></span>`).join(" ")
          : `<span class="muted">暂无候选</span>`}</div>
      </div>
      <div class="settings-panel">
        <b>运行</b>
        <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
          <button class="btn-normal" onclick="mxvAdminRun()">手动跑一批</button>
          <input id="mxv-bf-from" class="form-control" type="date" style="width:150px">
          <input id="mxv-bf-to" class="form-control" type="date" style="width:150px">
          <button class="btn-normal" onclick="mxvAdminStartBackfill()">回填</button>
          <button class="btn-sm" onclick="mxvAdminCancelBackfill()">取消回填</button>
          <span id="mxv-bf-progress" class="muted"></span>
        </div>
        <p id="mxv-status" class="muted" style="margin:8px 0 0">${mxvAdminStatusLine(status)}</p>
      </div>
      <div><button class="btn-normal" onclick="mxvAdminSaveConfig()">保存全部配置</button></div>
    </div>
  </section>`;
  mxvAdminStartProgressPoll();
}

function mxvAdminStatusLine(s) {
  return `游标 ${s.cursor} · 版本 ${s.version} · 今日 live 批次 ${s.batches_today} · 连续失败 ${s.fail_count}` +
    (s.last_batch ? ` · 上批 ${s.last_batch.trading_day} ${s.last_batch.snapshot_at} ${s.last_batch.status}${s.last_batch.error ? "：" + (s.last_batch.error || "").slice(0, 120) : ""}` : "");
}

async function mxvAdminSaveConfig() {
  let schedule;
  try {
    schedule = JSON.parse($("#mxv-schedule").value);
  } catch (e) {
    flash("快照时刻表不是合法 JSON", "error");
    return;
  }
  try {
    await api("/api/admin/mx-views/config", {
      method: "PUT",
      body: JSON.stringify({
        enabled: $("#mxv-enabled").checked,
        schedule,
        batch_size: Number($("#mxv-batch").value) || 600,
        summary_min_interval: Number($("#mxv-interval").value) || 0,
        kol_ids: _mxvAdmin.selected ? Array.from(_mxvAdmin.selected) : undefined,
        topic_hints: $("#mxv-hints").value.split("\n").map((x) => x.trim()).filter(Boolean),
      }),
    });
    flash("配置已保存");
    loadAdminMxViews();
  } catch (err) {
    flash(err.message, "error");
  }
}

async function mxvAdminToggleKols() {
  const box = $("#mxv-kols");
  if (box.style.display !== "none") { box.style.display = "none"; return; }
  if (!_mxvAdmin.kols.length) {
    const data = await api("/api/admin/kols?platform=mx&limit=300").catch(() => ({ items: [] }));
    _mxvAdmin.kols = data.items || data.kols || [];
    _mxvAdmin.selected = new Set(_mxvAdmin.cfg.kol_ids || []);
  }
  box.style.display = "block";
  box.innerHTML = _mxvAdmin.kols.map((k) => `
    <label style="display:inline-flex;gap:4px;align-items:center;margin:2px 10px 2px 0">
      <input type="checkbox" value="${k.id}" ${_mxvAdmin.selected.has(k.id) ? "checked" : ""}
        onchange="this.checked ? _mxvAdmin.selected.add(${k.id}) : _mxvAdmin.selected.delete(${k.id})">
      ${escapeHtml(k.name)}${k.enabled ? "" : "（停用）"}
    </label>`).join("");
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

function mxvAdminStartBackfill() {
  const dayFrom = $("#mxv-bf-from").value, dayTo = $("#mxv-bf-to").value;
  if (!dayFrom || !dayTo) { flash("请选择回填日期范围", "error"); return; }
  api("/api/admin/mx-views/backfill", { method: "POST", body: JSON.stringify({ day_from: dayFrom, day_to: dayTo }) })
    .then(() => { flash("回填已启动"); mxvAdminStartProgressPoll(); })
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

let _mxvProgressTimer = null;
function mxvAdminStartProgressPoll() {
  if (_mxvProgressTimer) clearInterval(_mxvProgressTimer);
  _mxvProgressTimer = setInterval(async () => {
    const el = $("#mxv-bf-progress");
    const st = $("#mxv-status");
    if (!el || !st) { clearInterval(_mxvProgressTimer); _mxvProgressTimer = null; return; }
    const [p, s] = await Promise.all([
      api("/api/admin/mx-views/backfill/progress").catch(() => null),
      api("/api/admin/mx-views/status").catch(() => null),
    ]);
    if (p) el.textContent = p.running ? `回填中 ${p.done_windows}/${p.total_windows}${p.current_day ? "（" + p.current_day + "）" : ""}` : "";
    if (s) st.textContent = mxvAdminStatusLine(s);
  }, 3000);
}
