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
    lockBodyScroll,
    unlockBodyScroll,
    fmtPublished,
    externalLinkIcon,
    avatarHtml,
    avatarText,
    mdToHtml,
    imgSrcFor,
    playNotificationSound,
    mxDisplayBody,
    mxAttachmentCards,
    upArrowIcon,
    PLATFORM_LABELS,
    PLATFORM_ICONS,
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
  let searchTimer = null; // 财经新闻/实时/调研共用的搜索去抖定时器（同一时刻只有一个栏目可见）
  let readAllUndoTimer = null;
  let readAllUndoPayload = null;

  // 实时资讯时间：当天只显示时钟，非当天才带日期（fmtPublished 当天返回「今天 HH:MM:SS」）
  function fmtRtTime(s) {
    const full = fmtPublished(s);
    return full.startsWith("今天") ? fmtPublished(s, true) : full;
  }

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

  function stopNewsThumbLoad() {
    state.newsThumbObserver?.disconnect();
    state.newsThumbObserver = null;
  }

  // 实时资讯/调研纪要的 stop* 与具名入口统一放在 createStreamFeed 双实例之后

  function abortNewsImageRequests() {
    state.newsImageAbort?.abort();
    state.newsImageAbort = new AbortController();
  }

  function clearNewsReaderState() {
    closeNewsArticleModal();
    stopNewsAutoLoad();
    stopNewsThumbLoad();
    stopNewsRtAutoLoad();
    stopNewsRtPoll();
    stopNewsResearchAutoLoad();
    stopNewsResearchPoll();
    abortNewsImageRequests();
    clearTimeout(searchTimer);
    clearNewsReadUndo();
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
    state.newsRtSources = [];
    state.newsRtSourceId = "";
    state.newsResearchItems = [];
    state.newsResearchOffset = 0;
    state.newsResearchHasMore = false;
    state.newsResearchLatestId = 0;
    state.newsResearchPending = [];
    state.newsResearchSeq += 1;
    state.newsResearchSources = [];
    state.newsResearchSourceId = "";
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

  // ---------- 页面骨架：财经资讯 = 实时资讯 + 调研纪要 + 财经新闻 三栏目 ----------

  function newsTabsHtml(active) {
    const tab = (id, label) => `<button type="button" class="news-tab${active === id ? " active" : ""}" role="tab" aria-selected="${active === id}" onclick="selectNewsTab('${id}')">${label}</button>`;
    return `<div class="news-tabs" role="tablist" aria-label="财经资讯栏目">${tab("realtime", "实时资讯")}${tab("research", "调研纪要")}${tab("articles", "财经新闻")}</div>`;
  }

  function renderNewsShell(active, panelHtml, headActionsHtml = "") {
    const main = $("#main");
    if (!main) return;
    const meta = active === "realtime"
      ? "盘中实时突发消息，自动更新，不错过每一条动态。"
      : active === "research"
        ? "大V调研纪要与产业动态，自动更新，不错过每一条动态。"
        : "按媒体聚合的长文阅读，原文链接保留。";
    main.innerHTML = `<section class="news-page" id="news-page">
      <header class="news-page-head"><div><h2 class="section-title">财经资讯</h2><p class="section-meta">${meta}</p></div>${headActionsHtml}</header>
      ${newsTabsHtml(active)}
      ${panelHtml}
    </section>`;
  }

  function renderNewsCenter(seq, articleId = "") {
    stopNewsAutoLoad();
    stopNewsThumbLoad();
    stopNewsRtAutoLoad();
    stopNewsRtPoll();
    stopNewsResearchAutoLoad();
    stopNewsResearchPoll();
    abortNewsImageRequests();
    if (!routeStillActive(seq)) return;
    state.newsTab = "realtime"; // 每次进入页面默认显示实时资讯
    const render = renderRealtimeNews(seq);
    // 深链 /news/<id>：列表先渲染，文章统一走弹窗（与点击卡片同口径）
    const id = Number(articleId);
    if (Number.isInteger(id) && id > 0) openNewsArticleModal(id);
    return render;
  }

  function selectNewsTab(tab) {
    const next = tab === "articles" ? "articles" : tab === "research" ? "research" : "realtime";
    if (next === state.newsTab) return;
    state.newsTab = next;
    closeNewsArticleModal();
    stopNewsRtPoll();
    stopNewsRtAutoLoad();
    stopNewsResearchPoll();
    stopNewsResearchAutoLoad();
    const seq = currentRouteSeq();
    window.scrollTo(0, 0);
    if (next === "realtime") return renderRealtimeNews(seq);
    if (next === "research") return renderResearchNews(seq);
    return renderFinancialNewsList(seq);
  }

  // ---------- 大V动态流（实时资讯/调研纪要）：参数化工厂双实例 ----------
  //
  // 两栏目仅 5 类差异：API 路径、DOM id/类名、state 键、全局 handler 名、空态文案；
  // 其余（增量轮询、待读胶囊、返回顶部、展开收起、来源筛选、搜索去抖）完全一致，
  // 统一在 createStreamFeed 里维护，避免改一处漏一处的双份镜像。

  function createStreamFeed(cfg) {
    const S = (key) => state[cfg.keys[key]];
    let pollTimer = null;
    let scrollRaf = 0;
    let scrollBound = false;
    let visibilityBound = false;

    function skeletonHtml() {
      const card = '<div class="admin-sk-card"><div class="admin-sk-line admin-sk-head"></div><div class="admin-sk-line"></div></div>';
      return `<div class="admin-skeleton" aria-hidden="true">${card.repeat(4)}</div>`;
    }

    function sourceFilterOptions() {
      return `<option value="">全部来源</option>${S("sources").map((source) => `<option value="${source.id}" ${String(S("sourceId")) === String(source.id) ? "selected" : ""}>${escapeHtml(source.name)}</option>`).join("")}`;
    }

    function itemHtml(post) {
      const images = (Array.isArray(post.images) ? post.images : []).filter(Boolean);
      const body = mxDisplayBody(post) || "（无正文）";
      const expanded = S("expanded").has(post.id);
      const shown = expanded ? body : body.slice(0, 200);
      const title = (post.title || "").trim();
      // X 帖常 title==content 或正文以标题开头，重复渲染只会有视觉噪音
      const titleDup = !!title && (title === body || body.startsWith(title));
      const safeUrl = /^https?:\/\//i.test(post.url || "") ? post.url : "";
      const tags = Array.isArray(post.tags) ? post.tags : [];
      return `<article class="${cfg.itemClass} post-item" data-post-id="${post.id}">
      <div class="p-header">
        <div class="p-name-line">
          <time class="p-time" datetime="${escapeHtml(post.published_at || "")}" title="${escapeHtml(post.published_at || "")}">${escapeHtml(fmtRtTime(post.published_at))}</time>
          <a class="p-name" href="/kol/${post.kol_id}" title="${escapeHtml(post.kol_name || "")}">${escapeHtml(post.kol_name || "")}</a>
        </div>
      </div>
      ${!titleDup && title ? `<div class="p-title">${escapeHtml(title)}</div>` : ""}
      <div class="p-content md-body">${mdToHtml(shown)}${body.length > 200
        ? `<button type="button" class="post-expand-btn" onclick="${cfg.globals.expand}(${post.id})" aria-expanded="${expanded}">${expanded ? "收起 ▲" : "展开全文 ▼"}</button>`
        : ""}</div>
      ${images.length ? `
        <div class="post-images">
          ${images.slice(0, 4).map((img) => `
            <a class="post-img-link" href="#" onclick="event.preventDefault();openLightbox(this.querySelector('img'))" aria-label="查看${escapeHtml(post.kol_name || "")}的配图"><img src="${escapeHtml(imgSrcFor(img))}" loading="lazy" alt="${escapeHtml(post.kol_name || "")} 的配图" onerror="imgOnError(this)"></a>`).join("")}
          ${images.length > 4 ? `<span class="post-images-more">+${images.length - 4}</span>` : ""}
        </div>` : ""}
      ${mxAttachmentCards(post)}
      <div class="p-meta">
        ${tags.slice(0, 6).map((t) => `<span class="cat cat-tag">${escapeHtml(t)}</span>`).join("")}
        ${safeUrl ? `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer nofollow">查看原文 →</a>` : ""}
      </div>
    </article>`;
    }

    function panelHtml() {
      return `<div class="news-list-toolbar"><select id="${cfg.filterId}" class="form-control" aria-label="资讯来源" onchange="${cfg.globals.source}(this.value)">${sourceFilterOptions()}</select><div class="search-bar"><input id="${cfg.queryId}" type="search" placeholder="搜索内容或大V" value="${escapeHtml(S("query") || "")}" oninput="${cfg.globals.search}(this.value)"></div></div><div id="${cfg.listId}" class="news-list ${cfg.listClass}">${skeletonHtml()}</div><div id="${cfg.sentinelId}" class="news-load-sentinel" role="status" aria-live="polite"></div>
      <div class="news-rt-new-badge" id="${cfg.badgeId}"><button type="button" class="news-rt-new-badge-btn" onclick="${cfg.globals.badge}()" aria-label="有新动态，点击查看">${upArrowIcon}<span class="news-rt-badge-avatars" id="${cfg.badgeAvatarsId}"></span><span class="news-rt-new-badge-label">有新动态</span></button></div>
      <button type="button" id="${cfg.backtopId}" class="tl-backtop" aria-label="返回顶部" title="返回顶部" onclick="${cfg.globals.backtop}()">${upArrowIcon}<span class="tl-backtop-new" id="${cfg.backtopNewId}" hidden></span></button>`;
    }

    async function render(seq = currentRouteSeq()) {
      setPageTitle("财经资讯");
      state[cfg.keys.query] = "";
      renderNewsShell(cfg.tab, panelHtml());
      state[cfg.keys.items] = [];
      state[cfg.keys.offset] = 0;
      state[cfg.keys.hasMore] = false;
      state[cfg.keys.latestId] = 0;
      state[cfg.keys.pending] = [];
      await load(true, seq);
      startPoll(seq);
      ensureScrollChrome();
      ensureVisibilityPoll();
      syncBacktop();
    }

    async function load(reset = false, seq = currentRouteSeq()) {
      const list = $(`#${cfg.listId}`);
      if (!list || !routeStillActive(seq)) return;
      const requestSeq = ++state[cfg.keys.seq];
      if (reset) {
        stopAutoLoad();
        state[cfg.keys.items] = [];
        state[cfg.keys.offset] = 0;
        // 勾选可能已被管理员改动：不在来源清单里的过滤值直接失效
        if (S("sourceId") && !S("sources").some((source) => String(source.id) === String(S("sourceId")))) state[cfg.keys.sourceId] = "";
        list.innerHTML = skeletonHtml();
      }
      const params = new URLSearchParams({ limit: "30", offset: String(S("offset")) });
      if (S("sourceId")) params.set("kol_id", S("sourceId"));
      if ((S("query") || "").trim()) params.set("q", S("query").trim());
      try {
        const data = await api(`${cfg.apiPath}?${params}`);
        if (!routeStillActive(seq) || requestSeq !== state[cfg.keys.seq]) return;
        const items = data.items || [];
        if (reset && Array.isArray(data.sources)) {
          state[cfg.keys.sources] = data.sources;
          const select = $(`#${cfg.filterId}`);
          if (select) select.innerHTML = sourceFilterOptions();
        }
        // 追加时按 id 去重：轮询预置新帖后 offset 窗口可能压到边界行
        const have = new Set(S("items").map((p) => p.id));
        const fresh = reset ? items : items.filter((p) => !have.has(p.id));
        state[cfg.keys.items] = reset ? items : S("items").concat(fresh);
        state[cfg.keys.offset] = data.next_offset || S("items").length;
        state[cfg.keys.hasMore] = !!data.has_more;
        if (reset) {
          list.innerHTML = S("items").length
            ? S("items").map(itemHtml).join("")
            : emptyState(
              (S("query") || "").trim()
                ? "没有符合条件的内容"
                : data.selected_count ? cfg.emptyNoItems : cfg.emptyNotSelected,
              state.user?.is_admin && !data.selected_count
                ? '<div><button type="button" class="btn-normal" onclick="go(\'admin/content?tab=kols\')">去内容管理勾选</button></div>'
                : "",
            );
          state[cfg.keys.latestId] = S("items").reduce((max, p) => Math.max(max, Number(p.id) || 0), 0);
        } else if (fresh.length) {
          list.insertAdjacentHTML("beforeend", fresh.map(itemHtml).join(""));
        }
        startAutoLoad(seq);
      } catch (err) {
        if (!routeStillActive(seq) || requestSeq !== state[cfg.keys.seq]) return;
        list.innerHTML = emptyState("加载失败: " + err.message, `<div><button type="button" class="btn-ghost" onclick="${cfg.globals.load}(${reset})">重试</button></div>`);
      }
    }

    function startAutoLoad(seq) {
      stopAutoLoad();
      const sentinel = $(`#${cfg.sentinelId}`);
      if (!sentinel || !S("hasMore")) return;
      if ("IntersectionObserver" in window) {
        state[cfg.keys.observer] = new IntersectionObserver((entries) => {
          if (entries.some((entry) => entry.isIntersecting)) load(false, seq);
        }, { rootMargin: "400px 0px" });
        state[cfg.keys.observer].observe(sentinel);
      }
    }

    function stopAutoLoad() {
      state[cfg.keys.observer]?.disconnect();
      state[cfg.keys.observer] = null;
    }

    function startPoll(seq) {
      stopPoll();
      pollTimer = setInterval(() => pollUpdates(seq), 60000);
    }

    function stopPoll() {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }

    // 增量轮询：新帖不自动插到顶部（不打断阅读位置），先攒进待读缓冲；
    // 用户在顶部时直接合并 + 提示音；用户在下方时弹胶囊 + 提示音，点击或滚回顶部再合并
    async function pollUpdates(seq) {
      if (document.visibilityState === "hidden") return;
      const list = $(`#${cfg.listId}`);
      if (!list || !S("latestId")) return;
      try {
        const q = (S("query") || "").trim();
        const src = S("sourceId") ? `&kol_id=${encodeURIComponent(S("sourceId"))}` : "";
        const data = await api(`${cfg.apiPath}?limit=30&since_id=${S("latestId")}${src}${q ? `&q=${encodeURIComponent(q)}` : ""}`);
        if (!routeStillActive(seq) || !$(`#${cfg.listId}`)) return;
        const seen = new Set([...S("items"), ...S("pending")].map((p) => p.id));
        const incoming = (data.items || []).filter((p) => !seen.has(p.id));
        if (!incoming.length) return;
        state[cfg.keys.latestId] = incoming.reduce((max, p) => Math.max(max, Number(p.id) || 0), S("latestId"));
        state[cfg.keys.pending] = [...incoming, ...S("pending")];
        if (window.scrollY <= 80) {
          playNotificationSound();
          mergePending();
        } else {
          playNotificationSound();
          showNewBadge();
          syncBacktop();
        }
      } catch { /* 轮询失败静默，下一轮重试 */ }
    }

    // 新帖胶囊：头像 + 条数 + 点击查看，挂在工具栏底部
    function showNewBadge() {
      const badge = $(`#${cfg.badgeId}`);
      if (!badge) return;
      const n = S("pending").length;
      const btn = badge.querySelector(".news-rt-new-badge-btn");
      if (btn) {
        const label = `${n} 条新动态，点击查看`;
        btn.title = label;
        btn.setAttribute("aria-label", label);
      }
      const labelEl = badge.querySelector(".news-rt-new-badge-label");
      if (labelEl) labelEl.textContent = `${n} 条新动态`;
      const avs = $(`#${cfg.badgeAvatarsId}`);
      if (avs) avs.innerHTML = badgeAvatarsHtml(S("pending"));
      badge.classList.add("show");
    }

    function hideNewBadge() {
      $(`#${cfg.badgeId}`)?.classList.remove("show");
    }

    // 胶囊头像：去重取前 3 个大V（无头像用首字色块）
    function badgeAvatarsHtml(posts, max = 3) {
      const seen = new Set();
      const avs = [];
      for (const p of posts) {
        const key = p.kol_id || p.kol_name;
        if (seen.has(key)) continue;
        seen.add(key);
        if (avs.length >= max) break;
        avs.push(p.avatar_url
          ? `<img src="${escapeHtml(p.avatar_url)}" alt="" data-av-name="${escapeHtml(p.kol_name)}" data-av-class="ph" onerror="avatarImgError(this)">`
          : `<span class="ph">${escapeHtml(avatarText(p.kol_name))}</span>`);
      }
      return avs.join("");
    }

    // 切回标签页时立即轮询一次，不用等下一个 60s 周期。
    // 不捕获 seq 闭包：listener 只绑一次，但每次切回本页 seq 会变，
    // 在调用时取最新 seq 才不会因 routeStillActive 判定过期而整段丢弃。
    // 离开本页后目标 DOM 消失，listener 自摘除（下次 render 再绑），不常驻堆积
    function ensureVisibilityPoll() {
      if (visibilityBound) return;
      visibilityBound = true;
      const onVisibility = () => {
        if (document.visibilityState !== "visible") return;
        if (!document.getElementById(cfg.listId)) {
          document.removeEventListener("visibilitychange", onVisibility);
          visibilityBound = false;
          return;
        }
        pollUpdates(currentRouteSeq());
      };
      document.addEventListener("visibilitychange", onVisibility);
    }

    // 返回顶部按钮：滚动较深时常显；有待读新帖时即使没滚也弹出并带条数角标。
    // 同上：离开本页 listener 自摘除，避免多栏目滚动监听常驻堆积
    function ensureScrollChrome() {
      if (scrollBound) return;
      scrollBound = true;
      const onScroll = () => {
        if (!document.getElementById(cfg.backtopId)) {
          window.removeEventListener("scroll", onScroll);
          scrollBound = false;
          return;
        }
        if (scrollRaf) return;
        scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; syncBacktop(); });
      };
      window.addEventListener("scroll", onScroll, { passive: true });
    }

    function syncBacktop() {
      const btn = $(`#${cfg.backtopId}`);
      if (!btn) return;
      const n = S("pending").length;
      // 用户自己滚回顶部：待读新帖直接合并显示，不用再点一下
      if (n && window.scrollY <= 80) {
        mergePending();
        return;
      }
      btn.classList.toggle("show", window.scrollY > 600 || n > 0);
      btn.classList.toggle("has-new", n > 0);
      const tip = $(`#${cfg.backtopNewId}`);
      if (tip) {
        tip.hidden = !n;
        tip.textContent = n > 99 ? "99+" : String(n);
      }
    }

    // 把待读新帖一次性合并进列表顶部（快讯流按 id 降序整批置顶，与原轮询置顶行为一致）
    function mergePending() {
      const pending = S("pending");
      if (!pending.length) return;
      state[cfg.keys.pending] = [];
      const have = new Set(S("items").map((p) => p.id));
      const incoming = pending.filter((p) => !have.has(p.id));
      if (incoming.length) {
        incoming.sort((a, b) => (Number(b.id) || 0) - (Number(a.id) || 0));
        state[cfg.keys.items] = [...incoming, ...S("items")];
        // 新帖插到顶部后，已加载行的分页窗口整体后移
        state[cfg.keys.offset] += incoming.length;
        const list = $(`#${cfg.listId}`);
        if (list) list.insertAdjacentHTML("afterbegin", incoming.map(itemHtml).join(""));
      }
      hideNewBadge();
      syncBacktop();
    }

    function backtopClick() {
      mergePending();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    function newBadgeClick() {
      backtopClick();
    }

    function expand(postId) {
      const id = Number(postId);
      if (S("expanded").has(id)) S("expanded").delete(id);
      else S("expanded").add(id);
      const post = S("items").find((p) => p.id === id);
      const card = document.querySelector(`.${cfg.itemClass}[data-post-id="${id}"]`);
      if (post && card) card.outerHTML = itemHtml(post);
    }

    function selectSource(sourceId) {
      state[cfg.keys.sourceId] = sourceId;
      return load(true, currentRouteSeq());
    }

    function queueSearch(query) {
      state[cfg.keys.query] = query;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => load(true, currentRouteSeq()), 250);
    }

    return {
      render, load, stopPoll, stopAutoLoad,
      selectSource, queueSearch, backtopClick, newBadgeClick, expand,
    };
  }

  const rtFeed = createStreamFeed({
    tab: "realtime",
    apiPath: "/api/news/realtime",
    listId: "news-rt-list",
    listClass: "news-rt-list",
    filterId: "news-rt-source-filter",
    queryId: "news-rt-query",
    sentinelId: "news-rt-load-sentinel",
    badgeId: "news-rt-new-badge",
    badgeAvatarsId: "news-rt-badge-avatars",
    backtopId: "news-rt-backtop",
    backtopNewId: "news-rt-backtop-new",
    itemClass: "news-rt-item",
    globals: {
      source: "selectNewsRtSource",
      search: "queueNewsRtSearch",
      expand: "newsRtExpand",
      badge: "newsRtNewBadgeClick",
      backtop: "newsRtBacktopClick",
      load: "loadRealtimeNews",
    },
    keys: {
      items: "newsRtItems", offset: "newsRtOffset", hasMore: "newsRtHasMore",
      latestId: "newsRtLatestId", pending: "newsRtPending", seq: "newsRtSeq",
      sources: "newsRtSources", sourceId: "newsRtSourceId", query: "newsRtQuery",
      expanded: "newsRtExpanded", observer: "newsRtObserver",
    },
    emptyNoItems: "勾选的大V暂时没有动态，稍后再来看看",
    emptyNotSelected: "管理员还没有勾选参与实时资讯的大V",
  });

  const researchFeed = createStreamFeed({
    tab: "research",
    apiPath: "/api/news/research",
    listId: "news-research-list",
    listClass: "news-research-list",
    filterId: "news-research-source-filter",
    queryId: "news-research-query",
    sentinelId: "news-research-load-sentinel",
    badgeId: "news-research-new-badge",
    badgeAvatarsId: "news-research-badge-avatars",
    backtopId: "news-research-backtop",
    backtopNewId: "news-research-backtop-new",
    itemClass: "news-research-item",
    globals: {
      source: "selectNewsResearchSource",
      search: "queueNewsResearchSearch",
      expand: "newsResearchExpand",
      badge: "newsResearchNewBadgeClick",
      backtop: "newsResearchBacktopClick",
      load: "loadResearchNews",
    },
    keys: {
      items: "newsResearchItems", offset: "newsResearchOffset", hasMore: "newsResearchHasMore",
      latestId: "newsResearchLatestId", pending: "newsResearchPending", seq: "newsResearchSeq",
      sources: "newsResearchSources", sourceId: "newsResearchSourceId", query: "newsResearchQuery",
      expanded: "newsResearchExpanded", observer: "newsResearchObserver",
    },
    emptyNoItems: "勾选的大V暂时没有调研纪要，稍后再来看看",
    emptyNotSelected: "管理员还没有勾选参与调研纪要的大V",
  });

  // 具名入口：内联 onclick 与 INLINE_HANDLERS 依赖这些全局名，保持不变
  async function renderRealtimeNews(seq = currentRouteSeq()) { return rtFeed.render(seq); }
  async function renderResearchNews(seq = currentRouteSeq()) { return researchFeed.render(seq); }
  async function loadRealtimeNews(reset = false, seq = currentRouteSeq()) { return rtFeed.load(reset, seq); }
  async function loadResearchNews(reset = false, seq = currentRouteSeq()) { return researchFeed.load(reset, seq); }
  function stopNewsRtPoll() { rtFeed.stopPoll(); }
  function stopNewsRtAutoLoad() { rtFeed.stopAutoLoad(); }
  function stopNewsResearchPoll() { researchFeed.stopPoll(); }
  function stopNewsResearchAutoLoad() { researchFeed.stopAutoLoad(); }
  function selectNewsRtSource(sourceId) { return rtFeed.selectSource(sourceId); }
  function selectNewsResearchSource(sourceId) { return researchFeed.selectSource(sourceId); }
  function queueNewsRtSearch(query) { rtFeed.queueSearch(query); }
  function queueNewsResearchSearch(query) { researchFeed.queueSearch(query); }
  function newsRtBacktopClick() { rtFeed.backtopClick(); }
  function newsRtNewBadgeClick() { rtFeed.newBadgeClick(); }
  function newsRtExpand(postId) { rtFeed.expand(postId); }
  function newsResearchBacktopClick() { researchFeed.backtopClick(); }
  function newsResearchNewBadgeClick() { researchFeed.newBadgeClick(); }
  function newsResearchExpand(postId) { researchFeed.expand(postId); }

  // ---------- 财经新闻：现有媒体长文栏目 ----------

  // 列表按日分组（今天/昨天/M/D），分组标签间插日分隔线
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
    const topics = Array.isArray(item.topics) && item.topics.length
      ? `<span class="news-item-topics">${item.topics.map((topic) => NEWS_TOPICS.includes(topic) ? `<button type="button" class="news-item-topic${topic === activeTopic ? " is-on" : ""}" aria-pressed="${topic === activeTopic ? "true" : "false"}" onclick="selectNewsTopic('${topic}')">${escapeHtml(topic)}</button>` : `<i>${escapeHtml(topic)}</i>`).join("")}</span>`
      : "";
    return `<article class="news-list-item ${unread ? "is-unread" : "is-read"}" data-news-id="${item.id}">
    <div class="news-list-copy">
      <a class="news-item-open" href="/news/${item.id}">
        <div class="news-item-title-row">${unread ? '<i class="news-item-unread-dot" aria-label="未读"></i>' : ""}<h3>${escapeHtml(item.title)}</h3></div>
        <p>${escapeHtml(item.summary || "暂无摘要")}</p>
      </a>
      <div class="news-list-meta"><span class="news-item-source">${escapeHtml(item.source_name || "")}</span><time datetime="${escapeHtml(item.published_at || "")}">${escapeHtml(fmtPublished(item.published_at, true))}</time>${topics}${unread ? `<button type="button" class="news-mark-read" onclick="markNewsItemRead(${item.id})" aria-label="标为已读">${CHECK_ICON}<span>标为已读</span></button>` : ""}</div>
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

  function newsEmptyHtml() {
    const query = (state.newsQuery || "").trim();
    if (state.newsUnreadOnly && !query && !state.newsTopic && !state.newsFilterSourceId) {
      return emptyState("没有未读文章，已经全部看完了");
    }
    if (query || state.newsTopic || state.newsFilterSourceId || state.newsUnreadOnly) {
      return emptyState("暂无相关财经资讯", `<div><button type="button" class="btn-ghost" onclick="clearNewsFilters()">清除筛选</button></div>`);
    }
    return emptyState("还没有财经新闻，采集开始后会自动出现");
  }

  function newsSourceFilterOptions() {
    return `<option value="">全部来源</option>${state.newsSources.map((source) => `<option value="${source.id}" ${String(state.newsFilterSourceId) === String(source.id) ? "selected" : ""}>${escapeHtml(source.name)}${source.enabled ? "" : "（已暂停）"}</option>`).join("")}`;
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
    document.querySelectorAll("#news-source-filter option").forEach((option) => {
      option.selected = selected ? option.value === selected : option.value === "";
    });
    const input = $("#news-query");
    if (input && input.value !== (state.newsQuery || "")) input.value = state.newsQuery || "";
  }

  // 吸收 main v1.12.259：筛选只刷新列表不再整页重绘，避免输入/滚动状态被打断
  function applyNewsListFilter() {
    state.newsListKey = newsListKey();
    syncNewsFilterChrome();
    return loadFinancialNews(true, currentRouteSeq());
  }

  function newsListSkeletonHtml() {
    const card = '<div class="admin-sk-card"><div class="news-sk-copy"><div class="admin-sk-line admin-sk-head"></div><div class="admin-sk-line"></div><div class="admin-sk-line"></div></div><div class="news-sk-thumb"></div></div>';
    return `<div class="admin-skeleton" aria-hidden="true">${card.repeat(3)}</div>`;
  }

  function renderFinancialNewsShell(collectionEnabled = true) {
    const unreadOn = !!state.newsUnreadOnly;
    const unreadCount = Number(state.newsUnreadCount) || 0;
  function renderFinancialNewsShell(collectionEnabled = true) {
    const unreadOn = !!state.newsUnreadOnly;
    const unreadCount = Number(state.newsUnreadCount) || 0;
    renderNewsShell(
      "articles",
      `${collectionEnabled ? "" : '<div class="notice notice-warn">管理员已暂停财经新闻采集，历史文章仍可阅读。</div>'}
      <div class="news-list-toolbar"><div class="news-toolbar-filters"><button type="button" class="news-unread-toggle ${unreadOn ? "is-on" : ""}" onclick="toggleNewsUnreadOnly()" aria-pressed="${unreadOn}">只看未读${unreadCount ? `<b>${unreadCount > 99 ? "99+" : unreadCount}</b>` : ""}</b></button><select id="news-source-filter" class="form-control" aria-label="新闻来源" onchange="selectNewsSource(this.value)">${newsSourceFilterOptions()}</select><div class="search-bar"><input id="news-query" type="search" placeholder="搜索标题或摘要" value="${escapeHtml(state.newsQuery)}" oninput="queueNewsSearch(this.value)"></div></div>${unreadCount ? `<button type="button" class="btn-ghost news-read-all" onclick="markAllNewsRead()" aria-label="全部已读">${CHECK_CHECK_ICON}<span>全部已读</span></button>` : ""}</div>
      <div id="news-list" class="news-list">${newsListSkeletonHtml()}</div>
      <div id="news-load-sentinel" class="news-load-sentinel" role="status" aria-live="polite"></div>
      <div id="news-read-undo" class="news-read-undo" role="status" aria-live="polite" hidden></div>`,
      "",
    );
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
    if (state.newsItems.length && state.newsListKey === newsListKey()) {
      clearNewsImageUrls();
      renderFinancialNewsShell(state.newsCollectionEnabled !== false);
      const list = $("#news-list");
      list.innerHTML = state.newsItems.length ? newsListHtml(state.newsItems) : newsEmptyHtml();
      observeNewsLazyImages();
      startNewsAutoLoad(seq);
      window.scrollTo(0, state.newsScrollY || 0);
      return;
    }
    state.newsItems = [];
    state.newsOffset = 0;
    state.newsHasMore = false;
    renderFinancialNewsShell(true);
    try {
      const sources = await api("/api/news/sources");
      if (!routeStillActive(seq)) return;
      state.newsSources = sources.items || [];
      state.newsUnreadCount = Number(sources.unread_count) || 0;
      syncUnreadBadge();
      if (state.newsFilterSourceId && !state.newsSources.some((source) => String(source.id) === String(state.newsFilterSourceId))) state.newsFilterSourceId = "";
      renderFinancialNewsShell(sources.collection_enabled !== false);
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
      // 吸收 main v1.12.259：筛选变化不清列表不清骨架，数据回来原地替换，避免整列表闪烁。
      // hmf 的懒加载/在途图片中断仍保留：reset 重查意味着旧缩略图可能不再出现在新结果里。
      stopNewsThumbLoad();
      abortNewsImageRequests();
      state.newsOffset = 0;
      if (!list.querySelector(".news-list-item, .empty-state")) list.innerHTML = newsListSkeletonHtml();
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
        list.innerHTML = state.newsItems.length ? newsListHtml(state.newsItems) : newsEmptyHtml();
      } else if (items.length) {
        list.insertAdjacentHTML("beforeend", newsListHtml(items, { append: true }));
      }
      observeNewsLazyImages();
      if (state.newsItems.length && !state.newsUnreadOnly) {
        const seenAt = data.view_started_at;
        await Promise.resolve();
        if (!routeStillActive(seq) || requestSeq !== state.newsRequestSeq) return;
        if (seenAt) api("/api/news/seen", { method: "POST", body: JSON.stringify({ view_started_at: seenAt }) }).catch(() => {});
      }
      const sentinel = $("#news-load-sentinel");
      if (sentinel) sentinel.innerHTML = "";
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
      const blob = await apiBlob(`/api/news/${articleId}/images/${index}`, { signal: state.newsImageAbort?.signal });
      if (!routeStillActive(seq) || !image || !document.body.contains(image)) return;
      const url = URL.createObjectURL(blob);
      state.newsImageUrls.set(newsImageUrlKey(articleId, index), url);
      image.src = url;
    } catch (err) {
      if (err?.name === "AbortError") return;
      if (routeStillActive(seq) && image && document.body.contains(image)) {
        const link = image.closest(".news-list-thumb-link");
        if (link) link.remove();
        else image.remove();
      }
    }
  }

  function closeNewsArticleModal(mask) {
    const existing = mask || document.querySelector(".news-article-modal");
    state.newsArticleId = 0;
    // 无弹窗时必须空操作:路由器每次切页都经 clearNewsReaderState 无条件调到这里,
    // 若无条件解锁会误解同一次点击里其他弹窗(如原始消息弹窗)刚加的滚动锁
    if (!existing) return;
    unlockBodyScroll();
    existing.remove();
  }

  async function openNewsArticleModal(articleId) {
    const id = Number(articleId);
    if (!Number.isInteger(id) || id <= 0) return;
    closeNewsArticleModal();
    lockBodyScroll(); // 锁背景滚动：内层滚到头后 touchmove/wheel 不再穿透到新闻列表
    const mask = document.createElement("div");
    mask.className = "modal-mask news-article-modal";
    mask.innerHTML = `<div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="news-article-modal-title">
      <button type="button" class="news-article-modal-close" data-close aria-label="关闭弹窗"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
      <div class="news-article-modal-content"><div class="admin-skeleton" aria-hidden="true"></div></div>
    </div>`;
    document.body.appendChild(mask);
    state.newsArticleId = id;
    const close = () => closeNewsArticleModal(mask);
    trapFocus(mask, close);
    mask.addEventListener("click", (event) => { if (event.target === mask) close(); });
    mask.querySelector("[data-close]").addEventListener("click", close);
    const content = mask.querySelector(".news-article-modal-content");
    try {
      const article = await api(`/api/news/${id}`);
      if (!document.body.contains(mask)) return;
      // 打开即视为已读：后台静默上报，列表角标/未读数同步刷新（失败不影响阅读）
      void api(`/api/news/${id}/read`, { method: "POST" }).then(() => {
        if (applyNewsItemRead(id)) {
          paintNewsItemRead(id);
          paintNewsUnreadChrome();
          syncUnreadBadge();
        }
      }).catch(() => {});
      const pager = (article.prev_id || article.next_id) ? `
        <div class="news-article-nav">
          ${article.prev_id ? `<button type="button" class="btn-ghost" onclick="openNewsArticle(${article.prev_id})">← 上一篇</button>` : "<span></span>"}
          ${article.next_id ? `<button type="button" class="btn-ghost" onclick="openNewsArticle(${article.next_id})">下一篇 →</button>` : "<span></span>"}
        </div>` : "";
      content.innerHTML = `<article class="news-article-page"><header class="news-article-head"><div class="news-article-meta"><span>${escapeHtml(article.source_name || "")}</span><time datetime="${escapeHtml(article.published_at || "")}">${escapeHtml(fmtPublished(article.published_at, false))}</time></div><h1 id="news-article-modal-title">${escapeHtml(article.title)}</h1>${article.author ? `<p class="section-meta">作者：${escapeHtml(article.author)}</p>` : ""}<div class="news-article-tools"><a class="btn-ghost news-original-link" href="${escapeHtml(article.url)}" target="_blank" rel="noopener noreferrer nofollow">打开原文 ${externalLinkIcon}</a><div class="news-font-switch" role="group" aria-label="正文字号">${[["small", "小"], ["", "标准"], ["large", "大"]].map(([value, label]) => `<button type="button" class="${((state.user && state.user.news_font_size) || "") === value ? "is-on" : ""}" onclick="setNewsFontSize('${value}')" aria-pressed="${((state.user && state.user.news_font_size) || "") === value}">${label}</button>`).join("")}</div></div></header><div class="news-article-body${newsFontSizeClass()}">${article.content_html || `<p>${escapeHtml(article.summary || "暂无正文")}</p>`}</div>${pager}</article>`;
      const modalContent = mask.querySelector(".news-article-modal-content");
      if (modalContent) modalContent.scrollTop = 0;
      observeNewsLazyImages();
    } catch (err) {
      if (!document.body.contains(mask)) return;
      content.innerHTML = emptyState("加载失败: " + err.message, `<div><button type="button" class="btn-ghost" onclick="openNewsArticle(${id})">重试</button></div>`);
    }
  }

  function newsFontSizeClass() {
    const size = (state.user && state.user.news_font_size) || "";
    return size === "small" ? " news-font-small" : size === "large" ? " news-font-large" : "";
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

  async function markNewsItemRead(articleId) {
    const seq = currentRouteSeq();
    const item = state.newsItems.find((entry) => Number(entry.id) === Number(articleId));
    const changed = item && !item.is_read;
    if (changed && $("#news-list")) {
      paintNewsItemRead(articleId);
      paintNewsUnreadChrome();
    }
    try {
      await api(`/api/news/${articleId}/read`, { method: "POST" });
      if (!routeStillActive(seq)) return;
      if (changed) applyNewsItemRead(articleId);
      syncUnreadBadge();
    } catch (err) {
      if (changed && routeStillActive(seq)) await renderFinancialNewsList(seq);
      flash(err.message, "error");
    }
  }

  function openNewsArticle(articleId) {
    const id = Number(articleId);
    if (Number.isInteger(id) && id > 0) openNewsArticleModal(id);
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
      renderFinancialNewsShell(state.newsCollectionEnabled !== false);
      $("#news-list").innerHTML = state.newsUnreadOnly ? newsEmptyHtml() : newsListHtml(state.newsItems);
      if (!state.newsUnreadOnly) {
        observeNewsLazyImages();
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

  function selectNewsSource(sourceId) {
    state.newsFilterSourceId = sourceId;
    return applyNewsListFilter();
  }

  function clearNewsFilters() {
    state.newsUnreadOnly = false;
    state.newsQuery = "";
    state.newsTopic = "";
    state.newsFilterSourceId = "";
    return applyNewsListFilter();
  }

  // 吸收 main：主题再点一次取消筛选（主题芯片在卡片上，无需单独主题条）
  function selectNewsTopic(topic) {
    const next = topic || "";
    state.newsTopic = state.newsTopic === next ? "" : next;
    return applyNewsListFilter();
  }

  function selectNewsRtSource(sourceId) {
    state.newsRtSourceId = sourceId;
    return loadRealtimeNews(true, currentRouteSeq());
  }

  function selectNewsResearchSource(sourceId) {
    state.newsResearchSourceId = sourceId;
    return loadResearchNews(true, currentRouteSeq());
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

  function queueNewsRtSearch(query) {
    state.newsRtQuery = query;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadRealtimeNews(true, currentRouteSeq()), 250);
  }

  function queueNewsResearchSearch(query) {
    state.newsResearchQuery = query;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadResearchNews(true, currentRouteSeq()), 250);
  }

  return {
    clearNewsReaderState,
    loadFinancialNews,
    loadRealtimeNews,
    loadResearchNews,
    markAllNewsRead,
    markNewsItemRead,
    queueNewsRtSearch,
    queueNewsResearchSearch,
    newsRtBacktopClick,
    newsRtExpand,
    newsRtNewBadgeClick,
    newsResearchBacktopClick,
    newsResearchExpand,
    newsResearchNewBadgeClick,
    openNewsArticle,
    openNewsArticleModal,
    queueNewsSearch,
    renderFinancialNewsList,
    renderNewsCenter,
    renderResearchNews,
    clearNewsFilters,
    selectNewsRtSource,
    selectNewsResearchSource,
    selectNewsSource,
    selectNewsTab,
    selectNewsTopic,
    setNewsFontSize,
    toggleNewsUnreadOnly,
    undoNewsReadAll,
  };
}
