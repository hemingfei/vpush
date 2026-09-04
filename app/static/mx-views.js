// MX 平台大V实时观点页（/mx-views）——页面级暗色终端，样式全部 .mxv- 前缀
window._mxvPosts = []; // 证据原帖缓存，供 app.js openRawModal 查找
const _mxv = { seq: 0, day: null, days: [], snapshots: [], at: null, payload: null,
  atLatest: true, hasNew: false, es: null, pollTimer: null, clockTimer: null, drawer: null };

function mxvTeardown() {
  if (_mxv.es) { try { _mxv.es.close(); } catch (e) {} _mxv.es = null; }
  if (_mxv.pollTimer) { clearInterval(_mxv.pollTimer); _mxv.pollTimer = null; }
  if (_mxv.clockTimer) { clearInterval(_mxv.clockTimer); _mxv.clockTimer = null; }
  const d = document.querySelector(".mxv-drawer-mask"); if (d) d.remove();
  const dr = document.querySelector(".mxv-drawer"); if (dr) dr.remove();
  Object.assign(_mxv, { day: null, payload: null, at: null, drawer: null, hasNew: false });
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
      if (!_mxv.pollTimer) _mxv.pollTimer = setInterval(() => { if (_mxv.atLatest) mxvRefreshLatest(); }, 60000);
    };
    es.onopen = () => { if (_mxv.pollTimer) { clearInterval(_mxv.pollTimer); _mxv.pollTimer = null; } };
    _mxv.es = es;
  } catch (e) { /* SSE 不可用时静默，靠手动刷新 */ }
}

async function mxvRefreshLatest() {
  if (!routeStillActive(_mxv.seq)) return;
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
      <span class="mxv-pill"><span class="mxv-dot sse"></span>SSE</span>
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
      <div class="mxv-tl-head" style="left:${left}%;${active ? "" : "display:none"}" id="mxv-tl-head">
        <div class="t">${s.snapshot_at}</div><div class="s"></div></div>`;
  }).join("");
  const idx = snaps.findIndex((s) => s.snapshot_at === _mxv.at);
  const doneW = n <= 1 ? 100 : (idx / (n - 1)) * 100;
  const prev = idx > 0 ? snaps[idx - 1] : null;
  const diff = mxvDiffText(_mxv.snapshots[idx], prev);
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

function mxvDiffText(cur, prev) {
  if (!cur || !_mxv.payload) return "";
  const prevMap = {};
  ((prev && prev.payload) ? prev.payload.topics : []).forEach((t) => { prevMap[t.name] = t.net; });
  const parts = [];
  (_mxv.payload.topics || []).slice(0, 3).forEach((t) => {
    if (prevMap[t.name] !== undefined && t.net !== prevMap[t.name]) {
      parts.push(`${escapeHtml(t.name)} 净多空 ${prevMap[t.name]}→${t.net}`);
    }
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
    const label = it.action ? `${it.name} ${it.action}×${it.count || ""}` :
      `${it.name}${it.count ? ` ×${it.count}` : ""}`;
    const cls = it.direction === "bear" ? "bear" : "bull";
    const target = it.type === "stock" ? "stock" : "topic";
    return `<span class="mxv-chip ${cls}" onclick="mxvOpenTarget('${target}', '${escapeHtml(it.name)}')">${escapeHtml(label)}</span>`;
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
    const topicRows = (p.topics || []).map((t, i) => `
      <div class="mxv-row" onclick="mxvOpenTarget('topic', '${escapeHtml(t.name)}')">
        <span class="rank">${i + 1}</span><span class="name">${escapeHtml(t.name)}</span>
        ${mxvRatioHtml(t.bull, t.bear)}
        <span class="mxv-net ${t.net > 0 ? "bull" : t.net < 0 ? "bear" : "flat"}">${t.bull}多/${t.bear}空</span>
        ${mxvMomo(t.momentum)}
        <span class="mxv-latest-time">${escapeHtml((t.latest_at || "").slice(11, 16))}</span>
      </div>`).join("");
    const stockRows = (p.stocks || []).map((s, i) => {
      const actions = Object.entries(s.actions || {}).map(([k, v]) => `${k}×${v}`).join(" ");
      return `
      <div class="mxv-row" onclick="mxvOpenTarget('stock', '${escapeHtml(s.name)}')">
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
function mxvRenderDrawer() { /* Task 14 填充：右侧抽屉 */ }
