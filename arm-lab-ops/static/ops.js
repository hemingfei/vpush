/* ARM 值班台：壳层 / 主题 / 路由照 vpush；动作仍走本机 /api。 */
const $ = (sel) => document.querySelector(sel);

const THEME_KEY = "theme";
const SIDEBAR_SLIM_KEY = "sidebar-slim";
const LOGO_LIGHT = "/static/logo-mark.svg";
const LOGO_DARK = "/static/logo-mark-dark.svg";

const THEME_SUN = `<svg class="theme-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>`;
const THEME_MOON = `<svg class="theme-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
const THEME_AUTO = `<svg class="theme-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>`;

const ICONS = {
  overview: `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>`,
  cicc: `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8M16 17H8"/></svg>`,
  ima: `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`,
  puller: `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/></svg>`,
  failed: `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/></svg>`,
  storage: `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
  settings: `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
  more: `<svg class="nav-svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg>`,
};

const NAV = [
  { group: "采集", items: [
    { route: "overview", icon: ICONS.overview, label: "总览" },
    { route: "cicc", icon: ICONS.cicc, label: "中金" },
    { route: "ima", icon: ICONS.ima, label: "IMA" },
  ]},
  { group: "缓存", items: [
    { route: "puller", icon: ICONS.puller, label: "Puller" },
    { route: "failed", icon: ICONS.failed, label: "失败队列" },
    { route: "storage", icon: ICONS.storage, label: "115" },
  ]},
  { group: "实验室", items: [
    { route: "settings", icon: ICONS.settings, label: "旋钮" },
  ]},
];

const MOBILE_NAV = [
  { route: "overview", icon: ICONS.overview, label: "总览" },
  { route: "cicc", icon: ICONS.cicc, label: "中金" },
  { route: "puller", icon: ICONS.puller, label: "Puller" },
  { route: "settings", icon: ICONS.settings, label: "旋钮" },
  { route: "more", icon: ICONS.more, label: "更多" },
];

const TITLES = {
  overview: "总览",
  cicc: "中金增量",
  ima: "IMA 凭据",
  puller: "Puller",
  failed: "失败队列",
  storage: "115 / OpenList",
  settings: "实验室旋钮",
  more: "更多",
};

const MORE_ROUTES = new Set(["ima", "failed", "storage", "more"]);

function themeMode() {
  try { return localStorage.getItem(THEME_KEY) || "auto"; }
  catch { return "auto"; }
}

function systemPrefersDark() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function themeIconFor(mode) {
  return { light: THEME_SUN, dark: THEME_MOON, auto: THEME_AUTO }[mode] || THEME_AUTO;
}

function themeLabelFor(mode) {
  return { light: "浅色", dark: "深色", auto: "跟随系统" }[mode] || "跟随系统";
}

function updateThemeToggleIcon() {
  const icon = themeIconFor(themeMode());
  document.querySelectorAll(".theme-toggle-btn").forEach((btn) => { btn.innerHTML = icon; });
}

function applyTheme() {
  const mode = themeMode();
  const dark = mode === "dark" || (mode === "auto" && systemPrefersDark());
  document.documentElement.classList.toggle("theme-dark", dark);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", dark ? "#0f1115" : "#f5f5f7");
  const src = dark ? LOGO_DARK : LOGO_LIGHT;
  document.querySelectorAll("#login-logo, #sidebar-logo, .topbar-logo").forEach((el) => { el.src = src; });
  const fav = document.getElementById("favicon");
  if (fav) fav.setAttribute("href", src);
  updateThemeToggleIcon();
  return dark;
}

function renderThemeSwitcher() {
  const el = $("#theme-switcher");
  if (!el) return;
  const mode = themeMode();
  el.innerHTML = ["light", "dark", "auto"].map((m) => `
    <button class="theme-mode ${mode === m ? "selected" : ""}" data-mode="${m}" title="${themeLabelFor(m)}" aria-label="${themeLabelFor(m)}" aria-pressed="${mode === m}" onclick="setTheme('${m}')">${themeIconFor(m)}</button>`).join("");
}

function setTheme(mode) {
  if (!["light", "dark", "auto"].includes(mode)) mode = "auto";
  try { localStorage.setItem(THEME_KEY, mode); } catch { /* 只影响当前页 */ }
  applyTheme();
  renderThemeSwitcher();
}

function cycleTheme() {
  const order = ["light", "dark", "auto"];
  setTheme(order[(order.indexOf(themeMode()) + 1) % order.length]);
}

function togglePassword(id, btn) {
  const input = document.getElementById(id);
  if (!input) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  if (btn) {
    btn.classList.toggle("visible", show);
    btn.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
  }
}

function sidebarIsSlim() {
  return document.documentElement.classList.contains("sidebar-slim");
}

function syncSidebarToggle() {
  const btn = $("#sidebar-toggle");
  if (!btn) return;
  const slim = sidebarIsSlim();
  btn.setAttribute("aria-expanded", slim ? "false" : "true");
  btn.setAttribute("aria-label", slim ? "展开侧栏" : "收起侧栏");
  btn.title = slim ? "展开侧栏" : "收起侧栏";
}

function toggleSidebarSlim() {
  if (window.matchMedia("(max-width: 900px)").matches) return;
  document.documentElement.classList.toggle("sidebar-slim", !sidebarIsSlim());
  try { localStorage.setItem(SIDEBAR_SLIM_KEY, sidebarIsSlim() ? "1" : "0"); }
  catch { /* 只改本页 */ }
  syncSidebarToggle();
}

function currentRoute() {
  const raw = String(location.hash || "").replace(/^#\/?/, "");
  return TITLES[raw] ? raw : "overview";
}

function go(route) {
  if (!TITLES[route]) route = "overview";
  if (location.hash !== "#/" + route) location.hash = "#/" + route;
  showView(route);
}

function showView(route) {
  if (!TITLES[route]) route = "overview";
  document.querySelectorAll(".ops-view").forEach((el) => {
    const on = el.id === "view-" + route;
    el.classList.toggle("hidden", !on);
    el.toggleAttribute("hidden", !on);
    el.setAttribute("aria-hidden", on ? "false" : "true");
  });
  const title = $("#page-title");
  if (title) title.textContent = TITLES[route];
  document.querySelectorAll(".nav-item").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.route === route);
  });
  document.querySelectorAll(".bnav-item").forEach((btn) => {
    const key = btn.dataset.route;
    const on = key === route || (key === "more" && MORE_ROUTES.has(route));
    btn.classList.toggle("active", on);
  });
}

function renderSidebar() {
  const nav = $("#sidebar-nav");
  if (!nav) return;
  nav.innerHTML = NAV.map((group) => `
    <div class="nav-group-label">${group.group}</div>
    ${group.items.map((item) => `
      <button class="nav-item" data-route="${item.route}" onclick="go('${item.route}')" title="${item.label}">
        <span class="nav-icon">${item.icon}</span>
        <span class="nav-label">${item.label}</span>
      </button>`).join("")}
  `).join("");
  const foot = $("#sidebar-user");
  if (foot) {
    foot.innerHTML = `
      <div class="theme-switcher" id="theme-switcher"></div>
      <div class="sidebar-foot-links">
        <span class="sidebar-user-meta">ARM lab</span>
      </div>`;
  }
  renderThemeSwitcher();
  syncSidebarToggle();
}

function renderTopbar() {
  const el = $("#topbar-user");
  if (!el) return;
  el.innerHTML = `
    <button class="theme-toggle-btn" id="theme-toggle-btn" onclick="cycleTheme()" aria-label="切换主题" title="切换主题"></button>
    <div class="user-chip">
      <div class="user-avatar">A</div>
      <div class="user-meta">
        <span class="user-name">ops</span>
        <span class="user-role">值班</span>
      </div>
    </div>
    <button class="topbar-logout" type="button" onclick="logout()">退出</button>`;
  updateThemeToggleIcon();
}

function logout() {
  const form = document.getElementById("logout-form");
  if (form) form.submit();
}

function renderBottomNav() {
  const nav = $("#bottom-nav");
  if (!nav) return;
  nav.innerHTML = MOBILE_NAV.map((item) => `
    <button type="button" class="bnav-item" data-route="${item.route}" onclick="go('${item.route}')" aria-label="${item.label}">
      <span class="bnav-icon">${item.icon}</span>
    </button>`).join("");
}

function fmtBytes(n) {
  if (n == null || n === "") return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = Number(n);
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return (i === 0 ? String(v) : v.toFixed(1)) + " " + units[i];
}

function bucket(b) {
  if (!b) return "-";
  if (!b.exists) return "无目录";
  const mark = b.truncated ? " · 已截断" : "";
  return (b.files || 0) + " 个 · " + fmtBytes(b.bytes) + mark;
}

function setPipe(id, state, value, sub) {
  const li = document.getElementById("pipe-" + id);
  const v = document.getElementById("pipe-" + id + "-v");
  const s = document.getElementById("pipe-" + id + "-s");
  if (li) li.dataset.state = state || "off";
  if (v && value) v.textContent = value;
  if (s && sub) s.textContent = sub;
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function renderFailed(queue) {
  const body = document.getElementById("failed-body");
  if (!body) return;
  body.textContent = "";
  const items = queue.items || [];
  setText("failed-meta", queue.exists
    ? (items.length + " / " + (queue.count || items.length) + (queue.truncated ? " · 已截断" : ""))
    : "无 failed 目录");
  items.forEach((item) => {
    const tr = document.createElement("tr");
    const checkTd = document.createElement("td");
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = item.path || "";
    cb.className = "failed-pick";
    checkTd.appendChild(cb);
    const pathTd = document.createElement("td");
    pathTd.textContent = item.path || "";
    const sizeTd = document.createElement("td");
    sizeTd.textContent = fmtBytes(item.size);
    const mtimeTd = document.createElement("td");
    mtimeTd.textContent = item.mtime || "-";
    tr.appendChild(checkTd);
    tr.appendChild(pathTd);
    tr.appendChild(sizeTd);
    tr.appendChild(mtimeTd);
    body.appendChild(tr);
  });
}

function render(s) {
  if (!s || !s.ok) return;
  const cache = s.cache || {};
  setText("cache-root", cache.root || "");
  const disk = cache.disk;
  setText("disk-used", disk
    ? fmtBytes(disk.used_bytes) + " / " + fmtBytes(disk.total_bytes) + "（" + disk.used_pct + "%）"
    : "-");
  setText("st-used", bucket(cache.staging));
  setText("hot-used", bucket(cache.hot));
  setText("fail-used", bucket(cache.failed));

  const water = cache.waterline || {};
  const bar = document.getElementById("waterline");
  const fill = document.getElementById("waterline-fill");
  if (bar && fill) {
    if (water.force_bytes) {
      bar.hidden = false;
      fill.classList.toggle("warn", water.level === "warn" || water.level === "force");
      fill.style.width = Math.min(100, Number(water.used_pct_of_force) || 0) + "%";
      setText("waterline-label",
        fmtBytes(water.used_bytes) + " · 告警 " + (water.warn_gb || 30) + "G · 强清 " + (water.force_gb || 35) + "G");
    } else {
      bar.hidden = true;
      setText("waterline-label", "-");
    }
  }

  const exp = s.export || {};
  setText("export-root", exp.root || "");
  setText("export-cicc", bucket(exp.cicc_research));
  const pull = s.pull || {};
  setText("pull-health", pull.ok
    ? "健康 · " + (pull.status || "ok")
    : ("不可达 · " + (pull.status || "-")));

  const puller = s.puller || {};
  const policy = puller.policy || {};
  setText("puller-source", "来源 " + (puller.source || "none"));
  setText("puller-policy", policy.keep_hot === false
    ? "策略：未开 keep_hot（115 失败会挡住热缓存）"
    : "策略：先入 hot，115 后台 · batch " + (policy.batch_size || "-"));
  const timer = puller.timer || {};
  const ciccTimer = puller.cicc_timer || {};
  let timerText = "IMA " + (timer.unit || "timer") + " · " + (timer.enabled || timer.active || "unknown");
  if (timer.next) timerText += " · next " + timer.next;
  if (ciccTimer.next) timerText += " · 中金 " + (ciccTimer.enabled || ciccTimer.active || "") + " · " + ciccTimer.next;
  setText("puller-timer", timerText);
  setText("set-ima-next", timer.next || timer.enabled || "-");
  setText("set-cicc-next", ciccTimer.next || ciccTimer.enabled || "-");
  const uploads = puller.uploads || {};
  setText("puller-uploads",
    "115 上传 ok " + (uploads.ok || 0) + " / fail " + (uploads.fail || 0) +
    (uploads.source && uploads.source !== "none" ? " · " + uploads.source : ""));
  const boxes = (puller.docker && puller.docker.containers) || [];
  setText("puller-docker", boxes.length
    ? boxes.map((c) => (c.name || "") + " " + (c.state || c.status || "")).join(" · ")
    : (puller.docker && puller.docker.available ? "docker 可见，无 puller 容器" : "未挂 docker.sock"));
  const logs = puller.logs || [];
  const pre = document.getElementById("puller-log");
  if (pre) {
    if (logs.length && logs[0].tail && logs[0].tail.length) {
      pre.hidden = false;
      pre.textContent = logs.map((f) => "# " + f.name + "\n" + (f.tail || []).join("\n")).join("\n\n");
    } else {
      pre.hidden = true;
    }
  }

  const ima = s.ima || {};
  setText("ima-meta", ima.present
    ? "在场 · mtime " + (ima.mtime || "-") + " · uid_len " + (ima.uid_len || 0)
    : "未找到 ima-pure.json");
  const imaTimer = ima.timer || timer;
  const imaLive = (s.roles && s.roles.ima_dual_collect) || imaTimer.active === "active";
  const imaPill = document.getElementById("ima-timer-pill");
  if (imaPill) {
    imaPill.textContent = imaLive ? "timer 仍在跑" : "timer 停用";
    imaPill.className = "ops-pill" + (imaLive ? " is-warn" : "");
  }
  setText("ima-timer",
    (imaTimer.unit || "vpush-ima-lab-sync.timer") + " · " +
    (imaTimer.enabled || "-") + " / " + (imaTimer.active || "-"));

  const p115 = s.p115 || {};
  setText("p115-meta", p115.present
    ? "在场 · mtime " + (p115.mtime || "-") + " · length " + (p115.length || 0)
    : "未找到 115-cookies.txt");

  const cicc = s.cicc || {};
  setText("cicc-meta", cicc.present
    ? "CICC Cookie 在场 · mtime " + (cicc.mtime || "-") + " · length " + (cicc.length || 0)
    : "CICC Cookie 未找到（dry-run/apply 会 400）");
  const ciccSync = s.cicc_sync || {};
  setText("cicc-sync-meta", ciccSync.log
    ? (ciccSync.log + " · last " + (ciccSync.last_run || ciccSync.mtime || "-") +
      (ciccSync.days != null ? " · days " + ciccSync.days : "") +
      (ciccSync.returncode != null ? " · rc " + ciccSync.returncode : ""))
    : "没有 cicc-host-sync 日志");
  const ciccDays = document.getElementById("cicc-days");
  if (cicc.incr_days && ciccDays && !ciccDays.dataset.touched) {
    ciccDays.value = cicc.incr_days;
  }

  const sync = s.sync || {};
  const totals = sync.totals || {};
  setText("sync-meta", sync.log
    ? (sync.log + " · last " + (sync.last_run || sync.mtime || "-"))
    : "没有 IMA host / lab sync 日志（正常：生产经 /pull 写入）");
  setText("sync-down", totals.downloaded == null ? "-" : String(totals.downloaded));
  setText("sync-skip", totals.skipped == null ? "-" : String(totals.skipped));
  setText("sync-fail", totals.failed == null ? "-" : String(totals.failed));
  setText("sync-next", imaTimer.next || imaTimer.enabled || "disabled");
  const groups = sync.groups || {};
  const groupKeys = Object.keys(groups);
  setText("sync-groups", groupKeys.length
    ? groupKeys.map((g) => {
        const row = groups[g] || {};
        return g + " d=" + (row.downloaded || 0) + " s=" + (row.skipped || 0) + " f=" + (row.failed || 0);
      }).join(" · ")
    : "无分组计数");
  const err = document.getElementById("sync-error");
  if (err) {
    if (sync.last_error) {
      err.hidden = false;
      err.textContent = "last error: " + sync.last_error;
    } else {
      err.hidden = true;
      err.textContent = "";
    }
  }
  const journal = (sync.journal && sync.journal.tail) || [];
  const jpre = document.getElementById("sync-journal");
  if (jpre) {
    if (journal.length) {
      jpre.hidden = false;
      jpre.textContent = journal.join("\n");
    } else {
      jpre.hidden = true;
    }
  }

  const lastJob = s.last_job;
  const jobPre = document.getElementById("job-log");
  if (jobPre) {
    if (lastJob && (lastJob.stdout || lastJob.stderr || lastJob.error)) {
      jobPre.hidden = false;
      jobPre.textContent = [
        "# " + (lastJob.action || "job") + " rc=" + (lastJob.returncode == null ? "-" : lastJob.returncode),
        lastJob.stdout || "",
        lastJob.stderr || "",
        lastJob.error || "",
      ].filter(Boolean).join("\n");
    } else if (!jobPre.textContent) {
      jobPre.hidden = true;
    }
  }

  renderFailed(s.failed_queue || {});

  const url = (s.openlist && s.openlist.url) || "";
  const slot = document.getElementById("openlist-link");
  if (slot) {
    if (url) {
      slot.textContent = "";
      const a = document.createElement("a");
      a.href = url;
      a.textContent = "打开 /lab-hot";
      slot.appendChild(a);
    } else {
      slot.textContent = "未配置 OPENLIST_PUBLIC_URL";
    }
  }

  setPipe(
    "ima",
    imaLive ? "warn" : "ok",
    imaLive ? "实验室 timer 仍在跑" : "vpush → /pull",
    ima.present ? "凭据在场 · 勿双采" : "缺 ima-pure.json",
  );
  setPipe(
    "cicc",
    cicc.present && ciccTimer.active === "active" ? "ok" : (cicc.present ? "ok" : "warn"),
    "本机增量 " + (cicc.incr_days || 3) + " 天",
    cicc.present ? ((ciccTimer.next || ciccTimer.active || "timer") + "") : "缺 Cookie",
  );
  setPipe(
    "hot",
    policy.keep_hot === false ? "warn" : "ok",
    policy.keep_hot === false ? "未开 keep_hot" : "先入 hot",
    bucket(cache.hot),
  );
  setPipe(
    "pull",
    pull.ok ? "ok" : "warn",
    pull.ok ? "/pull 健康" : "pull 不可达",
    bucket(exp.cicc_research),
  );
}

async function refresh() {
  const r = await fetch("/api/status", { credentials: "same-origin" });
  if (r.status === 401) {
    location.href = "/login";
    return;
  }
  render(await r.json());
}

function showBanner(el, msg, kind) {
  if (!el) return;
  el.hidden = false;
  el.className = "ops-banner" + (kind === "ok" ? " is-ok" : kind === "warn" ? " is-warn" : "");
  el.textContent = msg;
}

async function postJson(url, body) {
  const r = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (r.status === 401) {
    location.href = "/login";
    throw new Error("auth");
  }
  const data = await r.json();
  data._http = r.status;
  return data;
}

function wireConfirm(box, buttons) {
  if (!box) return;
  const sync = () => buttons.forEach((btn) => { if (btn) btn.disabled = !box.checked; });
  box.addEventListener("change", sync);
  sync();
}

function fillSettings(payload) {
  if (!payload || !payload.settings) return;
  const s = payload.settings;
  const clock = document.getElementById("set-clock");
  const days = document.getElementById("set-cicc-days");
  const batch = document.getElementById("set-batch");
  if (clock) clock.value = s.daily_sync_clock || "03:00";
  if (days) days.value = s.cicc_incr_days || 3;
  if (batch) batch.value = s.puller_batch_size;
  const ciccDays = document.getElementById("cicc-days");
  if (ciccDays && !ciccDays.dataset.touched) ciccDays.value = s.cicc_incr_days || 3;
  const timers = payload.timers || {};
  setText("set-ima-next", (timers.ima && (timers.ima.next || timers.ima.enabled)) || "-");
  setText("set-cicc-next", (timers.cicc && (timers.cicc.next || timers.cicc.enabled)) || "-");
  const apply = payload.apply || {};
  const hint = document.getElementById("settings-apply-hint");
  if (hint) {
    if (apply.applied) hint.textContent = "上次保存已自动改写中金 timer OnCalendar。IMA timer 未动。";
    else if (apply.host_command) hint.textContent = "自动改 timer 不可用时，在宿主机执行下方命令。";
  }
}

async function loadSettings() {
  const r = await fetch("/api/settings", { credentials: "same-origin" });
  if (r.status === 401) {
    location.href = "/login";
    return;
  }
  fillSettings(await r.json());
}

function wireDashboard() {
  if (!$("#pipeline-card")) return;

  renderSidebar();
  renderTopbar();
  renderBottomNav();
  showView(currentRoute());
  window.addEventListener("hashchange", () => showView(currentRoute()));
  document.querySelectorAll(".more-item[data-route]").forEach((btn) => {
    btn.addEventListener("click", () => go(btn.dataset.route));
  });

  const ciccDays = document.getElementById("cicc-days");
  if (ciccDays) ciccDays.addEventListener("input", () => { ciccDays.dataset.touched = "1"; });

  wireConfirm(document.getElementById("apply-confirm"), [document.getElementById("cicc-apply")]);
  wireConfirm(document.getElementById("requeue-confirm"), [
    document.getElementById("requeue-selected"),
    document.getElementById("requeue-all"),
  ]);
  wireConfirm(document.getElementById("settings-confirm"), [document.getElementById("settings-save")]);

  async function runCicc(apply) {
    const jobStatus = document.getElementById("job-status");
    const jobLog = document.getElementById("job-log");
    showBanner(jobStatus, apply ? "正在 apply…" : "正在 dry-run…", "");
    const body = { days: Number((document.getElementById("cicc-days") || {}).value || 3) };
    if (apply) body.confirm = true;
    const url = apply ? "/api/sync/cicc/apply" : "/api/sync/cicc/dry-run";
    const data = await postJson(url, body);
    const snippet = [data.stdout, data.stderr, data.error].filter(Boolean).join("\n");
    if (jobLog) {
      jobLog.hidden = !snippet;
      jobLog.textContent = snippet || "";
    }
    showBanner(jobStatus, data.ok ? (data.action || "cicc") + " 完成" : (data.error || "失败"), data.ok ? "ok" : "warn");
    refresh();
  }

  const ciccDry = document.getElementById("cicc-dry");
  const ciccApply = document.getElementById("cicc-apply");
  if (ciccDry) ciccDry.addEventListener("click", () => runCicc(false));
  if (ciccApply) ciccApply.addEventListener("click", () => runCicc(true));

  async function runRequeue(all) {
    const status = document.getElementById("requeue-status");
    if (!document.getElementById("requeue-confirm").checked) {
      showBanner(status, "请先确认", "warn");
      return;
    }
    const body = { confirm: true };
    if (all) {
      body.all = true;
    } else {
      body.paths = Array.from(document.querySelectorAll(".failed-pick:checked")).map((el) => el.value);
      if (!body.paths.length) {
        showBanner(status, "未选择文件", "warn");
        return;
      }
    }
    const data = await postJson("/api/failed/requeue", body);
    showBanner(status, data.ok ? ("已重入 " + (data.count || 0) + " 个") : (data.error || "重入失败"), data.ok ? "ok" : "warn");
    refresh();
  }

  const requeueSelected = document.getElementById("requeue-selected");
  const requeueAll = document.getElementById("requeue-all");
  if (requeueSelected) requeueSelected.addEventListener("click", () => runRequeue(false));
  if (requeueAll) requeueAll.addEventListener("click", () => runRequeue(true));

  const settingsSave = document.getElementById("settings-save");
  if (settingsSave) {
    settingsSave.addEventListener("click", async () => {
      const status = document.getElementById("settings-status");
      const cmd = document.getElementById("settings-host-cmd");
      if (!document.getElementById("settings-confirm").checked) {
        showBanner(status, "请先确认", "warn");
        return;
      }
      const data = await postJson("/api/settings", {
        confirm: true,
        daily_sync_clock: document.getElementById("set-clock").value,
        cicc_incr_days: Number(document.getElementById("set-cicc-days").value),
        puller_batch_size: Number(document.getElementById("set-batch").value),
      });
      fillSettings(data);
      const apply = data.apply || {};
      showBanner(
        status,
        data.ok
          ? (apply.applied ? "已保存，中金 timer 已改写" : "已保存。timer 需在宿主机 apply")
          : (data.error || "保存失败"),
        data.ok ? (apply.applied ? "ok" : "") : "warn",
      );
      if (!cmd) return;
      if (apply.host_command && !apply.applied) {
        cmd.hidden = false;
        cmd.textContent = apply.host_command;
      } else if (apply.detail && !apply.applied) {
        cmd.hidden = false;
        cmd.textContent = (apply.host_command || "") + (apply.detail ? "\n# " + apply.detail : "");
      } else {
        cmd.hidden = !apply.host_command;
        cmd.textContent = apply.host_command || "";
      }
    });
  }

  const qrStatus = document.getElementById("qr-status");
  const qrSlot = document.getElementById("qr-img-slot");
  let qrTimer = null;

  function qrImage() { return qrSlot && qrSlot.querySelector("img"); }
  function hideQrImage() { if (qrSlot) qrSlot.replaceChildren(); }
  function showQrImage(src) {
    if (!qrSlot) return;
    let img = qrImage();
    if (!img) {
      img = document.createElement("img");
      img.id = "qr-img";
      img.alt = "115 登录二维码";
      qrSlot.appendChild(img);
    }
    img.src = src;
  }
  function showQr(msg, kind) { showBanner(qrStatus, msg, kind); }

  async function pollQr(sessionId) {
    const r = await fetch("/api/115/qr/status?session_id=" + encodeURIComponent(sessionId), {
      credentials: "same-origin",
    });
    const data = await r.json();
    if (data.status === "pending") { showQr("等待扫码…", ""); return; }
    if (data.status === "scanned") { showQr("已扫码，请在手机上确认", ""); return; }
    clearInterval(qrTimer);
    qrTimer = null;
    if (data.ok && data.status === "ok") {
      hideQrImage();
      showQr("已写入 Cookie，长度 " + data.cookie_len, "ok");
      refresh();
      return;
    }
    showQr(data.error || data.status || "扫码失败", "warn");
  }

  const qrForm = document.getElementById("qr-form");
  if (qrForm) {
    qrForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      if (qrTimer) clearInterval(qrTimer);
      showQr("正在取码…", "");
      const device = document.getElementById("device-type").value;
      const r = await fetch("/api/115/qr/start", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_type: device }),
      });
      const data = await r.json();
      if (!data.ok) {
        hideQrImage();
        showQr(data.error || "无法开始扫码", "warn");
        return;
      }
      showQrImage(data.qr_png);
      showQr("用 115 App 扫码（设备 " + data.device_type + "）", "");
      qrTimer = setInterval(() => pollQr(data.session_id), 1500);
    });
  }

  if (typeof statusBoot !== "undefined") render(statusBoot);
  loadSettings();
  setInterval(refresh, 8000);
}

if (window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (themeMode() === "auto") {
      applyTheme();
      renderThemeSwitcher();
    }
  });
}

window.cycleTheme = cycleTheme;
window.setTheme = setTheme;
window.togglePassword = togglePassword;
window.toggleSidebarSlim = toggleSidebarSlim;
window.go = go;
window.logout = logout;

applyTheme();
if (document.getElementById("login-form")) updateThemeToggleIcon();
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", wireDashboard);
} else {
  wireDashboard();
}
