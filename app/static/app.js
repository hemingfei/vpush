import { escapeHtml, imgOnError, imgProxyUrl, imgSrcFor } from "./core/html.js";
import { trapFocus } from "./core/dialog.js";
import { createLightbox } from "./core/lightbox.js";
import { createNewsView } from "./views/news.js";
import { createFeishuPersonalView } from "./views/feishu-personal.js";
import { createAdminCodesView } from "./views/admin/codes.js";
import { createAdminNewsView } from "./views/admin/news.js";
import { createAdminUsersView } from "./views/admin/users.js";
import { createAdminKolsView } from "./views/admin/kol.js";
import { createAdminInfraView } from "./views/admin/infra.js";
import { createAdminDashboardView } from "./views/admin/dashboard.js";
import { createPushSettingsView } from "./views/push-settings.js";

const $ = (sel) => document.querySelector(sel);

const { openLightbox, closeLightbox, lightboxStep } = createLightbox({
  escapeHtml,
  imgOnError,
  trapFocus,
});

const PLATFORM_LABELS = { xueqiu: "雪球", combination: "雪球组合", weibo: "微博", twitter: "X", ima: "ima", zsxq: "知识星球" };
const PLATFORM_SHORT_LABELS = { xueqiu: "雪球", combination: "组合", weibo: "微博", twitter: "X", ima: "ima", zsxq: "星球" };
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
const APP_VERSION = "1.12.136";
const KEYWORDS_MAX_COUNT = 20;
const REPORT_WATCH_BLOCKED_TAGS = new Set([
  "中金研报", "宏观经济", "市场策略", "全球研究", "行业研究", "公司研究",
  "量化及ESG", "大宗商品", "外汇研究", "固定收益", "中金研究院", "其他",
]);
const TL_SOURCE_KEY = "timelineSource";
const PLATFORM_TABS = ["", "xueqiu", "combination", "weibo", "twitter", "zsxq"];
const STATS_TABS = ["config", "cookies", "proxies", "plaza", "news"];
const STALE_KOL_LIMIT = 10;
const STALE_KOL_HOURS = 48;
const TL_PLATFORMS = PLATFORM_TABS.map((p) => [p, p ? PLATFORM_LABELS[p] : "全部"]);
const STAR_SVG = `<svg class="star-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.95 5.98 6.6.96-4.78 4.66 1.13 6.58L12 17.6l-5.9 3.1 1.13-6.58L2.45 9.44l6.6-.96L12 2.5z"/></svg>`;
// 次要（降频）铃铛图标：线性风格，与 TRASH_ICON 一致（stroke=currentColor）
const BELL_ICON = `<svg class="bell-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>`;
const BELL_OFF_ICON = `<svg class="bell-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8.7 3A6 6 0 0 1 18 8a21.3 21.3 0 0 0 .6 5"/><path d="M17 17H3s3-2 3-9a4.67 4.67 0 0 1 .3-1.7"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/><path d="m2 2 20 20"/></svg>`;
// 显示/隐藏（筛选器语义）眼睛图标：线性风格，与 BELL_ICON 一致（stroke=currentColor）
const EYE_ICON = `<svg class="eye-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>`;
const EYE_OFF_ICON = `<svg class="eye-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><path d="m3 3 18 18"/></svg>`;
const TRASH_ICON = `<svg class="trash-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>`;
// 筛选漏斗图标：线性风格，与 EYE/BELL 一致（stroke=currentColor），补齐三键图标的视觉平衡
const FILTER_ICON = `<svg class="funnel-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>`;
const V_ICON = `<svg class="nav-v-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 4.5L12 19.5L19.5 4.5"/></svg>`;
const BOOK_ICON = `<svg class="nav-book-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`;
// 导航线性图标集（lucide 风格，stroke=currentColor，与 STAR/BELL/EYE 同一词汇）
const LIST_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/></svg>`;
const WSCN_LIVE_ICON = `<svg class="pt-icon" viewBox="180 240 640 620" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><path fill="currentColor" d="m466.944 649.6 41.152-102.464 18.4 49.472L432.192 828.8H416.32L246.08 423.136c-11.808-26.208-34.656-46.368-62.72-54.336l-1.6-.448V367.2h216.992v.608l-.192.096c-17.664 11.84-24.48 25.696-24.48 45.056 0 5.664 2.784 14.08 2.784 14.08l90.08 222.56zm239.648-345.92h135.264v.832l-.864.128c-16.96 3.136-32.576 18.848-43.104 44.576l-1.632 4.16-161.28 424.96h-14.4L548.192 597.76l67.488-151.104 55.2 140.544L752 370.176l.032-.032c11.68-31.616-11.424-65.28-45.12-65.728h-.32v-.736zm-21.44-68.576c-1.152 2.304-5.568 12.8-5.568 12.8L538.432 573.44 433.056 310.944c-6.4-18.4-25.184-51.84-64.64-62.816v-.768h248.48v1.216h-.448c-6.784 0-53.856 1.504-53.856 51.296 0 7.168 4.512 24.096 6.304 29.248l18.304 46.24 54.336-132.544c3.936-9.984 2.048-16.256 1.472-18.496-4.416-10.88-17.312-23.68-35.648-26.56v-.448h115.904v.576c-19.584 4.192-29.632 18.944-38.144 37.184"/></svg>`;
const NEWS_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M6 8h9M6 12h12M6 16h8"/><path d="M17 8h1"/></svg>`;
const GRID_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>`;
const GEAR_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
const DASHBOARD_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>`;
const FOLDER_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
const USER_PLUS_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/></svg>`;
const FILE_TEXT_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8M16 17H8"/></svg>`;
const SEND_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4z"/></svg>`;
const HISTORY_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/></svg>`;
const DATABASE_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/><path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/></svg>`;
const USERS_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;
const KEY_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>`;
const PLUS_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>`;
const X_ICON = `<svg class="x-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>`;
const ARROW_UP_ICON = `<svg class="tl-badge-arrow" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 3.59l7.457 7.45-1.414 1.42L13 7.41V21h-2V7.41l-5.043 5.05-1.414-1.42L12 3.59z"/></svg>`;
const REFRESH_ICON = `<svg class="refresh-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 5v4h4"/><path d="M4 13a8.1 8.1 0 0 0 15.5 2M20 19v-4h-4"/></svg>`;
const EXTERNAL_LINK_ICON = `<svg class="external-link-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
const SEARCH_ICON = `<svg class="search-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;
const FEISHU_DATE_ICON = `<svg class="feishu-date-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M8 3v4M16 3v4M3 11h18"/></svg>`;
const GITHUB_ICON = `<svg class="sidebar-gh-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.55 0-.27-.01-1.17-.02-2.12-3.2.7-3.87-1.36-3.87-1.36-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.75 2.69 1.25 3.35.95.1-.74.4-1.25.72-1.54-2.55-.29-5.23-1.28-5.23-5.68 0-1.26.45-2.28 1.18-3.09-.12-.29-.51-1.46.11-3.05 0 0 .96-.31 3.15 1.18a10.9 10.9 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.76.11 3.05.73.81 1.18 1.83 1.18 3.09 0 4.41-2.69 5.38-5.25 5.67.41.35.77 1.05.77 2.12 0 1.53-.01 2.76-.01 3.14 0 .3.2.66.8.55A11.51 11.51 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z"/></svg>`;
// 主题切换图标：线性风格，与 TRASH_ICON 一致（stroke=currentColor）
const THEME_SUN_ICON = `<svg class="theme-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>`;
const THEME_MOON_ICON = `<svg class="theme-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
const THEME_AUTO_ICON = `<svg class="theme-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>`;
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

const KS_TAB_KEY = "ks-tab";

// ponytail: tablist 方向键导航（roving tabindex），左右/上下/Home/End
function onKnowledgeTabsKey(event) {
  const current = event.target?.closest?.(".ks-tab");
  if (!current) return;
  const tabs = [...document.querySelectorAll(".ks-tab")];
  const i = tabs.indexOf(current);
  if (i < 0) return;
  let next = -1;
  if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (i + 1) % tabs.length;
  else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (i - 1 + tabs.length) % tabs.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = tabs.length - 1;
  else return;
  event.preventDefault();
  tabs[next].focus();
  switchKnowledgeSettingsTab(tabs[next].dataset.tab);
}

// ponytail: 刷新/关闭前只拦采集草稿（其他均为即时生效）；页签切换由 switchKnowledgeSettingsTab 守卫
window.addEventListener("beforeunload", (event) => {
  if (!imaCollectorHasUnsaved || !imaCollectorHasUnsaved()) return;
  event.preventDefault();
});
let imaCollectorPureCache = {
  uid: "",
  knowledge_base_id: "",
  root_folder_id: "",
  interval_seconds: 3600,
};
let imaProgressTimer = null;
let imaProgressPollSeq = 0;


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

function clearImaPdfUrl() {
  if (_imaPdfAbort) {
    _imaPdfAbort.abort();
    _imaPdfAbort = null;
  }
  const frame = $("#ima-pdf-frame");
  if (frame) frame.removeAttribute("src");
  const pdfUrl = window._imaPdfUrl;
  window._imaPdfUrl = "";
  if (pdfUrl) URL.revokeObjectURL(pdfUrl);
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

function _imaDocumentRoute(mediaId) {
  return `knowledge/${encodeURIComponent(mediaId).replace(/'/g, "%27")}`;
}

function imaDocumentReaderRoute(mediaId, groupId = "") {
  const listGroup = routeQuery().get("group") || state.imaDocumentsGroup || "";
  const listRoute = normalizeRoute(imaDocumentsRoute(
    listGroup,
    state.imaDocumentsQuery,
    state.imaDocumentsDay,
    state.imaDocumentsTag
  ));
  const params = new URLSearchParams(listRoute.split("?")[1] || "");
  if (groupId) params.set("doc_group", groupId);
  const query = params.toString();
  return `${_imaDocumentRoute(mediaId)}${query ? `?${query}` : ""}`;
}

function imaReaderDocumentGroup() {
  return routeQuery().get("doc_group")
    || routeQuery().get("group")
    || state.imaDocumentsGroup
    || "";
}

function openImaDocument(mediaId, groupId = "", replace = false) {
  const id = String(mediaId || "");
  if (!id) return;
  const listWasOpen = !!$("#ima-report-page");
  if (listWasOpen) captureImaListSnapshot(id, groupId);
  const url = normalizeRoute(imaDocumentReaderRoute(id, groupId));
  if (location.pathname + location.search !== url) {
    if (replace) history.replaceState(null, "", url);
    else history.pushState(null, "", url);
  }
  mountKnowledgeReaderShell();
  const seq = ++routeRenderSeq;
  renderImaDocument(seq, id);
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

function avatarHtml(name, url) {
  if (url) return `<img class="kol-avatar" src="${escapeHtml(url)}" alt="" loading="lazy">`;
  return `<div class="kol-avatar">${escapeHtml(avatarText(name))}</div>`;
}

// ---------- 壳 ----------
const NAV = [
  { group: "订阅", items: [
    { route: "timeline", icon: LIST_ICON, label: "最新动态" },
    { route: "news", icon: NEWS_ICON, label: "财经新闻" },
    { route: "knowledge", icon: BOOK_ICON, label: "研报库" },
    { route: "home", icon: GRID_ICON, label: "订阅广场" },
    { route: "settings", icon: GEAR_ICON, label: "设置" },
  ]},
  { group: "", admin: true, subs: [
    { label: "内容管理", items: [
      { route: "admin/dashboard", icon: DASHBOARD_ICON, label: "全景概览" },
      { route: "admin/kols", icon: V_ICON, label: "大V管理" },
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

function knowledgeMediaIdFromPath() {
  const [page, raw] = String(routePath() || "").split("/");
  if (page !== "knowledge" && page !== "ima-documents") return "";
  if (!raw) return "";
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function knowledgeTypingTarget(el) {
  const tag = (el && el.tagName) || "";
  return /^(INPUT|TEXTAREA|SELECT)$/.test(tag) || !!(el && el.isContentEditable);
}

function onKnowledgeListKey(e) {
  if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
  if (!isRoute("knowledge") && !isRoute("ima-documents")) return;
  if (e.key === "Escape" && (_imaDayPicker.open || _imaTagMenu.open)) {
    e.preventDefault();
    closeImaDayPicker();
    closeImaTagMenu();
    return;
  }
  if (_imaDayPicker.open || _imaTagMenu.open) return;
  if (knowledgeTypingTarget(e.target)) return;
  if (e.key !== "j" && e.key !== "k") return;
  const rows = [...document.querySelectorAll("#kb-list .ima-doc-row")];
  if (rows.length) {
    const current = knowledgeMediaIdFromPath();
    let idx = rows.findIndex((row) => row.dataset.mediaId === current);
    if (e.key === "j") idx = idx < 0 ? 0 : idx + 1;
    else idx = idx < 0 ? rows.length - 1 : idx - 1;
    if (idx < 0 || idx >= rows.length) return;
    e.preventDefault();
    rows[idx].focus();
    return;
  }
  const snapshot = _imaListSnapshot;
  if (!snapshot || snapshot.items.length < 2) return;
  const idx = snapshot.items.findIndex((item) => String(item.media_id) === knowledgeMediaIdFromPath());
  if (idx < 0) return;
  const next = snapshot.items[idx + (e.key === "j" ? 1 : -1)];
  if (!next) return;
  e.preventDefault();
  openImaDocument(next.media_id, next.group_id || "", true);
}

function ensureKnowledgeKeys() {
  if (window._kbKeysBound) return;
  window._kbKeysBound = true;
  document.addEventListener("keydown", onKnowledgeListKey);
  document.addEventListener("pointerdown", onImaDayPickerDocDown);
}

function mountKnowledgeListShell() {
  ensureKnowledgeKeys();
  if ($("#ima-report-page") && $("#kb-list")) return;
  clearImaPdfUrl();
  $("#main").innerHTML = `
    <section class="section-panel ima-report-page" id="ima-report-page">
      <div id="kb-list" tabindex="-1"><div class="admin-skeleton" aria-hidden="true"></div></div>
    </section>`;
}

function mountKnowledgeReaderShell() {
  ensureKnowledgeKeys();
  if ($("#ima-reader-page")) return;
  $("#main").innerHTML = `
    <section class="section-panel ima-reader-page" id="ima-reader-page">
      <div id="kb-reader"><div class="admin-skeleton" aria-hidden="true"></div></div>
    </section>`;
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
    <div class="sidebar-foot-links">
      <a id="sidebar-gh-link" class="sidebar-gh-link" href="https://github.com/icekale/vpush" target="_blank" rel="noopener" title="GitHub 项目">${GITHUB_ICON}</a>
      <span class="sidebar-user-meta" id="sidebar-version">v${APP_VERSION}</span>
    </div>
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

const _imaItems = [];
let _imaListSnapshot = null;
let _imaStreamSnapshot = null;
let _imaListSeq = 0;
let _imaReaderSeq = 0;
let _imaPdfAbort = null;
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
let _imaLoadingMore = false;
let _imaSearchTimer = null;
let _imaDocsLoadObserver = null;
let _imaDocsLoadFallback = null;
let _imaSearchComposing = false;
let _imaTagCounts = {};
let _imaDocumentCount = 0;
const IMA_TAG_COMMON_RATIO = 0.5;
const IMA_ABSTRACT_CLAMP_CHARS = 120;

function imaCountText(n) {
  return (Number(n) || 0).toLocaleString("zh-CN");
}

function imaResolvedCount(filtered, documentCount, itemCount, hasMore) {
  const loaded = Number(itemCount) || 0;
  const reported = Number(documentCount) || 0;
  // 读模型 document_count 是过滤后总数；JSON 回退路径仍可能给整库总量。
  // 已经一页装下、且上报数大于已加载数时，信已加载条数。
  if (filtered && !hasMore && loaded > 0 && reported > loaded) return loaded;
  return reported || loaded;
}

function imaDocumentsCountLabel(filtered, documentCount, itemCount, hasMore) {
  const total = imaResolvedCount(filtered, documentCount, itemCount, hasMore);
  return filtered ? `${imaCountText(total)} 条结果` : `${imaCountText(total)} 份`;
}

function imaSnapshotIsFiltered(snapshot) {
  const route = String((snapshot && snapshot.route) || "");
  return /[?&]q=/.test(route) || /[?&]tag=/.test(route);
}

function toggleImaAbstract(btn) {
  const box = btn && btn.closest(".ima-reader-abstract");
  if (!box) return;
  const expanded = box.classList.toggle("is-expanded");
  btn.textContent = expanded ? "收起" : "展开";
  btn.setAttribute("aria-expanded", expanded ? "true" : "false");
}

function copyImaAbstract() {
  const text = $("#ima-reader-abstract")?.textContent?.trim() || "";
  if (!text) return;
  const doFlash = () => flash("已复制研报摘要");
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(doFlash).catch(() => copyImaAbstractFallback(text, doFlash));
  } else {
    copyImaAbstractFallback(text, doFlash);
  }
}

function copyImaAbstractFallback(text, onSuccess) {
  const ta = document.createElement("textarea");
  try {
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    ta.setAttribute("readonly", "");
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    if (!ok) throw new Error("execCommand copy returned false");
    if (onSuccess) onSuccess();
  } catch (err) {
    flash("复制失败，请手动选择复制", "error");
  } finally {
    if (ta.parentNode) ta.remove();
  }
}

function fmtImaDay(day) {
  const raw = String(day || "").trim();
  let match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (match) {
    const year = Number(match[1]);
    const base = `${Number(match[2])}月${Number(match[3])}日`;
    return year === new Date().getFullYear() ? base : `${year}年${base}`;
  }
  match = /^(\d{2})(\d{2})$/.exec(raw);
  if (!match) return raw === "unknown" ? "未知日期" : raw;
  return `${Number(match[1])}月${Number(match[2])}日`;
}

function fmtImaDayShort(day) {
  const raw = String(day || "").trim();
  let match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (match) {
    const year = Number(match[1]);
    const base = `${Number(match[2])}/${Number(match[3])}`;
    return year === new Date().getFullYear() ? base : `${String(year).slice(2)}/${base}`;
  }
  match = /^(\d{2})(\d{2})$/.exec(raw);
  if (!match) return "";
  return `${Number(match[1])}/${Number(match[2])}`;
}

function imaDisplayTitle(name) {
  let s = String(name || "").replace(/\.pdf$/i, "").replace(/-副本$/u, "").trim();
  let lastCjk = -1;
  for (let i = 0; i < s.length; i += 1) {
    if (/[\u4e00-\u9fff]/.test(s[i])) lastCjk = i;
  }
  if (lastCjk >= 0) {
    const rest = s.slice(lastCjk + 1);
    const cut = rest.search(/\s+[A-Za-z]/);
    if (cut >= 0) s = s.slice(0, lastCjk + 1 + cut).trim();
  }
  return s;
}

function imaDocTicker(name) {
  const m = String(name || "").match(/[（(]([A-Z0-9][A-Z0-9.\-]*)[）)]/);
  return m ? m[1] : "";
}

function imaListTitle(name) {
  let s = imaDisplayTitle(name).replace(/[（(][A-Z0-9][A-Z0-9.\-]*[）)]/g, "");
  s = s.replace(/^[^\-–—]{1,8}[-–—]/, "");
  return s.replace(/\s+/g, " ").trim() || imaDisplayTitle(name);
}

function fmtDocSize(bytes) {
  const n = Number(bytes) || 0;
  return n > 0 ? fmtCacheBytes(n) : "";
}

function imaDocKindLabel(item) {
  if (item?.has_pdf) return "PDF";
  if (item?.has_txt) return "全文";
  return "仅摘要";
}

function imaDocumentTagsHtml(tags, interactive = false) {
  const list = Array.isArray(tags) ? tags.filter(Boolean) : [];
  if (!list.length) return "";
  const chips = list.map((tag) => {
    const label = escapeHtml(tag);
    return interactive
      ? `<button type="button" class="ima-doc-tag is-action" data-tag="${label}" onclick="event.stopPropagation();selectImaDocumentsTag(this.dataset.tag)">${label}</button>`
      : `<span class="ima-doc-tag">${label}</span>`;
  });
  return `<span class="ima-doc-tags">${chips.join("")}</span>`;
}

function isReportWatchableTag(tag) {
  const name = String(tag || "").trim();
  return !!name && !REPORT_WATCH_BLOCKED_TAGS.has(name);
}

function userKeywordSet() {
  return new Set((state.user?.keywords || []).map((k) => String(k || "").trim()).filter(Boolean));
}

function imaWatchTagButton(tag) {
  const name = String(tag || "").trim();
  if (!name) return "";
  const watching = userKeywordSet().has(name);
  const pressed = watching ? "true" : "false";
  const selected = watching ? " is-selected" : "";
  const title = watching ? "已在关键词提醒中" : "加入关键词提醒";
  return `<button type="button" class="ima-doc-tag is-action is-watch${selected}" data-tag="${escapeHtml(name)}" aria-pressed="${pressed}" title="${title}" onclick="event.stopPropagation();toggleReportKeyword(this.dataset.tag)">${escapeHtml(name)}</button>`;
}

function imaReaderWatchHtml(tags) {
  const list = (Array.isArray(tags) ? tags : []).map((tag) => String(tag || "").trim()).filter(Boolean);
  if (!list.length) return "";
  const chips = list.map((tag) => (
    isReportWatchableTag(tag)
      ? imaWatchTagButton(tag)
      : `<span class="ima-doc-tag">${escapeHtml(tag)}</span>`
  ));
  return `<div class="ima-reader-watch" aria-label="研报标签">${chips.join("")}</div>`;
}

function imaTagCountsFromData(data) {
  const raw = data && data.tag_counts;
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const counts = {};
    for (const [tag, n] of Object.entries(raw)) {
      const name = String(tag || "").trim();
      const count = Number(n) || 0;
      if (name && count) counts[name] = count;
    }
    if (Object.keys(counts).length) return counts;
  }
  const counts = {};
  for (const item of data?.items || []) {
    for (const tag of Array.isArray(item.tags) ? item.tags : []) {
      const name = String(tag || "").trim();
      if (name) counts[name] = (counts[name] || 0) + 1;
    }
  }
  return counts;
}

function imaTagCoverageBase(counts = _imaTagCounts, documentCount = _imaDocumentCount) {
  const n = Number(documentCount) || 0;
  if (n > 0) return n;
  const values = Object.values(counts || {}).map((item) => Number(item) || 0);
  return values.length ? Math.max(...values) : 0;
}

function imaDistinctiveTags(tags, counts = _imaTagCounts, documentCount = _imaDocumentCount) {
  const list = (Array.isArray(tags) ? tags : []).map((tag) => String(tag || "").trim()).filter(Boolean);
  if (!list.length) return [];
  const freq = counts && typeof counts === "object" ? counts : {};
  const total = imaTagCoverageBase(freq, documentCount);
  const ranked = list
    .map((tag) => ({ tag, n: Number(freq[tag]) || 0 }))
    .sort((a, b) => a.n - b.n || a.tag.localeCompare(b.tag, "zh"));
  const rare = total
    ? ranked.filter((item) => item.n > 0 && item.n / total <= IMA_TAG_COMMON_RATIO)
    : ranked;
  return rare.slice(0, 2).map((item) => item.tag);
}

function imaReportMetaHtml(item) {
  const parts = [];
  const ticker = imaDocTicker(item.name);
  if (ticker) parts.push(`<span>${escapeHtml(ticker)}</span>`);
  for (const tag of imaDistinctiveTags(item?.tags)) {
    parts.push(isReportWatchableTag(tag) ? imaWatchTagButton(tag) : `<span>${escapeHtml(tag)}</span>`);
  }
  const size = fmtDocSize(item?.size);
  if (size) parts.push(`<span>${escapeHtml(size)}</span>`);
  return parts.length
    ? `<span class="ima-report-meta">${parts.join("")}</span>`
    : "";
}

function imaDocumentRow(item) {
  const day = fmtImaDayShort(item.sort_date || item.day) || "—";
  const source = String(item.group_name || "");
  const meta = imaReportMetaHtml(item); // .ima-report-meta
  const snippet = item.search_snippet ? `<span class="ima-report-snippet">${escapeHtml(item.search_snippet)}</span>` : (item.abstract ? `<span class="ima-report-snippet">${escapeHtml(item.abstract)}</span>` : "");
  return `
    <article class="ima-doc-row" role="button" tabindex="0" data-media-id="${escapeHtml(item.media_id)}" data-group-id="${escapeHtml(item.group_id || "")}" onclick="openImaDocument(this.dataset.mediaId, this.dataset.groupId)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openImaDocument(this.dataset.mediaId, this.dataset.groupId)}">
      <time class="ima-report-date">${escapeHtml(day)}</time>
      <span class="ima-report-copy"><strong class="ima-report-title">${escapeHtml(imaListTitle(item.name))}</strong>${snippet}${meta}</span>
      <span class="ima-report-source">${escapeHtml(source)}</span>
    </article>`;
}

function imaReportSkeletonHtml() {
  return Array.from({ length: 6 }, () => `
    <div class="ima-report-skeleton-row" aria-hidden="true">
      <span class="ima-report-date"></span>
      <span class="ima-report-copy"></span>
      <span class="ima-report-source"></span>
    </div>`).join("");
}

function imaDocumentsEmptyHtml(hasFilter) {
  if (hasFilter) {
    return emptyState(
      "没有找到相关研报",
      `<div><p class="section-meta">换个公司、代码或主题试试</p><button type="button" class="btn-normal" onclick="clearImaDocumentsFilters()">清除筛选</button></div>`
    );
  }
  return emptyState("这里还没有研报");
}

function imaDocumentGroups(items, showGroupLabel = false) {
  const groups = new Map();
  for (const item of items || []) {
    const key = item.sort_date || item.day;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  return [...groups.entries()].map(([day, rows]) => `
    <section class="ima-doc-day">
      <header class="ima-doc-day-head"><h2>${escapeHtml(fmtImaDay(day) || day)}</h2><span>${rows.length} 份</span></header>
      <div class="ima-doc-list">${rows.map((item) => imaDocumentRow(item)).join("")}</div>
    </section>`).join("");
}

function imaDocumentsGroupFromRoute() {
  return routeQuery().get("group") || "";
}

function imaDocumentsRequestPath() {
  const params = new URLSearchParams();
  const query = imaUsableSearchQuery(routeQuery().get("q") || "");
  const day = routeQuery().get("day") || "";
  const tag = routeQuery().get("tag") || "";
  const group = imaDocumentsGroupFromRoute() || "";
  if (query) params.set("q", query);
  if (tag) params.set("tag", tag);
  if (group) params.set("group", group);
  if (query || tag || !day) {
    params.set("limit", "50");
    params.set("offset", "0");
  } else {
    params.set("day", day);
  }
  return `/api/ima-documents?${params.toString()}`;
}

function imaDocumentsRoute(group, query, day, tag) {
  const params = new URLSearchParams();
  if (group) params.set("group", group);
  if (query) params.set("q", query);
  if (day) params.set("day", day);
  const selectedTag = tag === undefined ? (state.imaDocumentsTag || "") : tag;
  if (selectedTag) params.set("tag", selectedTag);
  const routeQueryString = params.toString();
  return `knowledge${routeQueryString ? `?${routeQueryString}` : ""}`;
}

function imaDocumentKey(mediaId, groupId = "") {
  return `${String(groupId || "")}\u0000${String(mediaId || "")}`;
}

function cloneImaListSnapshotFields() {
  const body = $("#ima-docs-body");
  if (!body) return null;
  return {
    items: _imaItems.map((item) => ({ ...item, tags: [...(item.tags || [])] })),
    hasMore: !!state.imaDocumentsHasMore,
    days: [...(state.imaDocumentsDays || [])],
    tagCounts: { ..._imaTagCounts },
    documentCount: _imaDocumentCount,
    scrollTop: body.scrollTop,
    selectedKey: "",
    consumed: false,
  };
}

function captureImaListSnapshot(selectedMediaId = "", selectedGroupId = "") {
  const fields = cloneImaListSnapshotFields();
  if (!fields) return;
  _imaListSnapshot = {
    ...fields,
    route: location.pathname + location.search,
    selectedKey: imaDocumentKey(selectedMediaId, selectedGroupId),
  };
}

function stashImaStreamSnapshot() {
  if (routeQuery().get("q") || routeQuery().get("tag") || routeQuery().get("day")) return;
  const fields = cloneImaListSnapshotFields();
  if (!fields || !fields.items.length) return;
  _imaStreamSnapshot = fields;
}

function adoptImaStreamSnapshot() {
  if (!_imaStreamSnapshot || currentImaListSnapshot()) return;
  if (imaUsableSearchQuery(routeQuery().get("q") || "") || routeQuery().get("tag") || routeQuery().get("day")) return;
  _imaListSnapshot = {
    ..._imaStreamSnapshot,
    items: _imaStreamSnapshot.items.map((item) => ({ ...item, tags: [...(item.tags || [])] })),
    days: [..._imaStreamSnapshot.days],
    tagCounts: { ..._imaStreamSnapshot.tagCounts },
    route: location.pathname + location.search,
    consumed: false,
  };
}

function currentImaListSnapshot() {
  const snapshot = _imaListSnapshot;
  return snapshot && !snapshot.consumed && snapshot.route === location.pathname + location.search
    ? snapshot
    : null;
}

function restoreImaListSnapshot(snapshot, body) {
  if (!snapshot || !body) return false;
  _imaItems.length = 0;
  _imaItems.push(...snapshot.items.map((item) => ({ ...item, tags: [...(item.tags || [])] })));
  state.imaDocumentsHasMore = snapshot.hasMore;
  state.imaDocumentsDays = [...snapshot.days];
  _imaTagCounts = { ...snapshot.tagCounts };
  _imaDocumentCount = snapshot.documentCount;
  const more = snapshot.hasMore
    ? `<div id="ima-docs-more" class="ima-docs-more" role="status" aria-live="polite">下滑加载更多</div>`
    : "";
  body.innerHTML = `<div class="ima-doc-list">${snapshot.items.map((item) => imaDocumentRow(item)).join("")}</div>${more}`;
  startImaDocumentsAutoLoad();
  requestAnimationFrame(() => {
    body.scrollTop = snapshot.scrollTop;
    const row = [...body.querySelectorAll(".ima-doc-row")].find((item) => imaDocumentKey(item.dataset.mediaId, item.dataset.groupId) === snapshot.selectedKey);
    if (row) {
      row.classList.add("is-selected");
      row.setAttribute("aria-current", "true");
    }
    if (snapshot.focusSearch) {
      snapshot.focusSearch = false;
      $("#ima-doc-q")?.focus();
    }
  });
  snapshot.consumed = true;
  return true;
}

function replaceImaDocumentsRoute(path) {
  const url = normalizeRoute(path);
  if (location.pathname + location.search !== url) history.replaceState(null, "", url);
}

async function selectImaDocumentGroup(value) {
  const groupId = String(value || "");
  state.imaDocumentsGroup = groupId;
  state.imaDocumentsDay = "";
  state.imaDocumentsDays = [];
  state.imaDocumentsTag = "";
  state.imaDocumentsQuery = $("#ima-doc-q")?.value?.trim() || state.imaDocumentsQuery || "";
  replaceImaDocumentsRoute(imaDocumentsRoute(groupId, state.imaDocumentsQuery, "", ""));
  const seq = ++routeRenderSeq;
  // 飞书来源一库一文：选中即直接进时间线，省一次点击；带搜索词时仍回列表
  if (groupId.startsWith("feishu-") && !imaUsableSearchQuery(state.imaDocumentsQuery)) {
    renderImaDocuments(seq);
    try {
      const data = await api(`/api/ima-documents?group=${encodeURIComponent(groupId)}&limit=1`);
      if (!routeStillActive(seq)) return;
      const item = (data.items || [])[0];
      if (item) {
        openImaDocument(item.media_id, groupId, true);
        return;
      }
    } catch { /* 取不到就停留在列表 */ }
    return;
  }
  renderImaDocuments(seq);
}

function imaUsableSearchQuery(raw) {
  const query = String(raw || "").trim();
  if (!query) return "";
  if (query.length < 2 && /^[\x00-\x7F]*$/.test(query)) return "";
  return query;
}

function queueImaDocumentsSearch() {
  if (_imaSearchComposing) return;
  clearTimeout(_imaSearchTimer);
  _imaSearchTimer = setTimeout(() => submitImaDocumentsSearch(), 250);
}

function submitImaDocumentsSearch() {
  clearTimeout(_imaSearchTimer);
  _imaSearchTimer = null;
  if (!$("#ima-report-page") || !$("#ima-doc-q")) {
    _imaSearchComposing = false;
    return;
  }
  const nextQuery = imaUsableSearchQuery($("#ima-doc-q")?.value || "");
  if (nextQuery && !routeQuery().get("q") && !routeQuery().get("tag")) stashImaStreamSnapshot();
  state.imaDocumentsQuery = nextQuery;
  state.imaDocumentsDay = "";
  replaceImaDocumentsRoute(imaDocumentsRoute(state.imaDocumentsGroup, state.imaDocumentsQuery, state.imaDocumentsDay, state.imaDocumentsTag));
  const seq = ++routeRenderSeq;
  renderImaDocuments(seq);
}

function selectImaDocumentsDay(value) {
  const day = String(value || "");
  state.imaDocumentsQuery = "";
  state.imaDocumentsTag = "";
  state.imaDocumentsDay = day;
  const input = $("#ima-doc-q");
  if (input) input.value = "";
  replaceImaDocumentsRoute(imaDocumentsRoute(state.imaDocumentsGroup, "", state.imaDocumentsDay, ""));
  const seq = ++routeRenderSeq;
  renderImaDocuments(seq);
}

function selectImaDocumentsTag(value) {
  state.imaDocumentsTag = String(value || "");
  state.imaDocumentsDay = "";
  replaceImaDocumentsRoute(imaDocumentsRoute(state.imaDocumentsGroup, state.imaDocumentsQuery, state.imaDocumentsDay, state.imaDocumentsTag));
  const seq = ++routeRenderSeq;
  renderImaDocuments(seq);
}

let _imaDayPicker = { open: false };

function imaDayMenuDays(days) {
  return (Array.isArray(days) ? days : []).filter((day) => /^\d{4}$/.test(day));
}

function imaDayMenuHtml(day, days) {
  const current = String(day || "");
  const items = [`<button type="button" role="option" class="kb-desk-day-option${current ? "" : " is-selected"}" aria-selected="${!current}" onclick="pickImaDay('')">最新</button>`];
  for (const key of imaDayMenuDays(days)) {
    const on = key === current;
    items.push(`<button type="button" role="option" class="kb-desk-day-option${on ? " is-selected" : ""}" aria-selected="${on}" onclick="pickImaDay('${escapeHtml(key)}')">${escapeHtml(fmtImaDay(key))}</button>`);
  }
  return `<div class="kb-desk-day-menu" role="listbox" aria-label="日期">${items.join("")}</div>`;
}

function placeImaDayMenu(menu, trigger) {
  const box = trigger.getBoundingClientRect();
  const list = $("#kb-list")?.getBoundingClientRect();
  const width = Math.max(140, box.width);
  const minL = list ? list.left + 8 : 8;
  const maxL = (list ? list.right : window.innerWidth) - width - 8;
  const left = Math.min(Math.max(minL, box.right - width), Math.max(minL, maxL));
  menu.style.position = "fixed";
  menu.style.left = `${left}px`;
  menu.style.top = `${box.bottom + 4}px`;
  menu.style.minWidth = `${width}px`;
}

function closeImaDayPicker() {
  _imaDayPicker.open = false;
  document.querySelectorAll(".kb-desk-day-menu").forEach((el) => el.remove());
  const trigger = $("#ima-doc-day");
  if (trigger) trigger.setAttribute("aria-expanded", "false");
}

function renderImaDayMenu() {
  const trigger = $("#ima-doc-day");
  const host = trigger?.closest(".ima-report-searchbox") || trigger?.closest(".kb-desk-search") || trigger?.parentElement;
  if (!trigger || !host) return;
  host.querySelector(".kb-desk-day-menu")?.remove();
  host.insertAdjacentHTML("beforeend", imaDayMenuHtml(state.imaDocumentsDay || "", state.imaDocumentsDays));
  const menu = host.querySelector(".kb-desk-day-menu");
  if (menu) placeImaDayMenu(menu, trigger);
  trigger.setAttribute("aria-expanded", "true");
}

function toggleImaDayPicker(event) {
  event?.stopPropagation();
  if (_imaDayPicker.open) {
    closeImaDayPicker();
    return;
  }
  _imaDayPicker.open = true;
  renderImaDayMenu();
}

function pickImaDay(value) {
  closeImaDayPicker();
  selectImaDocumentsDay(value);
}

let _imaTagMenu = { open: false, keys: [] };

function closeImaTagMenu() {
  _imaTagMenu.open = false;
  document.querySelectorAll(".kb-desk-day-menu[data-tag-menu]").forEach((el) => el.remove());
  $("#ima-doc-tag")?.setAttribute("aria-expanded", "false");
}

// 标签名是任意字符串，不内联进 onclick（防注入），菜单存 keys，点选传下标
function imaTagMenuHtml(current) {
  const counts = _imaTagCounts || {};
  const keys = Object.keys(counts).sort((a, b) => (counts[b] || 0) - (counts[a] || 0));
  if (current && !keys.includes(current)) keys.unshift(current);
  _imaTagMenu.keys = keys;
  const items = [`<button type="button" role="option" class="kb-desk-day-option${current ? "" : " is-selected"}" aria-selected="${!current}" onclick="pickImaTag(-1)">全部</button>`];
  keys.forEach((key, i) => {
    const on = key === current;
    items.push(`<button type="button" role="option" class="kb-desk-day-option${on ? " is-selected" : ""}" aria-selected="${on}" onclick="pickImaTag(${i})">${escapeHtml(key)}${counts[key] ? `（${counts[key]}）` : ""}</button>`);
  });
  return `<div class="kb-desk-day-menu" data-tag-menu role="listbox" aria-label="标签">${items.join("")}</div>`;
}

function toggleImaTagMenu(event) {
  event?.stopPropagation();
  if (_imaTagMenu.open) {
    closeImaTagMenu();
    return;
  }
  closeImaDayPicker();
  const trigger = $("#ima-doc-tag");
  const host = trigger?.closest(".ima-report-tag");
  if (!trigger || !host) return;
  _imaTagMenu.open = true;
  host.insertAdjacentHTML("beforeend", imaTagMenuHtml(String(state.imaDocumentsTag || "")));
  const menu = host.querySelector(".kb-desk-day-menu");
  if (menu) {
    menu.style.position = "fixed";
    const box = trigger.getBoundingClientRect();
    const width = Math.max(160, box.width);
    menu.style.left = `${Math.max(8, Math.min(box.left, window.innerWidth - width - 8))}px`;
    menu.style.top = `${box.bottom + 4}px`;
    menu.style.width = `${width}px`;
  }
  trigger.setAttribute("aria-expanded", "true");
}

function pickImaTag(i) {
  const key = i >= 0 ? (_imaTagMenu.keys?.[i] || "") : "";
  closeImaTagMenu();
  selectImaDocumentsTag(key);
}

function onImaDayPickerDocDown(event) {
  if (_imaTagMenu.open && !event.target?.closest?.(".ima-tag-trigger, .kb-desk-day-menu[data-tag-menu]")) closeImaTagMenu();
  if (!_imaDayPicker.open) return;
  if (event.target?.closest?.(".kb-desk-day, .kb-desk-day-menu")) return;
  closeImaDayPicker();
}

function imaDocumentsDayNavHtml(day, days) {
  const list = imaDayMenuDays(days);
  if (!list.length && !(Array.isArray(days) && days.length)) return "";
  const current = String(day || "");
  const label = current ? (fmtImaDay(current) || current) : "最新";
  return `<button type="button" class="kb-desk-day" id="ima-doc-day" aria-label="筛选日期" aria-haspopup="listbox" aria-expanded="false" onclick="toggleImaDayPicker(event)">${escapeHtml(label)}</button>`;
}

function refreshImaDocuments() {
  const seq = ++routeRenderSeq;
  renderImaDocuments(seq, { keepOld: true });
}

function imaReportRefreshErrorHtml(message) {
  return `<div class="ima-report-refresh-error" role="alert"><span>最新研报暂时无法更新：${escapeHtml(message)}</span><button type="button" class="btn-ghost" onclick="refreshImaDocuments()">重试</button></div>`;
}

function knowledgeCardSummary(group) {
  const count = Number(group.document_count || 0);
  const day = fmtImaDay(group.latest_sort_date || group.latest_day);
  return count ? `${count} 份${day ? ` · ${day}` : ""}` : "还没有文档";
}

function knowledgeLibRowHtml(group, selected, mode) {
  const id = String(group.id || "");
  const name = feishuSourceDisplay(group.name || id).label;
  const summary = knowledgeCardSummary(group);
  if (mode === "available") {
    return `<div class="kb-lib-row is-available">
      <div class="kb-lib-copy"><strong class="kb-lib-name">${escapeHtml(name)}</strong><span class="kb-lib-meta">${escapeHtml(summary)}</span></div>
      <button type="button" class="btn-normal" data-group="${escapeHtml(id)}" onclick="subscribeKnowledge(this.dataset.group, this)">订阅</button>
    </div>`;
  }
  const on = id === String(selected || "");
  const unsub = !state.user?.is_admin
    ? `<button type="button" class="btn-ghost kb-lib-unsub" data-group="${escapeHtml(id)}" data-name="${escapeHtml(name)}" onclick="event.stopPropagation();unsubscribeKnowledge(this.dataset.group, this)">退订</button>`
    : "";
  return `<div class="kb-lib-row${on ? " is-selected" : ""}${unsub ? " has-unsub" : ""}">
    <button type="button" class="kb-lib-open" role="option" aria-selected="${on}" data-group="${escapeHtml(id)}" onclick="selectImaDocumentGroup(this.dataset.group)"><strong class="kb-lib-name">${escapeHtml(name)}</strong><span class="kb-lib-meta">${escapeHtml(summary)}</span></button>
    ${unsub}
  </div>`;
}

function knowledgeSourceControlsHtml(selectedGroup = "") {
  const subscribed = state.imaCatalogSubscribed || [];
  const sources = subscribed.map((group) => ({
    group_id: String(group.id || ""),
    title: group.name || group.id,
  }));
  const pillsHtml = `<div class="kb-source-pills-desk">${feishuSourcePillsHtml(sources, selectedGroup, "knowledge")}</div>`;
  const mobileOptions = [
    `<option value="" ${!selectedGroup ? "selected" : ""}>研报库</option>`,
    ...sources.map((s) => `<option value="${escapeHtml(s.group_id)}" ${s.group_id === selectedGroup ? "selected" : ""}>${escapeHtml(s.title)}</option>`)
  ].join("");
  const mobileSelectHtml = `<div class="kb-source-select-wrap"><select class="kb-source-select-mobile" aria-label="切换研报库" onchange="selectImaDocumentGroup(this.value)">${mobileOptions}</select></div>`;
  return `<div class="ima-report-source">${pillsHtml}${mobileSelectHtml}</div>`;
}

function refreshKnowledge() {
  const seq = ++routeRenderSeq;
  renderKnowledge(seq);
}

async function subscribeKnowledge(groupId, btn) {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  if (btn) btn.disabled = true;
  try {
    await api(`/api/ima-documents/groups/${encodeURIComponent(groupId)}/subscribe`, { method: "POST" });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash("已订阅");
    replaceImaDocumentsRoute(imaDocumentsRoute(groupId, "", "", ""));
    refreshKnowledge();
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message || "订阅失败", "error");
    if (btn) btn.disabled = false;
  }
}

async function unsubscribeKnowledge(groupId, btn) {
  const name = btn?.dataset?.name || "这个研报库";
  if (!confirm(`退订后将无法打开「${name}」。确定退订？`)) return;
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  if (btn) btn.disabled = true;
  try {
    await api(`/api/ima-documents/groups/${encodeURIComponent(groupId)}/subscribe`, { method: "DELETE" });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash("已退订");
    replaceImaDocumentsRoute(imaDocumentsRoute("", "", "", ""));
    refreshKnowledge();
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message || "退订失败", "error");
    if (btn) btn.disabled = false;
  }
}

async function renderKnowledge(seq, encodedMediaId = "") {
  stopImaDocumentsAutoLoad();
  const mediaId = encodedMediaId ? decodeURIComponent(encodedMediaId) : "";
  setPageTitle("研报库");
  if (mediaId && !$("#ima-reader-page")) {
    $("#main").innerHTML = `<div class="admin-skeleton" aria-hidden="true"></div>`;
  }
  if (!mediaId) mountKnowledgeListShell();
  const catalogPromise = api("/api/ima-documents/catalog");
  const documentsPromise = mediaId || currentImaListSnapshot() ? null : api(imaDocumentsRequestPath());
  const documentsRenderTask = mediaId
    ? null
    : renderImaDocuments(seq, { prefetched: documentsPromise });
  try {
    const settled = await Promise.allSettled(
      documentsPromise ? [catalogPromise, documentsPromise] : [catalogPromise]
    );
    if (!routeStillActive(seq)) return;
    const catalogResult = settled[0];
    const documentsResult = documentsPromise ? settled[1] : null;
    const catalogOk = catalogResult.status === "fulfilled";
    const documentsOk = documentsResult?.status === "fulfilled";
    const snapshot = currentImaListSnapshot();
    if (!catalogOk && !documentsOk && !mediaId && !snapshot) {
      const message = catalogResult.reason?.message || documentsResult?.reason?.message || "请求失败";
      $("#main").innerHTML = emptyState(`加载失败：${message}`, `<div><button type="button" class="btn-normal" onclick="refreshKnowledge()">重试</button></div>`);
      return;
    }
    let subscribed = [];
    let available = [];
    let catalogWarning = "";
    if (catalogOk) {
      const data = catalogResult.value;
      subscribed = Array.isArray(data.subscribed) ? data.subscribed : [];
      available = Array.isArray(data.available) ? data.available : [];
    } else if (documentsOk) {
      const groups = Array.isArray(documentsResult.value.groups) ? documentsResult.value.groups : [];
      subscribed = groups.map((group) => ({ id: group.id, name: group.name, enabled: true }));
      catalogWarning = "研报库目录加载失败";
    } else {
      subscribed = Array.isArray(state.imaCatalogSubscribed) ? state.imaCatalogSubscribed : [];
      available = Array.isArray(state.imaCatalogAvailable) ? state.imaCatalogAvailable : [];
      catalogWarning = "研报库目录加载失败";
    }
    state.imaCatalogSubscribed = subscribed;
    state.imaCatalogAvailable = available;
    const isAdmin = !!state.user?.is_admin;
    const selectedGroup = imaDocumentsGroupFromRoute();
    const sourceControl = $("#kb-list .ima-report-source");
    if (sourceControl) {
      sourceControl.outerHTML = knowledgeSourceControlsHtml(selectedGroup);
    }
    if (catalogOk && selectedGroup && !isAdmin && !subscribed.some((group) => String(group.id) === selectedGroup)) {
      setPageTitle("研报库", true, "knowledge", "回研报库");
      $("#main").innerHTML = emptyState("没有访问权限", `<div><button type="button" class="btn-normal" onclick="go('knowledge')">回研报库</button></div>`);
      return;
    }
    state.imaDocumentsGroup = selectedGroup;
    if (mediaId) {
      mountKnowledgeReaderShell();
      await renderImaDocument(seq, mediaId);
      return;
    }
    if (!subscribed.length && catalogOk) {
      const list = $("#kb-list");
      const controls = `<div class="ima-report-head"><div class="ima-report-filters ima-report-filters-row">${knowledgeSourceControlsHtml("")}</div></div>`;
      if (isAdmin) {
        list.innerHTML = `${controls}${emptyState("还没有配置研报库", `<div><button type="button" class="btn-normal" onclick="go('admin/knowledge')">去配置采集</button></div>`)}`;
      } else {
        list.innerHTML = `${controls}${emptyState(
          "还没有可看的研报库",
          available.length
            ? `<div class="kb-lib-empty">${available.map((group) => knowledgeLibRowHtml(group, "", "available")).join("")}</div>`
            : `<div><p class="section-meta">找管理员在用户设置里勾选研报库后再来</p></div>`
        )}`;
      }
      if (catalogWarning) {
        list.insertAdjacentHTML("afterbegin", `<p class="section-meta ima-catalog-warning">${escapeHtml(catalogWarning)}</p>`);
      }
      return;
    }
    await documentsRenderTask;
    if (catalogWarning) {
      const warning = `<p class="section-meta ima-catalog-warning">${escapeHtml(catalogWarning)}</p>`;
      const head = $("#kb-list .ima-report-head");
      if (head) head.insertAdjacentHTML("afterend", warning);
      else $("#kb-list")?.insertAdjacentHTML("afterbegin", warning);
    }
  } catch (err) {
    if (routeStillActive(seq)) {
      $("#main").innerHTML = emptyState(`加载失败：${err.message}`, `<div><button type="button" class="btn-normal" onclick="refreshKnowledge()">重试</button></div>`);
    }
  }
}

async function renderImaDocuments(seq, { keepOld = false, prefetched = null } = {}) {
  stopImaDocumentsAutoLoad();
  if (!$("#ima-report-page")) {
    await renderKnowledge(seq);
    return;
  }
  const previousBody = $("#ima-docs-body");
  const oldHtml = keepOld ? previousBody?.innerHTML || "" : "";
  _imaListSeq += 1;
  _imaLoadingMore = false;
  if (!keepOld) {
    _imaItems.length = 0;
    state.imaDocumentsHasMore = false;
  }
  const selectedGroup = imaDocumentsGroupFromRoute() || state.imaDocumentsGroup || "";
  const query = imaUsableSearchQuery(routeQuery().get("q") || "");
  const day = routeQuery().get("day") || "";
  const tag = routeQuery().get("tag") || "";
  const searchMode = !!(query || tag);
  const streamMode = !day && !searchMode;
  const paged = searchMode || streamMode;
  state.imaDocumentsGroup = selectedGroup;
  state.imaDocumentsQuery = query;
  state.imaDocumentsDay = day;
  state.imaDocumentsTag = tag;
  if (!knowledgeMediaIdFromPath()) setPageTitle("研报库");
  const listRoot = $("#kb-list");
  if (!listRoot) {
    await renderKnowledge(seq);
    return;
  }
  const existingHead = listRoot.querySelector(".ima-report-head");
  if (existingHead) {
    const input = $("#ima-doc-q");
    if (input && document.activeElement !== input) input.value = query;
    const source = existingHead.querySelector(".ima-report-source");
    if (source) source.outerHTML = knowledgeSourceControlsHtml(selectedGroup);
    let clearBtn = existingHead.querySelector(".ima-search-clear");
    if (query) {
      if (!clearBtn) {
        const searchBox = existingHead.querySelector(".ima-report-searchbox");
        if (searchBox) {
          searchBox.insertAdjacentHTML("beforeend", `<button type="button" class="ima-search-clear" onclick="clearImaDocumentsFilter('q')" aria-label="清除搜索">${X_ICON}</button>`);
        }
      }
    } else if (clearBtn) {
      clearBtn.remove();
    }
    const body = $("#ima-docs-body");
    if (body && !keepOld) body.innerHTML = imaReportSkeletonHtml();
  } else {
    _imaSearchComposing = false;
    const sourceControls = knowledgeSourceControlsHtml(selectedGroup);
    const clearBtn = query
      ? `<button type="button" class="ima-search-clear" onclick="clearImaDocumentsFilter('q')" aria-label="清除搜索">${X_ICON}</button>`
      : "";
    listRoot.innerHTML = `
  <header class="ima-report-head">
    <div class="ima-report-heading"><div><h2 id="ima-doc-title">最新研报</h2><p id="ima-doc-meta" class="section-meta"></p></div><button type="button" class="icon-btn" aria-label="刷新研报" title="刷新研报" onclick="refreshImaDocuments()">${REFRESH_ICON}</button></div>
    <form class="ima-report-search" onsubmit="event.preventDefault();submitImaDocumentsSearch()">
      <label class="ima-report-searchbox">${SEARCH_ICON}<input id="ima-doc-q" type="search" value="${escapeHtml(query)}" placeholder="搜标题、公司、代码、行业或资料源" aria-label="搜索研报" oninput="queueImaDocumentsSearch()" oncompositionstart="_imaSearchComposing=true" oncompositionend="_imaSearchComposing=false;queueImaDocumentsSearch()">${clearBtn}</label>
    </form>
    <div class="ima-report-filters">${sourceControls}<span id="ima-doc-day-nav-slot"></span><div class="ima-report-tag"><span class="sr-only">标签</span><button type="button" class="kb-desk-day ima-tag-trigger" id="ima-doc-tag" aria-haspopup="listbox" aria-expanded="false" onclick="toggleImaTagMenu(event)" hidden>标签</button></div></div>
    <div id="ima-doc-filter-chips" class="ima-doc-filter-chips"></div>
    <div class="ima-report-columns" aria-hidden="true"><span>日期</span><span>标题</span><span>资料源</span></div>
  </header>
  <div id="ima-docs-body" class="ima-report-body">${keepOld && oldHtml ? oldHtml : imaReportSkeletonHtml()}</div>`;
  }
  const body = $("#ima-docs-body");
  adoptImaStreamSnapshot();
  const snapshot = currentImaListSnapshot();
  if (snapshot && body) {
    const tagTrigger = $("#ima-doc-tag");
    const uniqueTags = Object.keys(snapshot.tagCounts || {});
    if (tag && !uniqueTags.includes(tag)) uniqueTags.unshift(tag);
    if (tagTrigger) {
      tagTrigger.textContent = tag || "标签";
      if (uniqueTags.length || tag) tagTrigger.removeAttribute("hidden");
      else tagTrigger.hidden = true;
    }
    const navSlot = $("#ima-doc-day-nav-slot");
    if (navSlot) {
      closeImaDayPicker();
      navSlot.innerHTML = imaDocumentsDayNavHtml(searchMode ? "" : day, snapshot.days);
    }
    restoreImaListSnapshot(snapshot, body);
    const title = $("#ima-doc-title");
    const meta = $("#ima-doc-meta");
    if (title) title.textContent = "最新研报";
    if (meta) {
      meta.textContent = imaDocumentsCountLabel(
        !!(query || tag),
        snapshot.documentCount,
        snapshot.items.length,
        snapshot.hasMore,
      );
    }
    syncImaDocumentsFilterStatus();
    $("#ima-report-page")?.removeAttribute("aria-busy");
    return;
  }
  $("#ima-report-page")?.setAttribute("aria-busy", "true");
  try {
    const data = prefetched != null ? await prefetched : await api(imaDocumentsRequestPath());
    if (!routeStillActive(seq)) return;
    $("#ima-report-page")?.removeAttribute("aria-busy");
    const groups = Array.isArray(data.groups) ? data.groups : [];
    const items = Array.isArray(data.items) ? data.items : [];
    const selectedGroupInfo = groups.find((group) => String(group.id || "") === selectedGroup);
    const selectedGroupName = selectedGroupInfo?.name || (selectedGroup ? selectedGroup : "全部");
    const title = $("#ima-doc-title");
    const meta = $("#ima-doc-meta");
    if (title) title.textContent = "最新研报";
    const resultCount = imaDocumentsCountLabel(!!(query || tag), data.document_count, items.length, data.has_more);
    if (meta) meta.textContent = resultCount;
    if (!knowledgeMediaIdFromPath()) setPageTitle(feishuSourceDisplay(selectedGroupName).label);
    const days = Array.isArray(data.days)
      ? data.days.filter(Boolean)
      : [...new Set(items.map((item) => item.day).filter(Boolean))];
    state.imaDocumentsDays = days;
    const tagTrigger = $("#ima-doc-tag");
    _imaTagCounts = imaTagCountsFromData(data);
    _imaDocumentCount = Number(data.document_count) || imaTagCoverageBase(_imaTagCounts, 0);
    const uniqueTags = Array.isArray(data.tags)
      ? data.tags.filter(Boolean)
      : Object.keys(_imaTagCounts);
    if (tag && !uniqueTags.includes(tag)) uniqueTags.unshift(tag);
    if (tagTrigger) {
      tagTrigger.textContent = tag || "标签";
      if (uniqueTags.length || tag) tagTrigger.removeAttribute("hidden");
      else tagTrigger.hidden = true;
    }
    const navSlot = $("#ima-doc-day-nav-slot");
    if (navSlot) {
      closeImaDayPicker();
      navSlot.innerHTML = imaDocumentsDayNavHtml(searchMode ? "" : day, days);
    }
    const hasFilter = !!(query || tag);
    syncImaDocumentsFilterStatus();
    _imaItems.length = 0;
    _imaItems.push(...items);
    state.imaDocumentsHasMore = !!(paged && data.has_more);
    const body = $("#ima-docs-body");
    if (!items.length) {
      body.innerHTML = imaDocumentsEmptyHtml(hasFilter);
      return;
    }
    const more = state.imaDocumentsHasMore
      ? `<div id="ima-docs-more" class="ima-docs-more" role="status" aria-live="polite">下滑加载更多</div>`
      : "";
    body.innerHTML = `<div class="ima-doc-list">${items.map((item) => imaDocumentRow(item)).join("")}</div>${more}`;
    startImaDocumentsAutoLoad();
  } catch (err) {
    if (!routeStillActive(seq)) return;
    const body = $("#ima-docs-body");
    $("#ima-report-page")?.removeAttribute("aria-busy");
    if (keepOld && oldHtml && body) {
      body.innerHTML = oldHtml;
      body.insertAdjacentHTML("afterbegin", imaReportRefreshErrorHtml(err.message || "请求失败"));
      return;
    }
    const denied = String(err.message || "").includes("知识库不存在");
    body.innerHTML = denied
      ? emptyState("没有访问权限", `<div><button type="button" class="btn-normal" onclick="go('knowledge')">回研报库</button></div>`)
      : emptyState(`加载失败：${err.message}`, `<div><button type="button" class="btn-normal" onclick="refreshImaDocuments()">重试</button></div>`);
  }
}

function imaDocumentsFilterChipsHtml() {
  const chips = [];
  if (state.imaDocumentsQuery) {
    chips.push(`<span class="ima-doc-filter-chip">搜索 ${escapeHtml(state.imaDocumentsQuery)}<button type="button" onclick="clearImaDocumentsFilter('q')" aria-label="清除搜索">${X_ICON}</button></span>`);
  }
  if (state.imaDocumentsTag) {
    chips.push(`<span class="ima-doc-filter-chip">${escapeHtml(state.imaDocumentsTag)}<button type="button" onclick="clearImaDocumentsFilter('tag')" aria-label="清除标签">${X_ICON}</button></span>`);
  }
  if (!chips.length) return "";
  chips.push(`<button type="button" class="btn-ghost" onclick="clearImaDocumentsFilters()">清除筛选</button>`);
  return chips.join("");
}

function syncImaDocumentsFilterStatus() {
  const chips = $("#ima-doc-filter-chips");
  if (chips) chips.innerHTML = imaDocumentsFilterChipsHtml();
}

function clearImaDocumentsFilter(kind) {
  if (kind === "q") {
    state.imaDocumentsQuery = "";
    const input = $("#ima-doc-q");
    if (input) input.value = "";
  }
  if (kind === "day") state.imaDocumentsDay = "";
  if (kind === "tag") state.imaDocumentsTag = "";
  if (kind !== "day") state.imaDocumentsDay = "";
  replaceImaDocumentsRoute(imaDocumentsRoute(state.imaDocumentsGroup, state.imaDocumentsQuery, state.imaDocumentsDay, state.imaDocumentsTag));
  renderImaDocuments(++routeRenderSeq);
}

function clearImaDocumentsFilters() {
  state.imaDocumentsQuery = "";
  state.imaDocumentsTag = "";
  state.imaDocumentsDay = "";
  const input = $("#ima-doc-q");
  if (input) input.value = "";
  replaceImaDocumentsRoute(imaDocumentsRoute(state.imaDocumentsGroup, "", state.imaDocumentsDay, ""));
  renderImaDocuments(++routeRenderSeq);
}

function stopImaDocumentsAutoLoad() {
  _imaDocsLoadObserver?.disconnect();
  _imaDocsLoadObserver = null;
  if (_imaDocsLoadFallback) {
    const body = $("#ima-docs-body");
    body?.removeEventListener("scroll", _imaDocsLoadFallback);
    _imaDocsLoadFallback = null;
  }
  clearTimeout(_imaSearchTimer);
  _imaSearchTimer = null;
  _imaLoadingMore = false;
}

function startImaDocumentsAutoLoad() {
  stopImaDocumentsAutoLoad();
  const body = $("#ima-docs-body");
  const sentinel = $("#ima-docs-more");
  if (!body || !sentinel || !state.imaDocumentsHasMore) return;
  const load = () => loadImaDocumentsMore();
  if ("IntersectionObserver" in window) {
    _imaDocsLoadObserver = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) load();
    }, { root: body, rootMargin: "400px 0px" });
    _imaDocsLoadObserver.observe(sentinel);
    return;
  }
  _imaDocsLoadFallback = () => {
    if (body.scrollTop + body.clientHeight >= body.scrollHeight - 400) load();
  };
  body.addEventListener("scroll", _imaDocsLoadFallback, { passive: true });
  _imaDocsLoadFallback();
}

async function loadImaDocumentsMore() {
  if (_imaLoadingMore || !state.imaDocumentsHasMore) return;
  if (state.imaDocumentsDay && !state.imaDocumentsQuery && !state.imaDocumentsTag) return;
  _imaLoadingMore = true;
  const moreBtn = $("#ima-docs-more");
  if (moreBtn) {
    moreBtn.textContent = "正在加载更多…";
    moreBtn.setAttribute("aria-busy", "true");
  }
  const seq = routeRenderSeq;
  const listSeq = _imaListSeq;
  try {
    const params = new URLSearchParams();
    if (state.imaDocumentsQuery) params.set("q", state.imaDocumentsQuery);
    if (state.imaDocumentsTag) params.set("tag", state.imaDocumentsTag);
    if (state.imaDocumentsGroup) params.set("group", state.imaDocumentsGroup);
    params.set("limit", "50");
    params.set("offset", String(_imaItems.length));
    const data = await api(`/api/ima-documents?${params.toString()}`);
    if (listSeq !== _imaListSeq || !routeStillActive(seq)) return;
    const incoming = Array.isArray(data.items) ? data.items : [];
    _imaItems.push(...incoming);
    state.imaDocumentsHasMore = !!data.has_more && incoming.length > 0;
    const body = $("#ima-docs-body");
    const list = body?.querySelector(".ima-doc-list");
    if (list && incoming.length) {
      list.insertAdjacentHTML("beforeend", incoming.map((item) => imaDocumentRow(item)).join(""));
    }
    const btn = $("#ima-docs-more");
    if (!state.imaDocumentsHasMore) {
      btn?.remove();
    } else if (btn) {
      btn.textContent = "下滑加载更多";
      btn.removeAttribute("aria-busy");
    }
    startImaDocumentsAutoLoad();
    const meta = $("#ima-doc-meta");
    if (meta) {
      meta.textContent = imaDocumentsCountLabel(
        !!(state.imaDocumentsQuery || state.imaDocumentsTag),
        _imaDocumentCount,
        _imaItems.length,
        state.imaDocumentsHasMore,
      );
    }
  } catch (err) {
    if (listSeq !== _imaListSeq || !routeStillActive(seq)) return;
    const failed = $("#ima-docs-more");
    if (failed) {
      failed.removeAttribute("aria-busy");
      failed.innerHTML = `<button type="button" class="btn-ghost" onclick="loadImaDocumentsMore()">加载失败，重试</button>`;
    }
  } finally {
    if (listSeq === _imaListSeq) _imaLoadingMore = false;
  }
}

function backFromImaReader(fallbackRoute, focusSearch = false) {
  clearImaPdfUrl();
  const snapshot = _imaListSnapshot;
  // ponytail: 直链/刷新进入时上一页不是知识库（history.back 会跑偏到广场）；列表点进来才有 selectedKey
  if (snapshot && snapshot.selectedKey && snapshot.route === normalizeRoute(fallbackRoute)) {
    if (focusSearch) snapshot.focusSearch = true;
    history.back();
    return;
  }
  go(fallbackRoute);
}

function imaReaderNavHtml(mediaId, groupId = "", snapshot = null) {
  if (!snapshot || snapshot.items.length < 2) return "";
  const current = imaDocumentKey(mediaId, groupId);
  const index = snapshot.items.findIndex((item) => imaDocumentKey(item.media_id, item.group_id) === current);
  if (index < 0) return "";
  const prev = snapshot.items[index - 1];
  const next = snapshot.items[index + 1];
  const button = (item, className, label) => item
    ? `<button type="button" class="${className}" data-media-id="${escapeHtml(item.media_id)}" data-group-id="${escapeHtml(item.group_id || "")}" onclick="openImaDocument(this.dataset.mediaId, this.dataset.groupId, true)">${label} <span>${escapeHtml(imaListTitle(item.name))}</span></button>`
    : "";
  return `<nav class="ima-reader-nav" aria-label="同一结果集">${button(prev, "ima-reader-prev", "上一份")}${button(next, "ima-reader-next", "下一份")}</nav>`;
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

async function renderImaDocument(seq, mediaId) {
  if (!$("#kb-reader")) {
    await renderKnowledge(seq, encodeURIComponent(mediaId));
    return;
  }
  const readerSeq = ++_imaReaderSeq;
  clearImaPdfUrl();
  const currentQuery = routeQuery();
  const listGroup = currentQuery.get("group") || state.imaDocumentsGroup || "";
  const documentGroup = currentQuery.get("doc_group") || listGroup;
  const query = currentQuery.get("q") || state.imaDocumentsQuery || "";
  const day = currentQuery.get("day") || state.imaDocumentsDay || "";
  const tag = currentQuery.get("tag") || state.imaDocumentsTag || "";
  state.imaDocumentsTag = tag;
  const groupQuery = documentGroup ? `?group=${encodeURIComponent(documentGroup)}` : "";
  let backRoute = imaDocumentsRoute(listGroup, query, day, tag);
  setPageTitle("研报库");
  $("#kb-reader").innerHTML = `<div class="admin-skeleton" aria-hidden="true"></div>`;
  try {
    const item = await api(`/api/ima-documents/${encodeURIComponent(mediaId)}${groupQuery}`);
    if (!currentQuery.has("group") && !currentQuery.has("doc_group") && item.group_id) {
      backRoute = imaDocumentsRoute(item.group_id, query, day, tag);
    }
    if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq) return;
    const isFeishuTimeline = item.type === "feishu_timeline";
    setPageTitle(
      isFeishuTimeline
        ? feishuSourceDisplay(item.group_name || item.name).label
        : (item.group_name || $("#ima-doc-title")?.textContent || "研报库")
    );
    const ticker = isFeishuTimeline ? "" : imaDocTicker(item.name);
    const tickerMeta = ticker ? `<span class="ima-reader-meta-item">${escapeHtml(ticker)}</span>` : "";
    const dayContext = !isFeishuTimeline && (item.sort_date || item.day)
      ? `<span class="ima-reader-day ima-reader-meta-item">${escapeHtml(fmtImaDay(item.sort_date || item.day))}</span>`
      : "";
    const abstractText = isFeishuTimeline ? "" : (item.abstract_zh || item.abstract || "");
    const abstractLong = abstractText.length > IMA_ABSTRACT_CLAMP_CHARS;
    const abstractMore = abstractLong
      ? `<button type="button" class="ima-abstract-more" aria-expanded="false" onclick="toggleImaAbstract(this)">展开</button>`
      : "";
    const copyBtn = `<button type="button" class="ima-abstract-copy-btn" onclick="event.stopPropagation();copyImaAbstract()" aria-label="复制摘要" title="复制摘要"><span aria-hidden="true">📋</span> 复制摘要</button>`;
    const abstractHtml = abstractText
      ? `<details open class="ima-reader-abstract${abstractLong ? " is-clamped" : ""}"><summary><span>摘要</span>${copyBtn}</summary><p id="ima-reader-abstract">${escapeHtml(abstractText)}</p>${abstractMore}</details>`
      : "";
    // 快照路由校验（与 currentImaListSnapshot 同思路）：与本次应返回的列表路由不匹配的旧快照不用于导航/计数
    const listSnapshot = _imaListSnapshot && _imaListSnapshot.route === normalizeRoute(backRoute) ? _imaListSnapshot : null;
    const standalonePwa = isStandalonePwa();
    const openLabel = standalonePwa ? "打开 PDF" : "新标签打开 PDF";
    const openNewTab = isFeishuTimeline
      ? `<a class="icon-btn" data-feishu-canonical="1" href="${escapeHtml(item.source_url || "")}" ${item.source_url ? "" : "hidden"} target="_blank" rel="noopener" aria-label="打开飞书原文" title="打开飞书原文">${EXTERNAL_LINK_ICON}</a>`
      : item.has_pdf
        ? `<button type="button" class="icon-btn" aria-label="${openLabel}" title="${openLabel}" onclick="openImaPdfNewTab()">${EXTERNAL_LINK_ICON}</button>`
        : "";
    const documentPanel = isFeishuTimeline
      ? `<div id="ima-document-panel" class="feishu-timeline-panel" aria-busy="true"><p class="ima-reader-status" role="status">正在载入时间线…</p></div>`
      : item.has_pdf
        ? `<div id="ima-pdf-panel" class="ima-pdf-panel" aria-busy="true"><p class="ima-reader-status" role="status">正在打开预览…</p>${standalonePwa
            ? `<button id="ima-pdf-pwa-open" type="button" class="btn-normal" onclick="openImaPdfNewTab()" hidden>打开 PDF</button>`
            : `<iframe id="ima-pdf-frame" title="PDF 预览" hidden style="position:absolute;inset:0;width:100%;height:100%;border:0"></iframe>`}</div>`
        : `<div class="ima-pdf-panel"><div class="ima-reader-empty" role="status"><p>还没有预览文件</p></div></div>`;
    const sizeLine = isFeishuTimeline ? "" : fmtDocSize(item.size);
    const sizeMeta = sizeLine ? `<span class="ima-reader-meta-item">${escapeHtml(sizeLine)}</span>` : "";
    const fileMetaHtml = (tickerMeta || dayContext || sizeMeta)
      ? `<div class="ima-reader-filemeta">${tickerMeta}${dayContext}${sizeMeta}</div>`
      : "";
    const readerTitle = escapeHtml(isFeishuTimeline ? feishuSourceDisplay(item.name).label : imaDisplayTitle(item.name));
    const fromSearch = !!(query || tag);
    const searchBack = fromSearch
      ? `<button type="button" class="icon-btn" aria-label="返回搜索" data-back="${escapeHtml(backRoute)}" onclick="backFromImaReader(this.dataset.back, true)">${SEARCH_ICON}</button>`
      : "";
    $("#kb-reader").innerHTML = isFeishuTimeline
      ? `
      <article class="ima-reader ima-reader--feishu">
        <header class="ima-reader-toolbar">
          <button type="button" class="ima-reader-back" data-back="${escapeHtml(backRoute)}" onclick="backFromImaReader(this.dataset.back)" aria-label="返回"><span class="ima-back-icon" aria-hidden="true">‹</span>返回</button>
          <h2 class="ima-reader-title">${readerTitle}</h2>
          <div class="ima-reader-actions">${searchBack}${openNewTab}</div>
        </header>
        <div id="feishu-timeline-toolbar" class="feishu-timeline-toolbar"></div>
        ${documentPanel}
      </article>`
      : `
      <article class="ima-reader">
        <header class="ima-reader-toolbar">
          <button type="button" class="ima-reader-back" data-back="${escapeHtml(backRoute)}" onclick="backFromImaReader(this.dataset.back)" aria-label="返回"><span class="ima-back-icon" aria-hidden="true">‹</span>返回</button>
          <div class="ima-reader-actions">${searchBack}${openNewTab}</div>
        </header>
        <section class="ima-reader-info">
          <h2 class="ima-reader-title">${readerTitle}</h2>
          ${fileMetaHtml}
          ${imaReaderWatchHtml(item.tags)}
          ${abstractHtml}
        </section>
        ${documentPanel}
        ${imaReaderNavHtml(mediaId, item.group_id || documentGroup, listSnapshot)}
      </article>`;
    if (isFeishuTimeline) await loadFeishuTimeline(item, seq, readerSeq);
    else if (item.has_pdf) loadImaPdf(mediaId, readerSeq);
    if (item.needs_translation) {
      try {
        const translated = await api(`/api/ima-documents/${encodeURIComponent(mediaId)}/translate${groupQuery}`, { method: "POST" });
        if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq) return;
        const zh = translated && translated.abstract_zh;
        const el = $("#ima-reader-abstract");
        if (el && zh) el.textContent = zh;
      } catch {
        /* keep original abstract */
      }
    }
  } catch (err) {
    if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq) return;
    const denied = String(err.message || "").includes("知识库不存在");
    $("#kb-reader").innerHTML = denied
      ? emptyState("没有访问权限", `<div><button type="button" class="btn-normal" onclick="go('${escapeHtml(backRoute)}')">回研报库</button></div>`)
      : emptyState(`文档加载失败：${err.message}`, `<div><button type="button" class="btn-normal" onclick="go('${escapeHtml(backRoute)}')">返回文档列表</button></div>`);
  }
}

function showImaPdfFail(mediaId, seq, readerSeq) {
  if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq) return;
  const panel = $("#ima-pdf-panel");
  if (!panel) return;
  clearImaPdfUrl();
  panel.hidden = false;
  panel.removeAttribute("aria-busy");
  panel.innerHTML = `<div class="ima-reader-empty" role="status"><p>预览打不开</p></div>`;
}

async function loadImaPdf(mediaId, readerSeq) {
  const seq = routeRenderSeq;
  const group = imaReaderDocumentGroup();
  const groupQuery = group ? `?group=${encodeURIComponent(group)}` : "";
  if (_imaPdfAbort) _imaPdfAbort.abort();
  const abort = new AbortController();
  _imaPdfAbort = abort;
  try {
    const blob = await apiBlob(`/api/ima-documents/${encodeURIComponent(mediaId)}/pdf${groupQuery}`, { signal: abort.signal });
    if (abort.signal.aborted) return;
    if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq) return;
    const head = blob.size ? await blob.slice(0, 5).text() : "";
    if (abort.signal.aborted) return;
    if (!routeStillActive(seq) || readerSeq !== _imaReaderSeq) return;
    if (blob.size < 64 || head !== "%PDF-") {
      showImaPdfFail(mediaId, seq, readerSeq);
      return;
    }
    if (window._imaPdfUrl) URL.revokeObjectURL(window._imaPdfUrl);
    window._imaPdfUrl = URL.createObjectURL(blob);
    const frame = $("#ima-pdf-frame");
    const panel = $("#ima-pdf-panel");
    const pwaOpen = $("#ima-pdf-pwa-open");
    if (panel && (frame || pwaOpen)) {
      const status = panel.querySelector(".ima-reader-status");
      if (status) status.remove();
      panel.hidden = false;
      panel.removeAttribute("aria-busy");
      if (pwaOpen) {
        pwaOpen.hidden = false;
      } else if (frame) {
        frame.src = `${window._imaPdfUrl}#view=FitH&zoom=page-width`;
        frame.hidden = false;
        frame.addEventListener("error", () => showImaPdfFail(mediaId, seq, readerSeq), { once: true });
      }
    }
  } catch (err) {
    if (err && err.name === "AbortError") return;
    if (routeStillActive(seq) && readerSeq === _imaReaderSeq) {
      const message = String(err.message || "");
      if (message.includes("频繁") || message.includes("上限")) flash(message, "error");
      showImaPdfFail(mediaId, seq, readerSeq);
    }
  }
}

function openImaPdfNewTab() {
  if (!window._imaPdfUrl) {
    flash("PDF 还没加载好，稍后再试", "error");
    return;
  }
  if (isStandalonePwa()) {
    window.location.assign(window._imaPdfUrl);
    return;
  }
  window.open(window._imaPdfUrl, "_blank", "noopener");
}

async function downloadImaPdf(mediaId) {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const group = imaReaderDocumentGroup();
  const groupQuery = group ? `&group=${encodeURIComponent(group)}` : "";
  const detailQuery = group ? `?group=${encodeURIComponent(group)}` : "";
  try {
    const [blob, item] = await Promise.all([
      apiBlob(`/api/ima-documents/${encodeURIComponent(mediaId)}/pdf?download=1${groupQuery}`),
      api(`/api/ima-documents/${encodeURIComponent(mediaId)}${detailQuery}`),
    ]);
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = item.name || "ima-document.pdf";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => {
      if (sessionOwnerStillActive(routeSeq, token, sessionGeneration)) URL.revokeObjectURL(url);
    }, 1000);
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(`PDF 下载失败：${err.message}`, "error");
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
      <div class="kol-card-head">
        ${avatarHtml(kol.name, kol.avatar_url)}
        <div class="kol-card-info">
          <span class="name" title="${escapeHtml(kol.name)}">${escapeHtml(kol.name)}</span>
          ${tags.length ? `<div class="kol-card-meta">${tags.join("")}</div>` : ""}
          <div class="desc">外部 ID：${escapeHtml(kol.external_id)}${kol.enabled ? "" : " · 已停用"}</div>
        </div>
      </div>
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
  if (!confirm(`确认删除该大V${kol ? `「${kol.name}」` : ""}？其订阅关系会一并移除。`)) return;
  try {
    await api(`/api/kols/${kolId}`, { method: "DELETE" });
    flash(`已删除「${kol ? kol.name : "该大V"}」`);
    await refreshKolsView(); // 按当前路由刷新，删除期间切走不会污染新页面
  } catch (err) {
    alert("删除失败: " + err.message);
  }
}

async function toggleSubscribe(kolId, btn) {
  const kol = state.catalog.find((k) => k.id === kolId);
  if (kol?.subscribed && !confirm(`取消订阅「${kol.name}」？将不再推送其新动态。`)) return;
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
    alert("操作失败: " + err.message);
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
    alert("操作失败: " + err.message);
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
    alert("操作失败: " + err.message);
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
    alert("订阅失败: " + err.message);
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
    alert("请至少保留一种订阅类型；取消订阅请点「已订阅」按钮");
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
    alert("切换订阅类型失败: " + err.message);
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
    state.timelineSecondary,
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
  return chips;
}

function tlSnapshotFilters() {
  return {
    timelinePlatform: state.timelinePlatform,
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
  state.timelineFavorite = snap.timelineFavorite;
  state.timelineSecondary = snap.timelineSecondary;
  state.timelineQ = snap.timelineQ;
  state.timelineTag = snap.timelineTag;
  state.timelineCategory = snap.timelineCategory;
  const q = $("#tl-q"); if (q) q.value = state.timelineQ || "";
  const tag = $("#tl-tag"); if (tag) tag.value = state.timelineTag || "";
  const pills = $("#tl-pills");
  if (pills) pills.innerHTML = tlPillsHtml();
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
  return !!el.closest("a, button, input, select, textarea, .tl-pills, .platform-tabs, .icon-badge-bar, .tl-filter-panel, .home-filter-content, .lightbox, .bottom-nav, .post-images");
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
    </div>`;
  tlSyncNewBadgeMode();
  if (live) startLiveClock();
  else stopLiveClock();
  renderLiveRail();
  if (reuse) {
    renderFeed();
    window.scrollTo(0, feedScrollY());
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
      if (state.timelineCategory) params.set("category_id", state.timelineCategory);
      if (state.timelineTag) params.set("tag", state.timelineTag);
      if (state.timelineFavorite) params.set("favorite", "1");
      if (state.timelineSecondary) params.set("include_secondary", "1");
      const posts = await api(`/api/my/feed?${params}`);
      if (!routeStillActive(seq) || !$("#feed") || isLiveTimeline()) return;
      newer = posts.filter((p) => p.id > pendingLatestId);
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
    avs.push(p.avatar_url
      ? `<img src="${escapeHtml(p.avatar_url)}" alt="" onerror="this.remove()">`
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
    const incoming = pending.filter((p) => !seen.has(p.id)).sort((a, b) => b.id - a.id);
    if (incoming.length) {
      posts.unshift(...incoming);
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
  if (leftLive) {
    stopTimelinePoll();
    if ($("#tl-feed-panel")) syncTimelineSourceView();
    else renderTimeline(routeRenderSeq);
    return;
  }
  const pills = $("#tl-pills");
  if (pills) pills.innerHTML = tlPillsHtml();
  tlSyncFilterChrome();
  loadTimeline(true, routeRenderSeq, { revert });
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
  state.timelineFavorite = false;
  state.timelineSecondary = false;
  const q = $("#tl-q"); if (q) q.value = "";
  const tag = $("#tl-tag"); if (tag) tag.value = "";
  const pills = $("#tl-pills"); if (pills) pills.innerHTML = tlPillsHtml();
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
  const body = escapeHtml(item.body || "").replace(/\n/g, "<br>");
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
  const post = _tlPosts.find((p) => p.id === id);
  const card = document.querySelector(`.post-item[data-post-id="${id}"]`);
  if (post && card) {
    const wrap = document.createElement("div");
    wrap.innerHTML = postCard(post).trim();
    const next = wrap.firstElementChild;
    if (next) {
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
  if (clockOnly) return `${p(d.getHours())}:${p(d.getMinutes())}`;
  const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (sameDay(d, now)) return `今天 ${p(d.getHours())}:${p(d.getMinutes())}`;
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (sameDay(d, yesterday)) return `昨天 ${p(d.getHours())}:${p(d.getMinutes())}`;
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}月${d.getDate()}日`;
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
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
      <div class="p-content">${escapeHtml(shown)}${body.length > 200
        ? `<button class="post-expand-btn" onclick="tlTogglePost(${post.id})" aria-expanded="${expanded}">${expanded ? "收起 ▲" : "展开全文 ▼"}</button>`
        : ""}</div>`}
      ${Array.isArray(post.images) && post.images.length ? `
        <div class="post-images">
          ${post.images.slice(0, 4).map((img) => `
            <a class="post-img-link" href="#" onclick="event.preventDefault();openLightbox(this.querySelector('img'))" aria-label="查看${escapeHtml(post.kol_name)}的配图"><img src="${escapeHtml(imgSrcFor(img))}" loading="lazy" alt="${escapeHtml(post.kol_name)} 的配图" onerror="imgOnError(this)"></a>`).join("")}
          ${post.images.length > 4 ? `<span class="post-images-more">+${post.images.length - 4}</span>` : ""}
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
      <div class="p-meta">
        ${post.category_name ? `<span class="cat">${escapeHtml(post.category_name)}</span>` : ""}
        ${post.post_type === "reply" ? `<span class="cat">回复</span>` : ""}
        ${Array.isArray(post.tags) && post.tags.length
          ? post.tags.map((t) => `<button type="button" class="cat cat-tag post-tag-filter" data-tag="${escapeHtml(t)}" onclick="tlPickTag(this.dataset.tag)">${escapeHtml(t)}</button>`).join("")
          : ""}
        ${post.platform === "zsxq" ? "" : `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener">查看原文 →</a>`}
      </div>
    </div>`;
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
async function renderKolPage(kolId, seq) {
  setPageTitle("大V动态", true);
  $("#main").innerHTML = `<div class="empty">加载中…</div>`;
  try {
    const kol = await api(`/api/kols/${kolId}`);
    const posts = await api(`/api/kols/${kolId}/posts?limit=50`);
    if (!routeStillActive(seq)) return; // 已切走：不写旧页面
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
        <div id="kol-posts">${posts.length ? posts.map(postCard).join("") : emptyState("暂无动态")}</div>
      </section>`;
  } catch (err) {
    if (!routeStillActive(seq)) return;
    $("#main").innerHTML = emptyState("加载失败: " + err.message);
  }
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
  // 数据源页分段导航：抓取设置 / Cookie 管理 / 代理 / 广场显示 / 财经资讯
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
  const loaders = { dashboard: loadAdminDashboard, stats: loadAdminStats, knowledge: loadAdminKnowledge, kols: loadAdminKols, requests: loadAdminRequests, codes: loadAdminCodes, vocab: loadAdminVocab, posts: loadAdminPosts, logs: loadAdminLogs, audit: loadAdminAudit, backup: loadAdminBackup, users: loadAdminUsers };
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
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/.exec(String(s));
  if (!m) return s;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
  if (Number.isNaN(d.getTime())) return s;
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

function imaMountCacheKey(groupId, parentId) {
  return `${groupId}\0${parentId}`;
}

function imaMountGroup(groupId) {
  return imaMountState.groups.find((group) => String(group.id || "") === String(groupId || "")) || null;
}

function imaMountDraft(groupId) {
  let draft = imaMountState.drafts.get(groupId);
  if (!draft) {
    draft = new Set();
    imaMountState.drafts.set(groupId, draft);
  }
  return draft;
}

function imaGroupIntervalSeconds(group) {
  const sec = Number(group?.interval_seconds || 3600);
  if (sec < 10800) return 3600;
  if (sec < 43200) return 21600;
  return 86400;
}

function initImaMountState(groups, preserve = false) {
  const oldDrafts = imaMountState.drafts;
  const oldSelected = imaMountState.selectedGroupId;
  const oldDirty = imaMountState.dirty;
  const oldGroupsById = new Map(
    imaMountState.groups.map((group) => [String(group.id), group]),
  );
  imaMountState.groups = (Array.isArray(groups) ? groups.filter((group) => group && group.id) : []).map((group) => {
    const previous = oldGroupsById.get(String(group.id));
    const incoming = Number(group.interval_seconds);
    const fallback = previous ? Number(previous.interval_seconds) || 3600 : 3600;
    return {
      ...group,
      interval_seconds: Number.isFinite(incoming) && incoming > 0 ? incoming : fallback,
    };
  });
  imaMountState.selectedGroupId = oldSelected;
  imaMountState.drafts = new Map();
  imaMountState.folders = new Map();
  imaMountState.parents = new Map();
  imaMountState.expanded = new Set();
  imaMountState.loading = new Set();
  imaMountState.errors = new Map();
  imaMountState.folderRequests = new Map();
  imaMountState.discoveryBusy = false;
  imaMountState.discoveryOwner = null;
  imaMountState.generation += 1;
  if (!preserve && !imaMountState.saveOwner) imaMountState.revision += 1;
  imaMountState.dirty = preserve ? oldDirty : false;
  if (!preserve) imaMountState.discoveryEntered = false;
  if (!preserve) imaMountState.folderPanelGroupId = "";
  if (!preserve) imaMountState.folderPanelTouched = false;
  const available = new Set(imaMountState.groups.map((group) => String(group.id)));
  for (const group of imaMountState.groups) {
    const previous = preserve ? oldDrafts.get(String(group.id)) : null;
    const values = previous
      ? [...previous]
      : (Array.isArray(group.folder_ids) ? group.folder_ids : []);
    imaMountState.drafts.set(
      String(group.id),
      new Set(values.filter((folderId) => typeof folderId === "string" && folderId.trim())),
    );
  }
  if (!available.has(String(imaMountState.selectedGroupId || ""))) {
    imaMountState.selectedGroupId = imaMountState.groups[0] ? String(imaMountState.groups[0].id) : "";
  }
}

function imaIntervalSegHtml(group) {
  const groupId = String(group?.id || "");
  const current = imaGroupIntervalSeconds(group);
  return `<span class="ima-interval-seg" data-group-id="${escapeHtml(groupId)}">${
    [[3600, "1h"], [21600, "6h"], [86400, "24h"]].map(([sec, label]) =>
      `<button type="button" id="ima-interval-${escapeHtml(groupId)}-${sec}" data-sec="${sec}" aria-pressed="${current === sec}" class="${current === sec ? "is-on" : ""}" onclick="setImaGroupInterval(event, this)">${label}</button>`
    ).join("")
  }</span>`;
}

function imaMountGroupRowHtml(group) {
  const groupId = String(group?.id || "");
  const draft = imaMountState.drafts.get(groupId) || new Set();
  const selected = groupId === String(imaMountState.selectedGroupId || "");
  const source = group?.source === "discovered" ? "自动发现" : "旧配置";
  const count = draft.size;
  const mountText = count ? `已选择 ${count} 个文件夹` : "未挂载";
  return `<button type="button" class="ima-mount-kb-row${selected ? " is-selected" : ""}"
    id="ima-kb-row-${escapeHtml(groupId)}" role="option" aria-selected="${selected}"
    data-group-id="${escapeHtml(groupId)}" onclick="selectImaMountGroup(this.dataset.groupId)">
    <span class="ima-mount-kb-copy">
      <span class="ima-mount-kb-name" title="${escapeHtml(group?.name || groupId)}">${escapeHtml(group?.name || groupId)}</span>
      <span class="ima-mount-kb-meta">${escapeHtml(source)} · ${escapeHtml(mountText)}</span>
    </span>
    <span class="ima-mount-kb-count" aria-hidden="true">${count}</span>
  </button>`;
}

function renderImaSelectedGroup() {
  const group = imaMountGroup(imaMountState.selectedGroupId);
  const title = $("#ima-selected-group-name");
  const interval = $("#ima-selected-interval");
  const select = $("#ima-kb-select");
  if (select) {
    select.innerHTML = imaMountState.groups.map((item) => {
      const id = String(item.id || "");
      return `<option value="${escapeHtml(id)}"${id === String(imaMountState.selectedGroupId) ? " selected" : ""}>${escapeHtml(item.name || id)}</option>`;
    }).join("");
  }
  if (!group) {
    if (title) title.textContent = "选择知识库";
    if (interval) interval.innerHTML = "";
    return;
  }
  if (title) title.textContent = group.name || String(group.id);
  if (interval) {
    const hours = Math.round(imaGroupIntervalSeconds(group) / 3600);
    const note = hours >= 24 ? "每日 01:00 后自动同步（上海）" : `每 ${hours} 小时检查`;
    interval.innerHTML = `${imaIntervalSegHtml(group)}<span class="muted">${note}</span>`;
  }
}

function setImaGroupInterval(event, button) {
  event?.stopPropagation?.();
  const seg = button?.closest?.(".ima-interval-seg");
  const groupId = seg?.dataset.groupId || "";
  const seconds = Number(button?.dataset.sec || 0);
  const group = imaMountGroup(groupId);
  if (!group || ![3600, 21600, 86400].includes(seconds)) return;
  group.interval_seconds = seconds;
  imaMountState.revision += 1;
  imaMountState.collectorRevision += 1;
  imaMountState.dirty = true;
  renderImaCollectorDirtyState();
  const draft = rememberImaCollectorDraft();
  if (imaMountState.saveOwner) imaMountState.saveOwner.liveSnapshot = draft;
  const focus = imaFocusSnapshot(button);
  renderImaMountGroups();
  imaRestoreFocus(focus);
}

function renderImaMountGroups() {
  const list = $("#ima-kb-list");
  if (!list) return;
  const groups = imaMountState.groups;
  list.innerHTML = groups.length
    ? groups.map((group) => imaMountGroupRowHtml(group)).join("")
    : '<div class="empty ima-mount-empty">尚未发现共享知识库</div>';
  const count = $("#ima-kb-count");
  if (count) count.textContent = `${groups.length} 个`;
  renderImaSelectedGroup();
  renderImaFolderTree(imaMountState.selectedGroupId);
  renderImaCollectorDirtyState();
}

function renderImaCollectorDirtyState() {
  const bar = $("#ima-collector-savebar");
  if (!bar) return;
  bar.hidden = !(imaMountState.dirty || imaMountState.collectorDirty);
}

function discardImaCollectorChanges() {
  if (!confirm("有未保存的采集配置修改，确定放弃？")) return;
  imaMountState.saveOwner = null;
  imaMountState.collectorDraft = null;
  imaMountState.collectorDraftRevision = "";
  imaMountState.collectorDirty = false;
  imaMountState.dirty = false;
  imaMountState.collectorConfirmedRevision = "";
  imaMountState.collectorConfirmedLiveRevision = -1;
  imaMountState.collectorConfirmedMountRevision = -1;
  renderImaCollectorDirtyState();
  loadAdminKnowledge(routeRenderSeq);
}

function imaFolderAncestorSelected(groupId, folderId) {
  const selected = imaMountDraft(groupId);
  const seen = new Set();
  let parentId = imaMountState.parents.get(imaMountCacheKey(groupId, folderId)) || "";
  while (parentId && !seen.has(parentId)) {
    if (selected.has(parentId)) return true;
    seen.add(parentId);
    parentId = imaMountState.parents.get(imaMountCacheKey(groupId, parentId)) || "";
  }
  return false;
}

function normalizeImaMountDraft(groupId) {
  const selected = imaMountDraft(groupId);
  for (const folderId of [...selected]) {
    if (imaFolderAncestorSelected(groupId, folderId)) selected.delete(folderId);
  }
}

function imaFolderDescendantSelected(groupId, folderId) {
  const selected = imaMountDraft(groupId);
  for (const selectedId of selected) {
    if (selectedId === folderId) continue;
    const seen = new Set();
    let parentId = imaMountState.parents.get(imaMountCacheKey(groupId, selectedId)) || "";
    while (parentId && !seen.has(parentId)) {
      if (parentId === folderId) return true;
      seen.add(parentId);
      parentId = imaMountState.parents.get(imaMountCacheKey(groupId, parentId)) || "";
    }
  }
  return false;
}

function imaFolderSelectionState(groupId, folderId) {
  const inherited = imaFolderAncestorSelected(groupId, folderId);
  const selected = imaMountDraft(groupId).has(folderId);
  return {
    checked: selected || inherited,
    disabled: inherited,
    indeterminate: !selected && !inherited && imaFolderDescendantSelected(groupId, folderId),
  };
}

function imaFolderRowHtml(groupId, item, depth) {
  const folderId = String(item?.id || "");
  const name = String(item?.name || folderId);
  if (!folderId) return "";
  imaMountState.parents.set(imaMountCacheKey(groupId, folderId), String(item?.parent_id || ""));
  const childKey = imaMountCacheKey(groupId, folderId);
  const knownEmpty = item?.has_children === false || Number(item?.folder_count) === 0;
  const hasChildren = !knownEmpty || imaMountState.folders.has(childKey);
  const expanded = imaMountState.expanded.has(childKey);
  const selection = imaFolderSelectionState(groupId, folderId);
  const inputId = `ima-folder-${groupId}-${folderId}`;
  const expand = hasChildren
    ? `<button type="button" class="ima-folder-expand" id="ima-folder-expand-${escapeHtml(groupId)}-${escapeHtml(folderId)}" data-group-id="${escapeHtml(groupId)}" data-folder-id="${escapeHtml(folderId)}" aria-expanded="${expanded}" aria-label="${expanded ? "收起" : "展开"} ${escapeHtml(name)}" title="${expanded ? "收起" : "展开"}" onclick="toggleImaFolderExpand(this)"><span aria-hidden="true">${expanded ? "⌄" : "›"}</span></button>`
    : '<span class="ima-folder-expand-placeholder" aria-hidden="true"></span>';
  const nested = expanded ? imaRenderFolderBranch(groupId, folderId, depth + 1) : "";
  return `
    <div class="ima-folder-node" style="--ima-folder-indent:${8 + Math.min(depth, 12) * 18}px">
      <div class="ima-folder-row">
        ${expand}
        <label class="ima-folder-choice" for="${escapeHtml(inputId)}">
          <input id="${escapeHtml(inputId)}" type="checkbox" data-group-id="${escapeHtml(groupId)}" data-folder-id="${escapeHtml(folderId)}"
            ${selection.checked ? "checked" : ""}${selection.disabled ? " disabled" : ""}${selection.indeterminate ? ' data-indeterminate="true"' : ""}
            onchange="toggleImaFolder(this)">
          <span class="ima-folder-icon" aria-hidden="true">${FOLDER_ICON}</span>
          <span class="ima-folder-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
        </label>
      </div>
      ${nested}
    </div>`;
}

function imaFolderErrorHtml(groupId, parentId, error) {
  return `<div class="ima-folder-state ima-folder-error" role="alert"><span>${escapeHtml(error || "文件夹加载失败")}</span><button type="button" class="btn-ghost btn-sm" id="ima-folder-retry-${escapeHtml(groupId)}-${escapeHtml(parentId)}" data-group-id="${escapeHtml(groupId)}" data-parent-id="${escapeHtml(parentId)}" onclick="retryImaFolderLoad(this)">重试</button></div>`;
}

function imaRenderFolderBranch(groupId, parentId, depth) {
  const key = imaMountCacheKey(groupId, parentId);
  if (!imaMountState.folders.has(key)) {
    if (imaMountState.loading.has(key)) return '<div class="ima-folder-state">正在加载文件夹…</div>';
    const error = imaMountState.errors.get(key);
    if (error) return imaFolderErrorHtml(groupId, parentId, error);
    return '<div class="ima-folder-state">展开后加载文件夹</div>';
  }
  const items = imaMountState.folders.get(key) || [];
  if (!items.length) return '<div class="ima-folder-state">没有可挂载的子文件夹</div>';
  return items.map((item) => imaFolderRowHtml(groupId, item, depth)).join("");
}

function imaFolderOrphansHtml(groupId, rootId) {
  const rootKey = imaMountCacheKey(groupId, rootId);
  if (!imaMountState.folders.has(rootKey)) return "";
  const known = new Set([rootId]);
  for (const [key, items] of imaMountState.folders) {
    if (!key.startsWith(`${groupId}\0`)) continue;
    for (const item of items || []) known.add(String(item.id || ""));
  }
  const orphanIds = [...imaMountDraft(groupId)].filter((folderId) => !known.has(folderId));
  if (!orphanIds.length) return "";
  return `<div class="ima-folder-orphans"><p class="ima-folder-state-title">已选择但当前目录中不可见</p>${orphanIds.map((folderId) => `
    <label class="ima-folder-orphan" for="ima-orphan-${escapeHtml(groupId)}-${escapeHtml(folderId)}">
      <input id="ima-orphan-${escapeHtml(groupId)}-${escapeHtml(folderId)}" type="checkbox" checked data-group-id="${escapeHtml(groupId)}" data-folder-id="${escapeHtml(folderId)}" onchange="toggleImaFolder(this)">
      <span class="ima-folder-name" title="${escapeHtml(folderId)}">${escapeHtml(folderId)}</span>
    </label>`).join("")}</div>`;
}

function toggleImaFolderPanel(button) {
  const groupId = String(imaMountState.selectedGroupId || "");
  imaMountState.folderPanelTouched = true;
  imaMountState.folderPanelGroupId = button?.getAttribute("aria-expanded") === "true" ? "" : groupId;
  renderImaFolderTree(groupId);
}

function renderImaFolderTree(groupId) {
  const tree = $("#ima-folder-tree");
  if (!tree) return;
  // ponytail: 空配置默认展开（主操作优先），选过文件夹后记住用户收起状态
  if (groupId && !imaMountDraft(String(groupId)).size && !imaMountState.folderPanelTouched) {
    imaMountState.folderPanelGroupId = String(groupId);
  }
  const open = !!groupId && imaMountState.folderPanelGroupId === String(groupId);
  const panel = $("#ima-folder-panel");
  const toggle = $("#ima-folder-panel-toggle");
  const summary = $("#ima-folder-summary");
  const selectedCount = groupId ? imaMountDraft(String(groupId)).size : 0;
  if (toggle) toggle.setAttribute("aria-expanded", String(open));
  if (panel) panel.hidden = !open;
  if (summary) summary.textContent = selectedCount ? `已选 ${selectedCount} 个 · 父目录包含新子目录` : "未选择文件夹";
  if (!open) return;
  const group = imaMountGroup(groupId);
  const title = $("#ima-folder-title");
  const count = $("#ima-folder-count");
  if (!group) {
    if (title) title.textContent = "选择知识库";
    if (count) count.textContent = "";
    tree.innerHTML = '<div class="ima-folder-state">先选择一个知识库</div>';
    return;
  }
  const groupKey = String(group.id);
  const rootId = String(group.root_folder_id || "");
  if (title) title.textContent = group.name || groupKey;
  if (count) count.textContent = `${selectedCount} 个文件夹`;
  const rootKey = imaMountCacheKey(groupKey, rootId);
  const scrollTop = tree.scrollTop;
  tree.setAttribute("aria-busy", String(imaMountState.loading.has(rootKey)));
  tree.innerHTML = imaFolderRowHtml(groupKey, {
    id: rootId,
    name: "整个知识库",
    parent_id: "",
    has_children: true,
  }, 0) + imaFolderOrphansHtml(groupKey, rootId);
  tree.querySelectorAll('input[data-indeterminate="true"]').forEach((input) => {
    input.indeterminate = true;
  });
  tree.scrollTop = scrollTop;
}

function imaRestoreFocus(focus) {
  if (!focus || (document.activeElement !== focus.element && document.activeElement !== document.body)) return;
  const target = focus.id ? document.getElementById(focus.id) : null;
  target?.focus({ preventScroll: true });
}

function imaFocusSnapshot(element = document.activeElement) {
  return { element, id: element?.id || "" };
}

function selectImaMountGroup(groupId) {
  const group = imaMountGroup(groupId);
  if (!group) return;
  const focus = imaFocusSnapshot();
  imaMountState.selectedGroupId = String(group.id);
  renderImaMountGroups();
  renderImaGroupAcl();
  imaRestoreFocus(focus);
}

let _aclCandidateUsers = null;
let _imaAclRenderSeq = 0;

async function fetchAclCandidateUsers(force = false) {
  if (!force && _aclCandidateUsers) return _aclCandidateUsers;
  _aclCandidateUsers = (await api("/api/users")).filter((u) => !u.is_admin);
  return _aclCandidateUsers;
}

function aclGrantedNames(picker) {
  return [...(picker?.querySelectorAll("[data-acl-remove]") || [])]
    .map((el) => el.getAttribute("data-acl-remove"))
    .filter(Boolean);
}

function aclChipHtml(name) {
  return `<button type="button" class="ima-acl-chip" data-acl-remove="${escapeHtml(name)}" aria-label="移除 ${escapeHtml(name)}">${escapeHtml(name)}<span aria-hidden="true">×</span></button>`;
}

function aclPickerHtml(usernames, listId, compact = false) {
  const granted = [...new Set(usernames || [])];
  const chips = granted.length
    ? granted.map(aclChipHtml).join("")
    : `<span class="muted ima-acl-none">仅管理员</span>`;
  return `<div class="ima-acl-picker${compact ? " is-compact" : ""}" data-count="${granted.length}">
    <input type="search" class="form-control ima-acl-search" placeholder="搜索并添加用户" role="combobox" aria-expanded="false" aria-autocomplete="list" aria-label="搜索并添加用户" aria-controls="${listId}" autocomplete="off" oninput="filterAclSuggest(this)" onkeydown="onAclSearchKey(event)" onfocus="filterAclSuggest(this)">
    <div id="${listId}" class="ima-acl-suggest" hidden role="listbox"></div>
    <p class="muted ima-acl-empty" hidden>没有匹配的用户</p>
    <div class="ima-acl-chips">${chips}</div>
    <button type="button" class="ima-acl-more" onclick="toggleImaAclExpanded(this)" hidden></button>
    <p class="muted ima-acl-status" aria-live="polite">${granted.length ? `${granted.length} 人可看` : "仅管理员"}</p>
  </div>`;
}

function aclSuggestItems(list) {
  return [...(list?.querySelectorAll("[data-acl-add]") || [])];
}

function setAclActive(list, index) {
  const items = aclSuggestItems(list);
  const input = list?.closest(".ima-acl-picker")?.querySelector(".ima-acl-search");
  items.forEach((el, i) => {
    const on = i === index;
    el.classList.toggle("is-on", on);
    el.setAttribute("aria-selected", String(on));
  });
  const active = items[index];
  if (input) input.setAttribute("aria-activedescendant", active?.id || "");
  active?.scrollIntoView({ block: "nearest" });
}

function filterAclSuggest(input) {
  const picker = input.closest(".ima-acl-picker");
  const list = picker?.querySelector(".ima-acl-suggest");
  const empty = picker?.querySelector(".ima-acl-empty");
  if (!picker || !list) return;
  const needle = input.value.trim().toLowerCase();
  const granted = new Set(aclGrantedNames(picker));
  const close = () => {
    list.hidden = true;
    list.innerHTML = "";
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  };
  // ponytail: 空查询展示前 8 个候选（可浏览），有输入再按子串过滤
  const hits = (_aclCandidateUsers || [])
    .map((u) => String(u.username || ""))
    .filter((name) => name && !granted.has(name) && (!needle || name.toLowerCase().includes(needle)))
    .slice(0, needle ? 50 : 8);
  if (!hits.length) {
    close();
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;
  const listId = list.id || "ima-acl-list";
  list.hidden = false;
  input.setAttribute("aria-expanded", "true");
  list.innerHTML = hits.map((name, i) =>
    `<button type="button" class="ima-acl-suggest-item" role="option" id="${listId}-opt-${i}" data-acl-add="${escapeHtml(name)}" aria-selected="false">${escapeHtml(name)}</button>`
  ).join("");
  setAclActive(list, 0);
}

function onAclSearchKey(event) {
  const input = event.target;
  const picker = input.closest(".ima-acl-picker");
  const list = picker?.querySelector(".ima-acl-suggest");
  if (event.key === "Escape") {
    event.preventDefault();
    input.value = "";
    filterAclSuggest(input);
    return;
  }
  const items = aclSuggestItems(list);
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    if (!items.length) return;
    event.preventDefault();
    const cur = items.findIndex((el) => el.classList.contains("is-on"));
    const next = event.key === "ArrowDown"
      ? Math.min(items.length - 1, (cur < 0 ? -1 : cur) + 1)
      : Math.max(0, (cur < 0 ? items.length : cur) - 1);
    setAclActive(list, next);
    return;
  }
  if (event.key !== "Enter") return;
  event.preventDefault();
  const active = items.find((el) => el.classList.contains("is-on")) || items[0];
  if (active) addAclUser(active.getAttribute("data-acl-add"), picker);
}

async function saveImaGroupAcl(groupId, usernames) {
  const r = await api(`/api/admin/ima-collector/groups/${encodeURIComponent(groupId)}/acl`, {
    method: "PUT",
    body: JSON.stringify({ usernames }),
  });
  return r.acl_usernames || usernames;
}

function applyAclNamesToPicker(picker, names) {
  const chips = picker.querySelector(".ima-acl-chips");
  const status = picker.querySelector(".ima-acl-status");
  if (chips) {
    chips.innerHTML = names.length
      ? names.map(aclChipHtml).join("")
      : `<span class="muted ima-acl-none">仅管理员</span>`;
  }
  if (status) status.textContent = names.length ? `${names.length} 人可看` : "仅管理员";
  syncImaAclMoreButton(picker, names.length);
}

function syncImaAclMoreButton(picker, count) {
  const button = picker?.querySelector(".ima-acl-more");
  if (!button) return;
  picker.dataset.count = String(count);
  button.hidden = count <= 6;
  const expanded = picker.classList.contains("is-expanded");
  button.textContent = expanded ? "收起" : `展开全部 ${count} 人`;
  button.setAttribute("aria-expanded", String(expanded));
}

function toggleImaAclExpanded(button) {
  const picker = button?.closest(".ima-acl-picker");
  if (!picker) return;
  picker.classList.toggle("is-expanded");
  syncImaAclMoreButton(picker, Number(picker.dataset.count || 0));
}

function rememberAclOnModel(groupId, names) {
  const group = imaMountGroup(groupId);
  if (group) group.acl_usernames = names;
  const lib = ((_localLibsLast && _localLibsLast.libraries) || [])
    .find((item) => `local-${item.slug}` === groupId);
  if (!lib) return;
  lib.acl_usernames = names;
  const el = document.querySelector(`.ima-source-block[data-slug="${lib.slug}"]`);
  const line = el?.querySelector(".section-meta");
  if (!line) return;
  const n = names.length;
  line.innerHTML = line.innerHTML.replace(
    /· (权限 \d+ 人|仅管理员)\s*$/,
    `· ${n ? `权限 ${n} 人` : "仅管理员"}`,
  );
}

async function addAclUser(name, picker) {
  if (!name || !picker || picker.dataset.busy) return;
  const groupId = picker.dataset.groupId;
  if (!groupId) return;
  const current = aclGrantedNames(picker);
  if (current.includes(name)) return;
  picker.dataset.busy = "1";
  try {
    const saved = await saveImaGroupAcl(groupId, [...current, name]);
    rememberAclOnModel(groupId, saved);
    applyAclNamesToPicker(picker, saved);
    const search = picker.querySelector(".ima-acl-search");
    if (search) {
      search.value = "";
      filterAclSuggest(search);
      search.focus();
    }
    flash("权限已保存");
  } catch (err) {
    flash("保存失败: " + err.message, "error");
  } finally {
    delete picker.dataset.busy;
  }
}

async function removeAclUser(name, picker) {
  if (!name || !picker || picker.dataset.busy) return;
  const groupId = picker.dataset.groupId;
  if (!groupId) return;
  const current = aclGrantedNames(picker);
  if (!current.includes(name)) return;
  if (current.length === 1 && !confirm("将只剩管理员可看，确定？")) return;
  picker.dataset.busy = "1";
  try {
    const saved = await saveImaGroupAcl(groupId, current.filter((item) => item !== name));
    rememberAclOnModel(groupId, saved);
    applyAclNamesToPicker(picker, saved);
    const search = picker.querySelector(".ima-acl-search");
    if (search?.value) filterAclSuggest(search);
    flash("权限已保存");
  } catch (err) {
    flash("保存失败: " + err.message, "error");
  } finally {
    delete picker.dataset.busy;
  }
}

async function renderImaGroupAcl() {
  const slot = $("#ima-group-acl");
  if (!slot) return;
  const group = imaMountGroup(imaMountState.selectedGroupId);
  if (!group) {
    slot.innerHTML = '<p class="muted">先选择一个知识库</p>';
    return;
  }
  const seq = ++_imaAclRenderSeq;
  const groupId = String(group.id);
  slot.innerHTML = '<p class="muted">加载用户…</p>';
  try {
    await fetchAclCandidateUsers();
    if (seq !== _imaAclRenderSeq || String(imaMountState.selectedGroupId) !== groupId) return;
    slot.innerHTML = aclPickerHtml(group.acl_usernames || [], "ima-acl-list", /* compact */ true);
    const picker = slot.querySelector(".ima-acl-picker");
    if (picker) {
      picker.dataset.groupId = groupId;
      syncImaAclMoreButton(picker, (group.acl_usernames || []).length);
    }
  } catch (err) {
    if (seq !== _imaAclRenderSeq) return;
    slot.innerHTML = `<p class="muted">用户列表加载失败：${escapeHtml(err.message)}</p>
      <button type="button" class="btn-ghost" onclick="retryImaGroupAcl()">重试</button>`;
  }
}

function toggleImaFolderExpand(button) {
  const groupId = button?.dataset.groupId || "";
  const folderId = button?.dataset.folderId || "";
  if (!groupId || !folderId) return;
  const focus = imaFocusSnapshot(button);
  const key = imaMountCacheKey(groupId, folderId);
  const opening = !imaMountState.expanded.has(key);
  if (opening) imaMountState.expanded.add(key);
  else imaMountState.expanded.delete(key);
  renderImaFolderTree(imaMountState.selectedGroupId);
  imaRestoreFocus(focus);
  if (opening && !imaMountState.folders.has(key)) loadImaFolderChildren(groupId, folderId);
}

function toggleImaFolder(input) {
  const groupId = input?.dataset.groupId || "";
  const folderId = input?.dataset.folderId || "";
  if (!groupId || !folderId || input.disabled) return;
  const focus = imaFocusSnapshot(input);
  const selected = imaMountDraft(groupId);
  const group = imaMountGroup(groupId);
  if (input.checked) {
    if (folderId === String(group?.root_folder_id || "")) {
      selected.clear();
    } else {
      selected.delete(folderId);
      for (const selectedId of [...selected]) {
        const seen = new Set();
        let parentId = imaMountState.parents.get(imaMountCacheKey(groupId, selectedId)) || "";
        while (parentId && !seen.has(parentId)) {
          if (parentId === folderId) selected.delete(selectedId);
          seen.add(parentId);
          parentId = imaMountState.parents.get(imaMountCacheKey(groupId, parentId)) || "";
        }
      }
    }
    selected.add(folderId);
  } else {
    selected.delete(folderId);
  }
  imaMountState.revision += 1;
  imaMountState.collectorRevision += 1;
  imaMountState.dirty = true;
  renderImaCollectorDirtyState();
  const draft = rememberImaCollectorDraft();
  if (imaMountState.saveOwner) imaMountState.saveOwner.liveSnapshot = draft;
  renderImaMountGroups();
  imaRestoreFocus(focus);
}

async function loadImaFolderChildren(groupId, parentId, force = false) {
  const key = imaMountCacheKey(groupId, parentId);
  if (!force && imaMountState.folders.has(key)) return;
  if (!force && imaMountState.loading.has(key)) return;
  const focus = imaFocusSnapshot();
  const request = { generation: imaMountState.generation, id: ++imaMountState.requestSeq };
  if (force) imaMountState.folders.delete(key);
  imaMountState.errors.delete(key);
  imaMountState.loading.add(key);
  imaMountState.folderRequests.set(key, request);
  if (String(imaMountState.selectedGroupId) === String(groupId)) {
    renderImaFolderTree(groupId);
    imaRestoreFocus(focus);
  }
  try {
    const path = `/api/admin/ima-collector/groups/${encodeURIComponent(groupId)}/folders?parent_id=${encodeURIComponent(parentId)}`;
    const data = await api(path);
    const current = request.generation === imaMountState.generation
      && imaMountState.folderRequests.get(key) === request;
    if (!current) return;
    const items = Array.isArray(data.items) ? data.items : [];
    imaMountState.folders.set(key, items);
    items.forEach((item) => {
      if (item?.id) imaMountState.parents.set(imaMountCacheKey(groupId, String(item.id)), String(item.parent_id || parentId));
    });
    normalizeImaMountDraft(groupId);
  } catch (err) {
    const current = request.generation === imaMountState.generation
      && imaMountState.folderRequests.get(key) === request;
    if (current) imaMountState.errors.set(key, imaSafeError(err.message || "文件夹加载失败"));
  } finally {
    const current = request.generation === imaMountState.generation
      && imaMountState.folderRequests.get(key) === request;
    if (!current) return;
    imaMountState.folderRequests.delete(key);
    imaMountState.loading.delete(key);
    if (String(imaMountState.selectedGroupId) === String(groupId)) {
      renderImaFolderTree(groupId);
      imaRestoreFocus(focus);
    }
  }
}

function retryImaFolderLoad(button) {
  loadImaFolderChildren(button?.dataset.groupId || "", button?.dataset.parentId || "", true);
}

async function discoverImaGroups() {
  if (imaMountState.discoveryBusy) return;
  const routeSeq = routeRenderSeq;
  const generation = imaMountState.generation;
  const discoverySeq = ++imaMountState.discoverySeq;
  const request = { generation, routeSeq, seq: discoverySeq };
  imaMountState.discoveryOwner = request;
  imaMountState.discoveryBusy = true;
  const button = $("#ima-discover-btn");
  const status = $("#ima-group-discovery-status");
  if (button) button.disabled = true;
  if (status) status.textContent = "正在发现共享知识库…";
  try {
    const result = await api("/api/admin/ima-collector/discover", { method: "POST" });
    if (generation !== imaMountState.generation
      || imaMountState.discoverySeq !== discoverySeq
      || imaMountState.discoveryOwner !== request
      || !routeStillActive(routeSeq)) return;
    if (result.ok && result.config) {
      initImaMountState(result.config.groups, true);
      imaMountState.discoveryOwner = request;
      imaMountState.discoveryBusy = true;
      renderImaMountGroups();
      renderImaGroupAcl();
      const currentStatus = $("#ima-group-discovery-status");
      if (currentStatus) currentStatus.innerHTML = imaGroupDiscoveryStatusText(result);
    } else {
      const error = result.discovery?.error || "自动发现失败";
      const currentStatus = $("#ima-group-discovery-status");
      if (currentStatus) currentStatus.innerHTML = `自动发现失败：${escapeHtml(imaSafeError(error))}（已保留上次结果）`;
    }
  } catch (err) {
    if (generation === imaMountState.generation
      && imaMountState.discoverySeq === discoverySeq
      && imaMountState.discoveryOwner === request
      && routeStillActive(routeSeq)) {
      const currentStatus = $("#ima-group-discovery-status");
      if (currentStatus) currentStatus.innerHTML = `自动发现失败：${escapeHtml(imaSafeError(err.message || "请求失败"))}（已保留上次结果）`;
    }
  } finally {
    if (imaMountState.discoveryOwner !== request || !routeStillActive(routeSeq)) return;
    imaMountState.discoveryBusy = false;
    imaMountState.discoveryOwner = null;
    const currentButton = $("#ima-discover-btn");
    if (currentButton && document.body.contains(currentButton)) currentButton.disabled = false;
  }
}

function readImaMountGroups() {
  return imaMountState.groups.map((group) => {
    const folderIds = [...imaMountDraft(String(group.id))];
    return {
      id: String(group.id || "") || null,
      name: String(group.name || "").trim(),
      knowledge_base_id: String(group.knowledge_base_id || "").trim(),
      root_folder_id: String(group.root_folder_id || "").trim(),
      folder_ids: folderIds,
      enabled: folderIds.length > 0,
      interval_seconds: imaGroupIntervalSeconds(group),
    };
  });
}

function imaCollectorFormSnapshot() {
  return {
    uid: imaCollectorPureCache.uid || "",
    knowledge_base_id: imaCollectorPureCache.knowledge_base_id || "",
    root_folder_id: imaCollectorPureCache.root_folder_id || "",
    interval_seconds: Number(imaCollectorPureCache.interval_seconds || 3600),
    groups: readImaMountGroups(),
    refresh_token: String(imaMountState.collectorDraft?.refresh_token || ""),
  };
}

function imaCollectorFormRevision(snapshot) {
  return JSON.stringify(snapshot);
}

function rememberImaCollectorDraft(snapshot = imaCollectorFormSnapshot()) {
  imaMountState.collectorDraft = snapshot;
  imaMountState.collectorDraftRevision = imaCollectorFormRevision(snapshot);
  imaMountState.collectorDirty = true;
  return snapshot;
}

function clearImaCollectorDraft(revision) {
  if (imaMountState.collectorDraftRevision !== revision) return;
  imaMountState.collectorDraft = null;
  imaMountState.collectorDraftRevision = "";
  imaMountState.collectorDirty = false;
  if (imaMountState.collectorConfirmedRevision === revision) {
    imaMountState.collectorConfirmedRevision = "";
    imaMountState.collectorConfirmedLiveRevision = -1;
    imaMountState.collectorConfirmedMountRevision = -1;
  }
}

function imaCollectorDraftChanged(event) {
  const target = event.target;
  if (!target?.closest?.(".ima-interval-seg")) return;
  if (event.type === "click") return;
  const snapshot = rememberImaCollectorDraft();
  imaMountState.collectorRevision += 1;
  if (imaMountState.saveOwner) imaMountState.saveOwner.liveSnapshot = snapshot;
}

document.addEventListener("input", imaCollectorDraftChanged);
document.addEventListener("change", imaCollectorDraftChanged);

function restoreImaCollectorOwnerToken(owner, seq, draft = null) {
  if (owner && owner !== imaMountState.saveOwner) return;
  const draftRevision = imaMountState.collectorDraftRevision;
  if (draftRevision === imaMountState.collectorConfirmedRevision
    && imaMountState.collectorRevision === imaMountState.collectorConfirmedLiveRevision) return;
  const pendingToken = owner?.liveSnapshot?.refresh_token || owner?.snapshot?.refresh_token || draft?.refresh_token;
  if (!pendingToken) return;
  const tokenInput = $("#ima-pure-token");
  if (tokenInput && !tokenInput.value) tokenInput.value = pendingToken;
}

function imaSafeError(value) {
  let text = String(value ?? "").split(/\r?\n/, 1)[0].slice(0, 240);
  text = text.replace(/https?:\/\/\S+/gi, "<url>");
  text = text.replace(/\bBearer\s+\S+/gi, "Bearer <redacted>");
  text = text.replace(/(^|[?&\s])((?:token|refresh_token|authorization|sign|q-sign)\b(?:\s*[=:]\s*|\s+))[^\s&]+/gi, "$1$2<redacted>");
  return text;
}

function imaGroupDiscoveryStatusText(status) {
  const result = status?.last_result || {};
  const discovery = status?.discovery || {};
  const discoveryError = String(discovery.error || result.discovery_error || "").trim();
  if (discoveryError) {
    const safeError = imaSafeError(discoveryError);
    return `自动发现失败：${escapeHtml(safeError)}（已保留上次结果）`;
  }
  const groups = Array.isArray(status?.config?.groups) ? status.config.groups : [];
  if (!groups.length) {
    return discovery.status === "ok" ? "未发现可用共享知识库" : "尚未发现共享知识库";
  }
  const mounted = groups.filter((group) => Array.isArray(group.folder_ids) && group.folder_ids.length).length;
  const synced = Number.isFinite(Number(result.succeeded_groups))
    ? ` · 最近同步 ${Number(result.succeeded_groups)} 个知识库`
    : " · 等待同步";
  return `已发现 ${groups.length} 个知识库 · 已挂载 ${mounted} 个${synced}`;
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

function imaCollectorHasUnsaved() {
  return !!(imaMountState.dirty || imaMountState.collectorDirty);
}

function switchKnowledgeSettingsTab(tab) {
  if (tab === "cicc") tab = "local"; // 旧页签记忆迁移：中金已并入本地库
  const allowed = ["collect", "zsxq", "storage", "local", "feishu"];
  const next = allowed.includes(tab) ? tab : "collect";
  // ponytail: 页签级守卫只拦采集未保存（ACL/cookie/开关均为即时生效，无需拦）
  const current = document.querySelector(".ks-tab.is-on")?.dataset.tab || "collect";
  if (next !== current && current === "collect" && imaCollectorHasUnsaved()
    && !confirm("采集配置有未保存的修改，切换页签将保留草稿。继续吗？")) return;
  if (next === "local") {
    loadLocalLibraries();
    loadCiccStatus();
    startCiccPoll();
  } else {
    stopCiccPoll();
  }
  if (next === "storage") loadStorageHealth();
  if (next === "feishu") loadFeishuDocumentSources();
  try { sessionStorage.setItem(KS_TAB_KEY, next); } catch { /* ignore */ }
  // ponytail: roving tabindex + aria-selected，方向键按 tablist 惯例切换
  document.querySelectorAll(".ks-tab").forEach((btn) => {
    const on = btn.dataset.tab === next;
    btn.classList.toggle("is-on", on);
    btn.setAttribute("aria-selected", String(on));
    btn.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll(".ks-panel").forEach((panel) => {
    panel.classList.toggle("is-on", panel.dataset.panel === next);
  });
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


async function loadAdminKnowledge(seq = _adminRenderSeq, authoritativeImaStatus = null) {
  if (!routeStillActive(seq)) return false;
  const generation = imaMountState.generation;
  const pendingOwner = imaMountState.saveOwner;
  if (pendingOwner && !pendingOwner.putCompleted && $("#ima-mount-layout")) {
    pendingOwner.liveSnapshot = imaCollectorFormSnapshot();
    rememberImaCollectorDraft(pendingOwner.liveSnapshot);
  }
  const statsLoadSeq = ++_adminStatsLoadSeq;
  let s;
  let statsLoadError = null;
  try {
    const stats = await api("/api/stats");
    if (!routeStillActive(seq) || statsLoadSeq !== _adminStatsLoadSeq
      || generation !== imaMountState.generation) return false;
    s = authoritativeImaStatus ? { ...stats, ima_collector: authoritativeImaStatus } : stats;
    _lastAdminStatsSnapshot = s;
  } catch (err) {
    if (!routeStillActive(seq) || statsLoadSeq !== _adminStatsLoadSeq
      || generation !== imaMountState.generation) return false;
    const message = `加载失败: ${err.message || "请求失败"}`;
    const fallbackStats = _lastAdminStatsSnapshot;
    if (fallbackStats && authoritativeImaStatus) {
      s = { ...fallbackStats, ima_collector: authoritativeImaStatus };
      statsLoadError = message;
    } else {
      const retry = `<div><button type="button" class="btn-normal" onclick="loadAdminKnowledge(${seq})">重试</button></div>`;
      const body = $("#admin-body");
      if (body) body.innerHTML = emptyState(message, retry);
      return false;
    }
  }
  if (!routeStillActive(seq) || statsLoadSeq !== _adminStatsLoadSeq
    || generation !== imaMountState.generation) return false;
  stopStatsTimer();
  const owner = imaMountState.saveOwner;
  const ownerIsCurrent = owner && owner === pendingOwner;
  const ownerLiveSnapshot = ownerIsCurrent ? owner.liveSnapshot : null;
  const ownerHasNewerEdits = !!ownerLiveSnapshot
    && imaCollectorFormRevision(ownerLiveSnapshot) !== owner.formRevision;
  const ownerSnapshot = ownerIsCurrent
    ? (owner.putCompleted
      ? (ownerHasNewerEdits ? ownerLiveSnapshot : null)
      : (ownerLiveSnapshot || owner.snapshot))
    : null;
  const pendingCollectorDraft = imaMountState.collectorDraft;
  const confirmedCollectorDraft = pendingCollectorDraft
    && imaMountState.collectorDraftRevision === imaMountState.collectorConfirmedRevision
    && imaMountState.collectorRevision === imaMountState.collectorConfirmedLiveRevision
    && imaMountState.revision === imaMountState.collectorConfirmedMountRevision;
  const preserveMountDraft = imaMountState.dirty
    && !confirmedCollectorDraft
    && !(ownerIsCurrent && owner.putCompleted && !ownerHasNewerEdits);
  const mountRevisionChangedDuringSave = ownerIsCurrent
    && imaMountState.revision !== owner.mountRevision;
  const preserveMountDraftForReload = preserveMountDraft || mountRevisionChangedDuringSave;
  const imaCollector = s.ima_collector || {};
  const pure = imaCollector.config || {};
  const collectorDraft = confirmedCollectorDraft ? null
    : (ownerSnapshot || (ownerIsCurrent && owner.putCompleted ? null : pendingCollectorDraft));
  const collector = collectorDraft || pure;
  const collectorGroups = collectorDraft?.groups || pure.groups || [];
  imaCollectorPureCache = {
    uid: collector.uid || "",
    interval_seconds: Number(collector.interval_seconds || 3600),
    knowledge_base_id: collector.knowledge_base_id || "",
    root_folder_id: collector.root_folder_id || "",
  };
  const zq = s.zsxq_cookie || {};
  const zc = s.zsxq_cache || { files: 0, bytes: 0 };
  const zcSize = fmtCacheBytes(zc.bytes);
  setPageTitle("研报库设置");
  $("#admin-body").innerHTML = `
    <div id="stats-poll-error"></div>
    <div class="knowledge-settings">
      <div class="ks-tabs" role="tablist" aria-label="研报库设置页签" onkeydown="onKnowledgeTabsKey(event)">
        <button type="button" role="tab" class="ks-tab is-on" data-tab="collect" aria-selected="true" aria-controls="ks-panel-collect" id="ks-tab-collect" onclick="switchKnowledgeSettingsTab(this.dataset.tab)">采集</button>
        <button type="button" role="tab" class="ks-tab" data-tab="zsxq" aria-selected="false" aria-controls="ks-panel-zsxq" id="ks-tab-zsxq" tabindex="-1" onclick="switchKnowledgeSettingsTab(this.dataset.tab)">星球</button>
        <button type="button" role="tab" class="ks-tab" data-tab="storage" aria-selected="false" aria-controls="ks-panel-storage" id="ks-tab-storage" tabindex="-1" onclick="switchKnowledgeSettingsTab(this.dataset.tab)">存储</button>
        <button type="button" role="tab" class="ks-tab" data-tab="local" aria-selected="false" aria-controls="ks-panel-local" id="ks-tab-local" tabindex="-1" onclick="switchKnowledgeSettingsTab(this.dataset.tab)">本地库</button>
        <button type="button" role="tab" class="ks-tab" data-tab="feishu" aria-selected="false" aria-controls="ks-panel-feishu" id="ks-tab-feishu" tabindex="-1" onclick="switchKnowledgeSettingsTab(this.dataset.tab)">飞书文档</button>
      </div>
      <section class="section-panel ks-panel is-on" data-panel="collect" role="tabpanel" id="ks-panel-collect" aria-labelledby="ks-tab-collect">
        <header class="section-head"><div><h2 class="section-title">IMA 文档采集</h2>
        <p class="section-meta">勾选文件夹后同步其中新增 PDF。父目录包含以后新建的子目录。</p></div></header>
        <div class="cfg-stack ima-collector-stack">
          <div class="cfg-group ima-groups-block">
            <div class="ima-groups-head">
              <div>
                <p class="cfg-group-title">共享知识库与文件夹</p>
                <span id="ima-group-discovery-status" class="muted" aria-live="polite">${imaGroupDiscoveryStatusText(imaCollector)}</span>
              </div>
              <div class="toolbar ima-groups-toolbar">
                <button type="button" class="btn-ghost" id="ima-discover-btn" onclick="discoverImaGroups()" aria-label="重新发现共享知识库">${REFRESH_ICON}<span>重新发现</span></button>
              </div>
            </div>
            <div class="ima-mount-layout" id="ima-mount-layout">
              <aside class="ima-mount-rail" aria-labelledby="ima-kb-pane-title">
                <header class="ima-mount-pane-head"><strong id="ima-kb-pane-title">知识库</strong><span id="ima-kb-count" class="muted"></span></header>
                <select id="ima-kb-select" class="form-control ima-kb-select" aria-label="选择知识库" onchange="selectImaMountGroup(this.value)"></select>
                <div id="ima-kb-list" class="ima-kb-list" role="listbox" aria-label="共享知识库"></div>
              </aside>
              <section class="ima-mount-detail" aria-labelledby="ima-selected-group-name">
                <header class="ima-selected-head">
                  <div><strong id="ima-selected-group-name">选择知识库</strong><span id="ima-selected-group-state" class="muted">${imaCollectorStatusText(imaCollector)}</span></div>
                  <button type="button" class="btn-ghost" id="ima-sync-btn" onclick="triggerImaCollector()" aria-label="同步当前库">${REFRESH_ICON}<span>同步当前库</span></button>
                </header>
                <section class="ima-detail-section ima-frequency-section">
                  <div><h3>同步频率</h3><p class="section-meta">修改后需要保存。</p></div>
                  <div id="ima-selected-interval" class="ima-selected-interval"></div>
                </section>
                <section class="ima-detail-section" id="ima-group-acl-block">
                  <header><h3>查看权限</h3><p class="section-meta">添加或移除即时生效；管理员始终可看。</p></header>
                  <div id="ima-group-acl"><p class="muted">加载中…</p></div>
                </section>
                <section class="ima-detail-section ima-folder-section">
                  <button type="button" class="ima-folder-panel-toggle" id="ima-folder-panel-toggle"
                    aria-expanded="false" aria-controls="ima-folder-panel" onclick="toggleImaFolderPanel(this)">
                    <span><strong>采集文件夹</strong><span id="ima-folder-summary" class="muted">未选择文件夹</span></span>
                    <span aria-hidden="true">›</span>
                  </button>
                  <div id="ima-folder-panel" hidden>
                    <header class="ima-mount-pane-head"><strong id="ima-folder-title">选择知识库</strong><span id="ima-folder-count" class="muted"></span></header>
                    <div id="ima-folder-tree" class="ima-folder-tree" role="tree" aria-label="知识库文件夹" aria-live="polite"></div>
                  </div>
                </section>
              </section>
            </div>
          </div>
        </div>
        <div class="ima-collector-runtime">
          <div id="ima-sync-progress">${imaCollectorProgressHtml(imaCollector)}</div>
          <span id="ima-collector-status" class="muted">${imaCollectorStatusText(imaCollector)}</span>
        </div>
        <div class="ima-collector-savebar" id="ima-collector-savebar" hidden>
          <span class="ima-unsaved-status"><span aria-hidden="true"></span>有未保存的采集配置修改</span>
          <div class="toolbar">
            <button type="button" class="btn-ghost" id="ima-collector-discard" onclick="discardImaCollectorChanges()">放弃修改</button>
            <button type="button" class="btn-normal" id="ima-collector-save"${imaMountState.saveOwner ? " disabled" : ""} onclick="saveImaCollector()">保存采集配置</button>
          </div>
        </div>
      </section>
      <section class="section-panel ks-panel" data-panel="feishu" role="tabpanel" id="ks-panel-feishu" aria-labelledby="ks-tab-feishu">
        <header class="section-head"><div><h2 class="section-title">飞书文档</h2>
        <p class="section-meta">订阅私有 Wiki 或 Docx，按文档 revision 自动更新为时间线。移除只撤下阅读入口，历史归档永久保留。</p></div></header>
        <form class="feishu-source-add" onsubmit="event.preventDefault();addFeishuDocumentSource()">
          <label for="feishu-document-url" class="sr-only">飞书文档链接</label>
          <input id="feishu-document-url" class="form-control" type="url" inputmode="url" placeholder="https://example.feishu.cn/wiki/... 或 /docx/..." autocomplete="off" oninput="queueFeishuDocumentPreview(this.value)">
          <button type="submit" class="btn-normal" id="feishu-document-add">添加来源</button>
          <div id="feishu-document-preview" class="feishu-document-preview" aria-live="polite"></div>
        </form>
        <div id="feishu-documents-body"><div class="admin-skeleton" aria-hidden="true"></div></div>
      </section>
      <section class="section-panel ks-panel" data-panel="zsxq" role="tabpanel" id="ks-panel-zsxq" aria-labelledby="ks-tab-zsxq">
      <header class="section-head"><div><h2 class="section-title">知识星球</h2>
      <p class="section-meta">Cookie 与抓取分开保存，互不覆盖。</p></div></header>
      <div class="ima-source-stack">
      <div class="ima-source-block">
        <header class="ima-source-block-head"><div><h3 class="ima-source-title">Cookie</h3>
        <p class="section-meta">${cookieUpdatedLabel(zq)}${zq.preview ? ` · 预览 ${escapeHtml(zq.preview)}` : ""}。登录 wx.zsxq.com 复制整串（含 zsxq_access_token）。</p></div></header>
        <label class="field-label" for="zq-cookie">知识星球 Cookie</label>
        <textarea id="zq-cookie" class="form-control cookie-paste" rows="3" placeholder="zsxq_access_token=..."></textarea>
        <div class="ima-credential-actions toolbar">
          <button type="button" class="btn-normal" onclick="saveZsxqCookie()">保存知识星球 Cookie</button>
          <button type="button" class="btn-ghost" onclick="pasteCookieField('zq-cookie')">从剪贴板填入</button>
          ${zq.set && !zq.from_env ? `<button type="button" class="btn-ghost danger" onclick="clearSavedCookie('zsxq','知识星球')" aria-label="清除知识星球 Cookie">清除</button>` : ""}
        </div>
      </div>
      <div class="ima-source-block">
        <header class="ima-source-block-head"><div><h3 class="ima-source-title">抓取</h3>
        <p class="section-meta">日常只开关评论和预缓存；翻页、间隔、App 通道在高级里。</p></div></header>
        <div class="cfg-group cfg-group--zsxq">
          <div class="cfg-fields">
            <label class="cfg-field cfg-check" title="新帖自动抓评论入库（可一并推送）；旧帖不动">
              <input id="pc-zq-comments" type="checkbox" ${s.polling_config.zsxq_fetch_comments ? "checked" : ""}>
              <span class="cfg-flag-text">
                <span>抓取评论</span>
                <span class="cfg-check-desc">新主题的评论在抓帖时一并入库</span>
              </span>
            </label>
            <label class="cfg-field cfg-check" title="抓到新帖时就把 PDF 拉到本地；默认关闭，点开再下，省日限">
              <input id="pc-zq-prefetch" type="checkbox" ${s.polling_config.zsxq_prefetch_files ? "checked" : ""}>
              <span class="cfg-flag-text">
                <span>抓取时预缓存附件</span>
                <span class="cfg-check-desc">打开后新帖 PDF 会立刻落到本地，费配额；默认点开再下</span>
              </span>
            </label>
          </div>
          <details class="ks-advanced">
            <summary class="cfg-group-title">高级（翻页、间隔、App 通道）</summary>
            <div class="cfg-fields">
              <label class="cfg-field" title="每星球每轮最多翻几页，每页 20 条">
                <span>单轮翻页<span class="cfg-unit">页</span></span>
                <input id="pc-zq-pages" type="number" class="form-control" min="1" max="20" value="${s.polling_config.zsxq_max_pages ?? 3}">
              </label>
              <label class="cfg-field" title="列表/详情请求间隔，过短容易触发 1059">
                <span>请求间隔<span class="cfg-unit">秒</span></span>
                <input id="pc-zq-delay" type="number" class="form-control" min="0.2" max="10" step="0.1" value="${s.polling_config.zsxq_fetch_delay_seconds ?? 1}">
              </label>
              <label class="cfg-field" title="附件 download_url 请求间隔，过短容易撞日限">
                <span>附件间隔<span class="cfg-unit">秒</span></span>
                <input id="pc-zq-file-delay" type="number" class="form-control" min="0.2" max="10" step="0.1" value="${s.polling_config.zsxq_file_delay_seconds ?? 1}">
              </label>
              <label class="cfg-field" title="单主题评论最多翻几页（每页 20 条）">
                <span>评论翻页<span class="cfg-unit">页</span></span>
                <input id="pc-zq-comment-pages" type="number" class="form-control" min="1" max="10" value="${s.polling_config.zsxq_max_comment_pages ?? 3}">
              </label>
              <label class="cfg-field" title="每轮最多发起的评论请求数，保护限流">
                <span>评论预算<span class="cfg-unit">次/轮</span></span>
                <input id="pc-zq-comment-budget" type="number" class="form-control" min="1" max="200" value="${s.polling_config.zsxq_comment_budget ?? 30}">
              </label>
              <label class="cfg-field cfg-check" title="用 App 通道请求头（xiaomiquan UA + X-Request-Id/X-Version）代替浏览器头；默认关，等你复测日限差异确认有收益再开">
                <input id="pc-zq-app" type="checkbox" ${s.polling_config.zsxq_app_channel ? "checked" : ""}>
                <span class="cfg-flag-text">
                  <span>App 通道头</span>
                  <span class="cfg-check-desc">伪称 Android 客户端请求；与 web 通道共用账号配额</span>
                </span>
              </label>
              <label class="cfg-field cfg-field--wide" title="App 通道 UA 里的设备标识：Android 版本 + 品牌_型号，空格自动压成下划线">
                <span>设备标识<span class="cfg-unit">RELEASE BRAND_MODEL</span></span>
                <input id="pc-zq-app-device" type="text" class="form-control" maxlength="64" value="${escapeHtml(s.polling_config.zsxq_app_device ?? "16 OnePlus_PJD110")}">
              </label>
            </div>
          </details>
          <div class="cfg-foot">
            <p class="muted" id="zq-cache-stat">附件缓存 ${zcSize} / ${zc.files || 0} 个文件</p>
            <div class="toolbar">
              <button type="button" class="btn-ghost" onclick="purgeZsxqCache()">清理未引用</button>
              <button type="button" class="btn-normal" id="pc-zq-save" onclick="saveZsxqPollingConfig()">保存星球设置</button>
            </div>
          </div>
        </div>
      </div>
      </div>
    </section>
    ${imaStoragePanelHtml(imaCollector.storage)}
    <section class="section-panel ks-panel" data-panel="local" role="tabpanel" id="ks-panel-local" aria-labelledby="ks-tab-local">
      <header class="section-head"><div><h2 class="section-title">本地库</h2>
      <p class="section-meta">存储机 <code>local/&lt;slug&gt;/</code> 下的文件夹研报库；中金研报由存储机采集脚本写入 cicc-research 库。启用并授权用户后即可在研报库中阅读。</p></div></header>
      <div id="local-libs-body"><p class="muted">加载中…</p></div>
    </section>
    </div>`;
  renderStatsData(s);
  if (statsLoadError) {
    const error = $("#stats-poll-error");
    const retry = `<div><button type="button" class="btn-normal" onclick="loadAdminKnowledge(${seq})">重试</button></div>`;
    if (error) error.innerHTML = `<div class="ima-folder-state ima-folder-error" role="alert">${escapeHtml(statsLoadError)}${retry}</div>`;
  }
  if (collectorDraft) initImaMountState(collectorGroups, true);
  else initImaMountState(pure.groups || [], preserveMountDraftForReload);
  renderImaMountGroups();
  renderImaGroupAcl();
  document.querySelectorAll(".ima-interval-seg").forEach((seg) => {
    const current = imaGroupIntervalSeconds(imaMountGroup(seg.dataset.groupId));
    seg.querySelectorAll("button[data-sec]").forEach((btn) => {
      btn.classList.toggle("is-on", Number(btn.dataset.sec) === current);
    });
  });
  restoreImaCollectorOwnerToken(owner, seq, pendingCollectorDraft);
  if (confirmedCollectorDraft) {
    const confirmedRevision = imaMountState.collectorConfirmedRevision;
    const confirmedLiveRevision = imaMountState.collectorConfirmedLiveRevision;
    if (imaMountState.collectorDraftRevision === confirmedRevision
      && imaMountState.collectorRevision === confirmedLiveRevision) {
      clearImaCollectorDraft(confirmedRevision);
      imaMountState.collectorConfirmedRevision = "";
      imaMountState.collectorConfirmedLiveRevision = -1;
      imaMountState.collectorConfirmedMountRevision = -1;
      imaMountState.dirty = false;
      const tokenInput = $("#ima-pure-token");
      if (tokenInput) tokenInput.value = "";
    }
  }
  let savedTab = "collect";
  try { savedTab = sessionStorage.getItem(KS_TAB_KEY) || "collect"; } catch { /* ignore */ }
  const knowledgeQuery = routeQuery();
  if (knowledgeQuery.get("tab") === "feishu") savedTab = "feishu";
  const oauthResult = knowledgeQuery.get("oauth");
  if (oauthResult) {
    flash(oauthResult === "success" ? "飞书文档授权已更新" : "飞书文档授权失败", oauthResult === "success" ? "success" : "error");
    history.replaceState(null, "", "/admin/knowledge");
  }
  switchKnowledgeSettingsTab(savedTab);
  if (imaCollector.running) startImaProgressPoll();
  else {
    stopImaProgressPoll();
    applyImaCollectorProgress(imaCollector);
  }
  startDashboardLiveTimer();
  return true;
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
  if (!confirm(`清除「${label}」Cookie？清除后该数据源会停止抓取，直到重新保存。`)) return;
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
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

function imaCollectorStatusText(status) {
  const result = status.last_result || {};
  const config = status.config || {};
  const storage = status.storage;
  const storageMessages = {
    unavailable: "研报库存储暂不可用",
    stale: "研报库存储状态过期",
    readonly: "研报库存储当前只读",
    capacity_blocked: "研报库存储空间已达限制",
  };
  if (storageMessages[storage?.status]) return storageMessages[storage.status];
  let text;
  if (!config.refresh_token?.set) text = "未配置 Refresh Token";
  else if (status.running) text = "同步中…";
  else {
    const groups = Array.isArray(config.groups) ? config.groups : [];
    const mounted = groups.filter((group) => Array.isArray(group.folder_ids) && group.folder_ids.length).length;
    if (!mounted) text = "已连接 · 尚未挂载研报库";
    else if (status.last_finished_at) {
      const ok = Number(result.downloaded || 0);
      const failed = Number(result.failed || 0);
      text = `已归档 ${Number(status.documents || 0).toLocaleString()} 份 · 上次新增 ${ok} 份${failed ? ` · 失败 ${failed} 份` : ""}`;
    } else {
      text = `已配置 · 每 ${Math.round(Number(config.interval_seconds || 3600) / 60)} 分钟检查`;
    }
  }
  if (storage?.status === "available") {
    const used = Math.max(0, Math.min(100, Number(storage.used_percent) || 0));
    text += ` · 存储 ${used}%`;
  }
  const indexMessages = {
    rebuilding: "索引重建中",
    fallback: "索引回退",
    failed: "索引异常",
  };
  const indexStatus = status.index?.status || "ready";
  if (indexStatus !== "ready" && indexMessages[indexStatus]) {
    text += ` · ${indexMessages[indexStatus]}`;
  }
  return text;
}

async function saveImaCollector() {
  const routeSeq = routeRenderSeq;
  const saveButton = $("#ima-collector-save");
  if (imaMountState.saveOwner) return;
  if (saveButton?.disabled) return;
  const sessionGeneration = imaMountState.sessionGeneration;
  const mountRevision = imaMountState.revision;
  const collectorRevision = imaMountState.collectorRevision;
  const focusElement = document.activeElement;
  const focusId = focusElement?.id || "";
  let focusMoved = false;
  const onFocusIn = (event) => {
    if (event.target !== focusElement && event.target !== document.body) focusMoved = true;
  };
  const snapshot = imaCollectorFormSnapshot();
  rememberImaCollectorDraft(snapshot);
  const body = {
    uid: snapshot.uid,
    knowledge_base_id: snapshot.knowledge_base_id,
    root_folder_id: snapshot.root_folder_id,
    interval_seconds: snapshot.interval_seconds,
    groups: readImaMountGroups(),
  };
  const token = snapshot.refresh_token;
  if (token) body.refresh_token = token;
  const saveOwner = {
    routeSeq,
    sessionGeneration,
    mountRevision,
    collectorRevision,
    formRevision: imaCollectorFormRevision(snapshot),
    snapshot,
  };
  const onDraftChange = (event) => {
    if (imaMountState.saveOwner !== saveOwner) return;
    const target = event.target;
    if (!target?.closest?.(".ima-interval-seg") && !target.closest?.("#ima-mount-layout")) return;
    const liveSnapshot = rememberImaCollectorDraft();
    if (imaMountState.saveOwner === saveOwner) saveOwner.liveSnapshot = liveSnapshot;
  };
  imaMountState.saveOwner = saveOwner;
  if (saveButton) saveButton.disabled = true;
  document.addEventListener("input", onDraftChange);
  document.addEventListener("change", onDraftChange);
  document.addEventListener("click", onDraftChange);
  document.addEventListener("focusin", onFocusIn);
  try {
    const savedImaStatus = await api("/api/admin/ima-collector", { method: "PUT", body: JSON.stringify(body) });
    if (sessionGeneration !== imaMountState.sessionGeneration || imaMountState.saveOwner !== saveOwner) return;
    saveOwner.savedImaStatus = savedImaStatus;
    saveOwner.putCompleted = true;
    const submittedLiveRevision = saveOwner.liveSnapshot
      ? imaCollectorFormRevision(saveOwner.liveSnapshot) : saveOwner.formRevision;
    const formStillCurrent = submittedLiveRevision === saveOwner.formRevision;
    const collectorStillCurrent = imaMountState.collectorRevision === saveOwner.collectorRevision;
    const mountStillCurrent = imaMountState.revision === saveOwner.mountRevision;
    if (formStillCurrent && collectorStillCurrent && mountStillCurrent) {
      imaMountState.collectorConfirmedRevision = saveOwner.formRevision;
      imaMountState.collectorConfirmedLiveRevision = saveOwner.collectorRevision;
      imaMountState.collectorConfirmedMountRevision = saveOwner.mountRevision;
    }
    const currentSnapshot = routeStillActive(routeSeq) && isAdminSettingsPath()
      && $("#ima-mount-layout") ? imaCollectorFormSnapshot() : null;
    const currentFormRevision = currentSnapshot
      ? imaCollectorFormRevision(currentSnapshot) : submittedLiveRevision;
    if (currentSnapshot && currentFormRevision !== saveOwner.formRevision) {
      saveOwner.liveSnapshot = rememberImaCollectorDraft(currentSnapshot);
    }
    if (sessionGeneration !== imaMountState.sessionGeneration || imaMountState.saveOwner !== saveOwner) return;
    if (!routeStillActive(routeSeq) && !isAdminSettingsPath()) return;
    const statsReloadSeq = routeStillActive(routeSeq) ? routeSeq : routeRenderSeq;
    let statsReloadAccepted;
    if (statsReloadSeq === routeSeq) {
      statsReloadAccepted = await reloadAdminSettingsPage(routeSeq, savedImaStatus);
    } else {
      statsReloadAccepted = await reloadAdminSettingsPage(routeRenderSeq, savedImaStatus);
    }
    if (!statsReloadAccepted || sessionGeneration !== imaMountState.sessionGeneration
      || imaMountState.saveOwner !== saveOwner) return;
    if (!routeStillActive(statsReloadSeq) || !isAdminSettingsPath()) return;
    const reloadedSnapshot = imaCollectorFormSnapshot();
    const reloadedRevision = imaCollectorFormRevision(reloadedSnapshot);
    const liveRevision = saveOwner.liveSnapshot
      ? imaCollectorFormRevision(saveOwner.liveSnapshot) : saveOwner.formRevision;
    const formStillCurrentAfterReload = !saveOwner.liveSnapshot || reloadedRevision === liveRevision;
    const mountStillCurrentAfterReload = imaMountState.revision === saveOwner.mountRevision;
    const noNewerEditsAfterReload = formStillCurrentAfterReload && mountStillCurrentAfterReload && liveRevision === saveOwner.formRevision;
    const collectorStillCurrentAfterReload = imaMountState.collectorRevision === saveOwner.collectorRevision;
    if (noNewerEditsAfterReload) {
      if (collectorStillCurrentAfterReload) {
        clearImaCollectorDraft(saveOwner.formRevision);
        imaMountState.dirty = false;
        const tokenInput = $("#ima-pure-token");
        if (tokenInput) tokenInput.value = "";
      }
    }
    const restoreFocus = document.activeElement === focusElement || document.activeElement === document.body;
    if (!focusMoved && restoreFocus) {
      const focusTarget = document.getElementById(focusId) || document.getElementById("ima-collector-save");
      focusTarget?.focus({ preventScroll: true });
    }
    flash("IMA 文档采集配置已保存");
  } catch (err) {
    if (sessionGeneration !== imaMountState.sessionGeneration || imaMountState.saveOwner !== saveOwner) return;
    if (routeStillActive(routeSeq) && isAdminSettingsPath()) {
      flash(err.message || "保存失败", "error");
    }
  } finally {
    document.removeEventListener("input", onDraftChange);
    document.removeEventListener("change", onDraftChange);
    document.removeEventListener("click", onDraftChange);
    document.removeEventListener("focusin", onFocusIn);
    if (imaMountState.saveOwner === saveOwner) {
      imaMountState.saveOwner = null;
      if (saveButton && document.body.contains(saveButton)) saveButton.disabled = false;
      const currentSaveButton = $("#ima-collector-save");
      if (currentSaveButton) currentSaveButton.disabled = false;
    }
  }
}

function imaCollectorProgressHtml(status) {
  const p = status.progress;
  if (!status.running || !p) return "";
  if (p.phase === "listing") {
    return `<div class="ima-progress"><div class="ima-progress-label">${escapeHtml(p.group_name || "")} · 列目录 ${Number(p.listed||0)}</div><div class="ima-progress-bar"><span style="width:15%"></span></div></div>`;
  }
  const total = Math.max(1, Number(p.pending || 0));
  const done = Number(p.downloaded || 0);
  const pct = Math.max(0, Math.min(100, Math.round(done * 100 / total)));
  return `<div class="ima-progress"><div class="ima-progress-label">${escapeHtml(p.group_name || "")} · 下载 ${done} / ${Number(p.pending||0)}</div><div class="ima-progress-bar"><span style="width:${pct}%"></span></div></div>`;
}

function stopImaProgressPoll() {
  imaProgressPollSeq += 1;
  if (imaProgressTimer) {
    clearInterval(imaProgressTimer);
    imaProgressTimer = null;
  }
}

function applyImaCollectorProgress(status) {
  const progress = $("#ima-sync-progress");
  if (progress) progress.innerHTML = imaCollectorProgressHtml(status);
  const btn = $("#ima-sync-btn");
  if (btn && document.body.contains(btn)) btn.disabled = !!status?.running;
  const text = imaCollectorStatusText(status);
  const target = $("#ima-collector-status");
  if (target) target.textContent = text;
  const selected = $("#ima-selected-group-state");
  if (selected) selected.textContent = text;
}

function startImaProgressPoll() {
  stopImaProgressPoll();
  const routeSeq = routeRenderSeq;
  const pollSeq = imaProgressPollSeq;
  const tick = async () => {
    try {
      const status = await api("/api/admin/ima-collector");
      if (pollSeq !== imaProgressPollSeq || !routeStillActive(routeSeq)) return;
      applyImaCollectorProgress(status);
      if (!status.running) stopImaProgressPoll();
    } catch {
      if (pollSeq !== imaProgressPollSeq || !routeStillActive(routeSeq)) return;
    }
  };
  imaProgressTimer = setInterval(tick, 2000);
  tick();
}

async function triggerImaCollector() {
  const routeSeq = routeRenderSeq;
  const btn = $("#ima-sync-btn");
  if (btn?.disabled) return;
  const groupId = imaMountState.selectedGroupId;
  if (!groupId) {
    flash("请先选择知识库", "error");
    return;
  }
  const group = imaMountGroup(groupId);
  const mounted = Array.isArray(group?.folder_ids) && group.folder_ids.length;
  if (!mounted) {
    flash("请先挂载该知识库并保存", "error");
    return;
  }
  if (btn) btn.disabled = true;
  try {
    const result = await api("/api/admin/ima-collector/sync", { method: "POST", body: JSON.stringify({ group_id: groupId }) });
    if (!routeStillActive(routeSeq)) return;
    flash(result.status === "already_running" ? "IMA 文档同步正在进行中" : `已启动同步「${group?.name || groupId}」`);
    const status = await api("/api/admin/ima-collector");
    if (!routeStillActive(routeSeq)) return;
    const target = $("#ima-collector-status");
    if (target) target.textContent = imaCollectorStatusText(status);
    const discovery = $("#ima-group-discovery-status");
    if (discovery) discovery.innerHTML = imaGroupDiscoveryStatusText(status);
    applyImaCollectorProgress(status);
    startImaProgressPoll();
  } catch (err) {
    if (routeStillActive(routeSeq)) {
      flash(err.message || "同步启动失败", "error");
      if (btn && document.body.contains(btn)) btn.disabled = false;
    }
  } finally {
    if (routeStillActive(routeSeq)) return;
    stopImaProgressPoll();
  }
}

async function saveImaCredentials() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const cookie = $("#ima-cookie")?.value?.trim() || "";
  const cid = $("#ima-cid")?.value?.trim() || "";
  const key = $("#ima-key")?.value?.trim() || "";
  if (!cookie && !(cid && key)) {
    flash("需至少填 Cookie 或 OpenAPI 凭证（clientid + apikey）", "error");
    return;
  }
  try {
    await api("/api/admin/ima-credentials", {
      method: "POST",
      body: JSON.stringify({ cookie, openapi_clientid: cid, openapi_apikey: key }),
    });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash("IMA 凭证已保存");
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    await reloadAdminSettingsPage(routeSeq);
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    focusCookieField("ima");
  } catch (e) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(e.message || "保存失败", "error");
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

function renderThemeSwitcher() {
  const el = $("#theme-switcher");
  if (!el) return;
  const mode = themeMode();
  el.innerHTML = ["light", "dark", "auto"].map((m) => `
    <button class="theme-mode ${mode === m ? "selected" : ""}" data-mode="${m}" title="${themeLabelFor(m)}" aria-label="${themeLabelFor(m)}" aria-pressed="${mode === m}" onclick="setTheme('${m}')">${themeIconFor(m)}</button>`).join("");
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

// PWA：注册 Service Worker（HTTP 或私有模式下失败静默，不影响功能）
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
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

function retryImaGroupAcl() {
  return fetchAclCandidateUsers(true).then(renderImaGroupAcl);
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
};
Object.assign(window, INLINE_HANDLERS);

applyTheme(); // 与 index.html 防闪脚本同一逻辑，兜底 + 同步 meta theme-color
router();
