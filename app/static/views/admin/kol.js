export function createAdminKolsView(dependencies) {
  const {
    $,
    state,
    api,
    flash,
    escapeHtml,
    routeStillActive,
    currentAdminSeq,
    emptyState,
    trapFocus,
    PLATFORM_LABELS,
    PLATFORM_TABS,
    platformTabHTML,
    routeQuery,
    fmtDbTime,
    fmtPublished,
    showConfirm,
    copyText,
  } = dependencies;

  let _adminKolsSeq = 0;
  const _adminKolsPageSize = 50;
  let _adminKolsSelected = new Set(); // 批量操作选中的大V id（跨页保留）

  async function loadAdminKols(opts) {
    opts = opts || {};
    const seq = ++_adminKolsSeq;
    let data, categories;
    try {
      const params = new URLSearchParams({
        limit: String(_adminKolsPageSize),
        offset: String((state.adminKolsPage || 0) * _adminKolsPageSize),
      });
      if (state.adminKolsPlatform) params.set("platform", state.adminKolsPlatform);
      if (state.adminKolsCategory) params.set("category_id", state.adminKolsCategory);
      if (state.adminKolsStatus !== "") params.set("status", state.adminKolsStatus);
      if (state.adminKolsQ) params.set("q", state.adminKolsQ);
      [data, categories] = await Promise.all([api(`/api/admin/kols?${params}`), api("/api/categories")]);
    } catch (err) {
      if (!routeStillActive(currentAdminSeq())) return;
      if (seq === _adminKolsSeq) $("#admin-body").innerHTML = emptyState("加载失败: " + err.message);
      return;
    }
    if (seq !== _adminKolsSeq) return; // 已切换筛选/翻页，丢弃过期响应
    const matchIds = new Set(data.ids || []);
    const focusIds = opts.focusIds || [];
    const visibleFocus = focusIds.filter((id) => matchIds.has(id));
    if (visibleFocus.length) {
      const idx = (data.ids || []).indexOf(visibleFocus[0]);
      const wantPage = Math.max(0, Math.floor(idx / _adminKolsPageSize));
      if (wantPage !== (state.adminKolsPage || 0)) {
        state.adminKolsPage = wantPage;
        return loadAdminKols({ focusIds: visibleFocus });
      }
    }
    const highlightIds = new Set(visibleFocus);
    const kols = data.items || [];
    state.adminKols = kols;
    state.adminKolsTotal = data.total || 0;
    for (const id of [..._adminKolsSelected]) {
      if (!matchIds.has(id)) _adminKolsSelected.delete(id);
    }
    const catOptions = categories.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("");
    const page = state.adminKolsPage || 0;
    const pages = Math.max(1, Math.ceil((data.total || 0) / _adminKolsPageSize));
    if (!routeStillActive(currentAdminSeq())) return;
    const selCount = _adminKolsSelected.size;
    const rows = kols.map((k) => {
      const tier = k.priority ? "优先" : k.secondary ? "次要" : "普通";
      const orig = k.platform === "weibo"
        ? (k.original_only ? '<span class="status-ok">是</span>' : "否")
        : "—";
      const kwList = k.block_keywords || [];
      const blockedCnt = Number(k.blocked_count) || 0;
      const kwCell = (kwList.length || blockedCnt)
        ? `<button type="button" class="btn-sm ak-kw-view${blockedCnt ? " status-warn" : ""}" title="${kwList.length ? escapeHtml(kwList.join("、")) : "未设置屏蔽词"}" onclick="adminViewKolBlock(${k.id})">${kwList.length ? `${kwList.length} 个词` : "无屏蔽词"}${blockedCnt ? ` · 拦 ${blockedCnt}` : ""}</button>`
        : '<span class="muted">—</span>';
      const tierSel = `<select class="form-control btn-sm ak-tier-select" aria-label="档位" onchange="adminSetTier(${k.id}, this.value)"><option value="normal" ${!k.priority && !k.secondary ? "selected" : ""}>普通档</option><option value="priority" ${k.priority ? "selected" : ""}>优先档</option><option value="secondary" ${k.secondary ? "selected" : ""}>次要档</option></select>`;
      return `
              <tr class="${highlightIds.has(k.id) ? "ak-row-flash" : ""}">
                <td class="ak-check"><input type="checkbox" class="kol-check" data-id="${k.id}" ${_adminKolsSelected.has(k.id) ? "checked" : ""} onchange="adminKolToggleSelect(this)" aria-label="选择 ${escapeHtml(k.name)}"></td>
                <td class="ak-hide-mobile" data-label="ID">${k.id}</td>
                <td data-label="平台">${PLATFORM_LABELS[k.platform] || k.platform}</td>
                <td data-label="昵称">${escapeHtml(k.name)}</td>
                <td data-label="分类">${escapeHtml(k.category_name || "")}</td>
                <td class="ak-hide-mobile" data-label="外部ID">${escapeHtml(k.external_id)}</td>
                <td data-label="档位">${tier}</td>
                <td class="ak-hide-mobile" data-label="原创">${orig}</td>
                <td data-label="可见性">${k.is_private ? '<span class="status-warn">私有</span>' : "公开"}</td>
                <td class="ak-hide-mobile" data-label="屏蔽词">${kwCell}</td>
                <td data-label="状态" class="${k.enabled ? "status-ok" : "status-fail"}">${k.enabled ? "启用" : "停用"}</td>
                <td class="ak-actions" data-label="操作">
                  ${tierSel}
                  ${k.platform === "system" ? `<button class="btn-sm" onclick="adminKolWebhook(${k.id})">Webhook</button>` : ""}
                  <button class="btn-sm" onclick="adminToggleKol(${k.id}, ${k.enabled ? 0 : 1})">${k.enabled ? "停用" : "启用"}</button>
                  <button class="btn-sm" onclick="adminEditKolKeywords(${k.id})">屏蔽词</button>
                  <button class="btn-sm" onclick="adminEditKol(${k.id})">编辑</button>
                  <button class="btn-sm danger" onclick="adminDeleteKol(${k.id})">删除</button>
                </td>
              </tr>`;
    }).join("");
    $("#admin-body").innerHTML = `
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">添加大V</h2>
          <p class="section-meta">每行一个：昵称 + 主页链接（昵称可省略）。平台由链接自动识别。</p></div>
        </header>
        <textarea id="ad-batch-lines" class="form-control ak-add-lines" rows="6" placeholder="https://xueqiu.com/u/12345&#10;段永平 https://xueqiu.com/u/12345&#10;https://weibo.com/u/1642591402&#10;https://x.com/elonmusk&#10;https://xueqiu.com/P/ZH123456" aria-label="大V主页链接，每行一个" oninput="adminBatchLinesHint()"></textarea>
        <div class="toolbar ak-add-bar">
          <label class="muted" for="ad-batch-system"><input type="checkbox" id="ad-batch-system" onchange="adminBatchSystemToggle()"> 系统 KOL（用于 AI 分析）</label>
          <select id="ad-batch-category" class="form-control" aria-label="分类"><option value="">未分类</option>${catOptions}</select>
          <button class="btn-normal" id="ad-batch-btn" onclick="adminBatchAddKols()">添加</button>
          <div id="ad-batch-result" class="muted ak-add-result"></div>
        </div>
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">大V列表</h2>
          <p class="section-meta" id="admin-kols-meta">共 ${state.adminKolsTotal} 个大V · 优先约 60 秒抓一次，次要走低频摘要</p></div>
          <div class="toolbar ak-filters">
            <input id="ak-q" class="form-control" style="width:200px" placeholder="昵称 / 外部ID" value="${escapeHtml(state.adminKolsQ || "")}" onkeydown="if(event.key==='Enter')adminKolsApplyFilter()">
            <select id="ak-category" class="form-control" style="width:auto" onchange="adminKolsApplyFilter()"><option value="">全部分类</option>${catOptions}</select>
            <select id="ak-status" class="form-control" style="width:auto" onchange="adminKolsApplyFilter()">
              <option value="">全部状态</option>
              <option value="1" ${state.adminKolsStatus === "1" ? "selected" : ""}>启用</option>
              <option value="0" ${state.adminKolsStatus === "0" ? "selected" : ""}>停用</option>
            </select>
            <button type="button" class="btn-ghost ak-search-btn" onclick="adminKolsApplyFilter()">搜索</button>
            <button type="button" class="btn-ghost ak-clear-btn" onclick="adminKolsClearFilter()">清除</button>
          </div>
          <div class="platform-tabs ak-platform-tabs" id="admin-kols-tabs"></div>
        </header>
        <div class="toolbar admin-batch-bar" id="ak-batch-bar" style="margin-top:10px;display:${selCount ? "flex" : "none"};align-items:center;gap:8px;flex-wrap:wrap">
          <strong>已选 ${selCount} 个</strong>
          <button class="btn-sm" onclick="adminKolBatch('enable')">批量启用</button>
          <button class="btn-sm" onclick="adminKolBatch('disable')">批量停用</button>
          <button class="btn-sm" onclick="adminKolBatch('priority', true)">批量设优先</button>
          <button class="btn-sm" onclick="adminKolBatch('secondary', true)">批量设次要</button>
          <button class="btn-sm" onclick="adminKolBatch('normal')">批量设普通</button>
          <select id="ak-batch-category" class="form-control" style="width:auto"><option value="">批量改分类…</option>${catOptions}<option value="0">（清除分类）</option></select>
          <button class="btn-sm" onclick="adminKolBatchCategory()">应用分类</button>
          <button class="btn-sm danger" onclick="adminKolBatch('delete')">批量删除</button>
          <button class="btn-sm" onclick="adminKolClearSelect()">取消选择</button>
        </div>
        <div class="table-wrap">
          <table class="ak-table">
            <thead><tr><th scope="col" style="width:32px"><input type="checkbox" id="ak-checkall" onchange="adminKolTogglePage(this)" aria-label="全选当前页"></th><th scope="col">ID</th><th scope="col">平台</th><th scope="col">昵称</th><th scope="col">分类</th><th scope="col">外部ID</th><th scope="col">档位</th><th scope="col">原创</th><th scope="col">可见性</th><th scope="col">屏蔽词</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
            <tbody>${rows || `<tr class="ak-empty"><td colspan="12" class="muted">${state.adminKolsQ || state.adminKolsCategory || state.adminKolsStatus !== "" || state.adminKolsPlatform ? "没有匹配的大V" : "还没有大V，先用上方表单添加"}</td></tr>`}</tbody>
          </table>
        </div>
        <div class="toolbar" style="margin-top:12px;justify-content:center;gap:12px;align-items:center">
          <button class="btn-sm" ${page <= 0 ? "disabled" : ""} onclick="adminKolsPage(${page - 1})">← 上一页</button>
          <span class="muted">第 ${page + 1}/${pages} 页 · 共 ${state.adminKolsTotal} 个</span>
          <button class="btn-sm" ${page + 1 >= pages ? "disabled" : ""} onclick="adminKolsPage(${page + 1})">下一页 →</button>
        </div>
      </section>`;
    // 回填筛选控件当前值（页面重建后）
    const qEl = $("#ak-q"); if (qEl) qEl.value = state.adminKolsQ || "";
    const catEl = $("#ak-category"); if (catEl) catEl.value = state.adminKolsCategory || "";
    const statusEl = $("#ak-status"); if (statusEl) statusEl.value = state.adminKolsStatus ?? "";
    adminKolSyncCheckall(kols);
    $("#admin-kols-tabs").innerHTML = PLATFORM_TABS.map((p) => platformTabHTML(p, state.adminKolsPlatform, "admin")).join("");
    return { hiddenFocus: focusIds.length > 0 && visibleFocus.length === 0 };
  }

  function switchAdminKolsPlatform(platform) {
    const qEl = $("#ak-q");
    if (qEl) state.adminKolsQ = qEl.value.trim();
    state.adminKolsPlatform = platform;
    state.adminKolsPage = 0;
    loadAdminKols();
  }

  function adminKolsApplyFilter() {
    state.adminKolsQ = $("#ak-q").value.trim();
    state.adminKolsCategory = $("#ak-category").value;
    state.adminKolsStatus = $("#ak-status").value;
    state.adminKolsPage = 0;
    loadAdminKols();
  }

  function adminKolsClearFilter() {
    state.adminKolsQ = "";
    state.adminKolsCategory = "";
    state.adminKolsStatus = "";
    state.adminKolsPlatform = "";
    state.adminKolsPage = 0;
    loadAdminKols();
  }

  function adminKolSyncCheckall(kols) {
    const list = kols || state.adminKols || [];
    const checkall = $("#ak-checkall");
    if (!checkall) return;
    const pageSelected = list.filter((k) => _adminKolsSelected.has(k.id)).length;
    checkall.checked = !!list.length && pageSelected === list.length;
    checkall.indeterminate = pageSelected > 0 && pageSelected < list.length;
  }

  function adminKolsPage(page) {
    state.adminKolsPage = page;
    loadAdminKols();
  }

  function adminKolToggleSelect(el) {
    const id = Number(el.dataset.id);
    if (el.checked) _adminKolsSelected.add(id);
    else _adminKolsSelected.delete(id);
    const bar = $("#ak-batch-bar");
    if (bar) {
      bar.style.display = _adminKolsSelected.size ? "flex" : "none";
      const strong = bar.querySelector("strong");
      if (strong) strong.textContent = `已选 ${_adminKolsSelected.size} 个`;
    }
    adminKolSyncCheckall();
  }

  function adminKolTogglePage(el) {
    document.querySelectorAll(".kol-check").forEach((c) => {
      c.checked = el.checked;
      const id = Number(c.dataset.id);
      if (el.checked) _adminKolsSelected.add(id);
      else _adminKolsSelected.delete(id);
    });
    const bar = $("#ak-batch-bar");
    if (bar) {
      bar.style.display = _adminKolsSelected.size ? "flex" : "none";
      const strong = bar.querySelector("strong");
      if (strong) strong.textContent = `已选 ${_adminKolsSelected.size} 个`;
    }
    adminKolSyncCheckall();
  }

  function adminKolClearSelect() {
    _adminKolsSelected.clear();
    document.querySelectorAll(".kol-check").forEach((c) => { c.checked = false; });
    const bar = $("#ak-batch-bar");
    if (bar) bar.style.display = "none";
    const checkall = $("#ak-checkall");
    if (checkall) {
      checkall.checked = false;
      checkall.indeterminate = false;
    }
  }

  async function adminKolBatch(action, value) {
    const ids = [..._adminKolsSelected];
    if (!ids.length) return;
    if (action === "delete" && !confirm(`确认删除选中的 ${ids.length} 个大V？（将同时清理其订阅/帖子/推送记录）`)) return;
    const bar = $("#ak-batch-bar");
    const buttons = bar ? [...bar.querySelectorAll("button")] : [];
    buttons.forEach((b) => { b.disabled = true; });
    try {
      await api("/api/admin/kols/batch", {
        method: "POST",
        body: JSON.stringify({ ids, action, value: value ?? null }),
      });
      flash(action === "normal" ? `已将 ${ids.length} 个大V设为普通档` : `已对 ${ids.length} 个大V执行批量操作`);
      _adminKolsSelected.clear();
      loadAdminKols();
    } catch (err) {
      flash("批量操作失败: " + err.message, "error");
      buttons.forEach((b) => { b.disabled = false; });
    }
  }

  async function adminKolBatchCategory() {
    const value = $("#ak-batch-category").value;
    if (value === "") { flash("请选择要应用到的分类", "error"); return; }
    await adminKolBatch("category", value === "0" ? null : Number(value));
  }

  async function adminBatchAddKols() {
    const lines = $("#ad-batch-lines").value;
    if (!lines.trim()) {
      flash("请先填写要添加的大V主页链接", "error");
      return;
    }
    const category = $("#ad-batch-category").value;
    // 系统 KOL：每行「中文名 外部ID」（空格分隔，中文名可省略），走 AI 分析专用平台
    const systemMode = $("#ad-batch-system")?.checked;
    const btn = $("#ad-batch-btn");
    if (btn) btn.disabled = true;
    try {
      const data = await api("/api/kols/batch", {
        method: "POST",
        body: JSON.stringify({
          lines,
          platform: systemMode ? "system" : undefined,
          category_id: category ? Number(category) : null,
        }),
      });
      const failLines = data.failed.map((f) => `${f.line} — ${f.error}`).join("\n");
      const view = await loadAdminKols({ focusIds: data.ids || [] });
      const resultEl = $("#ad-batch-result");
      if (resultEl) {
        resultEl.textContent = data.failed.length
          ? `成功 ${data.ok}/${data.total}，失败 ${data.failed.length} 条${failLines ? `\n${failLines}` : ""}`
          : `成功 ${data.ok}/${data.total}`;
        resultEl.style.color = data.failed.length ? "var(--color-danger)" : "var(--color-success)";
        resultEl.style.fontWeight = "600";
      }
      const hidden = view && view.hiddenFocus && data.ok;
      flash(data.failed.length
        ? `添加完成：成功 ${data.ok}/${data.total}，失败 ${data.failed.length} 条${hidden ? "，不在当前筛选里" : ""}`
        : hidden
          ? `添加成功：${data.ok} 个，不在当前筛选里`
          : `添加成功：${data.ok} 个`);
    } catch (err) {
      flash("添加失败: " + err.message, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function adminBatchLinesHint() {
    const lines = $("#ad-batch-lines")?.value || "";
    if (!/(?:xueqiu\.com\/P\/|ZH\d)/.test(lines)) return;
    const cat = $("#ad-batch-category");
    if (!cat || cat.value) return;
    for (const opt of cat.options) {
      if (opt.textContent.trim() === "实盘") { cat.value = opt.value; break; }
    }
  }

  async function adminSetTier(id, tier) {
    if (tier === "priority") return adminTogglePriority(id, true);
    if (tier === "secondary") return adminToggleSecondary(id, true);
    const kol = state.adminKols.find((k) => k.id === id);
    try {
      await api(`/api/kols/${id}`, { method: "PUT", body: JSON.stringify({ priority: false, secondary: false }) });
      flash(`已改为普通档「${kol ? kol.name : "该大V"}」`);
      loadAdminKols();
    } catch (err) {
      flash("操作失败: " + err.message, "error");
    }
  }

  async function adminEditKolKeywords(id) {
    let kol;
    try {
      kol = await api(`/api/kols/${id}`);
    } catch (err) {
      flash("加载失败: " + err.message, "error");
      return;
    }
    const keywords = kol.block_keywords || [];
    const row = state.adminKols.find((k) => k.id === id);
    const blockedCnt = Number(row && row.blocked_count) || 0;
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="ek-keywords-title">
        <h3 id="ek-keywords-title" style="margin-bottom:12px">屏蔽词：${escapeHtml(kol.name)}</h3>
        <label class="form-label">关键词（每行一个，不区分大小写）
          <textarea id="ek-keywords" class="form-control" rows="6" placeholder="广告&#10;加微信&#10;开户"></textarea>
        </label>
        <p class="muted" style="margin:8px 0 0">该大V的消息标题或正文包含任一关键词即被拦截：动态页不再显示，也不再推送给订阅用户。保存后立即对已抓取的历史消息生效。</p>
        ${blockedCnt ? `<p class="muted" style="margin:8px 0 0">当前已拦截 ${blockedCnt} 条消息。</p>` : ""}
        <div class="toolbar" style="margin-top:16px">
          <button class="btn-normal" id="ek-keywords-save" onclick="saveKolKeywords(${kol.id})">保存</button>
          <button type="button" class="btn-sm" data-close>取消</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    $("#ek-keywords").value = keywords.join("\n");
    const initial = kolKeywordsSnapshot();
    const tryClose = async () => {
      if (kolKeywordsSnapshot() !== initial && !(await showConfirm("有未保存的修改，确定关闭？"))) return;
      mask.remove();
    };
    mask.addEventListener("click", (e) => {
      if (e.target === mask) tryClose();
    });
    mask.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        tryClose();
      }
    });
    mask.querySelector("[data-close]").addEventListener("click", tryClose);
    const firstInput = mask.querySelector("textarea");
    if (firstInput) firstInput.focus();
  }

  async function saveKolKeywords(id) {
    const keywords = $("#ek-keywords").value.split(/\n+/).map((s) => s.trim()).filter(Boolean);
    const btn = $("#ek-keywords-save");
    if (btn) btn.disabled = true;
    try {
      await api(`/api/kols/${id}`, {
        method: "PUT",
        body: JSON.stringify({ block_keywords: keywords }),
      });
      const mask = btn && btn.closest(".modal-mask");
      if (mask) mask.remove();
      flash(keywords.length ? `已保存屏蔽词（${keywords.length} 个），命中消息将被拦截` : "已清空屏蔽词");
      loadAdminKols();
    } catch (err) {
      flash("保存失败: " + err.message, "error");
      if (btn) btn.disabled = false;
    }
  }

  function kolKeywordsSnapshot() {
    return $("#ek-keywords").value;
  }

  async function adminViewKolBlock(id) {
    const row = state.adminKols.find((k) => k.id === id);
    if (!row) return;
    const keywords = row.block_keywords || [];
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="ak-block-title">
        <h3 id="ak-block-title" style="margin-bottom:12px">拦截详情：${escapeHtml(row.name)}</h3>
        <div style="margin-bottom:12px">
          <div class="form-label" style="margin-bottom:6px">屏蔽词</div>
          <div id="ak-block-kws">${keywords.length
            ? keywords.map((kw) => `<span class="ak-kw-chip">${escapeHtml(kw)}</span>`).join(" ")
            : '<span class="muted">未设置屏蔽词</span>'}</div>
        </div>
        <div>
          <div class="form-label" style="margin-bottom:6px">拦截的内容</div>
          <div id="ak-block-posts" class="ak-block-list"><p class="muted">加载中…</p></div>
        </div>
        <div class="toolbar" style="margin-top:16px">
          <button class="btn-normal" onclick="this.closest('.modal-mask').remove(); adminEditKolKeywords(${id})">修改屏蔽词</button>
          <button type="button" class="btn-sm" data-close>关闭</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    mask.addEventListener("click", (e) => {
      if (e.target === mask) mask.remove();
    });
    mask.addEventListener("keydown", (e) => {
      if (e.key === "Escape") mask.remove();
    });
    mask.querySelector("[data-close]").addEventListener("click", () => mask.remove());
    const listEl = mask.querySelector("#ak-block-posts");
    try {
      const posts = await api(`/api/posts?kol_id=${id}&blocked=1&limit=200`);
      if (!posts.length) {
        listEl.innerHTML = '<p class="muted">暂无被拦截的消息</p>';
      } else {
        listEl.innerHTML = posts.map((p) => `
          <div class="ak-block-item">
            <div class="muted ak-block-meta">${escapeHtml(fmtDbTime(p.published_at))}${p.block_hit ? ` · 命中「${escapeHtml(p.block_hit)}」` : ""}</div>
            ${p.title ? `<div class="ak-block-title">${escapeHtml(p.title)}</div>` : ""}
            <div class="ak-block-content">${escapeHtml(p.content || "")}</div>
          </div>`).join("");
        const total = Number(row.blocked_count) || 0;
        if (total > posts.length) {
          listEl.insertAdjacentHTML("beforeend", `<p class="muted" style="margin:8px 0 0">共拦截 ${total} 条，当前显示最近 ${posts.length} 条</p>`);
        }
      }
    } catch (err) {
      listEl.innerHTML = `<p class="muted">加载失败: ${escapeHtml(err.message)}</p>`;
    }
  }

  async function adminKolWebhook(id) {
    const row = (state.adminKols || []).find((k) => k.id === id);
    if (!row) return;
    let wh;
    try {
      wh = await api(`/api/admin/kols/${id}/webhook`);
    } catch (err) {
      flash("加载失败: " + err.message, "error");
      return;
    }
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="kw-title">
        <h3 id="kw-title" style="margin-bottom:12px">Webhook：${escapeHtml(row.name)}</h3>
        <p class="muted" style="margin-top:0">外部程序 POST 消息到该地址，就会以「${escapeHtml(row.name)}」的身份发帖并推送给订阅者（参考飞书自定义机器人，兼容其请求格式）。</p>
        <label class="form-label" style="display:flex;align-items:center;gap:8px">
          <input id="kw-enabled" type="checkbox" ${wh.enabled ? "checked" : ""} onchange="adminKolWebhookToggle(${id}, this.checked)"> 启用 Webhook
        </label>
        <div id="kw-url-wrap" ${wh.enabled && wh.token ? "" : "hidden"}>
          <label class="form-label">Webhook 地址
            <div class="toolbar" style="gap:8px">
              <input id="kw-url" class="form-control" readonly value="${escapeHtml(_kolWebhookUrl(wh))}" onclick="this.select()">
              <button type="button" class="btn-sm" onclick="copyText(document.getElementById('kw-url').value, '已复制 Webhook 地址')">复制</button>
            </div>
          </label>
          <label class="form-label">签名密钥（可选，防伪造；飞书同款 HMAC 校验）
            <div class="toolbar" style="gap:8px">
              <input id="kw-secret" class="form-control" placeholder="${wh.secret_set ? "已设置（输入新值可更换）" : "留空则不校验签名"}">
              <button type="button" class="btn-sm" onclick="adminKolWebhookSaveSecret(${id})">保存密钥</button>
              ${wh.secret_set ? `<button type="button" class="btn-sm" onclick="adminKolWebhookSaveSecret(${id}, true)">清除</button>` : ""}
            </div>
          </label>
          <div class="toolbar" style="gap:8px">
            <button type="button" class="btn-sm" onclick="adminKolWebhookRegenerate(${id})">重新生成 Token（旧地址立即失效）</button>
          </div>
          <label class="form-label">调用示例
            <pre class="muted" style="white-space:pre-wrap;user-select:all">${escapeHtml(_kolWebhookCurl(wh))}</pre>
          </label>
        </div>
        <div class="toolbar" style="margin-top:16px">
          <button type="button" class="btn-sm" data-close>关闭</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    mask.addEventListener("click", (e) => { if (e.target === mask) mask.remove(); });
    mask.addEventListener("keydown", (e) => { if (e.key === "Escape") mask.remove(); });
    mask.querySelector("[data-close]").addEventListener("click", () => mask.remove());
  }

  async function adminKolWebhookToggle(id, enabled) {
    try {
      const wh = await api(`/api/admin/kols/${id}/webhook`, {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      });
      flash(enabled ? "Webhook 已启用" : "Webhook 已停用");
      const wrap = $("#kw-url-wrap");
      if (wrap) wrap.hidden = !(wh.enabled && wh.token);
      const urlEl = $("#kw-url");
      if (urlEl && wh.path) urlEl.value = _kolWebhookUrl(wh);
    } catch (err) {
      flash("保存失败: " + err.message, "error");
      const cb = $("#kw-enabled");
      if (cb) cb.checked = !enabled;
    }
  }

  async function adminKolWebhookRegenerate(id) {
    if (!(await showConfirm("确定更换 Token？旧 Webhook 地址会立即失效。"))) return;
    try {
      const wh = await api(`/api/admin/kols/${id}/webhook/regenerate`, { method: "POST" });
      const urlEl = $("#kw-url");
      if (urlEl) urlEl.value = _kolWebhookUrl(wh);
      flash("已更换 Token");
    } catch (err) {
      flash("操作失败: " + err.message, "error");
    }
  }

  async function adminKolWebhookSaveSecret(id, clear = false) {
    const value = clear ? "" : ($("#kw-secret")?.value || "").trim();
    if (!clear && !value) {
      flash("请输入密钥，或点「清除」", "error");
      return;
    }
    try {
      const wh = await api(`/api/admin/kols/${id}/webhook`, {
        method: "PUT",
        body: JSON.stringify({ secret: value }),
      });
      flash(wh.secret_set ? "签名密钥已保存" : "签名密钥已清除");
      const input = $("#kw-secret");
      if (input) {
        input.value = "";
        input.placeholder = wh.secret_set ? "已设置（输入新值可更换）" : "留空则不校验签名";
      }
    } catch (err) {
      flash("保存失败: " + err.message, "error");
    }
  }

  function adminBatchSystemToggle() {
    const system = $("#ad-batch-system")?.checked;
    const ta = $("#ad-batch-lines");
    if (!ta) return;
    const meta = ta.closest(".section-panel")?.querySelector(".section-meta");
    if (system) {
      ta.placeholder = "张三 sys_kol_001\n李四 sys_kol_002\nsys_kol_003";
      if (meta) meta.textContent = "每行一个：中文名 外部ID（空格分隔，中文名可省略，仅填一段文本时整行作为外部 ID）。";
    } else {
      ta.placeholder = "https://xueqiu.com/u/12345\n段永平 https://xueqiu.com/u/12345\nhttps://weibo.com/u/1642591402\nhttps://x.com/elonmusk\nhttps://xueqiu.com/P/ZH123456";
      if (meta) meta.textContent = "每行一个：昵称 + 主页链接（昵称可省略）。平台由链接自动识别。";
    }
  }
  function _kolWebhookUrl(wh) {
    return `${location.origin}${wh.path || ""}`;
  }

  function _kolWebhookCurl(wh) {
    return `curl -X POST '${_kolWebhookUrl(wh)}' -H 'Content-Type: application/json' -d '{"msg_type":"text","content":{"text":"大家好"}}'`;
  }

  async function adminToggleKol(id, enabled) {
    const kol = state.adminKols.find((k) => k.id === id);
    try {
      await api(`/api/kols/${id}`, { method: "PUT", body: JSON.stringify({ enabled: !!enabled }) });
      flash(`已${enabled ? "启用" : "停用"}「${kol ? kol.name : "该大V"}」`);
      loadAdminKols();
    } catch (err) {
      flash("操作失败: " + err.message, "error");
    }
  }

  async function adminTogglePriority(id, priority) {
    const kol = state.adminKols.find((k) => k.id === id);
    try {
      await api(`/api/kols/${id}`, { method: "PUT", body: JSON.stringify({ priority: !!priority }) });
      flash(`已${priority ? "设为优先" : "改为普通档"}「${kol ? kol.name : "该大V"}」`);
      loadAdminKols();
    } catch (err) {
      flash("操作失败: " + err.message, "error");
    }
  }

  async function adminToggleSecondary(id, secondary) {
    const kol = state.adminKols.find((k) => k.id === id);
    try {
      await api(`/api/kols/${id}`, { method: "PUT", body: JSON.stringify({ secondary: !!secondary }) });
      flash(`已${secondary ? "设为次要" : "改为普通档"}「${kol ? kol.name : "该大V"}」`);
      loadAdminKols();
    } catch (err) {
      flash("操作失败: " + err.message, "error");
    }
  }

  async function adminDeleteKol(id) {
    const kol = state.adminKols.find((k) => k.id === id);
    const subs = Number(kol && kol.subscriber_count) || 0;
    if (!confirm(`确认删除该大V${kol ? `「${kol.name}」` : ""}？将同时清理 ${subs} 个订阅及其帖子/推送记录。`)) return;
    try {
      await api(`/api/kols/${id}`, { method: "DELETE" });
      flash(`已删除「${kol ? kol.name : "该大V"}」`);
      loadAdminKols();
    } catch (err) {
      flash("删除失败: " + err.message, "error");
    }
  }

  function adminKolEditSnapshot() {
    return JSON.stringify({
      name: $("#ek-name").value.trim(),
      category: $("#ek-category").value,
      priv: $("#ek-private").checked,
      orig: $("#ek-original") ? $("#ek-original").checked : false,
      users: $("#ek-users").value.trim(),
    });
  }

  async function adminEditKol(id) {
    let kol, categories;
    try {
      [kol, categories] = await Promise.all([api(`/api/kols/${id}`), api("/api/categories")]);
    } catch (err) {
      flash("加载失败: " + err.message, "error");
      return;
    }
    const catOptions = categories.map((c) => `<option value="${c.id}" ${kol.category_id === c.id ? "selected" : ""}>${escapeHtml(c.name)}</option>`).join("");
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="modal-card" role="dialog" aria-modal="true" aria-labelledby="ek-title">
        <h3 id="ek-title" style="margin-bottom:12px">编辑大V：${escapeHtml(kol.name)}</h3>
        <label class="form-label">昵称
          <input id="ek-name" class="form-control" value="${escapeHtml(kol.name)}">
        </label>
        <label class="form-label">分类
          <select id="ek-category" class="form-control"><option value="">未分类</option>${catOptions}</select>
        </label>
        <label class="form-label" style="display:flex;align-items:center;gap:8px">
          <input id="ek-private" type="checkbox" ${kol.is_private ? "checked" : ""} onchange="document.getElementById('ek-users-wrap').hidden=!this.checked"> 私有大V（仅白名单用户可见/可订阅）
        </label>
        ${kol.platform === "weibo" ? `<label class="form-label" style="display:flex;align-items:center;gap:8px">
          <input id="ek-original" type="checkbox" ${kol.original_only ? "checked" : ""}> 只看原创（微博跳过转发，适合转发刷屏的大V）
        </label>` : ""}
        <label class="form-label" id="ek-users-wrap" ${kol.is_private ? "" : "hidden"}>白名单用户（逗号分隔用户名）
          <input id="ek-users" class="form-control" value="${escapeHtml((kol.visible_users || []).join(", "))}" placeholder="user1, user2">
        </label>
        <div class="toolbar" style="margin-top:16px">
          <button class="btn-normal" id="ek-save" onclick="saveKolEdit(${kol.id})">保存</button>
          <button type="button" class="btn-sm" data-close>取消</button>
        </div>
      </div>`;
    const initial = (() => {
      document.body.appendChild(mask);
      return adminKolEditSnapshot();
    })();
    const tryClose = () => {
      if (adminKolEditSnapshot() !== initial && !confirm("有未保存的修改，确定关闭？")) return;
      mask.remove();
    };
    mask.addEventListener("click", (e) => {
      if (e.target === mask) tryClose();
    });
    mask.querySelector("[data-close]").addEventListener("click", tryClose);
    trapFocus(mask, tryClose);
    mask.querySelector("input, select, textarea, button")?.focus();
  }

  async function saveKolEdit(id) {
    const mask = document.querySelector(".modal-mask");
    const name = $("#ek-name").value.trim();
    const isPrivate = $("#ek-private").checked;
    const visibleUsers = $("#ek-users").value.split(",").map((s) => s.trim()).filter(Boolean);
    if (isPrivate && !visibleUsers.length) {
      if (!confirm("白名单为空，该大V将对所有人隐藏。仍要保存？")) return;
    }
    const body = {
      name,
      category_id: $("#ek-category").value ? Number($("#ek-category").value) : null,
      is_private: isPrivate,
      visible_users: visibleUsers,
    };
    if ($("#ek-original")) body.original_only = $("#ek-original").checked;
    const btn = $("#ek-save");
    if (btn) btn.disabled = true;
    try {
      await api(`/api/kols/${id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      if (mask) mask.remove();
      flash(`已保存「${name}」`);
      loadAdminKols();
    } catch (err) {
      flash("保存失败: " + err.message, "error");
      if (btn) btn.disabled = false;
    }
  }

  async function loadAdminVocab() {
    // 深链：/admin/vocab?tab=tags 进标签 Tab，其余值（含无参数）进分类 Tab
    const params = routeQuery();
    const tab = params.get("tab") === "tags" ? "tags" : "categories";
    if (!routeStillActive(currentAdminSeq())) return;
    $("#admin-body").innerHTML = `
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">标签分类</h2>
          <p class="section-meta">分类按大V分组（订阅广场/动态页/管理列表筛选）；标签按关键词规则给贴文内容自动打标。</p></div>
          <div class="settings-tabs" role="tablist" aria-label="标签分类">
            <button class="settings-tab ${tab === "categories" ? "active" : ""}" data-tab="categories" onclick="go('admin/vocab')">分类</button>
            <button class="settings-tab ${tab === "tags" ? "active" : ""}" data-tab="tags" onclick="go('admin/vocab?tab=tags')">标签</button>
          </div>
        </header>
        <div id="vocab-tab-body" class="settings-tab-panel"></div>
      </section>`;
    await loadAdminVocabTab(tab);
  }

  async function loadAdminVocabTab(tab) {
    if (tab === "tags") return loadAdminTagsTab();
    return loadAdminCategoriesTab();
  }

  async function loadAdminCategoriesTab() {
    const categories = await api("/api/categories");
    if (!routeStillActive(currentAdminSeq())) return;
    $("#vocab-tab-body").innerHTML = `
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">添加分类</h2></div>
          <div class="toolbar" style="margin-top:12px">
            <input id="cat-name" class="form-control" style="margin:0;width:280px" placeholder="分类名，如：实盘、宏观、行业研究">
            <button class="btn-normal" onclick="adminAddCategory()">添加分类</button>
          </div>
        </header>
      </section>
      <section class="section-panel">
        <header class="section-head"><div><h2 class="section-title">分类列表</h2></div></header>
        <div class="table-wrap">
          <table>
            <thead><tr><th scope="col">ID</th><th scope="col">分类名</th><th scope="col">大V数</th><th scope="col">操作</th></tr></thead>
            <tbody>${categories.map((c) => `
              <tr>
                <td>${c.id}</td><td>${escapeHtml(c.name)}</td><td>${c.kol_count}</td>
                <td>
                  <button class="btn-sm" onclick="adminRenameCategory(${c.id})">重命名</button>
                  <button class="btn-sm danger" onclick="adminDeleteCategory(${c.id})">删除</button>
                </td>
              </tr>`).join("")}</tbody>
          </table>
        </div>
      </section>`;
  }

  async function adminAddCategory() {
    const name = $("#cat-name").value.trim();
    if (!name) {
      alert("请输入分类名");
      return;
    }
    try {
      await api("/api/categories", { method: "POST", body: JSON.stringify({ name }) });
      flash(`已添加分类「${name}」`);
      loadAdminVocabTab("categories");
    } catch (err) {
      alert("添加失败: " + err.message);
    }
  }

  async function adminRenameCategory(id) {
    const name = prompt("新的分类名：");
    if (name === null || !name.trim()) return;
    try {
      await api(`/api/categories/${id}`, { method: "PUT", body: JSON.stringify({ name: name.trim() }) });
      flash("已重命名分类");
      loadAdminVocabTab("categories");
    } catch (err) {
      alert("重命名失败: " + err.message);
    }
  }

  async function adminDeleteCategory(id) {
    if (!confirm("确认删除该分类？其下大V将变为未分类")) return;
    try {
      await api(`/api/categories/${id}`, { method: "DELETE" });
      flash("已删除分类");
      loadAdminVocabTab("categories");
    } catch (err) {
      alert("删除失败: " + err.message);
    }
  }

  async function loadAdminTagsTab() {
    let data, tagStatus, tagReviews, aliasCands, tagPending;
    try {
      [data, tagStatus, tagReviews, aliasCands, tagPending] = await Promise.all([
        api("/api/tags"),
        api("/api/admin/mx-llm-tag/status"),
        api("/api/admin/post-tag-reviews?status=pending"),
        api("/api/admin/stock-alias-candidates"),
        api("/api/admin/mx-llm-tag/pending"),
      ]);
    } catch (err) {
      if (!routeStillActive(currentAdminSeq())) return;
      $("#vocab-tab-body").innerHTML = emptyState("加载失败: " + err.message);
      return;
    }
    const tags = Array.isArray(data?.tags) ? data.tags : [];
    const stockNames = Array.isArray(data?.stock_names) ? data.stock_names : [];
    const stockAliases = Array.isArray(data?.stock_aliases) ? data.stock_aliases : [];
    const excludedNames = Array.isArray(data?.excluded_stock_names) ? data.excluded_stock_names : [];
    const universe = data?.universe && typeof data.universe === "object" ? data.universe : {};
    const universeCount = Number(universe.count) || 0;
    const universeUpdated = universe.updated ? String(universe.updated) : "";
    const stats = data?.stats || { total: 0, processed: 0, tagged: 0, pending: 0 };
    if (!routeStillActive(currentAdminSeq())) return;
    // 词表编辑：每行一个标签，格式「标签名 | 关键词,关键词」；关键词为空则该标签不命中
    const vocabText = tags.map((r) => `${r.tag} | ${(r.keywords || []).join(", ")}`).join("\n");
    // 别名表编辑：每行「别名=正式名」
    const aliasText = stockAliases.map((a) => `${a.alias}=${a.stock}`).join("\n");
    $("#vocab-tab-body").innerHTML = `
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">贴文标签词表</h2>
          <p class="section-meta">新帖抓取入库时按关键词规则自动打标（零成本、不依赖 LLM）。每行一个标签：<b>标签名 | 关键词1,关键词2</b>，正文/标题命中任一关键词即打该标签，每条最多 3 个。</p></div>
        </header>
        <textarea id="tag-vocab-input" class="form-control" rows="10" style="margin-top:12px;font-family:monospace;line-height:1.6" placeholder="宏观 | 央行,降息,GDP&#10;大盘 | A股,沪指,指数">${escapeHtml(vocabText)}</textarea>
        <div class="toolbar" style="margin-top:12px">
          <button class="btn-normal" onclick="adminSaveTags()">保存词表</button>
        </div>
        <p class="section-meta" style="margin-top:8px">已处理 ${stats.processed} / ${stats.total} 条，其中有标签 ${stats.tagged} 条，待处理 ${stats.pending} 条</p>
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">常用股票名</h2>
          <p class="section-meta">管理员可增删，每行一个。纯文字提及会打股票标签；$股票名(代码)$ 仍自动识别。删掉的名字每日维护不会加回，再写进列表并保存即可恢复。两字名只认这张表。</p></div>
        </header>
        <textarea id="stock-names-input" class="form-control" rows="8" style="margin-top:12px;font-family:monospace;line-height:1.6" placeholder="贵州茅台&#10;宁德时代">${escapeHtml(stockNames.join("\n"))}</textarea>
        <div class="toolbar" style="margin-top:12px">
          <button class="btn-normal" onclick="adminSaveStockNames()">保存股票名</button>
        </div>
        ${universeCount ? `<p class="section-meta" style="margin-top:8px">另有全市场 ${universeCount} 只 3 字及以上正式简称参与纯文字打标${universeUpdated ? `（${escapeHtml(universeUpdated)}）` : ""}，不占手改名单。</p>` : ""}
        ${excludedNames.length ? `<p class="section-meta" style="margin-top:8px">维护不加回：${excludedNames.map((n) => escapeHtml(n)).join("、")}</p>` : ""}
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">黑话别名</h2>
          <p class="section-meta">常见黑话（宁王、药茅）启动时写入；雪球 $戏称(代码)$ 由系统 LLM 解析。正式名切半（宁德/英伟）不会入库。每行「别名=正式名」，正式名需在常用表或全市场名表中。</p></div>
        </header>
        <textarea id="stock-aliases-input" class="form-control" rows="5" style="margin-top:12px;font-family:monospace;line-height:1.6" placeholder="宁王=宁德时代">${escapeHtml(aliasText)}</textarea>
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">标签维护</h2>
          <p class="section-meta">合并种子黑话、解析 $标记$ 新股、去掉指数/ETF 误入的股票名，并清理过期标签与碎片别名。每日自动一次，也可立即执行。标记解析跟管理员「设置 → AI 摘要」同一套 LLM。</p></div>
        </header>
        <p class="section-meta" style="margin-top:8px" id="tag-maintain-meta">${escapeHtml(adminMaintainSummary(data))}</p>
        ${data.maintain && data.maintain.llm_ready ? "" : `<p class="section-meta">未检测到站点 LLM。请到「设置 → AI 摘要」配置 OpenAI 兼容接口，或设环境变量 LLM_API_KEY。点运行仍会合并种子、清碎片和误标。</p>`}
        <div class="toolbar" style="margin-top:12px">
          <button class="btn-normal" onclick="adminMaintainTags('pending')">维护并回填待打标</button>
          <button class="btn-ghost" onclick="adminMaintainTags('none')">仅维护词表</button>
          <button class="btn-ghost" onclick="adminMaintainTags('all')">维护并重算全部</button>
          <span id="tag-maintain-result" class="muted"></span>
        </div>
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">回填历史贴文</h2>
          <p class="section-meta">给未打标贴文按当前词表 + 股票名单补标签；「按当前规则重算全部」会覆盖全部历史贴文标签（危险操作，需确认）。</p></div>
        </header>
        <div class="toolbar" style="margin-top:12px">
          <button class="btn-normal" onclick="adminBackfillTags('pending')">处理待打标</button>
          <button class="btn-ghost" onclick="adminBackfillTags('all')">按当前规则重算全部</button>
          <span id="tag-backfill-result" class="muted"></span>
        </div>
      </section>
      ${adminMxTagPanel(tagStatus, tagReviews, aliasCands, tagPending)}
      <section class="section-panel">
        <header class="section-head"><div><h2 class="section-title">当前词表（${tags.length} 个）</h2></div></header>
        <div class="tag-vocab-preview">
          ${tags.length ? tags.map((r) => `<span class="cat cat-tag">${escapeHtml(r.tag)}</span>`).join("") : "（空）"}
        </div>
      </section>`;
    // 有打标任务在跑（或刚结束未确认）：恢复进度轮询，更新面板里的进度区
    adminMxTagPollProgress();
  }

  const _TAG_REVIEW_KINDS = { topic: "话题", stock: "股票", action: "操作" };
  let _mxAliasCandidates = [];
  let _mxTagReviews = [];               // 当前待审标签列表（行内保留完整消息文本供「更多」展开）
  const _tagReviewExpanded = new Set(); // 已展开全文的审核记录 id（重渲染后保持展开状态）
  let _mxTagTestResult = null;
  let _mxTagPollTimer = null;
  const _mxTagSeenDoneRuns = new Set(); // 已提示过完成结果的打标任务 id（防重复弹提示）
  let _mxTagPollSeenOnce = false;  // 首次观察进度时静默采纳当前状态
  let _tagDetailDirty = false;     // 标签详情弹窗里发生过增删，关闭时需刷新审核队列

  function _tagDetailKindLabel(kind) {
    return _TAG_REVIEW_KINDS[kind] || (kind ? escapeHtml(kind) : "");
  }

  function adminMxTagPanel(tagStatus, tagReviews, aliasCands, tagPending) {
    const st = tagStatus || {};
    const pendingTotal = Number(tagPending?.total) || 0;
    const statusLine = [
      `未打标消息 ${pendingTotal} 条`,
      `今日 LLM 调用 ${(st.calls_today && st.calls_today.count) || 0} 次`,
      `待审标签 ${(st.pending_reviews || 0)} 条`,
      `黑话候选 ${(st.pending_alias_candidates || 0)} 条`,
    ].join("；");
    const alertLine = st.alert_active
      ? `<p class="status-fail" style="margin-top:8px">⚠️ 连续失败 ${st.consecutive_failures || 0} 次，已发系统告警，恢复后会再通知。</p>`
      : "";
    const reviewRows = (tagReviews || []).length === 0
      ? `<tr><td colspan="6" class="muted">暂无待审标签</td></tr>`
      : (tagReviews || []).map((r) => {
          // 全文渲染进单元格，默认钳 2 行，超过 60 字给「更多/收起」展开按钮
          const msg = String(r.title || r.content || "").trim();
          const expanded = _tagReviewExpanded.has(r.id);
          return `
          <tr>
            <td class="tag-review-check"><input type="checkbox" data-review-id="${r.id}" aria-label="选择审核 ${r.id}" onchange="adminTagReviewSelChange()"></td>
            <td>${r.id}</td>
            <td class="tag-review-msg"><span class="muted">${escapeHtml(r.kol_name || "")}：</span><span class="tag-review-msg-text${expanded ? " expanded" : ""}">${escapeHtml(msg)}</span>${msg.length > 60 ? `<button type="button" class="post-expand-btn" aria-expanded="${expanded}" onclick="toggleTagReviewMsg(${r.id}, this)">${expanded ? "收起 ▲" : "更多 ▼"}</button>` : ""}</td>
            <td><span class="cat cat-tag">${escapeHtml(r.tag)}</span></td>
            <td>${_TAG_REVIEW_KINDS[r.kind] || escapeHtml(r.kind || "—")}</td>
            <td>
              <button class="btn-sm" onclick="adminOpenTagReviewModal(${r.post_id})" title="查看该消息的全部标签并直接操作">查看</button>
              <button class="btn-sm" onclick="adminReviewTag(${r.id}, 'approve')">通过</button>
              <button class="btn-sm danger" onclick="adminReviewTag(${r.id}, 'reject')">拒绝</button>
            </td>
          </tr>`;
        }).join("");
    _mxAliasCandidates = Array.isArray(aliasCands?.candidates) ? aliasCands.candidates : [];
    const candRows = _mxAliasCandidates.length === 0
      ? `<tr><td colspan="5" class="muted">暂无黑话候选（LLM 判定为通用黑话时才会进入这里）</td></tr>`
      : _mxAliasCandidates.map((c, idx) => `
          <tr>
            <td>${escapeHtml(c.alias || "")}</td>
            <td>${escapeHtml(c.stock || "")}</td>
            <td>${Number(c.count) || 1}</td>
            <td>${escapeHtml(fmtDbTime(c.first_seen_at || ""))}</td>
            <td>
              <button class="btn-sm" onclick="adminReviewAliasCandidate(${idx}, 'approve')">通过</button>
              <button class="btn-sm danger" onclick="adminReviewAliasCandidate(${idx}, 'reject')">拒绝</button>
            </td>
          </tr>`).join("");
    return `
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">MX LLM 打标（手动）</h2>
          <p class="section-meta">选大V后对其未打标消息跑 LLM（话题/股票/操作三类标签，带准确度）：high 与消息已有标签<b>去重合并</b>写入，low 进下方审核队列（已在消息标签里的不再进审核）；发现的通用黑话进候选队列。一次最多处理 1000 条，每 100 条为一批（一次 LLM 调用只打一批）；同一时间最多 3 批并行，多余批次自动排队；自动触发见下方「MX LLM 打标（自动）」面板。</p></div>
        </header>
        <p class="section-meta" style="margin-top:8px">${statusLine}</p>
        ${alertLine}
        <div class="toolbar" style="margin-top:12px">
          <button class="btn-normal" onclick="adminMxTagOpenRunModal()">开始 LLM 打标</button>
          <button class="btn-ghost" onclick="adminMxTagTest()">试打 10 条（不写库）</button>
        </div>
        <div id="mx-tag-progress" style="margin-top:12px">${adminMxTagProgressInner(null, "manual")}</div>
        ${adminMxTagTestBlock()}
      </section>
      ${adminMxTagAutoPanel(st)}
      <section class="section-panel">
        <header class="section-head"><div><h2 class="section-title">标签审核</h2>
        <p class="section-meta">LLM 标了但不确定（low 准确度）的标签，通过后追加到该条消息。可勾选多条批量操作。</p></div></header>
        <div class="table-wrap">
          <table>
            <thead><tr><th scope="col" class="tag-review-check"><input type="checkbox" id="tag-review-sel-all" aria-label="全选待审标签" onchange="adminTagReviewSelAll(this.checked)"></th><th scope="col">ID</th><th scope="col">消息</th><th scope="col">标签</th><th scope="col">类型</th><th scope="col">操作</th></tr></thead>
            <tbody id="tag-review-tbody">${reviewRows}</tbody>
          </table>
        </div>
        <div class="toolbar" style="margin-top:10px">
          <button class="btn-normal" id="tag-review-batch-approve" disabled onclick="adminReviewTagsBatch('approve')">批量通过</button>
          <button class="btn-ghost" id="tag-review-batch-reject" disabled onclick="adminReviewTagsBatch('reject')">批量拒绝</button>
          <span class="muted" id="tag-review-sel-count">未选择</span>
        </div>
      </section>
      <section class="section-panel">
        <header class="section-head"><div><h2 class="section-title">黑话候选</h2>
        <p class="section-meta">LLM 判定为「社区通用」的新黑话（仅当前消息语境成立的不会进来）。通过后写入黑话别名表，后续消息免 LLM 直接命中。</p></div></header>
        <div class="table-wrap">
          <table>
            <thead><tr><th scope="col">别名</th><th scope="col">正式名</th><th scope="col">出现次数</th><th scope="col">首次发现</th><th scope="col">操作</th></tr></thead>
            <tbody>${candRows}</tbody>
          </table>
        </div>
      </section>`;
  }

  function adminMxTagAutoPanel(st) {
    const auto = (st && typeof st === "object") ? st : {};
    const enabled = !!auto.enabled;
    const regular = auto.regular || { name: "", start: "00:00", end: "23:59", threshold: 50, interval_minutes: 30 };
    const specials = Array.isArray(auto.specials) ? auto.specials : [];
    const statusBits = [];
    if (!enabled) {
      statusBits.push("自动打标未开启");
    } else if (!auto.active_period) {
      statusBits.push("当前不在任何配置的时间段内，不触发");
    } else {
      const p = auto.active_period;
      statusBits.push(
        `当前时段：${p.kind === "special" ? "特殊" : "常规"}${p.name ? `「${escapeHtml(p.name)}」` : ""}${escapeHtml(p.start)}-${escapeHtml(p.end)}（达 ${p.threshold} 条 / 间隔 ${p.interval_minutes} 分钟触发）`,
      );
      if (auto.last_trigger_at) statusBits.push(`上次触发 ${escapeHtml(auto.last_trigger_at)}`);
      statusBits.push(`自上次触发新消息 ${auto.new_since_trigger || 0} 条`);
      if (auto.interval_due_at) statusBits.push(`间隔触发点 ${escapeHtml(auto.interval_due_at)}`);
    }
    return `
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">MX LLM 打标（自动）</h2>
          <p class="section-meta">在时间段内自动对未打标消息跑 LLM 打标，与手动任务共用同一队列（每批 ≤100 条、最多 3 批并行；同一时刻最多一个自动任务在排队/执行，防止处理不及连环入队）。每个时间段两个触发维度：<b>消息条数</b>——新消息累计达到阈值立即触发；<b>时间间隔</b>——距上次触发超过间隔分钟（且有待打标消息）也触发。任一触发后条数累计与间隔计时都重新计算，间隔之内条数先到会把下一个间隔触发点推向后。特殊时间段命中时优先按其配置执行（可增删）。</p></div>
        </header>
        <p class="section-meta" style="margin-top:8px">${statusBits.join("；")}。</p>
        <div id="mx-tag-auto-progress" style="margin-top:12px">${adminMxTagProgressInner(null, "auto")}</div>
        <div style="margin-top:12px">
          <label style="display:inline-flex;align-items:center;gap:8px"><input type="checkbox" id="mx-auto-enabled" ${enabled ? "checked" : ""}> <b>开启自动打标</b></label>
          <div class="mx-auto-period" id="mx-auto-regular" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:10px">
            <span class="nowrap"><b>常规时间段</b>（必填）</span>
            ${mxAutoPeriodInputs(regular)}
          </div>
          <div id="mx-auto-specials">
            ${specials.map((p) => `
            <div class="mx-auto-period" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:8px">
              <span class="nowrap"><b>特殊时间段</b></span>
              ${mxAutoPeriodInputs(p)}
              <button type="button" class="btn-sm danger" onclick="adminMxTagAutoRemoveSpecial(this)">删除</button>
            </div>`).join("")}
          </div>
          <div class="toolbar" style="margin-top:10px">
            <button class="btn-ghost" onclick="adminMxTagAutoAddSpecial()">＋ 添加特殊时间段</button>
            <button class="btn-normal" onclick="adminMxTagAutoSave()">保存配置</button>
          </div>
        </div>
      </section>`;
  }

  async function adminMxTagAutoSave() {
    const regularRow = document.getElementById("mx-auto-regular");
    const enabledBox = document.getElementById("mx-auto-enabled");
    if (!regularRow || !enabledBox) return;
    const readPeriod = (row) => ({
      name: row.querySelector(".mx-auto-name").value.trim(),
      start: row.querySelector(".mx-auto-start").value,
      end: row.querySelector(".mx-auto-end").value,
      threshold: Number(row.querySelector(".mx-auto-threshold").value) || 0,
      interval_minutes: Number(row.querySelector(".mx-auto-interval").value) || 0,
    });
    const payload = {
      enabled: enabledBox.checked,
      regular: readPeriod(regularRow),
      specials: [...document.querySelectorAll("#mx-auto-specials .mx-auto-period")].map(readPeriod),
    };
    try {
      await api("/api/admin/mx-llm-tag/auto-config", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      flash("自动打标配置已保存");
      loadAdminVocabTab("tags");
    } catch (err) {
      flash("保存失败: " + err.message, "error");
    }
  }

  function adminMxTagAutoAddSpecial() {
    const box = document.getElementById("mx-auto-specials");
    if (!box) return;
    if (box.children.length >= 20) {
      flash("特殊时间段最多 20 个", "error");
      return;
    }
    const row = document.createElement("div");
    row.className = "mx-auto-period";
    row.style.cssText = "display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:8px";
    row.innerHTML = `
      <span class="nowrap"><b>特殊时间段</b></span>
      ${mxAutoPeriodInputs({ name: "", start: "09:00", end: "11:30", threshold: 20, interval_minutes: 5 })}
      <button type="button" class="btn-sm danger" onclick="adminMxTagAutoRemoveSpecial(this)">删除</button>`;
    box.appendChild(row);
  }

  function adminMxTagAutoRemoveSpecial(btn) {
    btn.closest(".mx-auto-period")?.remove();
  }

  async function adminMxTagCancel(runId) {
    try {
      await api("/api/admin/mx-llm-tag/cancel", {
        method: "POST",
        body: JSON.stringify({ run_id: runId }),
      });
      flash("已请求取消，当前批次完成后停止，排队批次直接跳过");
    } catch (err) {
      flash("取消失败: " + err.message, "error");
    }
  }

  async function adminMxTagOpenRunModal() {
    let pending;
    try {
      pending = await api("/api/admin/mx-llm-tag/pending");
    } catch (err) {
      flash("加载未打标数据失败: " + err.message, "error");
      return;
    }
    const kols = Array.isArray(pending?.kols) ? pending.kols : [];
    const cap = Number(pending?.max_messages) || 1000;
    if (!kols.length) {
      flash("还没有 MX 大V，请先在「数据源 → MX」同步房间", "error");
      return;
    }
    const rows = kols.map((k) => `
      <label class="mx-tag-kol-row" data-kol="${k.kol_id}" data-pending="${k.pending}">
        <input type="checkbox" data-kol="${k.kol_id}" ${k.pending > 0 ? "" : "disabled"}>
        <span class="mx-tag-kol-name">${escapeHtml(k.name || `大V${k.kol_id}`)}${k.enabled ? "" : ' <span class="muted">（已停用）</span>'}</span>
        <span class="mx-tag-kol-count ${k.pending ? "" : "muted"}">${k.pending} 条未打标</span>
      </label>`).join("");
    const mask = document.createElement("div");
    mask.className = "admin-modal-mask";
    mask.id = "mx-tag-run-mask";
    mask.innerHTML = `
      <div class="admin-modal" role="dialog" aria-modal="true" aria-label="选择要打标的 MX 大V">
        <h3 class="admin-modal-title">选择要 LLM 打标的 MX 大V</h3>
        <p class="section-meta">勾选大V，合计最多处理 ${cap} 条未打标消息（最旧优先）；单个大V超出上限时只处理其最旧的 ${cap} 条。每 100 条为一批，同一时间最多 3 批并行打标，多余批次自动排队，可与进行中的任务并存。</p>
        <div class="admin-modal-list">${rows}</div>
        <p class="section-meta" id="mx-tag-run-total">已选 0 / ${cap} 条</p>
        <div class="toolbar">
          <button class="btn-normal" id="mx-tag-run-start" disabled onclick="adminMxTagStartRun()">开始打标</button>
          <button class="btn-ghost" onclick="document.getElementById('mx-tag-run-mask').remove()">取消</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    const recount = () => {
      let total = 0;
      mask.querySelectorAll("input[type=checkbox]:checked").forEach((cb) => {
        const row = cb.closest(".mx-tag-kol-row");
        total += Math.min(Number(row?.dataset.pending) || 0, cap);
      });
      const startBtn = mask.querySelector("#mx-tag-run-start");
      startBtn.disabled = total === 0;
      startBtn.textContent = total > cap ? `开始打标（处理最旧的 ${cap} 条）` : `开始打标（${total} 条）`;
      mask.querySelector("#mx-tag-run-total").innerHTML = total > cap
        ? `已选超过上限，本次将处理最旧的 <b>${cap}</b> 条`
        : `已选 <b>${total}</b> / ${cap} 条`;
    };
    mask.addEventListener("change", recount);
    recount();
  }

  function adminMxTagPollProgress() {
    if (_mxTagPollTimer) return; // 已有轮询在跑
    const tick = async () => {
      let prog;
      try {
        prog = await api("/api/admin/mx-llm-tag/progress");
      } catch {
        _mxTagPollTimer = setTimeout(tick, 5000);
        return;
      }
      const box = $("#mx-tag-progress");
      if (box) box.innerHTML = adminMxTagProgressInner(prog, "manual");
      const autoBox = $("#mx-tag-auto-progress");
      if (autoBox) autoBox.innerHTML = adminMxTagProgressInner(prog, "auto");
      const runs = Array.isArray(prog?.runs) ? prog.runs : [];
      if (prog.running) {
        _mxTagPollTimer = setTimeout(tick, 3000);
      } else {
        _mxTagPollTimer = null;
      }
      const doneRuns = runs.filter((r) => r.status !== "running" && r.summary);
      if (!_mxTagPollSeenOnce) {
        // 首次观察：静默采纳当前已完成任务（避免页面加载时对历史任务重复提示）
        _mxTagPollSeenOnce = true;
        doneRuns.forEach((r) => _mxTagSeenDoneRuns.add(r.run_id));
        return;
      }
      const fresh = doneRuns.filter((r) => !_mxTagSeenDoneRuns.has(r.run_id));
      if (fresh.length && routeStillActive(currentAdminSeq())) {
        fresh.forEach((r) => _mxTagSeenDoneRuns.add(r.run_id));
        const msg = fresh.map((r) => {
          const s = r.summary;
          const base = `（${mxTagRunLabel(r)}）处理 ${s.processed || 0}/${s.total || 0} 条`;
          const errText = s.error;
          return errText
            ? `${base}，出错：${errText}`
            : `${s.cancelled ? "已取消" : "完成"}：${base}，合并标签 ${s.tagged_posts} 条消息`;
        }).join("；");
        flash(msg, fresh.some((r) => r.summary.error) ? "error" : "ok");
        loadAdminVocabTab("tags");
      }
    };
    tick();
  }

  function adminMxTagProgressInner(prog, source) {
    const runs = (prog && Array.isArray(prog.runs)) ? prog.runs : [];
    const wantAuto = source === "auto";
    const scoped = runs.filter((r) => (wantAuto ? r.source === "auto" : r.source !== "auto"));
    if (!scoped.length) {
      // 自动面板有自己的状态行，空闲时不必再占一行「暂无」
      return wantAuto ? "" : `<p class="section-meta">暂无进行中的打标任务。</p>`;
    }
    const activeHtml = scoped.filter((r) => r.status === "running").map(adminMxTagRunBlock).join("");
    const doneHtml = scoped.filter((r) => r.status !== "running").map(adminMxTagRunDoneLine).join("");
    return `${activeHtml}${doneHtml}`;
  }

  function adminMxTagRunBlock(r) {
    const pct = r.total ? Math.min(100, Math.round(((r.processed || 0) / r.total) * 100)) : 0;
    const settled = (r.batches_done || 0) + (r.batches_failed || 0) + (r.batches_skipped || 0);
    const queued = Math.max(0, (r.batch_total || 0) - settled - (r.batches_running || 0));
    return `
      <div style="margin-bottom:10px">
        <p class="section-meta">正在打标（${escapeHtml(mxTagRunLabel(r))}）：
          已处理 <b>${r.processed || 0}</b>/${r.total || 0} 条 · 批次 ${r.batches_done || 0}/${r.batch_total || 0} 完成
          （打标中 ${r.batches_running || 0} · 排队 ${queued} · 失败 ${r.batches_failed || 0}）</p>
        <div class="mx-tag-progress-bar"><div class="mx-tag-progress-fill" style="width:${pct}%"></div></div>
        <div class="toolbar" style="margin-top:8px">
          <button class="btn-sm danger" onclick="adminMxTagCancel(${r.run_id})">取消任务</button>
          ${r.cancel_requested ? `<span class="muted">取消中：当前批次完成后停止…</span>` : ""}
        </div>
        ${r.status === "failed" && r.error ? `<p class="status-fail" style="margin-top:4px">错误：${escapeHtml(r.error)}（剩余批次将跳过）</p>` : ""}
      </div>`;
  }

  function adminMxTagRunDoneLine(r) {
    const s = r.summary;
    const name = escapeHtml(mxTagRunLabel(r));
    if (!s) {
      return `<p class="section-meta">任务（${name}）已结束${r.error ? `：${escapeHtml(r.error)}` : ""}。</p>`;
    }
    const stateText = s.cancelled ? "已取消" : s.error ? "出错收场" : "已完成";
    const errLine = s.error
      ? `<p class="status-fail" style="margin-top:4px">错误：${escapeHtml(s.error)}</p>`
      : "";
    return `
      <p class="section-meta">任务（${name}）${stateText}（${escapeHtml(r.finished_at || "")}）：
        处理 <b>${s.processed || 0}</b>/${s.total || 0} 条，合并标签 <b>${s.tagged_posts || 0}</b> 条消息，
        进审核 ${s.reviews || 0} 个，黑话候选 ${s.candidates || 0} 个，失败批次 ${s.failed_batches || 0}。</p>
      ${errLine}`;
  }

  async function adminMxTagStartRun() {
    const mask = document.getElementById("mx-tag-run-mask");
    const kolIds = [...mask.querySelectorAll("input[type=checkbox]:checked")]
      .map((cb) => Number(cb.dataset.kol));
    if (!kolIds.length) return;
    try {
      const data = await api("/api/admin/mx-llm-tag/run", {
        method: "POST",
        body: JSON.stringify({ kol_ids: kolIds, max_messages: 1000 }),
      });
      mask.remove();
      flash(`打标任务已启动：${data.total} 条分 ${data.batches} 批（每批 ≤${data.batch_size} 条），与其他任务并行或排队执行`);
      adminMxTagPollProgress();
    } catch (err) {
      flash("启动失败: " + err.message, "error");
    }
  }

  async function adminMxTagTest() {
    try {
      const data = await api("/api/admin/mx-llm-tag/test", { method: "POST" });
      _mxTagTestResult = data;
      flash(`试打完成：${data.tested} 条，预计写入 ${data.summary?.would_tag || 0} 条`);
    } catch (err) {
      _mxTagTestResult = null;
      flash("试打失败: " + err.message, "error");
    }
    loadAdminVocabTab("tags");
  }

  function adminMxTagTestBlock() {
    const r = _mxTagTestResult;
    if (!r) return "";
    if (r.skipped === "no_posts") {
      return `<p class="section-meta" style="margin-top:8px">试打结果：暂无未打标消息。</p>`;
    }
    const summary = r.summary || {};
    const rows = (r.items || []).map((it) => `
      <tr>
        <td>${it.post_id}</td>
        <td>${escapeHtml(it.kol_name || "")}：${escapeHtml(it.excerpt || "")}</td>
        <td>${(it.tags || []).map((t) => `<span class="cat cat-tag">${escapeHtml(t)}</span>`).join("") || '<span class="muted">（无）</span>'}</td>
        <td>${(it.review_tags || []).map((t) => `<span class="cat cat-tag">${escapeHtml(t.tag)}</span>`).join("") || '<span class="muted">（无）</span>'}</td>
        <td>${(it.jargon || []).map((j) => `${escapeHtml(j.alias)}=${escapeHtml(j.stock)}`).join("、") || '<span class="muted">（无）</span>'}</td>
      </tr>`).join("");
    return `
      <p class="section-meta" style="margin-top:10px">试打 ${r.tested} 条未打标消息（未写库，正式打标将与已有标签去重合并）：
        预计直接写入 <b>${summary.would_tag || 0}</b> 条、
        进审核 <b>${summary.would_review || 0}</b> 个标签、
        新增黑话候选 <b>${summary.would_candidates || 0}</b> 个。</p>
      <div class="table-wrap" style="margin-top:8px">
        <table>
          <thead><tr><th scope="col">ID</th><th scope="col">消息</th><th scope="col">将写入标签</th><th scope="col">将进审核</th><th scope="col">将入候选黑话</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  function mxTagRunLabel(r) {
    const auto = r.source === "auto";
    const kols = (r.kols || []).join("、");
    const name = kols || (auto ? "全部大V" : `任务#${r.run_id}`);
    return `${auto ? "[自动] " : ""}${name}`;
  }

  async function adminOpenTagReviewModal(postId) {
    let data;
    try {
      data = await api(`/api/admin/posts/${postId}/tag-detail`);
    } catch (err) {
      flash("加载失败: " + err.message, "error");
      return;
    }
    closeTagReviewModal(); // 防连点叠开
    const mask = document.createElement("div");
    mask.className = "modal-mask tag-detail-mask";
    mask.id = "tag-detail-mask";
    mask.setAttribute("role", "dialog");
    mask.setAttribute("aria-modal", "true");
    mask.setAttribute("aria-label", "标签详情");
    mask.innerHTML = `
      <div class="modal-card tag-detail-card">
        <button type="button" class="tag-detail-close" aria-label="关闭" onclick="closeTagReviewModal()">×</button>
        <h3 class="mx-raw-title">标签详情</h3>
        <p class="mx-raw-meta">${escapeHtml(data.kol_name || "")} · ${fmtPublished(data.published_at)}</p>
        <div class="tag-detail-body" id="tag-detail-body"></div>
      </div>`;
    mask._postId = postId;
    mask.addEventListener("click", (e) => {
      if (e.target === mask) closeTagReviewModal();
    });
    mask._onKey = (e) => {
      if (e.key === "Escape") {
        // 正在输入标签时按 Escape：先清空输入，再按才关弹窗
        if (e.target && e.target.id === "tag-detail-add-input" && e.target.value) {
          e.target.value = "";
          e.preventDefault();
          return;
        }
        e.preventDefault();
        closeTagReviewModal();
      }
    };
    document.addEventListener("keydown", mask._onKey, true);
    document.body.appendChild(mask);
    adminPaintTagDetail(data);
  }

  function closeTagReviewModal() {
    const mask = document.getElementById("tag-detail-mask");
    if (!mask) return;
    document.removeEventListener("keydown", mask._onKey, true);
    mask.remove();
    if (_tagDetailDirty) {
      _tagDetailDirty = false;
      loadAdminVocabTab("tags"); // 弹窗里改过标签，关闭时同步背后的审核队列
    }
  }

  function toggleTagReviewMsg(id, btn) {
    if (_tagReviewExpanded.has(id)) _tagReviewExpanded.delete(id);
    else _tagReviewExpanded.add(id);
    const expanded = _tagReviewExpanded.has(id);
    const text = btn.closest("td")?.querySelector(".tag-review-msg-text");
    if (text) text.classList.toggle("expanded", expanded);
    btn.textContent = expanded ? "收起 ▲" : "更多 ▼";
    btn.setAttribute("aria-expanded", String(expanded));
  }

  async function adminTagReviewModalReview(reviewId, action) {
    try {
      await api(`/api/admin/post-tag-reviews/${reviewId}/${action}`, { method: "POST" });
      _tagDetailDirty = true;
      flash(action === "approve" ? "已通过并追加到消息标签" : "已拒绝该标签");
      adminTagDetailRefresh();
    } catch (err) {
      flash("操作失败: " + err.message, "error");
    }
  }

  function adminTagReviewSelAll(on) {
    document.querySelectorAll("#tag-review-tbody input[data-review-id]").forEach((cb) => { cb.checked = on; });
    adminTagReviewSelChange();
  }

  function adminTagReviewSelChange() {
    const ids = adminTagReviewSelectedIds();
    const total = document.querySelectorAll("#tag-review-tbody input[data-review-id]").length;
    const selAll = document.getElementById("tag-review-sel-all");
    if (selAll) {
      selAll.checked = total > 0 && ids.length === total;
      selAll.indeterminate = ids.length > 0 && ids.length < total;
    }
    const count = document.getElementById("tag-review-sel-count");
    if (count) count.textContent = ids.length ? `已选 ${ids.length} 条` : "未选择";
    const approveBtn = document.getElementById("tag-review-batch-approve");
    const rejectBtn = document.getElementById("tag-review-batch-reject");
    if (approveBtn) approveBtn.disabled = !ids.length;
    if (rejectBtn) rejectBtn.disabled = !ids.length;
  }

  function adminTagReviewSelectedIds() {
    return [...document.querySelectorAll("#tag-review-tbody input[data-review-id]:checked")]
      .map((cb) => Number(cb.dataset.reviewId))
      .filter(Number.isFinite);
  }

  async function adminReviewTag(id, action) {
    try {
      await api(`/api/admin/post-tag-reviews/${id}/${action}`, { method: "POST" });
      flash(action === "approve" ? "已通过并追加到消息标签" : "已拒绝该标签");
      loadAdminVocabTab("tags");
    } catch (err) {
      flash("操作失败: " + err.message, "error");
    }
  }

  async function adminReviewTagsBatch(action) {
    const ids = adminTagReviewSelectedIds();
    if (!ids.length) return;
    const label = action === "approve" ? "通过" : "拒绝";
    const tip = action === "approve" ? "通过后标签会追加到对应消息。" : "";
    if (!(await showConfirm(`确认${label}选中的 ${ids.length} 条待审标签？${tip}`))) return;
    try {
      const data = await api("/api/admin/post-tag-reviews/batch", {
        method: "POST",
        body: JSON.stringify({ ids, action }),
      });
      const okCount = Array.isArray(data.ok) ? data.ok.length : 0;
      const failed = Array.isArray(data.failed) ? data.failed : [];
      flash(
        failed.length
          ? `已${label} ${okCount} 条，失败 ${failed.length} 条：${failed.map((f) => `#${f.id} ${f.reason}`).join("；")}`
          : `已${label} ${okCount} 条待审标签`,
        failed.length ? "error" : "ok",
      );
      loadAdminVocabTab("tags");
    } catch (err) {
      flash(`批量${label}失败: ` + err.message, "error");
    }
  }

  async function adminReviewAliasCandidate(idx, action) {
    const cand = _mxAliasCandidates[idx];
    if (!cand) return;
    try {
      await api(`/api/admin/stock-alias-candidates/${action}`, {
        method: "POST",
        body: JSON.stringify({ alias: cand.alias, stock: cand.stock }),
      });
      flash(action === "approve" ? `已把「${cand.alias}=${cand.stock}」写入黑话别名表` : "已拒绝该候选");
      loadAdminVocabTab("tags");
    } catch (err) {
      flash("操作失败: " + err.message, "error");
    }
  }

  function adminTagDetailHtml(d) {
    const llmSet = new Set((d.llm_tags || []).map((x) => x.tag));
    const delBtn = (t) => `
      <button type="button" class="mx-raw-tag-del" data-tag="${escapeHtml(t)}"
        aria-label="删除标签 ${escapeHtml(t)}" title="删除标签 ${escapeHtml(t)}"
        onclick="adminTagDetailRemoveTag(this.dataset.tag)">×</button>`;
    const curChips = (d.tags || []).map((t) => `
      <span class="cat cat-tag tag-detail-chip${llmSet.has(t) ? " is-llm" : ""}">
        ${escapeHtml(t)}${llmSet.has(t) ? '<i class="tag-llm-badge" title="LLM 打标">LLM</i>' : ""}${delBtn(t)}
      </span>`).join("") || '<span class="muted">暂无标签，可在下方输入框添加</span>';
    const llmChips = (d.llm_tags || []).map((x) => `
      <span class="cat cat-tag tag-detail-chip is-llm">
        ${escapeHtml(x.tag)}<i class="tag-llm-badge" title="LLM 打标">LLM</i>${delBtn(x.tag)}
      </span>`).join("") || '<span class="muted">暂无（LLM 直写或审核通过的标签会显示在这里）</span>';
    const pendingRows = (d.pending_reviews || []).map((r) => `
      <div class="tag-detail-pending-row">
        <span class="cat cat-tag">${escapeHtml(r.tag)}</span>
        <span class="tag-detail-pending-meta">${_tagDetailKindLabel(r.kind) || "—"} · ${r.confidence === "high" ? "高准确度" : "低准确度"}</span>
        <span class="tag-detail-pending-ops">
          <button class="btn-sm" onclick="adminTagReviewModalReview(${r.id}, 'approve')">通过</button>
          <button class="btn-sm danger" onclick="adminTagReviewModalReview(${r.id}, 'reject')">拒绝</button>
        </span>
      </div>`).join("") || '<span class="muted">暂无待审核标签</span>';
    const content = String(d.content || "").trim() || String(d.title || "").trim();
    return `
      ${content ? `<div class="tag-detail-msg">${escapeHtml(content)}</div>` : ""}
      <section class="tag-detail-section">
        <h4 class="tag-detail-sec-title">当前标签（${(d.tags || []).length}）</h4>
        <div class="tag-detail-chips">${curChips}</div>
        <div class="mx-raw-tag-add">
          <input id="tag-detail-add-input" class="form-control" maxlength="30" placeholder="输入新标签，回车或点添加" onkeydown="if(event.key==='Enter'){event.preventDefault();adminTagDetailAddTag();}">
          <button type="button" class="btn-sm" onclick="adminTagDetailAddTag()">添加标签</button>
        </div>
      </section>
      <section class="tag-detail-section">
        <h4 class="tag-detail-sec-title">LLM 打入的标签（${(d.llm_tags || []).length}）</h4>
        <div class="tag-detail-chips">${llmChips}</div>
      </section>
      <section class="tag-detail-section">
        <h4 class="tag-detail-sec-title">待审核标签（${(d.pending_reviews || []).length}）</h4>
        <div class="tag-detail-pending">${pendingRows}</div>
      </section>`;
  }

  async function adminTagDetailRefresh() {
    const mask = document.getElementById("tag-detail-mask");
    if (!mask) return;
    try {
      adminPaintTagDetail(await api(`/api/admin/posts/${mask._postId}/tag-detail`));
    } catch (err) {
      flash("刷新失败: " + err.message, "error");
    }
  }

  async function adminTagDetailAddTag() {
    const mask = document.getElementById("tag-detail-mask");
    const input = document.getElementById("tag-detail-add-input");
    const tag = (input?.value || "").trim();
    if (!mask || !tag) return;
    try {
      await api(`/api/admin/posts/${mask._postId}/tags/add`, {
        method: "POST",
        body: JSON.stringify({ tag }),
      });
      _tagDetailDirty = true;
      flash(`已添加标签「${tag}」`);
      adminTagDetailRefresh();
    } catch (err) {
      flash("添加失败: " + err.message, "error");
    }
  }

  async function adminTagDetailRemoveTag(tag) {
    const mask = document.getElementById("tag-detail-mask");
    if (!mask || !tag) return;
    try {
      await api(`/api/admin/posts/${mask._postId}/tags/remove`, {
        method: "POST",
        body: JSON.stringify({ tag }),
      });
      _tagDetailDirty = true;
      flash(`已删除标签「${tag}」`);
      adminTagDetailRefresh();
    } catch (err) {
      flash("删除失败: " + err.message, "error");
    }
  }

  function adminPaintTagDetail(data) {
    const body = document.querySelector("#tag-detail-mask #tag-detail-body");
    if (body) body.innerHTML = adminTagDetailHtml(data);
  }

  function mxAutoPeriodInputs(p) {
    const q = p || {};
    return `
      <input type="text" class="form-control mx-auto-name" style="width:150px" placeholder="名称（可选）" maxlength="30" value="${escapeHtml(q.name || "")}">
      <input type="time" class="form-control mx-auto-start" style="width:auto" value="${escapeHtml(q.start || "00:00")}" aria-label="开始时间">
      <span>–</span>
      <input type="time" class="form-control mx-auto-end" style="width:auto" value="${escapeHtml(q.end || "23:59")}" aria-label="结束时间">
      <span class="nowrap">新消息达</span>
      <input type="number" class="form-control mx-auto-threshold" style="width:90px" min="1" step="1" value="${Number(q.threshold) || 50}" aria-label="触发条数">
      <span class="nowrap">条 / 间隔</span>
      <input type="number" class="form-control mx-auto-interval" style="width:90px" min="1" step="1" value="${Number(q.interval_minutes) || 30}" aria-label="间隔分钟">
      <span class="nowrap">分钟也触发</span>`;
  }

  async function adminSaveStockNames() {
    const stockNames = $("#stock-names-input").value.split(/\n/).map((s) => s.trim()).filter(Boolean);
    try {
      const data = await api("/api/tags", { method: "PUT", body: JSON.stringify({ stock_names: stockNames }) });
      const dropped = data.dropped_aliases || [];
      flash(dropped.length
        ? `已保存 ${data.stock_names.length} 只股票，去掉别名 ${dropped.map((a) => a.alias).join("、")}`
        : `已保存 ${data.stock_names.length} 只股票`);
      loadAdminVocabTab("tags");
    } catch (err) {
      alert("保存失败: " + err.message);
    }
  }

  async function adminSaveTags() {
    const raw = $("#tag-vocab-input").value;
    const tags = raw.split(/\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
      // 每行「标签名 | 关键词,关键词」；无 | 时整行视为标签名（无关键词）
      const [tag, kw] = line.split("|").map((s) => s.trim());
      const keywords = kw ? kw.split(/[,，]/).map((k) => k.trim()).filter(Boolean) : [];
      return { tag, keywords };
    }).filter((r) => r.tag);
    const stockNames = $("#stock-names-input").value.split(/\n/).map((s) => s.trim()).filter(Boolean);
    const stockAliases = $("#stock-aliases-input").value.split(/\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
      const [alias, stock] = line.split(/[=＝]/).map((s) => s.trim());
      return { alias, stock };
    }).filter((r) => r.alias && r.stock);
    try {
      const data = await api("/api/tags", { method: "PUT", body: JSON.stringify({ tags, stock_names: stockNames, stock_aliases: stockAliases }) });
      flash(`已保存词表（${data.tags.length} 个标签，${data.stock_names.length} 只股票，${data.stock_aliases.length} 个别名）`);
      loadAdminVocabTab("tags");
    } catch (err) {
      alert("保存失败: " + err.message);
    }
  }

  function adminMaintainSummary(data) {
    const last = data && data.maintain && data.maintain.last;
    if (!last || !last.at) return "尚未执行过";
    const parts = [`上次 ${last.at}`];
    if (last.llm_model) parts.push(String(last.llm_model));
    if (last.llm_used) parts.push("LLM 已返回");
    const aliases = last.added_aliases || [];
    const names = last.added_stock_names || [];
    const removed = last.removed_stock_names || [];
    const purged = last.purged_aliases || [];
    const seeded = last.seeded_aliases || [];
    if (aliases.length) parts.push(`新增别名 ${aliases.length}`);
    if (seeded.length) parts.push(`种子 ${seeded.length}`);
    if (purged.length) parts.push(`清除碎片 ${purged.length}`);
    if (names.length) parts.push(`新增股票 ${names.length}`);
    if (removed.length) parts.push(`移除非个股 ${removed.length}`);
    if (last.cleaned) parts.push(`清理 ${last.cleaned} 条`);
    if (last.backfill) parts.push(`回填 ${last.backfill.processed} 条`);
    if (last.error) parts.push("识别异常");
    return parts.join(" · ");
  }

  function formatMaintainResult(data) {
    const bits = [];
    const aliases = data.added_aliases || [];
    const names = data.added_stock_names || [];
    const removed = data.removed_stock_names || [];
    const purged = data.purged_aliases || [];
    if (aliases.length) {
      bits.push("新增别名 " + aliases.map((a) => `${a.alias}→${a.stock}`).join("、"));
    } else {
      bits.push("无新别名");
    }
    if (purged.length) bits.push("清除碎片 " + purged.map((a) => a.alias).join("、"));
    if (names.length) bits.push("新增股票 " + names.join("、"));
    if (removed.length) bits.push("移除 " + removed.join("、"));
    if (data.llm_used) bits.push("LLM 已返回");
    else if (data.error) bits.push("识别异常：" + data.error);
    if (data.cleaned) bits.push(`清理误标 ${data.cleaned} 条`);
    if (data.backfill) bits.push(`回填 ${data.backfill.processed} 条，其中 ${data.backfill.tagged} 条有标签`);
    if (data.error && data.llm_used) bits.push("识别异常：" + data.error);
    return bits.join("；");
  }

  async function adminMaintainTags(backfill = "pending") {
    if (backfill === "all" && !confirm("将覆盖全部历史贴文标签，确定继续？")) return;
    const buttons = document.querySelectorAll("[onclick^='adminMaintainTags']");
    buttons.forEach((button) => { button.disabled = true; });
    const result = $("#tag-maintain-result");
    if (result) result.textContent = backfill === "none" ? "维护中…" : "维护并回填中…";
    try {
      const data = await api("/api/tags/maintain", {
        method: "POST",
        body: JSON.stringify({ backfill }),
      });
      if (result) result.textContent = formatMaintainResult(data);
      flash(backfill === "none" ? "标签维护完成" : "标签维护并回填完成");
      loadAdminVocabTab("tags");
    } catch (err) {
      if (result) result.textContent = "";
      alert("维护失败: " + err.message);
    } finally {
      buttons.forEach((button) => { button.disabled = false; });
    }
  }

  async function adminBackfillTags(mode = "pending") {
    if (mode === "all" && !confirm("将覆盖全部历史贴文标签，确定继续？")) return;
    const buttons = document.querySelectorAll("[onclick^='adminBackfillTags']");
    buttons.forEach((button) => { button.disabled = true; });
    const result = $("#tag-backfill-result");
    if (result) result.textContent = mode === "all" ? "全量重算中…" : "处理中…";
    try {
      const data = await api("/api/tags/backfill", {
        method: "POST",
        body: JSON.stringify({ mode }),
      });
      if (result) result.textContent = `已处理 ${data.processed} 条，其中 ${data.tagged} 条有标签`;
      flash(mode === "all" ? "全量重算完成" : "待打标处理完成");
      loadAdminVocabTab("tags");
    } catch (err) {
      if (result) result.textContent = "";
      alert("处理失败: " + err.message);
    } finally {
      buttons.forEach((button) => { button.disabled = false; });
    }
  }



  return {
    loadAdminKols,
    loadAdminVocab,
    switchAdminKolsPlatform,
    adminKolsApplyFilter,
    adminKolsClearFilter,
    adminKolsPage,
    adminKolToggleSelect,
    adminKolTogglePage,
    adminKolClearSelect,
    adminKolBatch,
    adminKolBatchCategory,
    adminBatchAddKols,
    adminBatchLinesHint,
    adminToggleKol,
    adminTogglePriority,
    adminToggleSecondary,
    adminDeleteKol,
    adminEditKol,
    saveKolEdit,
    adminAddCategory,
    adminRenameCategory,
    adminDeleteCategory,
    adminSaveStockNames,
    adminSaveTags,
    adminMaintainTags,
    adminBackfillTags,
    adminSetTier,
    adminBatchSystemToggle,
    adminKolWebhook,
    adminKolWebhookToggle,
    adminKolWebhookRegenerate,
    adminKolWebhookSaveSecret,
    adminEditKolKeywords,
    saveKolKeywords,
    adminViewKolBlock,
    adminMxTagPanel,
    adminMxTagAutoPanel,
    adminMxTagAutoSave,
    adminMxTagAutoAddSpecial,
    adminMxTagAutoRemoveSpecial,
    adminMxTagCancel,
    adminMxTagOpenRunModal,
    adminMxTagPollProgress,
    adminMxTagProgressInner,
    adminMxTagRunBlock,
    adminMxTagRunDoneLine,
    adminMxTagStartRun,
    adminMxTagTest,
    adminMxTagTestBlock,
    mxTagRunLabel,
    adminOpenTagReviewModal,
    closeTagReviewModal,
    toggleTagReviewMsg,
    adminTagReviewModalReview,
    adminTagReviewSelAll,
    adminTagReviewSelChange,
    adminTagReviewSelectedIds,
    adminReviewTag,
    adminReviewTagsBatch,
    adminReviewAliasCandidate,
    adminTagDetailHtml,
    adminTagDetailRefresh,
    adminTagDetailAddTag,
    adminTagDetailRemoveTag,
    adminPaintTagDetail,
    mxAutoPeriodInputs,
  };
}
