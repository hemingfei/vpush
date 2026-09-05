import { escapeHtml, imgProxyUrl, imgSrcFor } from "./core/html.js";
import {
  ARROW_UP_ICON, BELL_ICON, BELL_OFF_ICON, BOOK_ICON, BRAIN_ICON, DATABASE_ICON, DASHBOARD_ICON, FOLDER_ICON,
  EYE_ICON, EYE_OFF_ICON, EXTERNAL_LINK_ICON, FEISHU_DATE_ICON, FILE_TEXT_ICON, FILTER_ICON,
  GEAR_ICON, GITHUB_ICON, GRID_ICON, HISTORY_ICON, KEY_ICON, LIST_ICON,
  MX_VIEWS_ICON, NEWS_ICON, PLUS_ICON, REFRESH_ICON, SEARCH_ICON, SEND_ICON, STAR_SVG,
  THEME_AUTO_ICON, THEME_MOON_ICON, THEME_SUN_ICON, TRASH_ICON, USER_PLUS_ICON, USERS_ICON,
  V_ICON, WSCN_LIVE_ICON, X_ICON,
} from "./core/icons.js";
import { trapFocus } from "./core/dialog.js";
import { createLightbox } from "./core/lightbox.js";
import { createNewsView } from "./views/news.js";
import { createImaView } from "./views/ima.js";
import { createFeishuPersonalView } from "./views/feishu-personal.js";
import { createAdminCodesView } from "./views/admin/codes.js";
import { createAdminNewsView } from "./views/admin/news.js";
import { createAdminUsersView } from "./views/admin/users.js";
import { createAdminKolsView } from "./views/admin/kol.js";
import { createAdminInfraView } from "./views/admin/infra.js";
import { createAdminImaCollectorView } from "./views/admin/ima-collector.js";
import { createAdminKnowledgeView } from "./views/admin/knowledge.js";
import { createAdminDashboardView } from "./views/admin/dashboard.js";
import { createPushSettingsView } from "./views/push-settings.js";

const $ = (sel) => document.querySelector(sel);

const { openLightbox, closeLightbox, lightboxStep, _lbZoomStep, _lbZoomReset } = createLightbox({
  escapeHtml,
  imgOnError,
  trapFocus,
});

const PLATFORM_LABELS = { xueqiu: "雪球", combination: "雪球组合", weibo: "微博", twitter: "X", ima: "ima", zsxq: "知识星球", mx: "MX平台", system: "系统" };
const PLATFORM_SHORT_LABELS = { xueqiu: "雪球", combination: "组合", weibo: "微博", twitter: "X", ima: "ima", zsxq: "星球", mx: "MX", system: "系统" };
function platformShortLabel(p) {
  return p ? (PLATFORM_SHORT_LABELS[p] || PLATFORM_LABELS[p]) : "全部";
}
const PLATFORM_ICONS = {
  "": `<svg class="pt-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg>`,
  xueqiu: `<img class="pt-icon" src="/xueqiu-mark.png" width="16" height="16" alt="" draggable="false" aria-hidden="true">`,
  combination: `<svg class="pt-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/></svg>`,
  weibo: `<svg class="pt-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M10.098 20.323c-3.977.391-7.414-1.406-7.672-4.02-.259-2.609 2.759-5.047 6.74-5.441 3.979-.394 7.413 1.404 7.671 4.018.259 2.6-2.759 5.049-6.737 5.439l-.002.004zM9.05 17.219c-.384.616-1.208.884-1.829.602-.612-.279-.793-.991-.406-1.593.379-.595 1.176-.861 1.793-.601.622.263.82.972.442 1.592zm1.27-1.627c-.141.237-.449.353-.689.253-.236-.09-.313-.361-.177-.586.138-.227.436-.346.672-.24.239.09.315.36.18.601l.014-.028zm.176-2.719c-1.893-.493-4.033.45-4.857 2.118-.836 1.704-.026 3.591 1.886 4.21 1.983.64 4.318-.341 5.132-2.179.8-1.793-.201-3.642-2.161-4.149zm7.563-1.224c-.346-.105-.57-.18-.405-.615.375-.977.42-1.804 0-2.404-.781-1.112-2.915-1.053-5.364-.03 0 0-.766.331-.571-.271.376-1.217.315-2.224-.27-2.809-1.338-1.337-4.869.045-7.888 3.08C1.309 10.87 0 13.273 0 15.348c0 3.981 5.099 6.395 10.086 6.395 6.536 0 10.888-3.801 10.888-6.82 0-1.822-1.547-2.854-2.915-3.284v.01zm1.908-5.092c-.766-.856-1.908-1.187-2.96-.962-.436.09-.706.511-.616.932.09.42.511.691.932.602.511-.105 1.067.044 1.442.465.376.421.466.977.316 1.473-.136.406.089.856.51.992.405.119.857-.105.992-.512.33-1.021.12-2.178-.646-3.035l.03.045zm2.418-2.195c-1.576-1.757-3.905-2.419-6.054-1.968-.496.104-.812.587-.706 1.081.104.496.586.813 1.082.707 1.532-.331 3.185.15 4.296 1.383 1.112 1.246 1.429 2.943.947 4.416-.165.48.106 1.007.586 1.157.479.165.991-.104 1.157-.586.675-2.088.241-4.478-1.338-6.235l.03.045z"/></svg>`,
  twitter: `<svg class="pt-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M14.234 10.162 22.977 0h-2.072l-7.591 8.824L7.251 0H.258l9.168 13.343L.258 24H2.33l8.016-9.318L16.749 24h6.993zm-2.837 3.299-.929-1.329L3.076 1.56h3.182l5.965 8.532.929 1.329 7.754 11.09h-3.182z"/></svg>`,
  zsxq: `<svg class="pt-icon" viewBox="0 0 26 26" fill="currentColor" fill-rule="evenodd" aria-hidden="true"><path d="M13.012 0c.874 0 1.582.708 1.582 1.581 0 .873-.708 1.58-1.582 1.58C7.582 3.161 3.164 7.575 3.164 13c0 5.425 4.418 9.839 9.848 9.839 5.43 0 9.848-4.414 9.848-9.839 0-.873.708-1.58 1.582-1.58S26 12.127 26 13c0 7.168-5.837 13-13 13S0 20.168 0 13 5.837 0 13.012 0zm7.989 2.015a3.003 3.003 0 1 1 0 6.006 3.003 3.003 0 0 1 0-6.006z"/></svg>`,
  mx: `<svg class="pt-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3 12l7-7 2 2 3-3 6 6-6 6-3-3-2 2-7-7z"/></svg>`,
  system: `<svg class="pt-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2"/></svg>`,
};
const CHANNEL_ICONS = {
  telegram: `<svg class="ch-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>`,
  feishu: `<svg class="ch-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2.5c-2 3.4-4.6 5.4-8.8 6.2 4.2.8 6.8 2.8 8.8 6.2 2-3.4 4.6-5.4 8.8-6.2-4.2-.8-6.8-2.8-8.8-6.2z"/></svg>`,
  wecom: `<svg class="ch-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 4c-4.42 0-8 3.02-8 6.75 0 2.13 1.22 4.02 3.12 5.26L6.2 19.5l3.66-1.83c.68.15 1.4.24 2.14.24 4.42 0 8-3.02 8-6.75S16.42 4 12 4z"/></svg>`,
  bark: `<svg class="ch-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z"/></svg>`,
  webpush: `<svg class="ch-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M4 3h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zm0 2v8h16V5H4zm4 13h8v2H8v-2z"/></svg>`,
};
const CHANNEL_LABELS = { telegram: "Telegram", feishu: "飞书", wecom: "企业微信", bark: "Bark", webpush: "浏览器通知" };
const USER_CHANNEL_KEYS = ["telegram", "feishu", "wecom", "bark", "webpush"];
const APP_VERSION = "1.12.139";
const KEYWORDS_MAX_COUNT = 20;
const REPORT_WATCH_BLOCKED_TAGS = new Set([
  "中金研报", "宏观经济", "市场策略", "全球研究", "行业研究", "公司研究",
  "量化及ESG", "大宗商品", "外汇研究", "固定收益", "中金研究院", "其他",
]);
const TL_SOURCE_KEY = "timelineSource";
const KB_LAST_GROUP_KEY = "kb-last-group";
const PLATFORM_TABS = ["", "system", "mx", "xueqiu", "combination", "weibo", "twitter", "zsxq"];
const STATS_TABS = ["config", "cookies", "mx", "imgbed", "plaza", "news", "proxies"];
const STALE_KOL_LIMIT = 10;
const STALE_KOL_HOURS = 48;
const TL_PLATFORMS = PLATFORM_TABS.map((p) => [p, p ? PLATFORM_LABELS[p] : "全部"]);
const state = {
  token: localStorage.getItem("dav_token") || "",
  user: null,
  catalog: [],
  platform: "",
  settingsTab: "push",
  newsSources: [],
  newsVisible: true,
  newsFilterSourceId: "",
  newsQuery: "",
  newsItems: [],
  newsOffset: 0,
  newsHasMore: false,
  newsRequestSeq: 0,
  newsObserver: null,
  newsImageUrls: new Set(),
  adminKolsPlatform: "",
  adminKols: [],
  adminKolsQ: "",
  adminKolsCategory: "",
  adminKolsStatus: "",
  adminKolsPage: 0,
  adminKolsTotal: 0,
  adminUsers: [],
  adminUsersQ: "",
  adminUsersFilter: "all",
  inactivePolicy: { inactive_after_days: 90, inactive_purge_after_days: 30, customized: false },
  homeQ: "",
  homeCategory: "",
  homeSubscribed: false,
  homeFavorite: false,
  timelineFavorite: false,
  timelineSecondary: false,
  timelinePlatform: "",
  timelineKolId: 0,
  timelineCategory: "",
  timelineTag: "",
  timelineQ: "",
  liveImportant: false,
  liveQ: "",
  timelineSource: (() => {
    try {
      const v = sessionStorage.getItem(TL_SOURCE_KEY);
      return v === "live" ? "live" : "kol";
    } catch {
      return "kol";
    }
  })(),
  imaDocumentsQuery: "",
  imaDocumentsDay: "",
  imaDocumentsDays: [],
  imaDocumentsHasMore: false,
  imaDocumentsGroup: "",
  imaDocumentsTag: "",
  imaCatalogSubscribed: [],
  imaCatalogAvailable: [],
  pageBackRoute: "",
  aiTasks: [],
  aiTaskEditing: null,
  aiTaskLogs: [],
  aiTaskLogsTaskId: null,
};

const imaMountState = {
  groups: [],
  selectedGroupId: "",
  folderPanelGroupId: "",
  folderPanelTouched: false,
  drafts: new Map(),
  folders: new Map(),
  parents: new Map(),
  expanded: new Set(),
  loading: new Set(),
  errors: new Map(),
  folderRequests: new Map(),
  discoveryBusy: false,
  discoverySeq: 0,
  discoveryOwner: null,
  discoveryEntered: false,
  dirty: false,
  revision: 0,
  collectorDraft: null,
  collectorDraftRevision: "",
  collectorDirty: false,
  collectorRevision: 0,
  collectorConfirmedRevision: "",
  collectorConfirmedLiveRevision: -1,
  collectorConfirmedMountRevision: -1,
  saveOwner: null,
  requestSeq: 0,
  sessionGeneration: 0,
  generation: 0,
};

const imaCollectorPureCache = {
  uid: "",
  knowledge_base_id: "",
  root_folder_id: "",
  interval_seconds: 3600,
};
function mdInline(s) {
  return s.replace(
    /(`[^`\n]+`)|(\[[^\]\n]+\]\(https?:\/\/[^\s)]+\))|(\*\*[^*\n]+\*\*)|(\*[^*\n]+\*)|(https?:\/\/[^\s<>"\u3000-\u303f\uff00-\uffef\u4e00-\u9fff]+)/g,
    (m, code, mdLink, bold, em, url) => {
      if (code) return `<code>${code.slice(1, -1)}</code>`;
      if (mdLink) {
        const mm = mdLink.match(/^\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)$/);
        return `<a href="${mm[2]}" target="_blank" rel="noopener">${mm[1]}</a>`;
      }
      if (bold) return `<strong>${bold.slice(2, -2)}</strong>`;
      if (em) return `<em>${em.slice(1, -1)}</em>`;
      if (url) {
        // 去掉句尾跟着的标点，避免链接把逗号句号一起吃进去
        const trimmed = url.replace(/[.,;:!?)\]}、，。；：）】]+$/, "");
        const rest = url.slice(trimmed.length);
        return `<a href="${trimmed}" target="_blank" rel="noopener">${trimmed}</a>${rest}`;
      }
      return m;
    });
}

function mdToHtml(text) {
  const src = escapeHtml(String(text ?? ""));
  if (!src.trim()) return escapeHtml(text ?? "");
  const lines = src.split("\n");
  const out = [];
  let para = [];
  const flushPara = () => {
    if (para.length) out.push(`<p>${mdInline(para.join("<br>"))}</p>`);
    para = [];
  };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      flushPara();
      const code = [];
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) { code.push(lines[i]); i++; }
      i++; // 跳过收尾 ```（缺失时自然结束）
      out.push(`<pre><code>${code.join("\n")}</code></pre>`);
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.+?)\s*#*$/);
    if (h) {
      flushPara();
      out.push(`<div class="md-h md-h${h[1].length}">${mdInline(h[2])}</div>`);
      i++;
      continue;
    }
    if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushPara();
      out.push("<hr>");
      i++;
      continue;
    }
    if (/^\s*&gt;\s?/.test(line)) {
      // escapeHtml 已把 > 转成 &gt;，这里按转义后的形态识别引用
      flushPara();
      const quote = [];
      while (i < lines.length && /^\s*&gt;\s?/.test(lines[i])) {
        quote.push(lines[i].replace(/^\s*&gt;\s?/, ""));
        i++;
      }
      out.push(`<blockquote>${mdInline(quote.join("<br>"))}</blockquote>`);
      continue;
    }
    // 表格：当前行以 | 开头，且下一行是 |---|---| 分隔行
    const isTableSep = (l) => /^\s*\|?\s*:?-{2,}[\s:|-]*\|?\s*$/.test(l) && l.includes("-");
    if (/^\s*\|/.test(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      flushPara();
      const parseRow = (l) => l.trim().replace(/^\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
      const head = parseRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(parseRow(lines[i])); i++; }
      const ths = head.map((c) => `<th>${mdInline(c)}</th>`).join("");
      const trs = rows.map((r) => `<tr>${r.map((c) => `<td>${mdInline(c)}</td>`).join("")}</tr>`).join("");
      out.push(`<div class="md-table-wrap"><table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`);
      continue;
    }
    if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line) || /^\s*\d+、/.test(line)) {
      flushPara();
      const ordered = /^\s*\d+[.、)]/.test(line);
      const items = [];
      // 「1. xxx」要求跟空格（避免把「1.5 倍」当列表）；「1、xxx」是中文习惯，不要求空格
      const re = /^\s*\d+、\s*/.test(line) ? /^\s*\d+、\s*/ : (ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/);
      while (i < lines.length && re.test(lines[i])) {
        items.push(`<li>${mdInline(lines[i].replace(re, ""))}</li>`);
        i++;
      }
      out.push(ordered ? `<ol>${items.join("")}</ol>` : `<ul>${items.join("")}</ul>`);
      continue;
    }
    if (!line.trim()) {
      flushPara();
      i++;
      continue;
    }
    para.push(line);
    i++;
  }
  flushPara();
  return out.join("");
}

// 本会话内确认失效的图片 URL（直连 + 代理都失败）。feed 重渲染是全量重建 <img> 的，
// 不记名单的话同一张死图每次重渲染都会重新请求一遍，控制台 404 刷屏
const _deadImgUrls = new Set();

function rememberDeadUrl(url) {
  if (url) _deadImgUrls.add(url);
}

// 代理地址还原出原始图片 URL；非代理地址原样返回
function originalUrlFromProxySrc(src) {
  if (!src.startsWith("/api/img-proxy")) return src;
  try {
    return new URL(src, location.origin).searchParams.get("url") || src;
  } catch {
    return src;
  }
}

// 图片彻底失效的收尾：记入失效名单并摘除元素。信息流缩略图整块移除；
// 灯箱的 img 是导航结构的一部分，改为隐藏并展示「图片已失效」提示
function markImgDead(img) {
  if (!img) return;
  rememberDeadUrl(originalUrlFromProxySrc(img.getAttribute("src") || ""));
  img.dataset.dead = "1";
  if (img.classList.contains("lightbox-img")) {
    img.style.display = "none";
    const box = img.parentElement;
    if (box && !box.querySelector(".lightbox-dead")) {
      const tip = document.createElement("div");
      tip.className = "lightbox-dead";
      tip.setAttribute("role", "alert");
      tip.textContent = "图片已失效";
      box.appendChild(tip);
    }
    return;
  }
  const link = img.closest(".post-img-link");
  if (link) link.remove();
  else img.remove();
}

function imgOnError(img) {
  // 第三方图床直连失败（大陆访问 X 图床被墙等）→ 经服务端代理转发；
  // 代理也失败说明图彻底挂了，标记失效避免后续重渲染反复请求。
  // onerror 必须保持绑定：原先失败即置 null，代理这一步永远没有第二次回调
  if (!img) return;
  const src = img.getAttribute("src") || "";
  if (src.startsWith("/api/img-proxy")) {
    markImgDead(img);
    return;
  }
  if (img.dataset.proxied) return;
  img.dataset.proxied = "1";
  img.src = imgProxyUrl(src);
  img.onerror = imgOnError;
}

let _toastTimer = null;
// 操作反馈统一走 toast：成功 flash(msg)，失败 flash(msg, "error")。绑定码等需停留的内容仍写在页面上。
function flash(message, type = "success") {
  let el = $("#toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.setAttribute("aria-live", "polite"); // 操作反馈对读屏可感知
    document.body.appendChild(el);
  }
  el.className = `toast ${type}`;
  el.textContent = message;
  el.classList.remove("hide");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    el.classList.add("hide");
    setTimeout(() => el.remove(), 320);
  }, 2600);
}

// 原生 confirm/alert/prompt 由浏览器渲染，固定在窗口顶部、样式不受控，统一换成应用内居中弹窗。
// showConfirm resolve(true/false)；showAlert 只作提示；showPrompt resolve(输入值/null)。
let _dialogOpen = false; // 一次只弹一个，避免连点导致弹窗叠加
function showDialog({ title, message = null, input = null, okText, cancelText = null, danger = false }) {
  const cancelled = input ? null : false;
  if (_dialogOpen) return Promise.resolve(cancelled);
  _dialogOpen = true;
  return new Promise((resolve) => {
    const mask = document.createElement("div");
    mask.className = "modal-mask dialog-mask";
    const card = document.createElement("div");
    card.className = "modal-card dialog-card";
    card.setAttribute("role", "alertdialog");
    card.setAttribute("aria-modal", "true");
    card.setAttribute("aria-label", title);
    const h = document.createElement("h3");
    h.className = "dialog-title";
    h.textContent = title;
    card.appendChild(h);
    if (message != null) {
      const p = document.createElement("p");
      p.className = "dialog-message"; // pre-line 保留换行；textContent 防止拼进消息的外部内容被当 HTML
      p.textContent = message;
      card.appendChild(p);
    }
    let inputEl = null;
    if (input) {
      inputEl = document.createElement("input");
      inputEl.className = "form-control dialog-input";
      inputEl.value = input.value || "";
      inputEl.placeholder = input.placeholder || "";
      card.appendChild(inputEl);
    }
    const actions = document.createElement("div");
    actions.className = "dialog-actions";
    let cancelBtn = null;
    if (cancelText) {
      cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "btn-ghost dialog-btn";
      cancelBtn.textContent = cancelText;
      actions.appendChild(cancelBtn);
    }
    const okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.className = "btn-normal dialog-btn" + (danger ? " dialog-btn-danger" : "");
    okBtn.textContent = okText;
    actions.appendChild(okBtn);
    card.appendChild(actions);
    mask.appendChild(card);

    const close = (result) => {
      document.removeEventListener("keydown", onKey, true);
      mask.remove();
      _dialogOpen = false;
      resolve(result);
    };
    const submit = () => close(inputEl ? inputEl.value : true);
    const cancel = () => close(cancelled);
    const focusables = [inputEl, cancelBtn, okBtn].filter(Boolean);
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation(); // 弹窗在上层时，避免连带触发底下弹窗/灯箱的 Esc 逻辑
        cancel();
      } else if (e.key === "Tab") {
        e.preventDefault(); // 可聚焦元素只有一两个，Tab 在弹窗内循环，避免焦点跑到页面背后
        e.stopPropagation(); // 避免与底下弹窗的 Tab 焦点陷阱双重处理
        const idx = focusables.indexOf(document.activeElement);
        const dir = e.shiftKey ? -1 : 1;
        focusables[(idx + dir + focusables.length) % focusables.length].focus();
      } else if (e.key === "Enter" && !document.activeElement.classList.contains("dialog-btn")) {
        e.preventDefault(); // 焦点在按钮上时交给浏览器原生 click，避免双重触发
        submit();
      }
    };
    if (cancelBtn) cancelBtn.addEventListener("click", cancel);
    okBtn.addEventListener("click", submit);
    mask.addEventListener("click", (e) => {
      if (e.target === mask) cancel(); // 点遮罩视为取消
    });
    document.addEventListener("keydown", onKey, true);
    document.body.appendChild(mask);
    if (inputEl) {
      inputEl.focus();
      inputEl.select();
    } else {
      okBtn.focus();
    }
  });
}
function showConfirm(message, { title = "确认操作", okText = "确定", cancelText = "取消", danger = false } = {}) {
  return showDialog({ title, message, okText, cancelText, danger });
}
function showAlert(message, { title = "提示", okText = "知道了" } = {}) {
  return showDialog({ title, message, okText });
}
function showPrompt(message, { title = "请输入", okText = "确定", value = "", placeholder = "" } = {}) {
  return showDialog({ title, message, okText, cancelText: "取消", input: { value, placeholder } });
}

async function api(path, options = {}) {
  const requestToken = state.token;
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (requestToken) headers.Authorization = `Bearer ${requestToken}`;
  const resp = await fetch(path, { ...options, headers });
  // 登录/注册的 401 是「凭据错误」业务响应：透出后端 detail，不清会话
  if (resp.status === 401 && !path.startsWith("/api/auth/") && state.token === requestToken) {
    logout();
    throw new Error("登录已过期，请重新登录");
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    // FastAPI 422 等校验错误的 detail 是数组/对象，直接拼接会显示 [object Object]
    const detail = data.detail;
    const msg = typeof detail === "string" ? detail : (detail ? JSON.stringify(detail) : resp.statusText);
    throw new Error(msg);
  }
  return data;
}

async function apiBlob(path, options = {}) {
  const requestToken = state.token;
  const headers = { ...(options.headers || {}) };
  if (requestToken) headers.Authorization = `Bearer ${requestToken}`;
  const resp = await fetch(path, { ...options, headers });
  if (resp.status === 401 && !path.startsWith("/api/auth/") && state.token === requestToken) {
    logout();
    throw new Error("登录已过期，请重新登录");
  }
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    const detail = data.detail;
    const msg = typeof detail === "string" ? detail : (detail ? JSON.stringify(detail) : resp.statusText);
    throw new Error(msg);
  }
  return resp.blob();
}

function revokeFeishuTimelineMediaUrls() {
  document.querySelectorAll("img[data-feishu-asset]").forEach((img) => {
    if (String(img.src || "").startsWith("blob:")) img.removeAttribute("src");
  });
  for (const url of _feishuTimelineMediaUrls) URL.revokeObjectURL(url);
  _feishuTimelineMediaUrls = [];
  _feishuTimelineMediaCache.clear();
}

function resetFeishuTimelineMedia() {
  _feishuMoreObserver?.disconnect();
  _feishuMoreObserver = null;
  _feishuAssetObserver?.disconnect();
  _feishuAssetObserver = null;
  clearTimeout(_feishuTimelineTimer);
  _feishuTimelineTimer = null;
  revokeFeishuTimelineMediaUrls();
  _feishuTimelineState = null;
}

function isStandalonePwa() {
  return window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
}

function clearSessionCaches() {
  clearImaPdfUrl();
  if (typeof stopTimelinePoll === "function") stopTimelinePoll();
  // 飞书扫码轮询不能跨会话存活：登出后它会每秒拿旧 token 打 401 循环
  if (typeof stopFeishuPersonalPoll === "function") stopFeishuPersonalPoll();
  fsPersonalState.owner = null;
  fsPersonalState.sessionId = "";
  fsPersonalState.bindCommand = "";
  fsPersonalState.bindExpiresAt = 0;
  fsPersonalState.verificationUri = "";
  fsPersonalState.qrUri = "";
  fsPersonalState.refreshInFlight = false;
  if (typeof wbQrTimer !== "undefined") {
    if (wbQrTimer) clearTimeout(wbQrTimer);
    wbQrTimer = null;
    wbQrSeq += 1;
  }
  clearNewsReaderState();
  _tlPosts.length = 0;
  _tlOffset = 0;
  _tlHasMore = true;
  _tlExpanded.clear();
  _tlLatestId = 0;
  _tlLoadedFilter = null;
  _tlSavedScrollY = 0;
  _tlPendingNew.length = 0;
  _tlPendingLatestId = 0;
  feishuPersonalView.pendingBind = null;
  state.timelineQ = "";
  state.timelineCategory = "";
  state.timelineTag = "";
  state.timelinePlatform = "";
  state.timelineKolId = 0;
  tlClearKolNewCounts();
  state.timelineFavorite = false;
  state.timelineSecondary = false;
  state.liveImportant = false;
  state.liveQ = "";
  if (typeof _livePosts !== "undefined") {
    _livePosts.length = 0;
    _liveCursor = "";
    _liveLatestId = 0;
    _livePendingNew.length = 0;
    _livePendingLatestId = 0;
    _liveInflight = null;
  }
  imaMountState.groups = [];
  imaMountState.selectedGroupId = "";
  imaMountState.drafts = new Map();
  imaMountState.folders = new Map();
  imaMountState.parents = new Map();
  imaMountState.expanded = new Set();
  imaMountState.loading = new Set();
  imaMountState.errors = new Map();
  imaMountState.folderRequests = new Map();
  imaMountState.discoveryBusy = false;
  imaMountState.discoverySeq += 1;
  imaMountState.discoveryOwner = null;
  imaMountState.discoveryEntered = false;
  imaMountState.dirty = false;
  imaMountState.revision += 1;
  imaMountState.collectorDraft = null;
  imaMountState.collectorDraftRevision = "";
  imaMountState.collectorDirty = false;
  imaMountState.collectorRevision = 0;
  imaMountState.collectorConfirmedRevision = "";
  imaMountState.collectorConfirmedLiveRevision = -1;
  imaMountState.collectorConfirmedMountRevision = -1;
  imaMountState.saveOwner = null;
  imaMountState.requestSeq += 1;
  imaMountState.sessionGeneration += 1;
  imaMountState.generation += 1;
  _lastAdminStatsSnapshot = null;
}

function logout() {
  state.token = "";
  state.user = null;
  localStorage.removeItem("dav_token");
  clearSessionCaches();
  replaceRoute("timeline");
  $("#app-view").classList.add("hidden");
  $("#auth-view").classList.remove("hidden");
  resetAuthButtons();
}

function resetAuthButtons() {
  // 登录/注册提交中按钮会 disabled；登出或切换模式后恢复默认态
  const loginBtn = $("#login-form")?.querySelector('button[type="submit"]');
  const regBtn = $("#register-form")?.querySelector('button[type="submit"]');
  if (loginBtn) { loginBtn.disabled = false; loginBtn.textContent = "登 录"; }
  if (regBtn) { regBtn.disabled = false; regBtn.textContent = "创建账号"; }
}

const USERNAME_RE = /^[A-Za-z\u4e00-\u9fff][A-Za-z0-9_\-\u4e00-\u9fff]{5,29}$/;
const USERNAME_CHARSET_MSG = "用户名仅限中文、字母、数字、下划线和连字符，须以中文或字母开头";

function usernameRuleError(name) {
  const trimmed = (name || "").trim();
  if (trimmed.length < 6) return "用户名至少6位";
  if (trimmed.length > 30) return "用户名最长30位";
  if (!USERNAME_RE.test(trimmed)) return USERNAME_CHARSET_MSG;
  return "";
}

function avatarText(name) {
  return (name || "?").trim().slice(0, 1).toUpperCase();
}

// 头像图挂了就换成首字色块占位，避免破图；name 由 data-av-name 带入。
// 失效 URL 记入名单：重渲染重建 <img> 时直接出色块，不再重复请求死链
function avatarImgError(img) {
  rememberDeadUrl(originalUrlFromProxySrc(img.getAttribute("src") || ""));
  const ph = document.createElement("div");
  ph.className = img.dataset.avClass || img.className || "kol-avatar";
  ph.textContent = avatarText(img.dataset.avName);
  img.replaceWith(ph);
}

function avatarHtml(name, url) {
  if (url && !_deadImgUrls.has(url)) return `<img class="kol-avatar" src="${escapeHtml(url)}" alt="" loading="lazy" data-av-name="${escapeHtml(name)}" onerror="avatarImgError(this)">`;
  return `<div class="kol-avatar">${escapeHtml(avatarText(name))}</div>`;
}

// ---------- 壳 ----------
const NAV = [
  { group: "订阅", items: [
    { route: "timeline", icon: LIST_ICON, label: "最新动态" },
    { route: "mx-views", icon: MX_VIEWS_ICON, label: "MX观点" },
    { route: "news", icon: NEWS_ICON, label: "财经新闻" },
    { route: "knowledge", icon: BOOK_ICON, label: "研报库" },
    { route: "home", icon: GRID_ICON, label: "订阅广场" },
    { route: "settings", icon: GEAR_ICON, label: "设置" },
  ]},
  { group: "", admin: true, subs: [
    { label: "内容管理", items: [
      { route: "admin/dashboard", icon: DASHBOARD_ICON, label: "全景概览" },
      { route: "admin/kols", icon: V_ICON, label: "大V管理" },
      { route: "admin/ai-analysis", icon: BRAIN_ICON, label: "AI分析" },
      { route: "admin/mx-views", icon: MX_VIEWS_ICON, label: "MX观点" },
      { route: "admin/vocab", icon: FOLDER_ICON, label: "标签分类" },
      { route: "admin/requests", icon: USER_PLUS_ICON, label: "添加审批" },
    ]},
    { label: "数据与日志", items: [
      { route: "admin/stats", icon: BOOK_ICON, label: "数据源" },
      { route: "admin/knowledge", icon: BOOK_ICON, label: "研报库设置" },
      { route: "admin/posts", icon: FILE_TEXT_ICON, label: "帖子" },
      { route: "admin/logs", icon: SEND_ICON, label: "推送记录" },
      { route: "admin/audit", icon: HISTORY_ICON, label: "操作日志" },
      { route: "admin/backup", icon: DATABASE_ICON, label: "备份" },
    ]},
    { label: "用户与注册", items: [
      { route: "admin/users", icon: USERS_ICON, label: "用户" },
      { route: "admin/codes", icon: KEY_ICON, label: "注册码" },
    ]},
  ]},
];

const SIDEBAR_SLIM_KEY = "sidebar-slim";

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
  try {
    localStorage.setItem(SIDEBAR_SLIM_KEY, sidebarIsSlim() ? "1" : "0");
  } catch {
    /* 无 localStorage 时只改本页 */
  }
  syncSidebarToggle();
}

function renderSidebar(user) {
  const navItemHtml = (item) => `
        <button class="nav-item" data-route="${item.route}" onclick="go('${item.route}')" title="${item.label}">
          <span class="nav-icon">${item.icon}</span>
          <span class="nav-label">${item.label}</span>
        </button>`;
  const html = NAV.filter((g) => !g.admin || user.is_admin)
    .map((group) => `
      ${group.group ? `<div class="nav-group-label">${group.group}</div>` : ""}
      ${(group.items || []).filter((item) => item.route !== "news" || state.newsVisible).map(navItemHtml).join("")}
      ${(group.subs || []).map((sub) => `
        <details class="nav-sub" open>
          <summary class="nav-sub-label">${sub.label}</summary>
          ${sub.items.filter((item) => item.route !== "news" || state.newsVisible).map(navItemHtml).join("")}
        </details>`).join("")}
    `).join("");
  $("#sidebar-nav").innerHTML = html;
  $("#sidebar-user").innerHTML = `
    <div class="theme-switcher" id="theme-switcher"></div>
  `;
  renderThemeSwitcher();
  syncSidebarToggle();
  checkUpdate();
  ensureVersionRefreshCheck();
}

const MOBILE_NAV = [
  { route: "timeline", icon: LIST_ICON, label: "动态" },
  { route: "news", icon: NEWS_ICON, label: "财经新闻" },
  { route: "home", icon: GRID_ICON, label: "广场" },
  { route: "mx-views", icon: MX_VIEWS_ICON, label: "观点" },
  { route: "settings", icon: GEAR_ICON, label: "设置" },
];

function renderBottomNav(user) {
  const tabs = MOBILE_NAV.filter((tab) => tab.route !== "news" || state.newsVisible);
  if (user.is_admin) tabs.push({ route: "more", icon: PLUS_ICON, label: "更多" });
  $("#bottom-nav").innerHTML = tabs.map((t) => `
    <button class="bnav-item" data-route="${t.route}" onclick="go('${t.route}')">
      <span class="bnav-icon">${t.icon}</span>
      <span class="bnav-label">${t.label}</span>
    </button>`).join("");
  ensureMobilePlatformSwipe();
}

async function renderMore(seq) {
  if (!state.user.is_admin) { replaceRoute("timeline"); return; }
  setPageTitle("更多");
  const adminGroup = NAV.find((g) => g.admin) || { items: [], subs: [] };
  const adminItems = [
    ...(adminGroup.items || []),
    ...(adminGroup.subs || []).flatMap((s) => s.items || []),
  ];
  $("#main").innerHTML = `
    <section class="section-panel">
      <div class="more-grid">
        ${adminItems.map((item) => `
          <button class="more-item" onclick="go('${item.route}')">
            <span class="more-icon">${item.icon}</span>
            <span class="more-label">${escapeHtml(item.label)}</span>
          </button>`).join("")}
      </div>
    </section>`;
}

let _feishuTimelineTimer = null;
let _feishuTimelineMediaUrls = [];
let _feishuTimelineMediaCache = new Map();
let _feishuTimelineState = null;
let _feishuMoreObserver = null;
let _feishuAssetObserver = null;
let _feishuSourceLoadSeq = 0;
let _feishuPreviewSeq = 0;
let _feishuPreviewTimer = null;
let _feishuPreview = { url: "", data: null };
let _imaReaderSeq = 0;

function isReportWatchableTag(tag) {
  const name = String(tag || "").trim();
  return !!name && !REPORT_WATCH_BLOCKED_TAGS.has(name);
}

function userKeywordSet() {
  return new Set((state.user?.keywords || []).map((k) => String(k || "").trim()).filter(Boolean));
}

function feishuTimelineAssetHtml(asset, mediaId, groupId) {
  if (!asset?.id) return "";
  const name = asset.name || (asset.kind === "image" ? "文档图片" : "文档附件");
  if (String(asset.mime || "").startsWith("image/") || asset.kind === "image") {
    return `<a class="post-img-link" href="#" onclick="event.preventDefault();openLightbox(this.querySelector('img'))" aria-label="查看${escapeHtml(name)}"><img src="data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=" data-feishu-asset="${escapeHtml(asset.id)}" data-media-id="${escapeHtml(mediaId)}" data-group-id="${escapeHtml(groupId)}" alt="${escapeHtml(name)}" loading="lazy"></a>`;
  }
  return `<button type="button" class="feishu-attachment" data-asset-id="${escapeHtml(asset.id)}" data-media-id="${escapeHtml(mediaId)}" data-group-id="${escapeHtml(groupId)}" data-name="${escapeHtml(name)}" onclick="downloadFeishuTimelineAsset(this)">${escapeHtml(name)}</button>`;
}

function feishuTimelineBlockHtml(block, mediaId, groupId, showSpeaker = true) {
  if (block.type === "table") {
    const rows = (block.rows || []).map((row, rowIndex) => {
      const tag = rowIndex === 0 ? "th" : "td";
      return `<tr>${(row || []).map((cell) => `<${tag}>${escapeHtml(cell?.text || "").replace(/\n/g, "<br>")}${(cell?.assets || []).map((asset) => feishuTimelineAssetHtml(asset, mediaId, groupId)).join("")}</${tag}>`).join("")}</tr>`;
    }).join("");
    return rows ? `<div class="feishu-entry-table" role="region" aria-label="文档表格" tabindex="0"><table><tbody>${rows}</tbody></table></div>` : "";
  }
  const speaker = String(block.speaker || "");
  const reply = String(block.reply_to || "");
  const text = String(block.text || "");
  const identity = speaker && showSpeaker
    ? `<div class="feishu-entry-speaker">${feishuSpeakerAvatarHtml(speaker)}<strong>${escapeHtml(feishuSourceDisplay(speaker).label)}</strong>${reply ? `<span class="feishu-entry-reply-to">↪ 回复 @${escapeHtml(reply)}</span>` : ""}</div>`
    : "";
  const assets = (block.assets || []).filter((asset) => asset && asset.id);
  const assetHtml = assets.length ? `<div class="post-images feishu-entry-assets">${assets.map((asset) => feishuTimelineAssetHtml(asset, mediaId, groupId)).join("")}</div>` : "";
  return `<div class="feishu-entry-block${speaker ? " has-speaker" : ""}${reply ? " is-reply" : ""}">${identity}${text ? `<p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>` : ""}${assetHtml}</div>`;
}

function feishuEntryAuthor(entry) {
  const blocks = Array.isArray(entry?.blocks) ? entry.blocks : [];
  const speakers = [...new Set(blocks.map((block) => String(block?.speaker || "").trim()).filter(Boolean))];
  if (speakers.length !== 1 || blocks.some((block) => String(block?.reply_to || "").trim())) return "";
  return speakers[0];
}

function feishuBlockHasContent(block) {
  if (!block) return false;
  if (block.type === "table") {
    return (block.rows || []).some((row) => (row || []).some((cell) => String(cell?.text || "").trim() || (cell?.assets || []).some((asset) => asset?.id)));
  }
  const text = String(block.text || "").trim();
  if ((block.assets || []).some((asset) => asset?.id)) return true;
  if (!text) return false;
  if (text === "收起") return false;
  if (/^\d+日无更新$/.test(text)) return false;
  return true;
}

function feishuEntryHasContent(entry) {
  return (entry?.blocks || []).some(feishuBlockHasContent);
}

const FEISHU_SOURCE_DISPLAY = {
  "K神-2026": { label: "杨康平", avatar: "/feishu-yang.png?v=1" },
  "杨康平": { label: "杨康平", avatar: "/feishu-yang.png?v=1" },
  "Q神-档案库": { label: "失业期神", avatar: "/feishu-shiye.png?v=1" },
  "Q神": { label: "失业期神", avatar: "/feishu-shiye.png?v=1" },
  "失业期神": { label: "失业期神", avatar: "/feishu-shiye.png?v=1" },
};

function feishuSourceDisplay(title) {
  const raw = String(title || "").trim();
  return FEISHU_SOURCE_DISPLAY[raw] || { label: raw, avatar: "" };
}

function feishuSpeakerAvatarHtml(name) {
  const display = feishuSourceDisplay(name);
  if (display.avatar) return `<img class="feishu-speaker-avatar" src="${escapeHtml(display.avatar)}" alt="" loading="lazy">`;
  // ponytail: 未建映射的新发言人掉回首字色块，不断档
  return `<span class="feishu-speaker-avatar feishu-speaker-fallback" aria-hidden="true">${escapeHtml(display.label.slice(0, 1))}</span>`;
}

function feishuLiveItemHtml(entry, showSource) {
  const source = entry.source || {};
  const author = feishuEntryAuthor(entry);
  const sourceLabel = showSource && source.title ? `<div class="feishu-live-source">${escapeHtml(feishuSourceDisplay(source.title).label)}</div>` : "";
  const speaker = author ? `<div class="feishu-live-speaker">${feishuSpeakerAvatarHtml(author)}<strong>${escapeHtml(feishuSourceDisplay(author).label)}</strong><time datetime="${escapeHtml(entry.timestamp || "")}">${escapeHtml(entry.time || "")}</time></div>` : "";
  const blocks = (entry.blocks || []).filter(feishuBlockHasContent).map((block) => feishuTimelineBlockHtml(block, source.media_id || "", source.group_id || "", !author)).join("");
  return `<article class="live-item" data-entry-id="${escapeHtml(entry.id || "")}">
    <div class="live-main">${speaker}${sourceLabel}<div class="live-body">${blocks}</div></div>
  </article>`;
}

function feishuTimelineEntriesHtml(entries, showSource) {
  const visible = (entries || []).filter(feishuEntryHasContent);
  if (!visible.length) return emptyState("这个范围内还没有时间线记录");
  const grouped = [];
  for (const entry of visible) {
    const day = String(entry.day || String(entry.timestamp || "").slice(0, 10));
    if (!grouped.length || grouped.at(-1).day !== day) grouped.push({ day, items: [] });
    grouped.at(-1).items.push(entry);
  }
  return grouped.map((group) => `
    <div class="tl-group live-group" id="feishu-day-${escapeHtml(group.day)}">
      <div class="tl-group-head"><span>${escapeHtml(fmtImaDay(group.day) || group.day)}</span></div>
      <div class="live-feed">${group.items.map((entry) => feishuLiveItemHtml(entry, showSource)).join("")}</div>
    </div>`).join("");
}

function renderFeishuTimelineView() {
  const host = $("#feishu-timeline-body");
  if (!host || !_feishuTimelineState) return;
  const state = _feishuTimelineState;
  const { data, selectedGroup } = state;
  const raw = selectedGroup
    ? (data.entries || []).filter((entry) => entry.source?.group_id === selectedGroup)
    : (data.entries || []);
  const entries = raw.filter(feishuEntryHasContent);
  const fab = $("#feishu-latest-fab");
  if (fab) fab.textContent = "回到最新";
  updateFeishuTimelineToolbar();
  updateFeishuTimelineHeader();
  if (state.loading && !entries.length) {
    host.innerHTML = '<p class="ima-reader-status" role="status">正在载入时间线…</p>';
    renderFeishuTimelineDates([]);
    observeFeishuTimelineMore();
    return;
  }
  const showSourceLabels = !selectedGroup && (data.sources || []).length > 1;
  host.innerHTML = `${feishuTimelineEntriesHtml(entries, showSourceLabels)}${feishuTimelineMoreHtml()}`;
  loadFeishuTimelineImages();
  renderFeishuTimelineDates(entries);
  observeFeishuTimelineMore();
  toggleFeishuLatestFab();
}

function renderFeishuTimelineDates(entries) {
  const nav = $("#feishu-date-nav");
  if (!nav) return;
  const days = [...new Set((entries || []).map((entry) => entry.day).filter(Boolean))];
  nav.innerHTML = days.map((day) => `<a href="#feishu-day-${escapeHtml(day)}">${escapeHtml(fmtImaDay(day) || day)}</a>`).join("");
  const select = $("#feishu-date-select");
  if (select) select.innerHTML = `<option value="">跳到日期</option>${days.map((day) => `<option value="${escapeHtml(day)}">${escapeHtml(fmtImaDay(day) || day)}</option>`).join("")}`;
}

function feishuTimelineRequestPath(state, before = "") {
  const params = new URLSearchParams({ order: "latest" });
  params.set("window_days", "7");
  if (state.selectedGroup) params.set("group", state.selectedGroup);
  if (before) params.set("before", before);
  return `/api/ima-documents/timeline/all?${params.toString()}`;
}

function mergeFeishuTimelineEntries(current, incoming) {
  const seen = new Set(current.map((entry) => String(entry.id || "")));
  return [...current, ...incoming.filter((entry) => {
    const id = String(entry.id || "");
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  })];
}

function feishuTimelineMoreHtml() {
  const state = _feishuTimelineState;
  if (!state || (!state.hasMore && !state.error)) return "";
  const label = state.loading ? "正在加载…" : state.error ? "重试" : "加载更早";
  const error = state.error ? `<p class="feishu-timeline-load-error" role="alert">${escapeHtml(state.error)}</p>` : "";
  return `<div class="feishu-timeline-more feishu-timeline-sentinel"><button type="button" class="btn-normal" onclick="loadMoreFeishuTimeline()"${state.loading ? " disabled" : ""}>${label}</button>${error}</div>`;
}

async function loadFeishuTimelinePage(reset = false) {
  const current = _feishuTimelineState;
  if (!current || current.loading) return false;
  const before = reset ? "" : current.nextCursor;
  if (reset) revokeFeishuTimelineMediaUrls();
  const requestState = {
    ...current,
    loading: true,
    error: "",
    nextCursor: reset ? "" : current.nextCursor,
    hasMore: reset ? false : current.hasMore,
    data: reset ? { ...current.data, entries: [], notices: [] } : current.data,
  };
  _feishuTimelineState = requestState;
  renderFeishuTimelineView();
  try {
    const data = await api(feishuTimelineRequestPath(requestState, before));
    if (!routeStillActive(requestState.seq) || requestState.readerSeq !== _imaReaderSeq || _feishuTimelineState !== requestState) return false;
    _feishuTimelineState = {
      ...requestState,
      data: {
        ...data,
        entries: reset ? (data.entries || []) : mergeFeishuTimelineEntries(requestState.data.entries || [], data.entries || []),
        notices: reset ? (data.notices || []) : (requestState.data.notices || []),
      },
      nextCursor: String(data.next_cursor || ""),
      hasMore: !!data.has_more,
      loading: false,
      error: "",
    };
    renderFeishuTimelineView();
    return true;
  } catch (err) {
    if (!routeStillActive(requestState.seq) || requestState.readerSeq !== _imaReaderSeq || _feishuTimelineState !== requestState) return false;
    _feishuTimelineState = { ...requestState, loading: false, error: err.message || "时间线加载失败" };
    renderFeishuTimelineView();
    return false;
  }
}

async function loadMoreFeishuTimeline() {
  const state = _feishuTimelineState;
  if (!state || state.loading || (!state.hasMore && !state.error)) return;
  await loadFeishuTimelinePage(false);
}

function observeFeishuTimelineMore() {
  _feishuMoreObserver?.disconnect();
  _feishuMoreObserver = null;
  const host = $("#feishu-timeline-body");
  const sentinel = host?.querySelector(".feishu-timeline-sentinel");
  if (!host || !sentinel || typeof IntersectionObserver !== "function") return;
  _feishuMoreObserver = new IntersectionObserver((items) => {
    if (!_feishuTimelineState || _feishuTimelineState.loading) return;
    if (items.some((item) => item.isIntersecting)) loadMoreFeishuTimeline();
  }, { root: host, rootMargin: "480px 0px" });
  _feishuMoreObserver.observe(sentinel);
}

async function selectFeishuTimelineSource(groupId) {
  if (!_feishuTimelineState || _feishuTimelineState.loading) return;
  const current = _feishuTimelineState;
  const selectedGroup = String(groupId || "");
  if (selectedGroup === current.selectedGroup) return;
  _feishuTimelineState = {
    ...current,
    selectedGroup,
    data: { ...current.data, entries: [], notices: [] },
    nextCursor: "",
    hasMore: false,
    error: "",
  };
  updateFeishuTimelineToolbar();
  updateFeishuTimelineHeader();
  updateFeishuTimelineRoute();
  const loaded = await loadFeishuTimelinePage(true);
  if (!loaded && routeStillActive(current.seq) && current.readerSeq === _imaReaderSeq && _feishuTimelineState?.selectedGroup === selectedGroup) {
    const message = _feishuTimelineState.error || "来源切换失败";
    _feishuTimelineState = current;
    updateFeishuTimelineToolbar();
    updateFeishuTimelineHeader();
    updateFeishuTimelineRoute();
    renderFeishuTimelineView();
    flash(message, "error");
  }
}

function updateFeishuTimelineToolbar() {
  const host = $("#feishu-timeline-toolbar");
  if (!host || !_feishuTimelineState) return;
  const selected = String(_feishuTimelineState.selectedGroup || "");
  const pills = host.querySelectorAll(".feishu-source-pills .tl-pill");
  if (pills.length) {
    pills.forEach((btn) => {
      const on = String(btn.dataset.group || "") === selected;
      btn.classList.toggle("selected", on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });
  } else {
    renderFeishuTimelineToolbar();
  }
}

function updateFeishuTimelineHeader() {
  if (!_feishuTimelineState) return;
  const { selectedGroup, data } = _feishuTimelineState;
  const sources = data?.sources || [];
  let title = "";
  let sourceUrl = "";
  if (selectedGroup) {
    const matched = sources.find((s) => String(s.group_id || "") === selectedGroup);
    title = feishuSourceDisplay(matched?.title || selectedGroup).label;
    sourceUrl = matched?.canonical_url || "";
  } else if (sources.length === 1) {
    title = feishuSourceDisplay(sources[0]?.title || "").label;
    sourceUrl = sources[0]?.canonical_url || "";
  } else {
    title = "全部时间线";
  }
  const titleEl = $(".ima-reader--feishu .ima-reader-title");
  if (titleEl) titleEl.textContent = title;
  setPageTitle(title);
  const openLink = $(".ima-reader--feishu .ima-reader-actions a[data-feishu-canonical]");
  if (openLink) {
    if (sourceUrl) {
      openLink.href = sourceUrl;
      openLink.removeAttribute("hidden");
    } else {
      openLink.setAttribute("hidden", "");
    }
  }
}

function updateFeishuTimelineRoute() {
  if (!_feishuTimelineState) return;
  const { selectedGroup, data, mediaId } = _feishuTimelineState;
  const sources = data?.sources || [];
  if (selectedGroup) {
    const matched = sources.find((s) => String(s.group_id || "") === selectedGroup);
    const targetMediaId = matched?.media_id || mediaId;
    if (targetMediaId) {
      replaceImaDocumentsRoute(imaDocumentReaderRoute(targetMediaId, selectedGroup));
    }
  } else {
    const targetMediaId = mediaId || sources[0]?.media_id;
    if (targetMediaId) {
      replaceImaDocumentsRoute(imaDocumentReaderRoute(targetMediaId, ""));
    }
  }
}

function jumpFeishuTimelineDay(day) {
  if (!day) return;
  document.getElementById(`feishu-day-${day}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function fetchFeishuTimelineAsset(img) {
  const seq = routeRenderSeq;
  const readerSeq = _imaReaderSeq;
  img.dataset.feishuLoading = "1";
  const mediaId = img.dataset.mediaId || "";
  const groupId = img.dataset.groupId || "";
  const assetId = img.dataset.feishuAsset || "";
  const cacheKey = `${mediaId}|${groupId}|${assetId}`;
  const cached = _feishuTimelineMediaCache.get(cacheKey);
  if (cached) {
    img.src = cached;
    return Promise.resolve();
  }
  const query = groupId ? `?group=${encodeURIComponent(groupId)}` : "";
  return apiBlob(`/api/ima-documents/${encodeURIComponent(mediaId)}/assets/${encodeURIComponent(assetId)}${query}`)
    .then((blob) => {
      if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq || !img.isConnected) return;
      const url = URL.createObjectURL(blob);
      _feishuTimelineMediaUrls.push(url);
      _feishuTimelineMediaCache.set(cacheKey, url);
      img.src = url;
    })
    .catch(() => {
      const link = img.closest(".post-img-link");
      if (link) link.remove();
      else if (img.isConnected) img.remove();
    });
}

function loadFeishuTimelineImages() {
  _feishuAssetObserver?.disconnect();
  _feishuAssetObserver = null;
  const images = [...document.querySelectorAll("img[data-feishu-asset]:not([data-feishu-loading])")];
  if (!images.length) return;
  if (typeof IntersectionObserver !== "function") {
    images.forEach((img) => fetchFeishuTimelineAsset(img));
    return;
  }
  _feishuAssetObserver = new IntersectionObserver((items, observer) => {
    for (const item of items) {
      if (!item.isIntersecting) continue;
      observer.unobserve(item.target);
      fetchFeishuTimelineAsset(item.target);
    }
  }, { rootMargin: "600px 0px" });
  images.forEach((img) => _feishuAssetObserver.observe(img));
}

async function downloadFeishuTimelineAsset(button) {
  button.disabled = true;
  const query = button.dataset.groupId ? `?group=${encodeURIComponent(button.dataset.groupId)}` : "";
  try {
    const blob = await apiBlob(`/api/ima-documents/${encodeURIComponent(button.dataset.mediaId)}/assets/${encodeURIComponent(button.dataset.assetId)}${query}`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = button.dataset.name || "attachment";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (err) {
    flash(err.message || "附件下载失败", "error");
  } finally {
    button.disabled = false;
  }
}

async function loadFeishuTimeline(item, seq, readerSeq) {
  const query = routeQuery();
  const selectedGroup = query.has("doc_group") ? (query.get("doc_group") || "") : (item.group_id || "");
  const requestState = {
    mediaId: item.media_id || "",
    selectedGroup,
    order: "latest",
    seq,
    readerSeq,
  };
  const data = await api(feishuTimelineRequestPath(requestState));
  if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq) return;
  _feishuTimelineState = {
    data,
    ...requestState,
    baseline: String(item.downloaded_at || ""),
    nextCursor: String(data.next_cursor || ""),
    hasMore: !!data.has_more,
    loading: false,
    error: "",
  };
  const panel = $("#ima-document-panel");
  if (!panel) return;
  panel.innerHTML = `<div class="feishu-timeline-layout"><main id="feishu-timeline-body" class="feishu-timeline-body"></main><nav id="feishu-date-nav" class="feishu-date-nav" aria-label="日期目录"></nav></div><button type="button" id="feishu-latest-fab" class="feishu-latest-fab" onclick="jumpFeishuTimelineLatest()">回到最新</button>`;
  renderFeishuTimelineToolbar();
  updateFeishuTimelineHeader();
  const body = $("#feishu-timeline-body");
  if (body) body.onscroll = () => toggleFeishuLatestFab();
  renderFeishuTimelineView();
  _feishuTimelineTimer = setTimeout(() => checkFeishuTimelineUpdate(item.media_id, item.group_id, _feishuTimelineState.baseline, seq, readerSeq), 60000);
}

function feishuSourcePillsHtml(sources, selectedGroup, target = "timeline") {
  const selected = String(selectedGroup || "");
  const items = sources.length > 1 ? [{ group_id: "", title: "全部" }, ...sources] : sources;
  if (!items.length) return "";
  return `<div class="tl-pills feishu-source-pills" role="radiogroup" aria-label="来源">${items.map((source) => {
    const id = String(source.group_id || "");
    const display = feishuSourceDisplay(source.title);
    const on = id === selected;
    const img = display.avatar ? `<img class="feishu-source-avatar" src="${escapeHtml(display.avatar)}" alt="">` : "";
    return `<button type="button" class="tl-pill${on ? " selected" : ""}${img ? " has-avatar" : ""}" role="radio" aria-checked="${on}" data-group="${escapeHtml(id)}" data-source-target="${target}" aria-label="${escapeHtml(display.label)}" onclick="selectFeishuSource(this)">${img}<span>${escapeHtml(display.label)}</span></button>`;
  }).join("")}</div>`;
}

function feishuTimelineToolbarHtml() {
  const state = _feishuTimelineState || {};
  const selectedGroup = state.selectedGroup || "";
  const sources = state.data?.sources || [];
  return `
    ${feishuSourcePillsHtml(sources, selectedGroup)}
    <label class="feishu-date-badge">${FEISHU_DATE_ICON}<select id="feishu-date-select" class="feishu-date-select" aria-label="跳到日期" onchange="jumpFeishuTimelineDay(this.value)"></select></label>`;
}

function renderFeishuTimelineToolbar() {
  const host = $("#feishu-timeline-toolbar");
  if (host && _feishuTimelineState) host.innerHTML = feishuTimelineToolbarHtml();
}

function toggleFeishuLatestFab() {
  const host = $("#feishu-timeline-body");
  const fab = $("#feishu-latest-fab");
  if (!host || !fab) return;
  fab.classList.toggle("is-visible", host.scrollTop > host.clientHeight * 1.5);
}

function jumpFeishuTimelineLatest() {
  const host = $("#feishu-timeline-body");
  if (!host) return;
  host.scrollTo({ top: 0, behavior: "smooth" });
  const fab = $("#feishu-latest-fab");
  if (fab) fab.classList.remove("is-visible");
}

function feishuAnchorEntry(host) {
  const hostTop = host.getBoundingClientRect().top;
  for (const el of host.querySelectorAll("[data-entry-id]")) {
    const rect = el.getBoundingClientRect();
    if (rect.bottom > hostTop + 4) return { id: el.dataset.entryId, delta: Math.max(0, rect.top - hostTop) };
  }
  return null;
}

function feishuRestoreEntry(host, anchor, fallbackTop) {
  if (anchor?.id) {
    const el = host.querySelector(`[data-entry-id="${CSS.escape(anchor.id)}"]`);
    if (el) {
      host.scrollTop = Math.max(0, el.offsetTop - anchor.delta);
      return;
    }
  }
  host.scrollTop = fallbackTop || 0;
}

function feishuTimelineCursorFromEntry(entry) {
  const raw = JSON.stringify({
    timestamp: String(entry?.timestamp || ""),
    id: String(entry?.id || ""),
  });
  const bytes = new TextEncoder().encode(raw);
  let bin = "";
  bytes.forEach((byte) => { bin += String.fromCharCode(byte); });
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function feishuTimelineUpdatePath(state) {
  return feishuTimelineRequestPath(state);
}

async function applyFeishuTimelineUpdate(button) {
  const current = _feishuTimelineState;
  const host = $("#feishu-timeline-body");
  const mediaId = button?.dataset?.mediaId || "";
  const groupId = button?.dataset?.groupId || "";
  if (!current || !host || !mediaId || current.loading) return;
  button.disabled = true;
  try {
    const metaPath = `/api/ima-documents/${encodeURIComponent(mediaId)}${groupId ? `?group=${encodeURIComponent(groupId)}` : ""}`;
    const [fresh, meta] = await Promise.all([
      api(feishuTimelineUpdatePath(current)),
      api(metaPath),
    ]);
    if (!routeStillActive(current.seq) || current.readerSeq !== _imaReaderSeq) return;
    const existing = new Set((current.data.entries || []).map((entry) => String(entry.id || "")));
    const added = (fresh.entries || []).filter((entry) => String(entry.id || "") && !existing.has(String(entry.id)));
    const anchor = feishuAnchorEntry(host);
    const scrollTop = host.scrollTop;
    _feishuTimelineState = {
      ...current,
      baseline: String(meta.downloaded_at || current.baseline || ""),
      data: {
        ...current.data,
        entries: [...added, ...(current.data.entries || [])],
      },
    };
    button.remove();
    renderFeishuTimelineView();
    feishuRestoreEntry(host, anchor, scrollTop);
    flash(added.length ? `已载入 ${added.length} 条新内容` : "已是最新内容");
    _feishuTimelineTimer = setTimeout(() => checkFeishuTimelineUpdate(mediaId, groupId, _feishuTimelineState.baseline, current.seq, current.readerSeq), 60000);
  } catch (err) {
    if (button.isConnected) button.disabled = false;
    flash(err.message || "载入新内容失败", "error");
  }
}

async function checkFeishuTimelineUpdate(mediaId, groupId, baseline, seq, readerSeq) {
  try {
    const item = await api(`/api/ima-documents/${encodeURIComponent(mediaId)}?group=${encodeURIComponent(groupId)}`);
    if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq) return;
    const state = _feishuTimelineState;
    const known = state && state.seq === seq && state.readerSeq === readerSeq
      ? String(state.baseline ?? baseline)
      : String(baseline);
    if (String(item.downloaded_at || "") !== known) {
      const panel = $("#ima-document-panel");
      if (panel && !$("#feishu-new-content")) panel.insertAdjacentHTML("afterbegin", `<button type="button" id="feishu-new-content" class="feishu-new-content" data-media-id="${escapeHtml(mediaId)}" data-group-id="${escapeHtml(groupId)}" onclick="applyFeishuTimelineUpdate(this)">有新内容，点击载入</button>`);
      return;
    }
  } catch { /* 保持 last-good 阅读 */ }
  if (routeStillActive(seq) && readerSeq === _imaReaderSeq) {
    _feishuTimelineTimer = setTimeout(() => checkFeishuTimelineUpdate(mediaId, groupId, baseline, seq, readerSeq), 60000);
  }
}

async function checkUpdate() {
  try {
    const v = await api("/api/version");
    if (v.current && v.current !== APP_VERSION) {
      const refreshKey = `dav_version_refresh_${v.current}`;
      if (!sessionStorage.getItem(refreshKey)) {
        sessionStorage.setItem(refreshKey, "1");
        location.reload();
        return;
      }
    }
    const link = $("#sidebar-gh-link");
    const meta = $("#sidebar-version");
    if (!link || !meta) return;
    // 始终显示服务端返回的当前版本，避免本地硬编码版本过期
    meta.innerHTML = `v${escapeHtml(v.current)}`;
    if (v.update_available && v.latest) {
      link.classList.add("has-update");
      meta.innerHTML += ` <a class="sidebar-update" href="${escapeHtml(v.url)}" target="_blank" rel="noopener" title="有新版本">↑ ${escapeHtml(v.latest)}</a>`;
    }
  } catch {
    /* 更新检查失败不打扰，保留本地硬编码版本兜底 */
  }
}

function ensureVersionRefreshCheck() {
  if (ensureVersionRefreshCheck.bound) return;
  ensureVersionRefreshCheck.bound = true;
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") checkUpdate();
  });
  window.addEventListener("focus", checkUpdate);
}

function renderTopbar(user) {
  $("#topbar-user").innerHTML = `
    <button class="theme-toggle-btn" id="theme-toggle-btn" onclick="cycleTheme()" aria-label="切换主题" title="切换主题"></button>
    <div class="user-chip">
      <div class="user-avatar">${escapeHtml(avatarText(user.username))}</div>
      <div class="user-meta">
        <span class="user-name">${escapeHtml(user.username)}</span>
        <span class="user-role">${user.is_admin ? "管理员" : "订阅用户"}</span>
      </div>
    </div>
    <button class="topbar-logout" onclick="logout()">退出</button>`;
  updateThemeToggleIcon();
}

function setPageTitle(title, back = false, backRoute = "", backLabel = "") {
  $("#page-title").textContent = title;
  $("#btn-back").classList.toggle("hidden", !back);
  $("#btn-back").setAttribute("aria-label", backLabel || "返回上一页");
  state.pageBackRoute = back && backRoute ? String(backRoute) : "";
}

function emptyState(text, actionHtml = "") {
  return `<div class="empty">${escapeHtml(text)}${actionHtml}</div>`;
}

function homePanelHasFilters() {
  return !!(state.homeCategory || state.homeFavorite || (isMobileTimelineFilter() && (state.homeQ || state.homeSubscribed)));
}

function homeSubscribedToggleHtml() {
  return `<button type="button" id="home-sub-toggle" class="fav-toggle ${state.homeSubscribed ? "fav-on" : ""}" aria-pressed="${state.homeSubscribed}" onclick="toggleHomeSubscribed()">已订阅</button>`;
}

function homeScopeTogglesHtml(includeSubscribed) {
  return `<div class="home-scope-filters">
    ${includeSubscribed ? `<label class="switch home-scope-switch">
      <input type="checkbox" id="home-sub-toggle" ${state.homeSubscribed ? "checked" : ""} onchange="toggleHomeSubscribed()">
      <span class="track"></span><span>只看已订阅</span>
    </label>` : ""}
    <label class="switch home-scope-switch">
      <input type="checkbox" id="home-fav-toggle" ${state.homeFavorite ? "checked" : ""} onchange="toggleHomeFavorite()">
      <span class="track"></span><span>只看特别关注</span>
    </label>
  </div>`;
}

function homeFilterToggleHtml() {
  return `<button type="button" id="home-filter-toggle" class="fav-toggle home-filter-toggle ${homePanelHasFilters() ? "has-filter" : ""}" aria-label="筛选" aria-expanded="false" aria-controls="home-filter-panel" onclick="homeToggleFilter()">${FILTER_ICON}</button>`;
}

function homeFilterPanelHtml(mobile) {
  return `<div class="home-filter-content" id="home-filter-panel" hidden>
    ${mobile ? `<div class="search-bar home-search-bar">
      ${SEARCH_ICON}
      <input id="home-search" placeholder="搜索昵称或 ID" value="${escapeHtml(state.homeQ || "")}" oninput="homeSearch(this.value)">
    </div>` : ""}
    <div class="home-cats" id="home-cats"></div>
    ${homeScopeTogglesHtml(mobile)}
    <div class="home-filter-actions">
      <button class="btn-ghost" onclick="homeResetFilters()">清除筛选</button>
    </div>
  </div>`;
}

function toggleHomeSubscribed() {
  state.homeSubscribed = !state.homeSubscribed;
  const toggle = $("#home-sub-toggle");
  if (toggle?.matches('input[type="checkbox"]')) {
    toggle.checked = state.homeSubscribed;
  } else if (toggle) {
    toggle.classList.toggle("fav-on", state.homeSubscribed);
    toggle.setAttribute("aria-pressed", String(state.homeSubscribed));
  }
  renderHomeList();
}

function toggleHomeFavorite() {
  state.homeFavorite = !state.homeFavorite;
  const toggle = $("#home-fav-toggle");
  if (toggle) toggle.checked = state.homeFavorite;
  renderHomeList();
}

function homeToggleFilter() {
  const panel = $("#home-filter-panel");
  const btn = $("#home-filter-toggle");
  if (!panel || !btn) return;
  const open = panel.hasAttribute("hidden");
  panel.toggleAttribute("hidden", !open);
  btn.setAttribute("aria-expanded", String(open));
}

function homeMobilePlatformsHtml() {
  return tlPlazaEntries().map(([p, label]) => {
    const short = platformShortLabel(p);
    return `
    <button class="tl-pill ${state.platform === p ? "selected" : ""}"
      data-platform="${p}" aria-label="${label}" title="${label}"
      role="radio" aria-checked="${state.platform === p}"
      onclick="homePickMobilePlatform('${p}')">
      ${PLATFORM_ICONS[p || ""]}<span>${short}</span>
    </button>`;
  }).join("");
}

async function homePickMobilePlatform(platform) {
  state.platform = platform;
  const platforms = $("#home-mobile-platforms");
  if (platforms) platforms.innerHTML = homeMobilePlatformsHtml();
  await loadHomeKols(routeRenderSeq);
}

async function homeResetFilters() {
  state.homeQ = state.homeCategory = state.platform = "";
  state.homeSubscribed = state.homeFavorite = false;
  await renderHome(routeRenderSeq);
}

let _homeMobileWatchBound = false;
function ensureHomeMobileWatch() {
  if (_homeMobileWatchBound) return;
  _homeMobileWatchBound = true;
  window.matchMedia("(max-width: 768px)").addEventListener("change", () => {
    if (routePath() === "home" && $(".home-panel") && $("#kol-list")) renderHome(++routeRenderSeq);
  });
}

// ---------- 订阅广场 ----------
async function renderHome(seq) {
  setPageTitle("订阅广场");
  ensurePlazaPlatformSelection();
  ensureHomeMobileWatch();
  let onboardingHtml = "";
  if (state.user && !state.user.subscription_count) {
    try {
      const recs = await api("/api/recommendations");
      if (routeStillActive(seq) && recs.length) {
        onboardingHtml = `
          <section class="section-panel">
            <header class="section-head"><div>
              <h2 class="section-title">欢迎！先订阅几位大V</h2>
              <p class="section-meta">以下是最热门的大V；订阅后新帖会自动推送到你绑定的渠道。</p>
            </div></header>
            <div class="row" style="gap:12px;flex-wrap:wrap">${recs.map((rec) => `
              <div class="kol-item" style="flex:1;min-width:230px">
                ${avatarHtml(rec.name, rec.avatar_url)}
                <a class="kol-info" href="/kol/${rec.id}">
                  <div class="base">
                    <span class="name">${escapeHtml(rec.name)}</span>
                    <span class="tag">${PLATFORM_LABELS[rec.platform] || escapeHtml(rec.platform)}</span>
                    ${rec.category_name ? `<span class="tag">${escapeHtml(rec.category_name)}</span>` : ""}
                  </div>
                  <div class="desc">${rec.subscriber_count} 人订阅</div>
                </a>
                <button class="btn-sub ${rec.subscribed ? "subscribed" : ""}" onclick="quickSubscribe(${rec.id}, this)">
                  ${rec.subscribed ? "✓ 已订阅" : "订阅"}
                </button>
              </div>`).join("")}
            </div>
            <p class="muted" style="margin-top:12px">也可以先去<a href="/settings">绑定推送渠道</a>，再回来订阅。</p>
          </section>`;
      }
    } catch {
      /* 推荐加载失败不阻塞页面 */
    }
  }
  if (!routeStillActive(seq)) return; // 已切走：不写旧首页的 DOM
  const mobileHome = isMobileTimelineFilter();
  $("#main").innerHTML = `
    ${onboardingHtml}
    <section class="section-panel home-panel">
      <header class="section-head home-head">
        <div>
          <h2 class="section-title">全部大V</h2>
          <p class="section-meta" id="catalog-meta">加载中…</p>
        </div>
        ${mobileHome ? `
          <div class="icon-badge-bar" id="home-mobile-bar">
            <div class="tl-pills" id="home-mobile-platforms" role="radiogroup" aria-label="平台">
              ${homeMobilePlatformsHtml()}
            </div>
            ${homeFilterToggleHtml()}
          </div>
          ${homeFilterPanelHtml(true)}` : `
          <div class="toolbar" style="margin-top:12px">
            <div class="search-bar" style="flex:1;min-width:220px">
              ${SEARCH_ICON}
              <input id="home-search" placeholder="搜索昵称或 ID，即时过滤" value="${escapeHtml(state.homeQ || "")}" oninput="homeSearch(this.value)">
            </div>
            <div class="platform-tabs" id="platform-tabs"></div>
            ${homeSubscribedToggleHtml()}
            ${homeFilterToggleHtml()}
          </div>
          ${homeFilterPanelHtml(false)}`}
      </header>
      ${state.user?.is_admin ? "" : `
        <div class="request-banner">
          <div class="request-banner-icon">${PLUS_ICON}</div>
          <div class="request-banner-copy">
            <div class="title">想关注的大V不在列表里？</div>
            <div class="desc">提交申请，管理员审批通过后自动上架并通知你</div>
          </div>
          <button class="btn-normal" onclick="go('search')">申请添加</button>
        </div>`}
      <div id="kol-list" class="kol-grid"></div>
    </section>`;
  renderPlatformTabs();
  await loadHomeKols(seq);
}

function renderPlatformTabs() {
  const tabs = $("#platform-tabs");
  if (tabs) tabs.innerHTML = tlPlazaEntries().map(([p]) => platformTabHTML(p, state.platform, "home")).join("");
}

function categoryChipsHtml() {
  const cats = [...new Set(state.catalog.map((k) => k.category_name || ""))].filter(Boolean).sort();
  const chip = (c, label) => `<button class="cat-chip ${state.homeCategory === c ? "selected" : ""}" data-cat="${escapeHtml(c)}" onclick="pickHomeCategory(this.dataset.cat)">${escapeHtml(label)}</button>`;
  return chip("", "全部分类") + cats.map((c) => chip(c, c)).join("");
}

function pickHomeCategory(cat) {
  state.homeCategory = cat;
  renderHomeList();
}

let _homeSearchTimer = null;
function homeSearch(v) {
  state.homeQ = v.trim();
  clearTimeout(_homeSearchTimer);
  _homeSearchTimer = setTimeout(renderHomeList, 200);
}

function homeFilteredKols() {
  const q = state.homeQ.toLowerCase();
  return state.catalog.filter((k) => {
    if (state.homeSubscribed && !k.subscribed) return false;
    if (state.homeFavorite && !k.favorite) return false;
    if (state.homeCategory && k.category_name !== state.homeCategory) return false;
    if (!q) return true;
    return (k.name || "").toLowerCase().includes(q) || (k.external_id || "").toLowerCase().includes(q);
  });
}

function renderHomeList() {
  $("#home-filter-toggle")?.classList.toggle("has-filter", homePanelHasFilters());
  const cats = $("#home-cats");
  if (cats) cats.innerHTML = categoryChipsHtml();
  const meta = $("#catalog-meta");
  if (meta) meta.textContent = `共 ${state.catalog.length} 位大V · 已订阅 ${state.catalog.filter((k) => k.subscribed).length} 位`;
  const list = homeFilteredKols();
  const target = $("#kol-list");
  if (!target) return; // 已离开首页（如正在加载时切走），不写不存在的 DOM
  target.innerHTML = list.length
    ? groupedKolCards(list)
    : emptyState(state.catalog.length ? "没有匹配的大V" : "暂无大V，管理员可在管理后台添加");
}

function platformTabHTML(p, current, target) {
  const label = p ? PLATFORM_LABELS[p] : "全部";
  const short = platformShortLabel(p);
  return `<button class="platform-tab ${p === current ? "selected" : ""}" data-platform="${p}" data-platform-target="${target}"
    title="${label}" aria-label="${label}"
    onclick="selectPlatformTab(this)">${PLATFORM_ICONS[p || ""]}<span class="pt-label">${short}</span></button>`;
}

let _homeKolsSeq = 0;
async function loadHomeKols(routeSeq) {
  const seq = ++_homeKolsSeq;
  let kols;
  try {
    const params = state.platform ? `?platform=${state.platform}` : "";
    kols = await api(`/api/catalog${params}`);
  } catch (err) {
    if (seq !== _homeKolsSeq || !routeStillActive(routeSeq)) return;
    const list = $("#kol-list");
    if (list) list.innerHTML = emptyState("加载失败: " + err.message);
    return;
  }
  // 平台已切换或已离开首页：不写全局状态也不写 DOM，避免旧目录覆盖当前页面
  if (seq !== _homeKolsSeq || !routeStillActive(routeSeq)) return;
  state.catalog = kols;
  renderHomeList();
}

function groupedKolCards(kols) {
  const groups = {};
  for (const kol of kols) {
    const key = kol.category_name || "";
    (groups[key] = groups[key] || []).push(kol);
  }
  return Object.entries(groups)
    .map(([name, items]) => `
      <div class="group-head">
        <span style="font-weight:600;color:var(--color-text-strong)">${escapeHtml(name || "未分类")}</span>
        <span class="g-count">${items.length} 位</span>
      </div>
      ${items.map(kolCard).join("")}`)
    .join("");
}

async function switchPlatform(platform) {
  state.platform = platform;
  renderPlatformTabs();
  await loadHomeKols(routeRenderSeq);
}

function kolCard(kol) {
  const tags = [];
  tags.push(`<span class="tag">${PLATFORM_LABELS[kol.platform] || escapeHtml(kol.platform)}</span>`);
  if (kol.category_name) tags.push(`<span class="tag">${escapeHtml(kol.category_name)}</span>`);
  if (kol.platform === "combination" && kol.quote && kol.quote.day_percent_gain != null) {
    const gain = kol.quote.day_percent_gain;
    tags.push(`<span class="tag cube-day ${gain >= 0 ? "up" : "down"}">${gain >= 0 ? "+" : ""}${gain.toFixed(2)}%</span>`);
  }
  return `
    <div class="kol-card">
      <a class="kol-card-head" href="/kol/${kol.id}" title="查看${escapeHtml(kol.name)}的动态页" aria-label="查看${escapeHtml(kol.name)}的动态页">
        ${avatarHtml(kol.name, kol.avatar_url)}
        <div class="kol-card-info">
          <span class="name" title="${escapeHtml(kol.name)}">${escapeHtml(kol.name)}</span>
          ${tags.length ? `<div class="kol-card-meta">${tags.join("")}</div>` : ""}
          <div class="desc">外部 ID：${escapeHtml(kol.external_id)}${kol.enabled ? "" : " · 已停用"}</div>
        </div>
      </a>
      ${kol.subscribed && kol.platform === "xueqiu" ? `<div class="kol-card-subtype">${subTypeSwitchesHtml(kol.id, kol.subscribe_type || "post")}</div>` : ""}
      <div class="kol-card-actions">
        <button class="btn-sub ${kol.subscribed ? "subscribed" : ""}" onclick="toggleSubscribe(${kol.id}, this)">
          ${kol.subscribed ? "✓ 已订阅" : "订阅"}
        </button>
        ${kol.subscribed ? `<button class="fav-btn ${kol.favorite ? "fav-on" : ""}" onclick="toggleFavorite(${kol.id}, this)" title="特别关注：优先推送" aria-label="${kol.favorite ? "取消特别关注" : "设为特别关注"}">${STAR_SVG}</button>` : ""}
        ${kol.subscribed ? `<button class="fav-btn ${kol.secondary ? "sec-on" : "sec-off"}" onclick="toggleSecondary(${kol.id}, this)" title="次要：新帖合并进摘要推送（降频）" aria-label="${kol.secondary ? "取消次要" : "设为次要"}">${kol.secondary ? BELL_OFF_ICON : BELL_ICON}</button>` : ""}
        ${state.user?.is_admin ? `<button class="btn-sm danger kol-del" onclick="adminDeleteKolFromHome(${kol.id})" title="删除该大V" aria-label="删除该大V">${TRASH_ICON}</button>` : ""}
      </div>
    </div>`;
}

async function adminDeleteKolFromHome(kolId) {
  const kol = state.catalog.find((k) => k.id === kolId);
  if (!(await showConfirm(`确认删除该大V${kol ? `「${kol.name}」` : ""}？其订阅关系会一并移除。`))) return;
  try {
    await api(`/api/kols/${kolId}`, { method: "DELETE" });
    flash(`已删除「${kol ? kol.name : "该大V"}」`);
    await refreshKolsView(); // 按当前路由刷新，删除期间切走不会污染新页面
  } catch (err) {
    flash("删除失败: " + err.message, "error");
  }
}

async function toggleSubscribe(kolId, btn) {
  const kol = state.catalog.find((k) => k.id === kolId);
  if (kol?.subscribed && !(await showConfirm(`取消订阅「${kol.name}」？将不再推送其新动态。`))) return;
  try {
    const wasSubscribed = kol ? kol.subscribed : btn.classList.contains("subscribed");
    if (wasSubscribed) {
      await api(`/api/subscriptions/${kolId}`, { method: "DELETE" });
    } else {
      await api("/api/subscriptions", { method: "POST", body: JSON.stringify({ kol_id: kolId, type: "post" }) });
    }
    flash(`已${wasSubscribed ? "退订" : "订阅"}「${kol ? kol.name : "该大V"}」`);
    if (kol) kol.subscribed = !wasSubscribed;
    await refreshKolsView();
  } catch (err) {
    flash("操作失败: " + err.message, "error");
  }
}

async function toggleFavorite(kolId, btn) {
  const kol = state.catalog.find((k) => k.id === kolId);
  const next = !(kol ? kol.favorite : false);
  try {
    await api(`/api/subscriptions/${kolId}/favorite`, {
      method: "PUT",
      body: JSON.stringify({ favorite: next }),
    });
    if (kol) kol.favorite = next;
    if (btn) btn.classList.toggle("fav-on", next);
    flash(next ? "已加星标" : "已取消星标");
    if (isRoute("home")) renderHomeList();
  } catch (err) {
    flash("操作失败: " + err.message, "error");
  }
}

async function toggleSecondary(kolId, btn) {
  const kol = state.catalog.find((k) => k.id === kolId);
  const next = !(kol ? kol.secondary : false);
  try {
    await api(`/api/subscriptions/${kolId}/secondary`, {
      method: "PUT",
      body: JSON.stringify({ secondary: next }),
    });
    if (kol) kol.secondary = next;
    if (btn) btn.classList.toggle("sec-on", next);
    flash(next ? "已设为次要（降频推送）" : "已取消次要");
    if (isRoute("home")) renderHomeList();
  } catch (err) {
    flash("操作失败: " + err.message, "error");
  }
}

async function quickSubscribe(kolId, btn) {
  try {
    await api("/api/subscriptions", { method: "POST", body: JSON.stringify({ kol_id: kolId, type: "post" }) });
    btn.classList.add("subscribed");
    btn.textContent = "✓ 已订阅";
    btn.disabled = true;
    state.user.subscription_count = (state.user.subscription_count || 0) + 1;
    loadHomeKols(routeRenderSeq); // 订阅后重拉 catalog，已订阅置顶即时生效
  } catch (err) {
    flash("订阅失败: " + err.message, "error");
  }
}

async function refreshKolsView() {
  // 发起前捕获当前路由令牌；完成后再写 DOM，避免局部刷新覆盖已切走的新路由
  const seq = routeRenderSeq;
  if (isRoute("home")) await loadHomeKols(seq); // 重拉 catalog，已订阅置顶即时生效
  else if (isRoute("kol/")) await renderKolPage(Number(routePath().split("/")[1] || 0), seq);
  else if (isRoute("search")) doSearch(seq);
}

function subTypeSwitchesHtml(kolId, current) {
  const cur = current || "post";
  const postOn = cur !== "reply";
  const replyOn = cur !== "post";
  return `
    <div class="sub-type-switches" data-kol="${kolId}">
      <label class="sub-type-switch">
        <input type="checkbox" ${postOn ? "checked" : ""} onchange="setSubscribeType(${kolId}, this)">
        <span>帖子</span>
      </label>
      <label class="sub-type-switch">
        <input type="checkbox" ${replyOn ? "checked" : ""} onchange="setSubscribeType(${kolId}, this)">
        <span>回复</span>
      </label>
    </div>`;
}

async function setSubscribeType(kolId, input) {
  const box = input.closest(".sub-type-switches");
  const boxes = box.querySelectorAll('input[type="checkbox"]');
  const postOn = boxes[0].checked;
  const replyOn = boxes[1].checked;
  if (!postOn && !replyOn) {
    input.checked = true; // 至少保留一种类型；取消订阅请点「已订阅」主按钮
    flash("请至少保留一种订阅类型；取消订阅请点「已订阅」按钮", "error");
    return;
  }
  const type = postOn && replyOn ? "both" : postOn ? "post" : "reply";
  try {
    await api(`/api/subscriptions/${kolId}`, { method: "PUT", body: JSON.stringify({ type }) });
    const kol = state.catalog.find((k) => k.id === kolId);
    if (kol) {
      kol.subscribed = true;
      kol.subscribe_type = type;
    }
  } catch (err) {
    flash("切换订阅类型失败: " + err.message, "error");
    refreshKolsView();
  }
}

// ---------- 动态 ----------
let _tlSeq = 0;
const _tlPosts = [];
let _tlOffset = 0;
let _tlHasMore = true;
let _tlLoadingMore = false;
const _tlExpanded = new Set();
let _tlTags = null;
let _tlDynamicTags = [];
let _tlLatestId = 0;        // 当前已加载的最新帖 id，用于后台检测新帖
let _tlLoadedFilter = null; // 缓存列表对应的筛选条件快照
let _tlSavedScrollY = 0;    // 离开动态页时的滚动位置，切回时恢复
let _tlPendingNew = [];     // 轮询拉到的新帖（点提示条时直接插到列表顶部）
let _tlPendingLatestId = 0; // 已拉取的新帖中最新 id，轮询去重
let _tlRefreshing = false;  // 刷新锁：防止连点/并发 poll 重复插入新帖
let _tlPollTimer = null;    // 新帖轮询定时器
let _tlWideWatchBound = false; // 1280px 断点只绑一次，避免开关留在已隐藏的栏里

let _liveSeq = 0;
const _livePosts = [];
let _liveCursor = "";
let _liveHasMore = true;
let _liveLoadingMore = false;
let _liveLatestId = 0;
let _livePendingNew = [];
let _livePendingLatestId = 0;
let _liveSavedScrollY = 0;
let _liveClockTimer = null;
let _liveInflight = null;
let _feedLoadObserver = null;
let _feedLoadFallback = null;

function isLiveTimeline() {
  return state.timelineSource === "live";
}

function feedScrollY() {
  return isLiveTimeline() ? _liveSavedScrollY : _tlSavedScrollY;
}

function feedPosts() {
  return isLiveTimeline() ? _livePosts : _tlPosts;
}

function feedPendingNew() {
  return isLiveTimeline() ? _livePendingNew : _tlPendingNew;
}

// 按发布时间比较（旧 → 新），id 只作同秒 tie-break。
// 补历史/并发入库会让 id 顺序≠时间顺序：新帖判定与合并必须以 published_at 为准，
// 否则旧消息（新 id）会被当成新帖顶到时间线最上面。
function feedPubTimeMs(p) {
  const d = parsePublished(p.published_at);
  const t = d ? d.getTime() : NaN;
  return Number.isNaN(t) ? 0 : t;
}

function feedTimeAsc(a, b) {
  return feedPubTimeMs(a) - feedPubTimeMs(b) || a.id - b.id;
}

function feedNewestPost(posts) {
  return posts.reduce((acc, p) => (!acc || feedTimeAsc(acc, p) < 0 ? p : acc), null);
}

function renderFeed() {
  if (isLiveTimeline()) renderLiveFeed();
  else renderTimelineFeed();
}

function tlPersistSource() {
  try { sessionStorage.setItem(TL_SOURCE_KEY, state.timelineSource); } catch { /* */ }
}

function tlNewBadgeLabel() {
  return isLiveTimeline() ? "有新快讯" : "已发布";
}

function tlSyncNewBadgeMode() {
  const badge = $("#tl-new-badge");
  if (!badge) return;
  badge.classList.toggle("live-mode", isLiveTimeline());
  const label = badge.querySelector(".tl-new-badge-label");
  if (label) label.textContent = tlNewBadgeLabel();
}

function tlFilterKey() {
  return JSON.stringify([
    state.timelineQ || "", state.timelinePlatform || "",
    state.timelineCategory || "", state.timelineTag || "", state.timelineFavorite,
    state.timelineSecondary, state.timelineKolId || 0,
  ]);
}

// 生效筛选条件 → 可见 chip 列表：用户随时能看到自己被什么过滤着，逐个可移除
// label 直接存已转义文本（escapeHtml 在构造行完成，渲染处不再重复转义）
function tlPanelFilterOn() {
  return !!(state.timelineQ || state.timelineTag || state.timelineFavorite || state.timelineSecondary);
}

function tlActiveChips() {
  const chips = [];
  if (state.timelineFavorite) chips.push({ key: "favorite", label: "特别关注" });
  if (state.timelineSecondary) chips.push({ key: "secondary", label: "次要大V" });
  if (state.timelineQ) chips.push({ key: "q", label: `关键词：${escapeHtml(state.timelineQ)}` });
  if (state.timelineTag) chips.push({ key: "tag", label: `标签：${escapeHtml(state.timelineTag)}` });
  if (state.timelineKolId) {
    const kol = _tlKolRows.find((k) => k.id === state.timelineKolId);
    chips.push({ key: "kol", label: `大V：${escapeHtml(kol ? kol.name : `#${state.timelineKolId}`)}` });
  }
  return chips;
}

function tlSnapshotFilters() {
  return {
    timelinePlatform: state.timelinePlatform,
    timelineKolId: state.timelineKolId,
    timelineFavorite: state.timelineFavorite,
    timelineSecondary: state.timelineSecondary,
    timelineQ: state.timelineQ,
    timelineTag: state.timelineTag,
    timelineCategory: state.timelineCategory,
  };
}

function tlPaintViewToggles() {
  const fav = $("#timeline-fav-toggle");
  if (fav) {
    fav.classList.toggle("fav-on", state.timelineFavorite);
    fav.setAttribute("aria-pressed", String(state.timelineFavorite));
  }
  const sec = $("#timeline-secondary-toggle");
  if (sec) {
    sec.classList.toggle("fav-on", state.timelineSecondary);
    sec.setAttribute("aria-pressed", String(state.timelineSecondary));
    sec.innerHTML = `${state.timelineSecondary ? EYE_ICON : EYE_OFF_ICON} 次要大V`;
  }
}

function tlSyncFilterChrome() {
  const btn = $("#tl-filter-toggle");
  if (btn) btn.classList.toggle("has-filter", tlPanelFilterOn());
  tlSyncActiveChips();
}

function tlRestoreFilters(snap) {
  if (!snap) return;
  state.timelinePlatform = snap.timelinePlatform;
  state.timelineKolId = snap.timelineKolId || 0;
  state.timelineFavorite = snap.timelineFavorite;
  state.timelineSecondary = snap.timelineSecondary;
  state.timelineQ = snap.timelineQ;
  state.timelineTag = snap.timelineTag;
  state.timelineCategory = snap.timelineCategory;
  const q = $("#tl-q"); if (q) q.value = state.timelineQ || "";
  const tag = $("#tl-tag"); if (tag) tag.value = state.timelineTag || "";
  const pills = $("#tl-pills");
  if (pills) pills.innerHTML = tlPillsHtml();
  renderTlKolBar();
  tlPaintViewToggles();
  tlSyncFilterChrome();
}

function tlActiveChipsHtml() {
  const chips = tlActiveChips();
  if (!chips.length) return "";
  return `<div class="tl-active-chips">${chips.map((c) => `
    <span class="tl-active-chip">${c.label}<button class="tl-chip-x" onclick="tlRemoveFilter('${c.key}')" aria-label="移除${c.label}" title="移除该筛选">${X_ICON}</button></span>`).join("")}</div>`;
}

function tlRemoveFilter(key) {
  const revert = tlSnapshotFilters();
  if (key === "q") state.timelineQ = "";
  else if (key === "tag") {
    state.timelineTag = "";
    const tagSel = $("#tl-tag");
    if (tagSel) tagSel.value = "";
  } else if (key === "favorite") state.timelineFavorite = false;
  else if (key === "secondary") state.timelineSecondary = false;
  else if (key === "kol") { state.timelineKolId = 0; tlClearKolNewCounts(); }
  if (key === "kol") renderTlKolBar();
  tlPaintViewToggles();
  tlSyncFilterChrome();
  loadTimeline(true, routeRenderSeq, { revert });
  renderRailTags(_tlDynamicTags.slice(0, 8));
}

const TL_SKELETON = `<div class="tl-skeleton">${Array(4).fill(`
    <div class="tl-sk-item">
      <div class="tl-sk-avatar"></div>
      <div class="tl-sk-lines">
        <div class="tl-sk-line" style="width:42%"></div>
        <div class="tl-sk-line" style="width:96%"></div>
        <div class="tl-sk-line" style="width:74%"></div>
      </div>
    </div>`).join("")}
  </div>`;


function plazaVisibleSet() {
  const list = state.user && Array.isArray(state.user.plaza_platforms)
    ? state.user.plaza_platforms
    : PLATFORM_TABS.filter(Boolean);
  return new Set(list);
}

function timelineVisibleSet() {
  const list = state.user && Array.isArray(state.user.timeline_platforms)
    ? state.user.timeline_platforms
    : plazaVisibleSet();
  return new Set(list);
}

function tlPlatformEntries(vis) {
  return TL_PLATFORMS.filter(([p]) => !p || vis.has(p));
}

function tlPlazaEntries() {
  return tlPlatformEntries(plazaVisibleSet());
}

function tlTimelineEntries() {
  return tlPlatformEntries(timelineVisibleSet());
}

let _platSwipe = null;

function mobilePlatformSwipeIgnore(el) {
  return !!el.closest("a, button, input, select, textarea, .tl-pills, .tl-kolbar, .platform-tabs, .icon-badge-bar, .tl-filter-panel, .home-filter-content, .lightbox, .bottom-nav, .post-images");
}

function mobilePlatformSwipeSurface(el) {
  if (isLiveTimeline()) return null;
  if ($("#tl-feed-panel") && el.closest(".tl-main")) return "timeline";
  if ($("#home-mobile-platforms") && ($("#kol-list")?.contains(el) || el.closest(".home-panel"))) return "home";
  return null;
}

function mobilePlatformSwipeContext(surface) {
  if (surface === "timeline") return { current: () => state.timelinePlatform, apply: (p) => tlPickPlatform(p), entries: tlTimelineEntries };
  if (surface === "home") return { current: () => state.platform, apply: (p) => homePickMobilePlatform(p), entries: tlPlazaEntries };
  return null;
}

function mobileSwipeAdjacent(current, dir, entries) {
  const idx = entries.findIndex(([p]) => p === current);
  const next = idx + dir;
  if (idx < 0 || next < 0 || next >= entries.length) return null;
  return entries[next][0];
}

function onPlatSwipeStart(e) {
  if (!isMobileTimelineFilter() || e.touches.length !== 1) {
    _platSwipe = null;
    return;
  }
  const t = e.target;
  if (!(t instanceof Element) || mobilePlatformSwipeIgnore(t)) {
    _platSwipe = null;
    return;
  }
  const surface = mobilePlatformSwipeSurface(t);
  if (!surface) {
    _platSwipe = null;
    return;
  }
  _platSwipe = { x: e.touches[0].clientX, y: e.touches[0].clientY, surface };
}

function onPlatSwipeEnd(e) {
  if (!_platSwipe) return;
  const start = _platSwipe;
  _platSwipe = null;
  if (!isMobileTimelineFilter()) return;
  const dx = e.changedTouches[0].clientX - start.x;
  const dy = e.changedTouches[0].clientY - start.y;
  if (Math.abs(dx) < 56 || Math.abs(dx) < Math.abs(dy) * 1.4) return;
  const ctx = mobilePlatformSwipeContext(start.surface);
  if (!ctx) return;
  const next = mobileSwipeAdjacent(ctx.current(), dx < 0 ? 1 : -1, ctx.entries());
  if (next === null) return;
  ctx.apply(next);
}

function ensureMobilePlatformSwipe() {
  if (ensureMobilePlatformSwipe.bound) return;
  ensureMobilePlatformSwipe.bound = true;
  document.addEventListener("touchstart", onPlatSwipeStart, { passive: true });
  document.addEventListener("touchend", onPlatSwipeEnd, { passive: true });
}

function ensurePlazaPlatformSelection() {
  const plaza = plazaVisibleSet();
  const timeline = timelineVisibleSet();
  if (state.timelinePlatform && !timeline.has(state.timelinePlatform)) {
    state.timelinePlatform = "";
  }
  if (state.platform && !plaza.has(state.platform)) {
    state.platform = "";
  }
}

function isMobileTimelineFilter() {
  return window.matchMedia("(max-width: 768px)").matches;
}

function isWideTimeline() {
  return window.matchMedia("(min-width: 1280px)").matches;
}

function ensureWideTimelineWatch() {
  if (_tlWideWatchBound) return;
  _tlWideWatchBound = true;
  window.matchMedia("(min-width: 1280px)").addEventListener("change", () => {
    if ($("#tl-feed-panel")) renderTimeline(routeRenderSeq);
  });
}

function tlViewTogglesHtml() {
  return `
          <button id="timeline-fav-toggle" class="fav-toggle ${state.timelineFavorite ? "fav-on" : ""}" aria-pressed="${state.timelineFavorite}" onclick="toggleTimelineFav()">${STAR_SVG} 特别关注</button>
          <button id="timeline-secondary-toggle" class="fav-toggle ${state.timelineSecondary ? "fav-on" : ""}" aria-pressed="${state.timelineSecondary}" onclick="toggleTimelineSecondary()" title="显示/隐藏次要大V动态（默认隐藏）">${state.timelineSecondary ? EYE_ICON : EYE_OFF_ICON} 次要大V</button>`;
}

function tlSearchBarHtml() {
  const live = isLiveTimeline();
  const q = live ? state.liveQ : state.timelineQ;
  const label = live ? "搜索快讯" : "搜索动态";
  return `<div class="search-bar tl-rail-search">
      ${SEARCH_ICON}
      <input id="tl-q" type="search" placeholder="${label}" value="${escapeHtml(q || "")}" aria-label="${label}" oninput="tlOnSearchInput(this.value)" onkeydown="if(event.key==='Enter')tlApplyRailSearch()">
    </div>`;
}

function tlOnSearchInput(value) {
  if (isLiveTimeline()) liveSearch(value);
}

function tlApplyRailSearch() {
  if (isLiveTimeline()) {
    const q = $("#tl-q");
    liveSearch(q ? q.value : state.liveQ);
    $("#tl-filterbar")?.classList.remove("open");
    return;
  }
  tlApplyFilter();
}

function tlSyncSearchBox() {
  const q = $("#tl-q");
  if (!q) return;
  const live = isLiveTimeline();
  q.value = live ? (state.liveQ || "") : (state.timelineQ || "");
  const label = live ? "搜索快讯" : "搜索动态";
  q.placeholder = label;
  q.setAttribute("aria-label", label);
}

function tlFilterActionsHtml() {
  return `<div class="tl-actions">
          <button id="tl-filter-toggle" class="fav-toggle ${tlPanelFilterOn() ? "has-filter" : ""}" aria-label="筛选" aria-expanded="false" aria-controls="tl-filter-panel" onclick="tlFilterPanel()">${FILTER_ICON}筛选</button>
        </div>`;
}

function tlFilterPanelHtml() {
  const live = isLiveTimeline();
  return `<div class="tl-filter-panel" id="tl-filter-panel">
        ${tlSearchBarHtml()}
        ${live ? "" : `<div class="tl-filter-views">${tlViewTogglesHtml()}</div>
        <div class="tl-filter-row">
          <select id="tl-tag" class="form-control" onchange="tlApplyFilter()"><option value="">全部标签</option></select>
        </div>`}
        <div class="tl-filter-actions">
          <button class="btn-ghost" onclick="tlResetFilters()">清除筛选</button>
          <button class="btn-normal" onclick="tlApplyFilter()">完成</button>
        </div>
      </div>`;
}

function syncTimelineSourceView() {
  if (!$("#tl-feed-panel") || !$("#tl-filterbar")) {
    renderTimeline(routeRenderSeq);
    return;
  }
  const live = isLiveTimeline();
  const wide = isWideTimeline();
  document.querySelector(".tl-layout")?.classList.toggle("live-mode", live);
  $("#tl-filterbar")?.classList.toggle("live-mode", live);
  const pills = $("#tl-pills");
  if (pills) pills.innerHTML = tlPillsHtml();
  renderTlKolBar();
  if (!live) loadTimelineKols();
  $("#live-toolbar")?.remove();
  const bar = $("#tl-platform-bar");
  const actions = bar?.querySelector(".tl-actions");
  if (wide) actions?.remove();
  else if (bar && !actions) bar.insertAdjacentHTML("beforeend", tlFilterActionsHtml());
  const panel = $("#tl-filter-panel");
  if (wide) {
    panel?.remove();
    $("#tl-filterbar")?.classList.remove("open");
  } else if (!panel) {
    const badge = $("#tl-new-badge");
    if (badge) badge.insertAdjacentHTML("beforebegin", tlFilterPanelHtml());
    else $("#tl-filterbar")?.insertAdjacentHTML("beforeend", tlFilterPanelHtml());
    if (!live) loadTimelineTags().catch(() => { _tlTags = []; _tlDynamicTags = []; });
  } else {
    panel.outerHTML = tlFilterPanelHtml();
  }
  $("#tl-filterbar")?.classList.remove("open");
  const filterBtn = $("#tl-filter-toggle");
  if (filterBtn) filterBtn.setAttribute("aria-expanded", "false");
  const feedPanel = $("#tl-feed-panel");
  const head = $("#live-feed-head");
  if (live) {
    if (head) head.outerHTML = liveFeedHeadHtml();
    else if (feedPanel) feedPanel.insertAdjacentHTML("afterbegin", liveFeedHeadHtml());
  } else {
    head?.remove();
  }
  tlSyncSearchBox();
  renderLiveRail();
  const chips = $("#tl-active-chips-wrap");
  if (chips) {
    chips.classList.toggle("is-hidden", live);
    chips.innerHTML = live ? "" : tlActiveChipsHtml();
  }
  const btn = $(".tl-new-badge-btn");
  if (btn) btn.setAttribute("aria-label", live ? "有新快讯，点击查看" : "有新动态，点击查看");
  $("#tl-new-badge")?.classList.toggle("live-mode", live);
  if (live) startLiveClock();
  else stopLiveClock();
  tlSyncNewBadgeMode();
  startTimelinePoll();
  if (live) {
    if (_livePosts.length) {
      renderLiveFeed();
      pollFeedUpdates();
    } else {
      loadTimeline(true, routeRenderSeq).then(() => pollFeedUpdates());
    }
    return;
  }
  if (_tlPosts.length && _tlLoadedFilter === tlFilterKey()) {
    renderTimelineFeed();
    pollFeedUpdates();
    if (wide) loadTimelineRail(routeRenderSeq);
  } else {
    loadTimeline(true, routeRenderSeq).then(() => {
      if (wide) loadTimelineRail(routeRenderSeq);
      pollFeedUpdates();
    });
  }
  prefetchLiveFeed();
}

function tlPickSource(source) {
  const next = source === "live" ? "live" : "kol";
  if (state.timelineSource === next) return;
  if (isLiveTimeline()) _liveSavedScrollY = window.scrollY;
  else _tlSavedScrollY = window.scrollY;
  state.timelineSource = next;
  tlPersistSource();
  stopTimelinePoll();
  if ($("#tl-feed-panel")) syncTimelineSourceView();
  else renderTimeline(routeRenderSeq);
}

async function renderTimeline(seq) {
  setPageTitle("最新动态");
  ensurePlazaPlatformSelection();
  ensureWideTimelineWatch();
  const live = isLiveTimeline();
  const reuse = live
    ? _livePosts.length > 0
    : (_tlPosts.length && _tlLoadedFilter === tlFilterKey());
  const wide = isWideTimeline();
  $("#main").innerHTML = `
    <div class="tl-layout${live ? " live-mode" : ""}">
    <div class="tl-main">
    <div class="tl-filterbar${live ? " live-mode" : ""}" id="tl-filterbar">
      <div class="tl-filterbar-top icon-badge-bar" id="tl-platform-bar">
        <div class="tl-pills" id="tl-pills" role="radiogroup" aria-label="平台和内容源">${tlPillsHtml()}</div>
        ${wide ? "" : tlFilterActionsHtml()}
      </div>
      <div class="tl-kolbar" id="tl-kolbar" hidden></div>
      ${wide ? "" : tlFilterPanelHtml()}
      <div class="tl-new-badge${live ? " live-mode" : ""}" id="tl-new-badge">
        <button class="tl-new-badge-btn" onclick="refreshTimeline()" aria-label="${live ? "有新快讯，点击查看" : "有新动态，点击查看"}">
          ${ARROW_UP_ICON}
          <span class="tl-badge-avatars" id="tl-new-avatars"></span>
          <span class="tl-new-badge-label">${tlNewBadgeLabel()}</span>
        </button>
      </div>
    </div>
    <div id="tl-active-chips-wrap"${live ? ' class="is-hidden"' : ""}>${live ? "" : tlActiveChipsHtml()}</div>
    <div class="tl-ima-entry">
      <button type="button" class="tl-ima-entry-btn" onclick="go('knowledge')">
        <span class="tl-ima-entry-icon">${BOOK_ICON}</span>
        <span><strong>研报库</strong><small>打开研报库</small></span>
      </button>
    </div>
    <section class="section-panel tl-feed-panel" id="tl-feed-panel">
      ${live ? liveFeedHeadHtml() : ""}
      <div id="feed">${reuse ? "" : TL_SKELETON}</div>
    </section>
    </div>
    ${wide ? `<aside class="tl-rail" id="tl-rail" aria-label="发现">
      <div class="tl-rail-head">${tlSearchBarHtml()}</div>
      <div class="tl-rail-body">
        <div class="tl-rail-card tl-rail-view" id="tl-rail-view">${tlViewTogglesHtml()}</div>
        <div id="tl-live-rail"></div>
        <div id="tl-rail-recs"></div>
        <div id="tl-rail-tags"></div>
      </div>
    </aside>` : ""}
    </div>
    <button type="button" id="tl-backtop" class="tl-backtop" aria-label="返回顶部" title="返回顶部" onclick="tlScrollToTop()">${ARROW_UP_ICON}</button>`;
  tlSyncNewBadgeMode();
  if (live) startLiveClock();
  else stopLiveClock();
  renderLiveRail();
  if (!live) {
    renderTlKolBar();
    loadTimelineKols();
  }
  ensureTlKolbarResizeSync();
  ensureTimelineScrollChrome();
  tlSyncScrollChrome();
  if (reuse) {
    renderFeed();
    window.scrollTo(0, feedScrollY());
    // 恢复滚动位置不算一次「下滑」，重置方向基准，避免进页面就收起筛选条
    _tlScrollLastY = feedScrollY();
    startTimelinePoll();
    pollFeedUpdates();
    if (!wide && !live) loadTimelineTags().catch(() => { _tlTags = []; _tlDynamicTags = []; });
    if (wide) loadTimelineRail(seq);
    if (!live) prefetchLiveFeed();
    return;
  }
  if (live) {
    _liveCursor = "";
    _liveHasMore = true;
    _liveLatestId = 0;
    try {
      await loadTimeline(true, seq);
      startTimelinePoll();
      pollFeedUpdates();
    } catch (err) {
      if (!routeStillActive(seq)) return;
      const feed = $("#feed");
      if (feed) feed.innerHTML = emptyState("加载失败: " + err.message,
        `<div><button class="btn-normal" onclick="renderTimeline()">重试</button></div>`);
    }
    return;
  }
  _tlPosts.length = 0;
  _tlOffset = 0;
  _tlHasMore = true;
  _tlLatestId = 0;
  try {
    if (!wide) {
      await loadTimelineTags().catch(() => { _tlTags = []; _tlDynamicTags = []; }); // 标签下拉失败降级，不阻塞 feed
    }
    await loadTimeline(true, seq);
    if (wide) loadTimelineRail(seq);
    startTimelinePoll();
    pollFeedUpdates();
    prefetchLiveFeed();
  } catch (err) {
    if (!routeStillActive(seq)) return;
    const feed = $("#feed");
    if (feed) feed.innerHTML = emptyState("加载失败: " + err.message,
      `<div><button class="btn-normal" onclick="renderTimeline()">重试</button></div>`);
  }
}

function startTimelinePoll() {
  stopTimelinePoll();
  ensureTimelineVisibilityPoll();
  const interval = isLiveTimeline() ? 15000 : 60000;
  _tlPollTimer = setInterval(pollFeedUpdates, interval);
}
function stopTimelinePoll() {
  if (_tlPollTimer) { clearInterval(_tlPollTimer); _tlPollTimer = null; }
  stopLiveClock();
}

function ensureTimelineVisibilityPoll() {
  if (ensureTimelineVisibilityPoll.bound) return;
  ensureTimelineVisibilityPoll.bound = true;
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    if (!$("#feed")) return;
    pollFeedUpdates();
  });
}

// 播放新消息提示音
function playNotificationSound() {
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const osc1 = audioContext.createOscillator();
    const osc2 = audioContext.createOscillator();
    const gain1 = audioContext.createGain();
    const gain2 = audioContext.createGain();
    
    osc1.type = "sine";
    osc1.frequency.setValueAtTime(1200, audioContext.currentTime);
    gain1.gain.setValueAtTime(0.2, audioContext.currentTime);
    gain1.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.25);
    
    osc2.type = "sine";
    osc2.frequency.setValueAtTime(1800, audioContext.currentTime + 0.15);
    gain2.gain.setValueAtTime(0.15, audioContext.currentTime + 0.15);
    gain2.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.35);
    
    osc1.connect(gain1);
    gain1.connect(audioContext.destination);
    osc2.connect(gain2);
    gain2.connect(audioContext.destination);
    
    osc1.start(audioContext.currentTime);
    osc1.stop(audioContext.currentTime + 0.25);
    osc2.start(audioContext.currentTime + 0.15);
    osc2.stop(audioContext.currentTime + 0.35);
  } catch {
    // 如果播放失败，静默处理
  }
}

async function pollFeedUpdates() {
  if (document.visibilityState === "hidden") return;
  const live = isLiveTimeline();
  const latestId = live ? _liveLatestId : _tlLatestId;
  const pendingLatestId = live ? _livePendingLatestId : _tlPendingLatestId;
  const pendingNew = feedPendingNew();
  if (!latestId || !$("#feed") || (live && !isLiveTimeline()) || (!live && isLiveTimeline())) return;
  const seq = routeRenderSeq;
  try {
    let newer = [];
    if (live) {
      const params = new URLSearchParams({
        limit: "30",
        since_id: String(pendingLatestId || latestId),
      });
      const data = await api(`/api/live/wscn?${params}`);
      if (!routeStillActive(seq) || !$("#feed") || !isLiveTimeline()) return;
      newer = data.items || [];
    } else {
      const params = new URLSearchParams({ limit: "50", since_id: String(pendingLatestId || latestId) });
      if (state.timelineQ) params.set("q", state.timelineQ);
      if (state.timelinePlatform) params.set("platform", state.timelinePlatform);
      if (state.timelineKolId) params.set("kol_id", String(state.timelineKolId));
      if (state.timelineCategory) params.set("category_id", state.timelineCategory);
      if (state.timelineTag) params.set("tag", state.timelineTag);
      if (state.timelineFavorite) params.set("favorite", "1");
      if (state.timelineSecondary) params.set("include_secondary", "1");
      const posts = await api(`/api/my/feed?${params}`);
      if (!routeStillActive(seq) || !$("#feed") || isLiveTimeline()) return;
      // 「新帖」以发布时间为准（锚点=列表里时间最新的一条），不能只按 id 过滤：
      // 补历史会给旧消息发新 id，按 id 过滤会把它们当成新帖顶到时间线最上面。
      // 能走到这里列表必非空（空列表 latestId=0 已提前返回），锚点必存在
      const anchor = feedNewestPost(feedPosts());
      newer = posts.filter((p) => feedTimeAsc(p, anchor) > 0);
    }
    // 筛选单个大V浏览时，顺带按 since_id 轮询其他大V的新动态并累计到头像角标；
    // 只累计计数，不触发当前视图的新帖胶囊/提示音/自动刷新
    if (!live && state.timelineKolId && _tlOthersAnchorId) {
      try {
        const others = await api(`/api/my/feed?limit=50&since_id=${_tlOthersAnchorId}`);
        if (!routeStillActive(seq) || !$("#feed") || isLiveTimeline()) return;
        let changed = false;
        for (const p of others) {
          if (p.id > _tlOthersAnchorId) _tlOthersAnchorId = p.id;
          if (p.kol_id && p.kol_id !== state.timelineKolId) {
            _tlKolNewCounts.set(p.kol_id, (_tlKolNewCounts.get(p.kol_id) || 0) + 1);
            changed = true;
          }
        }
        if (changed) tlApplyKolNewCounts();
      } catch { /* 其他大V计数拉取失败静默，不影响主轮询 */ }
    }
    if (!newer.length) return;
    const have = new Set(pendingNew.map((p) => p.id));
    for (const p of newer) {
      if (!have.has(p.id)) {
        have.add(p.id);
        pendingNew.push(p);
      }
    }
    if (live) _livePendingLatestId = Math.max(_livePendingLatestId, ...newer.map((p) => p.id));
    else _tlPendingLatestId = Math.max(_tlPendingLatestId, ...newer.map((p) => p.id));
    const unit = live ? "快讯" : "动态";
    const label = `${pendingNew.length} 条新${unit}，点击查看`;
    const btn = $(".tl-new-badge-btn");
    if (btn) {
      btn.title = label;
      btn.setAttribute("aria-label", label);
    }
    if (!live) {
      const avatars = $("#tl-new-avatars");
      if (avatars) avatars.innerHTML = tlBadgeAvatarsHtml(pendingNew);
    }
    $("#tl-new-badge")?.classList.add("show");
    $("#tl-feed-panel")?.classList.add("has-new");
    
    // 自动刷新显示新消息并播放提示音
    playNotificationSound();
    refreshTimeline();
  } catch { /* 轮询失败静默 */ }
}

// 新帖胶囊头像：去重取前 3 个（无头像用首字色块）；超出的作者不另画 +N，条数只在 aria-label
function tlBadgeAvatarsHtml(posts, max = 3) {
  const seen = new Set();
  const avs = [];
  for (const p of posts) {
    const key = p.kol_id || p.kol_name;
    if (seen.has(key)) continue;
    seen.add(key);
    if (avs.length >= max) break;
    avs.push(p.avatar_url && !_deadImgUrls.has(p.avatar_url)
      ? `<img src="${escapeHtml(p.avatar_url)}" alt="" data-av-name="${escapeHtml(p.kol_name)}" data-av-class="ph" onerror="avatarImgError(this)">`
      : `<span class="ph">${escapeHtml(avatarText(p.kol_name))}</span>`);
  }
  return avs.join("");
}

async function refreshTimeline() {
  if (_tlRefreshing) return;
  _tlRefreshing = true;
  try {
    const live = isLiveTimeline();
    const pending = feedPendingNew();
    const posts = feedPosts();
    if (!pending.length) {
      await loadTimeline(true, routeRenderSeq);
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    await pollFeedUpdates();
    const seen = new Set(posts.map((p) => p.id));
    const incoming = pending.filter((p) => !seen.has(p.id));
    if (incoming.length) {
      if (live) {
        // 快讯 id 与时间同序（上游保证），按 id 降序整批置顶
        incoming.sort((a, b) => b.id - a.id);
        posts.unshift(...incoming);
      } else {
        // id 顺序≠时间顺序（补历史/并发入库）：按发布时间逐条归位插入，
        // 新帖内部也严格按时间排，避免旧消息或同批乱序顶在最上面
        incoming.sort((a, b) => feedTimeAsc(b, a));
        for (const p of incoming) {
          const idx = posts.findIndex((q) => feedTimeAsc(q, p) < 0);
          if (idx < 0) posts.push(p);
          else posts.splice(idx, 0, p);
        }
      }
      if (live) {
        _liveLatestId = Math.max(_liveLatestId, _livePendingLatestId, ...incoming.map((p) => p.id));
        _livePendingNew.length = 0;
        _livePendingLatestId = 0;
      } else {
        _tlOffset += incoming.length;
        _tlLatestId = Math.max(_tlLatestId, _tlPendingLatestId);
        _tlPendingNew.length = 0;
        _tlPendingLatestId = 0;
      }
      renderFeed();
    }
    $("#tl-new-badge")?.classList.remove("show");
    $("#tl-feed-panel")?.classList.remove("has-new");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } finally {
    _tlRefreshing = false;
  }
}

function tlPillsHtml() {
  const liveSelected = isLiveTimeline();
  const livePill = `
    <button class="tl-pill ${liveSelected ? "selected" : ""}" role="radio" data-platform="live" aria-label="快讯" title="快讯" aria-checked="${liveSelected}" onclick="tlPickSource('live')">
      ${WSCN_LIVE_ICON}<span>快讯</span>
    </button>`;
  const pills = [];
  for (const [p, label] of tlTimelineEntries()) {
    const selected = !liveSelected && state.timelinePlatform === p;
    const short = platformShortLabel(p);
    pills.push(`
    <button class="tl-pill ${selected ? "selected" : ""}" role="radio" data-platform="${p}" aria-label="${label}" title="${label}" aria-checked="${selected}" onclick="tlPickPlatform('${p}')">
      ${PLATFORM_ICONS[p || ""]}
      <span>${short}</span>
    </button>`);
    if (!p) pills.push(livePill);
  }
  return pills.join("");
}

function tlPickPlatform(p) {
  const revert = tlSnapshotFilters();
  const leftLive = isLiveTimeline();
  if (leftLive) {
    state.timelineSource = "kol";
    tlPersistSource();
  }
  state.timelinePlatform = p;
  // 平台切换后原大V可能不属于新平台，会筛出空列表，直接清除
  state.timelineKolId = 0;
  tlClearKolNewCounts();
  if (leftLive) {
    stopTimelinePoll();
    if ($("#tl-feed-panel")) syncTimelineSourceView();
    else renderTimeline(routeRenderSeq);
    return;
  }
  const pills = $("#tl-pills");
  if (pills) pills.innerHTML = tlPillsHtml();
  renderTlKolBar();
  tlSyncFilterChrome();
  loadTimeline(true, routeRenderSeq, { revert });
}

// ---------- 时间线大V头像行（第二排） ----------
// 数据源 = 我的订阅（/api/my/subscriptions 已按广场可见性过滤）；
// feed 本身只含已订阅大V，按订阅列头像才能保证点击后筛得出内容。
// 排序：特别关注置顶、组内按最近发言倒序；只在头像行渲染时（进页面/点平台）算一次，不做持续重排。
let _tlKolRows = [];
let _tlKolsPromise = null;
let _tlKolsLoadedAt = 0;
const TL_KOLS_TTL = 30 * 1000;
const TL_KOLBAR_EXPANDED_KEY = "tl-kolbar-expanded";
let _tlKolbarExpanded = (() => {
  try { return sessionStorage.getItem(TL_KOLBAR_EXPANDED_KEY) === "1"; } catch { return false; }
})();
// 筛选单个大V浏览时，其他大V新到动态的会话内计数（kolId → 条数）。
// 清零时机：回到「全部」时全部清零；切换选中的大V只清新选中那个（他的新帖已列在列表里）。
// _tlOthersAnchorId 是「其他大V」轮询的 since_id 消费基准：选中大V时推进到
// max(旧锚点, 全量 feed 最新 id)，之后只被本查询自己推进（与所看大V的新帖无关）。
let _tlKolNewCounts = new Map();
let _tlOthersAnchorId = 0;
const TL_CARET_SVG = `<svg class="tl-kolbar-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>`;

function tlKolLastPostMs(k) {
  const t = k.last_post_at ? Date.parse(k.last_post_at) : NaN;
  return Number.isNaN(t) ? -1 : t;
}

function tlKolRowsFor(platform) {
  const rows = _tlKolRows.filter((k) => !platform || k.platform === platform);
  return rows.sort((a, b) =>
    ((b.favorite ? 1 : 0) - (a.favorite ? 1 : 0)) || (tlKolLastPostMs(b) - tlKolLastPostMs(a)));
}

function tlKolItemsHtml() {
  return tlKolRowsFor(state.timelinePlatform).map((k) => {
    const selected = state.timelineKolId === k.id;
    const avatar = k.avatar_url && !_deadImgUrls.has(k.avatar_url)
      ? `<img src="${escapeHtml(k.avatar_url)}" alt="" loading="lazy" data-av-name="${escapeHtml(k.name)}" data-av-class="tl-kol-ph" onerror="avatarImgError(this)">`
      : `<span class="tl-kol-ph">${escapeHtml(avatarText(k.name))}</span>`;
    // 新消息角标：只在筛选某位大V时统计「其他大V」新到的动态条数，回到全部即清零
    const n = _tlKolNewCounts.get(k.id) || 0;
    const count = n > 0
      ? `<span class="tl-kol-count" aria-hidden="true" title="${escapeHtml(k.name)} 有 ${n} 条新动态">${n > 99 ? "99+" : n}</span>`
      : "";
    return `<button class="tl-kol-item${selected ? " selected" : ""}" role="radio" aria-checked="${selected}"
      aria-label="只看 ${escapeHtml(k.name)}${n ? `，${n} 条新动态` : ""}" title="${escapeHtml(k.name)}" onclick="tlPickKol(${k.id})">
      <span class="tl-kol-avwrap"><span class="tl-kol-av">${avatar}</span>${count}</span>
      <span class="tl-kol-name">${escapeHtml(k.name)}</span>
    </button>`;
  }).join("");
}

function tlKolbarEmpty() {
  return isLiveTimeline()
    || !_tlKolRows.some((k) => !state.timelinePlatform || k.platform === state.timelinePlatform);
}

function renderTlKolBar() {
  const bar = $("#tl-kolbar");
  if (!bar) return;
  if (tlKolbarEmpty()) {
    bar.innerHTML = "";
    bar.hidden = true;
    return;
  }
  bar.hidden = false;
  bar.classList.toggle("expanded", _tlKolbarExpanded);
  bar.innerHTML = `
    <div class="tl-kolbar-strip" id="tl-kolbar-strip" role="radiogroup" aria-label="按大V筛选">${tlKolItemsHtml()}</div>
    <button type="button" class="tl-kolbar-toggle" aria-expanded="${_tlKolbarExpanded}" aria-controls="tl-kolbar-strip" onclick="tlToggleKolbar()">
      ${_tlKolbarExpanded ? "收起" : "展开"}${TL_CARET_SVG}
    </button>`;
  tlSyncKolbarToggle();
}

// 单行放得下就不显示展开开关（展开态始终显示，供收起）
function tlSyncKolbarToggle() {
  const strip = $("#tl-kolbar-strip");
  const toggle = $("#tl-kolbar .tl-kolbar-toggle");
  if (!strip || !toggle) return;
  toggle.hidden = !_tlKolbarExpanded && strip.scrollWidth <= strip.clientWidth + 1;
}

function tlToggleKolbar() {
  _tlKolbarExpanded = !_tlKolbarExpanded;
  try { sessionStorage.setItem(TL_KOLBAR_EXPANDED_KEY, _tlKolbarExpanded ? "1" : "0"); } catch { /* */ }
  renderTlKolBar();
}

let _tlKolbarResizeTimer = null;
function ensureTlKolbarResizeSync() {
  if (ensureTlKolbarResizeSync.bound) return;
  ensureTlKolbarResizeSync.bound = true;
  // 视口宽度变化会改变"单行是否放得下"，防抖后仅同步开关可见性
  window.addEventListener("resize", () => {
    clearTimeout(_tlKolbarResizeTimer);
    _tlKolbarResizeTimer = setTimeout(tlSyncKolbarToggle, 150);
  });
}

// ---------- 手机端滚动显隐：下滑收起筛选条（平台行+大V行），上滑恢复；滚动较深显示返回顶部 ----------
// 筛选条是 sticky 且被不透明 topbar 盖住（z 更高），translateY(-100%) 藏进 topbar 后面即可，
// transform 不改变文档流，不会引起内容跳动。
let _tlScrollChromeBound = false;
let _tlScrollLastY = 0;
let _tlScrollRaf = 0;

function ensureTimelineScrollChrome() {
  if (_tlScrollChromeBound) return;
  _tlScrollChromeBound = true;
  window.addEventListener("scroll", () => {
    if (_tlScrollRaf) return;
    _tlScrollRaf = requestAnimationFrame(() => { _tlScrollRaf = 0; tlSyncScrollChrome(); });
  }, { passive: true });
}

function tlSyncScrollChrome() {
  const y = window.scrollY;
  const bar = $("#tl-filterbar");
  if (bar && !bar.classList.contains("open")) { // 筛选面板展开时不收起
    const delta = y - _tlScrollLastY;
    if (y <= 80 || delta < -2 || !isMobileTimelineFilter()) bar.classList.remove("tl-bars-hidden");
    else if (delta > 2 && y > 120) bar.classList.add("tl-bars-hidden");
  }
  const backtop = $("#tl-backtop");
  if (backtop) backtop.classList.toggle("show", isMobileTimelineFilter() && y > 600);
  _tlScrollLastY = y;
}

function tlScrollToTop() {
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function ensureTimelineKols() {
  if (_tlKolRows.length && Date.now() - _tlKolsLoadedAt < TL_KOLS_TTL) return _tlKolRows;
  if (!_tlKolsPromise) {
    _tlKolsPromise = api("/api/my/subscriptions").then((rows) => {
      _tlKolRows = Array.isArray(rows) ? rows : [];
      _tlKolsLoadedAt = Date.now();
      return _tlKolRows;
    }).finally(() => { _tlKolsPromise = null; });
  }
  return _tlKolsPromise;
}

function loadTimelineKols() {
  ensureTimelineKols().then(() => renderTlKolBar()).catch(() => { /* 订阅列表拉不到就不显示大V行 */ });
}

function tlPickKol(id) {
  const revert = tlSnapshotFilters();
  state.timelineKolId = state.timelineKolId === id ? 0 : id;
  if (state.timelineKolId) {
    // 切到某位大V：只清他自己的角标（他的新帖此刻已列在列表里），其他大V角标原样保留；
    // 锚点推进到「已消费位置」与「此刻全量 feed 最新帖」的较大者，作为新起点
    _tlKolNewCounts.delete(state.timelineKolId);
    _tlOthersAnchorId = Math.max(_tlOthersAnchorId, _tlLatestId || 0);
  } else {
    // 回到「全部」：所有角标清零；锚点归零，下次选中时重新起步
    tlClearKolNewCounts();
  }
  renderTlKolBar();
  tlSyncFilterChrome();
  loadTimeline(true, routeRenderSeq, { revert });
}

// 计数变化后重绘大V行；恢复横向滚动位置，避免角标刷新把列表拽回开头
function tlApplyKolNewCounts() {
  const strip = $("#tl-kolbar-strip");
  const sl = strip ? strip.scrollLeft : 0;
  renderTlKolBar();
  const next = $("#tl-kolbar-strip");
  if (next) next.scrollLeft = sl;
}

function tlClearKolNewCounts() {
  _tlOthersAnchorId = 0;
  if (!_tlKolNewCounts.size) return;
  _tlKolNewCounts.clear();
  tlApplyKolNewCounts();
}

function tlSyncActiveChips() {
  const wrap = $("#tl-active-chips-wrap");
  if (wrap) wrap.innerHTML = tlActiveChipsHtml();
}

function tlFilterPanel() {
  const bar = $("#tl-filterbar");
  if (!bar) return;
  const open = bar.classList.toggle("open");
  const btn = $("#tl-filter-toggle");
  if (btn) btn.setAttribute("aria-expanded", String(open));
  if (open) $("#tl-q")?.focus();
}

function tlApplyFilter() {
  if (isLiveTimeline()) {
    tlApplyRailSearch();
    return;
  }
  const revert = tlSnapshotFilters();
  const q = $("#tl-q");
  if (q) state.timelineQ = q.value.trim();
  const tag = $("#tl-tag");
  if (tag) state.timelineTag = tag.value;
  state.timelineCategory = "";
  $("#tl-filterbar")?.classList.remove("open");
  const btn = $("#tl-filter-toggle");
  if (btn) btn.setAttribute("aria-expanded", "false");
  tlSyncFilterChrome();
  loadTimeline(true, routeRenderSeq, { revert });
}

function tlResetFilters() {
  if (isLiveTimeline()) {
    state.liveQ = "";
    tlSyncSearchBox();
    renderLiveFeed();
    $("#tl-filterbar")?.classList.remove("open");
    const fb = $("#tl-filter-toggle");
    if (fb) fb.setAttribute("aria-expanded", "false");
    return;
  }
  const revert = tlSnapshotFilters();
  state.timelineQ = "";
  state.timelineCategory = "";
  state.timelineTag = "";
  state.timelinePlatform = "";
  state.timelineKolId = 0;
  tlClearKolNewCounts();
  state.timelineFavorite = false;
  state.timelineSecondary = false;
  const q = $("#tl-q"); if (q) q.value = "";
  const tag = $("#tl-tag"); if (tag) tag.value = "";
  const pills = $("#tl-pills"); if (pills) pills.innerHTML = tlPillsHtml();
  renderTlKolBar();
  const fb = $("#tl-filter-toggle"); if (fb) fb.setAttribute("aria-expanded", "false");
  $("#tl-filterbar")?.classList.remove("open");
  tlPaintViewToggles();
  tlSyncFilterChrome();
  loadTimeline(true, routeRenderSeq, { revert });
  renderRailTags(_tlDynamicTags.slice(0, 8));
}

// 点击帖子标签直接进入该标签筛选（复用 timelineTag 状态与筛选条）
function tlPickTag(tag) {
  const revert = tlSnapshotFilters();
  state.timelineTag = tag;
  const tagSel = $("#tl-tag");
  if (tagSel) tagSel.value = tag;
  tlSyncFilterChrome();
  loadTimeline(true, routeRenderSeq, { revert });
  renderRailTags(_tlDynamicTags.slice(0, 8));
}

async function loadTimelineTags() {
  if (!_tlTags) {
    const data = await api("/api/tags");
    // 词表是对象数组（{tag, keywords}）+ 贴文实际出现的动态标签（含股票名），下拉合并去重
    const vocabTags = (Array.isArray(data?.tags) ? data.tags : [])
      .map((r) => (typeof r === "string" ? r : r.tag)).filter(Boolean);
    const dynamicTags = Array.isArray(data?.dynamic_tags) ? data.dynamic_tags : [];
    _tlDynamicTags = dynamicTags;
    _tlTags = [...new Set([...vocabTags, ...dynamicTags])];
  }
  const sel = $("#tl-tag");
  if (!sel) return;
  sel.innerHTML = `<option value="">全部标签</option>` + _tlTags.map((t) =>
    `<option value="${escapeHtml(t)}" ${state.timelineTag === t ? "selected" : ""}>${escapeHtml(t)}</option>`).join("");
}

async function loadTimelineRail(routeSeq) {
  if (!$("#tl-rail")) return;
  try {
    const recs = await api("/api/recommendations?unsubscribed=1");
    if (!routeStillActive(routeSeq) || !$("#tl-rail")) return;
    renderRailRecs(Array.isArray(recs) ? recs : []);
  } catch (err) {
    const el = $("#tl-rail-recs");
    if (el) el.innerHTML = railFailHtml("推荐关注", "推荐加载失败", err);
  }
  try {
    let tags = _tlDynamicTags;
    if (!_tlTags) {
      const data = await api("/api/tags");
      tags = Array.isArray(data?.dynamic_tags) ? data.dynamic_tags : [];
      _tlDynamicTags = tags;
    }
    if (!routeStillActive(routeSeq) || !$("#tl-rail")) return;
    renderRailTags((tags || []).slice(0, 8));
  } catch (err) {
    const el = $("#tl-rail-tags");
    if (el) el.innerHTML = railFailHtml("热门标签", "标签加载失败", err);
  }
}

function railFailHtml(title, lead, err) {
  const detail = err?.message ? `：${escapeHtml(err.message)}` : "";
  return `<section class="tl-rail-card">
      <h3 class="tl-rail-title">${escapeHtml(title)}</h3>
      <div class="tl-rail-fail">
        <p class="muted">${escapeHtml(lead)}${detail}</p>
        <button type="button" class="btn-ghost" onclick="reloadTimelineRail()">重试</button>
      </div>
    </section>`;
}

function renderRailRecs(recs) {
  const el = $("#tl-rail-recs");
  if (!el) return;
  const list = recs.filter((r) => !r.subscribed).slice(0, 4);
  if (!list.length) { el.innerHTML = ""; return; }
  el.innerHTML = `
    <section class="tl-rail-card">
      <h3 class="tl-rail-title">推荐关注</h3>
      ${list.map((r) => `
        <div class="tl-rail-rec">
          ${avatarHtml(r.name, r.avatar_url)}
          <div class="tl-rail-rec-info">
            <a class="tl-rail-rec-name" href="/kol/${r.id}">${escapeHtml(r.name)}</a>
            <div class="tl-rail-rec-meta">${escapeHtml(PLATFORM_LABELS[r.platform] || r.platform)}${r.category_name ? " · " + escapeHtml(r.category_name) : ""}</div>
          </div>
          <button type="button"
            class="btn-ghost tl-rail-subscribe"
            data-subscribed="0"
            aria-label="订阅${escapeHtml(r.name)}"
            onclick="railToggleSubscribe(${r.id}, this)">
            <span class="tl-rail-subscribe-state">订阅</span>
            <span class="tl-rail-subscribe-action" aria-hidden="true">退订</span>
          </button>
        </div>`).join("")}
      <a class="tl-rail-more" href="/search">显示更多</a>
    </section>`;
}

function renderRailTags(tags) {
  const el = $("#tl-rail-tags");
  if (!el) return;
  if (!tags.length) { el.innerHTML = ""; return; }
  el.innerHTML = `
    <section class="tl-rail-card">
      <h3 class="tl-rail-title">热门标签</h3>
      <div class="tl-rail-tags">${tags.map((t) => `
        <button type="button" class="tl-rail-tag ${state.timelineTag === t ? "selected" : ""}" data-tag="${escapeHtml(t)}" onclick="tlPickTag(this.dataset.tag)">${escapeHtml(t)}</button>`).join("")}</div>
    </section>`;
}

async function railToggleSubscribe(kolId, btn) {
  if (!btn || btn.disabled) return;
  const subscribed = btn.dataset.subscribed === "1";
  const name = btn.closest(".tl-rail-rec")?.querySelector(".tl-rail-rec-name")?.textContent || "该大V";
  const restoreFocus = document.activeElement === btn && btn.matches(":focus-visible");
  btn.disabled = true;
  btn.setAttribute("aria-busy", "true");
  try {
    if (subscribed) {
      await api(`/api/subscriptions/${kolId}`, { method: "DELETE" });
    } else {
      await api("/api/subscriptions", {
        method: "POST",
        body: JSON.stringify({ kol_id: kolId, type: "post" }),
      });
    }
    const nextSubscribed = !subscribed;
    btn.dataset.subscribed = nextSubscribed ? "1" : "0";
    btn.classList.toggle("subscribed", nextSubscribed);
    btn.setAttribute("aria-label", `${nextSubscribed ? "退订" : "订阅"}${name}`);
    btn.title = nextSubscribed ? "点击退订" : "";
    const stateLabel = btn.querySelector(".tl-rail-subscribe-state");
    if (stateLabel) stateLabel.textContent = nextSubscribed ? "✓ 已订阅" : "订阅";
    if (state.user) {
      const delta = nextSubscribed ? 1 : -1;
      state.user.subscription_count = Math.max(0, (state.user.subscription_count || 0) + delta);
    }
    flash(`已${nextSubscribed ? "订阅" : "退订"}「${name}」`);
  } catch (err) {
    flash(`${subscribed ? "退订" : "订阅"}「${name}」失败: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.removeAttribute("aria-busy");
    if (restoreFocus && btn.isConnected && document.activeElement === document.body) {
      btn.focus({ preventScroll: true });
    }
  }
}

async function loadTimeline(reset = true, routeSeq, opts) {
  opts = opts || {};
  const live = isLiveTimeline();
  if (!reset && (live ? _liveLoadingMore : _tlLoadingMore)) return;
  if (!reset) {
    if (live) _liveLoadingMore = true;
    else _tlLoadingMore = true;
  }
  const seq = live ? ++_liveSeq : ++_tlSeq;
  const pills = $("#tl-pills");
  if (reset) {
    const feed = $("#feed");
    if (feed) feed.innerHTML = TL_SKELETON;
    if (!live) pills?.setAttribute("aria-busy", "true");
  }
  try {
    if (live) {
      const params = new URLSearchParams({ limit: "30" });
      if (!reset && _liveCursor) params.set("cursor", _liveCursor);
      const data = await liveWscnRequest(params);
      if (seq !== _liveSeq || !$("#feed") || !routeStillActive(routeSeq) || !isLiveTimeline()) return;
      if (reset) _livePosts.length = 0;
      const items = data.items || [];
      _livePosts.push(...items);
      _liveCursor = data.next_cursor || "";
      _liveHasMore = !!(data.next_cursor && items.length);
      if (reset) {
        _liveLatestId = _livePosts[0]?.id || 0;
        _livePendingNew.length = 0;
        _livePendingLatestId = 0;
        $("#tl-new-badge")?.classList.remove("show");
        $("#tl-feed-panel")?.classList.remove("has-new");
      }
    } else {
      const params = new URLSearchParams({ limit: "50", offset: String(reset ? 0 : _tlOffset) });
      if (state.timelineQ) params.set("q", state.timelineQ);
      if (state.timelinePlatform) params.set("platform", state.timelinePlatform);
      if (state.timelineKolId) params.set("kol_id", String(state.timelineKolId));
      if (state.timelineCategory) params.set("category_id", state.timelineCategory);
      if (state.timelineTag) params.set("tag", state.timelineTag);
      if (state.timelineFavorite) params.set("favorite", "1");
      if (state.timelineSecondary) params.set("include_secondary", "1");
      const posts = await api(`/api/my/feed?${params}`);
      if (seq !== _tlSeq || !$("#feed") || !routeStillActive(routeSeq)) return;
      if (reset) {
        _tlPosts.length = 0;
        _tlOffset = 0;
      }
      _tlPosts.push(...posts);
      _tlOffset += posts.length;
      _tlHasMore = posts.length >= 50;
      if (reset) {
        _tlLatestId = posts[0]?.id || 0;
        _tlLoadedFilter = tlFilterKey();
        _tlPendingNew.length = 0;
        _tlPendingLatestId = 0;
        $("#tl-new-badge")?.classList.remove("show");
        $("#tl-feed-panel")?.classList.remove("has-new");
      }
    }
    renderFeed();
  } catch (err) {
    const activeSeq = live ? _liveSeq : _tlSeq;
    if (seq !== activeSeq || !$("#feed") || !routeStillActive(routeSeq)) return;
    if (!live && reset && opts.revert) tlRestoreFilters(opts.revert);
    $("#feed").innerHTML = emptyState("加载失败: " + err.message,
      `<div><button class="btn-normal" onclick="reloadTimeline()">重试</button></div>`);
  } finally {
    if (reset && !live) pills?.removeAttribute("aria-busy");
    if (!reset) {
      if (live) _liveLoadingMore = false;
      else _tlLoadingMore = false;
    }
  }
}

function feedLoadMore() {
  if (isLiveTimeline()) {
    if (_liveLoadingMore || !_liveHasMore) return;
  } else if (_tlLoadingMore || !_tlHasMore) {
    return;
  }
  stopFeedAutoLoad();
  const sentinel = $("#feed-load-sentinel");
  if (sentinel) {
    sentinel.classList.add("is-loading");
    sentinel.setAttribute("aria-busy", "true");
    sentinel.innerHTML = `<span class="feed-load-spinner" aria-hidden="true"></span><span>正在加载更多…</span>`;
  }
  loadTimeline(false, routeRenderSeq);
}

function timelineLoadMore() {
  feedLoadMore();
}

function liveWscnRequest(params) {
  const key = params.toString();
  if (_liveInflight && _liveInflight.key === key) return _liveInflight.p;
  const p = api(`/api/live/wscn?${params}`).finally(() => {
    if (_liveInflight && _liveInflight.p === p) _liveInflight = null;
  });
  _liveInflight = { key, p };
  return p;
}

function prefetchLiveFeed() {
  if (isLiveTimeline() || _livePosts.length) return;
  const params = new URLSearchParams({ limit: "30" });
  liveWscnRequest(params).then((data) => {
    if (isLiveTimeline() || _livePosts.length) return;
    const items = data.items || [];
    if (!items.length) return;
    _livePosts.push(...items);
    _liveCursor = data.next_cursor || "";
    _liveHasMore = !!(data.next_cursor && items.length);
    _liveLatestId = _livePosts[0]?.id || 0;
  }).catch(() => { /* 预取失败时点进快讯再拉 */ });
}

function liveClockText(now = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  const weekdays = ["日", "一", "二", "三", "四", "五", "六"];
  return `${now.getMonth() + 1}月${now.getDate()}日，星期${weekdays[now.getDay()]}，${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

function liveFeedHeadHtml() {
  return `<div class="live-feed-head" id="live-feed-head">
    <div class="live-toolbar-clock" id="live-clock" role="status" aria-live="off">${liveClockText()}</div>
    <span class="live-toolbar-divider" aria-hidden="true"></span>
    <label class="live-important-toggle" for="live-important">
      <input id="live-important" type="checkbox" ${state.liveImportant ? "checked" : ""} onchange="toggleLiveImportant(this.checked)">
      <span>只看重要的</span>
    </label>
  </div>`;
}

function updateLiveClock() {
  const clock = $("#live-clock");
  if (clock) clock.textContent = liveClockText();
}

function liveRailHtml() {
  const total = _livePosts.length;
  const important = _livePosts.filter((item) => Number(item.score) >= 2).length;
  const latest = _livePosts[0]?.published_at;
  const updated = latest ? fmtPublished(latest, true) : "暂无";
  return `<section class="tl-rail-card live-rail-card">
      <h3 class="tl-rail-title">快讯概览</h3>
      <dl class="live-rail-stats">
        <div><dt>已加载</dt><dd>${total} 条</dd></div>
        <div><dt>重要快讯</dt><dd>${important} 条</dd></div>
        <div><dt>最新快讯</dt><dd>${escapeHtml(updated)}</dd></div>
      </dl>
      <button type="button" class="btn-ghost live-rail-refresh" onclick="refreshTimeline()">${REFRESH_ICON} 刷新快讯</button>
    </section>`;
}

function renderLiveRail() {
  const el = $("#tl-live-rail");
  if (el) el.innerHTML = isLiveTimeline() ? liveRailHtml() : "";
}

function startLiveClock() {
  stopLiveClock();
  updateLiveClock();
  _liveClockTimer = setInterval(updateLiveClock, 1000);
}

function stopLiveClock() {
  if (_liveClockTimer) { clearInterval(_liveClockTimer); _liveClockTimer = null; }
}

function stopFeedAutoLoad() {
  _feedLoadObserver?.disconnect();
  _feedLoadObserver = null;
  if (_feedLoadFallback) {
    window.removeEventListener("scroll", _feedLoadFallback);
    _feedLoadFallback = null;
  }
}

function startFeedAutoLoad() {
  stopFeedAutoLoad();
  const sentinel = $("#feed-load-sentinel");
  const hasMore = isLiveTimeline() ? _liveHasMore : _tlHasMore;
  if (!sentinel || !hasMore) return;
  const load = () => feedLoadMore();
  if ("IntersectionObserver" in window) {
    _feedLoadObserver = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) load();
    }, { rootMargin: "400px 0px" });
    _feedLoadObserver.observe(sentinel);
    return;
  }
  _feedLoadFallback = () => {
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 400) load();
  };
  window.addEventListener("scroll", _feedLoadFallback, { passive: true });
  _feedLoadFallback();
}


function liveFilteredPosts() {
  const q = (state.liveQ || "").trim().toLowerCase();
  return _livePosts.filter((item) => {
    if (state.liveImportant && Number(item.score) < 2) return false;
    if (!q) return true;
    return `${item.highlight_title || ""} ${item.body || ""}`.toLowerCase().includes(q);
  });
}

function liveSearch(value) {
  state.liveQ = value;
  renderLiveFeed();
}

function toggleLiveImportant(checked) {
  state.liveImportant = !!checked;
  renderLiveFeed();
}

function liveFeedItem(item) {
  const score = Number(item.score) || 1;
  const title = item.highlight_title
    ? `<div class="live-title">${escapeHtml(item.highlight_title)}</div>`
    : "";
  const body = mdToHtml(item.body || "");
  return `
    <article class="live-item" data-score="${score}">
      <time class="live-time" datetime="${escapeHtml(item.published_at || "")}">${fmtPublished(item.published_at, true)}</time>
      <div class="live-main">
        ${title}
        <div class="live-body">${body}</div>
      </div>
    </article>`;
}

function renderLiveFeed() {
  const feed = $("#feed");
  if (!feed) return;
  const allPosts = _livePosts;
  const posts = liveFilteredPosts();
  const grouped = new Map();
  for (const p of posts) {
    const bucket = feedDateBucket(p.published_at);
    if (!grouped.has(bucket)) grouped.set(bucket, []);
    grouped.get(bucket).push(p);
  }
  const html = [...grouped.entries()].map(([bucket, list], gi) => `
    <div class="tl-group live-group">
      <div class="tl-group-head"><span>${escapeHtml(bucket)}</span>${gi === 0 ? `<span class="tl-group-count">已加载 ${posts.length}${posts.length !== allPosts.length ? ` / ${allPosts.length}` : ""} 条快讯</span>` : ""}</div>
      <div class="live-feed">${list.map(liveFeedItem).join("")}</div>
    </div>`).join("");
  const footer = _liveHasMore && posts.length
    ? `<div id="feed-load-sentinel" class="tl-feed-more" role="status" aria-live="polite"></div>`
    : (posts.length ? `<p class="muted tl-feed-end">已加载全部</p>` : "");
  const empty = allPosts.length
    ? emptyState("没有匹配的快讯")
    : emptyState("暂无快讯", `<div><button class="btn-normal" onclick="reloadTimeline()">刷新</button></div>`);
  const attr = posts.length
    ? html + footer + `<p class="live-attribution muted">数据来源：<a href="https://wallstreetcn.com/live/global" target="_blank" rel="noopener">华尔街见闻 · 快讯</a></p>`
    : empty;
  feed.innerHTML = attr;
  renderLiveRail();
  startFeedAutoLoad();
}

function renderTimelineFeed() {
  const feed = $("#feed");
  if (!feed) return;
  // 全量重绘会重建所有卡片，正在播放的语音先停掉，避免孤儿音频继续出声
  if (_mxAudioBtn && feed.contains(_mxAudioBtn)) stopMxAudio();
  const posts = _tlPosts;
  const visibleIds = new Set(posts.map((p) => p.id));
  for (const id of [..._tlExpanded]) {
    if (!visibleIds.has(id)) _tlExpanded.delete(id);
  }
  const grouped = new Map();
  for (const p of posts) {
    const bucket = feedDateBucket(p.published_at);
    if (!grouped.has(bucket)) grouped.set(bucket, []);
    grouped.get(bucket).push(p);
  }
  const html = [...grouped.entries()].map(([bucket, list], gi) => `
    <div class="tl-group">
      <div class="tl-group-head"><span>${escapeHtml(bucket)}</span>${gi === 0 ? `<span class="tl-group-count">已加载 ${_tlPosts.length} 条动态</span>` : ""}</div>
      ${list.map(postCard).join("")}
    </div>`).join("");
  const footer = _tlHasMore
    ? `<div id="feed-load-sentinel" class="tl-feed-more" role="status" aria-live="polite"></div>`
    : (posts.length ? `<p class="muted tl-feed-end">已加载全部</p>` : "");
  const hasFilter = state.timelineQ || state.timelinePlatform || state.timelineCategory || state.timelineTag;
  const emptyMsg = state.timelinePlatform === "zsxq"
    ? "星球动态不混入「全部」，订阅后会出现在这里"
    : state.timelineFavorite && !hasFilter
      ? "还没有特别关注大V的动态"
      : (hasFilter ? "没有符合条件的动态" : "还没有订阅任何大V");
  const emptyAction = hasFilter
    ? `<div><button class="btn-normal" onclick="tlResetFilters()">清除筛选</button></div>`
    : `<div><button class="btn-normal btn-add" onclick="go('home')">去订阅</button></div>`;
  feed.innerHTML = posts.length
    ? html + footer
    : emptyState(emptyMsg, emptyAction);
  startFeedAutoLoad();
  tlSyncActiveChips();
}

function toggleTimelineFav() {
  const revert = tlSnapshotFilters();
  state.timelineFavorite = !state.timelineFavorite;
  tlPaintViewToggles();
  tlSyncFilterChrome();
  loadTimeline(true, routeRenderSeq, { revert });
}

function toggleTimelineSecondary() {
  // 次要大V开关：默认关闭（动态页隐藏次要大V），开启后显示其动态。
  // 图标随状态切换：隐藏 = 划线眼睛（不看），显示 = 睁眼（看）。
  const revert = tlSnapshotFilters();
  state.timelineSecondary = !state.timelineSecondary;
  tlPaintViewToggles();
  tlSyncFilterChrome();
  loadTimeline(true, routeRenderSeq, { revert });
}

function tlTogglePost(id) {
  if (_tlExpanded.has(id)) _tlExpanded.delete(id);
  else _tlExpanded.add(id);
  const post = _tlPosts.find((p) => p.id === id) || _kolPagePosts.find((p) => p.id === id);
  const card = document.querySelector(`.post-item[data-post-id="${id}"]`);
  if (post && card) {
    const wrap = document.createElement("div");
    wrap.innerHTML = postCard(post).trim();
    const next = wrap.firstElementChild;
    if (next) {
      // 换卡会丢掉正在播放的语音按钮，先停掉避免出现"无声播放"的孤儿音频
      if (_mxAudioBtn && card.contains(_mxAudioBtn)) stopMxAudio();
      card.replaceWith(next);
      return;
    }
  }
  renderTimelineFeed();
}

// published_at 支持 "YYYY-MM-DD HH:MM(:SS)"（雪球）与 RFC2822（微博/X 存 GMT/+0000），
// 解析成 Date 后按本地时区展示；无法解析返回 null（回退原样显示）
function parsePublished(s) {
  const raw = String(s || "").trim();
  if (!raw) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?/.exec(raw);
  if (m) return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4] - 8, +m[5], +(m[6] || 0)));
  const d = new Date(raw); // RFC2822 等 JS 可解析格式（带时区偏移，正确换算本地时间）
  return isNaN(d.getTime()) ? null : d;
}

function fmtPublished(s, clockOnly = false) {
  const d = parsePublished(s);
  if (!d) return escapeHtml(s || "");
  const now = new Date();
  const p = (n) => String(n).padStart(2, "0");
  // 统一精确到秒：时间线消息次序存疑时（同分钟多条），秒位是唯一可信依据
  const clock = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  if (clockOnly) return clock;
  const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (sameDay(d, now)) return `今天 ${clock}`;
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (sameDay(d, yesterday)) return `昨天 ${clock}`;
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}月${d.getDate()}日 ${clock}`;
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日 ${clock}`;
}

function feedDateBucket(s) {
  const d = parsePublished(s);
  if (!d) return "更早";
  const now = new Date();
  const p = (n) => String(n).padStart(2, "0");
  const dateKey = (x) => `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())}`;
  const today = dateKey(now);
  const yesterday = dateKey(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
  const key = dateKey(d);
  if (key === today) return "今天";
  if (key === yesterday) return "昨天";
  // 今年内按具体日期分组（如 8月3日），跨年才归入「更早」
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}月${d.getDate()}日`;
  return "更早";
}

function postFiles(post) {
  let d = post.detail;
  if (typeof d === "string" && d) {
    try { d = JSON.parse(d); } catch { return []; }
  }
  return Array.isArray(d?.files) ? d.files.filter((f) => f && (f.url || f.name)) : [];
}

// MX 附件消息：MX 帖的 detail 是入库时的原始消息，msg 字段是 JSON 数组字符串。
// type=file 的项按后端 looks_like_image_url 同口径拆分：图片类已由后端转 images
// 不重复显示，其余（语音/PDF 等）作为附件——音频渲染播放按钮，其他渲染直链
const MX_IMG_EXT_RE = /\.(png|jpe?g|gif|webp|bmp|avif)$/i;
const MX_ANY_EXT_RE = /\.[A-Za-z0-9]{2,5}$/;
const MX_AUDIO_EXT_RE = /\.(mp3|m4a|aac|wav|ogg|oga|opus|amr|flac)$/i;

function mxLooksLikeImage(url, name) {
  const urlPath = String(url || "").split(/[?#]/)[0];
  const namePath = String(name || "").split(/[?#]/)[0];
  if (MX_IMG_EXT_RE.test(urlPath)) return true;
  if (MX_ANY_EXT_RE.test(urlPath)) return false;
  if (MX_ANY_EXT_RE.test(namePath)) return MX_IMG_EXT_RE.test(namePath);
  return true;
}

function mxAttachments(post) {
  if (post.platform !== "mx") return [];
  let detail = post.detail;
  if (typeof detail === "string" && detail) {
    try { detail = JSON.parse(detail); } catch { return []; }
  }
  if (!detail || typeof detail !== "object") return [];
  let msgList = detail.msg;
  if (typeof msgList === "string" && msgList) {
    try { msgList = JSON.parse(msgList); } catch { return []; }
  }
  if (!Array.isArray(msgList)) return [];
  return msgList
    .filter((item) => item && item.type === "file" && /^https?:\/\//i.test(String(item.url || "").trim()))
    .map((item) => {
      const url = String(item.url).trim();
      const name = String(item.name || "");
      if (mxLooksLikeImage(url, name)) return null; // 图片类已由后端转 images
      return {
        url,
        name,
        audio: MX_AUDIO_EXT_RE.test(url.split(/[?#]/)[0]) || MX_AUDIO_EXT_RE.test(name),
      };
    })
    .filter(Boolean);
}

function combinationDetailHtml(post) {
  let detail = post.detail;
  if (typeof detail === "string" && detail) {
    try { detail = JSON.parse(detail); } catch { return ""; }
  }
  if (!detail || typeof detail !== "object") return "";
  const stats = Array.isArray(detail.stats) ? detail.stats.filter((s) => Array.isArray(s) && s.length >= 2) : [];
  const actions = Array.isArray(detail.actions) ? detail.actions.filter((a) => a && typeof a === "object") : [];
  const holdings = Array.isArray(detail.holdings)
    ? detail.holdings.filter((h) => h && h.name && h.weight != null)
    : [];
  const sections = [];
  if (stats.length) {
    sections.push(`<div class="combo-stats">${stats.map(([key, value]) => `<span class="combo-stat"><b>${escapeHtml(key)}</b> ${escapeHtml(value)}</span>`).join("")}</div>`);
  }
  if (actions.length) {
    const rows = actions.map((a) => {
      const type = a.type || "调整";
      const stock = a.stock || a.symbol || "";
      const symbol = a.stock && a.symbol
        ? ` <span class="combo-sym">${escapeHtml(a.symbol)}</span>`
        : "";
      const price = a.price != null && String(a.price).trim()
        ? `<span class="combo-action-price">${escapeHtml(a.price)}</span>`
        : "";
      return `<div class="combo-action"><span class="combo-action-type">${escapeHtml(type)}</span><strong class="combo-action-name">${escapeHtml(stock)}${symbol}</strong><span class="combo-action-meta"><span class="combo-action-position">${escapeHtml(a.prev || "0.0%")} → ${escapeHtml(a.target || "0.0%")}</span>${price}</span></div>`;
    }).join("");
    sections.push(`<section class="combo-section"><h3 class="combo-section-title">调仓明细</h3><div class="combo-actions"><div class="combo-action combo-action-cols" aria-hidden="true"><span>操作</span><span>标的</span><span>仓位 / 成交价</span></div>${rows}</div></section>`);
  }
  if (holdings.length) {
    sections.push(`<section class="combo-section"><h3 class="combo-section-title">现有持仓</h3><div class="combo-holdings">${holdings.map((h) => {
      const name = h.name || h.symbol || "";
      const symbol = h.name && h.symbol ? ` <span class="combo-sym">${escapeHtml(h.symbol)}</span>` : "";
      return `<div class="combo-holding"><span>${escapeHtml(name)}${symbol}</span><span class="combo-w">${escapeHtml(h.weight)}%</span></div>`;
    }).join("")}</div></section>`);
  }
  if (detail.cash) sections.push(`<div class="combo-cash">现金 <b>${escapeHtml(detail.cash)}</b></div>`);
  return sections.length ? `<div class="combo-detail">${sections.join("")}</div>` : "";
}

function postCard(post) {
  const safeUrl = /^https?:\/\//i.test(post.url || "") ? post.url : "#";
  // 本会话已确认失效的配图直接过滤，重渲染不再为死链重建 <img>
  const images = (Array.isArray(post.images) ? post.images : []).filter((u) => u && !_deadImgUrls.has(u));
  const comboHtml = post.platform === "combination" ? combinationDetailHtml(post) : "";
  const isCombination = !!comboHtml;
  const body = post.content || "（无正文）";
  const expanded = _tlExpanded.has(post.id);
  const shown = expanded ? body : body.slice(0, 200);
  // X 帖常 title==content（如纯链接帖），标题和正文都渲染会视觉重复，跳过标题；
  // 长文帖 title 常为 content 开头一段（截断），同样跳过避免重复展示
  const titleDup = !!post.title && (
    post.title.trim() === (post.content || "").trim()
    || (post.content || "").trimStart().startsWith(post.title.trim())
  );
  return `
    <div class="post-item" data-post-id="${post.id}">
      <div class="p-header">
        ${avatarHtml(post.kol_name, post.avatar_url)}
        <div class="p-name-line">
          <a class="p-name" href="/kol/${post.kol_id}" title="${escapeHtml(post.kol_name)}">${escapeHtml(post.kol_name)}</a>
          <span class="p-platform" data-platform="${escapeHtml(post.platform)}" title="${escapeHtml(PLATFORM_LABELS[post.platform] || post.platform)}">
            ${PLATFORM_ICONS[post.platform] || ""}
          </span>
          <span class="p-time" title="${escapeHtml(post.published_at)}">${fmtPublished(post.published_at)}</span>
        </div>
      </div>
      ${isCombination ? `<div class="combo-post">${comboHtml}</div>` : `${!titleDup && post.title ? `<div class="p-title">${escapeHtml(post.title)}</div>` : ""}
      <div class="p-content md-body">${mdToHtml(shown)}${body.length > 200
        ? `<button class="post-expand-btn" onclick="tlTogglePost(${post.id})" aria-expanded="${expanded}">${expanded ? "收起 ▲" : "展开全文 ▼"}</button>`
        : ""}</div>`}
      ${images.length ? `
        <div class="post-images">
          ${images.slice(0, 4).map((img) => `
            <a class="post-img-link" href="#" onclick="event.preventDefault();openLightbox(this.querySelector('img'))" aria-label="查看${escapeHtml(post.kol_name)}的配图"><img src="${escapeHtml(imgSrcFor(img))}" loading="lazy" alt="${escapeHtml(post.kol_name)} 的配图" onerror="imgOnError(this)"></a>`).join("")}
          ${images.length > 4 ? `<span class="post-images-more">+${images.length - 4}</span>` : ""}
        </div>` : ""}
      ${postFiles(post).map((f) => {
          // 附件一律走鉴权路由（服务端校验订阅可见性，命中本地缓存时直接下发）；
          // 历史详情里缓存的 /zsxq-files/ 静态链接已随挂载移除，不再直连
          const href = f.file_id
            ? `/api/media/zsxq-file/${encodeURIComponent(f.file_id)}?token=${encodeURIComponent(state.token || "")}`
            : (f.url || "");
          return href
            ? `<a class="p-file" href="${escapeHtml(href)}" target="_blank" rel="noopener">📎 ${escapeHtml(f.name || "附件")}</a>`
            : `<span class="p-file">📎 ${escapeHtml(f.name || "附件")}</span>`;
        }).join("")}
      ${mxAttachments(post).map((f) => f.audio
        ? `<div class="mx-audio-row">
            <button type="button" class="mx-audio-btn" data-url="${escapeHtml(f.url)}" onclick="toggleMxAudio(this)">
              <span class="mx-audio-icon" aria-hidden="true">▶</span>
              <span class="mx-audio-label">${escapeHtml(f.name || "点击播放")}</span>
            </button>
          </div>`
        : `<a class="p-file" href="${escapeHtml(f.url)}" target="_blank" rel="noopener">📎 ${escapeHtml(f.name || "附件")}</a>`).join("")}
      <div class="p-meta">
        ${post.category_name ? `<span class="cat">${escapeHtml(post.category_name)}</span>` : ""}
        ${post.post_type === "reply" ? `<span class="cat">回复</span>` : ""}
        ${renderPostTagChips(post.tags)}
        ${post.platform === "zsxq" ? "" : RAW_MODAL_LABELS[post.platform]
          ? `<a href="#" onclick="event.preventDefault();openRawModal(${post.id}, '${RAW_MODAL_LABELS[post.platform]}')" title="查看${RAW_MODAL_LABELS[post.platform]}原始消息">查看原文 →</a>`
          : `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener">查看原文 →</a>`}
      </div>
    </div>`;
}

// 标签徽章：最多直接显示 6 个，超出折叠进「更多N」，点击展开/收起
function renderPostTagChips(tags) {
  if (!Array.isArray(tags) || !tags.length) return "";
  const chip = (t) => `<button type="button" class="cat cat-tag post-tag-filter" data-tag="${escapeHtml(t)}" onclick="tlPickTag(this.dataset.tag)">${escapeHtml(t)}</button>`;
  if (tags.length <= 6) return tags.map(chip).join("");
  return `${tags.slice(0, 6).map(chip).join("")}` +
    `<span class="tag-extra" hidden>${tags.slice(6).map(chip).join("")}</span>` +
    `<button type="button" class="cat cat-tag tags-more-btn" data-n="${tags.length - 6}" onclick="togglePostTags(this)">更多${tags.length - 6}</button>`;
}

function togglePostTags(btn) {
  const extra = btn.previousElementSibling;
  if (!extra || !extra.classList.contains("tag-extra")) return;
  const open = !extra.hidden;
  extra.hidden = open;
  btn.textContent = open ? `更多${btn.dataset.n || ""}` : "收起";
}

// 无外部原文链接的平台（MX/系统 KOL）「查看原文」弹窗展示入库时保存的原始消息：
// MX = 推送解密后的原始 JSON；系统 KOL = webhook 入站原始 payload（posts.detail）
const RAW_MODAL_LABELS = { mx: "MX", system: "系统 KOL" };

function openRawModal(postId, label) {
  const post = _tlPosts.find((p) => p.id === postId) || _kolPagePosts.find((p) => p.id === postId) || (Array.isArray(window._mxvPosts) ? window._mxvPosts.find((p) => p.id === postId) : null);
  if (!post) return;
  closeRawModal(); // 防连点叠开
  let detail = post.detail;
  if (typeof detail === "string" && detail) {
    try { detail = JSON.parse(detail); } catch { /* 非 JSON 字符串按原样展示 */ }
  }
  const hasRaw = typeof detail === "object" && detail !== null
    ? Object.keys(detail).length > 0
    : String(detail ?? "").trim().length > 0;
  const text = hasRaw && typeof detail === "object" ? JSON.stringify(detail, null, 2) : String(detail ?? "");
  const who = post.kol_name ? `${escapeHtml(post.kol_name)} · ` : "";
  const isAdmin = !!state.user?.is_admin;
  const mask = document.createElement("div");
  mask.className = "modal-mask mx-raw-mask";
  mask.setAttribute("role", "dialog");
  mask.setAttribute("aria-modal", "true");
  mask.setAttribute("aria-label", `${label} 原始消息`);
  mask.innerHTML = `
    <div class="modal-card mx-raw-card">
      <h3 class="mx-raw-title">${escapeHtml(label)} 原始消息</h3>
      <p class="mx-raw-meta">${who}${fmtPublished(post.published_at, true)}</p>
      ${text
        ? `<button type="button" class="btn-ghost mx-raw-copy" onclick="copyText(mxRawModalText(), '已复制原始消息')">复制 JSON</button>
           <pre class="mx-raw-pre">${escapeHtml(text)}</pre>`
        : `<p class="mx-raw-empty muted">该消息没有保存原始数据</p>`}
      <div class="mx-raw-tags">
        <div class="mx-raw-tags-title">标签</div>
        <div class="mx-raw-tags-list" id="mx-raw-tags-list">${mxRawTagsHtml(post.tags, isAdmin)}</div>
        ${isAdmin ? `
        <div class="mx-raw-tag-add">
          <input id="mx-raw-tag-input" class="form-control" maxlength="30" placeholder="输入新标签，回车或点添加" onkeydown="if(event.key==='Enter'){event.preventDefault();mxRawAddTag();}">
          <button type="button" class="btn-sm" onclick="mxRawAddTag()">添加标签</button>
        </div>` : ""}
      </div>
    </div>`;
  mask._rawText = text;
  mask._postId = postId;
  mask.addEventListener("click", (e) => {
    if (e.target === mask) closeRawModal();
  });
  mask._onKey = (e) => {
    if (e.key === "Escape") {
      // 正在输入标签时按 Escape：先清空输入，再按才关弹窗
      if (e.target && e.target.id === "mx-raw-tag-input" && e.target.value) {
        e.target.value = "";
        e.preventDefault();
        return;
      }
      e.preventDefault();
      closeRawModal();
    }
  };
  document.addEventListener("keydown", mask._onKey, true);
  document.body.appendChild(mask);
}

// 原始消息弹窗里的标签徽章：管理员带 × 删除按钮
function mxRawTagsHtml(tags, isAdmin) {
  const list = Array.isArray(tags) ? tags : [];
  const chips = list.map((t) => `
    <span class="cat cat-tag mx-raw-tag">${escapeHtml(t)}${isAdmin
      ? `<button type="button" class="mx-raw-tag-del" data-tag="${escapeHtml(t)}" aria-label="删除标签 ${escapeHtml(t)}" title="删除标签 ${escapeHtml(t)}" onclick="mxRawRemoveTag(this.dataset.tag)">×</button>`
      : ""}</span>`).join("");
  return chips || '<span class="muted mx-raw-tag-empty">暂无标签</span>';
}

function _mxRawModalPost() {
  const mask = document.querySelector(".mx-raw-mask");
  if (!mask) return null;
  return _tlPosts.find((p) => p.id === mask._postId)
    || _kolPagePosts.find((p) => p.id === mask._postId)
    || null;
}

function mxRawRenderTags(tags) {
  const list = document.getElementById("mx-raw-tags-list");
  if (list) list.innerHTML = mxRawTagsHtml(tags, !!state.user?.is_admin);
}

// 增删标签后同步内存缓存，并热替换背后的帖子卡片（关弹窗即见新标签，不用整页刷新）
function _syncPostTags(postId, tags) {
  if (!Array.isArray(tags)) return;
  const post = _tlPosts.find((p) => p.id === postId) || _kolPagePosts.find((p) => p.id === postId);
  if (post) post.tags = tags;
  const card = document.querySelector(`.post-item[data-post-id="${postId}"]`);
  if (!post || !card) return;
  const wrap = document.createElement("div");
  wrap.innerHTML = postCard(post).trim();
  const next = wrap.firstElementChild;
  if (next) {
    // 换卡会丢掉正在播放的语音按钮，先停掉避免出现"无声播放"的孤儿音频
    if (_mxAudioBtn && card.contains(_mxAudioBtn)) stopMxAudio();
    card.replaceWith(next);
  }
}

async function mxRawAddTag() {
  const post = _mxRawModalPost();
  const input = document.getElementById("mx-raw-tag-input");
  const tag = (input?.value || "").trim();
  if (!post || !tag) return;
  try {
    const data = await api(`/api/admin/posts/${post.id}/tags/add`, {
      method: "POST",
      body: JSON.stringify({ tag }),
    });
    if (input) input.value = "";
    _syncPostTags(post.id, data.tags);
    mxRawRenderTags(data.tags);
    flash(`已添加标签「${tag}」`);
  } catch (err) {
    flash("添加失败: " + err.message, "error");
  }
}

async function mxRawRemoveTag(tag) {
  const post = _mxRawModalPost();
  if (!post || !tag) return;
  try {
    const data = await api(`/api/admin/posts/${post.id}/tags/remove`, {
      method: "POST",
      body: JSON.stringify({ tag }),
    });
    _syncPostTags(post.id, data.tags);
    mxRawRenderTags(data.tags);
    flash(`已删除标签「${tag}」`);
  } catch (err) {
    flash("删除失败: " + err.message, "error");
  }
}

// 复制按钮取当前弹窗内存的原文（避免从 DOM 读 pre 文本时转义还原出错）
function mxRawModalText() {
  return document.querySelector(".mx-raw-mask")?._rawText || "";
}

function closeRawModal() {
  const mask = document.querySelector(".mx-raw-mask");
  if (!mask) return;
  document.removeEventListener("keydown", mask._onKey, true);
  mask.remove();
}

// ---------- MX 语音播放 ----------
// 全局同一时刻只播一条语音：点击按钮用 <audio> 直接拉 MX CDN 音频流（源公开可访问、
// 支持 Range，无需代理）；再点一次停止，点其他语音自动停掉上一条
let _mxAudio = null;
let _mxAudioBtn = null;

function _mxPaintAudioBtn(btn, icon, label, cls = "") {
  if (!btn) return;
  btn.classList.remove("loading", "playing");
  if (cls) btn.classList.add(cls);
  const iconEl = btn.querySelector(".mx-audio-icon");
  const labelEl = btn.querySelector(".mx-audio-label");
  if (iconEl) iconEl.textContent = icon;
  if (labelEl) labelEl.textContent = label;
}

function stopMxAudio() {
  const audio = _mxAudio;
  const btn = _mxAudioBtn;
  _mxAudio = null;
  _mxAudioBtn = null;
  if (audio) {
    audio.pause();
    audio.removeAttribute("src");
    audio.load(); // 释放未播完的下载连接
  }
  _mxPaintAudioBtn(btn, "▶", "点击播放");
}

function toggleMxAudio(btn) {
  const url = btn.dataset.url || "";
  if (!/^https?:\/\//i.test(url)) return;
  if (_mxAudioBtn === btn) { stopMxAudio(); return; }
  stopMxAudio();
  const audio = new Audio(url);
  _mxAudio = audio;
  _mxAudioBtn = btn;
  _mxPaintAudioBtn(btn, "⟳", "加载中…", "loading");
  const isCurrent = () => _mxAudio === audio;
  audio.addEventListener("playing", () => {
    if (isCurrent()) _mxPaintAudioBtn(btn, "⏸", "播放中…", "playing");
  });
  audio.addEventListener("ended", () => {
    if (isCurrent()) stopMxAudio();
  });
  const fail = () => {
    // 主动 stop 时 removeAttribute+load 会连带触发 error，此时不算失败
    if (!isCurrent()) return;
    stopMxAudio();
    _mxPaintAudioBtn(btn, "✕", "播放失败");
    setTimeout(() => { if (_mxAudioBtn !== btn) _mxPaintAudioBtn(btn, "▶", "点击播放"); }, 2000);
  };
  audio.addEventListener("error", fail);
  audio.play().catch(fail);
}

// ---------- 搜索 ----------
async function renderSearch(seq) {
  setPageTitle("搜索", true);
  const params = routeQuery();
  const query = params.get("q") || "";
  $("#main").innerHTML = `
    <section class="section-panel">
      <div class="search-bar" style="margin-bottom:16px">
        ${SEARCH_ICON}
        <input id="search-input" placeholder="输入昵称或 ID，回车搜索" value="${escapeHtml(query)}" onkeydown="if(event.key==='Enter')runSearch()">
        <button class="btn-ghost" onclick="runSearch()">搜索</button>
      </div>
      <div id="search-result" class="kol-grid">${emptyState("加载中…")}</div>
    </section>`;
  if (!state.user?.is_admin) {
    let cats = [];
    try { cats = await api("/api/categories"); } catch (err) { cats = []; }
    if (!routeStillActive(seq)) return;
    const catOptions = cats.map((c) => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join("");
    const askSection = document.createElement("div");
    askSection.innerHTML = `
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">申请添加大V</h2>
          <p class="section-meta">目录里没有的大V？提交申请，管理员审批通过后即可订阅。</p></div>
        </header>
        <div class="toolbar" style="margin-top:12px">
          <select id="ask-platform" class="form-control" style="margin:0;width:auto">
            <option value="xueqiu">雪球</option>
            <option value="combination">雪球组合</option>
            <option value="weibo">微博</option>
            <option value="twitter">X</option>
            <option value="zsxq">知识星球</option>
          </select>
          <select id="ask-category" class="form-control" style="margin:0;width:auto" aria-label="分类" required>
            <option value="">请选择分类</option>${catOptions}
          </select>
          <input id="ask-link" class="form-control" style="margin:0;flex:1;min-width:220px" placeholder="大V主页链接或 ID" oninput="onAskLinkInput()">
          <button class="btn-normal" onclick="submitAsk()">提交申请</button>
        </div>
        <div id="ask-result" class="muted" style="margin-top:12px"></div>
      </section>
      <section class="section-panel">
        <header class="section-head"><div><h2 class="section-title">我的申请</h2></div></header>
        <div id="my-asks"></div>
      </section>`;
    // 先取引用再 append：第一次 appendChild 会移动节点，children[1] 会随之失效
    const askPanel = askSection.firstElementChild;
    const myAskPanel = askSection.children[1];
    $("#main").appendChild(askPanel);
    $("#main").appendChild(myAskPanel);
    loadMyAsks(seq);
  }
  await doSearch(seq);
  if (!query && routeStillActive(seq)) $("#search-input")?.focus();
}


function detectAskPlatform(link) {
  // 与后端 _detect_platform_from_link 同规则：输入链接时自动甄别平台
  if (/(?:xueqiu\.com\/P\/|ZH\d)/.test(link)) return "combination";
  if (link.includes("xueqiu.com")) return "xueqiu";
  if (/weibo\.(com|cn)/.test(link)) return "weibo";
  if (/(^|[\/:.])x\.com|twitter\.com/.test(link)) return "twitter";
  if (/(?:wx\.)?zsxq\.com/.test(link)) return "zsxq";
  return "";
}

function onAskLinkInput() {
  // 粘贴链接时自动甄别平台：识别出其他平台则自动切换下拉并提示
  const link = $("#ask-link").value.trim();
  const detected = detectAskPlatform(link);
  const sel = $("#ask-platform");
  if (!detected || !sel || sel.value === detected) return;
  sel.value = detected;
  showAskResult(`已识别为「${PLATFORM_LABELS[detected]}」主页链接，平台已自动切换`, false);
}

function showAskResult(msg, isError) {
  const el = $("#ask-result");
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle("ask-error", !!isError);
  el.classList.toggle("ask-ok", !isError);
}

async function submitAsk() {
  const external_id = $("#ask-link").value.trim();
  const category_id = $("#ask-category") && $("#ask-category").value;
  if (!external_id) {
    showAskResult("请填写大V主页链接或 ID", true);
    return;
  }
  if (!category_id) {
    showAskResult("请选择分类", true);
    return;
  }
  try {
    await api("/api/kol-requests", {
      method: "POST",
      body: JSON.stringify({ platform: $("#ask-platform").value, external_id, category_id: Number(category_id) }),
    });
    $("#ask-link").value = "";
    showAskResult("已提交 ✅ 管理员审批通过后会自动出现在订阅广场", false);
    loadMyAsks();
  } catch (err) {
    showAskResult(err.message, true); // 后端返回具体的纠错提示（平台切换/链接格式）
  }
}

async function loadMyAsks(routeSeq) {
  try {
    const asks = await api("/api/my/kol-requests");
    if (!routeStillActive(routeSeq)) return; // 已切走：不写旧页面
    const statusMap = { pending: "待审批", approved: "已通过 ✅", rejected: "已拒绝" };
    $("#my-asks").innerHTML = asks.length
      ? `<div class="table-wrap"><table>
          <thead><tr><th scope="col">平台</th><th scope="col">外部 ID</th><th scope="col">分类</th><th scope="col">状态</th><th scope="col">提交时间</th></tr></thead>
          <tbody>${asks.map((a) => `
            <tr>
              <td>${PLATFORM_LABELS[a.platform] || escapeHtml(a.platform)}</td>
              <td>${escapeHtml(a.external_id)}</td>
              <td>${escapeHtml(a.category_name || "—")}</td>
              <td class="${a.status === "approved" ? "status-ok" : a.status === "rejected" ? "status-fail" : ""}">${statusMap[a.status] || escapeHtml(a.status)}</td>
              <td>${escapeHtml(fmtDbTime(a.created_at))}</td>
            </tr>`).join("")}</tbody>
        </table></div>`
      : emptyState("还没有提交过申请");
  } catch {
    /* 忽略加载失败 */
  }
}

async function doSearch(routeSeq) {
  const input = $("#search-input");
  if (!input) return;
  const keyword = input.value.trim().toLowerCase();
  try {
    const kols = await api("/api/catalog");
    if (!routeStillActive(routeSeq)) return;
    state.catalog = kols;
    const available = kols.filter((k) => !k.subscribed);
    const hits = keyword
      ? available.filter(
        (k) => (k.name || "").toLowerCase().includes(keyword)
          || (k.external_id || "").toLowerCase().includes(keyword)
      )
      : available;
    const target = $("#search-result");
    if (!target) return;
    target.innerHTML = hits.length
      ? hits.map(kolCard).join("")
      : emptyState(keyword ? "没有匹配的未订阅大V" : "所有大V都已订阅");
  } catch (err) {
    if (!routeStillActive(routeSeq)) return;
    const target = $("#search-result");
    if (target) target.innerHTML = emptyState("搜索失败: " + err.message);
  }
}

// ---------- 大V动态页 ----------
let _kolPagePosts = []; // 当前大V动态页已渲染的帖子（展开全文在非时间线路由下的取数兜底）

async function renderKolPage(kolId, seq) {
  setPageTitle("大V动态", true);
  $("#main").innerHTML = `<div class="empty">加载中…</div>`;
  try {
    const kol = await api(`/api/kols/${kolId}`);
    const posts = await api(`/api/kols/${kolId}/posts?limit=50`);
    if (!routeStillActive(seq)) return; // 已切走：不写旧页面
    _kolPagePosts = posts;
    const extra = kol.platform === "combination"
      ? await renderCombinationSnapshots(kol)
      : "";
    if (!routeStillActive(seq)) return;
    $("#main").innerHTML = `
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">${escapeHtml(kol.name)} · 最近动态</h2>
            <p class="section-meta">外部 ID：${escapeHtml(kol.external_id)} · ${PLATFORM_LABELS[kol.platform] || escapeHtml(kol.platform)}${kol.category_name ? " · " + escapeHtml(kol.category_name) : ""}</p>
          </div>
          <div class="toolbar" style="margin-top:12px">
            ${kol.subscribed && kol.platform === "xueqiu" ? subTypeSwitchesHtml(kol.id, kol.subscribe_type || "post") : ""}
            <button class="btn-sub ${kol.subscribed ? "subscribed" : ""}" id="kol-sub-btn" onclick="toggleKolPageSubscribe(${kol.id})">
              ${kol.subscribed ? "✓ 已订阅" : "订阅"}
            </button>
          </div>
        </header>
        ${extra}
        <div class="search-bar" style="margin:14px 0 12px">
          ${SEARCH_ICON}
          <input id="kol-posts-search" placeholder="搜索该大V的消息内容，即时过滤" aria-label="搜索该大V的消息内容" oninput="kolPageSearchInput(${kol.id}, ${seq})">
        </div>
        <div id="kol-posts">${kolPostsListHtml(posts, "")}</div>
      </section>`;
  } catch (err) {
    if (!routeStillActive(seq)) return;
    $("#main").innerHTML = emptyState("加载失败: " + err.message);
  }
}

function kolPostsListHtml(posts, q) {
  if (!posts.length) return emptyState(q ? `没有匹配「${q}」的动态` : "暂无动态");
  const meta = q ? `<p class="section-meta" style="margin-bottom:10px">匹配 ${posts.length} 条动态（搜索范围为最近 200 条）</p>` : "";
  return meta + posts.map(postCard).join("");
}

let _kolPageSearchTimer = null;
function kolPageSearchInput(kolId, seq) {
  const input = $("#kol-posts-search");
  if (!input) return;
  const q = input.value.trim();
  clearTimeout(_kolPageSearchTimer);
  _kolPageSearchTimer = setTimeout(async () => {
    try {
      const target = $("#kol-posts");
      if (!target || !routeStillActive(seq)) return;
      // 关键词搜索时扩大回溯范围到 200 条（后端上限 500）；空关键词回到最近 50 条
      const posts = await api(`/api/kols/${kolId}/posts?limit=${q ? 200 : 50}&q=${encodeURIComponent(q)}`);
      if (!routeStillActive(seq)) return;
      const list = $("#kol-posts");
      if (!list) return; // 输入期间已切走
      _kolPagePosts = posts;
      list.innerHTML = kolPostsListHtml(posts, q);
    } catch (err) {
      flash("搜索失败: " + err.message, "error");
    }
  }, 250);
}

async function renderCombinationSnapshots(kol) {
  try {
    const [holdings, nav] = await Promise.all([
      api(`/api/kols/${kol.id}/holdings`),
      api(`/api/kols/${kol.id}/nav`),
    ]);
    const q = kol.quote || {};
    const quoteHtml = q.day_percent_gain != null || q.net_value != null ? `
      <div class="cube-quote">
        <div class="cube-quote-item"><span class="cube-quote-label">净值</span><span class="cube-quote-value">${q.net_value != null ? q.net_value.toFixed(3) : "—"}</span></div>
        <div class="cube-quote-item"><span class="cube-quote-label">今日涨跌</span><span class="cube-quote-value ${q.day_percent_gain != null ? (q.day_percent_gain >= 0 ? "up" : "down") : ""}">${q.day_percent_gain != null ? (q.day_percent_gain >= 0 ? "+" : "") + q.day_percent_gain.toFixed(2) + "%" : "—"}</span></div>
        ${kol.quote_at ? `<div class="cube-quote-item"><span class="cube-quote-label">快照</span><span class="cube-quote-value small">${escapeHtml(formatSnapshotTs(kol.quote_at))}</span></div>` : ""}
      </div>` : "";
    const rows = (holdings.holdings || []).map((h) => {
      const delta = h.prev != null && Math.abs(h.weight - h.prev) >= 0.01
        ? `${h.weight >= h.prev ? "+" : ""}${(h.weight - h.prev).toFixed(1)}`
        : "";
      return { ...h, delta };
    });
    if (holdings.cash != null) rows.push({ name: "现金", symbol: "CASH", weight: holdings.cash, delta: "" });
    const holdingsHtml = rows.length ? `
      <div class="cube-holdings">
        ${rows.map((h) => `
          <div class="cube-holding">
            <div class="cube-holding-head">
              <span class="cube-holding-name" title="${escapeHtml(h.symbol)}">${escapeHtml(h.name)}</span>
              <span class="cube-holding-weight">${h.weight}%${h.delta ? ` <em class="cube-holding-delta ${Number(h.delta) >= 0 ? "up" : "down"}">${h.delta}</em>` : ""}</span>
            </div>
            <div class="cube-weight-bar"><div class="cube-weight-fill" style="width:${Math.max(h.weight, 1)}%"></div></div>
          </div>`).join("")}
        ${holdings.updated_at ? `<p class="section-meta" style="margin-top:10px">持仓更新于 ${escapeHtml(formatSnapshotTs(holdings.updated_at))}</p>` : ""}
      </div>` : `<p class="section-meta">暂无持仓数据（订阅后自动抓取）</p>`;
    const navHtml = (nav.series || []).length >= 2 ? `
      <div class="cube-nav-head">
        <b>最新 ${nav.series[nav.series.length - 1].value}</b>
        <span class="section-meta">${escapeHtml(nav.series[nav.series.length - 1].date)}${(nav.benchmark || []).length >= 2 ? " · 对照沪深300" : ""}</span>
      </div>
      ${navChartSvg(nav.series, nav.benchmark)}` : `<p class="section-meta">暂无净值数据（订阅后自动抓取）</p>`;
    return `
      ${quoteHtml ? `<section class="section-panel"><h2 class="section-title">组合状态</h2>${quoteHtml}</section>` : ""}
      <section class="section-panel"><h2 class="section-title">当前持仓</h2>${holdingsHtml}</section>
      <section class="section-panel"><h2 class="section-title">净值走势</h2>${navHtml}</section>`;
  } catch (err) {
    return `<section class="section-panel"><p class="section-meta">组合数据加载失败：${escapeHtml(err.message)}</p></section>`;
  }
}

// 后端快照时间（UTC "YYYY-MM-DD HH:MM:SS"）转本地 "MM-DD HH:MM"
function formatSnapshotTs(ts) {
  const d = new Date(String(ts).replace(" ", "T") + "Z");
  if (isNaN(d.getTime())) return ts;
  const p = (n) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

// 净值曲线：手绘 SVG 折线（含渐变面积、网格、首/中/尾日期），A股红涨绿跌
function navChartSvg(series, benchmark) {
  const W = 640, H = 200, padL = 44, padR = 10, padT = 10, padB = 24;
  let cube = series;
  let bench = null;
  if (benchmark && benchmark.length >= 2) {
    const bm = Object.fromEntries(benchmark.map((p) => [p.date, p.value]));
    const aligned = series.filter((p) => bm[p.date] != null);
    if (aligned.length >= 2 && aligned[0].value && bm[aligned[0].date]) {
      const c0 = aligned[0].value;
      const b0 = bm[aligned[0].date];
      cube = aligned.map((p) => ({ date: p.date, value: p.value / c0 }));
      bench = aligned.map((p) => ({ date: p.date, value: bm[p.date] / b0 }));
    }
  }
  const vals = cube.map((p) => p.value).concat(bench ? bench.map((p) => p.value) : []);
  let min = Math.min(...vals);
  let max = Math.max(...vals);
  if (max - min < 1e-9) { max += 0.005; min -= 0.005; }
  const span = max - min;
  min -= span * 0.05;
  max += span * 0.05;
  const X = (i) => padL + (i / (cube.length - 1)) * (W - padL - padR);
  const Y = (v) => padT + (1 - (v - min) / (max - min)) * (H - padT - padB);
  const pts = cube.map((p, i) => `${X(i).toFixed(1)},${Y(p.value).toFixed(1)}`).join(" ");
  const up = series[series.length - 1].value >= series[0].value;
  const cssVar = up ? "--color-data-positive" : "--color-data-negative";
  const color = getComputedStyle(document.documentElement).getPropertyValue(cssVar).trim() || (up ? "#b05b63" : "#23714a");
  const muted = getComputedStyle(document.documentElement).getPropertyValue("--color-text-muted").trim() || "#6e6e73";
  const base = (H - padB).toFixed(1);
  const area = `M${X(0).toFixed(1)},${base} L${pts.replace(/ /g, " L")} L${X(cube.length - 1).toFixed(1)},${base} Z`;
  const grid = [0, 1, 2, 3].map((i) => {
    const v = min + ((max - min) * i) / 3;
    return `<line x1="${padL}" y1="${Y(v).toFixed(1)}" x2="${W - padR}" y2="${Y(v).toFixed(1)}" class="cube-nav-grid"/>`
      + `<text x="4" y="${(Y(v) + 3).toFixed(1)}" class="cube-nav-tick">${v.toFixed(3)}</text>`;
  }).join("");
  const first = cube[0], mid = cube[Math.floor(cube.length / 2)], last = cube[cube.length - 1];
  const benchLine = bench
    ? `<polyline points="${bench.map((p, i) => `${X(i).toFixed(1)},${Y(p.value).toFixed(1)}`).join(" ")}" fill="none" stroke="${muted}" stroke-width="1.5" stroke-dasharray="4 3" stroke-linejoin="round"/>`
    : "";
  return `<svg viewBox="0 0 ${W} ${H}" class="cube-nav-svg" role="img" aria-label="净值曲线">
    ${grid}
    <path d="${area}" fill="${up ? "var(--color-data-positive-soft)" : "var(--color-data-negative-soft)"}"/>
    ${benchLine}
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
    <text x="${padL}" y="${H - 6}" class="cube-nav-date">${escapeHtml(first.date)}</text>
    <text x="${(padL + W - padR) / 2}" y="${H - 6}" text-anchor="middle" class="cube-nav-date">${escapeHtml(mid.date)}</text>
    <text x="${W - padR}" y="${H - 6}" text-anchor="end" class="cube-nav-date">${escapeHtml(last.date)}</text>
    <text x="${W - padR}" y="${(Y(last.value) - 5).toFixed(1)}" text-anchor="end" class="cube-nav-last" fill="${color}">${series[series.length - 1].value}</text>
  </svg>`;
}


async function toggleKolPageSubscribe(kolId) {
  await toggleSubscribe(kolId, $("#kol-sub-btn"));
}


function statsTabsHtml(active = "config") {
  const labels = {
    config: "抓取设置",
    cookies: "Cookie 管理",
    mx: "MX平台",
    imgbed: "图床设置",
    proxies: "代理",
    plaza: "广场显示",
    news: "财经资讯",
  };
  return `<div class="settings-tabs" role="tablist" aria-label="数据源管理">
    ${STATS_TABS.map((tab) => `<button type="button" class="settings-tab ${tab === active ? "active" : ""}" role="tab" id="tab-${tab}" aria-selected="${tab === active}" aria-controls="st-${tab}" data-tab="${tab}" onclick="switchStatsTab('${tab}')">${labels[tab]}</button>`).join("")}
  </div>`;
}

function statsTabFromHash() {
  const tab = routeQuery().get("tab") || "config";
  if (tab === "overview" || tab === "health") return "legacy-dashboard";
  return STATS_TABS.includes(tab) ? tab : "config";
}

function switchStatsTab(name) {
  // 数据源页分段导航：抓取设置 / Cookie 管理 / MX平台 / 图床设置 / 代理 / 广场显示 / 财经资讯
  if (name === "legacy-dashboard" || name === "overview" || name === "health") {
    replaceRoute("admin/dashboard");
    return;
  }
  if (!STATS_TABS.includes(name)) name = "config";
  if (name === "news") {
    stopStatsTimer();
    const next = "/admin/stats?tab=news";
    if (location.pathname + location.search !== next) history.replaceState(null, "", next);
    loadAdminNews(routeRenderSeq);
    return;
  }
  document.querySelectorAll(".settings-tab[data-tab]").forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("active", on);
    if (STATS_TABS.includes(b.dataset.tab)) b.setAttribute("aria-selected", String(on));
  });
  STATS_TABS.forEach((t) => {
    const el = document.getElementById("st-" + t);
    if (!el) return;
    const on = t === name;
    el.style.display = on ? "" : "none";
    el.hidden = !on;
  });
  const next = name === "config" ? "/admin/stats" : `/admin/stats?tab=${name}`;
  if (location.pathname + location.search !== next) history.replaceState(null, "", next);
  document.getElementById(`tab-${name}`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  if (name === "proxies") loadProxyAdmin();
  if (name === "mx") loadMxAdmin();
  if (name === "config" && !imaMountState.discoveryEntered) {
    imaMountState.discoveryEntered = true;
    discoverImaGroups();
  }
}

function cookieRepairItems(s) {
  const items = [];
  const src = {};
  (s.sources || []).forEach((row) => { src[row.platform] = row; });
  const live = (s.kol_health || []).filter((k) => k.enabled);
  const hasXq = live.some((k) => k.platform === "xueqiu" || k.platform === "combination");
  const hasWb = live.some((k) => k.platform === "weibo");
  const hasTw = live.some((k) => k.platform === "twitter");
  const xq = s.xueqiu_cookie || {};
  const xqErr = `${src.xueqiu?.last_error || ""} ${src.combination?.last_error || ""}`;
  const xqSick = /cookie|waf|反爬|401|403|失效|登录/i.test(xqErr);
  if (hasXq && !xq.set) items.push({ key: "xq-missing", label: "雪球 Cookie 未写入" });
  else if (hasXq && src.xueqiu && !src.xueqiu.ok && xqSick) {
    items.push({ key: "xq-bad", label: "雪球 Cookie 可能失效" });
  }
  const wb = src.weibo;
  if (hasWb && wb && !wb.ok && /登录|login|cookie|会话/i.test(wb.last_error || "")) {
    items.push({ key: "wb-bad", label: "微博登录态失效，可扫码续期" });
  }
  const tw = s.twitter_cookie || {};
  const twReason = src.twitter?.direct_fallback_reason || src.twitter?.last_error || "";
  if (hasTw && src.twitter?.direct_mode === "fallback" && /cookie|401|403|89|32|未配置|twitter/i.test(twReason)) {
    items.push({ key: "x-bad", label: "X Cookie 可能失效" });
  } else if (hasTw && !tw.set) {
    items.push({ key: "x-missing", label: "X Cookie 未写入" });
  }
  const hasZq = live.some((k) => k.platform === "zsxq");
  const zqCookie = s.zsxq_cookie || {};
  const zqErr = src.zsxq?.last_error || "";
  if (hasZq && !zqCookie.set) items.push({ key: "zq-missing", label: "知识星球 Cookie 未写入" });
  else if (hasZq && src.zsxq && !src.zsxq.ok && /cookie|401|1059|登录|token/i.test(zqErr)) {
    items.push({ key: "zq-bad", label: "知识星球 Cookie 可能失效" });
  }
  return items;
}

function cookieRepairBanner(s) {
  const items = cookieRepairItems(s);
  if (!items.length) return "";
  return `<div class="notice notice-warn" role="status">
    <div class="notice-warn-body">
      <strong>Cookie 需要更新</strong>
      <p>${items.map((i) => escapeHtml(i.label)).join("；")}。保存后即时生效，不用改配置文件、不用重启。</p>
    </div>
    <button type="button" class="btn-normal" onclick="go('admin/stats?tab=cookies')">去更新</button>
  </div>`;
}

function cookieUpdatedLabel(info) {
  if (!info || !info.set) return "未写入";
  if (info.from_env) return "已从环境变量读取";
  return info.updated_at ? `已写入（${escapeHtml(fmtTs(info.updated_at))}）` : "已写入";
}

function imgbedStatusLabel(info) {
  if (!info || !info.enabled) return "未接入";
  if (info.token_from_env) return "已从环境变量读取";
  return info.updated_at ? `已接入（${escapeHtml(fmtTs(info.updated_at))}）` : "已接入";
}

async function saveImgbedSettings() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const baseUrl = $("#imgbed-base-url")?.value.trim() || "";
  const apiKey = $("#imgbed-token")?.value.trim() || "";
  const channelName = $("#imgbed-channel-name")?.value.trim() || "";
  const folder = $("#imgbed-folder")?.value.trim() || "";
  if (!baseUrl) {
    flash("请填写图床地址", "error");
    $("#imgbed-base-url")?.focus();
    return;
  }
  try {
    const saved = await api("/api/admin/imgbed", {
      method: "PUT",
      body: JSON.stringify({
        base_url: baseUrl,
        token: apiKey,
        channel_name: channelName,
        folder,
      }),
    });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    if (saved?.last_check_error) {
      flash(`已保存，但连通检查失败：${saved.last_check_error}`, "error");
    } else {
      flash("图床设置已保存，连通正常");
    }
    history.replaceState(null, "", "/admin/stats?tab=imgbed");
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    await loadAdminStats(routeSeq);
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  }
}

let _imgbedClearPending = false;

async function clearImgbedSettings() {
  if (_imgbedClearPending) return;
  if (!confirm("清除图床设置？清除后 X 配图退回服务端代理，直到重新接入。")) return;
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  _imgbedClearPending = true;
  try {
    await api("/api/admin/imgbed", { method: "DELETE" });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash("已清除图床设置，X 配图走服务端代理");
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    await loadAdminStats(routeSeq);
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  } finally {
    _imgbedClearPending = false;
  }
}


// ---------- 管理后台（导航统一走左侧边栏） ----------
let _adminRenderSeq = 0; // 当前管理后台渲染令牌：loader 写 #admin-body 前凭此丢弃过期响应
let _adminStatsLoadSeq = 0;
let _adminStatsTimerSeq = 0;
let _lastAdminStatsSnapshot = null;

async function renderAdmin(tab, seq) {
  _adminRenderSeq = seq;
  setPageTitle("管理后台");
  $("#main").innerHTML = `
    <div id="admin-body"><div class="admin-skeleton" aria-hidden="true">${Array(3).fill(`
      <div class="admin-sk-card">
        <div class="admin-sk-line admin-sk-head"></div>
        <div class="admin-sk-table-row"><div class="admin-sk-line"></div><div class="admin-sk-line"></div><div class="admin-sk-line"></div></div>
        <div class="admin-sk-table-row"><div class="admin-sk-line"></div><div class="admin-sk-line"></div></div>
        <div class="admin-sk-table-row"><div class="admin-sk-line"></div><div class="admin-sk-line"></div><div class="admin-sk-line"></div></div>
      </div>`).join("")}
    </div>`;
  const loaders = { dashboard: loadAdminDashboard, stats: loadAdminStats, knowledge: loadAdminKnowledge, kols: loadAdminKols, "ai-analysis": loadAdminAiAnalysis, requests: loadAdminRequests, codes: loadAdminCodes, vocab: loadAdminVocab, "mx-views": loadAdminMxViews, posts: loadAdminPosts, logs: loadAdminLogs, audit: loadAdminAudit, backup: loadAdminBackup, users: loadAdminUsers };
  try {
    await loaders[tab]();
  } catch (err) {
    // 只有当前路由仍是本次渲染目标时才写错误状态，避免旧路由的错误覆盖新 tab
    if (routeStillActive(seq)) $("#admin-body").innerHTML = emptyState("加载失败: " + err.message);
  }
}

let statsTimer = null;

function stopStatsTimer() {
  _adminStatsTimerSeq += 1;
  if (statsTimer) {
    clearInterval(statsTimer);
    statsTimer = null;
  }
}

function startDashboardLiveTimer() {
  stopStatsTimer();
  statsTimer = setInterval(async () => {
    const timerSeq = _adminRenderSeq;
    const timerRequestSeq = ++_adminStatsTimerSeq;
    try {
      const fresh = await api("/api/stats");
      if (!routeStillActive(timerSeq) || timerRequestSeq !== _adminStatsTimerSeq) return;
      _lastAdminStatsSnapshot = fresh;
      renderStatsData(fresh);
    } catch {
      /* 后台刷新失败不打扰 */
    }
  }, 30000);
}

async function refreshDashboardLive() {
  try {
    const st = await api("/api/stats");
    if (!routeStillActive(_adminRenderSeq)) return;
    _lastAdminStatsSnapshot = st;
    renderStatsData(st);
  } catch (err) {
    if (!routeStillActive(_adminRenderSeq)) return;
    flash("刷新失败: " + err.message, "error");
  }
}

function fmtTs(ts) {
  return ts ? new Date(Number(ts) * 1000).toLocaleString() : "-";
}

// 飞书来源的 ISO 时间串（2026-09-03T00:58:17+00:00），fmtTs 的秒数语义会得到 Invalid Date
function fmtFeishuTime(s) {
  if (!s) return "-";
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? String(s) : d.toLocaleString();
}

// 数据库里 SQLite 生成的 created_at/fetched_at 是 UTC（datetime('now')），
// 展示时按 UTC 解析并转成浏览器本地时间（北京时间），避免慢 8 小时
function fmtDbTime(s) {
  if (!s) return "-";
  const str = String(s);
  let d;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/.exec(str);
  if (m) {
    // 无时区的库内时间一律按 UTC（与写入端 datetime.now(timezone.utc) 对齐）
    d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
  } else if (/(?:z|[+-]\d{2}:?\d{2})$/i.test(str)) {
    d = new Date(str); // 带时区的 ISO 串（如 AI 分析日志）按其时区换算
  } else {
    // 其余截断格式（如带毫秒无时区）仍按 UTC 解析，解析不了原样返回
    const m2 = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(str);
    d = m2 ? new Date(Date.UTC(+m2[1], +m2[2] - 1, +m2[3], +m2[4], +m2[5], +m2[6])) : new Date(str);
  }
  if (!d || Number.isNaN(d.getTime())) return str;
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function rateBar(rate) {
  if (rate === null || rate === undefined) return `<span class="muted">暂无数据</span>`;
  const tone = rate >= 95 ? "ok" : rate >= 70 ? "warn" : "fail";
  return `
    <div class="rate-row">
      <div class="rate-bar">
        <div class="rate-fill ${tone}" style="width:${Math.min(100, Math.max(0, rate))}%"></div>
      </div>
      <span class="rate-label">${rate}%</span>
    </div>`;
}

function isAdminSettingsPath() {
  const path = location.pathname;
  return path === "/admin/stats" || path === "/admin/knowledge";
}

async function reloadAdminSettingsPage(seq, authoritativeImaStatus = null) {
  if (location.pathname === "/admin/knowledge") {
    return loadAdminKnowledge(seq, authoritativeImaStatus);
  }
  return loadAdminStats(seq, authoritativeImaStatus);
}

function feishuSourceStatusLabel(source) {
  const labels = {
    pending: "等待同步",
    running: "同步中",
    succeeded: "同步正常",
    failed: "同步失败",
    authorization_required: "需要重新授权",
    disabled: "已停用",
  };
  return labels[source.sync_status] || source.sync_status || "未知";
}

function feishuSourceRowsHtml(data) {
  const sources = data.sources || [];
  if (!sources.length) return emptyState("还没有飞书文档来源");
  return `<div class="feishu-source-list">${sources.map((source) => {
    const detail = [
      source.source_type === "wiki" ? "Wiki" : "Docx",
      source.revision_id ? `revision ${source.revision_id}` : "尚无版本",
      source.entry_count ? `${source.entry_count} 条记录` : "尚无记录",
      source.last_success_at ? `最近成功 ${fmtFeishuTime(source.last_success_at)}` : "尚未同步成功",
      source.next_check_at && source.enabled ? `下次检查 ${fmtFeishuTime(source.next_check_at)}` : "",
    ].filter(Boolean).join(" · ");
    const error = source.last_error ? `<p class="feishu-source-error">${escapeHtml(imaSafeError(source.last_error))}</p>` : "";
    const displayMode = source.display_mode === "document" ? "document" : "timeline";
    const readable = source.sync_status === "succeeded" && Number(source.entry_count || 0) > 0;
    const openLine = readable
      ? `<p class="feishu-source-open">全员可读，无需单独授权</p>`
      : `<p class="feishu-source-open is-blocked">同步成功后全员可读，当前暂无可读内容</p>`;
    const shownTitle = source.display_name || source.title;
    return `<article class="feishu-source-row" data-source-id="${source.id}">
      <div class="feishu-source-copy"><div class="feishu-source-title"><strong>${escapeHtml(shownTitle)}</strong><button type="button" class="feishu-title-rename" onclick="renameFeishuDocumentSource(this.closest('[data-source-id]').dataset.sourceId,'${escapeHtml(shownTitle)}')" aria-label="修改展示名">改名</button><span class="feishu-source-state" data-status="${escapeHtml(source.sync_status)}">${escapeHtml(feishuSourceStatusLabel(source))}</span></div><p>${escapeHtml(detail)}</p>${error}</div>
      <label class="feishu-source-toggle"><span>启用</span><input type="checkbox" ${source.enabled ? "checked" : ""} onchange="toggleFeishuDocumentSource(this.closest('[data-source-id]').dataset.sourceId,this.checked,this)"></label>
      <div class="feishu-source-actions">
        <span class="feishu-display-label">展示方式</span>
        <div class="feishu-display-segment" role="group" aria-label="展示方式 ${escapeHtml(source.title)}">
        <button type="button" class="feishu-display-option${displayMode === "timeline" ? " is-selected" : ""}" aria-pressed="${displayMode === "timeline"}" onclick="setFeishuSourceDisplay(this.closest('[data-source-id]').dataset.sourceId,'timeline',this)">时间线</button>
        <button type="button" class="feishu-display-option${displayMode === "document" ? " is-selected" : ""}" aria-pressed="${displayMode === "document"}" onclick="setFeishuSourceDisplay(this.closest('[data-source-id]').dataset.sourceId,'document',this)">文档</button>
        </div>
        <button type="button" class="btn-ghost feishu-action" data-source-id="${source.id}" onclick="syncFeishuDocumentSource(this.dataset.sourceId,this)" aria-label="立即同步 ${escapeHtml(source.title)}">${REFRESH_ICON}<span>立即同步</span></button>
        <a class="btn-ghost feishu-action" href="${escapeHtml(source.canonical_url)}" target="_blank" rel="noopener" aria-label="打开飞书原文 ${escapeHtml(source.title)}">${EXTERNAL_LINK_ICON}<span>打开原文</span></a>
        <button type="button" class="btn-ghost danger feishu-action" data-source-id="${source.id}" data-title="${escapeHtml(source.title)}" onclick="removeFeishuDocumentSource(this.dataset.sourceId,this.dataset.title,this)">移除</button>
      </div>
      ${openLine}
    </article>`;
  }).join("")}</div>`;
}

function feishuDocsConfigHtml(data) {
  const cfg = data.config || {};
  const secretPlaceholder = cfg.app_secret_set ? "已保存（留空保持不变）" : "飞书开放平台 → 凭证与基础信息";
  const defaultRedirect = location.protocol === "https:"
    ? `${location.origin}/api/admin/feishu-documents/oauth/callback`
    : "";
  const redirectValue = cfg.redirect_uri || defaultRedirect;
  const redirectWarn = cfg.redirect_uri && cfg.redirect_path_ok === false
    ? `<p class="form-error" role="alert">当前回调路径不是本站 OAuth 回调（…/api/admin/feishu-documents/oauth/callback），授权会失败。</p>`
    : "";
  const sourceLabel = { db: "设置页", env: "环境变量" }[cfg.config_source] || "";
  return `<div class="cfg-group feishu-config">
    <div class="feishu-config-head">
      <p class="cfg-group-title">应用与采集</p>
      <span class="muted">${sourceLabel ? `配置来源：${sourceLabel}` : "尚未配置"}</span>
    </div>
    <div class="cfg-fields">
      <label class="cfg-field"><span>App ID</span><input id="feishu-cfg-app-id" class="form-control" value="${escapeHtml(cfg.app_id || "")}" placeholder="cli_..." autocomplete="off"></label>
      <label class="cfg-field"><span>App Secret</span><input id="feishu-cfg-secret" class="form-control" type="password" autocomplete="new-password" placeholder="${escapeHtml(secretPlaceholder)}"></label>
      <label class="cfg-field feishu-field--wide"><span>回调地址（须与开放平台安全设置一致）</span><input id="feishu-cfg-redirect" class="form-control" type="url" value="${escapeHtml(redirectValue)}" placeholder="https://your.domain.com/api/admin/feishu-documents/oauth/callback" autocomplete="off"></label>
      <label class="cfg-field feishu-field--wide"><span>授权权限（空格分隔）</span><input id="feishu-cfg-scopes" class="form-control" value="${escapeHtml(cfg.scopes || "")}" placeholder="wiki:node:read docx:document:readonly docs:document.media:download offline_access" autocomplete="off"></label>
      <label class="cfg-field"><span>检查间隔（秒，≥15）</span><input id="feishu-cfg-interval" class="form-control" type="number" min="15" max="86400" step="1" value="${Number(cfg.interval_seconds) || 60}"></label>
    </div>
    ${redirectWarn}
    <p class="section-meta">修改 App ID / Secret 后需重新授权；检查间隔对所有来源生效，按文档 revision 增量同步。</p>
    <div class="toolbar feishu-config-actions">
      <button type="button" class="btn-normal" id="feishu-cfg-save" onclick="saveFeishuDocsConfig()">保存设置</button>
    </div>
  </div>`;
}

async function renameFeishuDocumentSource(id, current) {
  const name = prompt("新的展示名（留空则恢复飞书标题）：", current || "");
  if (name === null) return;
  const value = name.trim();
  if (value.length > 200) {
    flash("展示名过长（≤200 字）", "error");
    return;
  }
  try {
    await api(`/api/admin/feishu-documents/${id}`, { method: "PATCH", body: JSON.stringify({ display_name: value }) });
    flash(value ? "展示名已更新，知识库内容将随之刷新" : "已恢复飞书标题，知识库内容将随之刷新");
    await loadFeishuDocumentSources();
  } catch (err) {
    flash(err.message || "保存失败", "error");
  }
}

async function saveFeishuDocsConfig() {
  const button = $("#feishu-cfg-save");
  const interval = Number($("#feishu-cfg-interval")?.value || 0);
  if (!Number.isFinite(interval) || interval < 15 || interval > 86400) {
    flash("检查间隔需在 15–86400 秒之间", "error");
    return;
  }
  const payload = {
    app_id: $("#feishu-cfg-app-id")?.value.trim() || "",
    redirect_uri: $("#feishu-cfg-redirect")?.value.trim() || "",
    scopes: $("#feishu-cfg-scopes")?.value.trim() || "",
    interval_seconds: interval,
  };
  const secret = $("#feishu-cfg-secret")?.value?.trim();
  if (secret) payload.app_secret = secret;
  if (button) button.disabled = true;
  try {
    const r = await api("/api/admin/feishu-documents/config", { method: "PUT", body: JSON.stringify(payload) });
    flash(r.reauth_required ? "设置已保存；应用凭据已变更，请重新授权" : "飞书文档设置已保存");
    await loadFeishuDocumentSources();
  } catch (err) {
    flash(err.message || "保存失败", "error");
  } finally {
    if (button) button.disabled = false;
  }
}

async function loadFeishuDocumentSources() {
  const host = $("#feishu-documents-body");
  if (!host) return;
  const loadSeq = ++_feishuSourceLoadSeq;
  const routeSeq = routeRenderSeq;
  const active = () => loadSeq === _feishuSourceLoadSeq && routeStillActive(routeSeq) && $("#feishu-documents-body") === host;
  try {
    const data = await api("/api/admin/feishu-documents");
    if (!active()) return;
    const auth = data.authorized ? "已授权" : (data.configured ? "尚未授权" : "应用未配置");
    const authButton = data.configured
      ? `<button type="button" class="btn-ghost" onclick="authorizeFeishuDocuments()">${data.authorized ? "重新授权" : "授权飞书"}</button>`
      : "";
    host.innerHTML = `${feishuDocsConfigHtml(data)}<div class="feishu-source-summary"><span>${escapeHtml(auth)} · 每 ${Number(data.interval_seconds) || 60} 秒检查</span>${authButton}</div>${feishuSourceRowsHtml(data)}`;
  } catch (err) {
    if (!active()) return;
    host.innerHTML = emptyState(`飞书文档加载失败：${err.message}`, `<div><button type="button" class="btn-normal" onclick="loadFeishuDocumentSources()">重试</button></div>`);
  }
}

async function authorizeFeishuDocuments() {
  try {
    const data = await api("/api/admin/feishu-documents/oauth/start", { method: "POST" });
    location.assign(data.url);
  } catch (err) {
    flash(err.message || "无法开始飞书授权", "error");
  }
}

function feishuLocalUrlInfo(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  try {
    const parsed = new URL(raw);
    const host = (parsed.hostname || "").toLowerCase().replace(/\.$/, "");
    const parts = parsed.pathname.split("/").filter(Boolean);
    const trusted = ["feishu.cn", "larksuite.com"].some((suffix) => host === suffix || host.endsWith(`.${suffix}`));
    if (parsed.protocol !== "https:" || !trusted || parts.length !== 2 || !["wiki", "docx"].includes(parts[0])) return { invalid: true };
    return { type: parts[0], label: parts[0] === "wiki" ? "Wiki" : "Docx" };
  } catch {
    return { invalid: true };
  }
}

function renderFeishuDocumentPreview(info = null, message = "") {
  const preview = $("#feishu-document-preview");
  if (!preview) return;
  if (!info && !message) { preview.innerHTML = ""; return; }
  if (info?.loading) {
    preview.innerHTML = `<span class="feishu-preview-status is-loading">正在读取 ${escapeHtml(info.label)} 文档信息…</span>`;
    return;
  }
  if (info?.data) {
    const data = info.data;
    preview.innerHTML = `<span class="feishu-preview-status is-ready"><strong>${escapeHtml(data.title || "飞书文档")}</strong><span>${escapeHtml(data.source_type === "wiki" ? "Wiki" : "Docx")} · revision ${escapeHtml(data.revision_id || "-")}</span></span>`;
    return;
  }
  preview.innerHTML = `<span class="feishu-preview-status${info?.invalid ? " is-invalid" : ""}">${escapeHtml(message || (info?.invalid ? "请输入有效的飞书 Wiki 或 Docx 链接" : "尚未读取文档信息"))}</span>`;
}

function queueFeishuDocumentPreview(value) {
  const url = String(value || "").trim();
  clearTimeout(_feishuPreviewTimer);
  _feishuPreview = { url, data: null };
  const local = feishuLocalUrlInfo(url);
  if (!url) { renderFeishuDocumentPreview(); return; }
  if (!local || local.invalid) { renderFeishuDocumentPreview({ invalid: true }); return; }
  renderFeishuDocumentPreview({ loading: true, label: local.label });
  const seq = ++_feishuPreviewSeq;
  _feishuPreviewTimer = setTimeout(() => previewFeishuDocument(url, seq), 360);
}

async function previewFeishuDocument(url, seq = _feishuPreviewSeq) {
  try {
    const data = await api("/api/admin/feishu-documents/preview", { method: "POST", body: JSON.stringify({ url }) });
    if (seq !== _feishuPreviewSeq || $("#feishu-document-url")?.value.trim() !== url) return;
    _feishuPreview = { url, data };
    renderFeishuDocumentPreview({ data });
  } catch (err) {
    if (seq !== _feishuPreviewSeq || $("#feishu-document-url")?.value.trim() !== url) return;
    _feishuPreview = { url, data: null };
    renderFeishuDocumentPreview(null, err.message || "暂时无法读取文档信息");
  }
}

async function addFeishuDocumentSource() {
  const input = $("#feishu-document-url");
  const button = $("#feishu-document-add");
  const url = input?.value?.trim() || "";
  if (!url) { flash("请填写飞书 Wiki 或 Docx 链接", "error"); return; }
  const local = feishuLocalUrlInfo(url);
  if (!local || local.invalid) { renderFeishuDocumentPreview({ invalid: true }); flash("请输入有效的飞书 Wiki 或 Docx 链接", "error"); return; }
  if (!confirm("飞书文档添加后全站用户可读，不支持单独授权。确认添加吗？")) return;
  if (button) button.disabled = true;
  try {
    if (_feishuPreview.url !== url || !_feishuPreview.data) {
      await previewFeishuDocument(url, ++_feishuPreviewSeq);
    }
    await api("/api/admin/feishu-documents", { method: "POST", body: JSON.stringify({ url }) });
    input.value = "";
    _feishuPreview = { url: "", data: null };
    renderFeishuDocumentPreview();
    flash("来源已添加，正在首次同步");
    await loadFeishuDocumentSources();
  } catch (err) {
    flash(err.message || "添加失败", "error");
  } finally {
    if (button) button.disabled = false;
  }
}

async function setFeishuSourceDisplay(sourceId, displayMode, button) {
  const row = button?.closest("[data-source-id]");
  const options = row?.querySelectorAll(".feishu-display-option") || [];
  options.forEach((option) => { option.disabled = true; });
  try {
    await api(`/api/admin/feishu-documents/${encodeURIComponent(sourceId)}`, { method: "PATCH", body: JSON.stringify({ display_mode: displayMode }) });
    options.forEach((option) => {
      const selected = option.textContent.trim() === (displayMode === "document" ? "文档" : "时间线");
      option.classList.toggle("is-selected", selected);
      option.setAttribute("aria-pressed", String(selected));
    });
    flash(displayMode === "document" ? "已切换为文档视图，重新打开即生效" : "已切换为时间线视图");
  } catch (err) {
    const previous = displayMode === "document" ? "timeline" : "document";
    options.forEach((option) => {
      const selected = option.textContent.trim() === (previous === "document" ? "文档" : "时间线");
      option.classList.toggle("is-selected", selected);
      option.setAttribute("aria-pressed", String(selected));
    });
    flash(err.message || "切换失败", "error");
  } finally {
    options.forEach((option) => { option.disabled = false; });
  }
}

async function toggleFeishuDocumentSource(sourceId, enabled, input) {
  input.disabled = true;
  try {
    await api(`/api/admin/feishu-documents/${encodeURIComponent(sourceId)}`, { method: "PATCH", body: JSON.stringify({ enabled }) });
    flash(enabled ? "来源已启用" : "来源已停用");
    await loadFeishuDocumentSources();
  } catch (err) {
    input.checked = !enabled;
    flash(err.message || "更新失败", "error");
  } finally {
    input.disabled = false;
  }
}

async function syncFeishuDocumentSource(sourceId, button) {
  button.disabled = true;
  try {
    await api(`/api/admin/feishu-documents/${encodeURIComponent(sourceId)}/sync`, { method: "POST" });
    flash("已开始同步");
    setTimeout(loadFeishuDocumentSources, 1200);
  } catch (err) {
    flash(err.message || "同步失败", "error");
  } finally {
    button.disabled = false;
  }
}

async function removeFeishuDocumentSource(sourceId, title, button) {
  if (!confirm(`移除「${title}」？历史归档会永久保留。`)) return;
  button.disabled = true;
  try {
    await api(`/api/admin/feishu-documents/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
    flash("来源已移除，历史归档仍保留");
    await loadFeishuDocumentSources();
  } catch (err) {
    flash(err.message || "移除失败", "error");
    button.disabled = false;
  }
}

function imaStoragePanelHtml(storage) {
  const st = storage || {};
  const status = st.status || "local";
  const used = Number.isFinite(Number(st.used_percent)) ? `${st.used_percent}%` : "—";
  const resticOk = st.restic_last_check_ok === true ? "通过" : (st.restic_last_check_at ? "未通过" : "无记录");
  const resticAt = st.restic_last_success ? fmtTs(st.restic_last_success) : "无";
  const checkAt = st.restic_last_check_at ? fmtTs(st.restic_last_check_at) : "无";
  const labels = {
    local: "本地归档",
    available: "可用",
    stale: "状态过期",
    unavailable: "暂不可用",
    readonly: "只读",
    capacity_blocked: "容量已限制",
    missing: "未配置",
    invalid: "状态无效",
  };
  return `<section class="section-panel ks-panel" data-panel="storage" id="ks-panel-storage" role="tabpanel" aria-labelledby="ks-tab-storage">
    <header class="section-head"><div><h2 class="section-title">存储</h2>
    <p class="section-meta">刷新探测，备份归档。密钥不进网页。</p></div></header>
    <p class="muted" id="ima-storage-status">${escapeHtml(labels[status] || status)} · 用量 ${escapeHtml(used)} · 上次备份 ${escapeHtml(resticAt)} · 检查 ${escapeHtml(resticOk)}（${escapeHtml(checkAt)}）</p>
    <div class="toolbar ima-storage-toolbar">
      <button type="button" class="btn-ghost" id="ima-storage-refresh" onclick="refreshImaStorage()">刷新状态</button>
      <button type="button" class="btn-normal" id="ima-storage-backup" onclick="backupImaStorage()">立即备份</button>
      <button type="button" class="btn-ghost" id="ima-consistency-run" onclick="runStorageConsistency()">一致性体检</button>
    </div>
    <div id="ima-storage-health"><p class="muted">存储健康加载中…</p></div>
    <div id="ima-consistency" hidden></div>
    <details class="ks-advanced" id="ima-storage-more">
      <summary class="cfg-group-title">磁盘、备份与告警</summary>
      <div id="ima-storage-details"><p class="muted">加载中…</p></div>
    </details>
    <p class="muted">去重每月 1 日 04:00 自动执行。</p>
  </section>`;
}


async function savePollingConfig() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const body = {
    interval_seconds: Number($("#pc-interval").value),
    priority_interval_seconds: Number($("#pc-priority").value),
    digest_interval_seconds: Number($("#pc-digest").value),
    source_probe_interval_seconds: Number($("#pc-probe").value),
    cookie_keepalive_interval_seconds: Number($("#pc-keepalive").value),
    daily_report_hour: Number($("#pc-daily").value),
    translate_twitter_content: $("#pc-translate").checked,
    telegram_rich_messages: $("#pc-tg-rich") ? $("#pc-tg-rich").checked : true,
    combination_base_seconds: Number($("#pc-cb").value),
    combination_idle_cap_seconds: Number($("#pc-cc").value),
    normal_idle_cap_seconds: Number($("#pc-nc").value),
    priority_idle_cap_seconds: Number($("#pc-pc").value),
    x_fallback_cap_seconds: Number($("#pc-xc").value),
    secondary_interval_seconds: Number($("#pc-si").value),
    secondary_idle_cap_seconds: Number($("#pc-sc").value),
    secondary_digest_interval_seconds: Number($("#pc-sd").value),
    secondary_min_digest_count: Number($("#pc-sd-min").value),
  };
  const btn = $("#pc-save");
  if (btn) btn.disabled = true;
  try {
    await api("/api/admin/polling-config", { method: "PUT", body: JSON.stringify(body) });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    // 标准操作反馈 toast；不重建页面（loadAdminStats 会整页重建）
    flash("抓取设置已保存，即时生效");
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  } finally {
    if (btn && document.body.contains(btn)) btn.disabled = false;
  }
}

async function saveZsxqPollingConfig() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const body = {
    zsxq_max_pages: Number($("#pc-zq-pages").value),
    zsxq_fetch_delay_seconds: Number($("#pc-zq-delay").value),
    zsxq_file_delay_seconds: Number($("#pc-zq-file-delay").value),
    zsxq_prefetch_files: $("#pc-zq-prefetch").checked,
    zsxq_fetch_comments: $("#pc-zq-comments").checked,
    zsxq_max_comment_pages: Number($("#pc-zq-comment-pages").value),
    zsxq_comment_budget: Number($("#pc-zq-comment-budget").value),
    zsxq_app_channel: $("#pc-zq-app").checked,
    zsxq_app_device: $("#pc-zq-app-device").value.trim(),
  };
  const btn = $("#pc-zq-save");
  if (btn) btn.disabled = true;
  try {
    await api("/api/admin/polling-config", { method: "PUT", body: JSON.stringify(body) });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash("星球设置已保存，即时生效");
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  } finally {
    if (btn && document.body.contains(btn)) btn.disabled = false;
  }
}

let _ciccPollTimer = null;
let _ciccLastStatus = null;
let _ciccDetailsOpen = false; // 轮询重绘时保留「研报采集」展开状态
let _localLibsLast = null;
let _scanInFlight = false; // 扫描进行中：15s 轮询重渲染时按钮保持禁用，不复活
function startCiccPoll() {
  stopCiccPoll();
  _ciccPollTimer = setInterval(() => {
    if (location.pathname !== "/admin/knowledge") { stopCiccPoll(); return; }
    loadCiccStatus(true);
  }, 15000);
}

function stopCiccPoll() {
  if (_ciccPollTimer) { clearInterval(_ciccPollTimer); _ciccPollTimer = null; }
}

function ciccRunningText(data) {
  if (!data.available) return "不可用（未挂载存储归档）";
  if (data.stale) return "状态过期（存储机未刷新）";
  const parts = [];
  if (data.running > 0) parts.push(`采集中（${data.running} 路）`);
  if (data.compress_running > 0) parts.push("压缩回刷中");
  if (!parts.length) parts.push("空闲");
  parts.push(`库存 ${data.files_total ?? "—"} 篇`);
  parts.push(`每日增量：${data.schedule_enabled ? "开" : "关"}（${(data.storage && data.storage.schedule && data.storage.schedule.time) || "03:00"}）`);
  if (data.last_incremental?.ts) {
    parts.push(`上次自动增量 ${fmtTs(data.last_incremental.ts)}（${data.last_incremental.note === "launched" ? "已启动" : data.last_incremental.note || ""}）`);
  }
  return parts.join(" · ");
}

const CICC_RESEARCH_SLUG = "cicc-research";
// 与后端 app/cicc_collector.py 的 CICC_CATEGORIES 保持一致
const CICC_CATEGORIES = ["宏观经济", "市场策略", "全球研究", "行业研究", "公司研究", "量化及ESG", "大宗商品", "外汇研究", "固定收益", "中金研究院", "其他"];

function ciccPausedLine(cicc) {
  const p = cicc.paused;
  if (!p) return "";
  const why = p.reason === "quota" ? "本月研报配额已满，等月初重置"
    : p.reason === "auth" ? "登录态失效，请更新存储机 Cookie"
    : escapeHtml(p.detail || "未知原因");
  return `<p class="muted" style="color:var(--color-danger)" aria-live="polite">⏸ 采集已熔断：${why}（${fmtTs(p.ts)}）</p>`;
}

function ciccCategoriesHtml(cicc) {
  const active = Array.isArray(cicc.cicc_settings && cicc.cicc_settings.categories)
    ? cicc.cicc_settings.categories : [];
  const boxes = CICC_CATEGORIES.map((c) =>
    `<label style="margin-right:12px;white-space:nowrap"><input type="checkbox" class="cicc-cat" value="${escapeHtml(c)}" ${active.includes(c) ? "checked" : ""}> ${escapeHtml(c)}</label>`).join("");
  const activeKw = Array.isArray(cicc.cicc_settings && cicc.cicc_settings.keywords)
    ? cicc.cicc_settings.keywords : [];
  return `<details><summary class="cfg-group-title">品类定向与关键词白名单（全不勾选 = 采集全部）</summary>
    <p class="muted">当前：${active.length ? escapeHtml(active.join("、")) : "全部品类"}${activeKw.length ? ` · 关键词：${escapeHtml(activeKw.join("、"))}` : ""}</p>
    <div style="display:flex;flex-wrap:wrap;gap:4px 0;margin:6px 0;max-width:560px">${boxes}</div>
    <div style="margin:8px 0">标题关键词白名单（逗号分隔，命中任一即采集）：
      <input type="text" id="cicc-keywords" class="form-control" style="width:320px;display:inline-block;vertical-align:middle" value="${escapeHtml(activeKw.join(","))}" placeholder="如：宁德时代,半导体"></div>
    <button type="button" class="btn-ghost" onclick="saveCiccCategories()">保存品类与关键词</button></details>`;
}

async function saveCiccCategories() {
  const cats = Array.from(document.querySelectorAll(".cicc-cat:checked")).map((el) => el.value);
  const keywords = (document.getElementById("cicc-keywords") || {}).value || "";
  try {
    const r = await api("/api/admin/ima-collector/cicc-categories", { method: "PUT", body: JSON.stringify({ categories: cats, keywords }) });
    flash(r.categories.length ? `品类定向已保存：${r.categories.join("、")}` : "已设为采集全部品类");
    loadCiccStatus();
  } catch (err) {
    flash(`保存失败：${err.message}`, "error");
  }
}

function ciccControlInnerHtml(cicc) {
  const logs = Object.entries(cicc.logs || {})
    .filter(([, line]) => line)
    .map(([name, line]) => `<p class="muted" style="margin:2px 0"><strong>${escapeHtml(name)}</strong>：${escapeHtml(line)}</p>`)
    .join("") || '<p class="muted">暂无日志</p>';
  const cmds = (cicc.commands || []).slice(-5).reverse()
    .map((c) => `<p class="muted" style="margin:2px 0">${fmtTs(c.ts)} · ${escapeHtml(c.mode || "?")} · ${c.ok ? "已执行" : `失败（${escapeHtml(c.error || "")}）`}</p>`)
    .join("") || '<p class="muted">暂无操作记录</p>';
  return `
    <p class="muted" aria-live="polite">${escapeHtml(ciccRunningText(cicc))} · 更新于 ${fmtTs(cicc.ts)}</p>
    <p class="muted">增量完成后，向已授权且开启「匹配研报库」的用户推送命中摘要。</p>
    ${ciccPausedLine(cicc)}
    <div class="toolbar" style="margin:12px 0">
      <button type="button" class="btn-normal" onclick="triggerCicc('incr')">增量采集（近3天）</button>
      <button type="button" class="btn-normal" onclick="triggerCicc('year')">今年回补</button>
      <button type="button" class="btn-ghost" onclick="triggerCicc('compress')">压缩回刷</button>
      <button type="button" class="btn-ghost" onclick="triggerCicc('all')">全量回补</button>
      <button type="button" class="btn-ghost danger" onclick="triggerCicc('stop')">停止采集</button>
    </div>
    <div class="toolbar" style="margin:0 0 12px">
      <input type="time" id="cicc-schedule-time" class="form-control" style="width:120px;display:inline-block;vertical-align:middle" value="${(_ciccLastStatus && _ciccLastStatus.storage && _ciccLastStatus.storage.schedule && _ciccLastStatus.storage.schedule.time) || "03:00"}">
      <button type="button" class="btn-ghost" onclick="saveCiccScheduleTime()">保存时间</button>
      <button type="button" class="btn-ghost" onclick="toggleCiccSchedule()">${cicc.schedule_enabled ? "关闭每日增量" : "开启每日增量"}（03:00）</button>
      <button type="button" class="btn-ghost" onclick="loadCiccStatus()">${REFRESH_ICON}<span>刷新</span></button>
    </div>
    ${ciccCategoriesHtml(cicc)}
    <details open><summary class="cfg-group-title">采集日志（最新一行）</summary>${logs}</details>
    <details><summary class="cfg-group-title">最近操作</summary>${cmds}</details>`;
}

async function loadCiccStatus(quiet = false) {
  const routeSeq = routeRenderSeq;
  try {
    const data = await api("/api/admin/cicc/status");
    if (!routeStillActive(routeSeq)) return;
    _ciccLastStatus = data;
    renderLocalTab();
  } catch (err) {
    if (!routeStillActive(routeSeq)) return;
    if (!quiet) flash(err.message, "error");
    _ciccLastStatus = null;
    renderLocalTab();
  }
}

async function triggerCicc(mode) {
  if (mode === "all" && !confirm("全量回补会拉取历史全部研报（数万篇，需数天），确定？")) return;
  if (mode === "stop" && !confirm("确定停止当前采集？已下载文件保留，下次触发自动续传。")) return;
  try {
    await api("/api/admin/cicc/trigger", { method: "POST", body: JSON.stringify({ mode }) });
    flash(mode === "stop" ? "已发送停止命令" : "已触发，稍候刷新看进度");
    setTimeout(() => loadCiccStatus(true), 3000);
  } catch (err) {
    flash(err.message, "error");
  }
}

async function saveCiccScheduleTime() {
  const value = (document.getElementById("cicc-schedule-time") || {}).value || "";
  if (!/^[0-9]{2}:[0-9]{2}$/.test(value)) { flash("时间格式应为 HH:mm", "error"); return; }
  const enabled = !!(_ciccLastStatus && _ciccLastStatus.schedule_enabled);
  try {
    const r = await api("/api/admin/cicc/schedule", {
      method: "PUT", body: JSON.stringify({ enabled, time: value }),
    });
    flash(`采集时间已设为每天 ${r.time}`);
    loadCiccStatus();
  } catch (err) { flash(`保存失败：${err.message}`, "error"); }
}

async function toggleCiccSchedule() {
  try {
    const enabled = !(_ciccLastStatus && _ciccLastStatus.schedule_enabled);
    const time = (document.getElementById("cicc-schedule-time") || {}).value || "03:00";
    const r = await api("/api/admin/cicc/schedule", {
      method: "PUT", body: JSON.stringify({ enabled, time }),
    });
    flash(r.schedule_enabled ? `每日增量已开启（每天 ${r.time}）` : "每日增量已关闭");
    loadCiccStatus(true);
  } catch (err) {
    flash(err.message, "error");
  }
}

function localLibraryCardHtml(lib) {
  const meta = lib.error ? `异常：${escapeHtml(lib.error)}` : `${lib.pdf_count ?? 0} 个 PDF`;
  const aclCount = (lib.acl_usernames || []).length;
  const tags = (lib.tags || []).length ? ` · 标签 ${escapeHtml(lib.tags.join("、"))}` : "";
  const ciccInner = lib.slug === CICC_RESEARCH_SLUG && _ciccLastStatus
    ? `<details class="cicc-collect"${_ciccDetailsOpen ? " open" : ""}><summary class="cfg-group-title">研报采集</summary>${ciccControlInnerHtml(_ciccLastStatus)}</details>`
    : "";
  return `<div class="ima-source-block" data-slug="${escapeHtml(lib.slug)}">
    <header class="ima-source-block-head"><div><h3 class="ima-source-title">${escapeHtml(lib.name)}</h3>
    <p class="section-meta"><code>${escapeHtml(lib.slug)}</code> · ${meta} · ${lib.enabled ? "已启用" : "未启用"}${tags} · ${aclCount ? `权限 ${aclCount} 人` : "仅管理员"}</p></div>
    <div class="toolbar">
      <button type="button" class="btn-ghost" data-ll-edit="${escapeHtml(lib.slug)}">编辑</button>
      <button type="button" class="btn-ghost" data-ll-toggle="${escapeHtml(lib.slug)}" data-ll-enabled="${lib.enabled ? "false" : "true"}">${lib.enabled ? "停用" : "启用"}</button>
    </div></header>
    ${ciccInner}
  </div>`;
}

function renderLocalTab() {
  const slot = $("#local-libs-body");
  if (!slot || !_localLibsLast) return;
  const prev = slot.querySelector("details.cicc-collect");
  if (prev) _ciccDetailsOpen = prev.open;
  const libs = _localLibsLast.libraries || [];
  const hasCiccLib = libs.some((lib) => lib.slug === CICC_RESEARCH_SLUG);
  const fallbackCicc = !hasCiccLib && _ciccLastStatus
    ? `<div class="ima-source-block" style="margin:12px 0">
        <h3 class="ima-source-title">中金研报采集</h3>
        <p class="section-meta">尚未扫描到 cicc-research 库；采集可先行，文件落盘后扫描即入库。</p>
        ${ciccControlInnerHtml(_ciccLastStatus)}
      </div>`
    : "";
  // scanned_at 是 ISO 串（fmtTs 只吃 epoch 秒）
  const scannedAt = _localLibsLast.scanned_at ? new Date(_localLibsLast.scanned_at) : null;
  const scannedLabel = scannedAt && !Number.isNaN(scannedAt.getTime())
    ? `上次扫描 ${scannedAt.toLocaleString()}`
    : "从未扫描";
  slot.innerHTML = `
    <div class="toolbar" style="margin:12px 0">
      <button type="button" class="btn-normal" id="local-scan-btn" ${_scanInFlight ? "disabled" : ""} onclick="scanLocalLibraries()">${_scanInFlight ? "扫描中…" : "扫描本地库"}</button>
      <button type="button" class="btn-ghost" onclick="openLocalLibraryCreateModal()">新建本地库</button>
      <span class="muted" aria-live="polite">${scannedLabel}</span>
    </div>
    ${fallbackCicc}
    ${libs.length
      ? libs.map(localLibraryCardHtml).join("")
      : '<p class="muted">尚未发现本地库。点「新建本地库」创建，或在存储机 local/&lt;slug&gt;/ 放入 .vpush-local-library.json 标记与 PDF 后点「扫描本地库」。</p>'}`;
}

async function loadLocalLibraries(quiet = false) {
  const routeSeq = routeRenderSeq;
  try {
    const data = await api("/api/admin/ima-local-libraries");
    if (!routeStillActive(routeSeq)) return;
    _localLibsLast = data;
    renderLocalTab();
  } catch (err) {
    if (!routeStillActive(routeSeq)) return;
    if (!quiet) flash(err.message, "error");
    const slot = $("#local-libs-body");
    if (slot) slot.innerHTML = `<p class="muted">${escapeHtml(err.message)}</p>`;
  }
}

async function scanLocalLibraries() {
  if (_scanInFlight) return;
  _scanInFlight = true;
  renderLocalTab();
  try {
    const data = await api("/api/admin/ima-local-libraries/scan", { method: "POST" });
    flash(data.status === "scan_failed" ? "扫描失败：存储归档不可读" : "扫描完成");
    _localLibsLast = data;
  } catch (err) {
    flash(err.message, "error");
  } finally {
    _scanInFlight = false;
    renderLocalTab();
  }
}

async function toggleLocalLibrary(slug, enabled) {
  try {
    const data = await api(`/api/admin/ima-local-libraries/${encodeURIComponent(slug)}/enabled`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    });
    flash(enabled ? "本地库已启用" : "本地库已停用");
    _localLibsLast = data;
    renderLocalTab();
  } catch (err) {
    flash(err.message, "error");
  }
}

function splitListCsv(text) {
  return String(text || "").split(/[,，、]/).map((s) => s.trim()).filter(Boolean);
}

function localLibraryModalShell(title, innerHtml) {
  const mask = document.createElement("div");
  mask.className = "modal-mask";
  mask.innerHTML = `
    <div class="modal-card" role="dialog" aria-modal="true" aria-label="${title}">
      <h3 class="ima-source-title" style="margin-bottom:12px">${title}</h3>
      ${innerHtml}
      <div class="toolbar" style="margin-top:16px">
        <button class="btn-normal" id="ll-save">保存</button>
        <button type="button" class="btn-sm" data-close>取消</button>
      </div>
    </div>`;
  document.body.appendChild(mask);
  const snap = () => ({
    name: mask.querySelector("#ll-name")?.value || "",
    tags: mask.querySelector("#ll-tags")?.value || "",
  });
  const initial = snap();
  const close = () => {
    const now = snap();
    if ((now.name !== initial.name || now.tags !== initial.tags)
      && !confirm("有未保存的修改，确定关闭？")) return;
    mask.remove();
  };
  mask.addEventListener("click", (e) => {
    if (e.target === mask) close();
  });
  trapFocus(mask, close);
  mask.querySelector("[data-close]").addEventListener("click", close);
  const first = mask.querySelector("#ll-name, input, select, textarea, button");
  if (first) first.focus();
  return mask;
}

async function openLocalLibraryModal(slug) {
  const lib = ((_localLibsLast && _localLibsLast.libraries) || []).find((l) => l.slug === slug);
  if (!lib) return;
  try {
    await fetchAclCandidateUsers();
  } catch (err) {
    flash("加载用户失败: " + err.message, "error");
    return;
  }
  const aclHtml = aclPickerHtml(lib.acl_usernames || [], "ll-acl-list");
  const mask = localLibraryModalShell(`编辑本地库：${escapeHtml(lib.name)}`, `
    <label class="form-label">库名
      <input id="ll-name" class="form-control" maxlength="80" value="${escapeHtml(lib.name)}">
    </label>
    <label class="form-label">库级标签（逗号分隔）
      <input id="ll-tags" class="form-control" value="${escapeHtml((lib.tags || []).join(", "))}" placeholder="研报, 中金">
    </label>
    <p class="muted">改标签后保存可立刻扫描，写入库内文档。</p>
    <p class="form-label">权限控制（添加或移除即时生效）</p>
    ${aclHtml}`);
  const picker = mask.querySelector(".ima-acl-picker");
  if (picker) picker.dataset.groupId = `local-${slug}`;
  mask.querySelector("#ll-save").addEventListener("click", () => saveLocalLibraryModal(slug, mask, lib.tags || []));
}

async function saveLocalLibraryModal(slug, mask, previousTags) {
  const btn = mask.querySelector("#ll-save");
  const name = mask.querySelector("#ll-name").value.trim();
  const tags = splitListCsv(mask.querySelector("#ll-tags").value);
  if (!name) {
    flash("库名不能为空", "error");
    return;
  }
  const tagsChanged = tags.slice().sort().join("\0") !== [...previousTags].map(String).sort().join("\0");
  if (btn) btn.disabled = true;
  try {
    await api(`/api/admin/ima-local-libraries/${encodeURIComponent(slug)}`, {
      method: "PUT",
      body: JSON.stringify({ name, tags }),
    });
    mask.remove();
    flash("已保存本地库设置");
    await loadLocalLibraries(true);
    if (tagsChanged && confirm("库级标签已改，现在扫描以应用到库内文档？")) {
      await scanLocalLibraries();
    }
  } catch (err) {
    flash("保存失败: " + err.message, "error");
    if (btn) btn.disabled = false;
  }
}

function openLocalLibraryCreateModal() {
  const mask = localLibraryModalShell("新建本地库", `
    <label class="form-label">目录名 slug（小写字母/数字/短横线）
      <input id="ll-slug" class="form-control" maxlength="47" placeholder="my-papers">
    </label>
    <label class="form-label">库名
      <input id="ll-name" class="form-control" maxlength="80" placeholder="我的论文库">
    </label>
    <label class="form-label">库级标签（可选，逗号分隔）
      <input id="ll-tags" class="form-control" placeholder="研报">
    </label>
    <p class="muted" style="margin-top:8px">创建后在存储机 <code>local/&lt;slug&gt;/</code> 放入 PDF，回这里点「扫描本地库」。</p>`);
  mask.querySelector("#ll-save").addEventListener("click", () => saveLocalLibraryCreate(mask));
}

async function saveLocalLibraryCreate(mask) {
  const btn = mask.querySelector("#ll-save");
  const slug = mask.querySelector("#ll-slug").value.trim().toLowerCase();
  const name = mask.querySelector("#ll-name").value.trim();
  const tags = splitListCsv(mask.querySelector("#ll-tags").value);
  if (!slug || !name) {
    flash("slug 与库名必填", "error");
    return;
  }
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/admin/ima-local-libraries", {
      method: "POST",
      body: JSON.stringify({ slug, name, tags }),
    });
    mask.remove();
    flash(data.status === "scan_failed" ? `已创建「${name}」，但扫描失败：存储归档不可读` : `已创建「${name}」`);
    _localLibsLast = data;
    renderLocalTab();
  } catch (err) {
    flash("创建失败: " + err.message, "error");
    if (btn) btn.disabled = false;
  }
}

function fmtCacheBytes(bytes) {
  const n = Number(bytes) || 0;
  if (n <= 0) return "0 MB";
  if (n < 1048576) return `${Math.max(1, Math.round(n / 1024))} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

async function purgeZsxqCache() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  try {
    const r = await api("/api/admin/zsxq-cache/purge", { method: "POST" });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    const el = $("#zq-cache-stat");
    if (el) {
      el.textContent = `附件缓存 ${fmtCacheBytes(r.bytes)} / ${r.files || 0} 个文件`;
    }
    flash(r.deleted ? `已清理 ${r.deleted} 个未引用附件` : "没有可清理的附件");
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  }
}

async function pasteCookieField(inputId) {
  const el = $("#" + inputId);
  if (!el) return;
  try {
    const text = (await navigator.clipboard.readText()).trim();
    if (!text) {
      flash("剪贴板是空的", "error");
      return;
    }
    el.value = text;
    el.focus();
    flash("已填入，确认后点保存");
  } catch {
    flash("无法读剪贴板，请直接粘贴到输入框", "error");
  }
}

function focusCookieField(kind) {
  const focusId = { xueqiu: "xq-cookie", weibo: "wb-qr-start", twitter: "tw-cookie", ima: "ima-cookie", zsxq: "zq-cookie" }[kind];
  if (focusId) $(`#${focusId}`)?.focus();
}

let _cookieClearPending = false;

async function clearSavedCookie(kind, label) {
  if (_cookieClearPending) return;
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  if (!(await showConfirm(`清除「${label}」Cookie？清除后该数据源会停止抓取，直到重新保存。`))) return;
  _cookieClearPending = true;
  try {
    await api(`/api/admin/cookies/${kind}`, { method: "DELETE" });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(`已清除「${label}」Cookie`);
    if (kind === "ima" || kind === "zsxq") {
      if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
      await reloadAdminSettingsPage(routeSeq);
    } else {
      history.replaceState(null, "", "/admin/stats?tab=cookies");
      if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
      await loadAdminStats(routeSeq);
    }
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    focusCookieField(kind);
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  } finally {
    _cookieClearPending = false;
  }
}

async function saveXueqiuCookie() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const cookie = $("#xq-cookie").value.trim();
  if (!cookie) {
    flash("请先粘贴雪球 Cookie", "error");
    return;
  }
  try {
    await api("/api/admin/xueqiu-cookie", {
      method: "POST",
      body: JSON.stringify({ cookie }),
    });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash("雪球 Cookie 已保存，即时生效");
    history.replaceState(null, "", "/admin/stats?tab=cookies");
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    await loadAdminStats(routeSeq);
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    focusCookieField("xueqiu");
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  }
}

async function saveZsxqCookie() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const cookie = $("#zq-cookie").value.trim();
  if (!cookie) {
    flash("请先粘贴知识星球 Cookie", "error");
    return;
  }
  try {
    await api("/api/admin/zsxq-cookie", {
      method: "POST",
      body: JSON.stringify({ cookie }),
    });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash("知识星球 Cookie 已保存，即时生效");
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    await reloadAdminSettingsPage(routeSeq);
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    focusCookieField("zsxq");
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  }
}

async function saveTwitterCookie() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const cookie = $("#tw-cookie").value.trim();
  if (!cookie) {
    flash("请先粘贴 X Cookie", "error");
    return;
  }
  try {
    await api("/api/admin/twitter-cookie", {
      method: "POST",
      body: JSON.stringify({ cookie }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash("X Cookie 已保存，即时生效");
    history.replaceState(null, "", "/admin/stats?tab=cookies");
    await loadAdminStats(routeSeq);
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    focusCookieField("twitter");
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

let wbQrTimer = null;
let wbQrSeq = 0;

function weiboQrOwnerActive(owner) {
  return !!owner && owner.seq === wbQrSeq
    && owner.token === state.token
    && owner.sessionGeneration === imaMountState.sessionGeneration
    && routeStillActive(owner.routeSeq);
}

async function startWeiboQr() {
  const owner = {
    routeSeq: routeRenderSeq,
    token: state.token,
    sessionGeneration: imaMountState.sessionGeneration,
    seq: ++wbQrSeq,
  };
  if (wbQrTimer) {
    clearTimeout(wbQrTimer);
    wbQrTimer = null;
  }
  try {
    const data = await api("/api/admin/weibo-qr/start", { method: "POST" });
    if (!weiboQrOwnerActive(owner)) return;
    $("#wb-qr-box").innerHTML = `
      <div class="qr-card">
        <img src="${escapeHtml(data.qrurl)}" alt="微博登录二维码" width="220" height="220">
      </div>
      <p class="muted qr-status" id="wb-qr-status">等待扫码…</p>`;
    let timer = null;
    const tick = async () => {
      if (!weiboQrOwnerActive(owner) || wbQrTimer !== timer) return;
      const cont = await pollWeiboQr(data.qrid, owner);
      if (!weiboQrOwnerActive(owner) || wbQrTimer !== timer || !cont) return;
      timer = setTimeout(tick, 2000);
      wbQrTimer = timer;
    };
    timer = setTimeout(tick, 2000);
    wbQrTimer = timer;
  } catch (err) {
    if (weiboQrOwnerActive(owner)) flash(err.message, "error");
  }
}

async function pollWeiboQr(qrid, owner) {
  owner = owner || {
    routeSeq: routeRenderSeq,
    token: state.token,
    sessionGeneration: imaMountState.sessionGeneration,
    seq: wbQrSeq,
  };
  if (!weiboQrOwnerActive(owner)) return false;
  try {
    const data = await api(`/api/admin/weibo-qr/status?qrid=${encodeURIComponent(qrid)}`);
    if (!weiboQrOwnerActive(owner)) return false;
    const statusEl = $("#wb-qr-status");
    if (!statusEl) return false;
    if (data.status === "pending") {
      statusEl.textContent = "等待扫码…";
      return true;
    }
    if (data.status === "scanned") {
      statusEl.textContent = "已扫描，请在手机上确认登录";
      return true;
    }
    if (data.status === "ok") {
      statusEl.textContent = "登录成功，微博 Cookie 已自动保存";
      flash("微博 Cookie 已保存");
    }
    return false;
  } catch (err) {
    if (!weiboQrOwnerActive(owner)) return false;
    const statusEl = $("#wb-qr-status");
    if (statusEl) statusEl.textContent = "登录失败：" + err.message;
    return false;
  }
}

function parseDbUtcMs(s) {
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/.exec(String(s));
  if (!m) return null;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
}

// ---------- 主题（深色模式）----------
const THEME_KEY = "theme"; // 值：light | dark | auto

function themeMode() {
  try {
    return localStorage.getItem(THEME_KEY) || "auto";
  } catch {
    return "auto";
  }
}

function systemPrefersDark() {
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyTheme() {
  const mode = themeMode();
  const dark = mode === "dark" || (mode === "auto" && systemPrefersDark());
  document.documentElement.classList.toggle("theme-dark", dark);
  // 同步顶部浏览器 UI（桌面无意义，PWA/移动端状态栏）。
  // 用页面顶部背景色而非品牌强调色：iOS 用 theme-color 填充状态栏/安全区，
  // 若填强调蓝会出现一条与页面不符的蓝色条（详见 PWA 顶部蓝条问题）。
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", dark ? "#11141a" : "#f8f8fb");
  const statusBar = document.querySelector('meta[name="apple-mobile-web-app-status-bar-style"]');
  if (statusBar) statusBar.setAttribute("content", dark ? "black-translucent" : "default");
  // 同步 manifest 链接：部分安卓 PWA 独立窗口只认 manifest 静态 theme_color
  const manifestLink = document.getElementById("manifest");
  if (manifestLink) manifestLink.setAttribute("href", dark ? "/manifest-dark.webmanifest?v=2" : "/manifest.webmanifest?v=2");
  // 品牌符号（登录页 + topbar + 侧边栏）用融合版，深浅各一
  const logo = document.querySelector(".topbar-logo");
  if (logo) logo.src = dark ? "/logo-mark-dark.svg" : "/logo-mark.svg";
  const sidebarLogo = document.querySelector("#sidebar-logo");
  if (sidebarLogo) sidebarLogo.src = dark ? "/logo-mark-dark.svg" : "/logo-mark.svg";
  const loginLogo = document.querySelector("#login-logo");
  if (loginLogo) loginLogo.src = dark ? "/logo-mark-dark.svg" : "/logo-mark.svg";
  const favicon = document.getElementById("favicon");
  if (favicon) favicon.setAttribute("href", dark ? "/logo-mark-dark.svg" : "/logo-mark.svg");
  return dark;
}

function setTheme(mode) {
  if (!["light", "dark", "auto"].includes(mode)) mode = "auto";
  try {
    localStorage.setItem(THEME_KEY, mode);
  } catch { /* localStorage 不可用则只影响当前页 */ }
  applyTheme();
  renderThemeSwitcher();
}

function themeIconFor(mode) {
  return { light: THEME_SUN_ICON, dark: THEME_MOON_ICON, auto: THEME_AUTO_ICON }[mode] || THEME_AUTO_ICON;
}

function themeLabelFor(mode) {
  return { light: "浅色", dark: "深色", auto: "跟随系统" }[mode] || "跟随系统";
}

function toggleLightDarkTheme() {
  // 浅色/深色互切按钮：auto 时按当前生效主题取反，落回显式主题
  const dark = document.documentElement.classList.contains("theme-dark");
  setTheme(dark ? "light" : "dark");
}

function renderThemeSwitcher() {
  const el = $("#theme-switcher");
  if (!el) return;
  const mode = themeMode();
  // 浅色/深色合成一个互切按钮（图标显示当前生效主题），跟随系统独立保留
  const effective = document.documentElement.classList.contains("theme-dark") ? "dark" : "light";
  const toggleLabel = effective === "dark" ? "切换为浅色" : "切换为深色";
  el.innerHTML = `
    <button class="theme-mode ${mode !== "auto" ? "selected" : ""}" data-mode="${effective}" title="${toggleLabel}" aria-label="${toggleLabel}" aria-pressed="${mode !== "auto"}" onclick="toggleLightDarkTheme()">${themeIconFor(effective)}</button>
    <button class="theme-mode ${mode === "auto" ? "selected" : ""}" data-mode="auto" title="${themeLabelFor("auto")}" aria-label="${themeLabelFor("auto")}" aria-pressed="${mode === "auto"}" onclick="setTheme('auto')">${themeIconFor("auto")}</button>`;
}

function updateThemeToggleIcon() {
  const btn = $("#theme-toggle-btn");
  if (btn) btn.innerHTML = themeIconFor(themeMode());
}

function cycleTheme() {
  // 移动端顶部按钮：light → dark → auto 循环切换
  const order = ["light", "dark", "auto"];
  const next = order[(order.indexOf(themeMode()) + 1) % order.length];
  setTheme(next);
  updateThemeToggleIcon();
}

// 系统主题变化时，auto 模式跟随；手动模式不打扰
if (window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (themeMode() === "auto") {
      applyTheme();
      renderThemeSwitcher();
      updateThemeToggleIcon();
    }
  });
}

// ---------- 路由 ----------
let routeRenderSeq = 0; // 每次路由切换递增；异步渲染完成后凭此丢弃过期响应
const SPA_PREFIXES = new Set([
  "timeline", "home", "combinations", "mysubs", "settings", "news",
  "search", "kol", "more", "admin", "zsxq", "ima-documents", "knowledge",
  "mx-views",
]);

function routeStillActive(seq) {
  // 令牌必须是整数且等于当前路由序号；局部刷新必须在发起请求前捕获 routeRenderSeq 并回传
  return Number.isInteger(seq) && seq === routeRenderSeq;
}

function sessionOwnerStillActive(routeSeq, token, sessionGeneration) {
  return routeStillActive(routeSeq) && token === state.token
    && sessionGeneration === imaMountState.sessionGeneration;
}

function normalizeRoute(path) {
  const raw = String(path || "").replace(/^#\/?/, "").replace(/^\/+/, "");
  const [pathname, query] = raw.split("?");
  const clean = pathname || "timeline";
  return query ? `/${clean}?${query}` : `/${clean}`;
}

function routePath() {
  return location.pathname.replace(/^\/+/, "") || "timeline";
}

function routeQuery() {
  return new URLSearchParams(location.search);
}

function isRoute(prefix) {
  const path = routePath();
  return prefix.endsWith("/") ? path.startsWith(prefix) : path === prefix || path.startsWith(prefix + "/");
}

function isSpaPath(pathname) {
  const first = String(pathname || "").replace(/^\/+/, "").split("/")[0] || "";
  return SPA_PREFIXES.has(first);
}

function go(path) {
  const url = normalizeRoute(path);
  if (location.pathname + location.search !== url) history.pushState(null, "", url);
  router();
}

const {
  clearNewsReaderState,
  loadFinancialNews,
  openNewsArticle,
  openNewsSourcePicker,
  queueNewsSearch,
  renderFinancialNewsArticle,
  renderFinancialNewsList,
  renderNewsCenter,
  saveNewsSources,
  selectNewsSource,
} = createNewsView({
  $,
  state,
  api,
  apiBlob,
  routeStillActive,
  currentRouteSeq: () => routeRenderSeq,
  setPageTitle,
  emptyState,
  go,
  flash,
  escapeHtml,
  trapFocus,
  fmtPublished,
  externalLinkIcon: EXTERNAL_LINK_ICON,
});

const {
  clearImaPdfUrl,
  openImaDocument,
  renderKnowledge,
  renderImaDocuments,
  refreshKnowledge,
  subscribeKnowledge,
  unsubscribeKnowledge,
  backFromImaReader,
  openImaPdfNewTab,
  downloadImaPdf,
  loadImaDocumentsMore,
  clearImaDocumentsFilter,
  clearImaDocumentsFilters,
  copyImaAbstract,
  pickImaDay,
  pickImaTag,
  queueImaDocumentsSearch,
  refreshImaDocuments,
  selectImaDocumentGroup,
  selectImaDocumentsTag,
  submitImaDocumentsSearch,
  toggleImaAbstract,
  toggleImaDayPicker,
  toggleImaTagMenu,
  restoreImaListSnapshot,
  stopImaDocumentsAutoLoad,
  fmtImaDay,
  imaDocumentReaderRoute,
  replaceImaDocumentsRoute,
} = createImaView({
  $,
  state,
  api,
  apiBlob,
  flash,
  escapeHtml,
  emptyState,
  go,
  isRoute,
  isStandalonePwa,
  normalizeRoute,
  routePath,
  routeQuery,
  routeStillActive,
  sessionOwnerStillActive,
  currentRouteSeq: () => routeRenderSeq,
  bumpRouteSeq: () => ++routeRenderSeq,
  currentImaReaderSeq: () => _imaReaderSeq,
  bumpImaReaderSeq: () => ++_imaReaderSeq,
  setPageTitle,
  imaMountState,
  fmtCacheBytes,
  loadFeishuTimeline,
  feishuSourceDisplay,
  feishuSourcePillsHtml,
  resetFeishuTimelineMedia,
  userKeywordSet,
  isReportWatchableTag,
  SEARCH_ICON,
  REFRESH_ICON,
  X_ICON,
  EXTERNAL_LINK_ICON,
});


let pushSettingsView;
const feishuPersonalView = createFeishuPersonalView({
  $,
  state,
  api,
  currentRouteSeq: () => routeRenderSeq,
  routeStillActive,
  sessionOwnerStillActive,
  flash,
  escapeHtml,
  imaMountState,
  feishuChannelBound: (user) => pushSettingsView.feishuChannelBound(user),
  startSettingsPoll: () => pushSettingsView.startSettingsPoll(),
  reloadSettings: (routeSeq) => pushSettingsView.reloadSettings(routeSeq),
  switchSettingsTab: (name) => pushSettingsView.switchSettingsTab(name),
  userKeywordSet,
  isReportWatchableTag,
  KEYWORDS_MAX_COUNT,
  CHANNEL_ICONS,
});
const {
  fsPersonalState,
  stopFeishuPersonalPoll,
  feishuPersonalHtml,
  pushChannelsHtml,
  webPushSupported,
  renderBindResult,
  startFeishuPersonal,
  cancelFeishuPersonal,
  refreshFeishuBindCode,
  openBindGuide,
  savePushChannels,
  saveNotify,
  saveDailyReport,
  saveTranslateTwitter,
  toggleDnd,
  saveDnd,
  saveCustomTgBot,
  unbindChannel,
  saveWecomWebhook,
  saveBarkKey,
  enableWebPush,
  disableWebPush,
  saveKeywords,
  saveKeywordsMatchReports,
  toggleReportKeyword,
  saveLlm,
  loadLlmModels,
  savePassword,
  genBindCode,
} = feishuPersonalView;

pushSettingsView = createPushSettingsView({
  $,
  state,
  api,
  currentRouteSeq: () => routeRenderSeq,
  routeStillActive,
  imaMountState,
  flash,
  escapeHtml,
  emptyState,
  go,
  isRoute,
  setPageTitle,
  CHANNEL_ICONS,
  PLATFORM_LABELS,
  SEARCH_ICON,
  avatarHtml,
  feishuPersonalView,
  feishuPersonalHtml,
  pushChannelsHtml,
  webPushSupported,
  toggleDnd,
});
const {
  stopSettingsPoll,
  startSettingsPoll,
  reloadSettings,
  feishuChannelBound,
  renderSettings,
  switchSettingsTab,
  filterKolImageSettings,
  toggleKolImages,
  loadKolImageSettings,
} = pushSettingsView;

const {
  loadAdminCodes,
  adminCodesBatch,
  adminCodesClearSelect,
  adminCodesCopySelected,
  adminCodesNoteInput,
  adminCodesPreset,
  adminCodesToggle,
  adminCodesToggleBatch,
  adminCodesTogglePage,
  adminGenerateCodes,
  adminRevokeBatch,
  adminRevokeCode,
  searchAdminCodes,
  selectAdminCodeFilter,
  clearAdminCodesResult,
  copyText,
} = createAdminCodesView({
  showConfirm,
  $,
  state,
  api,
  flash,
  escapeHtml,
  routeStillActive,
  SEARCH_ICON,
  fmtDbTime,
  parseDbUtcMs,
  currentAdminSeq: () => _adminRenderSeq,
});

const {
  loadAdminNews,
  loadAdminPosts,
  selectAdminNewsSource,
  saveAdminNewsSettings,
  refreshAllAdminNews,
  refreshAdminNewsFeed,
  toggleAdminNewsSource,
  toggleAdminNewsFeed,
  archiveAdminNewsSource,
  restoreAdminNewsSource,
  archiveAdminNewsFeed,
  restoreAdminNewsFeed,
  openNewsSourceModal,
  openNewsFeedModal,
  updateAdminNewsQuery,
  updateAdminNewsStatus,
  updateAdminNewsArchived,
  adminFilterPosts,
  adminPostsLoadMore,
  adminTogglePost,
  adminDeletePost,
  adminSetPostHidden,
} = createAdminNewsView({
  $,
  state,
  api,
  flash,
  escapeHtml,
  routeStillActive,
  currentRouteSeq: () => routeRenderSeq,
  currentAdminSeq: () => _adminRenderSeq,
  stopStatsTimer,
  statsTabsHtml,
  emptyState,
  renderSidebar,
  renderTopbar,
  renderBottomNav,
  trapFocus,
  REFRESH_ICON,
  PLUS_ICON,
  PLATFORM_LABELS,
});

const {
  loadAdminUsers,
  loadAdminRequests,
  adminApproveRequest,
  adminRejectRequest,
  adminUsersApplyFilter,
  adminUsersBatch,
  adminUserToggleSelect,
  adminUserTogglePage,
  adminUserClearSelect,
  adminOpenUser,
  adminSaveUserKnowledge,
  adminSaveUsername,
  adminSavePassword,
  adminSendTestPush,
  adminDeleteUser,
  adminToggleAdmin,
  adminSaveInactivePolicy,
  adminInactivePolicySyncSave,
  adminInactivePolicyKeydown,
  closeAdminModal,
} = createAdminUsersView({
  showConfirm,
  $,
  state,
  api,
  flash,
  escapeHtml,
  routeStillActive,
  currentAdminSeq: () => _adminRenderSeq,
  emptyState,
  SEARCH_ICON,
  fmtDbTime,
  trapFocus,
  renderSidebar,
  renderTopbar,
  USER_CHANNEL_KEYS,
  CHANNEL_LABELS,
  CHANNEL_ICONS,
  PLATFORM_LABELS,
  usernameRuleError,
});

const {
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
  adminMxTagAutoSave,
  adminMxTagAutoAddSpecial,
  adminMxTagAutoRemoveSpecial,
  adminMxTagCancel,
  adminMxTagOpenRunModal,
  adminMxTagSelAll,
  adminMxTagStartRun,
  adminMxTagTest,
  adminOpenTagReviewModal,
  closeTagReviewModal,
  toggleTagReviewMsg,
  adminTagReviewModalReview,
  adminTagReviewSelAll,
  adminTagReviewSelChange,
  adminReviewTag,
  adminReviewTagsBatch,
  adminReviewAliasCandidate,
  adminTagDetailAddTag,
  adminTagDetailRemoveTag,
} = createAdminKolsView({
  $,
  state,
  api,
  flash,
  escapeHtml,
  routeStillActive,
  currentAdminSeq: () => _adminRenderSeq,
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
});

const {
  runStorageConsistency,
  runStorageDedup,
  loadStorageHealth,
  saveStorageAlerts,
  refreshImaStorage,
  backupImaStorage,
  loadProxyAdmin,
  syncProxyRouteInputs,
  syncProxyPoolForm,
  saveProxyRoutes,
  createProxyPool,
  importProxyPool,
  extractProxyPool,
  deleteProxyPool,
  deleteProxyNode,
  testProxyNode,
  loadAdminBackup,
  saveBackupWebDAV,
  testBackupWebDAV,
  backupDownload,
  backupRestoreWebDAV,
  backupRestoreUpload,
} = createAdminInfraView({
  showConfirm,
  $,
  state,
  api,
  flash,
  escapeHtml,
  routeStillActive,
  currentRouteSeq: () => routeRenderSeq,
  currentAdminSeq: () => _adminRenderSeq,
  sessionOwnerStillActive,
  imaMountState,
  fmtTs,
  imaStoragePanelHtml,
  logout,
  PLATFORM_LABELS,
});

const {
  initImaMountState,
  imaCollectorHasUnsaved,
  renderImaMountGroups,
  renderImaSelectedGroup,
  renderImaFolderTree,
  renderImaGroupAcl,
  renderImaCollectorDirtyState,
  discardImaCollectorChanges,
  selectImaMountGroup,
  setImaGroupInterval,
  toggleImaFolderPanel,
  toggleImaFolderExpand,
  toggleImaFolder,
  retryImaFolderLoad,
  discoverImaGroups,
  filterAclSuggest,
  onAclSearchKey,
  toggleImaAclExpanded,
  retryImaGroupAcl,
  saveImaCollector,
  triggerImaCollector,
  saveImaCredentials,
  stopImaProgressPoll,
  applyImaCollectorProgress,
  startImaProgressPoll,
  imaCollectorStatusText,
  imaGroupDiscoveryStatusText,
  imaCollectorProgressHtml,
  imaMountGroup,
  imaGroupIntervalSeconds,
  fetchAclCandidateUsers,
  aclPickerHtml,
  addAclUser,
  removeAclUser,
  imaCollectorFormSnapshot,
  imaCollectorFormRevision,
  rememberImaCollectorDraft,
  clearImaCollectorDraft,
  restoreImaCollectorOwnerToken,
  imaSafeError,
} = createAdminImaCollectorView({
  $,
  state,
  api,
  flash,
  escapeHtml,
  emptyState,
  routeStillActive,
  sessionOwnerStillActive,
  currentRouteSeq: () => routeRenderSeq,
  bumpRouteSeq: () => ++routeRenderSeq,
  currentAdminSeq: () => _adminRenderSeq,
  FOLDER_ICON,
  imaMountState,
  imaCollectorPureCache,
  reloadAdminSettingsPage,
  isAdminSettingsPath,
  currentLocalLibraries: () => _localLibsLast,
  focusCookieField,
});


const {
  loadAdminStats,
  loadAdminDashboard,
  loadAdminAudit,
  loadAdminLogs,
  loadAdminErrorLogs,
  loadAdminSysLogsPanel,
  adminFilterLogs,
  stopSysLogsTimer,
  renderStatsData,
  openAdminKolFromHealth,
  setPlazaSourceMode,
} = createAdminDashboardView({
  $,
  state,
  api,
  flash,
  escapeHtml,
  routeStillActive,
  currentAdminSeq: () => _adminRenderSeq,
  emptyState,
  statsTabsHtml,
  switchStatsTab,
  statsTabFromHash,
  startDashboardLiveTimer,
  stopStatsTimer,
  fmtTs,
  fmtDbTime,
  parseDbUtcMs,
  PLATFORM_LABELS,
  CHANNEL_LABELS,
  imaMountState,
  sessionOwnerStillActive,
  imaCollectorStatusText,
  imaGroupDiscoveryStatusText,
  go,
  nextStatsLoadSeq: () => ++_adminStatsLoadSeq,
  currentStatsLoadSeq: () => _adminStatsLoadSeq,
  getStatsSnapshot: () => _lastAdminStatsSnapshot,
  setStatsSnapshot: (s) => { _lastAdminStatsSnapshot = s; },
  cookieRepairItems,
  cookieRepairBanner,
  cookieUpdatedLabel,
  imgbedStatusLabel,
  setPageTitle,
  STALE_KOL_HOURS,
  STALE_KOL_LIMIT,
  PLATFORM_ICONS,
  fmtCacheBytes,
  loadAdminNews,
  replaceRoute,
  imaCollectorFormSnapshot,
  rememberImaCollectorDraft,
  imaCollectorFormRevision,
  rateBar,
  currentRouteSeq: () => routeRenderSeq,
});

const {
  loadAdminKnowledge,
  switchKnowledgeSettingsTab,
  onKnowledgeTabsKey,
} = createAdminKnowledgeView({
  $,
  state,
  api,
  flash,
  escapeHtml,
  emptyState,
  routeStillActive,
  currentRouteSeq: () => routeRenderSeq,
  currentAdminSeq: () => _adminRenderSeq,
  routeQuery,
  REFRESH_ICON,
  setPageTitle,
  imaMountState,
  imaCollectorPureCache,
  imaStoragePanelHtml,
  fmtCacheBytes,
  imaCollectorHasUnsaved,
  imaCollectorFormSnapshot,
  rememberImaCollectorDraft,
  initImaMountState,
  renderImaMountGroups,
  renderImaGroupAcl,
  imaGroupIntervalSeconds,
  imaMountGroup,
  restoreImaCollectorOwnerToken,
  clearImaCollectorDraft,
  startImaProgressPoll,
  stopImaProgressPoll,
  applyImaCollectorProgress,
  imaCollectorFormRevision,
  imaCollectorStatusText,
  imaGroupDiscoveryStatusText,
  imaCollectorProgressHtml,
  cookieUpdatedLabel,
  stopStatsTimer,
  renderStatsData,
  startDashboardLiveTimer,
  loadLocalLibraries,
  loadCiccStatus,
  startCiccPoll,
  stopCiccPoll,
  loadStorageHealth,
  loadFeishuDocumentSources,
  nextStatsLoadSeq: () => ++_adminStatsLoadSeq,
  currentStatsLoadSeq: () => _adminStatsLoadSeq,
  getStatsSnapshot: () => _lastAdminStatsSnapshot,
  setStatsSnapshot: (s) => { _lastAdminStatsSnapshot = s; },
});


function replaceRoute(path) {
  const url = normalizeRoute(path);
  if (location.pathname + location.search !== url) history.replaceState(null, "", url);
  router();
}

function migrateHashRoute() {
  const hash = location.hash;
  if (!hash || hash === "#" || hash === "#main") return;
  if (!hash.startsWith("#/")) return;
  history.replaceState(null, "", normalizeRoute(hash));
}

async function router() {
  const renderSeq = ++routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  stopSettingsPoll();
  stopSysLogsTimer();
  stopStatsTimer();
  stopImaProgressPoll();
  stopTimelinePoll();
  // 离开 MX观点页：关 SSE 连接、停时钟/兜底轮询（重进页面时会重建）
  if (typeof mxvTeardown === "function") mxvTeardown();
  // 离开动态页前记录滚动位置，切回时恢复阅读位置
  if (document.querySelector("#feed")) {
    if (isLiveTimeline()) _liveSavedScrollY = window.scrollY;
    else _tlSavedScrollY = window.scrollY;
  }
  const path = routePath();
  const [page, rawParam] = path.split("/");
  if (page !== "news") clearNewsReaderState();
  if (page !== "settings") state.settingsTab = "push";
  // 管理后台默认全景概览：/admin 与 /admin/dashboard 等价，侧边栏高亮才能对上
  const param = page === "admin" && !rawParam ? "dashboard" : rawParam;
  if (!state.token) {
    $("#app-view").classList.add("hidden");
    $("#auth-view").classList.remove("hidden");
    return;
  }
  let user;
  try {
    user = await api("/api/me");
  } catch {
    if (!sessionOwnerStillActive(renderSeq, token, sessionGeneration)) return;
    return;
  }
  if (!sessionOwnerStillActive(renderSeq, token, sessionGeneration)) return;
  $("#app-view").classList.remove("hidden");
  $("#auth-view").classList.add("hidden");
  state.user = user;
  state.newsVisible = user.news_visible !== false;
  if (page === "news" && !state.newsVisible) {
    replaceRoute("timeline");
    return;
  }
  renderSidebar(state.user);
  renderTopbar(state.user);
  renderBottomNav(state.user);
  prefetchLiveFeed();
  const navPage = page === "ima-documents" ? "knowledge" : page;
  document.querySelectorAll(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.route === navPage || b.dataset.route === `${navPage}/${param}`)
  );
  // 底部栏高亮：管理员进后台页时高亮「更多」
  const activeBottom = navPage === "admin" ? "more" : navPage;
  document.querySelectorAll(".bnav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.route === activeBottom)
  );
  try {
    if (page === "home") await renderHome(renderSeq);
    else if (page === "combinations") {
      state.platform = "combination";
      replaceRoute("home");
      return;
    }
    else if (page === "mysubs") {
      state.homeSubscribed = true;
      replaceRoute("home");
      return;
    }
    else if (page === "news") await renderNewsCenter(renderSeq, rawParam);
    else if (page === "zsxq") {
      state.timelinePlatform = timelineVisibleSet().has("zsxq") ? "zsxq" : "";
      replaceRoute("timeline");
      return;
    }
    else if (page === "timeline") await renderTimeline(renderSeq);
    else if (page === "mx-views") await renderMxViews(renderSeq);
    else if (page === "settings") await renderSettings(renderSeq);
    else if (page === "more") await renderMore(renderSeq);
    else if (page === "search") await renderSearch(renderSeq);
    else if (page === "kol") await renderKolPage(Number(param), renderSeq);
    else if (page === "ima-documents") {
      const next = `${location.pathname.replace(/^\/ima-documents\b/, "/knowledge")}${location.search}`;
      if (location.pathname + location.search !== next) history.replaceState(null, "", next);
      await renderKnowledge(renderSeq, param);
    }
    else if (page === "knowledge") await renderKnowledge(renderSeq, param);
    else if (page === "admin") {
      if (!state.user.is_admin) { replaceRoute("timeline"); return; }
      // 分类管理/标签管理已合并为 admin/vocab：旧书签自动跳转
      if (param === "categories" || param === "tags") {
        replaceRoute("admin/vocab");
        return;
      }
      await renderAdmin(param || "dashboard", renderSeq);
    }
    else { replaceRoute("timeline"); return; }
  } catch (err) {
    // 只在当前路由仍是本次渲染目标时才写错误状态，避免旧路由的错误覆盖新页面
    if (routeStillActive(renderSeq)) $("#main").innerHTML = emptyState(err.message);
  }
}

// ---------- 认证 ----------
function togglePassword(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  btn.classList.toggle("visible", show);
  btn.setAttribute("aria-label", show ? "隐藏密码" : "显示密码");
  btn.setAttribute("aria-pressed", String(show));
}

async function doLogin(e) {
  e.preventDefault();
  $("#auth-error").textContent = "";
  const btn = $("#login-form").querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.textContent = "登录中…";
  try {
    const data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: $("#login-username").value.trim(), password: $("#login-password").value }),
    });
    state.token = data.token;
    localStorage.setItem("dav_token", data.token);
    go("timeline");
  } catch (err) {
    $("#auth-error").textContent = err.message;
    btn.disabled = false;
    btn.textContent = "登 录";
  }
}

async function doRegister(e) {
  e.preventDefault();
  $("#reg-error").textContent = "";
  const username = $("#reg-username").value.trim();
  const ruleErr = usernameRuleError(username);
  if (ruleErr) {
    $("#reg-error").textContent = ruleErr;
    return;
  }
  const btn = $("#register-form").querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.textContent = "创建中…";
  try {
    const data = await api("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        username,
        password: $("#reg-password").value,
        code: $("#reg-code").value.trim(),
      }),
    });
    state.token = data.token;
    localStorage.setItem("dav_token", data.token);
    go("timeline");
  } catch (err) {
    $("#reg-error").textContent = err.message;
    btn.disabled = false;
    btn.textContent = "创建账号";
  }
}

function switchAuthMode(mode) {
  const isLogin = mode === "login";
  const loginForm = $("#login-form");
  const registerForm = $("#register-form");
  loginForm.classList.toggle("hidden", !isLogin);
  registerForm.classList.toggle("hidden", isLogin);
  loginForm.hidden = !isLogin;
  registerForm.hidden = isLogin;
  $("#auth-error").textContent = "";
  $("#reg-error").textContent = "";
  resetAuthButtons();
  document.querySelectorAll(".switch-btn").forEach((btn) => {
    const on = btn.dataset.mode === mode;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", String(on));
  });
}

// ---------- 事件 ----------
$("#login-form").addEventListener("submit", doLogin);
$("#register-form").addEventListener("submit", doRegister);
document.querySelectorAll(".switch-btn").forEach((btn) =>
  btn.addEventListener("click", () => switchAuthMode(btn.dataset.mode))
);
$("#btn-back").addEventListener("click", () => {
  if (state.pageBackRoute) go(state.pageBackRoute);
  else history.back();
});
// 本地库卡片按钮：slug 来自存储机目录名，用 data 属性委托而非内联 onclick（防 JS 注入）
document.addEventListener("click", (e) => {
  const add = e.target.closest("[data-acl-add]");
  if (add) {
    addAclUser(add.getAttribute("data-acl-add"), add.closest(".ima-acl-picker"));
    return;
  }
  const remove = e.target.closest("[data-acl-remove]");
  if (remove) {
    removeAclUser(remove.getAttribute("data-acl-remove"), remove.closest(".ima-acl-picker"));
    return;
  }
  const edit = e.target.closest("[data-ll-edit]");
  if (edit) {
    openLocalLibraryModal(edit.dataset.llEdit);
    return;
  }
  const toggle = e.target.closest("[data-ll-toggle]");
  if (toggle) toggleLocalLibrary(toggle.dataset.llToggle, toggle.dataset.llEnabled === "true");
});
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a || a.target === "_blank" || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const url = new URL(a.getAttribute("href"), location.href);
  if (url.origin !== location.origin) return;
  if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
  if (!isSpaPath(url.pathname)) return;
  e.preventDefault();
  go(url.pathname.replace(/^\/+/, "") + url.search);
});
migrateHashRoute();
window.addEventListener("popstate", router);
window.addEventListener("hashchange", () => {
  const hash = location.hash;
  if (!hash.startsWith("#/")) return; // 保留 #main
  migrateHashRoute();
  router();
});

// ---------- AI 分析任务管理 ----------
async function loadAdminAiAnalysis() {
	  let tasks, defaultPrompt, kols;
	  try {
	    [tasks, defaultPrompt, kols] = await Promise.all([
	      api("/api/admin/ai-tasks"),
	      api("/api/admin/ai-tasks/default-prompt").catch(() => ""),
	      api("/api/kols")
	    ]);
	  } catch (err) {
	    if (!routeStillActive(_adminRenderSeq)) return;
	    $("#admin-body").innerHTML = emptyState("加载失败: " + err.message);
	    return;
	  }
	  // API返回的是 { tasks: [...] } 对象，提取数组
	  state.aiTasks = tasks && tasks.tasks ? tasks.tasks : [];
	  state.aiDefaultPrompt = defaultPrompt && defaultPrompt.prompt ? defaultPrompt.prompt : "";
	  state.kols = kols || [];
	  // 创建 KOL ID 到名称的映射
	  state.kolIdToName = {};
	  for (const k of kols) {
	    state.kolIdToName[k.id] = k.name;
	  }
	  renderAdminAiAnalysis();
	}

function renderAdminAiAnalysis() {
  if (!routeStillActive(_adminRenderSeq)) return;
  const body = $("#admin-body");
  if (!body) return;
  const tasks = state.aiTasks || [];
  const enabledCount = tasks.filter(t => t.enabled).length;

  const rows = tasks.map(task => {
    const scheduleDays = task.schedule_day_of_week ? task.schedule_day_of_week.split(',').map(d => {
      const days = ['日', '一', '二', '三', '四', '五', '六'];
      return `周${days[Number(d)]}`;
    }).sort((a, b) => {
      // 排序：周一到周日
      const order = { '周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6 };
      return order[a] - order[b];
    }).join(', ') : '';
    const lastRunStatus = task.last_run_status;
    const lastRunStatusClass = lastRunStatus === 'success' ? 'success' : lastRunStatus === 'failed' ? 'error' : 'neutral';
    const lastRunStatusText = lastRunStatus === 'success' ? '成功' : lastRunStatus === 'failed' ? '失败' : '未运行';
    // 自动重试后仍失败被停用的任务单独标注，与手动禁用区分开
    const autoStopped = !task.enabled && lastRunStatus === 'failed' && Number(task.fail_count || 0) >= 2;
    const statusBadgeCls = task.enabled ? 'enabled' : (autoStopped ? 'disabled auto-stopped' : 'disabled');
    const statusBadgeText = task.enabled ? '已启用' : (autoStopped ? '失败停用' : '已禁用');
    const targetKol = (state.kolIdToName && state.kolIdToName[task.target_kol_id]) || `ID: ${task.target_kol_id}`;
    const analyzedCount = (() => {
      try {
        const kols = typeof task.selected_kol_ids === 'string'
          ? task.selected_kol_ids.split(',').map(s => s.trim()).filter(Boolean)
          : (task.selected_kol_ids || []);
        return `${kols.length} 个`;
      } catch {
        return '未知';
      }
    })();
    const schedule = [scheduleDays, task.schedule_time].filter(Boolean).map(escapeHtml).join(' ') || '—';

    return `
      <tr>
        <td>
          <div class="ai-task-cell-main">${escapeHtml(task.name)}</div>
          ${task.description ? `<div class="ai-task-cell-sub">${escapeHtml(task.description)}</div>` : ''}
        </td>
        <td>
          <span class="ai-task-status-badge ${statusBadgeCls}" ${autoStopped ? 'title="自动重试后仍失败，已停止调度；修复后可点「启用」恢复"' : ''}>${statusBadgeText}</span>
          ${autoStopped ? `<div class="ai-task-cell-sub">连续失败 ${task.fail_count} 次</div>` : ''}
        </td>
        <td>${escapeHtml(targetKol)}</td>
        <td>${schedule}</td>
        <td>${analyzedCount}</td>
        <td>
          <span class="ai-task-run-status ${lastRunStatusClass}">${lastRunStatusText}</span>
          ${task.last_run_at ? `<div class="ai-task-run-time">${escapeHtml(fmtDbTime(task.last_run_at))}</div>` : ''}
        </td>
        <td>
          <button type="button" class="btn-sm" onclick="runAiTask(${task.id})">运行</button>
          <button type="button" class="btn-sm" onclick="openAiTaskModal(${task.id})">编辑</button>
          <button type="button" class="btn-sm" onclick="viewAiTaskLogs(${task.id})">日志</button>
          <button type="button" class="btn-sm ${task.enabled ? 'danger' : ''}" onclick="toggleAiTask(${task.id}, ${task.enabled ? 1 : 0})">${task.enabled ? '禁用' : '启用'}</button>
          <button type="button" class="btn-sm danger" onclick="deleteAiTask(${task.id})">删除</button>
        </td>
      </tr>
    `;
  }).join('');

  body.innerHTML = `
    <div class="ai-analysis-page">
      <section class="section-panel">
        <header class="section-head ai-head-row">
          <div>
            <h2 class="section-title">AI 分析任务</h2>
            <p class="section-meta">${tasks.length} 个任务 · ${enabledCount} 个已启用</p>
          </div>
          <button type="button" class="btn-normal ai-new-task-btn" onclick="openAiTaskModal()">＋ 新建任务</button>
        </header>
        ${tasks.length ? `
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">任务</th>
                <th scope="col">状态</th>
                <th scope="col">目标 KOL</th>
                <th scope="col">调度</th>
                <th scope="col">分析范围</th>
                <th scope="col">上次运行</th>
                <th scope="col">操作</th>
              </tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>` : `
        <div class="ai-analysis-empty">
          <div class="empty-state-icon">${BRAIN_ICON}</div>
          <h3>开始使用 AI 分析</h3>
          <p>点击右上角「新建任务」来设置你的第一个 AI 分析任务</p>
        </div>`}
      </section>
    </div>
  `;
}

async function openAiTaskModal(taskId = null) {
		  const task = taskId ? (state.aiTasks || []).find(t => t.id === taskId) : null;
		  const isEdit = !!taskId;
	  
	  // 确保 KOL 数据已加载
	  if (!state.kols || !state.kols.length) {
	    try {
	      state.kols = await api("/api/kols");
	    } catch {
	      state.kols = [];
	    }
	  }
	  
	  // 顺序：周一到周日，对应的数字值是 1,2,3,4,5,6,0
	  const daysOrder = [
	    { num: 1, label: '一' },
	    { num: 2, label: '二' },
	    { num: 3, label: '三' },
	    { num: 4, label: '四' },
	    { num: 5, label: '五' },
	    { num: 6, label: '六' },
	    { num: 0, label: '日' }
	  ];
	  
	  const daysOptions = daysOrder.map(({ num, label }) => {
	    const isChecked = task && task.schedule_day_of_week && task.schedule_day_of_week.split(',').includes(String(num));
	    return `
	      <div class="ai-day-checkbox ${isChecked ? 'checked' : ''}" data-day="${num}">
	        <span class="ai-day-label">周${label}</span>
	      </div>
	    `;
	  }).join('');
		  
			// 加载 KOL 列表用于选择目标 KOL
			let kolSelectHtml = '<option value="">加载中...</option>';
			try {
			  const kols = state.kols || await api("/api/kols");
			  // 仅显示系统平台的 KOL
			  const systemKols = kols.filter((k) => k.platform === 'system');
			  kolSelectHtml = systemKols
			    .map((k) => `<option value="${k.id}" ${task && task.target_kol_id == k.id ? 'selected' : ''}>${escapeHtml(k.name)}</option>`)
			    .join("");
			  if (!systemKols.length) {
			    kolSelectHtml = '<option value="">暂无系统 KOL</option>';
			  }
			} catch {
			  kolSelectHtml = '<option value="">加载失败，请手动输入 KOL ID</option>';
			}

	const mask = document.createElement("div");
	mask.className = "modal-mask";
	mask.innerHTML = `
	    <div class="ai-task-modal modal-card" role="dialog" aria-modal="true" aria-labelledby="ai-task-title">
	      <div class="ai-modal-header">
	        <h3 id="ai-task-title">${isEdit ? '编辑 AI 分析任务' : '新建 AI 分析任务'}</h3>
	        <button class="ai-modal-close" onclick="closeAdminModal()" aria-label="关闭">
	          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
	            <line x1="18" y1="6" x2="6" y2="18"/>
	            <line x1="6" y1="6" x2="18" y2="18"/>
	          </svg>
	        </button>
	      </div>
	      
	      <div class="ai-modal-body">
	        <div class="ai-form-section">
	          <div class="ai-form-section-title">基本信息</div>
	          
	          <div class="ai-form-group">
	            <label class="ai-form-label">
	              <span>任务名称 <span class="required">*</span></span>
	              <input id="ai-task-name" class="ai-form-input" type="text" value="${task ? escapeHtml(task.name) : ''}" placeholder="例如：每日市场热点分析">
	            </label>
	            
	            <label class="ai-form-label">
	              <span>任务描述</span>
	              <textarea id="ai-task-desc" class="ai-form-textarea" rows="2" placeholder="简单描述这个任务的用途">${task ? escapeHtml(task.description || '') : ''}</textarea>
	            </label>
	          </div>
	        </div>

	        <div class="ai-form-section">
	          <div class="ai-form-section-title">目标设置</div>
	          
	          <div class="ai-form-group">
	            <label class="ai-form-label">
	              <span>目标 KOL <span class="required">*</span></span>
	              <select id="ai-task-target-kol" class="ai-form-select">
	                <option value="">请选择 KOL（分析结果将发布到此 KOL）</option>
	                ${kolSelectHtml}
	              </select>
	            </label>
	          </div>
	        </div>

        <div class="ai-form-section">
          <div class="ai-form-section-title">时间范围</div>
          
          <div class="ai-form-row">
            <label class="ai-form-label ai-form-label-half">
              <span>开始: 天数偏移 <span class="required">*</span></span>
              <input id="ai-task-start-offset" class="ai-form-input" type="number" value="${task ? task.time_range_start_days_offset : '-1'}" placeholder="-1 表示昨天">
            </label>
            
            <label class="ai-form-label ai-form-label-half">
              <span>开始: 时间点 <span class="required">*</span></span>
              <input id="ai-task-start-time" class="ai-form-input" type="time" value="${task ? task.time_range_start_time : '21:00'}">
            </label>
          </div>
          
          <div class="ai-form-row">
            <label class="ai-form-label ai-form-label-half">
              <span>结束: 天数偏移 <span class="required">*</span></span>
              <input id="ai-task-end-offset" class="ai-form-input" type="number" value="${task ? task.time_range_end_days_offset : '0'}" placeholder="0 表示今天">
            </label>
            
            <label class="ai-form-label ai-form-label-half">
              <span>结束: 时间点 <span class="required">*</span></span>
              <input id="ai-task-end-time" class="ai-form-input" type="time" value="${task ? task.time_range_end_time : '08:00'}">
            </label>
          </div>
          
          <div class="ai-form-hint">
            例如：从昨天 21:00 到今天 08:00，将分析这段时间内的内容
          </div>
        </div>

	        <div class="ai-form-section">
	          <div class="ai-form-section-title">分析范围</div>
	          
	          <div class="ai-form-group">
	            <label class="ai-form-label">
	              <span>选择要分析的 KOL <span class="required">*</span></span>
	            </label>
	            <div class="ai-kol-dropdown">
	              <div id="ai-kol-dropdown-trigger" class="ai-kol-dropdown-trigger">
	                <span id="ai-kol-selected-text" class="ai-kol-selected-text">点击选择 KOL</span>
	                <svg class="ai-kol-dropdown-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
	                  <polyline points="6 9 12 15 18 9"/>
	                </svg>
	              </div>
	            <div id="ai-kol-dropdown-menu" class="ai-kol-dropdown-menu">
	                ${(() => {
	                  const selectedIds = task && task.selected_kol_ids 
	                    ? (Array.isArray(task.selected_kol_ids) ? task.selected_kol_ids : JSON.parse(task.selected_kol_ids || '[]'))
	                    : [];
	                  
	                  // 已选的KOL排在前面
	                  const sortedKols = [...(state.kols || [])].sort((a, b) => {
	                    const aSelected = selectedIds.includes(a.id);
	                    const bSelected = selectedIds.includes(b.id);
	                    if (aSelected && !bSelected) return -1;
	                    if (!aSelected && bSelected) return 1;
	                    return 0; // 保持原有顺序
	                  });
	                  
		                  return sortedKols.map(kol => {
		                    const isSelected = selectedIds.includes(kol.id);
		                    return `
		                  <div class="ai-kol-item ${isSelected ? 'checked' : ''}" 
		                       data-kol-id="${kol.id}">
		                    <input type="checkbox" class="ai-kol-checkbox" id="ai-kol-${kol.id}" value="${kol.id}" 
		                           ${isSelected ? 'checked' : ''}>
		                    <div class="ai-kol-content">
		                      <span class="ai-kol-name">${escapeHtml(kol.name)}</span>
		                      <span class="ai-kol-platform">${escapeHtml(kol.platform || '未知平台')}</span>
		                    </div>
		                  </div>
		                `}).join('');
	                })()}
	            </div>
	            </div>
	          </div>
	        </div>

        <div class="ai-form-section">
          <div class="ai-form-section-title">Prompt 模板</div>
          
          <div class="ai-form-group">
            <label class="ai-form-label">
              <span>自定义 Prompt</span>
              <textarea id="ai-task-prompt" class="ai-form-textarea ai-prompt-textarea" rows="8" placeholder="留空则使用默认模板">${task ? escapeHtml(task.prompt_template || '') : ''}</textarea>
            </label>
            <button type="button" class="ai-form-btn-secondary" onclick="restoreDefaultPrompt()">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="1 4 1 10 7 10"/>
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
              </svg>
              恢复默认模板
            </button>
          </div>
        </div>

        <div class="ai-form-section">
          <div class="ai-form-section-title">调度设置</div>
          
          <div class="ai-form-row">
            <label class="ai-form-label ai-form-label-half">
              <span>调度时间 <span class="required">*</span></span>
              <input id="ai-task-schedule-time" class="ai-form-input" type="time" value="${task ? task.schedule_time : '09:00'}">
            </label>
          </div>
          
          <div class="ai-form-group">
            <label class="ai-form-label">
              <span>调度星期 <span class="required">*</span></span>
              <div class="ai-days-container">
                ${daysOptions}
              </div>
            </label>
          </div>
        </div>

        ${isEdit ? `
          <div class="ai-form-section">
            <div class="ai-form-section-title">任务状态</div>
            
            <div class="ai-form-group">
              <label class="ai-form-label">
                <span>状态</span>
                <select id="ai-task-enabled" class="ai-form-select">
                  <option value="1" ${task.enabled ? 'selected' : ''}>已启用 - 任务将按计划运行</option>
                  <option value="0" ${!task.enabled ? 'selected' : ''}>已禁用 - 任务暂停运行</option>
                </select>
              </label>
            </div>
          </div>
        ` : ''}
      </div>

      <div class="ai-modal-footer">
        <button type="button" class="ai-modal-btn ai-modal-btn-cancel" onclick="closeAdminModal()">取消</button>
        <button type="button" class="ai-modal-btn ai-modal-btn-primary" onclick="saveAiTask(${taskId || 'null'})">${isEdit ? '保存修改' : '创建任务'}</button>
      </div>
    </div>
  `;

  closeAdminModal();
  document.body.appendChild(mask);
  
	  // 添加星期选择和 KOL 选择的交互效果
	  setTimeout(() => {
	    // 星期选择
	    const dayCheckboxes = document.querySelectorAll('.ai-day-checkbox');
	    dayCheckboxes.forEach(checkbox => {
	      checkbox.addEventListener('click', () => {
	        checkbox.classList.toggle('checked');
	      });
	    });
	    
	    // KOL 下拉框
	    const dropdownTrigger = document.getElementById('ai-kol-dropdown-trigger');
	    const dropdownMenu = document.getElementById('ai-kol-dropdown-menu');
	    const selectedText = document.getElementById('ai-kol-selected-text');
	    
	    // 更新已选 KOL 显示
	    function updateSelectedKolsDisplay() {
	      const checkedBoxes = document.querySelectorAll('.ai-kol-checkbox:checked');
	      if (checkedBoxes.length === 0) {
	        selectedText.textContent = '点击选择 KOL';
	        selectedText.classList.add('placeholder');
	      } else if (checkedBoxes.length <= 3) {
	        const names = Array.from(checkedBoxes).map(cb => {
	          const kol = state.kols.find(k => k.id === Number(cb.value));
	          return kol ? kol.name : '';
	        }).filter(Boolean);
	        selectedText.textContent = names.join(', ');
	        selectedText.classList.remove('placeholder');
	      } else {
	        selectedText.textContent = `已选择 ${checkedBoxes.length} 个 KOL`;
	        selectedText.classList.remove('placeholder');
	      }
	    }
	    
	    // 初始化显示
	    updateSelectedKolsDisplay();
	    
	    // 下拉框切换
	    dropdownTrigger.addEventListener('click', (e) => {
	      e.stopPropagation();
	      dropdownMenu.classList.toggle('open');
	      dropdownTrigger.classList.toggle('open');
	    });
	    
	    // 点击外部关闭下拉框
	    document.addEventListener('click', (e) => {
	      if (!e.target.closest('.ai-kol-dropdown')) {
	        dropdownMenu.classList.remove('open');
	        dropdownTrigger.classList.remove('open');
	      }
	    });
	    
		    // KOL 选择
		    const kolItems = document.querySelectorAll('.ai-kol-item');
		    kolItems.forEach(item => {
		      const checkbox = item.querySelector('.ai-kol-checkbox');
		      
		      // 点击整个item区域时切换选中状态
		      item.addEventListener('click', (e) => {
		        // 不阻止input的默认行为
		        if (e.target !== checkbox) {
		          e.preventDefault();
		          checkbox.checked = !checkbox.checked;
		          // 触发change事件
		          checkbox.dispatchEvent(new Event('change'));
		        }
		      });
		      
		      // 监听checkbox的change事件
		      checkbox.addEventListener('change', () => {
		        item.classList.toggle('checked', checkbox.checked);
		        updateSelectedKolsDisplay();
		      });
		    });
	  }, 50);
}

function restoreDefaultPrompt() {
  const input = document.getElementById("ai-task-prompt");
  if (input && state.aiDefaultPrompt) {
    input.value = state.aiDefaultPrompt;
  }
}

async function saveAiTask(taskId = null) {
	  const name = document.getElementById("ai-task-name").value.trim();
	  const desc = document.getElementById("ai-task-desc").value.trim();
	  const targetKolId = Number(document.getElementById("ai-task-target-kol").value);
	  const startOffset = Number(document.getElementById("ai-task-start-offset").value);
	  const startTime = document.getElementById("ai-task-start-time").value;
	  const endOffset = Number(document.getElementById("ai-task-end-offset").value);
	  const endTime = document.getElementById("ai-task-end-time").value;
	  const prompt = document.getElementById("ai-task-prompt").value.trim();
	  const scheduleTime = document.getElementById("ai-task-schedule-time").value;
	  const enabledEl = document.getElementById("ai-task-enabled");
	  const enabled = enabledEl ? enabledEl.value === "1" : true;

	  const kolIds = Array.from(document.querySelectorAll('.ai-kol-checkbox:checked')).map(cb => Number(cb.value));

  if (!name || !targetKolId || !startTime || !endTime || !kolIds.length || !scheduleTime) {
    flash("请填写所有必填项", "error");
    return;
  }

  const scheduleDays = Array.from(document.querySelectorAll('.ai-day-checkbox.checked'))
    .map(el => el.dataset.day)
    .join(',');

  if (!scheduleDays) {
    flash("请至少选择一个调度星期", "error");
    return;
  }

  try {
    const body = {
      name,
      description: desc || null,
      target_kol_id: targetKolId,
      time_range_start_days_offset: startOffset,
      time_range_start_time: startTime,
      time_range_end_days_offset: endOffset,
      time_range_end_time: endTime,
      selected_kol_ids: kolIds,
      prompt_template: prompt || state.aiDefaultPrompt,
      schedule_day_of_week: scheduleDays,
      schedule_time: scheduleTime
    };

    if (taskId) {
      body.enabled = enabled;
      await api(`/api/admin/ai-tasks/${taskId}`, {
        method: "PUT",
        body: JSON.stringify(body)
      });
      flash("任务已更新");
    } else {
      await api("/api/admin/ai-tasks", {
        method: "POST",
        body: JSON.stringify(body)
      });
      flash("任务已创建");
    }

    closeAdminModal();
    await loadAdminAiAnalysis();
  } catch (err) {
    flash(err.message, "error");
  }
}

async function runAiTask(taskId) {
  if (!(await showConfirm("确定要立即运行此任务吗？"))) return;
  try {
    await api(`/api/admin/ai-tasks/${taskId}/run`, { method: "POST" });
    flash("任务已开始运行，请稍后查看日志");
  } catch (err) {
    flash(err.message, "error");
  }
}

async function toggleAiTask(taskId, currentlyEnabled) {
  const action = currentlyEnabled ? "禁用" : "启用";
  if (!(await showConfirm(`确定要${action}此任务吗？`))) return;
  try {
    // 启用时后端会重算下次运行时间并清零连续失败计数
    await api(`/api/admin/ai-analysis/tasks/${taskId}/${currentlyEnabled ? "disable" : "enable"}`, { method: "POST" });
    flash(`任务已${action}`);
    await loadAdminAiAnalysis();
  } catch (err) {
    flash(err.message, "error");
  }
}

async function deleteAiTask(taskId) {
  if (!(await showConfirm("确定要删除此任务吗？此操作不可恢复。"))) return;
  try {
    await api(`/api/admin/ai-tasks/${taskId}`, { method: "DELETE" });
    flash("任务已删除");
    await loadAdminAiAnalysis();
  } catch (err) {
    flash(err.message, "error");
  }
}

function aiLogStatusMeta(status) {
  if (status === "success") return { cls: "success", label: "成功" };
  if (status === "failed") return { cls: "error", label: "失败" };
  if (status === "running") return { cls: "running", label: "运行中" };
  return { cls: "running", label: status || "未知" };
}

function aiLogBrief(log) {
  if (log.status === "running") return "运行中…";
  if (log.status === "failed") return log.message || "运行失败";
  if (log.post_count != null) {
    return log.post_count > 0 ? `分析了 ${log.post_count} 条发言` : "窗口内没有发言";
  }
  return log.message || "分析完成";
}

function aiLogDuration(log) {
  if (!log.started_at || !log.completed_at) return "";
  const t1 = Date.parse(log.started_at);
  const t2 = Date.parse(log.completed_at);
  if (Number.isNaN(t1) || Number.isNaN(t2)) return "";
  const s = Math.round((t2 - t1) / 1000);
  if (s <= 0) return "";
  if (s < 60) return `${s} 秒`;
  return `${Math.floor(s / 60)} 分 ${s % 60} 秒`;
}

function aiLogRowHtml(log) {
  const meta = aiLogStatusMeta(log.status);
  const brief = escapeHtml(aiLogBrief(log));
  const time = fmtDbTime(log.started_at);
  const shortTime = time === "-" ? "-" : time.slice(5, 16); // MM-DD HH:MM
  const dur = aiLogDuration(log);
  const toks = log.total_tokens > 0 ? `${log.total_tokens} tokens` : "";
  const rowMeta = [toks, dur].filter(Boolean).map(escapeHtml).join(" · ");
  return `
    <div class="ai-log-row ${meta.cls}">
      <button type="button" class="ai-log-row-main" onclick="toggleAiLogDetail(this)" aria-expanded="false">
        <span class="ai-log-dot"></span>
        <span class="ai-log-row-time">${escapeHtml(shortTime)}</span>
        <span class="ai-log-row-brief" title="${brief}">${brief}</span>
        ${rowMeta ? `<span class="ai-log-row-meta">${rowMeta}</span>` : ""}
        <svg class="ai-log-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
      <div class="ai-log-detail">
        <div class="ai-log-facts">
          <span>状态 <b>${meta.label}</b></span>
          <span>开始 <b>${escapeHtml(time)}</b></span>
          ${log.completed_at ? `<span>结束 <b>${escapeHtml(fmtDbTime(log.completed_at))}</b></span>` : ""}
          ${dur ? `<span>耗时 <b>${escapeHtml(dur)}</b></span>` : ""}
          ${log.post_count != null ? `<span>发言 <b>${log.post_count} 条</b></span>` : ""}
          ${log.total_tokens > 0 ? `<span>Tokens <b>提示 ${log.prompt_tokens || 0} · 完成 ${log.completion_tokens || 0} · 总计 ${log.total_tokens}</b></span>` : ""}
        </div>
        ${log.message ? `<div class="ai-log-msg">${escapeHtml(log.message)}</div>` : ""}
        ${log.output_post_id || log.has_prompt ? `
        <div class="ai-log-detail-actions">
          ${log.output_post_id ? `
          <a href="#" onclick="event.preventDefault();viewAiReportPost(${log.output_post_id})">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <polyline points="15 3 21 3 21 9"/>
              <line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
            查看输出帖子
          </a>` : ""}
          ${log.has_prompt ? `
          <a href="#" onclick="event.preventDefault();viewAiPrompt(${log.id})">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
            </svg>
            查看发送给大模型的内容
          </a>` : ""}
        </div>` : ""}
      </div>
    </div>`;
}

function toggleAiLogDetail(headerEl) {
  const row = headerEl.closest(".ai-log-row");
  const wasOpen = row.classList.contains("open");
  document.querySelectorAll(".ai-log-row.open").forEach((r) => r.classList.remove("open"));
  if (!wasOpen) {
    row.classList.add("open");
    headerEl.setAttribute("aria-expanded", "true");
  }
}

async function viewAiTaskLogs(taskId) {
  try {
    const resp = await api(`/api/admin/ai-tasks/${taskId}/logs`);
    const logs = Array.isArray(resp) ? resp : (resp.logs || []);
    state.aiTaskLogs = logs;
    state.aiTaskLogsTaskId = taskId;

    const task = (state.aiTasks || []).find(t => t.id === taskId) || resp.task;
    const taskName = task ? task.name : '未知任务';

    const mask = document.createElement("div");
    mask.className = "modal-mask";

    const logsHtml = logs.length ? logs.map(aiLogRowHtml).join('') : `
      <div class="ai-logs-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
        <p>暂无运行日志</p>
      </div>
    `;

    mask.innerHTML = `
      <div class="ai-logs-modal modal-card" role="dialog" aria-modal="true" aria-labelledby="ai-logs-title">
        <div class="ai-logs-header">
          <div>
            <h3 id="ai-logs-title">运行日志</h3>
            <p class="ai-logs-subtitle">${escapeHtml(taskName)}${logs.length ? ` · 最近 ${logs.length} 次` : ""}</p>
          </div>
          <button class="ai-modal-close" onclick="closeAdminModal()" aria-label="关闭">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="ai-logs-content">
          ${logsHtml}
        </div>
        <div class="ai-logs-footer">
          <button type="button" class="ai-modal-btn ai-modal-btn-primary" onclick="closeAdminModal()">关闭</button>
        </div>
      </div>
    `;

    closeAdminModal();
    document.body.appendChild(mask);
  } catch (err) {
    flash(err.message, "error");
  }
}

async function viewAiReportPost(postId) {
  try {
    const post = await api(`/api/posts/${postId}`);
    const who = post.kol_name ? `${escapeHtml(post.kol_name)} · ` : "";
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="ai-logs-modal modal-card" role="dialog" aria-modal="true" aria-labelledby="ai-report-title">
        <div class="ai-logs-header">
          <div>
            <h3 id="ai-report-title">${escapeHtml(post.title || "AI 分析报告")}</h3>
            <p class="ai-logs-subtitle">${who}${fmtPublished(post.published_at)}</p>
          </div>
          <button class="ai-modal-close" onclick="closeAdminModal()" aria-label="关闭">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="ai-logs-content">
          <div class="ai-report-content">${escapeHtml(post.content || "（无正文）")}</div>
        </div>
        <div class="ai-logs-footer">
          <a class="ai-modal-btn ai-modal-btn-cancel" style="text-decoration:none;display:inline-block" href="/kol/${post.kol_id}" onclick="closeAdminModal()">前往大V主页</a>
          <button type="button" class="ai-modal-btn ai-modal-btn-primary" onclick="closeAdminModal()">关闭</button>
        </div>
      </div>
    `;
    closeAdminModal();
    document.body.appendChild(mask);
  } catch (err) {
    flash(err.message, "error");
  }
}

async function viewAiPrompt(logId) {
  try {
    const resp = await api(`/api/admin/ai-logs/${logId}/prompt`);
    const prompt = resp.prompt || "";
    state.aiPromptText = prompt;
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `
      <div class="ai-logs-modal modal-card" role="dialog" aria-modal="true" aria-labelledby="ai-prompt-title">
        <div class="ai-logs-header">
          <div>
            <h3 id="ai-prompt-title">发送给大模型的内容</h3>
            <p class="ai-logs-subtitle">${prompt.length} 字符</p>
          </div>
          <button class="ai-modal-close" onclick="closeAdminModal()" aria-label="关闭">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="ai-logs-content">
          <div class="ai-report-content">${escapeHtml(prompt)}</div>
        </div>
        <div class="ai-logs-footer">
          <button type="button" class="ai-modal-btn ai-modal-btn-cancel" onclick="copyText(state.aiPromptText || '', '已复制')">复制</button>
          <button type="button" class="ai-modal-btn ai-modal-btn-primary" onclick="closeAdminModal()">关闭</button>
        </div>
      </div>
    `;
    closeAdminModal();
    document.body.appendChild(mask);
  } catch (err) {
    flash(err.message, "error");
  }
}

// PWA：注册 Service Worker（HTTP 或私有模式下失败静默，不影响功能）
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => { });
}

function selectFeishuSource(button) {
  return button.dataset.sourceTarget === "knowledge"
    ? selectImaDocumentGroup(button.dataset.group)
    : selectFeishuTimelineSource(button.dataset.group);
}

function selectPlatformTab(button) {
  return button.dataset.platformTarget === "admin"
    ? switchAdminKolsPlatform(button.dataset.platform)
    : switchPlatform(button.dataset.platform);
}

function reloadTimelineRail() {
  return loadTimelineRail(routeRenderSeq);
}

function reloadTimeline() {
  return loadTimeline(true, routeRenderSeq);
}

function runSearch() {
  return doSearch(routeRenderSeq);
}

function reloadKolImageSettings() {
  return loadKolImageSettings(routeRenderSeq);
}


// ---------- MX 数据源管理（数据源页 st-mx 面板；由 switchStatsTab('mx') 触发加载） ----------
async function loadMxAdmin() {
  const box = $("#st-mx");
  if (!box) return;
  try {
    // Load MX config
    const config = await api("/api/admin/sources/mx");
    $("#mx-enabled").checked = config.enabled;
    $("#mx-token").value = config.token || "";
    $("#mx-api-base").value = config.api_base || "https://mx.2026.naaifu.cn/business-api/5";
    $("#mx-ws-url").value = config.ws_url || "wss://mx.2026.naaifu.cn/business-api/5";
    $("#mx-ws-path").value = config.ws_path || "/socket.io";
    $("#mx-ws-namespace").value = config.ws_namespace || "/msg";
    $("#mx-ws-enabled").checked = config.ws_enabled;
    $("#mx-page-size").value = config.page_size || 30;
    $("#mx-max-pages").value = config.max_history_pages || 100;
    updateMxTokenUpdatedLabel(config);

    // Load rooms
    loadMxRooms();
    refreshMxWsStatus();

    // Add event listeners for search/filter
    const qInput = $("#mx-rooms-q");
    const enabledOnly = $("#mx-rooms-enabled-only");
    if (qInput) {
      let searchTimeout = null;
      qInput.oninput = () => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => loadMxRooms(), 300);
      };
    }
    if (enabledOnly) enabledOnly.onchange = () => loadMxRooms();

  } catch (err) {
    box.innerHTML = `<p class="muted">${escapeHtml(err.message || "加载 MX 配置失败")}</p>
      <div class="toolbar"><button type="button" class="btn-ghost" onclick="loadMxAdmin()">重试</button></div>`;
  }
}

async function saveMxConfig() {
  const btn = $("#mx-save-btn");
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  try {
    // Parse numbers with defaults, ensure minimum values
    const page_size = Math.max(1, Number($("#mx-page-size").value) || 30);
    const max_history_pages = Math.max(1, Number($("#mx-max-pages").value) || 100);

    const payload = {
      enabled: $("#mx-enabled").checked,
      token: $("#mx-token").value.trim(),
      api_base: $("#mx-api-base").value.trim() || "https://mx.2026.naaifu.cn/business-api/5",
      ws_url: $("#mx-ws-url").value.trim() || "wss://mx.2026.naaifu.cn/business-api/5",
      ws_path: $("#mx-ws-path").value.trim() || "/socket.io",
      ws_namespace: $("#mx-ws-namespace").value.trim() || "/msg",
      ws_enabled: $("#mx-ws-enabled").checked,
      page_size,
      max_history_pages,
    };
    console.log("Saving MX config payload:", payload);

    await api("/api/admin/sources/mx", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    flash("MX配置已保存");
    try {
      updateMxTokenUpdatedLabel(await api("/api/admin/sources/mx"));
    } catch {}
    refreshMxWsStatus();
  } catch (err) {
    flash(err.message || "保存失败", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function updateMxTokenUpdatedLabel(config) {
  const el = $("#mx-token-updated");
  if (!el) return;
  if (config.token) {
    el.textContent = config.token_updated_at
      ? `Token 更新于 ${fmtTs(config.token_updated_at)}`
      : "Token 更新时间：暂无记录（Token 可能由环境变量提供）";
    el.style.display = "";
  } else {
    el.style.display = "none";
  }
}

async function refreshMxWsStatus() {
  const el = $("#mx-ws-status");
  if (!el) return;
  try {
    const s = await api("/api/admin/sources/mx/ws-status");
    const last = s.last_message_at ? new Date(s.last_message_at).toLocaleString() : "从未收到";
    const detail = s.detail ? `（${s.detail}）` : "";
    el.innerHTML = `<span>WebSocket 状态：${s.connected ? "✅ 已连接" : "❌ 未连接"}，最近收到消息：${escapeHtml(last)}${escapeHtml(detail)}</span>`;
    renderMxApiStatus(s.login_report);
  } catch (err) {
    el.textContent = `WebSocket 状态：获取失败（${err.message || "未知错误"}）`;
  }
}

function renderMxApiStatus(report) {
  const box = $("#mx-api-status");
  if (!box) return;
  if (!report || !Array.isArray(report.steps) || !report.steps.length) {
    box.textContent = "接口状态：尚无会话记录（等待运行时段到点系统自动 MX 平台登录，或点击「登录」手动执行）";
    return;
  }
  const rows = report.steps.map((s) => {
    const mark = s.ok ? "✅" : "❌";
    const ms = Number.isFinite(s.ms) ? `（${s.ms}ms）` : "";
    return `<li>${mark} ${escapeHtml(s.name)}${ms}：${escapeHtml(s.detail || "")}</li>`;
  }).join("");
  const head = report.ok ? "✅ 全部成功" : "❌ 存在失败项";
  const source = report.source === "auto" ? "系统自动登录" : "管理员手动登录";
  box.innerHTML = `<details><summary>接口状态（${escapeHtml(report.time || "")}，${source}）：${head}</summary><ul>${rows}</ul></details>`;
}

async function mxSessionLogin() {
  const btn = $("#mx-login-btn");
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  if ($("#mx-logout-btn")) $("#mx-logout-btn").disabled = true;
  try {
    const result = await api("/api/admin/sources/mx/session/login", { method: "POST" });
    renderMxApiStatus(result.report);
    flash(result.ok ? "登录成功：启动序列、房间同步与 WS 均正常" : "登录完成，存在失败项（见接口状态）", result.ok ? "success" : "error");
  } catch (err) {
    flash(err.message || "登录失败", "error");
  } finally {
    if (btn) btn.disabled = false;
    if ($("#mx-logout-btn")) $("#mx-logout-btn").disabled = false;
    refreshMxWsStatus();
    setTimeout(refreshMxWsStatus, 2500);
  }
}

async function mxSessionLogout() {
  const btn = $("#mx-logout-btn");
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  try {
    const res = await api("/api/admin/sources/mx/ws/disconnect", { method: "POST" });
    flash(res.message || "已退出 MX 会话");
  } catch (err) {
    flash(err.message || "退出失败", "error");
  } finally {
    if (btn) btn.disabled = false;
    refreshMxWsStatus();
  }
}

async function loadMxRooms() {
  const listBox = $("#mx-rooms-list");
  if (!listBox) return;
  try {
    const q = ($("#mx-rooms-q")?.value || "").toLowerCase();
    const enabledOnly = $("#mx-rooms-enabled-only")?.checked;
    const result = await api(`/api/admin/sources/mx/rooms?search=${encodeURIComponent(q)}&enabled_only=${enabledOnly ? "1" : "0"}`);
    const rooms = result.rooms || [];
    if (!rooms.length) {
      listBox.innerHTML = `<p class="muted">暂无房间，请先同步</p>`;
      return;
    }
    listBox.innerHTML = `<div class="table-wrap">
      <table>
        <thead><tr><th scope="col">房间</th><th scope="col">今日消息</th><th scope="col">最近更新</th><th scope="col">已启用</th><th scope="col">广场显示</th><th scope="col">订阅数</th><th scope="col">操作</th></tr></thead>
        <tbody>
          ${rooms.map((r) => `<tr>
            <td>
              <div class="kol-row-main">
                ${avatarHtml(r.title, r.avatar)}
                <div>
                  <div class="kol-name">${escapeHtml(r.title)}</div>
                  ${r.teaname ? `<div class="muted" style="font-size:12px">${escapeHtml(r.teaname)}</div>` : ""}
                </div>
              </div>
            </td>
            <td>${Number(r.message_today) || 0}</td>
            <td>${r.msgtime ? escapeHtml(r.msgtime) : "-"}</td>
            <td>${r.enabled ? "✅" : "❌"}</td>
            <td>${r.show_in_plaza ? "✅" : "❌"}</td>
            <td>${Number(r.subscriber_count) || 0}</td>
	            <td>
	              <div class="toolbar">
	                <button type="button" class="btn-ghost" onclick="updateMxRoom(${r.id}, { enabled: !${r.enabled} })">${r.enabled ? "禁用" : "启用"}</button>
	                <button type="button" class="btn-ghost" onclick="updateMxRoom(${r.id}, { show_in_plaza: !${r.show_in_plaza} })">${r.show_in_plaza ? "隐藏广场" : "显示广场"}</button>
	                <button type="button" class="btn-ghost" onclick="pullMxRoomHistory(${r.id})">拉取历史消息</button>
	              </div>
	            </td>
          </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
  } catch (err) {
    listBox.innerHTML = `<p class="muted">${escapeHtml(err.message || "加载房间失败")}</p>
      <div class="toolbar"><button type="button" class="btn-ghost" onclick="loadMxRooms()">重试</button></div>`;
  }
}

async function updateMxRoom(roomId, body) {
  try {
    await api(`/api/admin/sources/mx/rooms/${roomId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    flash("房间已更新");
    loadMxRooms();
  } catch (err) {
    flash(err.message || "更新失败", "error");
  }
}

async function pullMxRoomHistory(roomId) {
  try {
    await api(`/api/admin/sources/mx/rooms/${roomId}/pull-history`, {
      method: "POST",
    });
    flash("历史消息拉取已触发");
  } catch (err) {
    flash(err.message || "拉取历史消息失败", "error");
  }
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

const INLINE_HANDLERS = {
  addFeishuDocumentSource,
  adminAddCategory,
  adminApproveRequest,
  adminBackfillTags,
  adminBatchAddKols,
  adminBatchLinesHint,
  adminCodesBatch,
  adminCodesClearSelect,
  adminCodesCopySelected,
  adminCodesNoteInput,
  adminCodesPreset,
  adminCodesToggle,
  adminCodesToggleBatch,
  adminCodesTogglePage,
  adminDeleteCategory,
  adminDeleteKol,
  adminDeleteKolFromHome,
  adminDeleteUser,
  adminEditKol,
  adminFilterLogs,
  adminFilterPosts,
  adminGenerateCodes,
  adminInactivePolicyKeydown,
  adminInactivePolicySyncSave,
  adminKolBatch,
  adminKolBatchCategory,
  adminKolClearSelect,
  adminKolTogglePage,
  adminKolToggleSelect,
  adminKolsApplyFilter,
  adminKolsClearFilter,
  adminKolsPage,
  adminMaintainTags,
  adminOpenUser,
  adminPostsLoadMore,
  adminRejectRequest,
  adminRenameCategory,
  adminRevokeBatch,
  adminRevokeCode,
  adminSaveInactivePolicy,
  adminSavePassword,
  adminSaveStockNames,
  adminSaveTags,
  adminSaveUserKnowledge,
  adminSaveUsername,
  adminSendTestPush,
  adminToggleAdmin,
  adminToggleKol,
  adminTogglePost,
  adminTogglePriority,
  adminToggleSecondary,
  adminUserClearSelect,
  adminUserTogglePage,
  adminUserToggleSelect,
  adminUsersApplyFilter,
  adminUsersBatch,
  applyFeishuTimelineUpdate,
  archiveAdminNewsFeed,
  archiveAdminNewsSource,
  authorizeFeishuDocuments,
  backFromImaReader,
  backupDownload,
  backupImaStorage,
  backupRestoreUpload,
  backupRestoreWebDAV,
  cancelFeishuPersonal,
  clearAdminCodesResult,
  clearImaDocumentsFilter,
  clearImaDocumentsFilters,
  clearSavedCookie,
  closeAdminModal,
  closeLightbox,
  copyImaAbstract,
  copyText,
  createProxyPool,
  cycleTheme,
  deleteProxyNode,
  deleteProxyPool,
  disableWebPush,
  discardImaCollectorChanges,
  discoverImaGroups,
  downloadFeishuTimelineAsset,
  enableWebPush,
  extractProxyPool,
  filterAclSuggest,
  filterKolImageSettings,
  genBindCode,
  go,
  homePickMobilePlatform,
  homeResetFilters,
  homeSearch,
  homeToggleFilter,
  imgOnError,
  importProxyPool,
  jumpFeishuTimelineDay,
  jumpFeishuTimelineLatest,
  lightboxStep,
  loadAdminDashboard,
  loadAdminErrorLogs,
  loadAdminKnowledge,
  loadAdminNews,
  loadAdminStats,
  loadAdminSysLogsPanel,
  loadCiccStatus,
  loadFeishuDocumentSources,
  loadFinancialNews,
  loadImaDocumentsMore,
  loadLlmModels,
  loadMoreFeishuTimeline,
  loadProxyAdmin,
  logout,
  onAclSearchKey,
  onAskLinkInput,
  onKnowledgeTabsKey,
  openAdminKolFromHealth,
  openBindGuide,
  openImaDocument,
  openImaPdfNewTab,
  openLightbox,
  openLocalLibraryCreateModal,
  openNewsArticle,
  openNewsFeedModal,
  openNewsSourceModal,
  openNewsSourcePicker,
  pasteCookieField,
  pickHomeCategory,
  pickImaDay,
  pickImaTag,
  purgeZsxqCache,
  queueFeishuDocumentPreview,
  queueImaDocumentsSearch,
  queueNewsSearch,
  quickSubscribe,
  railToggleSubscribe,
  refreshAdminNewsFeed,
  refreshAllAdminNews,
  refreshDashboardLive,
  refreshFeishuBindCode,
  refreshImaDocuments,
  refreshImaStorage,
  refreshKnowledge,
  refreshTimeline,
  reloadKolImageSettings,
  reloadTimeline,
  reloadTimelineRail,
  removeFeishuDocumentSource,
  renameFeishuDocumentSource,
  renderFinancialNewsArticle,
  renderFinancialNewsList,
  renderTimeline,
  restoreAdminNewsFeed,
  restoreAdminNewsSource,
  retryImaFolderLoad,
  retryImaGroupAcl,
  runSearch,
  runStorageConsistency,
  runStorageDedup,
  saveAdminNewsSettings,
  saveBackupWebDAV,
  saveBarkKey,
  saveCiccCategories,
  saveCiccScheduleTime,
  saveCustomTgBot,
  saveDailyReport,
  saveDnd,
  saveFeishuDocsConfig,
  saveImaCollector,
  saveImgbedSettings,
  clearImgbedSettings,
  saveKeywords,
  saveKeywordsMatchReports,
  saveKolEdit,
  saveLlm,
  saveNewsSources,
  saveNotify,
  savePassword,
  savePollingConfig,
  saveProxyRoutes,
  savePushChannels,
  saveStorageAlerts,
  saveTranslateTwitter,
  saveTwitterCookie,
  saveWecomWebhook,
  saveXueqiuCookie,
  saveZsxqCookie,
  saveZsxqPollingConfig,
  scanLocalLibraries,
  searchAdminCodes,
  selectAdminCodeFilter,
  selectAdminNewsSource,
  selectFeishuSource,
  selectImaDocumentGroup,
  selectImaDocumentsTag,
  selectImaMountGroup,
  selectNewsSource,
  selectPlatformTab,
  setFeishuSourceDisplay,
  setImaGroupInterval,
  setPlazaSourceMode,
  setSubscribeType,
  setTheme,
  startFeishuPersonal,
  startWeiboQr,
  submitAsk,
  submitImaDocumentsSearch,
  subscribeKnowledge,
  switchKnowledgeSettingsTab,
  switchSettingsTab,
  switchStatsTab,
  syncFeishuDocumentSource,
  syncProxyPoolForm,
  syncProxyRouteInputs,
  testBackupWebDAV,
  testProxyNode,
  tlApplyFilter,
  tlApplyRailSearch,
  tlFilterPanel,
  tlOnSearchInput,
  tlPickPlatform,
  tlPickSource,
  tlPickTag,
  tlRemoveFilter,
  tlResetFilters,
  tlTogglePost,
  toggleAdminNewsFeed,
  toggleAdminNewsSource,
  toggleCiccSchedule,
  toggleDnd,
  toggleFavorite,
  toggleFeishuDocumentSource,
  toggleHomeFavorite,
  toggleHomeSubscribed,
  toggleImaAbstract,
  toggleImaAclExpanded,
  toggleImaDayPicker,
  toggleImaFolder,
  toggleImaFolderExpand,
  toggleImaFolderPanel,
  toggleImaTagMenu,
  toggleKolImages,
  toggleKolPageSubscribe,
  toggleLiveImportant,
  togglePassword,
  toggleReportKeyword,
  toggleSecondary,
  toggleSidebarSlim,
  toggleSubscribe,
  toggleTimelineFav,
  toggleTimelineSecondary,
  triggerCicc,
  triggerImaCollector,
  unbindChannel,
  unsubscribeKnowledge,
  updateAdminNewsArchived,
  updateAdminNewsQuery,
  updateAdminNewsStatus,
  // ---- hmf：MX 数据源管理（st-mx 面板）----
  loadMxAdmin,
  saveMxConfig,
  mxSessionLogin,
  mxSessionLogout,
  loadMxRooms,
  updateMxRoom,
  pullMxRoomHistory,
  refreshMxWsStatus,
  // ---- hmf：KOL 管理扩展（系统KOL/屏蔽词/档位/webhook）----
  adminSetTier,
  adminBatchSystemToggle,
  adminKolWebhook,
  adminKolWebhookToggle,
  adminKolWebhookRegenerate,
  adminKolWebhookSaveSecret,
  adminEditKolKeywords,
  saveKolKeywords,
  adminViewKolBlock,
  // ---- hmf：MX LLM 打标面板（词表管理 tab）----
  adminMxTagAutoSave,
  adminMxTagAutoAddSpecial,
  adminMxTagAutoRemoveSpecial,
  adminMxTagCancel,
  adminMxTagOpenRunModal,
  adminMxTagSelAll,
  adminMxTagStartRun,
  adminMxTagTest,
  adminOpenTagReviewModal,
  closeTagReviewModal,
  toggleTagReviewMsg,
  adminTagReviewModalReview,
  adminTagReviewSelAll,
  adminTagReviewSelChange,
  adminReviewTag,
  adminReviewTagsBatch,
  adminReviewAliasCandidate,
  adminTagDetailAddTag,
  adminTagDetailRemoveTag,
  // ---- hmf：帖子管理（隐藏/删除）----
  adminDeletePost,
  adminSetPostHidden,
  // ---- hmf：灯箱缩放工具条 ----
  _lbZoomStep,
  _lbZoomReset,
};
Object.assign(window, INLINE_HANDLERS);

applyTheme(); // 与 index.html 防闪脚本同一逻辑，兜底 + 同步 meta theme-color
router();
