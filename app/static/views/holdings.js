// 持股研判页（/holdings）：顶部用户持股管理（个股/题材），下方最近一个月相关观点
// 聚合卡 + 双页签流（观点=LLM 研判 / 快讯=标签命中帖），SSE 版本变更 + 60s 兜底轮询
// 增量上屏。样式全部 .hd- 前缀（holdings.css，跟随全局主题）
export function createHoldingsView(dependencies) {
  const {
    $, state, api, escapeHtml, setPageTitle, routeStillActive, flash, showConfirm,
  } = dependencies;

  window._hdTargets = []; // 聚合卡下标索引：onclick 传下标，避免标的名称注入 JS 字符串
  window._hdSug = []; // 输入建议下标索引，同上
  const _hd = {
    seq: 0, holdings: [], summary: [], items: [], maxId: 0,
    filter: null, // {type, name} 单标的筛选；null = 全部
    expanded: new Set(), es: null, sseOk: false, pollTimer: null,
    sugTimer: null, pickedType: null, // 添加框点选建议记住的类型（手输时提交前探测）
    exhausted: false, loadingMore: false, freshIds: new Set(),
    watchOpen: true, // 关注列表折叠状态（localStorage 持久化）
    // 标签快讯流：posts.tags 命中关注标的名（相关观点之外的标签口径信号）
    tab: "opinions", // 流内页签：opinions=相关观点 | tags=相关快讯
    tagItems: [], tagMaxId: 0, tagSummary: new Map(),
    tagExhausted: false, tagLoadingMore: false, tagFresh: new Set(),
    postOpen: new Set(), // 快讯行展开全文
  };
  try {
    _hd.watchOpen = localStorage.getItem("hd_watch_open") !== "0";
  } catch (e) { /* 存储不可用：默认展开 */ }
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
      expanded: new Set(), sseOk: false,
      exhausted: false, loadingMore: false, freshIds: new Set(),
      tab: "opinions",
      tagItems: [], tagMaxId: 0, tagSummary: new Map(),
      tagExhausted: false, tagLoadingMore: false, tagFresh: new Set(),
      postOpen: new Set(), pickedType: null,
    });
  }

  function fmtTime(ts) {
    const s = String(ts || "");
    return s.length >= 16 ? s.slice(5, 16) : s; // "YYYY-MM-DD HH:MM:SS" → "MM-DD HH:MM"
  }

  // 分组日期头：最近两天显示 今天/昨天，其余显示 MM-DD
  function hdDayLabel(day) {
    const d = String(day || "");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return d.slice(5) || "—";
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const yKey = `${yesterday.getFullYear()}-${pad(yesterday.getMonth() + 1)}-${pad(yesterday.getDate())}`;
    if (d === today) return "今天";
    if (d === yKey) return "昨天";
    return d.slice(5);
  }

  function hdHolderQ() {
    return _hd.filter
      ? `&holder=${encodeURIComponent(`${_hd.filter.type}:${_hd.filter.name}`)}`
      : "";
  }

  function hdApplyViews(data) {
    _hd.summary = (data && data.summary && data.summary.targets) || [];
    _hd.maxId = Math.max(_hd.maxId, (data && data.max_id) || 0);
    _hd.items = (data && data.items) || [];
    _hd.exhausted = _hd.items.length < PAGE_SIZE;
  }

  function hdApplyTagPosts(data) {
    const sum = (data && data.summary && data.summary.targets) || [];
    // 复合键：股票与题材可同名，单 name 键会互相覆盖计数
    _hd.tagSummary = new Map(sum.map((s) => [`${s.target_type}:${s.target_name}`, s]));
    _hd.tagMaxId = Math.max(_hd.tagMaxId, (data && data.max_id) || 0);
    _hd.tagItems = (data && data.items) || [];
    _hd.tagExhausted = _hd.tagItems.length < PAGE_SIZE;
  }

  async function renderHoldings(seq) {
    hdTeardown();
    _hd.seq = seq;
    setPageTitle("持股研判");
    $("#main").innerHTML = `<div class="hd-root"><div class="hd-empty">加载中…</div></div>`;
    try {
      const [holdings, views, tagPosts] = await Promise.all([
        api("/api/my/holdings"),
        api(`/api/my/holdings/views?limit=${PAGE_SIZE}${hdHolderQ()}`),
        api(`/api/my/holdings/tag-posts?limit=${PAGE_SIZE}${hdHolderQ()}`),
      ]);
      if (!routeStillActive(seq)) return;
      _hd.holdings = Array.isArray(holdings) ? holdings : [];
      hdApplyViews(views);
      hdApplyTagPosts(tagPosts);
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
      const [holdings, views, tagPosts] = await Promise.all([
        api("/api/my/holdings"),
        api(`/api/my/holdings/views?limit=${PAGE_SIZE}${hdHolderQ()}`),
        api(`/api/my/holdings/tag-posts?limit=${PAGE_SIZE}${hdHolderQ()}`),
      ]);
      if (!routeStillActive(seq)) return;
      _hd.holdings = Array.isArray(holdings) ? holdings : [];
      hdApplyViews(views);
      hdApplyTagPosts(tagPosts);
      hdRenderAll();
    } catch (err) {
      flash(`刷新失败: ${err.message}`, "error");
    }
  }

  async function hdReloadFeed() {
    try {
      const [views, tagPosts] = await Promise.all([
        api(`/api/my/holdings/views?limit=${PAGE_SIZE}${hdHolderQ()}`),
        api(`/api/my/holdings/tag-posts?limit=${PAGE_SIZE}${hdHolderQ()}`),
      ]);
      if (!routeStillActive(_hd.seq)) return;
      hdApplyViews(views);
      hdApplyTagPosts(tagPosts);
      hdRenderFeed();
    } catch (err) {
      flash(`刷新失败: ${err.message}`, "error");
    }
  }

  // SSE 版本变更/兜底轮询：两条流各自增量拉新插入顶部（响应同时带回重算后的全窗口聚合）。
  // 增量循环拉到不足一页为止：积压超过一页时中间段不会形成「顶部新 + 底部旧」的断层
  async function hdIncRefresh() {
    if (!routeStillActive(_hd.seq)) return;
    try {
      const data = await api(`/api/my/holdings/views?limit=${PAGE_SIZE}&after_id=${_hd.maxId}${hdHolderQ()}`);
      if (!routeStillActive(_hd.seq)) return;
      _hd.summary = (data.summary && data.summary.targets) || [];
      _hd.maxId = Math.max(_hd.maxId, data.max_id || 0);
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

  // 标签快讯增量：新帖入库不 bump 观点版本号，主要靠兜底轮询到账
  async function hdTagIncRefresh() {
    if (!routeStillActive(_hd.seq)) return;
    try {
      const data = await api(`/api/my/holdings/tag-posts?limit=${PAGE_SIZE}&after_id=${_hd.tagMaxId}${hdHolderQ()}`);
      if (!routeStillActive(_hd.seq)) return;
      const sum = (data.summary && data.summary.targets) || [];
      _hd.tagSummary = new Map(sum.map((s) => [`${s.target_type}:${s.target_name}`, s]));
      _hd.tagMaxId = Math.max(_hd.tagMaxId, data.max_id || 0);
      const known = new Set(_hd.tagItems.map((it) => it.id));
      const fresh = (data.items || []).filter((it) => !known.has(it.id));
      if (fresh.length) {
        fresh.forEach((it) => _hd.tagFresh.add(it.id));
        _hd.tagItems = fresh.concat(_hd.tagItems);
        if (fresh.length >= PAGE_SIZE) _hd.tagExhausted = false;
        setTimeout(() => {
          _hd.tagFresh.clear();
          if (routeStillActive(_hd.seq)) hdRenderFeed();
        }, 2600);
      }
      hdRenderCards();
      if (_hd.tab === "tags") hdRenderFeed();
    } catch (e) { /* 静默：下次兜底轮询再试 */ }
  }

  function hdIncAll() {
    hdIncRefresh();
    hdTagIncRefresh();
  }

  function hdSseSync() {
    const dot = document.querySelector(".hd-dot.sse");
    if (dot) dot.classList.toggle("on", !!_hd.sseOk);
  }

  // 复用观点研判的版本号 SSE：新批次落库 → version 事件 → 增量拉相关观点/快讯
  function hdEnsureSSE() {
    // 新帖入库不 bump 观点版本号，标签快讯的到账靠 60s 兜底轮询（恒开，覆盖 SSE 断连）
    if (!_hd.pollTimer) _hd.pollTimer = setInterval(hdIncAll, 60000);
    if (!state.token || _hd.es) return;
    try {
      const es = new EventSource(`/api/mx-views/stream?token=${encodeURIComponent(state.token)}`);
      es.addEventListener("version", () => { hdIncAll(); });
      es.onerror = () => { // EventSource 自动重连；连接状态只管实时点
        _hd.sseOk = false;
        hdSseSync();
      };
      es.onopen = () => {
        _hd.sseOk = true;
        hdSseSync();
      };
      _hd.es = es;
    } catch (e) { /* SSE 不可用时静默 */ }
  }

  function hdRenderAll() {
    $("#main").innerHTML = `
      <div class="hd-root">
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

  function hdWatchToggle() {
    _hd.watchOpen = !_hd.watchOpen;
    try { localStorage.setItem("hd_watch_open", _hd.watchOpen ? "1" : "0"); } catch (e) { /* 本页生效即可 */ }
    hdRenderManage();
  }

  function hdRenderManage() {
    const el = document.getElementById("hd-manage");
    if (!el) return;
    const n = _hd.holdings.length;
    const atMax = n >= HD_MAX;
    const head = `
      <div class="hd-panel-head">
        <b>关注列表</b>
        <span class="hd-hint">${n}/${HD_MAX}${atMax ? " · 已达上限" : ""}</span>
        <button type="button" class="hd-btn sm" aria-expanded="${_hd.watchOpen}" onclick="hdWatchToggle()">${_hd.watchOpen ? "收起" : "展开"}</button>
        <span class="hd-pills">
          <span class="hd-pill"><span class="hd-dot sse"></span>实时</span>
          <span class="hd-pill">近 ${WINDOW_DAYS} 天</span>
        </span>
      </div>`;
    if (!_hd.watchOpen) {
      el.innerHTML = head;
      return;
    }
    const chip = (h) => `
      <div class="hd-item" data-holding-id="${h.id}">
        <div class="hd-item-main">
          ${hdTypeBadge(h.target_type)}
          <span class="hd-name" title="${escapeHtml(h.target_name)}">${escapeHtml(h.target_name)}</span>
          <span class="hd-item-ops">
            <button type="button" class="hd-btn sm ghost" onclick="hdDelete(${h.id})">删</button>
          </span>
        </div>
      </div>`;
    const stocks = _hd.holdings.filter((h) => h.target_type === "stock");
    const topics = _hd.holdings.filter((h) => h.target_type !== "stock");
    const group = (title, list) => `
      <div class="hd-col">
        <div class="hd-col-head">${title} <span>${list.length}</span></div>
        <div class="hd-grid">${list.map(chip).join("") || `<div class="hd-empty-sm">暂无</div>`}</div>
      </div>`;
    el.innerHTML = head + `
      <div class="hd-add">
        <div class="hd-add-fields">
          <div class="hd-add-name">
            <input id="hd-add-input" autocomplete="off" maxlength="40"
              placeholder="输入个股或板块名，如 贵州茅台 / AI算力"
              aria-label="标的名称" oninput="hdSugInput(this.value)">
            <div class="hd-sug" id="hd-sug" hidden></div>
          </div>
          <button type="button" class="hd-btn primary" onclick="hdAddSubmit()"${atMax ? " disabled" : ""}>添加</button>
        </div>
        <div class="hd-hint">个股须在全市场名单内（建议点选自动识别类型）；板块开放输入，无相关观点时先空着。</div>
      </div>
      ${n ? `<div class="hd-cols">${group("个股", stocks)}${group("板块", topics)}</div>`
          : `<div class="hd-empty-sm">还没有关注：先添加你持有的个股或关注的板块，下方才开始汇总相关观点。</div>`}
    `;
  }

  // 输入建议：个股（名单强校验源）与板块（研判产出+词表，只建议不拦截）共用一个搜索框，
  // 两路并行合并——个股在前、按名去重（同名优先个股口径），250ms 防抖；输入即清掉点选类型记忆
  function hdSugInput(value) {
    if (_hd.sugTimer) clearTimeout(_hd.sugTimer);
    _hd.pickedType = null;
    const q = String(value || "").trim();
    const box = document.getElementById("hd-sug");
    if (!q) {
      if (box) { box.hidden = true; box.innerHTML = ""; }
      return;
    }
    _hd.sugTimer = setTimeout(async () => {
      _hd.sugTimer = null;
      try {
        const [stocks, topics] = await Promise.all([
          api(`/api/my/holdings/suggestions?type=stock&q=${encodeURIComponent(q)}`),
          api(`/api/my/holdings/suggestions?type=topic&q=${encodeURIComponent(q)}`),
        ]);
        if (!routeStillActive(_hd.seq)) return;
        const seen = new Set();
        const items = [];
        for (const it of [
          ...((stocks && stocks.items) || []).map((x) => ({ ...x, type: "stock" })),
          ...((topics && topics.items) || []).map((x) => ({ ...x, type: "topic" })),
        ]) {
          if (!it.name || seen.has(it.name)) continue;
          seen.add(it.name);
          items.push(it);
          if (items.length >= SUG_LIMIT) break;
        }
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
    if (it && input) {
      input.value = it.name;
      _hd.pickedType = it.type || null; // 点选即记住类型，提交不再探测
    }
    const box = document.getElementById("hd-sug");
    if (box) { box.hidden = true; box.innerHTML = ""; }
  }

  async function hdAddSubmit() {
    const input = document.getElementById("hd-add-input");
    const name = String((input && input.value) || "").trim();
    if (!name) { flash("请先输入标的名称", "error"); return; }
    try {
      // 类型识别：点选建议自带；手输时按个股名单探测——命中即个股，否则按开放输入的板块
      let type = _hd.pickedType;
      if (type !== "stock" && type !== "topic") {
        const sug = await api(`/api/my/holdings/suggestions?type=stock&q=${encodeURIComponent(name)}`);
        type = ((sug && sug.items) || []).some((it) => it.name === name) ? "stock" : "topic";
      }
      await api("/api/my/holdings", { method: "POST", body: JSON.stringify({
        target_type: type,
        target_name: name,
      }) });
      flash("已添加");
      _hd.pickedType = null;
      await hdReload();
    } catch (err) {
      flash(err.message, "error");
    }
  }

  async function hdDelete(id) {
    const h = _hd.holdings.find((x) => x.id === id);
    if (!h) return;
    // 应用内确认弹窗（原生 confirm 与全站弹窗体系不一致，且部分内嵌 WebView 禁用）
    const ok = await showConfirm(
      `删除持股「${h.target_name}」？仅影响你的持股研判页，原始消息与观点研判不受影响。`,
      { title: "删除持股", okText: "删除", danger: true });
    if (!ok) return;
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

  // 占比条：同观点研判总览卡（红=看多 / 灰=中立 / 绿=看空，中段吸收取整误差）
  function hdRatioHtml(bull, bear, neutral) {
    const total = Math.max(bull + bear + neutral, 1);
    const bp = Math.round((bull / total) * 100), sp = Math.round((bear / total) * 100);
    const np = Math.max(0, 100 - bp - sp);
    return `<div class="mxv-ratio" role="img" aria-label="看多${bull} 中立${neutral} 看空${bear}">
      ${bull ? `<div class="b" style="width:${bp}%"></div>` : ""}
      ${neutral ? `<div class="n" style="width:${np}%"></div>` : ""}
      ${bear ? `<div class="s" style="width:${sp}%"></div>` : ""}</div>`;
  }

  function hdRenderCards() {
    const el = document.getElementById("hd-cards");
    if (!el) return;
    const sumMap = new Map(_hd.summary.map((s) => [`${s.target_type}:${s.target_name}`, s]));
    const cards = _hd.holdings.map((h) => ({
      h,
      s: sumMap.get(`${h.target_type}:${h.target_name}`) || {
        bull: 0, bear: 0, neutral: 0, total: 0, latest_at: "",
        kols: { count: 0, bull: 0, bear: 0, neutral: 0,
                bull_names: [], bear_names: [], neutral_names: [] },
        actions: {},
      },
    })).sort((a, b) => b.s.total - a.s.total); // 稳定排序：无观点保持清单原序垫底
    window._hdTargets = cards.map((c) => ({ type: c.h.target_type, name: c.h.target_name }));
    // 名单行：同总览按个股卡——前 6 个大V名顿号相连，超出补「等 N 人」（N=去重计数）
    const namesLine = (names, cnt, colorVar, arrow) => (names && names.length)
      ? `<span style="color:${colorVar}">${arrow}</span> ${escapeHtml(names.slice(0, 6).join("、"))}` +
        (cnt > names.length ? `<span style="color:var(--mxv-faint)"> 等${cnt}人</span>` : "")
      : `<span style="color:var(--mxv-faint)">${arrow} 暂无</span>`;
    el.innerHTML = cards.map((c, i) => {
      const k = c.s.kols || { count: 0, bull: 0, bear: 0, neutral: 0,
                              bull_names: [], bear_names: [], neutral_names: [] };
      const actionsHtml = Object.entries(c.s.actions || {}).map(([w, n]) => `${w}×${n}`).join(" ");
      const tagc = (_hd.tagSummary.get(`${c.h.target_type}:${c.h.target_name}`) || {}).tag_count || 0;
      const active = _hd.filter && _hd.filter.type === c.h.target_type
        && _hd.filter.name === c.h.target_name;
      return `
      <button type="button" class="mxv-stockcard hd-card${active ? " active" : ""}" onclick="hdFilter(${i})">
        <span class="n">${hdTypeBadge(c.h.target_type)}<b>${escapeHtml(c.h.target_name)}</b>
          <span style="color:var(--mxv-faint);font-size:11px">${k.count} 大V</span>
          ${tagc ? `<span style="color:var(--mxv-faint);font-size:11px" title="近 ${WINDOW_DAYS} 天标签提及 ${tagc} 帖">· #${tagc} 帖</span>` : ""}
          ${actionsHtml ? `<span class="mxv-actions">${escapeHtml(actionsHtml)}</span>` : ""}</span>
        ${hdRatioHtml(k.bull, k.bear, k.neutral)}
        <span class="names">${namesLine(k.bull_names, k.bull, "var(--mxv-bull)", "▲")}</span>
        <span class="names">${namesLine(k.bear_names, k.bear, "var(--mxv-bear)", "▼")}</span>
        <span class="names">${namesLine(k.neutral_names, k.neutral, "var(--mxv-muted)", "◎")}</span>
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

  // ---- 流区：观点（LLM 研判）与快讯（标签命中）双页签，样式对齐观点研判实时观点流 ----
  function hdFeedTab(t) {
    const next = t === "tags" ? "tags" : "opinions";
    if (next === _hd.tab) return;
    _hd.tab = next;
    hdRenderFeed();
  }

  // 标签快讯行：同一 mxv 行内网格（时间/多空徽章/标的/大V/摘要），点击展开全文
  function hdTagItemHtml(it) {
    const kol = it.kol_name || "";
    const kolShort = kol.length > 6 ? `${kol.slice(0, 6).replace(/[（(【\[]$/, "")}…` : kol;
    const names = it.target_names || [];
    const dir = it.direction === "bull" || it.direction === "bear" ? it.direction : "";
    const open = _hd.postOpen.has(it.id);
    return `
    <div class="mxv-feed-item${_hd.tagFresh.has(it.id) ? " fresh" : ""} has-post${open ? " open" : ""}"
      data-post-id="${it.id}" title="点击展开全文" onclick="hdPostExpand(${it.id})">
      <span class="t" style="color:var(--mxv-accent)">${escapeHtml((it.published_at || "").slice(11, 16))}</span>
      ${dir
        ? `<span class="mxv-badge ${dir}">${dir === "bull" ? "↑看多" : "↓看空"}</span>`
        : `<span class="mxv-badge neutral">帖</span>`}
      <span></span>
      <span class="target" style="color:var(--mxv-text)" title="${escapeHtml(names.join(" · "))}">${escapeHtml(names[0] || "")}</span>
      <span style="color:var(--mxv-muted)" title="${escapeHtml(kol)}">· ${escapeHtml(kolShort)}</span>
      <span class="sum" style="color:var(--mxv-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(it.content || "")}">${escapeHtml(it.content || "")}</span>
    </div>
    ${open ? `<div class="hd-ev"><div class="hd-ev-item">
      <div class="hd-ev-meta">${escapeHtml(kol)} · ${escapeHtml(fmtTime(it.published_at))}</div>
      <div class="hd-ev-content">${escapeHtml(it.content || "")}</div>
    </div></div>` : ""}`;
  }

  function hdRenderFeed() {
    const el = document.getElementById("hd-feed");
    if (!el) return;
    const count = _hd.tab === "tags" ? _hd.tagItems.length : _hd.items.length;
    const head = `
    <div class="mxv-kol-head">
      <h3>${_hd.tab === "tags" ? "相关快讯" : "相关观点"}<span class="hd-feed-sub">近 ${WINDOW_DAYS} 天</span></h3>
      <div class="hd-seg hd-feed-tabs" role="tablist">
        <button type="button" class="hd-seg-btn${_hd.tab !== "tags" ? " on" : ""}" onclick="hdFeedTab('opinions')">观点</button>
        <button type="button" class="hd-seg-btn${_hd.tab === "tags" ? " on" : ""}" onclick="hdFeedTab('tags')">快讯</button>
      </div>
      <div class="hd-feed-tail">
        ${_hd.filter ? `<button type="button" class="mxv-fchip on" onclick="hdFilter(-1)">✕ ${escapeHtml(_hd.filter.name)}</button>` : ""}
        <span class="hd-hint">${count ? `${count} 条` : ""}</span>
      </div>
    </div>`;
    let body;
    if (!_hd.holdings.length) {
      body = `<div class="mxv-empty">先在上方添加关注，相关观点会在这里按月汇总、实时更新。</div>`;
    } else if (_hd.tab === "tags") {
      if (!_hd.tagItems.length) {
        body = `<div class="mxv-empty">${_hd.filter ? "该标的最近一个月暂无命中标签的快讯" : "最近一个月暂无命中你关注标的标签的快讯"}</div>`;
      } else {
        // 按发布日分段单列流（与观点流同构）：一天一段，一行一条消息
        const groups = new Map();
        _hd.tagItems.forEach((it) => {
          const day = (it.published_at || "").slice(0, 10);
          if (!groups.has(day)) groups.set(day, []);
          groups.get(day).push(it);
        });
        body = [...groups.entries()].map(([day, posts]) => {
          const grid = `<div class="mxv-feed-cols single"><div class="mxv-feed-col">${posts.map(hdTagItemHtml).join("")}</div></div>`;
          return `<div class="mxv-feed-sep"><span>${escapeHtml(hdDayLabel(day))} · ${posts.length} 条</span></div>${grid}`;
        }).join("") + `<div class="mxv-feed-sep"><span>共 ${_hd.tagItems.length} 条</span></div>`;
        if (!_hd.tagExhausted) {
          body += `<div class="hd-more-wrap"><button type="button" class="hd-btn" onclick="hdTagMore()"${_hd.tagLoadingMore ? " disabled" : ""}>${_hd.tagLoadingMore ? "加载中…" : "加载更多"}</button></div>`;
        }
      }
    } else if (!_hd.items.length) {
      body = `<div class="mxv-empty">${_hd.filter ? "该标的最近一个月暂无相关观点" : "最近一个月暂无与你关注标的相关的观点"}</div>`;
    } else {
      // 按交易日分段单列流：一天一段（不看批次/快照时刻），一行一条消息
      const groups = new Map();
      _hd.items.forEach((it) => {
        const day = it.trading_day || (it.occurred_at || "").slice(0, 10);
        if (!groups.has(day)) groups.set(day, []);
        groups.get(day).push(it);
      });
      body = [...groups.entries()].map(([day, ops]) => {
        const grid = `<div class="mxv-feed-cols single"><div class="mxv-feed-col">${ops.map(hdFeedItemHtml).join("")}</div></div>`;
        return `<div class="mxv-feed-sep"><span>${escapeHtml(hdDayLabel(day))} · ${ops.length} 条</span></div>${grid}`;
      }).join("") + `<div class="mxv-feed-sep"><span>共 ${_hd.items.length} 条</span></div>`;
      if (!_hd.exhausted) {
        body += `<div class="hd-more-wrap"><button type="button" class="hd-btn" onclick="hdMore()"${_hd.loadingMore ? " disabled" : ""}>${_hd.loadingMore ? "加载中…" : "加载更多"}</button></div>`;
      }
    }
    el.innerHTML = head + body;
  }

  function hdExpand(id) {
    if (_hd.expanded.has(id)) _hd.expanded.delete(id);
    else _hd.expanded.add(id);
    hdRenderFeed();
  }

  function hdPostExpand(id) {
    if (_hd.postOpen.has(id)) _hd.postOpen.delete(id);
    else _hd.postOpen.add(id);
    hdRenderFeed();
  }

  async function hdTagMore() {
    if (_hd.tagLoadingMore || !_hd.tagItems.length) return;
    _hd.tagLoadingMore = true;
    hdRenderFeed();
    try {
      // 复合游标：与观点流同因同修（回灌旧帖 id 新、published_at 旧，纯 id 漏页）
      const last = _hd.tagItems[_hd.tagItems.length - 1];
      const data = await api(`/api/my/holdings/tag-posts?limit=${PAGE_SIZE}`
        + `&before_at=${encodeURIComponent(last.published_at || "")}&before_id=${last.id}${hdHolderQ()}`);
      if (!routeStillActive(_hd.seq)) return;
      const more = data.items || [];
      const known = new Set(_hd.tagItems.map((it) => it.id));
      _hd.tagItems = _hd.tagItems.concat(more.filter((it) => !known.has(it.id)));
      _hd.tagExhausted = more.length < PAGE_SIZE;
      _hd.tagMaxId = Math.max(_hd.tagMaxId, data.max_id || 0);
    } catch (err) {
      flash(`加载失败: ${err.message}`, "error");
    } finally {
      _hd.tagLoadingMore = false;
      if (routeStillActive(_hd.seq)) hdRenderFeed();
    }
  }

  // 观点行：LLM 研判结论（依据原帖可展开）
  function hdFeedItemHtml(it) {
    const kol = it.kol_name || "";
    const kolShort = kol.length > 6 ? `${kol.slice(0, 6).replace(/[（(【\[]$/, "")}…` : kol;
    const ev = it.evidence || [];
    const open = ev.length && _hd.expanded.has(it.id);
    return `
    <div class="mxv-feed-item${_hd.freshIds.has(it.id) ? " fresh" : ""}${ev.length ? ` has-ev${open ? " open" : ""}` : ""}"
      ${ev.length ? `data-ev="${ev.length}" data-op-id="${it.id}" title="点击展开依据原帖" onclick="hdExpand(${it.id})"` : ""}>
      <span class="t" style="color:var(--mxv-accent)">${escapeHtml((it.occurred_at || "").slice(11, 16))}</span>
      <span class="mxv-badge ${escapeHtml(it.direction)}">${it.direction === "bull" ? "↑看多" : it.direction === "bear" ? "↓看空" : "中性"}</span>
      ${it.action ? `<span class="mxv-badge act" title="${escapeHtml(it.action)}">${escapeHtml(it.action)}</span>` : "<span></span>"}
      <span class="target" style="color:var(--mxv-text)" title="${escapeHtml(it.target_name)}">${escapeHtml(it.target_name)}</span>
      <span style="color:var(--mxv-muted)" title="${escapeHtml(kol)}">· ${escapeHtml(kolShort)}</span>
      <span class="sum" style="color:var(--mxv-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escapeHtml(it.summary || "")}">${escapeHtml(it.summary || "")}</span>
    </div>
    ${open ? `<div class="hd-ev">${ev.map((evItem) => `
      <div class="hd-ev-item">
        <div class="hd-ev-meta">${escapeHtml(evItem.author || "")} · ${escapeHtml(fmtTime(evItem.time))}</div>
        <div class="hd-ev-content">${escapeHtml(evItem.content || "")}</div>
      </div>`).join("")}</div>` : ""}`;
  }

  async function hdMore() {
    if (_hd.loadingMore || !_hd.items.length) return;
    _hd.loadingMore = true;
    hdRenderFeed();
    try {
      // 复合游标：列表最底行的 occurred_at + id（与后端排序键一致）。
      // 研判批次会回填「id 新、occurred_at 旧」的观点，纯 id 游标会整段跳过这类行
      const last = _hd.items[_hd.items.length - 1];
      const data = await api(`/api/my/holdings/views?limit=${PAGE_SIZE}`
        + `&before_at=${encodeURIComponent(last.occurred_at || "")}&before_id=${last.id}${hdHolderQ()}`);
      if (!routeStillActive(_hd.seq)) return;
      const more = data.items || [];
      const known = new Set(_hd.items.map((it) => it.id));
      _hd.items = _hd.items.concat(more.filter((it) => !known.has(it.id)));
      _hd.exhausted = more.length < PAGE_SIZE;
      // 水位只增不减：翻旧页响应里的 max_id 可能落后于增量已推进的值
      _hd.maxId = Math.max(_hd.maxId, data.max_id || 0);
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
    hdTeardown,
    hdSugInput,
    hdSugPick,
    hdAddSubmit,
    hdDelete,
    hdFilter,
    hdExpand,
    hdMore,
    hdFeedTab,
    hdPostExpand,
    hdTagMore,
    hdWatchToggle,
  };
}
