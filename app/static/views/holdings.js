// 持股研判页（/holdings）：顶部用户持股管理（个股/题材），下方最近一个月相关观点
// 聚合卡 + 时间流，SSE 版本变更增量上屏。样式全部 .hd- 前缀（holdings.css，跟随全局主题）
export function createHoldingsView(dependencies) {
  const {
    $, state, api, escapeHtml, setPageTitle, routeStillActive, flash,
  } = dependencies;

  window._hdTargets = []; // 聚合卡下标索引：onclick 传下标，避免标的名称注入 JS 字符串
  window._hdSug = []; // 输入建议下标索引，同上
  const _hd = {
    seq: 0, holdings: [], summary: [], items: [], maxId: 0,
    filter: null, // {type, name} 单标的筛选；null = 全部
    expanded: new Set(), es: null, sseOk: false, pollTimer: null,
    addType: "stock", sugTimer: null, editId: null,
    exhausted: false, loadingMore: false, freshIds: new Set(),
  };
  const PAGE_SIZE = 50;
  const HD_MAX = 30;
  const WINDOW_DAYS = 30;
  const SUG_LIMIT = 20;

  function hdTeardown() {
    if (_hd.es) { try { _hd.es.close(); } catch (e) {} _hd.es = null; }
    if (_hd.pollTimer) { clearInterval(_hd.pollTimer); _hd.pollTimer = null; }
    if (_hd.sugTimer) { clearTimeout(_hd.sugTimer); _hd.sugTimer = null; }
    Object.assign(_hd, {
      holdings: [], summary: [], items: [], maxId: 0, filter: null,
      expanded: new Set(), sseOk: false, editId: null,
      exhausted: false, loadingMore: false, freshIds: new Set(),
    });
  }

  function fmtTime(ts) {
    const s = String(ts || "");
    return s.length >= 16 ? s.slice(5, 16) : s; // "YYYY-MM-DD HH:MM:SS" → "MM-DD HH:MM"
  }

  function hdHolderQ() {
    return _hd.filter
      ? `&holder=${encodeURIComponent(`${_hd.filter.type}:${_hd.filter.name}`)}`
      : "";
  }

  function hdApplyViews(data) {
    _hd.summary = (data && data.summary && data.summary.targets) || [];
    _hd.maxId = (data && data.max_id) || _hd.maxId;
    _hd.items = (data && data.items) || [];
    _hd.exhausted = _hd.items.length < PAGE_SIZE;
  }

  async function renderHoldings(seq) {
    hdTeardown();
    _hd.seq = seq;
    setPageTitle("持股研判");
    $("#main").innerHTML = `<div class="hd-root"><div class="hd-empty">加载中…</div></div>`;
    try {
      const [holdings, views] = await Promise.all([
        api("/api/my/holdings"),
        api(`/api/my/holdings/views?limit=${PAGE_SIZE}${hdHolderQ()}`),
      ]);
      if (!routeStillActive(seq)) return;
      _hd.holdings = Array.isArray(holdings) ? holdings : [];
      hdApplyViews(views);
      hdRenderAll();
      hdEnsureSSE();
    } catch (err) {
      if (!routeStillActive(seq)) return;
      $("#main").innerHTML = `<div class="hd-root"><div class="hd-empty">加载失败: ${escapeHtml(err.message)}</div></div>`;
    }
  }

  // 持股增删改后的整页刷新（保持筛选）
  async function hdReload() {
    const seq = _hd.seq;
    try {
      const [holdings, views] = await Promise.all([
        api("/api/my/holdings"),
        api(`/api/my/holdings/views?limit=${PAGE_SIZE}${hdHolderQ()}`),
      ]);
      if (!routeStillActive(seq)) return;
      _hd.holdings = Array.isArray(holdings) ? holdings : [];
      hdApplyViews(views);
      hdRenderAll();
    } catch (err) {
      flash(`刷新失败: ${err.message}`, "error");
    }
  }

  async function hdReloadFeed() {
    try {
      const data = await api(`/api/my/holdings/views?limit=${PAGE_SIZE}${hdHolderQ()}`);
      if (!routeStillActive(_hd.seq)) return;
      hdApplyViews(data);
      hdRenderFeed();
    } catch (err) {
      flash(`刷新失败: ${err.message}`, "error");
    }
  }

  // SSE 版本变更：增量拉新插入顶部（响应同时带回重算后的全窗口聚合）
  async function hdIncRefresh() {
    if (!routeStillActive(_hd.seq)) return;
    try {
      const data = await api(`/api/my/holdings/views?limit=${PAGE_SIZE}&after_id=${_hd.maxId}${hdHolderQ()}`);
      if (!routeStillActive(_hd.seq)) return;
      _hd.summary = (data.summary && data.summary.targets) || [];
      _hd.maxId = data.max_id || _hd.maxId;
      const known = new Set(_hd.items.map((it) => it.id));
      const fresh = (data.items || []).filter((it) => !known.has(it.id));
      if (fresh.length) {
        fresh.forEach((it) => _hd.freshIds.add(it.id));
        _hd.items = fresh.concat(_hd.items);
        if (fresh.length >= PAGE_SIZE) _hd.exhausted = false;
        setTimeout(() => { // 高亮渐隐后摘掉 fresh 类，避免后续重渲染重播动画
          _hd.freshIds.clear();
          if (routeStillActive(_hd.seq)) hdRenderFeed();
        }, 2600);
      }
      hdRenderCards();
      hdRenderFeed();
    } catch (e) { /* 静默：下次版本变更/兜底轮询再试 */ }
  }

  function hdSseSync() {
    const dot = document.querySelector(".hd-dot.sse");
    if (dot) dot.classList.toggle("on", !!_hd.sseOk);
  }

  // 复用观点研判的版本号 SSE：新批次落库 → version 事件 → 增量拉相关观点
  function hdEnsureSSE() {
    if (!state.token || _hd.es) return;
    try {
      const es = new EventSource(`/api/mx-views/stream?token=${encodeURIComponent(state.token)}`);
      es.addEventListener("version", () => { hdIncRefresh(); });
      es.onerror = () => { // EventSource 自动重连；兜底 60s 轮询
        _hd.sseOk = false;
        hdSseSync();
        if (!_hd.pollTimer) _hd.pollTimer = setInterval(hdIncRefresh, 60000);
      };
      es.onopen = () => {
        _hd.sseOk = true;
        hdSseSync();
        if (_hd.pollTimer) { clearInterval(_hd.pollTimer); _hd.pollTimer = null; }
      };
      _hd.es = es;
    } catch (e) { /* SSE 不可用时静默 */ }
  }

  function hdRenderAll() {
    $("#main").innerHTML = `
      <div class="hd-root">
        <span class="hd-statusbar"><span class="hd-pill"><span class="hd-dot sse"></span>实时</span><span class="hd-pill">近 ${WINDOW_DAYS} 天</span></span>
        <section class="hd-panel" id="hd-manage"></section>
        <section class="hd-cards-wrap" id="hd-cards"></section>
        <section class="hd-feed" id="hd-feed"></section>
      </div>`;
    hdSseSync();
    hdRenderManage();
    hdRenderCards();
    hdRenderFeed();
  }

  function hdTypeBadge(t) {
    return `<span class="hd-badge ${t === "stock" ? "stock" : "topic"}">${t === "stock" ? "股" : "题"}</span>`;
  }

  function hdRenderManage() {
    const el = document.getElementById("hd-manage");
    if (!el) return;
    const n = _hd.holdings.length;
    const atMax = n >= HD_MAX;
    const rows = _hd.holdings.map((h) => {
      if (_hd.editId === h.id) {
        return `
        <div class="hd-item editing" data-holding-id="${h.id}">
          <div class="hd-edit-row">
            ${hdTypeBadge(h.target_type)}
            <input id="hd-edit-name-${h.id}" value="${escapeHtml(h.target_name)}" maxlength="40" aria-label="标的名称">
            <input id="hd-edit-note-${h.id}" value="${escapeHtml(h.note || "")}" maxlength="200" placeholder="备注" aria-label="备注">
          </div>
          <div class="hd-item-ops">
            <button type="button" class="hd-btn primary sm" onclick="hdEditSave(${h.id})">保存</button>
            <button type="button" class="hd-btn sm" onclick="hdEditCancel()">取消</button>
          </div>
        </div>`;
      }
      return `
      <div class="hd-item" data-holding-id="${h.id}">
        ${hdTypeBadge(h.target_type)}
        <span class="hd-name">${escapeHtml(h.target_name)}</span>
        <span class="hd-note">${escapeHtml(h.note || "")}</span>
        <span class="hd-item-ops">
          <button type="button" class="hd-btn sm" onclick="hdEditOpen(${h.id})">编辑</button>
          <button type="button" class="hd-btn sm danger" onclick="hdDelete(${h.id})">删除</button>
        </span>
      </div>`;
    }).join("");
    el.innerHTML = `
      <div class="hd-panel-head">
        <b>我的持股</b>
        <span class="hd-hint">${n}/${HD_MAX}${atMax ? " · 已达上限" : ""}</span>
      </div>
      <div class="hd-add">
        <div class="hd-seg" role="tablist">
          <button type="button" class="hd-seg-btn${_hd.addType === "stock" ? " on" : ""}" onclick="hdAddType('stock')">个股</button>
          <button type="button" class="hd-seg-btn${_hd.addType === "topic" ? " on" : ""}" onclick="hdAddType('topic')">题材</button>
        </div>
        <div class="hd-add-fields">
          <div class="hd-add-name">
            <input id="hd-add-input" autocomplete="off" maxlength="40"
              placeholder="${_hd.addType === "stock" ? "输入 A 股简称，如 贵州茅台" : "输入题材，如 AI算力"}"
              aria-label="标的名称" oninput="hdSugInput(this.value)">
            <div class="hd-sug" id="hd-sug" hidden></div>
          </div>
          <input id="hd-add-note" maxlength="200" placeholder="备注（可选）" aria-label="备注">
          <button type="button" class="hd-btn primary" onclick="hdAddSubmit()"${atMax ? " disabled" : ""}>添加</button>
        </div>
        ${_hd.addType === "topic" ? `<div class="hd-hint">题材开放输入，无相关观点时先空着；研判覆盖到该题材后自动汇入。</div>` : ""}
      </div>
      ${n ? `<div class="hd-list">${rows}</div>`
          : `<div class="hd-empty-sm">还没有持股：先添加你持有的个股或关注的题材，下方才开始汇总相关观点。</div>`}
    `;
  }

  // 输入建议（个股=名单强校验源；题材=研判产出+词表，只建议不拦截），250ms 防抖
  function hdSugInput(value) {
    if (_hd.sugTimer) clearTimeout(_hd.sugTimer);
    const q = String(value || "").trim();
    const box = document.getElementById("hd-sug");
    if (!q) {
      if (box) { box.hidden = true; box.innerHTML = ""; }
      return;
    }
    _hd.sugTimer = setTimeout(async () => {
      _hd.sugTimer = null;
      try {
        const data = await api(`/api/my/holdings/suggestions?type=${_hd.addType}&q=${encodeURIComponent(q)}`);
        if (!routeStillActive(_hd.seq)) return;
        const items = (data && data.items) || [];
        window._hdSug = items;
        if (!box) return;
        if (!items.length) { box.hidden = true; box.innerHTML = ""; return; }
        box.innerHTML = items.map((it, i) => `
          <button type="button" class="hd-sug-item" onmousedown="hdSugPick(${i})">
            <b>${escapeHtml(it.name)}</b>${it.extra ? `<span>${escapeHtml(it.extra)}</span>` : ""}
          </button>`).join("");
        box.hidden = false;
      } catch (e) { /* 建议失败不影响手输提交 */ }
    }, 250);
  }

  function hdSugPick(idx) {
    const it = window._hdSug[idx];
    const input = document.getElementById("hd-add-input");
    if (it && input) input.value = it.name;
    const box = document.getElementById("hd-sug");
    if (box) { box.hidden = true; box.innerHTML = ""; }
  }

  function hdAddType(t) {
    const next = t === "topic" ? "topic" : "stock";
    if (next === _hd.addType) return;
    const prevInput = document.getElementById("hd-add-input");
    const prevNote = document.getElementById("hd-add-note");
    const name = prevInput ? prevInput.value : "";
    const note = prevNote ? prevNote.value : "";
    _hd.addType = next;
    hdRenderManage();
    const input = document.getElementById("hd-add-input");
    const noteEl = document.getElementById("hd-add-note");
    if (input) input.value = name;
    if (noteEl) noteEl.value = note;
  }

  async function hdAddSubmit() {
    const input = document.getElementById("hd-add-input");
    const note = document.getElementById("hd-add-note");
    const name = String((input && input.value) || "").trim();
    if (!name) { flash("请先输入标的名称", "error"); return; }
    try {
      await api("/api/my/holdings", { method: "POST", body: JSON.stringify({
        target_type: _hd.addType,
        target_name: name,
        note: String((note && note.value) || "").trim(),
      }) });
      flash("已添加");
      _hd.editId = null;
      await hdReload();
    } catch (err) {
      flash(err.message, "error");
    }
  }

  function hdEditOpen(id) {
    _hd.editId = id;
    hdRenderManage();
    const el = document.getElementById(`hd-edit-name-${id}`);
    if (el) el.focus();
  }

  function hdEditCancel() {
    _hd.editId = null;
    hdRenderManage();
  }

  async function hdEditSave(id) {
    const nameEl = document.getElementById(`hd-edit-name-${id}`);
    const noteEl = document.getElementById(`hd-edit-note-${id}`);
    try {
      await api(`/api/my/holdings/${id}`, { method: "PATCH", body: JSON.stringify({
        target_name: String((nameEl && nameEl.value) || "").trim(),
        note: String((noteEl && noteEl.value) || "").trim(),
      }) });
      flash("已保存");
      _hd.editId = null;
      await hdReload();
    } catch (err) {
      flash(err.message, "error");
    }
  }

  async function hdDelete(id) {
    const h = _hd.holdings.find((x) => x.id === id);
    if (!h) return;
    if (!confirm(`删除持股「${h.target_name}」？仅影响你的持股研判页，原始消息与观点研判不受影响。`)) return;
    try {
      await api(`/api/my/holdings/${id}`, { method: "DELETE" });
      flash("已删除");
      if (_hd.filter && _hd.filter.type === h.target_type && _hd.filter.name === h.target_name) {
        _hd.filter = null;
      }
      await hdReload();
    } catch (err) {
      flash(err.message, "error");
    }
  }

  function hdRenderCards() {
    const el = document.getElementById("hd-cards");
    if (!el) return;
    const sumMap = new Map(_hd.summary.map((s) => [`${s.target_type}:${s.target_name}`, s]));
    const cards = _hd.holdings.map((h) => ({
      h,
      s: sumMap.get(`${h.target_type}:${h.target_name}`) ||
        { bull: 0, bear: 0, neutral: 0, total: 0, latest_at: "" },
    })).sort((a, b) => b.s.total - a.s.total); // 稳定排序：无观点保持清单原序垫底
    window._hdTargets = cards.map((c) => ({ type: c.h.target_type, name: c.h.target_name }));
    el.innerHTML = cards.map((c, i) => {
      const net = c.s.bull - c.s.bear;
      const active = _hd.filter && _hd.filter.type === c.h.target_type
        && _hd.filter.name === c.h.target_name;
      return `
      <button type="button" class="hd-card${active ? " active" : ""}${c.s.total ? "" : " zero"}" onclick="hdFilter(${i})">
        <span class="hd-card-head">${hdTypeBadge(c.h.target_type)}<b>${escapeHtml(c.h.target_name)}</b></span>
        <span class="hd-net ${net > 0 ? "bull" : net < 0 ? "bear" : "flat"}">${c.s.total ? `净 ${net > 0 ? "+" : ""}${net}` : "暂无观点"}</span>
        <span class="hd-counts"><i class="bull">▲${c.s.bull}</i><i class="bear">▼${c.s.bear}</i><i class="neutral">○${c.s.neutral}</i></span>
        ${c.s.latest_at ? `<span class="hd-latest">最新 ${escapeHtml(fmtTime(c.s.latest_at))}</span>` : ""}
      </button>`;
    }).join("");
  }

  // idx = 聚合卡下标（window._hdTargets）；-1 = 清除筛选
  async function hdFilter(idx) {
    if (idx < 0) {
      _hd.filter = null;
    } else {
      const t = window._hdTargets[idx];
      if (!t) return;
      if (_hd.filter && _hd.filter.type === t.type && _hd.filter.name === t.name) {
        _hd.filter = null; // 再点取消
      } else {
        _hd.filter = t;
      }
    }
    hdRenderCards();
    await hdReloadFeed();
  }

  function hdDirBadge(d) {
    if (d === "bull") return `<span class="hd-dir bull">▲ 看多</span>`;
    if (d === "bear") return `<span class="hd-dir bear">▼ 看空</span>`;
    return `<span class="hd-dir neutral">◎ 中性</span>`;
  }

  function hdRenderFeed() {
    const el = document.getElementById("hd-feed");
    if (!el) return;
    const rows = _hd.items.map((it) => {
      const evs = it.evidence || [];
      const open = _hd.expanded.has(it.id);
      return `
      <div class="hd-op${_hd.freshIds.has(it.id) ? " fresh" : ""}" data-op-id="${it.id}">
        <div class="hd-op-head">
          ${hdDirBadge(it.direction)}
          <span class="hd-op-target">${escapeHtml(it.target_name)}</span>
          ${it.action ? `<span class="hd-action">${escapeHtml(it.action)}</span>` : ""}
          <span class="hd-op-meta">${escapeHtml(it.kol_name || "")} · ${escapeHtml(fmtTime(it.occurred_at))}</span>
          ${evs.length ? `<button type="button" class="hd-ev-toggle" onclick="hdExpand(${it.id})">${open ? "收起依据" : `依据 ${evs.length}`}</button>` : ""}
        </div>
        ${it.summary ? `<div class="hd-op-summary">${escapeHtml(it.summary)}</div>` : ""}
        ${open && evs.length ? `<div class="hd-ev">${evs.map((ev) => `
          <div class="hd-ev-item">
            <div class="hd-ev-meta">${escapeHtml(ev.author || "")} · ${escapeHtml(fmtTime(ev.time))}</div>
            <div class="hd-ev-content">${escapeHtml(ev.content || "")}</div>
          </div>`).join("")}</div>` : ""}
      </div>`;
    }).join("");
    const chip = _hd.filter
      ? `<button type="button" class="hd-chip" onclick="hdFilter(-1)">✕ ${escapeHtml(_hd.filter.name)}</button>`
      : "";
    el.innerHTML = `
      <div class="hd-feed-head">
        <b>相关观点</b>
        <span class="hd-hint">近 ${WINDOW_DAYS} 天</span>
        ${chip}
        <span class="hd-hint right">${_hd.items.length ? `${_hd.items.length} 条` : ""}</span>
      </div>
      ${!_hd.holdings.length
        ? `<div class="hd-empty">先在上方添加持股，相关观点会在这里按月汇总、实时更新。</div>`
        : !_hd.items.length
          ? `<div class="hd-empty">${_hd.filter ? "该标的最近一个月暂无相关观点" : "最近一个月暂无与你持股相关的观点"}</div>`
          : rows}
      ${_hd.items.length && !_hd.exhausted
        ? `<div class="hd-more-wrap"><button type="button" class="hd-btn" onclick="hdMore()"${_hd.loadingMore ? " disabled" : ""}>${_hd.loadingMore ? "加载中…" : "加载更多"}</button></div>`
        : ""}
    `;
  }

  function hdExpand(id) {
    if (_hd.expanded.has(id)) _hd.expanded.delete(id);
    else _hd.expanded.add(id);
    hdRenderFeed();
  }

  async function hdMore() {
    if (_hd.loadingMore || !_hd.items.length) return;
    _hd.loadingMore = true;
    hdRenderFeed();
    try {
      const before = _hd.items[_hd.items.length - 1].id;
      const data = await api(`/api/my/holdings/views?limit=${PAGE_SIZE}&before_id=${before}${hdHolderQ()}`);
      if (!routeStillActive(_hd.seq)) return;
      const more = data.items || [];
      const known = new Set(_hd.items.map((it) => it.id));
      _hd.items = _hd.items.concat(more.filter((it) => !known.has(it.id)));
      _hd.exhausted = more.length < PAGE_SIZE;
      _hd.maxId = data.max_id || _hd.maxId;
      _hd.summary = (data.summary && data.summary.targets) || _hd.summary;
    } catch (err) {
      flash(`加载失败: ${err.message}`, "error");
    } finally {
      _hd.loadingMore = false;
      if (routeStillActive(_hd.seq)) hdRenderFeed();
    }
  }

  return {
    renderHoldings,
    hdAddType,
    hdSugInput,
    hdSugPick,
    hdAddSubmit,
    hdEditOpen,
    hdEditSave,
    hdEditCancel,
    hdDelete,
    hdFilter,
    hdExpand,
    hdMore,
  };
}
