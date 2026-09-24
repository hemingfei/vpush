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
  let releaseSourceSheet = null;

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

  function newsListItemHtml(item) {
    const unread = !item.is_read;
    const thumbnail = item.has_image
      ? `<img class="news-list-thumb" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 3 2'%3E%3C/svg%3E" data-news-thumbnail="${item.id}" alt="" width="112" height="75" loading="lazy" onerror="this.closest('.news-list-thumb-link').style.display='none'">`
      : "";
    const activeTopic = state.newsTopic || "";
    const topicNames = (Array.isArray(item.topics) ? item.topics : []).filter((topic) => topic && topic !== item.source_name);
    const topics = topicNames.length
      ? `<span class="news-item-topics">${topicNames.map((topic) => NEWS_TOPICS.includes(topic) ? `<button type="button" class="news-item-topic${topic === activeTopic ? " is-on" : ""}" aria-pressed="${topic === activeTopic ? "true" : "false"}" onclick="selectNewsTopic('${topic}')">${escapeHtml(topic)}</button>` : `<i>${escapeHtml(topic)}</i>`).join("")}</span>`
      : "";
    return `<article class="news-list-item ${unread ? "is-unread" : "is-read"}" data-news-id="${item.id}">
    <div class="news-list-copy">
      <a class="news-item-open" href="/news/${item.id}">
        <div class="news-item-title-row">${unread ? '<i class="news-item-unread-dot" aria-label="未读"></i>' : ""}<h3>${escapeHtml(item.title)}</h3></div>
        <p>${escapeHtml(item.summary || "暂无摘要")}</p>
      </a>
      <div class="news-list-meta"><span class="news-item-source">${escapeHtml(item.source_name || "")}</span><time datetime="${escapeHtml(item.published_at || "")}">${escapeHtml(fmtPublished(item.published_at, true))}</time>${topics}${unread ? `<button type="button" class="news-mark-read" onclick="markNewsItemRead(${item.id})" aria-label="标为已读">${CHECK_ICON}</button>` : ""}</div>
    </div>${thumbnail ? `<a class="news-list-thumb-link" href="/news/${item.id}" tabindex="-1" aria-hidden="true">${thumbnail}</a>` : ""}
  </article>`;
  }

  function newsListHtml(items, { append = false } = {}) {
    const groups = groupNewsItemsByDay(items);
    let continued = "";
    if (append) {
      const labels = document.querySelectorAll("#news-list .news-day-sep span");
      continued = labels.length ? labels[labels.length - 1].textContent : "";
    }
    return groups.map((group, index) => {
      const head = append && index === 0 && group.label === continued
        ? ""
        : `<div class="news-day-sep"><span>${escapeHtml(group.label)}</span></div>`;
      return `${head}${group.items.map(newsListItemHtml).join("")}`;
    }).join("");
  }

  function magazineShelfHtml(issues) {
    const years = new Map();
    for (const issue of issues) {
      const year = String(issue.published_at || "").slice(0, 4) || "更早";
      if (!years.has(year)) years.set(year, []);
      years.get(year).push(issue);
    }
    return `<div class="news-magazine">${[...years.entries()].map(([year, list], index) => `
      <details class="news-magazine-year" ${index === 0 ? "open" : ""}>
        <summary>${escapeHtml(year)} 年<span>${list.length} 期</span></summary>
        <div class="news-magazine-issues">${list.map((issue, issueIndex) => {
          const read = issue.articles.filter((article) => article.is_read).length;
          const cover = issue.cover
            ? `<img class="news-issue-cover" src="${escapeHtml(issue.cover)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
            : `<span class="news-issue-cover is-blank" aria-hidden="true"></span>`;
          let lastSection = "";
          const articles = issue.articles.map((article) => {
            const section = article.section && article.section !== lastSection
              ? `<div class="news-issue-section">${escapeHtml(lastSection = article.section)}</div>`
              : "";
            return `${section}<a class="news-issue-article ${article.is_read ? "is-read" : ""}" href="/news/${article.id}"><strong>${escapeHtml(article.title)}</strong>${article.author ? `<span>${escapeHtml(article.author)}</span>` : ""}</a>`;
          }).join("");
          return `<details class="news-issue" ${index === 0 && issueIndex === 0 ? "open" : ""}>
            <summary class="news-issue-head">${cover}<span class="news-issue-meta"><b>${escapeHtml(issue.label || "")}</b>${issue.title ? `<em>${escapeHtml(issue.title)}</em>` : ""}<small>${escapeHtml(String(issue.published_at || "").slice(0, 10))} · 已读 ${read} / ${issue.articles.length} 篇</small></span></summary>
            <div class="news-issue-body">${articles}</div>
          </details>`;
        }).join("")}</div>
      </details>`).join("")}</div>`;
  }

  function newsEmptyHtml() {
    const query = (state.newsQuery || "").trim();
    const hasSource = state.newsSources.some((source) => source.selected) || state.newsFilterSourceId;
    if (!hasSource) {
      return emptyState("还没有选择新闻来源", `<div><button type="button" class="btn-normal" onclick="openNewsSourcePicker()">选择来源</button></div>`);
    }
    if (state.newsUnreadOnly && !query && !state.newsTopic && !state.newsFilterSourceId) {
      return emptyState("没有未读文章，已经全部看完了");
    }
    if (query || state.newsTopic || state.newsFilterSourceId || state.newsUnreadOnly) {
      return emptyState("暂无相关财经资讯", `<div><button type="button" class="btn-ghost" onclick="clearNewsFilters()">清除筛选</button></div>`);
    }
    return emptyState("没有符合条件的资讯", `<div><button type="button" class="btn-normal" onclick="openNewsSourcePicker()">选择来源</button></div>`);
  }

  function selectedNewsSources() {
    return state.newsSources.filter((source) => source.selected && source.enabled !== false);
  }

  function newsSourceNavigationHtml() {
    const groups = new Map();
    for (const source of selectedNewsSources()) {
      const label = source.group_name || "其他来源";
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(source);
    }
    for (const sources of groups.values()) {
      sources.sort((a, b) => (Number(b.unread_count) || 0) - (Number(a.unread_count) || 0) || String(a.name).localeCompare(String(b.name), "zh"));
    }
    const allOn = !state.newsFilterSourceId;
    const groupOrder = ["财新", "FT中文"];
    const rows = [...groups.entries()].sort((a, b) => {
      const ia = groupOrder.indexOf(a[0]);
      const ib = groupOrder.indexOf(b[0]);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a[0].localeCompare(b[0], "zh");
    }).map(([label, sources]) => `
    <details class="news-source-group" open>
      <summary>${CHEVRON_DOWN_ICON}<span>${escapeHtml(label)}</span></summary>
      ${sources.map((source) => {
        const magazine = source.kind === "magazine";
        const badge = magazine ? "" : (Number(source.unread_count) || "");
        return `<button type="button" class="news-source-row ${String(state.newsFilterSourceId) === String(source.id) ? "is-on" : ""}" data-source-id="${source.id}" onclick="selectNewsSource('${source.id}')"><span>${escapeHtml(source.name)}</span><b>${badge}</b></button>`;
      }).join("")}
    </details>`).join("");
    return `<nav class="news-source-rail" id="news-source-rail" aria-label="资讯来源">
    <div class="news-source-rail-head"><strong>资讯来源</strong><button type="button" class="icon-btn" onclick="openNewsSourcePicker()" aria-label="管理资讯来源" title="管理资讯来源">${GEAR_ICON}</button></div>
    <button type="button" class="news-source-row news-source-all ${allOn ? "is-on" : ""}" onclick="selectNewsSource('')">${NEWS_ICON}<span>全部资讯</span><b>${Number(state.newsUnreadCount) || ""}</b></button>
    ${rows || '<p class="muted">尚未选择资讯来源</p>'}
  </nav>`;
  }

  function newsSourceSwitchLabel() {
    if (!state.newsFilterSourceId) return "全部资讯";
    const source = state.newsSources.find((item) => String(item.id) === String(state.newsFilterSourceId));
    return source?.name || "指定来源";
  }

  function newsActiveFilterParts() {
    const parts = [];
    if (state.newsFilterSourceId) {
      const source = state.newsSources.find((item) => String(item.id) === String(state.newsFilterSourceId));
      parts.push(source?.name || "指定来源");
    }
    if (state.newsTopic) parts.push(state.newsTopic);
    if (state.newsUnreadOnly) parts.push("未读");
    const query = (state.newsQuery || "").trim();
    if (query) parts.push(`「${query}」`);
    return parts;
  }

  function newsFilterSummaryHtml() {
    const parts = newsActiveFilterParts();
    const body = parts.length ? `<span>${parts.map((part) => escapeHtml(part)).join(" · ")}</span><button type="button" class="btn-ghost" onclick="clearNewsFilters()">清除</button>` : "";
    return `<div id="news-filter-summary" class="news-filter-summary"${parts.length ? "" : " hidden"}>${body}</div>`;
  }

  function syncNewsFilterChrome() {
    const topic = state.newsTopic || "";
    const selected = String(state.newsFilterSourceId || "");
    document.querySelectorAll(".news-item-topic").forEach((button) => {
      const on = !!topic && (button.textContent || "").trim() === topic;
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-pressed", on ? "true" : "false");
    });
    const unread = document.querySelector(".news-unread-toggle");
    if (unread) {
      unread.classList.toggle("is-on", !!state.newsUnreadOnly);
      unread.setAttribute("aria-pressed", state.newsUnreadOnly ? "true" : "false");
    }
    document.querySelectorAll(".news-source-row").forEach((row) => {
      const on = selected ? row.dataset.sourceId === selected : row.classList.contains("news-source-all");
      row.classList.toggle("is-on", on);
    });
    const switchLabel = document.querySelector(".news-source-switch span");
    if (switchLabel) switchLabel.textContent = newsSourceSwitchLabel();
    const input = $("#news-query");
    if (input && input.value !== (state.newsQuery || "")) input.value = state.newsQuery || "";
    const summary = document.querySelector("#news-filter-summary");
    if (summary) summary.outerHTML = newsFilterSummaryHtml();
  }

  function applyNewsListFilter() {
    state.newsListKey = newsListKey();
    syncNewsFilterChrome();
    return loadFinancialNews(true, currentRouteSeq());
  }

  function newsListSkeletonHtml() {
    const card = '<div class="admin-sk-card"><div class="news-sk-copy"><div class="admin-sk-line admin-sk-head"></div><div class="admin-sk-line"></div><div class="admin-sk-line"></div></div><div class="news-sk-thumb"></div></div>';
    return `<div class="admin-skeleton" aria-hidden="true">${card.repeat(3)}</div>`;
  }

  function renderNewsListShell(collectionEnabled = true) {
    const main = $("#main");
    if (!main) return;
    const unreadOn = !!state.newsUnreadOnly;
    const unreadCount = Number(state.newsUnreadCount) || 0;
    const searching = !!(state.newsQuery || "").trim();
    main.innerHTML = `<section class="news-page${searching ? " is-searching" : ""}" id="news-page">
  <header class="news-stream-head">
    <div class="news-stream-title"><button type="button" class="news-source-switch" onclick="toggleNewsSourceSheet()" aria-haspopup="dialog" aria-expanded="false" aria-controls="news-source-rail"><span>${escapeHtml(newsSourceSwitchLabel())}</span>${CHEVRON_DOWN_ICON}</button></div>
    <div class="news-stream-actions">
      <button type="button" class="news-unread-toggle ${unreadOn ? "is-on" : ""}" onclick="toggleNewsUnreadOnly()" aria-pressed="${unreadOn}" aria-label="未读">${EYE_ICON}<span>未读</span>${unreadCount ? `<b>${unreadCount > 99 ? "99+" : unreadCount}</b>` : ""}</button>
      <button type="button" class="icon-btn news-search-toggle${searching ? " is-on" : ""}" onclick="toggleNewsSearch()" aria-expanded="${searching ? "true" : "false"}" aria-label="搜索资讯">${SEARCH_ICON}</button>
      ${unreadCount ? `<button type="button" class="btn-ghost news-read-all" onclick="markAllNewsRead()" aria-label="全部已读">${CHECK_CHECK_ICON}<span>全部已读</span></button>` : ""}
      <button type="button" class="btn-ghost news-source-manage" onclick="openNewsSourcePicker()">${GEAR_ICON}<span>我的来源</span></button>
    </div>
    <label class="news-stream-search">${SEARCH_ICON}<input id="news-query" type="search" placeholder="搜索资讯..." value="${escapeHtml(state.newsQuery)}" oninput="queueNewsSearch(this.value)" aria-label="搜索资讯"></label>
  </header>
  ${collectionEnabled ? "" : '<div class="notice notice-warn">管理员已暂停资讯采集，历史文章仍可阅读。</div>'}
  <div class="news-stream-layout">
    <main class="news-stream-main">
      ${newsFilterSummaryHtml()}
      <div id="news-list" class="news-list">${newsListSkeletonHtml()}</div>
      <div id="news-load-sentinel" class="news-load-sentinel" role="status" aria-live="polite"></div>
    </main>
    ${newsSourceNavigationHtml()}
  </div>
  <div class="news-source-backdrop" onclick="toggleNewsSourceSheet(false)" aria-hidden="true"></div>
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
    setPageTitle("财经资讯");
    // 文章返回且筛选未变：直接复用已加载列表并恢复滚动位置
    if (state.newsItems.length && state.newsListKey === newsListKey() && !state.newsMagazine) {
      renderNewsListShell(state.newsCollectionEnabled !== false);
      const list = $("#news-list");
      list.innerHTML = state.newsItems.length ? newsListHtml(state.newsItems) : newsEmptyHtml();
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
      state.newsOffset = 0;
      if (!list.querySelector(".news-list-item, .empty-state")) list.innerHTML = newsListSkeletonHtml();
    }
    const picked = state.newsSources.find((source) => String(source.id) === String(state.newsFilterSourceId));
    if (reset && picked && picked.kind === "magazine") {
      state.newsMagazine = true;
      state.newsHasMore = false;
      stopNewsAutoLoad();
      try {
        const data = await api(`/api/news/magazine?source_id=${encodeURIComponent(picked.id)}`);
        if (!routeStillActive(seq) || requestSeq !== state.newsRequestSeq) return;
        state.newsIssues = data.issues || [];
        state.newsItems = [];
        list.innerHTML = state.newsIssues.length ? magazineShelfHtml(state.newsIssues) : newsEmptyHtml();
      } catch (err) {
        if (!routeStillActive(seq) || requestSeq !== state.newsRequestSeq) return;
        list.innerHTML = emptyState("加载失败: " + err.message, `<div><button type="button" class="btn-ghost" onclick="loadFinancialNews(true)">重试</button></div>`);
      }
      return;
    }
    state.newsMagazine = false;
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
        list.innerHTML = state.newsItems.length ? newsListHtml(state.newsItems) : newsEmptyHtml();
      } else if (items.length) {
        list.insertAdjacentHTML("beforeend", newsListHtml(items, { append: true }));
      }
      const sentinel = $("#news-load-sentinel");
      if (sentinel) sentinel.innerHTML = "";
      attachListImages(seq);
      startNewsAutoLoad(seq);
    } catch (err) {
      if (!routeStillActive(seq) || requestSeq !== state.newsRequestSeq) return;
      if (!reset && state.newsItems.length) {
        stopNewsAutoLoad();
        const sentinel = $("#news-load-sentinel");
        if (sentinel) sentinel.innerHTML = `<button type="button" class="btn-ghost" onclick="loadFinancialNews(false)">加载失败，点击重试</button>`;
        return;
      }
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
      if (routeStillActive(seq) && image && document.body.contains(image)) {
        const link = image.closest(".news-list-thumb-link");
        if (link) link.remove();
        else image.remove();
      }
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
    setPageTitle("财经资讯", true, "news", "返回财经资讯");
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

  function paintNewsUnreadChrome() {
    const count = Number(state.newsUnreadCount) || 0;
    const badge = count > 99 ? "99+" : String(count);
    document.querySelectorAll(".news-unread-toggle").forEach((button) => {
      let mark = button.querySelector("b");
      if (!count) {
        mark?.remove();
        return;
      }
      if (!mark) {
        mark = document.createElement("b");
        button.appendChild(mark);
      }
      mark.textContent = badge;
    });
    document.querySelectorAll(".news-source-all b").forEach((node) => {
      node.textContent = count ? String(count) : "";
    });
    for (const source of state.newsSources) {
      const row = document.querySelector(`.news-source-row[data-source-id="${source.id}"] b`);
      if (row) row.textContent = Number(source.unread_count) ? String(source.unread_count) : "";
    }
    if (!count) document.querySelector(".news-read-all")?.remove();
  }

  function paintNewsItemRead(articleId) {
    const card = document.querySelector(`[data-news-id="${articleId}"]`);
    if (!card) return false;
    if (state.newsUnreadOnly) {
      card.remove();
      const list = $("#news-list");
      if (list && !list.querySelector(".news-list-item")) list.innerHTML = newsEmptyHtml();
      return true;
    }
    card.classList.remove("is-unread");
    card.classList.add("is-read");
    card.querySelector(".news-item-unread-dot")?.remove();
    card.querySelector(".news-mark-read")?.remove();
    return true;
  }

  async function markNewsItemRead(articleId, { navigate = false } = {}) {
    const seq = currentRouteSeq();
    const item = state.newsItems.find((entry) => Number(entry.id) === Number(articleId));
    const changed = item && !item.is_read;
    if (changed) applyNewsItemRead(articleId);
    if (changed && !navigate && $("#news-list")) {
      paintNewsItemRead(articleId);
      paintNewsUnreadChrome();
    }
    try {
      if (changed) await api(`/api/news/${articleId}/read`, { method: "POST" });
      if (!routeStillActive(seq)) return;
      syncUnreadBadge();
      if (navigate) return go(`news/${articleId}`);
      if (!$("#news-list")) return;
      if (changed) return;
      renderNewsListShell(state.newsCollectionEnabled !== false);
      const list = $("#news-list");
      list.innerHTML = state.newsItems.length ? newsListHtml(state.newsItems) : newsEmptyHtml();
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
    if (state.newsUnreadOnly) await refreshUnreadCount(currentRouteSeq());
    return applyNewsListFilter();
  }

  async function markAllNewsRead() {
    const seq = currentRouteSeq();
    const marked = Number(state.newsUnreadCount) || 0;
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
      $("#news-list").innerHTML = state.newsUnreadOnly ? newsEmptyHtml() : newsListHtml(state.newsItems);
      if (!state.newsUnreadOnly) {
        attachListImages(seq);
        startNewsAutoLoad(seq);
      }
      const banner = $("#news-read-undo");
      banner.hidden = false;
      banner.innerHTML = `<span>已将 ${marked} 篇资讯标为已读</span><button type="button" onclick="undoNewsReadAll()">撤销</button>`;
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
    toggleNewsSourceSheet(false);
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

  function toggleNewsSourceSheet(force) {
    const page = $("#news-page");
    const rail = $("#news-source-rail");
    if (!page || !rail) return;
    const open = typeof force === "boolean" ? force : !page.classList.contains("is-sources-open");
    if (open === page.classList.contains("is-sources-open")) return;
    page.classList.toggle("is-sources-open", open);
    const trigger = page.querySelector(".news-source-switch");
    trigger?.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      rail.setAttribute("role", "dialog");
      rail.setAttribute("aria-modal", "true");
      releaseSourceSheet = trapFocus(rail, () => toggleNewsSourceSheet(false));
      rail.querySelector(".news-source-row.is-on")?.focus();
      return;
    }
    rail.removeAttribute("role");
    rail.removeAttribute("aria-modal");
    releaseSourceSheet?.();
    releaseSourceSheet = null;
    trigger?.focus();
  }

  function selectNewsSource(sourceId) {
    toggleNewsSourceSheet(false);
    state.newsFilterSourceId = sourceId;
    return applyNewsListFilter();
  }

  function toggleNewsSearch() {
    const page = $("#news-page");
    if (!page) return;
    const open = page.classList.toggle("is-searching");
    const button = page.querySelector(".news-search-toggle");
    if (button) {
      button.setAttribute("aria-expanded", open ? "true" : "false");
      button.classList.toggle("is-on", open || !!(state.newsQuery || "").trim());
    }
    if (open) $("#news-query")?.focus();
  }

  function clearNewsFilters() {
    state.newsUnreadOnly = false;
    state.newsQuery = "";
    state.newsTopic = "";
    state.newsFilterSourceId = "";
    return applyNewsListFilter();
  }

  function selectNewsTopic(topic) {
    const next = topic || "";
    state.newsTopic = state.newsTopic === next ? "" : next;
    return applyNewsListFilter();
  }

  function queueNewsSearch(query) {
    state.newsQuery = query;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.newsListKey = newsListKey();
      syncNewsFilterChrome();
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
    clearNewsFilters,
    selectNewsSource,
    selectNewsTopic,
    setNewsFontSize,
    toggleNewsSearch,
    toggleNewsSourceSheet,
    toggleNewsUnreadOnly,
    undoNewsReadAll,
  };
}
