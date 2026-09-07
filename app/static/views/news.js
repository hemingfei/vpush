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
    upArrowIcon,
    PLATFORM_LABELS,
    PLATFORM_ICONS,
  } = dependencies;
  let searchTimer = null;
  let rtPollTimer = null;
  let rtScrollRaf = 0;
  let rtScrollBound = false;

  // 实时资讯时间：当天只显示时钟，非当天才带日期（fmtPublished 当天返回「今天 HH:MM:SS」）
  function fmtRtTime(s) {
    const full = fmtPublished(s);
    return full.startsWith("今天") ? fmtPublished(s, true) : full;
  }

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
    state.newsRtPending = [];
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
      ? "盘中实时突发消息，自动更新，不错过每一条动态。"
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
    state.newsRtQuery = "";
    renderNewsShell(
      "realtime",
      `<div class="news-list-toolbar"><div class="search-bar"><input id="news-rt-query" type="search" placeholder="搜索内容或大V" value="${escapeHtml(state.newsRtQuery || "")}" oninput="queueNewsRtSearch(this.value)"></div></div><div id="news-rt-list" class="news-list news-rt-list">${newsRtSkeletonHtml()}</div><div id="news-rt-load-sentinel" class="news-load-sentinel" role="status" aria-live="polite"></div>
      <button type="button" id="news-rt-backtop" class="tl-backtop" aria-label="返回顶部" title="返回顶部" onclick="newsRtBacktopClick()">${upArrowIcon}<span class="tl-backtop-new" id="news-rt-backtop-new" hidden></span></button>`,
    );
    state.newsRtItems = [];
    state.newsRtOffset = 0;
    state.newsRtHasMore = false;
    state.newsRtLatestId = 0;
    state.newsRtPending = [];
    await loadRealtimeNews(true, seq);
    startNewsRtPoll(seq);
    ensureNewsRtScrollChrome();
    newsRtSyncBacktop();
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
        <div class="p-name-line">
          <time class="p-time" datetime="${escapeHtml(post.published_at || "")}" title="${escapeHtml(post.published_at || "")}">${escapeHtml(fmtRtTime(post.published_at))}</time>
          <a class="p-name" href="/kol/${post.kol_id}" title="${escapeHtml(post.kol_name || "")}">${escapeHtml(post.kol_name || "")}</a>
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
    if ((state.newsRtQuery || "").trim()) params.set("q", state.newsRtQuery.trim());
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
            (state.newsRtQuery || "").trim()
              ? "没有符合条件的内容"
              : data.selected_count ? "勾选的大V暂时没有动态，稍后再来看看" : "管理员还没有勾选参与实时资讯的大V",
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

  // 增量轮询：新帖不自动插到顶部（不打断阅读位置），先攒进待读缓冲，
  // 由返回顶部按钮的角标提示；用户本来就在顶部时直接合并显示，
  // 点击按钮或自己滚回顶部时也一次性合并
  async function pollNewsRtUpdates(seq) {
    if (document.visibilityState === "hidden") return;
    const list = $("#news-rt-list");
    if (!list || !state.newsRtLatestId) return;
    try {
      const q = (state.newsRtQuery || "").trim();
      const data = await api(`/api/news/realtime?limit=30&since_id=${state.newsRtLatestId}${q ? `&q=${encodeURIComponent(q)}` : ""}`);
      if (!routeStillActive(seq) || !$("#news-rt-list")) return;
      const incoming = (data.items || []).filter((p) => !state.newsRtItems.some((q) => q.id === p.id)
        && !state.newsRtPending.some((q) => q.id === p.id));
      if (!incoming.length) return;
      state.newsRtLatestId = incoming.reduce((max, p) => Math.max(max, Number(p.id) || 0), state.newsRtLatestId);
      state.newsRtPending = [...incoming, ...state.newsRtPending];
      if (window.scrollY <= 80) newsRtMergePending();
      else newsRtSyncBacktop();
    } catch { /* 轮询失败静默，下一轮重试 */ }
  }

  // 返回顶部按钮：滚动较深时常显；有待读新帖时即使没滚也弹出并带条数角标
  function ensureNewsRtScrollChrome() {
    if (rtScrollBound) return;
    rtScrollBound = true;
    window.addEventListener("scroll", () => {
      if (rtScrollRaf) return;
      rtScrollRaf = requestAnimationFrame(() => { rtScrollRaf = 0; newsRtSyncBacktop(); });
    }, { passive: true });
  }

  function newsRtSyncBacktop() {
    const btn = $("#news-rt-backtop");
    if (!btn) return;
    const n = state.newsRtPending.length;
    // 用户自己滚回顶部：待读新帖直接合并显示，不用再点一下
    if (n && window.scrollY <= 80) {
      newsRtMergePending();
      return;
    }
    btn.classList.toggle("show", window.scrollY > 600 || n > 0);
    btn.classList.toggle("has-new", n > 0);
    const tip = $("#news-rt-backtop-new");
    if (tip) {
      tip.hidden = !n;
      tip.textContent = n > 99 ? "99+" : String(n);
    }
  }

  // 把待读新帖一次性合并进列表顶部（快讯流按 id 降序整批置顶，与原轮询置顶行为一致）
  function newsRtMergePending() {
    const pending = state.newsRtPending;
    if (!pending.length) return;
    state.newsRtPending = [];
    const have = new Set(state.newsRtItems.map((p) => p.id));
    const incoming = pending.filter((p) => !have.has(p.id));
    if (incoming.length) {
      incoming.sort((a, b) => (Number(b.id) || 0) - (Number(a.id) || 0));
      state.newsRtItems = [...incoming, ...state.newsRtItems];
      // 新帖插到顶部后，已加载行的分页窗口整体后移
      state.newsRtOffset += incoming.length;
      const list = $("#news-rt-list");
      if (list) list.insertAdjacentHTML("afterbegin", incoming.map(newsRtItemHtml).join(""));
    }
    newsRtSyncBacktop();
  }

  function newsRtBacktopClick() {
    newsRtMergePending();
    window.scrollTo({ top: 0, behavior: "smooth" });
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
    return `<option value="">全部来源</option>${state.newsSources.map((source) => `<option value="${source.id}" ${String(state.newsFilterSourceId) === String(source.id) ? "selected" : ""}>${escapeHtml(source.name)}${source.enabled ? "" : "（已暂停）"}</option>`).join("")}`;
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
      "",
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
      if (state.newsFilterSourceId && !state.newsSources.some((source) => String(source.id) === String(state.newsFilterSourceId))) state.newsFilterSourceId = "";
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
        list.innerHTML = state.newsItems.length ? items.map(newsListItemHtml).join("") : emptyState("暂无符合条件的财经新闻");
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

  function selectNewsSource(sourceId) {
    state.newsFilterSourceId = sourceId;
    return loadFinancialNews(true, currentRouteSeq());
  }

  function queueNewsSearch(query) {
    state.newsQuery = query;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadFinancialNews(true, currentRouteSeq()), 250);
  }

  function queueNewsRtSearch(query) {
    state.newsRtQuery = query;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadRealtimeNews(true, currentRouteSeq()), 250);
  }

  return {
    clearNewsReaderState,
    loadFinancialNews,
    loadRealtimeNews,
    queueNewsRtSearch,
    newsRtBacktopClick,
    newsRtExpand,
    openNewsArticle,
    queueNewsSearch,
    renderFinancialNewsArticle,
    renderFinancialNewsList,
    renderNewsCenter,
    selectNewsSource,
    selectNewsTab,
  };
}
