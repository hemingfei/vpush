export function createNewsView(dependencies) {
  const {
    $,
    state,
    api,
    apiBlob,
    routeStillActive,
    currentRouteSeq,
    setPageTitle,
    emptyState,
    go,
    flash,
    escapeHtml,
    trapFocus,
    fmtPublished,
    externalLinkIcon,
    renderSidebar,
    renderBottomNav,
    updateNewsBadge,
    SEARCH_ICON,
    GEAR_ICON,
    NEWS_ICON,
    EYE_ICON,
    CHEVRON_DOWN_ICON,
    CHECK_ICON,
    CHECK_CHECK_ICON,
  } = dependencies;
  let searchTimer = null;
  let readAllUndoTimer = null;
  let readAllUndoPayload = null;

  function clearNewsReadUndo() {
    clearTimeout(readAllUndoTimer);
    readAllUndoTimer = null;
    readAllUndoPayload = null;
    const banner = $("#news-read-undo");
    if (banner) {
      banner.hidden = true;
      banner.innerHTML = "";
    }
  }

  function newsImageUrlKey(articleId, index) {
    return `${articleId}:${index}`;
  }

  function clearNewsImageUrls() {
    for (const url of state.newsImageUrls.values()) URL.revokeObjectURL(url);
    state.newsImageUrls.clear();
  }

  function stopNewsAutoLoad() {
    state.newsObserver?.disconnect();
    state.newsObserver = null;
  }

  function stopReadProgress() {
    if (state.newsProgressHandler) {
      window.removeEventListener("scroll", state.newsProgressHandler);
      state.newsProgressHandler = null;
    }
  }

  function clearNewsReaderState() {
    stopNewsAutoLoad();
    stopReadProgress();
    clearNewsReadUndo();
    clearNewsImageUrls();
    state.newsSources = [];
    state.newsFilterSourceId = "";
    state.newsQuery = "";
    state.newsItems = [];
    state.newsOffset = 0;
    state.newsHasMore = false;
    state.newsRequestSeq += 1;
    state.newsScrollY = 0;
  }

  function newsListKey() {
    const topic = state.newsTopic || "";
    return `${state.newsFilterSourceId || ""}|${(state.newsQuery || "").trim()}|${state.newsUnreadOnly ? "u" : ""}|${topic}`;
  }

  function startNewsAutoLoad(seq) {
    stopNewsAutoLoad();
    const sentinel = $("#news-load-sentinel");
    if (!sentinel || !state.newsHasMore) return;
    if ("IntersectionObserver" in window) {
      state.newsObserver = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadFinancialNews(false, seq);
      }, { rootMargin: "400px 0px" });
      state.newsObserver.observe(sentinel);
    }
  }

  function renderNewsCenter(seq, articleId = "") {
    stopNewsAutoLoad();
    stopReadProgress();
    if (!routeStillActive(seq)) return;
    if (articleId) return renderFinancialNewsArticle(Number(articleId), seq);
    return renderFinancialNewsList(seq);
  }

  function newsDayLabel(publishedAt) {
    const date = new Date(publishedAt);
    if (Number.isNaN(date.getTime())) return "更早";
    const today = new Date();
    const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const dayMs = 86400000;
    const diff = Math.floor((startOfToday - new Date(date.getFullYear(), date.getMonth(), date.getDate())) / dayMs);
    if (diff <= 0) return "今天";
    if (diff === 1) return "昨天";
    const md = `${date.getMonth() + 1}/${date.getDate()}`;
    return date.getFullYear() === today.getFullYear() ? md : `${date.getFullYear()}/${md}`;
  }

  function groupNewsItemsByDay(items) {
    const groups = [];
    let current = null;
    for (const item of items) {
      const label = newsDayLabel(item.published_at);
      if (!current || current.label !== label) {
        current = { label, items: [] };
        groups.push(current);
      }
      current.items.push(item);
    }
    return groups;
  }

  const NEWS_TOPICS = ["宏观", "国际", "科技", "公司", "市场"];

  function newsTopicBarHtml() {
    const active = state.newsTopic || "";
    return `<div class="news-topic-bar" role="tablist" aria-label="新闻主题">
      <button type="button" class="news-topic-chip ${active ? "" : "is-on"}" onclick="selectNewsTopic('')" aria-pressed="${active ? "false" : "true"}">全部</button>
      ${NEWS_TOPICS.map((topic) => `<button type="button" class="news-topic-chip ${active === topic ? "is-on" : ""}" onclick="selectNewsTopic('${topic}')" aria-pressed="${active === topic ? "true" : "false"}">${topic}</button>`).join("")}
    </div>`;
  }

  function newsListItemHtml(item) {
    const unread = !item.is_read;
    const thumbnail = item.has_image
      ? `<img class="news-list-thumb" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 120 84'%3E%3C/svg%3E" data-news-thumbnail="${item.id}" alt="" loading="lazy" onerror="this.style.display='none'">`
      : "";
    const topics = Array.isArray(item.topics) && item.topics.length
      ? `<span class="news-item-topics">${item.topics.map((topic) => `<i>${escapeHtml(topic)}</i>`).join("")}</span>`
      : "";
    return `<article class="news-list-item ${unread ? "is-unread" : ""}" data-news-id="${item.id}" tabindex="0" role="link" onclick="openNewsArticle(${item.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openNewsArticle(${item.id})}">
    <div class="news-list-copy">
      ${topics}
      <div class="news-item-title-row">${unread ? '<i class="news-item-unread-dot" aria-label="未读"></i>' : ""}<h3>${escapeHtml(item.title)}</h3></div>
      <p>${escapeHtml(item.summary || "暂无摘要")}</p>
      <div class="news-list-meta"><span>${escapeHtml(item.source_name || "")}</span><time datetime="${escapeHtml(item.published_at || "")}">${escapeHtml(fmtPublished(item.published_at, true))}</time></div>
      ${unread ? `<button type="button" class="news-mark-read" onclick="event.stopPropagation();markNewsItemRead(${item.id})">${CHECK_ICON}<span>标为已读</span></button>` : ""}
    </div>${thumbnail}
  </article>`;
  }

  function newsListHtml(items) {
    return groupNewsItemsByDay(items).map((group) => `
      <div class="news-day-sep"><span>${escapeHtml(group.label)}</span></div>
      ${group.items.map(newsListItemHtml).join("")}`).join("");
  }

  function selectedNewsSources() {
    return state.newsSources.filter((source) => source.selected);
  }

  function newsSourceNavigationHtml() {
    const groups = new Map();
    for (const source of selectedNewsSources()) {
      const label = source.group_name || "其他来源";
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(source);
    }
    const allOn = !state.newsFilterSourceId;
    const rows = [...groups.entries()].map(([label, sources]) => `
    <details class="news-source-group" open>
      <summary>${CHEVRON_DOWN_ICON}<span>${escapeHtml(label)}</span></summary>
      ${sources.map((source) => `<button type="button" class="news-source-row ${String(state.newsFilterSourceId) === String(source.id) ? "is-on" : ""}" onclick="selectNewsSource('${source.id}')"><span>${escapeHtml(source.name)}</span><b>${Number(source.unread_count) || ""}</b></button>`).join("")}
    </details>`).join("");
    return `<nav class="news-source-rail" aria-label="资讯来源">
    <div class="news-source-rail-head"><strong>资讯来源</strong><button type="button" class="icon-btn" onclick="openNewsSourcePicker()" aria-label="管理资讯来源" title="管理资讯来源">${GEAR_ICON}</button></div>
    <button type="button" class="news-source-row news-source-all ${allOn ? "is-on" : ""}" onclick="selectNewsSource('')">${NEWS_ICON}<span>全部资讯</span><b>${Number(state.newsUnreadCount) || ""}</b></button>
    ${rows || '<p class="muted">尚未选择资讯来源</p>'}
  </nav>`;
  }

  function newsGroupedOptions() {
    const groups = new Map();
    for (const source of selectedNewsSources()) {
      const label = source.group_name || "其他来源";
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(source);
    }
    const options = [...groups.entries()].map(([label, sources]) => `
      <optgroup label="${escapeHtml(label)}">${sources.map((source) => `<option value="${source.id}" ${String(state.newsFilterSourceId) === String(source.id) ? "selected" : ""}>${escapeHtml(source.name)}</option>`).join("")}</optgroup>`).join("");
    return `<option value="">全部资讯</option>${options}`;
  }

  function newsListSkeletonHtml() {
    const card = '<div class="admin-sk-card"><div class="admin-sk-line admin-sk-head"></div><div class="admin-sk-line"></div></div>';
    return `<div class="admin-skeleton" aria-hidden="true">${card.repeat(3)}</div>`;
  }

  function renderNewsListShell(collectionEnabled = true) {
    const main = $("#main");
    if (!main) return;
    const unreadOn = !!state.newsUnreadOnly;
    const unreadCount = Number(state.newsUnreadCount) || 0;
    main.innerHTML = `<section class="news-page" id="news-page">
  <header class="news-stream-head">
    <div><h2 class="section-title">资讯流</h2><p class="section-meta">实时更新的财经资讯聚合</p></div>
    <div class="news-stream-actions">
      <label class="news-stream-search">${SEARCH_ICON}<input id="news-query" type="search" placeholder="搜索资讯..." value="${escapeHtml(state.newsQuery)}" oninput="queueNewsSearch(this.value)" aria-label="搜索资讯"></label>
      ${unreadCount ? `<button type="button" class="btn-ghost news-read-all" onclick="markAllNewsRead()">${CHECK_CHECK_ICON} 全部已读</button>` : ""}
      <button type="button" class="btn-ghost news-source-manage" onclick="openNewsSourcePicker()">${GEAR_ICON} 我的来源</button>
    </div>
  </header>
  ${collectionEnabled ? "" : '<div class="notice notice-warn">管理员已暂停财经新闻采集，历史文章仍可阅读。</div>'}
  <div class="news-stream-topbar">
    <div class="news-source-mobile"><select aria-label="资讯来源" onchange="selectNewsSource(this.value)">${newsGroupedOptions()}</select>${CHEVRON_DOWN_ICON}</div>
    ${newsTopicBarHtml()}
    <button type="button" class="news-unread-toggle ${unreadOn ? "is-on" : ""}" onclick="toggleNewsUnreadOnly()" aria-pressed="${unreadOn}">${EYE_ICON}<span>未读</span>${unreadCount ? `<b>${unreadCount > 99 ? "99+" : unreadCount}</b>` : ""}</button>
  </div>
  <div class="news-stream-layout">
    ${newsSourceNavigationHtml()}
    <main class="news-stream-main">
      <div id="news-list" class="news-list">${newsListSkeletonHtml()}</div>
      <div id="news-load-sentinel" class="news-load-sentinel" role="status" aria-live="polite"></div>
    </main>
  </div>
  <div id="news-read-undo" class="news-read-undo" role="status" aria-live="polite" hidden></div>
</section>`;
  }

  function attachListImages(seq) {
    for (const item of state.newsItems) {
      const image = document.querySelector(`[data-news-thumbnail="${item.id}"]`);
      if (image) loadNewsImageBlob(item.id, 0, image, seq);
    }
  }

  function syncUnreadBadge() {
    updateNewsBadge?.();
    renderSidebar?.();
    renderBottomNav?.();
  }

  async function refreshUnreadCount(seq) {
    try {
      const sources = await api("/api/news/sources");
      if (!routeStillActive(seq)) return null;
      state.newsUnreadCount = Number(sources.unread_count) || 0;
      syncUnreadBadge();
      return sources;
    } catch {
      return null;
    }
  }

  async function renderFinancialNewsList(seq = currentRouteSeq()) {
    setPageTitle("财经新闻");
    // 文章返回且筛选未变：直接复用已加载列表并恢复滚动位置
    if (state.newsItems.length && state.newsListKey === newsListKey()) {
      renderNewsListShell(state.newsCollectionEnabled !== false);
      const list = $("#news-list");
      list.innerHTML = state.newsItems.length ? newsListHtml(state.newsItems) : emptyState("没有符合条件的财经新闻");
      attachListImages(seq);
      startNewsAutoLoad(seq);
      window.scrollTo(0, state.newsScrollY || 0);
      return;
    }
    state.newsItems = [];
    state.newsOffset = 0;
    state.newsHasMore = false;
    state.newsScrollY = 0;
    renderNewsListShell(true);
    try {
      const sources = await api("/api/news/sources");
      if (!routeStillActive(seq)) return;
      state.newsSources = sources.items || [];
      state.newsCollectionEnabled = sources.collection_enabled;
      state.newsUnreadCount = Number(sources.unread_count) || 0;
      syncUnreadBadge();
      if (state.newsFilterSourceId && !state.newsSources.some((source) => String(source.id) === String(state.newsFilterSourceId))) state.newsFilterSourceId = "";
      renderNewsListShell(sources.collection_enabled !== false);
      await loadFinancialNews(true, seq);
    } catch (err) {
      if (!routeStillActive(seq)) return;
      const shell = $("#news-list");
      if (shell) shell.innerHTML = emptyState("加载失败: " + err.message, `<div><button type="button" class="btn-ghost" onclick="renderFinancialNewsList()">重试</button></div>`);
    }
  }

  async function loadFinancialNews(reset = false, seq = currentRouteSeq()) {
    const list = $("#news-list");
    if (!list || !routeStillActive(seq)) return;
    const requestSeq = ++state.newsRequestSeq;
    if (reset) {
      stopNewsAutoLoad();
      state.newsItems = [];
      state.newsOffset = 0;
      list.innerHTML = newsListSkeletonHtml();
    }
    const params = new URLSearchParams({ limit: "30", offset: String(state.newsOffset) });
    if (state.newsFilterSourceId) params.set("source_id", state.newsFilterSourceId);
    if (state.newsQuery.trim()) params.set("q", state.newsQuery.trim());
    if (state.newsUnreadOnly) params.set("unread", "1");
    if (state.newsTopic) params.set("topic", state.newsTopic);
    try {
      const data = await api(`/api/news?${params}`);
      if (!routeStillActive(seq) || requestSeq !== state.newsRequestSeq) return;
      const items = data.items || [];
      state.newsItems = reset ? items : state.newsItems.concat(items);
      state.newsOffset = data.next_offset || state.newsItems.length;
      state.newsHasMore = !!data.has_more;
      if (reset) {
        const hasSource = state.newsSources.some((source) => source.selected) || state.newsFilterSourceId;
        list.innerHTML = state.newsItems.length ? newsListHtml(state.newsItems) : emptyState(
          state.newsUnreadOnly ? "没有未读文章，已经全部看完了" : hasSource ? "没有符合条件的财经新闻" : "还没有选择新闻来源",
          `<div><button type="button" class="btn-normal" onclick="openNewsSourcePicker()">选择来源</button></div>`,
        );
      } else if (items.length) {
        list.insertAdjacentHTML("beforeend", newsListHtml(items));
      }
      attachListImages(seq);
      startNewsAutoLoad(seq);
    } catch (err) {
      if (!routeStillActive(seq) || requestSeq !== state.newsRequestSeq) return;
      list.innerHTML = emptyState("加载失败: " + err.message, `<div><button type="button" class="btn-ghost" onclick="loadFinancialNews(${reset})">重试</button></div>`);
    }
  }

  async function loadNewsImageBlob(articleId, index, image, seq = currentRouteSeq()) {
    const cached = state.newsImageUrls.get(newsImageUrlKey(articleId, index));
    if (cached) {
      if (image && document.body.contains(image)) image.src = cached;
      return;
    }
    try {
      const blob = await apiBlob(`/api/news/${articleId}/images/${index}`);
      if (!routeStillActive(seq) || !image || !document.body.contains(image)) return;
      const url = URL.createObjectURL(blob);
      state.newsImageUrls.set(newsImageUrlKey(articleId, index), url);
      image.src = url;
    } catch {
      if (routeStillActive(seq) && image && document.body.contains(image)) image.remove();
    }
  }

  async function loadNewsImages(articleId, seq = currentRouteSeq()) {
    const images = [...document.querySelectorAll("[data-news-image-index]")];
    await Promise.all(images.map((image) => loadNewsImageBlob(articleId, Number(image.dataset.newsImageIndex), image, seq)));
  }

  function newsFontSizeClass() {
    const size = (state.user && state.user.news_font_size) || "";
    return size === "small" ? " news-font-small" : size === "large" ? " news-font-large" : "";
  }

  function startReadProgress() {
    stopReadProgress();
    state.newsProgressHandler = () => {
      const bar = document.querySelector(".news-read-progress i");
      const body = document.querySelector(".news-article-body");
      if (!bar || !body) return;
      const top = body.offsetTop - 56;
      const total = Math.max(1, body.offsetHeight - window.innerHeight + 80);
      const progress = Math.max(0, Math.min(1, (window.scrollY - top) / total));
      bar.style.transform = `scaleX(${progress})`;
    };
    window.addEventListener("scroll", state.newsProgressHandler, { passive: true });
    state.newsProgressHandler();
  }

  async function renderFinancialNewsArticle(articleId, seq = currentRouteSeq()) {
    setPageTitle("财经新闻", true, "news", "返回财经新闻");
    const main = $("#main");
    if (!main) return;
    main.innerHTML = `<article class="news-article-page"><div class="admin-skeleton" aria-hidden="true"></div></article>`;
    window.scrollTo(0, 0);
    stopReadProgress();
    try {
      const article = await api(`/api/news/${articleId}`);
      if (!routeStillActive(seq)) return;
      void api(`/api/news/${articleId}/read`, { method: "POST" }).then(() => {
        if (!routeStillActive(seq)) return;
        applyNewsItemRead(articleId);
        syncUnreadBadge();
      }).catch(() => {});
      const pager = (article.prev_id || article.next_id) ? `
        <div class="news-article-nav">
          ${article.prev_id ? `<button type="button" class="btn-ghost" onclick="openNewsArticle(${article.prev_id})">← 上一篇</button>` : "<span></span>"}
          ${article.next_id ? `<button type="button" class="btn-ghost" onclick="openNewsArticle(${article.next_id})">下一篇 →</button>` : "<span></span>"}
        </div>` : "";
      main.innerHTML = `
        <div class="news-read-progress" aria-hidden="true"><i></i></div>
        <article class="news-article-page">
          <header class="news-article-head">
            <div class="news-article-meta"><span>${escapeHtml(article.source_name || "")}</span><time datetime="${escapeHtml(article.published_at || "")}">${escapeHtml(fmtPublished(article.published_at, false))}</time></div>
            <h1>${escapeHtml(article.title)}</h1>
            ${article.author ? `<p class="section-meta">作者：${escapeHtml(article.author)}</p>` : ""}
            <div class="news-article-tools">
              <a class="btn-ghost news-original-link" href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer nofollow">打开原文 ${externalLinkIcon}</a>
              <div class="news-font-switch" role="group" aria-label="正文字号">
                ${[["small", "小"], ["", "标准"], ["large", "大"]].map(([value, label]) => `
                  <button type="button" class="${((state.user && state.user.news_font_size) || "") === value ? "is-on" : ""}" onclick="setNewsFontSize('${value}')" aria-pressed="${((state.user && state.user.news_font_size) || "") === value}">${label}</button>`).join("")}
              </div>
            </div>
          </header>
          <div class="news-article-body${newsFontSizeClass()}">${article.content_html || `<p>${escapeHtml(article.summary || "暂无正文")}</p>`}</div>
          ${pager}
        </article>`;
      loadNewsImages(articleId, seq);
      startReadProgress();
    } catch (err) {
      if (routeStillActive(seq)) main.innerHTML = emptyState("加载失败: " + err.message, `<div><button type="button" class="btn-ghost" onclick="renderFinancialNewsArticle(${articleId})">重试</button></div>`);
    }
  }

  function applyNewsItemRead(articleId) {
    const item = state.newsItems.find((entry) => Number(entry.id) === Number(articleId));
    if (!item || item.is_read) return false;
    item.is_read = true;
    item.is_new = false;
    state.newsUnreadCount = Math.max(0, Number(state.newsUnreadCount) - 1);
    const source = state.newsSources.find((entry) => Number(entry.id) === Number(item.source_id));
    if (source) source.unread_count = Math.max(0, Number(source.unread_count) - 1);
    return true;
  }

  async function markNewsItemRead(articleId, { navigate = false } = {}) {
    const seq = currentRouteSeq();
    const item = state.newsItems.find((entry) => Number(entry.id) === Number(articleId));
    const changed = item && !item.is_read;
    if (changed) applyNewsItemRead(articleId);
    try {
      if (changed) await api(`/api/news/${articleId}/read`, { method: "POST" });
      if (!routeStillActive(seq)) return;
      syncUnreadBadge();
      if (navigate) return go(`news/${articleId}`);
      if (!$("#news-list")) return;
      renderNewsListShell(state.newsCollectionEnabled !== false);
      const list = $("#news-list");
      list.innerHTML = state.newsItems.length ? newsListHtml(state.newsItems) : emptyState("没有符合条件的财经新闻");
      attachListImages(seq);
      startNewsAutoLoad(seq);
    } catch (err) {
      if (changed && routeStillActive(seq)) await renderFinancialNewsList(seq);
      flash(err.message, "error");
    }
  }

  function openNewsArticle(articleId) {
    const id = Number(articleId);
    if (Number.isInteger(id) && id > 0) {
      state.newsListKey = newsListKey();
      state.newsScrollY = window.scrollY;
      const item = state.newsItems.find((entry) => Number(entry.id) === Number(id));
      if (item && !item.is_read) return markNewsItemRead(id, { navigate: true });
      go(`news/${id}`);
    }
  }

  async function toggleNewsUnreadOnly() {
    state.newsUnreadOnly = !state.newsUnreadOnly;
    state.newsListKey = newsListKey();
    if (state.newsUnreadOnly) await refreshUnreadCount(currentRouteSeq());
    renderNewsListShell(state.newsCollectionEnabled !== false);
    await loadFinancialNews(true, currentRouteSeq());
  }

  async function markAllNewsRead() {
    const seq = currentRouteSeq();
    try {
      const data = await api("/api/news/read-all", { method: "POST" });
      state.newsUnreadCount = 0;
      state.newsSources.forEach((source) => { source.unread_count = 0; });
      state.newsItems.forEach((item) => { item.is_read = true; item.is_new = false; });
      readAllUndoPayload = {
        read_all_seen_at: data.read_all_seen_at,
        previous_seen_at: data.previous_seen_at || null,
      };
      syncUnreadBadge();
      if (!routeStillActive(seq)) return;
      const list = $("#news-list");
      if (!list) return;
      renderNewsListShell(state.newsCollectionEnabled !== false);
      $("#news-list").innerHTML = state.newsUnreadOnly ? emptyState("没有未读文章，已经全部看完了") : newsListHtml(state.newsItems);
      if (!state.newsUnreadOnly) {
        attachListImages(seq);
        startNewsAutoLoad(seq);
      }
      const banner = $("#news-read-undo");
      banner.hidden = false;
      banner.innerHTML = `<span>已将全部资讯标为已读</span><button type="button" onclick="undoNewsReadAll()">撤销</button>`;
      clearTimeout(readAllUndoTimer);
      readAllUndoTimer = setTimeout(clearNewsReadUndo, 5000);
    } catch (err) { flash(err.message, "error"); }
  }

  async function undoNewsReadAll() {
    if (!readAllUndoPayload) return;
    const payload = readAllUndoPayload;
    clearNewsReadUndo();
    try {
      await api("/api/news/read-all/undo", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.newsListKey = "";
      await renderFinancialNewsList(currentRouteSeq());
      flash("已撤销全部已读");
    } catch (err) {
      flash(err.message, "error");
      await refreshUnreadCount(currentRouteSeq());
    }
  }

  async function setNewsFontSize(value) {
    try {
      const data = await api("/api/me", { method: "PUT", body: JSON.stringify({ news_font_size: value }) });
      if (state.user) state.user.news_font_size = data.news_font_size || value;
      const body = document.querySelector(".news-article-body");
      if (body) {
        body.classList.remove("news-font-small", "news-font-large");
        if (value) body.classList.add(`news-font-${value}`);
      }
      document.querySelectorAll(".news-font-switch button").forEach((button) => {
        const on = button.textContent === (value === "small" ? "小" : value === "large" ? "大" : "标准");
        button.classList.toggle("is-on", on);
        button.setAttribute("aria-pressed", on ? "true" : "false");
      });
    } catch (err) { flash(err.message, "error"); }
  }

  function newsSourcePickerRows(filter = "", selectedIds = null) {
    const q = filter.trim().toLowerCase();
    const visible = state.newsSources.filter((source) => !q || source.name.toLowerCase().includes(q));
    if (!visible.length) return '<p class="muted">没有匹配的媒体</p>';
    if (q) {
      return visible.map((source) => newsSourceOptionHtml(source, selectedIds)).join("");
    }
    const groups = new Map();
    for (const source of visible) {
      const label = source.group_name || "未分组";
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(source);
    }
    const ordered = [...groups.entries()].sort((a, b) => (a[0] === "未分组") - (b[0] === "未分组"));
    return ordered.map(([label, sources]) => `
      <div class="news-source-group-label">${escapeHtml(label)}</div>
      ${sources.map((source) => newsSourceOptionHtml(source, selectedIds)).join("")}`).join("");
  }

  function newsSourceOptionHtml(source, selectedIds) {
    return `<label class="news-source-option"><input type="checkbox" value="${source.id}" ${(selectedIds ? selectedIds.has(Number(source.id)) : source.selected) ? "checked" : ""}><span>${escapeHtml(source.name)}</span>${source.enabled ? "" : '<em>管理员已暂停更新</em>'}</label>`;
  }

  function openNewsSourcePicker() {
    const newsSelectedIds = new Set(state.newsSources.filter((source) => source.selected).map((source) => Number(source.id)));
    const mask = document.createElement("div");
    mask.className = "modal-mask news-source-modal";
    mask._newsSelectedIds = newsSelectedIds;
    mask.innerHTML = `<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="news-source-picker-title"><h3 id="news-source-picker-title">我的来源</h3><input id="news-source-search" class="form-control" type="search" placeholder="搜索媒体"><div id="news-source-options" class="news-source-options">${newsSourcePickerRows("", newsSelectedIds)}</div><div class="toolbar"><button type="button" class="btn-normal" onclick="saveNewsSources(this.closest('.news-source-modal'))">保存</button><button type="button" class="btn-ghost" data-close>取消</button></div></div>`;
    document.body.appendChild(mask);
    const close = () => mask.remove();
    const captureSelection = () => {
      mask.querySelectorAll(".news-source-option input").forEach((input) => {
        const id = Number(input.value);
        if (input.checked) newsSelectedIds.add(id);
        else newsSelectedIds.delete(id);
      });
    };
    mask.addEventListener("click", (event) => { if (event.target === mask) close(); });
    trapFocus(mask, close);
    mask.querySelector("[data-close]").addEventListener("click", close);
    mask.querySelector("#news-source-search").addEventListener("input", (event) => {
      captureSelection();
      mask.querySelector("#news-source-options").innerHTML = newsSourcePickerRows(event.target.value, newsSelectedIds);
    });
    mask.querySelector("#news-source-search").focus();
  }

  async function saveNewsSources(mask) {
    if (!mask) return;
    const ids = (() => {
      const selected = mask._newsSelectedIds || new Set();
      mask.querySelectorAll(".news-source-option input").forEach((input) => {
        const id = Number(input.value);
        if (input.checked) selected.add(id);
        else selected.delete(id);
      });
      return [...selected];
    })();
    const button = mask.querySelector("button.btn-normal");
    if (button) button.disabled = true;
    const seq = currentRouteSeq();
    try {
      await api("/api/me", { method: "PUT", body: JSON.stringify({ news_source_ids: ids }) });
      if (!routeStillActive(seq)) return;
      mask.remove();
      state.newsFilterSourceId = "";
      state.newsListKey = "";
      flash("新闻来源已保存");
      await renderFinancialNewsList(seq);
    } catch (err) {
      flash(err.message, "error");
      if (button) button.disabled = false;
    }
  }

  function selectNewsSource(sourceId) {
    state.newsFilterSourceId = sourceId;
    state.newsListKey = newsListKey();
    renderNewsListShell(state.newsCollectionEnabled !== false);
    return loadFinancialNews(true, currentRouteSeq());
  }

  function selectNewsTopic(topic) {
    state.newsTopic = topic || "";
    state.newsListKey = newsListKey();
    renderNewsListShell(state.newsCollectionEnabled !== false);
    return loadFinancialNews(true, currentRouteSeq());
  }

  function queueNewsSearch(query) {
    state.newsQuery = query;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.newsListKey = newsListKey();
      loadFinancialNews(true, currentRouteSeq());
    }, 250);
  }

  return {
    clearNewsReaderState,
    loadFinancialNews,
    markAllNewsRead,
    markNewsItemRead,
    openNewsArticle,
    openNewsSourcePicker,
    queueNewsSearch,
    renderFinancialNewsArticle,
    renderFinancialNewsList,
    renderNewsCenter,
    saveNewsSources,
    selectNewsSource,
    selectNewsTopic,
    setNewsFontSize,
    toggleNewsUnreadOnly,
    undoNewsReadAll,
  };
}
