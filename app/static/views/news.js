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
    avatarHtml,
    mdToHtml,
    imgSrcFor,
    PLATFORM_LABELS,
    PLATFORM_ICONS,
  } = dependencies;
  let searchTimer = null;
  let rtPollTimer = null;

  function clearNewsImageUrls() {
    for (const url of state.newsImageUrls) URL.revokeObjectURL(url);
    state.newsImageUrls.clear();
  }

  function stopNewsAutoLoad() {
    state.newsObserver?.disconnect();
    state.newsObserver = null;
  }

  function stopNewsThumbLoad() {
    state.newsThumbObserver?.disconnect();
    state.newsThumbObserver = null;
  }

  function stopNewsRtAutoLoad() {
    state.newsRtObserver?.disconnect();
    state.newsRtObserver = null;
  }

  function stopNewsRtPoll() {
    if (rtPollTimer) {
      clearInterval(rtPollTimer);
      rtPollTimer = null;
    }
  }

  function abortNewsImageRequests() {
    state.newsImageAbort?.abort();
    state.newsImageAbort = new AbortController();
  }

  function clearNewsReaderState() {
    stopNewsAutoLoad();
    stopNewsThumbLoad();
    stopNewsRtAutoLoad();
    stopNewsRtPoll();
    abortNewsImageRequests();
    clearTimeout(searchTimer);
    clearNewsImageUrls();
    state.newsSources = [];
    state.newsFilterSourceId = "";
    state.newsQuery = "";
    state.newsItems = [];
    state.newsOffset = 0;
    state.newsHasMore = false;
    state.newsArticleId = 0;
    state.newsRequestSeq += 1;
    state.newsRtItems = [];
    state.newsRtOffset = 0;
    state.newsRtHasMore = false;
    state.newsRtLatestId = 0;
    state.newsRtSeq += 1;
  }

  // 缩略图和正文图都等进入视口再请求，避免一次列表渲染打出几十个图片代理请求
  function dispatchNewsLazyImage(img) {
    img.dataset.newsThumbLoaded = "1";
    const thumbId = img.dataset.newsThumbnail;
    if (thumbId !== undefined) loadNewsImageBlob(Number(thumbId), 0, img);
    else if (state.newsArticleId) loadNewsImageBlob(state.newsArticleId, Number(img.dataset.newsImageIndex), img);
  }

  function observeNewsLazyImages() {
    const pending = document.querySelectorAll(
      "[data-news-thumbnail]:not([data-news-thumb-loaded]), [data-news-image-index]:not([data-news-thumb-loaded])"
    );
    if (!pending.length) return;
    if (!("IntersectionObserver" in window)) {
      pending.forEach(dispatchNewsLazyImage);
      return;
    }
    if (!state.newsThumbObserver) {
      state.newsThumbObserver = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          state.newsThumbObserver?.unobserve(entry.target);
          dispatchNewsLazyImage(entry.target);
        }
      }, { rootMargin: "300px 0px" });
    }
    pending.forEach((img) => state.newsThumbObserver.observe(img));
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

  // ---------- 页面骨架：财经资讯 = 实时资讯（默认）+ 财经新闻 双栏目 ----------

  function newsTabsHtml(active) {
    const tab = (id, label) => `<button type="button" class="news-tab${active === id ? " active" : ""}" role="tab" aria-selected="${active === id}" onclick="selectNewsTab('${id}')">${label}</button>`;
    return `<div class="news-tabs" role="tablist" aria-label="财经资讯栏目">${tab("realtime", "实时资讯")}${tab("articles", "财经新闻")}</div>`;
  }

  function renderNewsShell(active, panelHtml, headActionsHtml = "") {
    const main = $("#main");
    if (!main) return;
    const meta = active === "realtime"
      ? "管理员勾选的大V消息动态流，自动更新。"
      : "按媒体聚合的长文阅读，原文链接保留。";
    main.innerHTML = `<section class="news-page" id="news-page">
      <header class="news-page-head"><div><h2 class="section-title">财经资讯</h2><p class="section-meta">${meta}</p></div>${headActionsHtml}</header>
      ${newsTabsHtml(active)}
      ${panelHtml}
    </section>`;
  }

  function renderNewsCenter(seq, articleId = "") {
    clearNewsImageUrls();
    stopNewsAutoLoad();
    stopNewsThumbLoad();
    stopNewsRtAutoLoad();
    stopNewsRtPoll();
    abortNewsImageRequests();
    if (!routeStillActive(seq)) return;
    if (articleId) return renderFinancialNewsArticle(Number(articleId), seq);
    state.newsTab = "realtime"; // 每次进入页面默认显示实时资讯
    return renderRealtimeNews(seq);
  }

  function selectNewsTab(tab) {
    const next = tab === "articles" ? "articles" : "realtime";
    if (next === state.newsTab) return;
    state.newsTab = next;
    stopNewsRtPoll();
    stopNewsRtAutoLoad();
    const seq = currentRouteSeq();
    window.scrollTo(0, 0);
    if (next === "realtime") return renderRealtimeNews(seq);
    return renderFinancialNewsList(seq);
  }

  // ---------- 实时资讯：管理员勾选的大V动态流 ----------

  function newsRtSkeletonHtml() {
    const card = '<div class="admin-sk-card"><div class="admin-sk-line admin-sk-head"></div><div class="admin-sk-line"></div></div>';
    return `<div class="admin-skeleton" aria-hidden="true">${card.repeat(4)}</div>`;
  }

  async function renderRealtimeNews(seq = currentRouteSeq()) {
    setPageTitle("财经资讯");
    renderNewsShell(
      "realtime",
      `<div id="news-rt-list" class="news-list news-rt-list">${newsRtSkeletonHtml()}</div><div id="news-rt-load-sentinel" class="news-load-sentinel" role="status" aria-live="polite"></div>`,
    );
    state.newsRtItems = [];
    state.newsRtOffset = 0;
    state.newsRtHasMore = false;
    state.newsRtLatestId = 0;
    await loadRealtimeNews(true, seq);
    startNewsRtPoll(seq);
  }

  function newsRtItemHtml(post) {
    const images = (Array.isArray(post.images) ? post.images : []).filter(Boolean);
    const body = (post.content || "").trim() || "（无正文）";
    const expanded = state.newsRtExpanded.has(post.id);
    const shown = expanded ? body : body.slice(0, 200);
    const title = (post.title || "").trim();
    // X 帖常 title==content 或正文以标题开头，重复渲染只会有视觉噪音
    const titleDup = !!title && (title === body || body.startsWith(title));
    const safeUrl = /^https?:\/\//i.test(post.url || "") ? post.url : "";
    const tags = Array.isArray(post.tags) ? post.tags : [];
    return `<article class="news-rt-item post-item" data-post-id="${post.id}">
      <div class="p-header">
        ${avatarHtml(post.kol_name, post.avatar_url, post.platform)}
        <div class="p-name-line">
          <a class="p-name" href="/kol/${post.kol_id}" title="${escapeHtml(post.kol_name || "")}">${escapeHtml(post.kol_name || "")}</a>
          <span class="p-platform" data-platform="${escapeHtml(post.platform)}" title="${escapeHtml(PLATFORM_LABELS[post.platform] || post.platform)}">${PLATFORM_ICONS[post.platform] || ""}</span>
          <time class="p-time" datetime="${escapeHtml(post.published_at || "")}" title="${escapeHtml(post.published_at || "")}">${escapeHtml(fmtPublished(post.published_at))}</time>
        </div>
      </div>
      ${!titleDup && title ? `<div class="p-title">${escapeHtml(title)}</div>` : ""}
      <div class="p-content md-body">${mdToHtml(shown)}${body.length > 200
        ? `<button type="button" class="post-expand-btn" onclick="newsRtExpand(${post.id})" aria-expanded="${expanded}">${expanded ? "收起 ▲" : "展开全文 ▼"}</button>`
        : ""}</div>
      ${images.length ? `
        <div class="post-images">
          ${images.slice(0, 4).map((img) => `
            <a class="post-img-link" href="#" onclick="event.preventDefault();openLightbox(this.querySelector('img'))" aria-label="查看${escapeHtml(post.kol_name || "")}的配图"><img src="${escapeHtml(imgSrcFor(img))}" loading="lazy" alt="${escapeHtml(post.kol_name || "")} 的配图" onerror="imgOnError(this)"></a>`).join("")}
          ${images.length > 4 ? `<span class="post-images-more">+${images.length - 4}</span>` : ""}
        </div>` : ""}
      <div class="p-meta">
        ${post.category_name ? `<span class="cat">${escapeHtml(post.category_name)}</span>` : ""}
        ${tags.slice(0, 6).map((t) => `<span class="cat cat-tag">${escapeHtml(t)}</span>`).join("")}
        ${safeUrl ? `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer nofollow">查看原文 →</a>` : ""}
      </div>
    </article>`;
  }

  async function loadRealtimeNews(reset = false, seq = currentRouteSeq()) {
    const list = $("#news-rt-list");
    if (!list || !routeStillActive(seq)) return;
    const requestSeq = ++state.newsRtSeq;
    if (reset) {
      stopNewsRtAutoLoad();
      state.newsRtItems = [];
      state.newsRtOffset = 0;
      list.innerHTML = newsRtSkeletonHtml();
    }
    const params = new URLSearchParams({ limit: "30", offset: String(state.newsRtOffset) });
    try {
      const data = await api(`/api/news/realtime?${params}`);
      if (!routeStillActive(seq) || requestSeq !== state.newsRtSeq) return;
      const items = data.items || [];
      // 追加时按 id 去重：轮询预置新帖后 offset 窗口可能压到边界行
      const have = new Set(state.newsRtItems.map((p) => p.id));
      const fresh = reset ? items : items.filter((p) => !have.has(p.id));
      state.newsRtItems = reset ? items : state.newsRtItems.concat(fresh);
      state.newsRtOffset = data.next_offset || state.newsRtItems.length;
      state.newsRtHasMore = !!data.has_more;
      if (reset) {
        list.innerHTML = state.newsRtItems.length
          ? state.newsRtItems.map(newsRtItemHtml).join("")
          : emptyState(
            data.selected_count ? "勾选的大V暂时没有动态，稍后再来看看" : "管理员还没有勾选参与实时资讯的大V",
            state.user?.is_admin && !data.selected_count
              ? '<div><button type="button" class="btn-normal" onclick="go(\'admin/content?tab=kols\')">去内容管理勾选</button></div>'
              : "",
          );
        state.newsRtLatestId = state.newsRtItems.reduce((max, p) => Math.max(max, Number(p.id) || 0), 0);
      } else if (fresh.length) {
        list.insertAdjacentHTML("beforeend", fresh.map(newsRtItemHtml).join(""));
      }
      startNewsRtAutoLoad(seq);
    } catch (err) {
      if (!routeStillActive(seq) || requestSeq !== state.newsRtSeq) return;
      list.innerHTML = emptyState("加载失败: " + err.message, `<div><button type="button" class="btn-ghost" onclick="loadRealtimeNews(${reset})">重试</button></div>`);
    }
  }

  function startNewsRtAutoLoad(seq) {
    stopNewsRtAutoLoad();
    const sentinel = $("#news-rt-load-sentinel");
    if (!sentinel || !state.newsRtHasMore) return;
    if ("IntersectionObserver" in window) {
      state.newsRtObserver = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadRealtimeNews(false, seq);
      }, { rootMargin: "400px 0px" });
      state.newsRtObserver.observe(sentinel);
    }
  }

  function startNewsRtPoll(seq) {
    stopNewsRtPoll();
    rtPollTimer = setInterval(() => pollNewsRtUpdates(seq), 60000);
  }

  // 增量轮询：新帖直接置顶插入（消息流场景，不用动态页的「点击查看」胶囊）
  async function pollNewsRtUpdates(seq) {
    if (document.visibilityState === "hidden") return;
    const list = $("#news-rt-list");
    if (!list || !state.newsRtLatestId) return;
    try {
      const data = await api(`/api/news/realtime?limit=30&since_id=${state.newsRtLatestId}`);
      if (!routeStillActive(seq) || !$("#news-rt-list")) return;
      const incoming = (data.items || []).filter((p) => !state.newsRtItems.some((q) => q.id === p.id));
      if (!incoming.length) return;
      state.newsRtLatestId = incoming.reduce((max, p) => Math.max(max, Number(p.id) || 0), state.newsRtLatestId);
      state.newsRtItems = [...incoming, ...state.newsRtItems];
      // 新帖插到顶部后，已加载行的分页窗口整体后移
      state.newsRtOffset += incoming.length;
      list.insertAdjacentHTML("afterbegin", incoming.map(newsRtItemHtml).join(""));
    } catch { /* 轮询失败静默，下一轮重试 */ }
  }

  function newsRtExpand(postId) {
    const id = Number(postId);
    if (state.newsRtExpanded.has(id)) state.newsRtExpanded.delete(id);
    else state.newsRtExpanded.add(id);
    const post = state.newsRtItems.find((p) => p.id === id);
    const card = document.querySelector(`.news-rt-item[data-post-id="${id}"]`);
    if (post && card) card.outerHTML = newsRtItemHtml(post);
  }

  // ---------- 财经新闻：现有媒体长文栏目 ----------

  function newsListItemHtml(item) {
    const thumbnail = item.has_image
      ? `<img class="news-list-thumb" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 64'%3E%3C/svg%3E" data-news-thumbnail="${item.id}" alt="" loading="lazy" onerror="this.style.display='none'">`
      : "";
    return `<article class="news-list-item" data-news-id="${item.id}" tabindex="0" role="link" onclick="openNewsArticle(${item.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openNewsArticle(${item.id})}">
      ${thumbnail}<div class="news-list-copy"><div class="news-list-meta"><span>${escapeHtml(item.source_name || "")}</span><time datetime="${escapeHtml(item.published_at || "")}">${escapeHtml(fmtPublished(item.published_at, true))}</time>${item.is_new ? '<span class="news-new-label">新</span>' : ""}</div>
      <h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary || "暂无摘要")}</p></div>
    </article>`;
  }

  function newsSourceFilterOptions() {
    const selected = new Set(state.newsSources.filter((source) => source.selected).map((source) => String(source.id)));
    return `<option value="">全部来源</option>${state.newsSources.filter((source) => selected.has(String(source.id))).map((source) => `<option value="${source.id}" ${String(state.newsFilterSourceId) === String(source.id) ? "selected" : ""}>${escapeHtml(source.name)}</option>`).join("")}`;
  }

  function newsListSkeletonHtml() {
    const card = '<div class="admin-sk-card"><div class="admin-sk-line admin-sk-head"></div><div class="admin-sk-line"></div></div>';
    return `<div class="admin-skeleton" aria-hidden="true">${card.repeat(3)}</div>`;
  }

  function renderFinancialNewsShell(collectionEnabled = true) {
    renderNewsShell(
      "articles",
      `${collectionEnabled ? "" : '<div class="notice notice-warn">管理员已暂停财经新闻采集，历史文章仍可阅读。</div>'}
      <div class="news-list-toolbar"><select id="news-source-filter" class="form-control" aria-label="新闻来源" onchange="selectNewsSource(this.value)">${newsSourceFilterOptions()}</select><div class="search-bar"><input id="news-query" type="search" placeholder="搜索标题或摘要" value="${escapeHtml(state.newsQuery)}" oninput="queueNewsSearch(this.value)"></div></div>
      <div id="news-list" class="news-list">${newsListSkeletonHtml()}</div>
      <div id="news-load-sentinel" class="news-load-sentinel" role="status" aria-live="polite"></div>`,
      '<button type="button" class="btn-normal" onclick="openNewsSourcePicker()">我的来源</button>',
    );
  }

  async function renderFinancialNewsList(seq = currentRouteSeq()) {
    setPageTitle("财经资讯");
    clearNewsImageUrls();
    state.newsItems = [];
    state.newsOffset = 0;
    state.newsHasMore = false;
    renderFinancialNewsShell(true);
    try {
      const sources = await api("/api/news/sources");
      if (!routeStillActive(seq)) return;
      state.newsSources = sources.items || [];
      if (state.newsFilterSourceId && !state.newsSources.some((source) => source.selected && String(source.id) === String(state.newsFilterSourceId))) state.newsFilterSourceId = "";
      renderFinancialNewsShell(sources.collection_enabled !== false);
      await loadFinancialNews(true, seq);
    } catch (err) {
      if (!routeStillActive(seq)) return;
      const list = $("#news-list");
      if (list) list.innerHTML = emptyState("加载失败: " + err.message, `<div><button type="button" class="btn-ghost" onclick="renderFinancialNewsList()">重试</button></div>`);
    }
  }

  async function loadFinancialNews(reset = false, seq = currentRouteSeq()) {
    const list = $("#news-list");
    if (!list || !routeStillActive(seq)) return;
    const requestSeq = ++state.newsRequestSeq;
    if (reset) {
      stopNewsAutoLoad();
      stopNewsThumbLoad();
      abortNewsImageRequests();
      state.newsItems = [];
      state.newsOffset = 0;
      list.innerHTML = newsListSkeletonHtml();
    }
    const params = new URLSearchParams({ limit: "30", offset: String(state.newsOffset) });
    if (state.newsFilterSourceId) params.set("source_id", state.newsFilterSourceId);
    if (state.newsQuery.trim()) params.set("q", state.newsQuery.trim());
    try {
      const data = await api(`/api/news?${params}`);
      if (!routeStillActive(seq) || requestSeq !== state.newsRequestSeq) return;
      const items = data.items || [];
      state.newsItems = reset ? items : state.newsItems.concat(items);
      state.newsOffset = data.next_offset || state.newsItems.length;
      state.newsHasMore = !!data.has_more;
      if (reset) {
        list.innerHTML = state.newsItems.length ? items.map(newsListItemHtml).join("") : emptyState(state.newsSources.some((source) => source.selected) ? "没有符合条件的财经新闻" : "还没有选择新闻来源", `<div><button type="button" class="btn-normal" onclick="openNewsSourcePicker()">选择来源</button></div>`);
      } else if (items.length) {
        list.insertAdjacentHTML("beforeend", items.map(newsListItemHtml).join(""));
      }
      observeNewsLazyImages();
      if (state.newsItems.length) {
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
    try {
      const blob = await apiBlob(`/api/news/${articleId}/images/${index}`, { signal: state.newsImageAbort?.signal });
      if (!routeStillActive(seq) || !image || !document.body.contains(image)) return;
      const url = URL.createObjectURL(blob);
      state.newsImageUrls.add(url);
      image.src = url;
    } catch (err) {
      if (err?.name === "AbortError") return;
      if (routeStillActive(seq) && image && document.body.contains(image)) image.remove();
    }
  }

  async function renderFinancialNewsArticle(articleId, seq = currentRouteSeq()) {
    setPageTitle("财经资讯", true, "news", "返回财经资讯");
    state.newsArticleId = articleId;
    const main = $("#main");
    if (!main) return;
    main.innerHTML = `<article class="news-article-page"><div class="admin-skeleton" aria-hidden="true"></div></article>`;
    try {
      const article = await api(`/api/news/${articleId}`);
      if (!routeStillActive(seq)) return;
      main.innerHTML = `<article class="news-article-page"><header class="news-article-head"><div class="news-article-meta"><span>${escapeHtml(article.source_name || "")}</span><time datetime="${escapeHtml(article.published_at || "")}">${escapeHtml(fmtPublished(article.published_at, false))}</time></div><h1>${escapeHtml(article.title)}</h1>${article.author ? `<p class="section-meta">作者：${escapeHtml(article.author)}</p>` : ""}<a class="btn-ghost news-original-link" href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer nofollow">打开原文 ${externalLinkIcon}</a></header><div class="news-article-body">${article.content_html || `<p>${escapeHtml(article.summary || "暂无正文")}</p>`}</div></article>`;
      observeNewsLazyImages();
    } catch (err) {
      if (routeStillActive(seq)) main.innerHTML = emptyState("加载失败: " + err.message, `<div><button type="button" class="btn-ghost" onclick="renderFinancialNewsArticle(${articleId})">重试</button></div>`);
    }
  }

  function openNewsArticle(articleId) {
    const id = Number(articleId);
    if (Number.isInteger(id) && id > 0) go(`news/${id}`);
  }

  function newsSourcePickerRows(filter = "", selectedIds = null) {
    const q = filter.trim().toLowerCase();
    return state.newsSources.filter((source) => !q || source.name.toLowerCase().includes(q)).map((source) => `<label class="news-source-option"><input type="checkbox" value="${source.id}" ${(selectedIds ? selectedIds.has(Number(source.id)) : source.selected) ? "checked" : ""}><span>${escapeHtml(source.name)}</span>${source.enabled ? "" : '<em>管理员已暂停更新</em>'}</label>`).join("") || '<p class="muted">没有匹配的媒体</p>';
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
      flash("新闻来源已保存");
      await renderFinancialNewsList(seq);
    } catch (err) {
      flash(err.message, "error");
      if (button) button.disabled = false;
    }
  }

  function selectNewsSource(sourceId) {
    state.newsFilterSourceId = sourceId;
    return loadFinancialNews(true, currentRouteSeq());
  }

  function queueNewsSearch(query) {
    state.newsQuery = query;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadFinancialNews(true, currentRouteSeq()), 250);
  }

  return {
    clearNewsReaderState,
    loadFinancialNews,
    loadRealtimeNews,
    newsRtExpand,
    openNewsArticle,
    openNewsSourcePicker,
    queueNewsSearch,
    renderFinancialNewsArticle,
    renderFinancialNewsList,
    renderNewsCenter,
    saveNewsSources,
    selectNewsSource,
    selectNewsTab,
  };
}
