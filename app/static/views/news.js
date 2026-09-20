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
  } = dependencies;
  let searchTimer = null;

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
    return `${state.newsFilterSourceId || ""}|${(state.newsQuery || "").trim()}|${state.newsUnreadOnly ? "u" : ""}`;
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

  function newsListItemHtml(item) {
    const thumbnail = item.has_image
      ? `<img class="news-list-thumb" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 64'%3E%3C/svg%3E" data-news-thumbnail="${item.id}" alt="" loading="lazy" onerror="this.style.display='none'">`
      : "";
    return `<article class="news-list-item" data-news-id="${item.id}" tabindex="0" role="link" onclick="openNewsArticle(${item.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openNewsArticle(${item.id})}">
      <div class="news-list-copy"><div class="news-list-meta"><span>${escapeHtml(item.source_name || "")}</span><time datetime="${escapeHtml(item.published_at || "")}">${escapeHtml(fmtPublished(item.published_at, true))}</time>${item.is_new ? '<span class="news-new-label">新</span>' : ""}</div>
      <h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary || "暂无摘要")}</p></div>${thumbnail}
    </article>`;
  }

  function newsListHtml(items) {
    return groupNewsItemsByDay(items).map((group) => `
      <div class="news-day-sep"><span>${escapeHtml(group.label)}</span></div>
      ${group.items.map(newsListItemHtml).join("")}`).join("");
  }

  function newsGroupedOptions() {
    const groups = new Map();
    for (const source of state.newsSources) {
      const label = source.group_name || "未分组";
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(source);
    }
    const ordered = [...groups.entries()].sort((a, b) => (a[0] === "未分组") - (b[0] === "未分组"));
    return `<option value="">全部来源</option>${ordered.map(([label, sources]) => `
      <optgroup label="${escapeHtml(label)}">${sources.map((source) => {
        const suffix = source.selected ? "" : source.enabled ? "（未订阅）" : "（未订阅·已停用）";
        return `<option value="${source.id}" ${String(state.newsFilterSourceId) === String(source.id) ? "selected" : ""}>${escapeHtml(source.name + suffix)}</option>`;
      }).join("")}</optgroup>`).join("")}`;
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
      <header class="news-page-head"><div><h2 class="section-title">财经新闻</h2><p class="section-meta">${unreadCount ? `${unreadCount} 篇未读` : "按媒体聚合的长文阅读，原文链接保留。"}</p></div><button type="button" class="btn-normal" onclick="openNewsSourcePicker()">我的来源</button></header>
      ${collectionEnabled ? "" : '<div class="notice notice-warn">管理员已暂停财经新闻采集，历史文章仍可阅读。</div>'}
      <div class="news-list-toolbar">
        <div class="news-toolbar-filters">
          <button type="button" class="news-unread-toggle ${unreadOn ? "is-on" : ""}" onclick="toggleNewsUnreadOnly()" aria-pressed="${unreadOn}">只看未读${unreadCount ? `<b>${unreadCount > 99 ? "99+" : unreadCount}</b>` : ""}</button>
          <select id="news-source-filter" class="form-control" aria-label="新闻来源" onchange="selectNewsSource(this.value)">${newsGroupedOptions()}</select>
          <div class="search-bar"><input id="news-query" type="search" placeholder="搜索标题或摘要" value="${escapeHtml(state.newsQuery)}" oninput="queueNewsSearch(this.value)"></div>
        </div>
        ${unreadCount ? '<button type="button" class="btn-ghost news-read-all" onclick="markAllNewsRead()">全部已读</button>' : ""}
      </div>
      <div id="news-list" class="news-list">${newsListSkeletonHtml()}</div>
      <div id="news-load-sentinel" class="news-load-sentinel" role="status" aria-live="polite"></div>
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
      if (state.newsItems.length && !state.newsUnreadOnly) {
        const seenAt = data.view_started_at;
        await Promise.resolve();
        if (!routeStillActive(seq) || requestSeq !== state.newsRequestSeq) return;
        if (seenAt) api("/api/news/seen", { method: "POST", body: JSON.stringify({ view_started_at: seenAt }) }).catch(() => {});
      }
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

  function openNewsArticle(articleId) {
    const id = Number(articleId);
    if (Number.isInteger(id) && id > 0) {
      state.newsListKey = newsListKey();
      state.newsScrollY = window.scrollY;
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
    if (!confirm("把全部文章标记为已读？")) return;
    try {
      await api("/api/news/read-all", { method: "POST" });
      state.newsUnreadCount = 0;
      syncUnreadBadge();
      flash("已全部标记为已读");
      if (state.newsUnreadOnly) {
        renderNewsListShell(state.newsCollectionEnabled !== false);
        await loadFinancialNews(true, currentRouteSeq());
      } else {
        renderNewsListShell(state.newsCollectionEnabled !== false);
      }
    } catch (err) { flash(err.message, "error"); }
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
    openNewsArticle,
    openNewsSourcePicker,
    queueNewsSearch,
    renderFinancialNewsArticle,
    renderFinancialNewsList,
    renderNewsCenter,
    saveNewsSources,
    selectNewsSource,
    setNewsFontSize,
    toggleNewsUnreadOnly,
  };
}
