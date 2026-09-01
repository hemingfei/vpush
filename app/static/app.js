const $ = (sel) => document.querySelector(sel);

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
const APP_VERSION = "1.12.125";
const KEYWORDS_MAX_COUNT = 20;
const REPORT_WATCH_BLOCKED_TAGS = new Set([
  "中金研报", "宏观经济", "市场策略", "全球研究", "行业研究", "公司研究",
  "量化及ESG", "大宗商品", "外汇研究", "固定收益", "中金研究院", "其他",
]);
const TL_SOURCE_KEY = "timelineSource";
const PLATFORM_TABS = ["", "xueqiu", "combination", "weibo", "twitter", "zsxq"];
const STATS_TABS = ["config", "cookies", "proxies", "plaza"];
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
const GRID_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>`;
const TRENDING_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 7l-8.5 8.5-5-5L2 17"/><path d="M16 7h6v6"/></svg>`;
const BOOKMARK_ICON = `<svg class="nav-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>`;
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
  mysubsPlatform: "",
  mysubsFavorite: false,
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
let imaCollectorPureCache = {
  uid: "",
  knowledge_base_id: "",
  root_folder_id: "",
  interval_seconds: 3600,
};
let imaProgressTimer = null;
let imaProgressPollSeq = 0;

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function imgProxyUrl(url) {
  return `/api/img-proxy?url=${encodeURIComponent(url)}`;
}

function imgOnError(img) {
  // 第三方图床直连失败（大陆访问 X 图床被墙等）→ 经服务端代理转发
  if (!img || img.dataset.proxied) return;
  const src = img.getAttribute("src") || "";
  if (src.startsWith("/api/img-proxy")) return;
  img.dataset.proxied = "1";
  img.src = imgProxyUrl(src);
  img.onerror = null;
}

// ---------- 图片灯箱（点击放大原图，背景变暗，多图可左右切换） ----------
let _lightboxImages = [];
let _lightboxIndex = 0;

function openLightbox(img) {
  if (!img) return;
  // 收集当前帖子（同一 .post-images 容器）里的全部图片，支持左右切换
  const container = img.closest(".post-images");
  if (container) {
    _lightboxImages = [...container.querySelectorAll("img")]
      .map((im) => im.currentSrc || im.src || "")
      .filter(Boolean);
  } else {
    _lightboxImages = [(img.currentSrc || img.src || "")].filter(Boolean);
  }
  if (!_lightboxImages.length) return;
  _lightboxIndex = Math.max(0, _lightboxImages.indexOf(img.currentSrc || img.src || ""));
  closeLightbox(); // 防重复打开
  const overlay = document.createElement("div");
  overlay.className = "lightbox";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "查看大图");
  overlay.innerHTML = `
    <button class="lightbox-close" aria-label="关闭" onclick="event.stopPropagation();closeLightbox()">✕</button>
    <img class="lightbox-img" src="${escapeHtml(_lightboxImages[_lightboxIndex])}" alt="动态配图" onerror="imgOnError(this)">
    ${_lightboxImages.length > 1 ? `
      <button class="lightbox-nav lightbox-prev" aria-label="上一张" onclick="event.stopPropagation();lightboxStep(-1)">‹</button>
      <button class="lightbox-nav lightbox-next" aria-label="下一张" onclick="event.stopPropagation();lightboxStep(1)">›</button>
      <span class="lightbox-count">${_lightboxIndex + 1} / ${_lightboxImages.length}</span>` : ""}`;
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeLightbox();
  });
  // 移动端滑动手势：左右滑动切换图片（与「点击遮罩关闭」的 tap 区分）
  overlay.addEventListener("touchstart", lightboxTouchStart, { passive: true });
  overlay.addEventListener("touchmove", lightboxTouchMove, { passive: false });
  overlay.addEventListener("touchend", lightboxTouchEnd, { passive: true });
  document.body.appendChild(overlay);
  document.body.classList.add("lightbox-open");
  document.addEventListener("keydown", lightboxKeyHandler);
}

let _lbTouchStart = null;

function lightboxTouchStart(e) {
  // 从箭头/关闭按钮上开始的滑动不拦截（按钮有自己的事件）
  if (e.target.closest(".lightbox-nav, .lightbox-close")) return;
  _lbTouchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
}

function lightboxTouchMove(e) {
  if (!_lbTouchStart) return;
  const dx = e.touches[0].clientX - _lbTouchStart.x;
  const dy = e.touches[0].clientY - _lbTouchStart.y;
  // 水平滑动占优时拦截：阻止页面滚动，也阻止松手后合成 click（避免误关灯箱）
  if (Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) e.preventDefault();
}

function lightboxTouchEnd(e) {
  if (!_lbTouchStart) return;
  const dx = e.changedTouches[0].clientX - _lbTouchStart.x;
  const dy = e.changedTouches[0].clientY - _lbTouchStart.y;
  _lbTouchStart = null;
  if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy) * 1.5) return; // 阈值：水平 40px 且明显占优
  lightboxStep(dx < 0 ? 1 : -1);
}

function lightboxStep(dir) {
  if (_lightboxImages.length < 2) return;
  _lightboxIndex = (_lightboxIndex + dir + _lightboxImages.length) % _lightboxImages.length;
  const img = document.querySelector(".lightbox-img");
  if (!img) return;
  img.style.opacity = "0";
  setTimeout(() => {
    img.src = _lightboxImages[_lightboxIndex];
    img.style.opacity = "";
    img.onerror = imgOnError;
    const count = document.querySelector(".lightbox-count");
    if (count) count.textContent = `${_lightboxIndex + 1} / ${_lightboxImages.length}`;
  }, 120); // 与淡出过渡衔接
}

function lightboxKeyHandler(e) {
  if (e.key === "Escape") closeLightbox();
  else if (e.key === "ArrowLeft") lightboxStep(-1);
  else if (e.key === "ArrowRight") lightboxStep(1);
}

function closeLightbox() {
  const overlay = document.querySelector(".lightbox");
  if (!overlay) return;
  overlay.classList.add("closing"); // 触发淡出+轻微缩小动画
  // 动画结束后移除 DOM；reduced-motion 下 animation 被禁用（animationend 不触发），用超时兜底
  const remove = () => overlay.remove();
  overlay.addEventListener("animationend", remove, { once: true });
  setTimeout(remove, 240); // 略大于关闭动画 200ms；reduced-motion 下 animationend 不触发时兜底
  document.body.classList.remove("lightbox-open");
  document.removeEventListener("keydown", lightboxKeyHandler);
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

function clearImaPdfUrl() {
  if (_imaPdfAbort) {
    _imaPdfAbort.abort();
    _imaPdfAbort = null;
  }
  if (window._imaPdfUrl) {
    URL.revokeObjectURL(window._imaPdfUrl);
    window._imaPdfUrl = "";
  }
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
  _tlPosts.length = 0;
  _tlOffset = 0;
  _tlHasMore = true;
  _tlExpanded.clear();
  _tlLatestId = 0;
  _tlLoadedFilter = null;
  _tlSavedScrollY = 0;
  _tlPendingNew.length = 0;
  _tlPendingLatestId = 0;
  pendingBind = null;
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
    { route: "knowledge", icon: BOOK_ICON, label: "研报库" },
    { route: "home", icon: GRID_ICON, label: "订阅广场" },
    { route: "combinations", icon: TRENDING_ICON, label: "组合订阅" },
    { route: "mysubs", icon: BOOKMARK_ICON, label: "我的订阅" },
    { route: "settings", icon: GEAR_ICON, label: "推送设置" },
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
  if (e.key === "Escape" && _imaDayPicker.open) {
    e.preventDefault();
    closeImaDayPicker();
    return;
  }
  if (_imaDayPicker.open) return;
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
  if ($("#ima-report-page")) return;
  clearImaPdfUrl();
  $("#main").innerHTML = `
    <section class="section-panel ima-report-page" id="ima-report-page">
      <div id="kb-list" tabindex="-1"></div>
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
      ${(group.items || []).map(navItemHtml).join("")}
      ${(group.subs || []).map((sub) => `
        <details class="nav-sub" open>
          <summary class="nav-sub-label">${sub.label}</summary>
          ${sub.items.map(navItemHtml).join("")}
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
}

const MOBILE_NAV = [
  { route: "timeline", icon: LIST_ICON, label: "动态" },
  { route: "home", icon: GRID_ICON, label: "广场" },
  { route: "combinations", icon: TRENDING_ICON, label: "组合" },
  { route: "mysubs", icon: BOOKMARK_ICON, label: "订阅" },
  { route: "settings", icon: GEAR_ICON, label: "设置" },
];

function renderBottomNav(user) {
  const tabs = [...MOBILE_NAV];
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
let _imaListSeq = 0;
let _imaReaderSeq = 0;
let _imaPdfAbort = null;
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
  return `
    <article class="ima-doc-row" role="button" tabindex="0" data-media-id="${escapeHtml(item.media_id)}" data-group-id="${escapeHtml(item.group_id || "")}" onclick="openImaDocument(this.dataset.mediaId, this.dataset.groupId)" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();openImaDocument(this.dataset.mediaId, this.dataset.groupId)}">
      <time class="ima-report-date">${escapeHtml(day)}</time>
      <span class="ima-report-copy"><strong class="ima-report-title">${escapeHtml(imaListTitle(item.name))}</strong>${meta}</span>
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

function captureImaListSnapshot(selectedMediaId = "", selectedGroupId = "") {
  const body = $("#ima-docs-body");
  if (!body) return;
  _imaListSnapshot = {
    route: location.pathname + location.search,
    items: _imaItems.map((item) => ({ ...item, tags: [...(item.tags || [])] })),
    hasMore: !!state.imaDocumentsHasMore,
    days: [...(state.imaDocumentsDays || [])],
    tagCounts: { ..._imaTagCounts },
    documentCount: _imaDocumentCount,
    scrollTop: body.scrollTop,
    selectedKey: imaDocumentKey(selectedMediaId, selectedGroupId),
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

function selectImaDocumentGroup(value) {
  state.imaDocumentsGroup = String(value || "");
  state.imaDocumentsDay = "";
  state.imaDocumentsDays = [];
  state.imaDocumentsTag = "";
  state.imaDocumentsQuery = $("#ima-doc-q")?.value?.trim() || state.imaDocumentsQuery || "";
  replaceImaDocumentsRoute(imaDocumentsRoute(value, state.imaDocumentsQuery, "", ""));
  const seq = ++routeRenderSeq;
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
  state.imaDocumentsQuery = imaUsableSearchQuery($("#ima-doc-q")?.value || "");
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

function onImaDayPickerDocDown(event) {
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
  const name = group.name || id;
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
  const selected = String(selectedGroup || "");
  const subscribed = state.imaCatalogSubscribed || [];
  const options = [{ id: "", name: "全部研报" }, ...subscribed.map((group) => ({
    id: String(group.id || ""),
    name: group.name || group.id,
  }))];
  return `<label class="ima-report-source"><span class="sr-only">资料源</span><select id="ima-doc-source" aria-label="资料源" onchange="selectImaDocumentGroup(this.value)"><option value=""${selected ? "" : " selected"}>全部研报</option>${options.filter((group) => group.id).map((group) => `<option value="${escapeHtml(group.id)}"${group.id === selected ? " selected" : ""}>${escapeHtml(group.name)}</option>`).join("")}</select></label>`;
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
  if (!$("#ima-report-page") && !$("#ima-reader-page")) {
    $("#main").innerHTML = `<div class="admin-skeleton" aria-hidden="true"></div>`;
  }
  const catalogPromise = api("/api/ima-documents/catalog");
  const documentsPromise = mediaId || currentImaListSnapshot() ? null : api(imaDocumentsRequestPath());
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
    mountKnowledgeListShell();
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
    await renderImaDocuments(seq, { prefetched: documentsPromise });
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
    const source = $("#ima-doc-source");
    if (source) source.value = selectedGroup;
    const body = $("#ima-docs-body");
    if (body && !keepOld) body.innerHTML = imaReportSkeletonHtml();
  } else {
    _imaSearchComposing = false;
    const sourceControls = knowledgeSourceControlsHtml(selectedGroup);
    listRoot.innerHTML = `
  <header class="ima-report-head">
    <div class="ima-report-heading"><div><h2 id="ima-doc-title">最新研报</h2><p id="ima-doc-meta" class="section-meta"></p></div><button type="button" class="icon-btn" aria-label="刷新研报" title="刷新研报" onclick="refreshImaDocuments()">${REFRESH_ICON}</button></div>
    <form class="ima-report-search" onsubmit="event.preventDefault();submitImaDocumentsSearch()">
      <label class="ima-report-searchbox">${SEARCH_ICON}<input id="ima-doc-q" type="search" value="${escapeHtml(query)}" placeholder="搜标题、公司、代码、行业或资料源" aria-label="搜索研报" oninput="queueImaDocumentsSearch()" oncompositionstart="_imaSearchComposing=true" oncompositionend="_imaSearchComposing=false;queueImaDocumentsSearch()"><span id="ima-doc-day-nav-slot"></span></label>
      <div class="ima-report-filters">${sourceControls}<label class="ima-report-tag"><span class="sr-only">标签</span><select id="ima-doc-tag" aria-label="标签" onchange="selectImaDocumentsTag(this.value)" hidden><option value="">全部标签</option></select></label></div>
    </form>
    <div id="ima-doc-filter-chips" class="ima-doc-filter-chips"></div>
    <div class="ima-report-columns" aria-hidden="true"><span>日期</span><span>标题</span><span>资料源</span></div>
  </header>
  <div id="ima-docs-body" class="ima-report-body">${keepOld && oldHtml ? oldHtml : imaReportSkeletonHtml()}</div>`;
  }
  const body = $("#ima-docs-body");
  const snapshot = currentImaListSnapshot();
  if (snapshot && body) {
    const tagSelect = $("#ima-doc-tag");
    const uniqueTags = Object.keys(snapshot.tagCounts || {});
    if (tag && !uniqueTags.includes(tag)) uniqueTags.unshift(tag);
    if (tagSelect) {
      tagSelect.innerHTML = `<option value="">全部标签</option>${uniqueTags.map((value) => {
        const n = snapshot.tagCounts[value];
        return `<option value="${escapeHtml(value)}" ${value === tag ? "selected" : ""}>${escapeHtml(value)}${n ? `（${n}）` : ""}</option>`;
      }).join("")}`;
      if (uniqueTags.length || tag) tagSelect.removeAttribute("hidden");
      else tagSelect.hidden = true;
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
    if (!knowledgeMediaIdFromPath()) setPageTitle(selectedGroupName);
    const days = Array.isArray(data.days)
      ? data.days.filter(Boolean)
      : [...new Set(items.map((item) => item.day).filter(Boolean))];
    state.imaDocumentsDays = days;
    const tagSelect = $("#ima-doc-tag");
    _imaTagCounts = imaTagCountsFromData(data);
    _imaDocumentCount = Number(data.document_count) || imaTagCoverageBase(_imaTagCounts, 0);
    const uniqueTags = Array.isArray(data.tags)
      ? data.tags.filter(Boolean)
      : Object.keys(_imaTagCounts);
    if (tag && !uniqueTags.includes(tag)) uniqueTags.unshift(tag);
    if (tagSelect) {
      tagSelect.innerHTML = `<option value="">全部标签</option>${uniqueTags.map((value) => {
        const n = _imaTagCounts[value];
        return `<option value="${escapeHtml(value)}" ${value === tag ? "selected" : ""}>${escapeHtml(value)}${n ? `（${n}）` : ""}</option>`;
      }).join("")}`;
      if (uniqueTags.length || tag) tagSelect.removeAttribute("hidden");
      else tagSelect.hidden = true;
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
  const snapshot = _imaListSnapshot;
  if (snapshot && snapshot.route === normalizeRoute(fallbackRoute)) {
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
    setPageTitle(item.group_name || $("#ima-doc-title")?.textContent || "研报库");
    const ticker = imaDocTicker(item.name);
    const tickerMeta = ticker ? `<span class="ima-reader-meta-item">${escapeHtml(ticker)}</span>` : "";
    const dayContext = (item.sort_date || item.day)
      ? `<span class="ima-reader-day ima-reader-meta-item">${escapeHtml(fmtImaDay(item.sort_date || item.day))}</span>`
      : "";
    const abstractText = item.abstract_zh || item.abstract || "";
    const abstractLong = abstractText.length > IMA_ABSTRACT_CLAMP_CHARS;
    const abstractMore = abstractLong
      ? `<button type="button" class="ima-abstract-more" aria-expanded="false" onclick="toggleImaAbstract(this)">展开</button>`
      : "";
    const abstractHtml = abstractText
      ? `<details open class="ima-reader-abstract${abstractLong ? " is-clamped" : ""}"><summary>摘要</summary><p id="ima-reader-abstract">${escapeHtml(abstractText)}</p>${abstractMore}</details>`
      : "";
    // 快照路由校验（与 currentImaListSnapshot 同思路）：与本次应返回的列表路由不匹配的旧快照不用于导航/计数
    const listSnapshot = _imaListSnapshot && _imaListSnapshot.route === normalizeRoute(backRoute) ? _imaListSnapshot : null;
    const openNewTab = item.has_pdf
      ? `<button type="button" class="icon-btn" aria-label="新标签打开 PDF" title="新标签打开 PDF" onclick="openImaPdfNewTab()">${EXTERNAL_LINK_ICON}</button>`
      : "";
    const pdfPanel = item.has_pdf
      ? `<div id="ima-pdf-panel" class="ima-pdf-panel" aria-busy="true"><p class="ima-reader-status" role="status">正在打开预览…</p><iframe id="ima-pdf-frame" title="PDF 预览" hidden style="position:absolute;inset:0;width:100%;height:100%;border:0"></iframe></div>`
      : `<div class="ima-pdf-panel"><div class="ima-reader-empty" role="status"><p>还没有预览文件</p></div></div>`;
    const sizeLine = fmtDocSize(item.size);
    const sizeMeta = sizeLine ? `<span class="ima-reader-meta-item">${escapeHtml(sizeLine)}</span>` : "";
    const fileMetaHtml = (tickerMeta || dayContext || sizeMeta)
      ? `<div class="ima-reader-filemeta">${tickerMeta}${dayContext}${sizeMeta}</div>`
      : "";
    $("#kb-reader").innerHTML = `
      <article class="ima-reader">
        <header class="ima-reader-toolbar">
          <button type="button" class="ima-reader-back" data-back="${escapeHtml(backRoute)}" onclick="backFromImaReader(this.dataset.back)" aria-label="返回"><span class="ima-back-icon" aria-hidden="true">‹</span>返回</button>
          <div class="ima-reader-actions"><button type="button" class="icon-btn" aria-label="返回搜索" data-back="${escapeHtml(backRoute)}" onclick="backFromImaReader(this.dataset.back, true)">${SEARCH_ICON}</button>${openNewTab}</div>
        </header>
        <section class="ima-reader-info">
          <h2 class="ima-reader-title">${escapeHtml(imaDisplayTitle(item.name))}</h2>
          ${fileMetaHtml}
          ${imaReaderWatchHtml(item.tags)}
          ${abstractHtml}
        </section>
        ${pdfPanel}
        ${imaReaderNavHtml(mediaId, item.group_id || documentGroup, listSnapshot)}
      </article>`;
    if (item.has_pdf) loadImaPdf(mediaId, readerSeq);
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
    if (panel && frame) {
      const status = panel.querySelector(".ima-reader-status");
      if (status) status.remove();
      panel.hidden = false;
      panel.removeAttribute("aria-busy");
      frame.src = `${window._imaPdfUrl}#view=FitH&zoom=page-width`;
      frame.hidden = false;
      frame.addEventListener("error", () => showImaPdfFail(mediaId, seq, readerSeq), { once: true });
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

function homeHasFilters() {
  return !!(state.homeQ || state.homeCategory);
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
  await renderHome(routeRenderSeq);
}

// ---------- 订阅广场 ----------
async function renderHome(seq) {
  setPageTitle("订阅广场");
  ensurePlazaPlatformSelection();
  const mobileHome = isMobileTimelineFilter();
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
            <button type="button" id="home-filter-toggle" class="fav-toggle ${homeHasFilters() ? "has-filter" : ""}" aria-label="筛选" aria-expanded="false" aria-controls="home-filter-panel" onclick="homeToggleFilter()">${FILTER_ICON}筛选</button>
          </div>
          <div class="home-filter-content" id="home-filter-panel" hidden>
            <div class="search-bar home-search-bar">
              ${SEARCH_ICON}
              <input id="home-search" placeholder="搜索昵称或 ID" value="${escapeHtml(state.homeQ || "")}" oninput="homeSearch(this.value)">
            </div>
            <div class="home-cats" id="home-cats"></div>
            <div class="home-filter-actions">
              <button class="btn-ghost" onclick="homeResetFilters()">清除筛选</button>
            </div>
          </div>` : `
          <div class="toolbar" style="margin-top:12px">
            <div class="search-bar" style="flex:1;min-width:220px">
              ${SEARCH_ICON}
              <input id="home-search" placeholder="搜索昵称或 ID，即时过滤" oninput="homeSearch(this.value)">
            </div>
            <div class="platform-tabs" id="platform-tabs"></div>
          </div>
          <div class="home-cats" id="home-cats"></div>`}
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
  if (tabs) tabs.innerHTML = tlPlazaEntries().map(([p]) => platformTabHTML(p, state.platform, "switchPlatform")).join("");
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
    if (state.homeCategory && k.category_name !== state.homeCategory) return false;
    if (!q) return true;
    return (k.name || "").toLowerCase().includes(q) || (k.external_id || "").toLowerCase().includes(q);
  });
}

function renderHomeList() {
  $("#home-filter-toggle")?.classList.toggle("has-filter", homeHasFilters());
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

function platformTabHTML(p, current, handler) {
  const label = p ? PLATFORM_LABELS[p] : "全部";
  const short = platformShortLabel(p);
  return `<button class="platform-tab ${p === current ? "selected" : ""}" data-platform="${p || "all"}"
    title="${label}" aria-label="${label}"
    onclick="${handler}('${p}')">${PLATFORM_ICONS[p || ""]}<span class="pt-label">${short}</span></button>`;
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

function kolCard(kol, opts) {
  opts = opts || {};
  const tags = [];
  if (!opts.hidePlatform) {
    tags.push(`<span class="tag">${PLATFORM_LABELS[kol.platform] || escapeHtml(kol.platform)}</span>`);
  }
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
    else if (isRoute("mysubs")) renderMySubsList();
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
    else if (isRoute("mysubs")) renderMySubsList();
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
  else if (isRoute("combinations")) await renderCombinations(seq);
  else if (isRoute("mysubs")) await renderMySubs(seq);
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

// ---------- 我的订阅 / 动态 ----------
async function renderMySubs(seq) {
  setPageTitle("我的订阅");
  ensurePlazaPlatformSelection();
  const mobileFilter = isMobileTimelineFilter();
  $("#main").innerHTML = `
    <section class="section-panel${mobileFilter ? " home-panel" : ""}">
      <header class="section-head home-head">
        <div>
          <h2 class="section-title">已订阅</h2>
        </div>
      </header>
      <div class="toolbar" style="margin:12px 0 16px">
        <div class="${mobileFilter ? "icon-badge-bar mysubs-mobile-filters" : "platform-tabs"}" id="mysubs-tabs"></div>
        ${mobileFilter ? "" : `<button id="mysubs-fav-toggle" class="fav-toggle ${state.mysubsFavorite ? "fav-on" : ""}" onclick="toggleMySubsFav()">${STAR_SVG} 特别关注</button>`}
      </div>
      <div id="mysubs-list" class="kol-grid"></div>
    </section>`;
  try {
    const subs = await api("/api/my/subscriptions");
    if (!routeStillActive(seq)) return; // 已切走：不写旧页面数据
    state.catalog = subs.map((k) => ({ ...k, subscribed: true }));
    renderMySubsTabs();
    renderMySubsList();
  } catch (err) {
    if (!routeStillActive(seq)) return;
    $("#mysubs-list").innerHTML = emptyState(err.message);
  }
}

function mysubsMobileFiltersHtml() {
  const platforms = tlTimelineEntries().map(([p, label]) => {
    const short = platformShortLabel(p);
    return `
    <button class="tl-pill ${state.mysubsPlatform === p ? "selected" : ""}"
      data-platform="${p}"
      aria-label="${label}"
      title="${label}"
      role="radio"
      aria-checked="${state.mysubsPlatform === p}"
      onclick="switchMySubsPlatform('${p}')">
      ${PLATFORM_ICONS[p || ""]}<span>${short}</span>
    </button>`;
  }).join("");
  return `<div class="tl-pills" role="radiogroup" aria-label="平台">${platforms}</div>
    <button class="fav-toggle ${state.mysubsFavorite ? "fav-on" : ""}"
      aria-label="特别关注"
      aria-pressed="${state.mysubsFavorite}"
      onclick="toggleMySubsFav()">${STAR_SVG} 特别关注</button>`;
}

function renderMySubsTabs() {
  $("#mysubs-tabs").innerHTML = isMobileTimelineFilter()
    ? mysubsMobileFiltersHtml()
    : tlTimelineEntries().map(([p]) => platformTabHTML(p, state.mysubsPlatform, "switchMySubsPlatform")).join("");
}

function switchMySubsPlatform(platform) {
  state.mysubsPlatform = platform;
  renderMySubsTabs();
  renderMySubsList();
}

function renderMySubsList() {
  let kols = state.catalog.filter(
    (k) => !state.mysubsPlatform || k.platform === state.mysubsPlatform
  );
  if (state.mysubsFavorite) {
    kols = kols.filter((k) => k.favorite);
  } else {
    kols = [...kols].sort((a, b) => (b.favorite ? 1 : 0) - (a.favorite ? 1 : 0));
  }
  // 同类别排在一起（组内保持星标优先/订阅顺序），未分类排最后
  kols = [...kols].sort((a, b) => (a.category_name ? 0 : 1) - (b.category_name ? 0 : 1));
  $("#mysubs-list").innerHTML = kols.length
    ? groupedKolCards(kols)
    : emptyState("这里还没有订阅", `<div><button class="btn-normal btn-add" onclick="go('home')">去订阅广场看看</button></div>`);
}

function toggleMySubsFav() {
  state.mysubsFavorite = !state.mysubsFavorite;
  const btn = $("#mysubs-fav-toggle");
  if (btn) btn.classList.toggle("fav-on", state.mysubsFavorite);
  renderMySubsTabs(); // 移动端星标角标在 #mysubs-tabs 内，需重绘
  renderMySubsList();
}

async function renderCombinations(seq) {
  setPageTitle("组合订阅");
  $("#main").innerHTML = `
    <section class="section-panel">
      <header class="section-head">
        <div>
          <h2 class="section-title">雪球组合</h2>
          <p class="section-meta" id="combo-meta">加载中…</p>
        </div>
      </header>
      <div id="combo-list" class="kol-grid"></div>
    </section>`;
  try {
    const kols = await api("/api/catalog?platform=combination");
    if (!routeStillActive(seq)) return; // 已切走：不写旧页面数据
    state.catalog = kols;
    $("#combo-meta").textContent = `共 ${kols.length} 个组合`;
    $("#combo-list").innerHTML = kols.length
      ? kols.map((k) => kolCard(k, { hidePlatform: true })).join("")
      : emptyState(
          "还没有添加雪球组合",
          state.user?.is_admin
            ? `<div><button class="btn-normal btn-add" onclick="go('admin/kols')">去管理后台添加</button></div>`
            : `<div><button class="btn-normal btn-add" onclick="go('search')">申请添加 →</button></div>`
        );
  } catch (err) {
    if (!routeStillActive(seq)) return;
    $("#combo-list").innerHTML = emptyState(err.message);
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
  if ($("#mysubs-tabs") && $("#mysubs-list")?.contains(el)) return "mysubs";
  return null;
}

function mobilePlatformSwipeContext(surface) {
  if (surface === "timeline") return { current: () => state.timelinePlatform, apply: (p) => tlPickPlatform(p), entries: tlTimelineEntries };
  if (surface === "home") return { current: () => state.platform, apply: (p) => homePickMobilePlatform(p), entries: tlPlazaEntries };
  if (surface === "mysubs") return { current: () => state.mysubsPlatform, apply: (p) => switchMySubsPlatform(p), entries: tlTimelineEntries };
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
  if (state.mysubsPlatform && !timeline.has(state.mysubsPlatform)) {
    state.mysubsPlatform = "";
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
        <button type="button" class="btn-ghost" onclick="loadTimelineRail(routeRenderSeq)">重试</button>
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
      `<div><button class="btn-normal" onclick="loadTimeline(true, routeRenderSeq)">重试</button></div>`);
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
    : emptyState("暂无快讯", `<div><button class="btn-normal" onclick="loadTimeline(true, routeRenderSeq)">刷新</button></div>`);
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
            <a class="post-img-link" href="#" onclick="event.preventDefault();openLightbox(this.querySelector('img'))" aria-label="查看${escapeHtml(post.kol_name)}的配图"><img src="${escapeHtml(img)}" loading="lazy" alt="${escapeHtml(post.kol_name)} 的配图" onerror="imgOnError(this)"></a>`).join("")}
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
        <input id="search-input" placeholder="输入昵称或 ID，回车搜索" value="${escapeHtml(query)}" onkeydown="if(event.key==='Enter')doSearch(routeRenderSeq)">
        <button class="btn-ghost" onclick="doSearch(routeRenderSeq)">搜索</button>
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

// ---------- 推送设置 ----------
let settingsPollTimer = null;
let _pushStatusHtml = "";
const SETTINGS_TABS = ["push", "bind", "llm", "account"];
let _kolImageSubscriptions = [];
const _kolImagePendingIds = new Set();
let _kolImageLoadGeneration = 0;
let _kolImageDataRevision = 0;
let _kolImageReloadNeeded = false;

function stopSettingsPoll() {
  if (settingsPollTimer) {
    clearInterval(settingsPollTimer);
    settingsPollTimer = null;
  }
}

function startSettingsPoll() {
  stopSettingsPoll();
  settingsPollTimer = setInterval(refreshSettingsStatus, 10000);
}

function pendingBindActive() {
  return !!(pendingBind && Date.now() < pendingBind.expiresAt);
}

function settingsTargetBound(user) {
  return !!(user && (user.telegram_chat_id || feishuChannelBound(user)));
}

async function reloadSettings(routeSeq) {
  if (!routeStillActive(routeSeq)) return;
  stopSettingsPoll();
  await renderSettings(routeSeq);
}

function feishuChannelBound(user) {
  return !!(user.feishu_open_id || user.feishu_chat_id || user.feishu_personal?.status === "active");
}

function channelStatusHtml(user) {
  const tg = user.telegram_chat_id;
  const tgCustom = user.custom_telegram_bot;
  const fsOpen = user.feishu_open_id;
  const fsChat = user.feishu_chat_id;
  const fsPersonal = user.feishu_personal || {};
  const fsPersonalActive = fsPersonal.status === "active";
  const wc = user.wecom_webhook;
  const bk = user.bark_key;
  const wp = !!user.webpush_bound;
  const wpCount = user.webpush_count || 0;
  const wpOk = webPushSupported();
  const fsOk = !!(fsOpen && fsChat);
  const statusPill = (cls, text) => `<span class="channel-status ${cls}"><i class="dot"></i>${text}</span>`;
  return `
    <div class="channel-grid">
      <div class="channel-card" data-channel="telegram">
        <div class="channel-head">
          <span class="channel-title">${CHANNEL_ICONS.telegram}<b>Telegram${tgCustom ? ' <span class="tag">自建</span>' : ""}</b></span>
          ${statusPill(tg ? "status-ok" : "status-fail", tg ? "已绑定" : "未绑定")}
        </div>
        <p class="muted channel-desc">${tg ? (tgCustom ? "使用你自己的机器人推送" : "官方机器人推送已启用") : "按下方步骤操作"}</p>
        <div class="channel-actions">
          ${tg ? "" : `<div id="bind-result-telegram"></div>`}
          ${tg
            ? `<button class="channel-btn secondary" onclick="unbindChannel('${tgCustom ? "telegram_bot_token" : "telegram_chat_id"}')">解绑</button>`
            : `<button class="channel-btn primary" onclick="openBindGuide('custom-bots-bind')">去绑定</button>`}
        </div>
      </div>
      <div class="channel-card" data-channel="feishu">
        <div class="channel-head">
          <span class="channel-title">${CHANNEL_ICONS.feishu}<b>飞书${fsPersonalActive ? ' <span class="tag">个人</span>' : (fsOk ? ' <span class="tag">共享</span>' : "")}</b></span>
          ${fsPersonalActive ? statusPill("status-ok", "已绑定")
            : fsOk ? statusPill("status-ok", "已绑定")
            : fsPersonal?.status === "degraded" || fsPersonal?.status === "disabled"
              ? statusPill("status-warn", fsPersonal.status === "degraded" ? "已降级" : "已停用")
            : fsOpen ? statusPill("status-warn", "未完成")
            : statusPill("status-fail", "未绑定")}
        </div>
        <p class="muted channel-desc">
          ${fsPersonalActive ? `个人机器人推送已启用（免共享限频）${fsPersonal.app_id_masked ? " · " + escapeHtml(fsPersonal.app_id_masked) : ""}`
            : fsOk ? "共享机器人推送（不推荐，受限频影响）；建议升级个人机器人"
            : (fsOpen ? "已关联账号，请先在飞书私聊机器人发一条消息"
            : "推荐个人机器人：扫码自动创建，免共享限频")}
        </p>
        <div class="channel-actions">
          ${fsOpen || fsPersonalActive ? "" : `<div id="bind-result-feishu"></div>`}
          ${fsPersonalActive
            ? `<button class="channel-btn secondary" onclick="unbindChannel('feishu_personal')">解绑</button>`
            : fsOpen
              ? `<button class="channel-btn secondary" onclick="unbindChannel('feishu')">解绑</button>`
              : `<button class="channel-btn primary" onclick="openBindGuide('custom-bots-bind')">去绑定</button>`}
        </div>
      </div>
      <div class="channel-card" data-channel="wecom">
        <div class="channel-head">
          <span class="channel-title">${CHANNEL_ICONS.wecom}<b>企业微信</b></span>
          ${wc ? statusPill("status-ok", "已绑定") : statusPill("status-fail", "未绑定")}
        </div>
        <p class="muted channel-desc">${wc ? "群机器人推送已启用" : "在企业微信群添加群机器人，把 webhook 粘贴到下方输入框即可"}</p>
        <div class="channel-actions">
          ${wc
            ? `<button class="channel-btn secondary" onclick="unbindChannel('wecom')">解绑</button>`
            : `<button class="channel-btn primary" onclick="openBindGuide('wecom-bind')">去绑定</button>`}
        </div>
      </div>
      <div class="channel-card" data-channel="bark">
        <div class="channel-head">
          <span class="channel-title">${CHANNEL_ICONS.bark}<b>Bark</b></span>
          ${bk ? statusPill("status-ok", "已绑定") : statusPill("status-fail", "未绑定")}
        </div>
        <p class="muted channel-desc">${bk ? "iOS 推送已启用" : "iPhone 装 Bark App，把推送 key 粘贴到下方输入框即可"}</p>
        <div class="channel-actions">
          ${bk
            ? `<button class="channel-btn secondary" onclick="unbindChannel('bark')">解绑</button>`
            : `<button class="channel-btn primary" onclick="openBindGuide('bark-bind')">去绑定</button>`}
        </div>
      </div>
      <div class="channel-card" data-channel="webpush">
        <div class="channel-head">
          <span class="channel-title">${CHANNEL_ICONS.webpush}<b>浏览器通知</b></span>
          ${!wpOk
            ? statusPill("status-fail", "当前环境不可用")
            : wp ? statusPill("status-ok", wpCount > 1 ? `已开启 · ${wpCount} 台设备` : "已开启")
            : statusPill("status-fail", "未开启")}
        </div>
        <p class="muted channel-desc">${!wpOk
          ? "请用 Chrome 或 Edge，并打开 HTTPS（本机 localhost 也可以）"
          : wp
            ? "Chrome / Edge 系统通知已启用，关掉标签页也能收到"
            : "在本页一键开启；Chrome / Edge 关掉标签页也能弹系统通知（需 HTTPS）"}</p>
        <div class="channel-actions">
          ${!wpOk
            ? `<button type="button" class="channel-btn primary" disabled>开启</button>`
            : wp
              ? `<button type="button" class="channel-btn primary" onclick="enableWebPush()">在此浏览器开启</button>
                 <button type="button" class="channel-btn secondary" onclick="disableWebPush()">关闭</button>`
              : `<button type="button" class="channel-btn primary" onclick="enableWebPush()">开启</button>`}
        </div>
      </div>
    </div>`;
}

function paintPushStatus(user) {
  const el = $("#push-status");
  if (!el) return;
  const html = channelStatusHtml(user);
  if (html === _pushStatusHtml) return;
  const active = document.activeElement;
  let restore = null;
  if (active && el.contains(active)) {
    const card = active.closest("[data-channel]");
    restore = {
      channel: card && card.dataset.channel,
      text: (active.textContent || "").trim(),
      tag: active.tagName,
    };
  }
  el.innerHTML = html;
  _pushStatusHtml = html;
  if (!restore) return;
  const card = restore.channel ? el.querySelector(`[data-channel="${restore.channel}"]`) : el;
  if (!card) return;
  const nodes = [...card.querySelectorAll(restore.tag)];
  const match = nodes.find((n) => (n.textContent || "").trim() === restore.text) || nodes[0];
  if (match && typeof match.focus === "function") match.focus();
}

async function refreshSettingsStatus() {
  const seq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  try {
    const user = await api("/api/me");
    if (!routeStillActive(seq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    state.user = user;
    const el = $("#push-status");
    if (!el) {
      stopSettingsPoll();
      return;
    }
    paintPushStatus(user);
    // 状态轮询会重绘卡片，把未过期的绑定码重新显示，避免刚生成的码被刷掉
    if (pendingBind && Date.now() < pendingBind.expiresAt) {
      renderBindResult(pendingBind.channel, pendingBind.code);
    } else if (pendingBind) {
      pendingBind = null;
    }
    if (!pendingBindActive() || settingsTargetBound(user)) stopSettingsPoll();
  } catch {
    /* 轮询失败忽略 */
  }
}

async function renderSettings(seq) {
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  setPageTitle("推送设置");
  try {
    const user = await api("/api/me");
    if (!routeStillActive(seq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    state.user = user;
    stopSettingsPoll();
    const guide = state.user.push_guide || {};
    const tgBot = guide.telegram_bot_username || "";
    const fsBot = guide.feishu_bot_name || "";
    const tgTarget = tgBot
      ? `<a href="https://t.me/${encodeURIComponent(tgBot)}" target="_blank" rel="noopener">@${escapeHtml(tgBot)}</a>`
      : "你的机器人";
    const fsTarget = fsBot ? `<b>${escapeHtml(fsBot)}</b>` : "你的机器人应用名";
    $("#main").innerHTML = `
      <div class="settings-tabs" role="tablist" aria-label="设置分页">
        <button type="button" class="settings-tab active" role="tab" id="tab-push" aria-selected="true" aria-controls="st-push" data-tab="push" onclick="switchSettingsTab('push')">推送设置</button>
        <button type="button" class="settings-tab" role="tab" id="tab-bind" aria-selected="false" aria-controls="st-bind" data-tab="bind" onclick="switchSettingsTab('bind')">渠道绑定</button>
        <button type="button" class="settings-tab" role="tab" id="tab-llm" aria-selected="false" aria-controls="st-llm" data-tab="llm" onclick="switchSettingsTab('llm')">AI 摘要</button>
        <button type="button" class="settings-tab" role="tab" id="tab-account" aria-selected="false" aria-controls="st-account" data-tab="account" onclick="switchSettingsTab('account')">账号设置</button>
      </div>
      <div id="st-push" class="settings-tab-panel" role="tabpanel" aria-labelledby="tab-push">
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">推送开关</h2>
            <p class="section-meta">总开关与每日精选摘要。</p>
          </div>
        </header>
        <div class="form-row">
          <label for="set-notify">新帖推送开关</label>
          <select id="set-notify" class="form-control" onchange="saveNotify()">
            <option value="1" ${state.user.notify_enabled ? "selected" : ""}>开启</option>
            <option value="0" ${!state.user.notify_enabled ? "selected" : ""}>关闭</option>
          </select>
        </div>
        <p class="muted">关闭后不会向任何渠道推送新帖，订阅关系保留。</p>
        <div class="form-row" style="margin-top:16px">
          <label for="set-daily">每日精选摘要</label>
          <select id="set-daily" class="form-control" onchange="saveDailyReport()">
            <option value="1" ${state.user.daily_report_enabled ? "selected" : ""}>开启（每天 20:00 推一次 AI 每日精选）</option>
            <option value="0" ${!state.user.daily_report_enabled ? "selected" : ""}>关闭</option>
          </select>
        </div>
        <p class="muted">开启后，每天 20:00 把你订阅大V当天的新动态汇总成一条推送。</p>
        <div class="form-row" style="margin-top:16px">
          <label for="set-x-translate">X 帖文</label>
          <select id="set-x-translate" class="form-control" onchange="saveTranslateTwitter()">
            <option value="1" ${state.user.translate_twitter !== false ? "selected" : ""}>翻译成中文</option>
            <option value="0" ${state.user.translate_twitter === false ? "selected" : ""}>保留原文</option>
          </select>
        </div>
        <p class="muted">只影响你的时间线和推送。管理员需开启「X 内容自动翻译」后，新抓的帖才会同时留下原文。</p>
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">免打扰时段</h2>
            <p class="section-meta">时段内不推送新帖（支持跨午夜），结束后一次性补一条汇总；系统告警不受影响。特别关注可设为穿透免打扰。</p>
          </div>
        </header>
        <div class="dnd-form">
          <label class="switch">
            <input id="dnd-enabled" type="checkbox" ${state.user.dnd_start ? "checked" : ""} onchange="toggleDnd()">
            <span class="track"></span>
            <span>开启免打扰</span>
          </label>
          <div class="dnd-range-field" id="dnd-range-field">
            <span class="dnd-range-label">免打扰时段</span>
            <div class="dnd-range">
              <input id="dnd-start" type="time" class="form-control" value="${escapeHtml(state.user.dnd_start || "23:00")}">
              <span class="dnd-sep">至</span>
              <input id="dnd-end" type="time" class="form-control" value="${escapeHtml(state.user.dnd_end || "07:00")}">
            </div>
          </div>
          <label class="switch">
            <input id="dnd-fav" type="checkbox" ${state.user.dnd_allow_favorite ? "checked" : ""}>
            <span class="track"></span>
            <span>特别关注可穿透免打扰</span>
          </label>
          <div class="dnd-actions">
            <button class="btn-normal" onclick="saveDnd()">保存</button>
          </div>
        </div>
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">关键词提醒</h2>
            <p class="section-meta">每行一个，最多 20 个，每个不超过 50 字。动态命中会加标记并实时推送（穿透免打扰）；研报命中在每日更新后合并成一条，不穿透免打扰。</p>
          </div>
        </header>
        <div class="form-row">
          <label for="set-keywords">关键词（每行一个）</label>
          <textarea id="set-keywords" class="form-control" rows="4"
            placeholder="ETF&#10;降息&#10;中概股">${escapeHtml((state.user.keywords || []).join("\n"))}</textarea>
        </div>
        <label class="switch kw-report-switch">
          <input id="set-kw-reports" type="checkbox" ${state.user.keywords_match_reports ? "checked" : ""} onchange="saveKeywordsMatchReports()">
          <span class="track"></span>
          <span>匹配研报库</span>
        </label>
        <div class="toolbar" style="margin-top:10px">
          <button class="btn-normal" onclick="saveKeywords()">保存关键词</button>
        </div>
        <p class="muted">动态命中即实时送达。开启「匹配研报库」后，每日研报入库结束会把命中篇目合成一条推送；需要管理员已授权对应研报库。</p>
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">动态图片</h2>
            <p class="section-meta">关闭某位大V的图片显示后，该大V的动态图片会从网页和推送中隐藏；头像仍会显示。仅影响当前账号。</p>
          </div>
        </header>
        <div id="kol-images-settings" class="muted kol-images-state" role="status">正在加载已订阅大V…</div>
      </section>
      </div>
      <div id="st-bind" class="settings-tab-panel" role="tabpanel" aria-labelledby="tab-bind">
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">推送渠道</h2>
            <p class="section-meta">绑定状态每 10 秒自动刷新；绑定了多个渠道时，可在下方勾选要接收推送的渠道（不选则全部推送）。</p>
          </div>
        </header>
        <div id="push-status">${channelStatusHtml(state.user)}</div>
        <div class="channel-picks" id="push-channels-box" style="margin-top:18px;padding-top:18px;border-top:var(--border-default)">${pushChannelsHtml(state.user)}</div>
        ${(state.user.telegram_chat_id || feishuChannelBound(state.user) || state.user.wecom_webhook || state.user.bark_key || state.user.webpush_bound)
          ? `<div class="toolbar" style="margin-top:14px">
               <button class="btn-normal" onclick="savePushChannels()">保存推送通道</button>
             </div>` : ""}
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">渠道绑定</h2>
            <p class="section-meta">按序绑定想用的推送渠道，每个渠道的步骤可展开；绑定状态在「推送渠道状态」卡片查看。</p>
          </div>
        </header>
        <div class="channel-bind-block" id="custom-bots-bind">
          <h4 class="section-title">自建机器人（推荐，免共享限频）</h4>
          <p class="section-meta">共享机器人所有用户共用一个应用配额；自建/个人机器人是<b>属于你自己的机器人应用</b>，推送配额独立、不受共享应用限制。Telegram 自建约 1 分钟，飞书个人扫码自动创建。</p>
          <div class="channel-bind-block" style="padding-top:8px">
            <h4 class="section-title">Telegram 自建机器人</h4>
            <ol style="padding-left:20px;line-height:2">
              <li>打开 Telegram 搜索 <b>@BotFather</b>，发 <code>/newbot</code> 创建机器人，拿到 token</li>
              <li>给你的新机器人发任意消息（如 <code>/start</code>）</li>
              <li>把 token 粘贴到下方点「保存」，系统自动识别你的会话，无需手动填 ID</li>
            </ol>
            <div class="row" style="gap:8px;margin-top:10px">
              <input id="set-custom-tg" class="form-control" style="flex:1;min-width:220px" type="password" placeholder="123456:ABC-DEF...">
              <button class="btn-normal" onclick="saveCustomTgBot()">保存</button>
            </div>
          </div>
          <div class="channel-bind-block" style="padding-top:8px">
            <h4 class="section-title">飞书个人机器人（扫码自动创建）</h4>
            <div id="fs-personal-block">${feishuPersonalHtml(state.user.feishu_personal)}</div>
          </div>
        </div>
        <div class="channel-bind-block" id="telegram-bind">
          <h4 class="section-title">1. Telegram 机器人</h4>
          ${bindGuideHtml(!!state.user.telegram_chat_id, `
        <ol style="padding-left:20px;line-height:2">
          <li>打开 Telegram，搜索并进入 ${tgTarget}（找不到就点上方链接）。</li>
          <li>点击「开始」或发送任意消息（如 <code>/start</code>），系统自动记录你的会话。</li>
          <li>回到本页，状态几秒内自动变成「已绑定 ✅」。</li>
          <li>发 <code>/list</code> 可查看大V目录，<code>/sub 大VID</code> 直接订阅。</li>
        </ol>`)}
        </div>
        <div class="channel-bind-block" id="feishu-bind">
          <h4 class="section-title">2. 飞书机器人 · 共享备选</h4>
          <p class="section-meta">不推荐：所有用户共用一个应用，推送配额共享，人多可能被限频。仅作为没有个人机器人时的临时备选，建议优先用上方「自建机器人」里的个人机器人。</p>
          ${bindGuideHtml(!!(state.user.feishu_open_id && state.user.feishu_chat_id), `
        <ol style="padding-left:20px;line-height:2">
          <li>打开飞书 App，点顶部「搜索」，搜索 ${fsTarget} 并进入。</li>
          <li>关键：请在该机器人的<b>「私聊」会话</b>里发任意消息（如 <code>/start</code>）——群聊不会推送新帖，这一步只是建立会话。</li>
          <li>回到本页，在下方「与网页/小程序账号同步」里点「生成绑定码」，把 <code>/bind 6位码</code> 发给机器人。</li>
          <li>发送后本页状态会变成「已绑定 ✅」，网页订阅与飞书推送自动同步。</li>
          <li>发 <code>/list</code> 可查看大V目录，点卡片上的按钮即可订阅。</li>
        </ol>`)}
        </div>
        <div class="channel-bind-block" id="wecom-bind">
          <h4 class="section-title">3. 企业微信群机器人</h4>
          <p class="section-meta">无需申请应用；在企业微信任意群里添加「群机器人」即可，推送会发到这个群。</p>
          ${bindGuideHtml(!!state.user.wecom_webhook, `
        <ol style="padding-left:20px;line-height:2">
          <li>打开企业微信，进入一个群（没有就新建一个，例如「大V推送」）。</li>
          <li>点右上角 <code>...</code> → 「群机器人」→「添加机器人」，按提示创建并起名。</li>
          <li>创建完成后复制 webhook 地址（<code>https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...</code>）。</li>
          <li>粘贴到下方输入框，点「保存绑定」，状态即变为「已绑定 ✅」。</li>
        </ol>`)}
          <div class="form-row" style="margin-top:14px">
            <label for="set-wecom-webhook">群机器人 webhook 地址</label>
            <div class="row" style="gap:10px;flex-wrap:wrap">
              <input id="set-wecom-webhook" class="form-control" style="flex:1;min-width:280px"
                type="text" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
                value="${escapeHtml(state.user.wecom_webhook || "")}">
              <button class="btn-normal" onclick="saveWecomWebhook()">保存绑定</button>
            </div>
          </div>
          <p class="muted">⚠️ webhook 等同群管理权限，请勿泄露给他人；不同用户应使用各自的群机器人。</p>
        </div>
        <div class="channel-bind-block" id="bark-bind">
          <h4 class="section-title">4. Bark（iPhone 推送）</h4>
          <p class="section-meta">iOS 自托管用户神器：Bark App 免登录、免费、推送直达锁屏，无需申请任何开发者资质。</p>
          ${bindGuideHtml(!!state.user.bark_key, `
        <ol style="padding-left:20px;line-height:2">
          <li>iPhone 在 App Store 搜索「Bark」安装，打开后主屏会显示你的推送 key（形如 <code>AaBbCcDdEe...</code>）。</li>
          <li>把这个 key 粘贴到下方输入框，点「保存绑定」即可。</li>
          <li>想用自建 Bark 服务器？直接把服务器里的完整地址（<code>https://bark.example.com/xxx</code>）粘贴进来也行。</li>
        </ol>`)}
          <div class="form-row" style="margin-top:14px">
            <label for="set-bark-key">Bark 推送 key 或完整地址</label>
            <div class="row" style="gap:10px;flex-wrap:wrap">
              <input id="set-bark-key" class="form-control" style="flex:1;min-width:280px"
                type="text" placeholder="AaBbCcDdEeFf...（Bark App 里的 key）"
                value="${escapeHtml(state.user.bark_key || "")}">
              <button class="btn-normal" onclick="saveBarkKey()">保存绑定</button>
            </div>
          </div>
          <p class="muted">🔔 key 等同推送权限，请勿泄露；系统告警不依赖此 key（管理员另配系统级 Bark）。</p>
        </div>
        <div class="channel-bind-block" id="webpush-bind">
          <h4 class="section-title">5. 浏览器通知（Chrome / Edge）</h4>
          <p class="section-meta">网页系统通知：在「推送渠道」卡片点「开启」授权即可。关掉标签页也能收到；需 HTTPS。可在多台 Chrome / Edge 分别点「在此浏览器开启」。点「关闭」会关掉该功能（所有已开启的浏览器都不再弹）。</p>
        </div>
      </section>
      </div>
      <div id="st-llm" class="settings-tab-panel" role="tabpanel" aria-labelledby="tab-llm">
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">AI 摘要（可选，用你的大模型）</h2>
            <p class="section-meta">任意 OpenAI 兼容接口（/chat/completions 与 /models）。DeepSeek、Grok、OpenAI、本地网关均可。不填则用站点默认模型。</p>
          </div>
        </header>
        <div class="form-row">
          <label for="set-llm-base">API 地址（Base URL）</label>
          <input id="set-llm-base" class="form-control" type="text"
            placeholder="https://api.openai.com/v1"
            value="${escapeHtml(state.user.llm_api_base || "")}">
          <p class="muted" style="margin-top:4px">OpenAI 兼容的 http(s) Base URL，内网和本机也可以。留空跟站点同一套。</p>
        </div>
        <div class="form-row">
          <label for="set-llm-key">API Key</label>
          <input id="set-llm-key" class="form-control" type="password"
            placeholder="sk-...（清空并保存 = 用站点默认）"
            value="${escapeHtml(state.user.llm_api_key || "")}" autocomplete="off">
        </div>
        <div class="form-row">
          <label for="set-llm-model">模型</label>
          <div class="row" style="gap:10px;flex-wrap:wrap">
            <input id="set-llm-model" class="form-control" type="text" list="set-llm-model-list"
              placeholder="保存地址和 Key 后可拉取列表，也可手填"
              value="${escapeHtml(state.user.llm_model || "")}" style="flex:1;min-width:220px">
            <datalist id="set-llm-model-list"></datalist>
            <button type="button" class="btn-ghost" onclick="loadLlmModels()">拉取模型列表</button>
          </div>
          <p class="muted" style="margin-top:4px">列表来自该接口的 <code>/models</code>；没有列表的网关仍可手填模型名。</p>
        </div>
        <div class="toolbar" style="margin-top:10px">
          <button class="btn-normal" onclick="saveLlm()">保存</button>
        </div>
        <p class="muted">🔒 自己的 Key 只对当前账号生效，费用由你的 API 账号承担；生成失败会自动回退为普通摘要，不影响推送。</p>
      </section>
      </div>
      <div id="st-account" class="settings-tab-panel" role="tabpanel" aria-labelledby="tab-account">
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">修改密码</h2>
            <p class="section-meta">定期更换密码，保护你的账号安全。</p>
          </div>
        </header>
        <div class="form-row">
          <label for="pw-old">原密码</label>
          <input id="pw-old" class="form-control" type="password" placeholder="输入当前密码" autocomplete="current-password">
        </div>
        <div class="form-row">
          <label for="pw-new">新密码</label>
          <input id="pw-new" class="form-control" type="password" placeholder="至少 6 位" autocomplete="new-password">
        </div>
        <div class="form-row">
          <label for="pw-confirm">确认新密码</label>
          <input id="pw-confirm" class="form-control" type="password" placeholder="再次输入新密码" autocomplete="new-password">
        </div>
        <button class="btn-normal" onclick="savePassword()">修改密码</button>
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div>
            <h2 class="section-title">与网页/小程序账号同步（可选）</h2>
            <p class="section-meta">机器人是独立账号；想让机器人订阅与网页账号合并，用绑定码。</p>
          </div>
        </header>
        <details class="bind-steps">
          <summary>展开查看同步步骤</summary>
        <ol style="padding-left:20px;line-height:2">
          <li>点下方「生成绑定码」。</li>
          <li>把 <code>/bind 6位码</code> 发给 Telegram / 飞书机器人（企业微信群机器人是单向 webhook，不支持指令）。</li>
          <li>绑定后机器人账号合并到当前账号，订阅与推送同步，一处订阅处处同步。</li>
        </ol>
        </details>
        <div class="row">
          <button class="btn-ghost" onclick="genBindCode()">生成绑定码</button>
        </div>
        <div id="bind-result" class="muted" style="margin-top:14px"></div>
      </section>
      </div>`;
    _pushStatusHtml = channelStatusHtml(state.user);
    if (pendingBindActive() && !settingsTargetBound(state.user)) startSettingsPoll();
    switchSettingsTab(state.settingsTab || "push"); // 恢复上次所在分栏
    toggleDnd(); // 根据开关初始状态同步时段输入框的禁用/置灰
    loadKolImageSettings(seq);
  } catch (err) {
    if (!routeStillActive(seq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    $("#main").innerHTML = emptyState(err.message);
  }
}

function reloadKolImageSettingsIfNeeded() {
  if (!_kolImageReloadNeeded || _kolImagePendingIds.size) return;
  if (!isRoute("settings")) return;
  _kolImageReloadNeeded = false;
  loadKolImageSettings(routeRenderSeq);
}

async function loadKolImageSettings(seq) {
  const target = $("#kol-images-settings");
  if (!target) return;
  const loadGeneration = ++_kolImageLoadGeneration;
  const loadRevision = _kolImageDataRevision;
  target.className = "muted kol-images-state";
  target.setAttribute("role", "status");
  target.textContent = "正在加载已订阅大V…";
  try {
    const subscriptions = await api("/api/my/subscriptions");
    if (loadGeneration !== _kolImageLoadGeneration || !routeStillActive(seq)) return;
    if (loadRevision !== _kolImageDataRevision || _kolImagePendingIds.size) {
      _kolImageReloadNeeded = true;
      reloadKolImageSettingsIfNeeded();
      return;
    }
    _kolImageReloadNeeded = false;
    _kolImageSubscriptions = subscriptions;
    renderKolImageSettings();
  } catch (err) {
    if (loadGeneration !== _kolImageLoadGeneration || !routeStillActive(seq)) return;
    if (loadRevision !== _kolImageDataRevision || _kolImagePendingIds.size) {
      _kolImageReloadNeeded = true;
      reloadKolImageSettingsIfNeeded();
      return;
    }
    _kolImageReloadNeeded = false;
    const current = $("#kol-images-settings");
    if (!current) return;
    current.className = "kol-images-local-state";
    current.setAttribute("role", "alert");
    current.innerHTML = `
      <p class="muted">加载失败: ${escapeHtml(err.message)}</p>
      <button type="button" class="btn-ghost" onclick="loadKolImageSettings(routeRenderSeq)">重试</button>`;
  }
}

function renderKolImageSettings() {
  const target = $("#kol-images-settings");
  if (!target) return;
  target.className = "";
  target.removeAttribute("role");
  if (!_kolImageSubscriptions.length) {
    target.innerHTML = emptyState(
      "还没有订阅大V",
      `<div><button type="button" class="btn-normal btn-add" onclick="go('home')">去订阅广场</button></div>`
    );
    return;
  }
  const search = _kolImageSubscriptions.length >= 12
    ? `<div class="search-bar kol-images-search">
         ${SEARCH_ICON}
         <input id="kol-images-search" type="search" aria-label="搜索已订阅大V"
           placeholder="搜索已订阅大V" oninput="filterKolImageSettings()">
       </div>`
    : "";
  target.innerHTML = `${search}<div id="kol-images-list" class="kol-images-list" role="region" aria-label="已订阅大V的动态图片"></div><p id="kol-images-more" class="section-meta" hidden></p>`;
  filterKolImageSettings();
}

function filterKolImageSettings() {
  const list = $("#kol-images-list");
  if (!list) return;
  const query = ($("#kol-images-search")?.value || "").trim().toLowerCase();
  const filtered = query
    ? _kolImageSubscriptions.filter((kol) => {
        const platform = PLATFORM_LABELS[kol.platform] || kol.platform || "";
        return [kol.name, kol.external_id, platform]
          .some((value) => String(value || "").toLowerCase().includes(query));
      })
    : _kolImageSubscriptions;
  list.innerHTML = filtered.length
    ? filtered.map(kolImageSettingsRowHtml).join("")
    : emptyState("没有匹配的已订阅大V");
  const more = $("#kol-images-more");
  if (more) {
    const extra = Math.max(0, filtered.length - 5);
    more.hidden = extra === 0;
    more.textContent = extra ? `还有 ${extra} 位` : "";
  }
}

function kolImageSettingsRowHtml(kol) {
  const platform = PLATFORM_LABELS[kol.platform] || kol.platform || "";
  return `
    <div class="kol-images-row">
      ${avatarHtml(kol.name, kol.avatar_url)}
      <div class="kol-images-info">
        <span class="kol-images-name" title="${escapeHtml(kol.name)}">${escapeHtml(kol.name)}</span>
        <span class="kol-images-platform">${escapeHtml(platform)}</span>
      </div>
      <label class="switch kol-images-switch">
        <input type="checkbox" ${!kol.hide_images ? "checked" : ""}
          ${_kolImagePendingIds.has(kol.id) ? "disabled" : ""}
          data-kol-id="${kol.id}"
          aria-label="显示${escapeHtml(kol.name)}（${escapeHtml(platform)}）的动态图片"
          onchange="toggleKolImages(${kol.id}, this)">
        <span class="track"></span>
        <span>显示</span>
      </label>
    </div>`;
}

async function toggleKolImages(kolId, input) {
  if (!input || input.disabled || _kolImagePendingIds.has(kolId)) return;
  const kol = _kolImageSubscriptions.find((item) => item.id === kolId);
  if (!kol) return;
  const seq = routeRenderSeq;
  const show = input.checked;
  const previousHideImages = kol.hide_images;
  const restoreFocus = document.activeElement === input && input.matches(":focus-visible");
  _kolImageDataRevision += 1;
  _kolImagePendingIds.add(kolId);
  kol.hide_images = !show;
  input.disabled = true;
  try {
    await api(`/api/subscriptions/${kolId}/hide-images`, {
      method: "PUT",
      body: JSON.stringify({ hide_images: !show }),
    });
    if (!routeStillActive(seq)) return;
    flash(`${show ? "已显示" : "已隐藏"}「${kol ? kol.name : "该大V"}」的动态图片`);
  } catch (err) {
    kol.hide_images = previousHideImages;
    if (!routeStillActive(seq)) return;
    input.checked = !previousHideImages;
    flash("保存失败: " + err.message, "error");
  } finally {
    _kolImagePendingIds.delete(kolId);
    _kolImageDataRevision += 1;
    const isCurrentSettings = isRoute("settings");
    if (!routeStillActive(seq) && isCurrentSettings) _kolImageReloadNeeded = true;
    if (_kolImagePendingIds.size === 0 && _kolImageReloadNeeded) {
      reloadKolImageSettingsIfNeeded();
    } else if (routeStillActive(seq)) {
      const mountedInput = document.querySelector(`#kol-images-list input[data-kol-id="${kolId}"]`);
      if (mountedInput) {
        mountedInput.checked = !kol.hide_images;
        mountedInput.disabled = false;
        if (restoreFocus && (document.activeElement === input || document.activeElement === document.body)) {
          mountedInput.focus({ preventScroll: true });
        }
      }
    }
  }
}

function switchSettingsTab(name) {
  // 设置页分段导航：推送 / 渠道绑定 / AI 摘要 / 账号设置
  if (!SETTINGS_TABS.includes(name)) name = "push";
  state.settingsTab = name;
  document.querySelectorAll(".settings-tab[data-tab]").forEach((b) => {
    if (!SETTINGS_TABS.includes(b.dataset.tab)) return;
    const on = b.dataset.tab === name;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  });
  SETTINGS_TABS.forEach((t) => {
    const el = document.getElementById("st-" + t);
    if (!el) return;
    const on = t === name;
    el.style.display = on ? "" : "none";
    el.hidden = !on;
  });
}

function statsTabFromHash() {
  const tab = routeQuery().get("tab") || "config";
  if (tab === "overview" || tab === "health") return "legacy-dashboard";
  return STATS_TABS.includes(tab) ? tab : "config";
}

function switchStatsTab(name) {
  // 数据源页分段导航：抓取设置 / Cookie 管理 / 代理 / 广场显示
  if (name === "legacy-dashboard" || name === "overview" || name === "health") {
    replaceRoute("admin/dashboard");
    return;
  }
  if (!STATS_TABS.includes(name)) name = "config";
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

function bindGuideHtml(bound, stepsHtml) {
  // 渠道绑定步骤折叠：未绑定时默认展开引导，已绑定时收起来（页面不再一屏放不下）
  return `<details class="bind-steps" ${bound ? "" : "open"}>
    <summary>${bound ? "已绑定 ✅ · 展开查看绑定步骤" : "展开查看绑定步骤"}</summary>
    ${stepsHtml}
  </details>`;
}

// ---------- 飞书个人机器人（扫码注册） ----------
const fsPersonalState = {
  sessionId: "", bindCommand: "", bindExpiresAt: 0, verificationUri: "", qrUri: "",
  pollTimer: null, countdownTimer: null, owner: null, refreshInFlight: false,
};

function fsPersonalOwnerActive(owner) {
  return !!owner && fsPersonalState.owner === owner
    && owner.token === state.token
    && owner.sessionGeneration === imaMountState.sessionGeneration
    && routeStillActive(owner.routeSeq);
}


function feishuPersonalHtml(fs) {
  fs = fs || {};
  if (!fs.available) {
    return `<p class="muted">⚠️ 个人机器人功能未启用（服务端未配置 FEISHU_CREDENTIAL_KEY），请使用上方共享机器人。</p>`;
  }
  if (fs.status === "active") {
    return `<div class="row" style="gap:10px;flex-wrap:wrap;align-items:center">
      <span class="channel-status status-ok"><i class="dot"></i>个人机器人已激活${fs.app_id_masked ? " · " + escapeHtml(fs.app_id_masked) : ""}</span>
      <button class="channel-btn secondary" onclick="unbindChannel('feishu_personal')">解绑个人机器人</button>
    </div>
    <p class="muted" style="margin-top:8px">推送将使用你的个人应用发送，配额独立、不受共享应用限制；共享机器人绑定保留，个人机器人失效时自动回退。</p>`;
  }
  if (fs.status === "degraded") {
    return `<div class="row" style="gap:10px;flex-wrap:wrap;align-items:center">
      <span class="channel-status status-warn"><i class="dot"></i>个人机器人已降级（暂用共享推送）</span>
      <button class="channel-btn primary" onclick="startFeishuPersonal()">重新扫码绑定</button>
    </div>`;
  }
  if (fsPersonalState.sessionId) {
    return fsPersonalStateHtml();
  }
  return `<div class="row" style="gap:10px;flex-wrap:wrap;margin-top:8px">
    <button class="btn-normal" onclick="startFeishuPersonal()">扫码创建个人机器人</button>
    <span class="muted">需要飞书扫码；个人应用会创建在你自己的飞书租户里。</span>
  </div>`;
}

function fsPersonalStateHtml() {
  const st = fsPersonalState;
  const secs = Math.max(0, Math.ceil((st.bindExpiresAt - Date.now()) / 1000));
  const uri = st.verificationUri || "";
  return `<div id="fs-personal-flow">
    <div style="text-align:center;padding:8px 0 12px">
      ${st.qrUri ? `<img class="qr-frame" src="${st.qrUri}" alt="扫码二维码">` : ""}
      <p class="muted qr-status">用飞书「扫一扫」扫码；或点链接打开：
        <a href="${escapeHtml(uri)}" target="_blank" rel="noopener">${escapeHtml(uri)}</a>
      </p>
    </div>
    ${st.bindCommand ? `
    <p style="line-height:1.9">下一步：打开刚创建的个人机器人<b>私聊窗口</b>，发送：<br>
      <code class="bind-code">${escapeHtml(st.bindCommand)}</code>
      <span id="fs-bind-countdown" class="muted" style="margin-left:8px">${secs}s</span>
    </p>
    <div class="row" style="gap:10px;margin-top:8px;flex-wrap:wrap">
      <button class="btn-normal btn-sm" onclick="refreshFeishuBindCode()">重新生成绑定码</button>
      <button class="btn-ghost btn-sm" onclick="cancelFeishuPersonal()">取消</button>
    </div>` : `
    <p class="muted">⏳ 等待扫码…（扫完码会自动进入下一步）</p>
    <button class="btn-ghost btn-sm" onclick="cancelFeishuPersonal()">取消</button>`}
  </div>`;
}

async function startFeishuPersonal() {
  const owner = {
    routeSeq: routeRenderSeq,
    token: state.token,
    sessionGeneration: imaMountState.sessionGeneration,
  };
  fsPersonalState.owner = owner;
  stopFeishuPersonalPoll(owner);
  try {
    const data = await api("/api/me/feishu-personal/register", { method: "POST" });
    if (!fsPersonalOwnerActive(owner)) return;
    fsPersonalState.sessionId = data.session_id;
    fsPersonalState.bindCommand = "";
    fsPersonalState.verificationUri = data.verification_uri;
    fsPersonalState.qrUri = data.qr_uri || "";
    fsPersonalRender(owner);
    startFeishuPersonalPoll(data.session_id, owner);
  } catch (err) {
    if (fsPersonalOwnerActive(owner)) flash("发起个人机器人注册失败: " + err.message, "error");
  }
}

function fsPersonalRender(owner = fsPersonalState.owner) {
  // 局部重绘个人机器人区块（不整页重绘：renderSettings 需要路由序号，轮询里拿不到）
  if (!fsPersonalOwnerActive(owner)) return;
  const el = $("#fs-personal-block");
  if (el) el.innerHTML = feishuPersonalHtml(state.user?.feishu_personal);
}

function startFeishuPersonalPoll(sessionId, owner = fsPersonalState.owner) {
  if (!fsPersonalOwnerActive(owner)) return;
  stopFeishuPersonalPoll(owner);
  const timer = setInterval(async () => {
    if (!fsPersonalOwnerActive(owner) || fsPersonalState.pollTimer !== timer) return;
    try {
      const data = await api(`/api/me/feishu-personal/register/${sessionId}`);
      if (!fsPersonalOwnerActive(owner) || fsPersonalState.pollTimer !== timer) return;
      fsPersonalState.verificationUri = data.verification_uri;
      fsPersonalState.qrUri = data.qr_uri || fsPersonalState.qrUri;
      // 同步个人机器人展示状态（轮询期间 /api/me 不会刷新）
      state.user.feishu_personal = state.user.feishu_personal || {};
      if (data.personal_bot_status) state.user.feishu_personal.status = data.personal_bot_status;
      if (data.status === "awaiting_bind") {
        if (data.bind_command) {
          const expiresAt = (data.bind_code_expires_at || 0) * 1000;
          const changed = fsPersonalState.bindCommand !== data.bind_command
            || fsPersonalState.bindExpiresAt !== expiresAt;
          fsPersonalState.bindCommand = data.bind_command;
          fsPersonalState.bindExpiresAt = expiresAt;
          if (changed) {
            fsPersonalRender(owner);
            startFeishuBindCountdown(owner);
          }
        } else {
          refreshFeishuBindCode();
        }
      } else if (data.status === "active") {
        stopFeishuPersonalPoll(owner);
        fsPersonalState.sessionId = "";
        fsPersonalRender(owner);
        flash("个人机器人已绑定");
      } else if (["expired", "cancelled", "degraded"].includes(data.status)) {
        stopFeishuPersonalPoll(owner);
        fsPersonalState.sessionId = "";
        fsPersonalRender(owner);
        if (data.status === "degraded") flash("个人机器人绑定失败：" + (data.last_error || "未知错误"), "error");
      } else {
        // pending / credentials_created：局部刷新等待扫码区域
        fsPersonalRender(owner);
      }
    } catch (err) {
      // 轮询失败静默，下轮再试；会话不存在则结束
      if (fsPersonalOwnerActive(owner) && fsPersonalState.pollTimer === timer
        && String(err.message).includes("404")) {
        stopFeishuPersonalPoll(owner);
        fsPersonalState.sessionId = "";
        fsPersonalRender(owner);
      }
    }
  }, 1000);  // 绑定轮询：1s 一次，扫码/绑定完成及时反映（状态接口很轻量）
  fsPersonalState.pollTimer = timer;
}

function stopFeishuPersonalPoll(owner = null) {
  if (owner && fsPersonalState.owner !== owner) return;
  if (fsPersonalState.pollTimer) {
    clearInterval(fsPersonalState.pollTimer);
    fsPersonalState.pollTimer = null;
  }
  if (fsPersonalState.countdownTimer) {
    clearInterval(fsPersonalState.countdownTimer);
    fsPersonalState.countdownTimer = null;
  }
}

function startFeishuBindCountdown(owner = fsPersonalState.owner) {
  if (!fsPersonalOwnerActive(owner)) return;
  if (fsPersonalState.countdownTimer) clearInterval(fsPersonalState.countdownTimer);
  const timer = setInterval(() => {
    if (!fsPersonalOwnerActive(owner) || fsPersonalState.countdownTimer !== timer) return;
    const secs = Math.max(0, Math.ceil((fsPersonalState.bindExpiresAt - Date.now()) / 1000));
    const el = $("#fs-bind-countdown");
    if (el) el.textContent = `${secs}s`;
    if (secs <= 0) {
      clearInterval(timer);
      fsPersonalState.countdownTimer = null;
      if (fsPersonalState.sessionId) refreshFeishuBindCode();
    }
  }, 1000);
  fsPersonalState.countdownTimer = timer;
}

async function refreshFeishuBindCode() {
  const owner = fsPersonalState.owner;
  const sessionId = fsPersonalState.sessionId;
  if (!sessionId || !fsPersonalOwnerActive(owner) || fsPersonalState.refreshInFlight) return;
  fsPersonalState.refreshInFlight = true;
  try {
    const data = await api(`/api/me/feishu-personal/register/${sessionId}/refresh-code`, { method: "POST" });
    if (!fsPersonalOwnerActive(owner) || fsPersonalState.sessionId !== sessionId) return;
    fsPersonalState.bindCommand = data.bind_command;
    fsPersonalState.bindExpiresAt = (data.bind_code_expires_at || 0) * 1000;
    fsPersonalRender(owner);
    startFeishuBindCountdown(owner);
  } catch (err) {
    if (fsPersonalOwnerActive(owner)) flash(err.message, "error");
  } finally {
    fsPersonalState.refreshInFlight = false;
  }
}

async function cancelFeishuPersonal() {
  const owner = fsPersonalState.owner;
  const sessionId = fsPersonalState.sessionId;
  if (!sessionId || !fsPersonalOwnerActive(owner)) return;
  try {
    await api(`/api/me/feishu-personal/register/${sessionId}/cancel`, { method: "POST" });
  } catch { /* 忽略 */ }
  if (!fsPersonalOwnerActive(owner) || fsPersonalState.sessionId !== sessionId) return;
  stopFeishuPersonalPoll(owner);
  fsPersonalState.sessionId = "";
  fsPersonalRender(owner);
}

function openBindGuide(sectionId) {
  // 渠道绑定块在独立「渠道绑定」分栏里，先切过去再滚动并展开步骤
  if (sectionId.endsWith("-bind")) {
    switchSettingsTab("bind");
  }
  const sec = document.getElementById(sectionId);
  if (!sec) return;
  sec.scrollIntoView({ behavior: "smooth", block: "start" });
  const details = sec.querySelector("details.bind-steps");
  if (details) details.open = true;
}

function pushChannelsHtml(user) {
  const opts = [];
  if (user.telegram_chat_id) opts.push(["telegram", "Telegram"]);
  if (feishuChannelBound(user)) opts.push(["feishu", "飞书"]);
  if (user.wecom_webhook) opts.push(["wecom", "企业微信"]);
  if (user.bark_key) opts.push(["bark", "Bark"]);
  if (user.webpush_bound) opts.push(["webpush", "浏览器通知"]);
  if (!opts.length) return `<p class="muted">还没有绑定推送渠道，先完成上方任一渠道绑定后即可选择。</p>`;
  const selected = (user.push_channels || "").split(",").map((s) => s.trim()).filter(Boolean);
  const isChecked = (ch) => selected.length === 0 || selected.includes(ch);
  return opts.map(([ch, label]) => `
    <label class="channel-pick ${isChecked(ch) ? "selected" : ""}" data-channel="${ch}" title="${escapeHtml(label)}">
      <input type="checkbox" value="${ch}" ${isChecked(ch) ? "checked" : ""}
        onchange="this.closest('.channel-pick').classList.toggle('selected', this.checked)">
      <span class="ch-icon-wrap">${CHANNEL_ICONS[ch]}</span>
      <span class="ch-check">✓</span>
    </label>`).join("");
}

async function savePushChannels() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const boxes = [...document.querySelectorAll("#push-channels-box input[type=checkbox]")];
  if (!boxes.length) return;
  const channels = boxes.filter((b) => b.checked).map((b) => b.value);
  if (!channels.length) {
    flash("请至少保留一个推送通道；全部不想要可以关闭「新帖推送开关」", "error");
    return;
  }
  try {
    await api("/api/me", { method: "PUT", body: JSON.stringify({ push_channels: channels.join(",") }) });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    state.user.push_channels = channels.join(",");
    flash("已保存");
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function saveNotify() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  try {
    await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({ notify_enabled: $("#set-notify").value === "1" }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash("已保存");
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function saveDailyReport() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  try {
    await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({ daily_report_enabled: $("#set-daily").value === "1" }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash("已保存");
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function saveTranslateTwitter() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  try {
    const on = $("#set-x-translate").value === "1";
    await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({ translate_twitter: on }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    state.user.translate_twitter = on;
    flash("已保存");
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

function toggleDnd() {
  // 免打扰开关与时段输入联动：关闭时时段输入禁用并置灰
  const on = $("#dnd-enabled").checked;
  const field = $("#dnd-range-field");
  if (field) field.classList.toggle("is-off", !on);
  $("#dnd-start").disabled = !on;
  $("#dnd-end").disabled = !on;
}

async function saveDnd() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const enabled = $("#dnd-enabled").checked;
  const start = $("#dnd-start").value;
  const end = $("#dnd-end").value;
  const allowFav = $("#dnd-fav").checked;
  if (enabled && (!start || !end || start === end)) {
    flash("请设置不同的开始与结束时间", "error");
    return;
  }
  try {
    await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({
        dnd_start: enabled ? start : "",
        dnd_end: enabled ? end : "",
        dnd_allow_favorite: allowFav,
      }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    state.user.dnd_start = enabled ? start : "";
    state.user.dnd_end = enabled ? end : "";
    state.user.dnd_allow_favorite = allowFav;
    flash("已保存");
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

let pendingBind = null; // { channel, code, expiresAt }——轮询重绘后恢复显示

function renderBindResult(channel, code) {
  const el = channel === "telegram" ? $("#bind-result-telegram") : $("#bind-result-feishu");
  if (!el) return;
  const guide = state.user.push_guide || {};
  if (channel === "telegram" && guide.telegram_bot_username) {
    const link = `https://t.me/${encodeURIComponent(guide.telegram_bot_username)}?start=bind_${code}`;
    el.innerHTML = `
      <p style="margin:10px 0 6px">点击下方按钮，Telegram 会自动打开机器人并完成绑定：</p>
      <a class="btn-normal" href="${link}" target="_blank" rel="noopener">一键绑定 Telegram</a>
      <p class="muted" style="margin-top:8px">按钮没反应？复制 <b>${escapeHtml(code)}</b> 粘贴给机器人也可以。</p>`;
  } else {
    const label = channel === "telegram" ? "Telegram" : "飞书";
    el.innerHTML = `
      <p style="margin:10px 0 6px">复制绑定码，粘贴发送给${label}机器人（自动识别，无需命令）：</p>
      <b style="font-size:var(--text-icon);letter-spacing:3px;font-family:var(--font-mono);font-variant-numeric:tabular-nums">${escapeHtml(code)}</b>`;
  }
}

async function bindChannel(channel) {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  try {
    const data = await api("/api/me/bind-code", { method: "POST" });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    pendingBind = {
      channel,
      code: data.code,
      expiresAt: Date.now() + (data.expires_in_seconds || 600) * 1000,
    };
    renderBindResult(channel, data.code);
    startSettingsPoll();
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function saveCustomTgBot() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const botToken = ($("#set-custom-tg").value || "").trim();
  if (!botToken) {
    flash("请先粘贴你的 bot token", "error");
    return;
  }
  try {
    await api("/api/me", { method: "PUT", body: JSON.stringify({ telegram_bot_token: botToken }) });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash("自建机器人已绑定");
    await reloadSettings(routeSeq);
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function unbindChannel(channel) {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const label = channel === "telegram_chat_id" ? "Telegram"
    : channel === "telegram_bot_token" ? "Telegram（自建机器人）"
    : channel === "feishu_personal" ? "飞书个人机器人"
    : channel === "wecom" ? "企业微信"
    : channel === "bark" ? "Bark" : "飞书";
  if (!confirm(`确认解绑 ${label}？解绑后将不再通过该方式推送（共享机器人绑定不受影响）。`)) return;
  try {
    if (channel === "feishu_personal") {
      stopFeishuPersonalPoll();
      fsPersonalState.sessionId = "";
      await api("/api/me/feishu-personal", { method: "DELETE" });
      if (!routeStillActive(routeSeq) || token !== state.token
        || sessionGeneration !== imaMountState.sessionGeneration) return;
      flash(`已解绑 ${label}`);
      await reloadSettings(routeSeq);
      return;
    }
    const body = channel === "feishu"
      ? { feishu_open_id: "", feishu_chat_id: "" }
      : channel === "wecom"
        ? { wecom_webhook: "" }
        : channel === "bark"
          ? { bark_key: "" }
        : channel === "telegram_bot_token"
          ? { telegram_bot_token: "", telegram_chat_id: "" }
        : { telegram_chat_id: "" };
    await api("/api/me", { method: "PUT", body: JSON.stringify(body) });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(`已解绑 ${label}`);
    await reloadSettings(routeSeq);
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function saveWecomWebhook() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const webhook = ($("#set-wecom-webhook").value || "").trim();
  if (webhook && !/^https:\/\/qyapi\.weixin\.qq\.com\/cgi-bin\/webhook\/send\?key=/.test(webhook)) {
    flash("webhook 地址无效，应为 https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=... 格式", "error");
    return;
  }
  try {
    await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({ wecom_webhook: webhook }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(webhook ? "企业微信已绑定" : "企业微信已解绑");
    await reloadSettings(routeSeq);
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function saveBarkKey() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const key = ($("#set-bark-key").value || "").trim();
  try {
    await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({ bark_key: key }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(key ? "Bark 已绑定" : "Bark 已解绑");
    await reloadSettings(routeSeq);
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

function webPushSupported() {
  return window.isSecureContext
    && "Notification" in window
    && "serviceWorker" in navigator
    && "PushManager" in window;
}

function urlBase64ToUint8Array(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

async function enableWebPush() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  if (!webPushSupported()) {
    flash("当前环境不支持浏览器通知，请用 Chrome 或 Edge，并打开 HTTPS", "error");
    return;
  }
  const btns = document.querySelectorAll('[data-channel="webpush"] .channel-btn');
  btns.forEach((b) => { b.disabled = true; });
  try {
    const perm = await Notification.requestPermission();
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    if (perm !== "granted") {
      flash("未授予通知权限，请在浏览器设置里允许本站通知", "error");
      return;
    }
    const key = state.user && state.user.vapid_public_key;
    if (!key) {
      flash("服务端未就绪，请刷新后再试", "error");
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    const json = sub.toJSON();
    await api("/api/me/webpush", {
      method: "POST",
      body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash("浏览器通知已开启");
    await reloadSettings(routeSeq);
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message || "开启失败", "error");
  } finally {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    btns.forEach((b) => { b.disabled = false; });
  }
}

async function disableWebPush() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  if (!confirm("关闭后，所有已开启的 Chrome / Edge 都不再弹出通知。")) return;
  try {
    const reg = await navigator.serviceWorker.ready;
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    const sub = await reg.pushManager.getSubscription();
    if (sub) await sub.unsubscribe();
  } catch {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    /* 本地订阅清不掉也不挡服务端关闭 */
  }
  if (!routeStillActive(routeSeq) || token !== state.token
    || sessionGeneration !== imaMountState.sessionGeneration) return;
  try {
    await api("/api/me/webpush", { method: "DELETE" });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash("浏览器通知已关闭");
    await reloadSettings(routeSeq);
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function saveKeywords() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const keywords = ($("#set-keywords").value || "")
    .split(/[\n,]/)
    .map((k) => k.trim())
    .filter(Boolean);
  try {
    await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({ keywords }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    if (state.user) state.user.keywords = keywords;
    flash(`已保存 ${keywords.length} 个关键词`);
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function saveKeywordsMatchReports() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const input = $("#set-kw-reports");
  const on = !!(input && input.checked);
  try {
    const data = await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({ keywords_match_reports: on }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    if (state.user) state.user.keywords_match_reports = !!(data && data.keywords_match_reports);
    flash(on ? "已开启研报匹配" : "已关闭研报匹配");
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    if (input) input.checked = !on;
    flash(err.message, "error");
  }
}

function syncReportWatchChips() {
  const watching = userKeywordSet();
  document.querySelectorAll(".ima-doc-tag.is-watch").forEach((btn) => {
    const on = watching.has(String(btn.dataset.tag || "").trim());
    btn.classList.toggle("is-selected", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    btn.title = on ? "已在关键词提醒中" : "加入关键词提醒";
  });
}

async function toggleReportKeyword(tag) {
  const name = String(tag || "").trim();
  if (!name || !isReportWatchableTag(name)) return;
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const current = [...userKeywordSet()];
  if (current.includes(name)) {
    flash("已在关键词提醒中");
    return;
  }
  if (current.length >= KEYWORDS_MAX_COUNT) {
    flash(`关键词最多 ${KEYWORDS_MAX_COUNT} 个`, "error");
    return;
  }
  const keywords = [...current, name];
  try {
    const data = await api("/api/me", {
      method: "PUT",
      body: JSON.stringify({ keywords, keywords_match_reports: true }),
    });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    if (state.user) {
      state.user.keywords = keywords;
      state.user.keywords_match_reports = data?.keywords_match_reports !== false;
    }
    syncReportWatchChips();
    flash("已加入关键词提醒，每日更新后推送");
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function saveLlm() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const payload = {
    llm_api_base: ($("#set-llm-base").value || "").trim(),
    llm_api_key: ($("#set-llm-key").value || "").trim(),
    llm_model: ($("#set-llm-model").value || "").trim(),
  };
  try {
    await api("/api/me", { method: "PUT", body: JSON.stringify(payload) });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(payload.llm_api_key ? "已保存，将用你的模型" : "已保存，将用站点默认模型");
    await reloadSettings(routeSeq);
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
  }
}

async function loadLlmModels() {
  const routeSeq = routeRenderSeq;
  const list = $("#set-llm-model-list");
  const input = $("#set-llm-model");
  try {
    const data = await api("/api/me/llm-models", {
      method: "POST",
      body: JSON.stringify({
        llm_api_base: ($("#set-llm-base").value || "").trim(),
        llm_api_key: ($("#set-llm-key").value || "").trim(),
      }),
    });
    if (!routeStillActive(routeSeq)) return;
    const models = Array.isArray(data.models) ? data.models : [];
    if (list) {
      list.innerHTML = models.map((id) => `<option value="${escapeHtml(id)}"></option>`).join("");
    }
    if (input && models.length && !input.value) input.value = models[0];
    flash(models.length ? `已加载 ${models.length} 个模型` : "接口未返回模型，可手填模型名");
  } catch (err) {
    if (routeStillActive(routeSeq)) flash(err.message || "拉取模型失败", "error");
  }
}

async function savePassword() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const oldPw = $("#pw-old").value;
  const newPw = $("#pw-new").value;
  const confirmPw = $("#pw-confirm").value;
  if (!oldPw || newPw.length < 6) {
    flash("请填写原密码，新密码至少 6 位", "error");
    return;
  }
  if (newPw !== confirmPw) {
    flash("两次输入的新密码不一致", "error");
    return;
  }
  try {
    await api("/api/me/password", {
      method: "POST",
      body: JSON.stringify({ old_password: oldPw, new_password: newPw }),
    });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    $("#pw-old").value = $("#pw-new").value = $("#pw-confirm").value = "";
    flash("密码已修改");
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  }
}

async function genBindCode() {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  try {
    const data = await api("/api/me/bind-code", { method: "POST" });
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    pendingBind = {
      channel: "any",
      code: data.code,
      expiresAt: Date.now() + (data.expires_in_seconds || 600) * 1000,
    };
    $("#bind-result").innerHTML =
      `绑定码：<b style="font-size:var(--text-icon);letter-spacing:3px;font-family:var(--font-mono);font-variant-numeric:tabular-nums">${escapeHtml(data.code)}</b>` +
      `（${Math.floor(data.expires_in_seconds / 60)} 分钟内有效）<br>` +
      `发给机器人：<code>/bind ${escapeHtml(data.code)}</code>`;
    startSettingsPoll();
  } catch (err) {
    if (!routeStillActive(routeSeq) || token !== state.token
      || sessionGeneration !== imaMountState.sessionGeneration) return;
    flash(err.message, "error");
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
  imaMountState.folderPanelGroupId = button?.getAttribute("aria-expanded") === "true" ? "" : groupId;
  renderImaFolderTree(groupId);
}

function renderImaFolderTree(groupId) {
  const tree = $("#ima-folder-tree");
  if (!tree) return;
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
    <input type="search" class="form-control ima-acl-search" placeholder="搜索并添加用户" role="combobox" aria-expanded="false" aria-autocomplete="list" aria-label="搜索并添加用户" aria-controls="${listId}" autocomplete="off" oninput="filterAclSuggest(this)" onkeydown="onAclSearchKey(event)">
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
  if (!needle) {
    close();
    if (empty) empty.hidden = true;
    return;
  }
  const hits = (_aclCandidateUsers || [])
    .map((u) => String(u.username || ""))
    .filter((name) => name && !granted.has(name) && name.toLowerCase().includes(needle));
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
      <button type="button" class="btn-ghost" onclick="fetchAclCandidateUsers(true).then(renderImaGroupAcl)">重试</button>`;
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

function switchKnowledgeSettingsTab(tab) {
  if (tab === "cicc") tab = "local"; // 旧页签记忆迁移：中金已并入本地库
  const allowed = ["collect", "zsxq", "storage", "local"];
  const next = allowed.includes(tab) ? tab : "collect";
  if (next === "local") {
    loadLocalLibraries();
    loadCiccStatus();
    startCiccPoll();
  } else {
    stopCiccPoll();
  }
  if (next === "storage") loadStorageHealth();
  try { sessionStorage.setItem(KS_TAB_KEY, next); } catch { /* ignore */ }
  document.querySelectorAll(".ks-tab").forEach((btn) => {
    const on = btn.dataset.tab === next;
    btn.classList.toggle("is-on", on);
    btn.setAttribute("aria-selected", String(on));
  });
  document.querySelectorAll(".ks-panel").forEach((panel) => {
    panel.classList.toggle("is-on", panel.dataset.panel === next);
  });
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
  return `<section class="section-panel ks-panel" data-panel="storage" id="ima-storage-panel">
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

async function loadAdminStats(seq = _adminRenderSeq, authoritativeImaStatus = null) {
  if (!routeStillActive(seq)) return false;
  const tab = statsTabFromHash();
  if (tab === "legacy-dashboard") {
    replaceRoute("admin/dashboard");
    return false;
  }
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
      const retry = `<div><button type="button" class="btn-normal" onclick="loadAdminStats(${seq})">重试</button></div>`;
      const error = $("#stats-poll-error");
      if (error && document.body.contains(error)) {
        error.innerHTML = `<div class="ima-folder-state ima-folder-error" role="alert">${escapeHtml(message)}${retry}</div>`;
      } else {
        const body = $("#admin-body");
        if (body) body.innerHTML = emptyState(message, retry);
      }
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
  const xq = s.xueqiu_cookie || {};
  const tw = s.twitter_cookie || {};
  const ima = s.ima_credentials || {};
  const imaCollector = s.ima_collector || {};
  const pure = imaCollector.config || {};
  const collectorDraft = confirmedCollectorDraft ? null
    : (ownerSnapshot || (ownerIsCurrent && owner.putCompleted ? null : pendingCollectorDraft));
  const collector = collectorDraft || pure;
  const collectorGroups = collectorDraft?.groups || pure.groups || [];
  const zq = s.zsxq_cookie || {};
  const zc = s.zsxq_cache || { files: 0, bytes: 0 };
  const zcSize = fmtCacheBytes(zc.bytes);
  $("#admin-body").innerHTML = `
    <div id="stats-poll-error"></div>
    <div class="settings-tabs" role="tablist" aria-label="数据源管理">
      <button type="button" class="settings-tab active" role="tab" id="tab-config" aria-selected="true" aria-controls="st-config" data-tab="config" onclick="switchStatsTab('config')">抓取设置</button>
      <button type="button" class="settings-tab" role="tab" id="tab-cookies" aria-selected="false" aria-controls="st-cookies" data-tab="cookies" onclick="switchStatsTab('cookies')">Cookie 管理</button>
      <button type="button" class="settings-tab" role="tab" id="tab-proxies" aria-selected="false" aria-controls="st-proxies" data-tab="proxies" onclick="switchStatsTab('proxies')">代理</button>
      <button type="button" class="settings-tab" role="tab" id="tab-plaza" aria-selected="false" aria-controls="st-plaza" data-tab="plaza" onclick="switchStatsTab('plaza')">广场显示</button>
    </div>
    <div id="st-plaza" class="settings-tab-panel" role="tabpanel" aria-labelledby="tab-plaza" style="display:none">
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">动态广场显示</h2>
          <p class="section-meta">控制时间线角标和「全部」里的内容。自动：该源启用大V 为 0 时隐藏；也可手动显示或隐藏。</p></div>
        </header>
        <div id="plaza-sources">${plazaSourceRowsHtml(s.plaza_sources)}</div>
      </section>
    </div>
    <div id="st-config" class="settings-tab-panel" role="tabpanel" aria-labelledby="tab-config">
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">抓取设置</h2>
          <p class="section-meta">按抓取档位分组配置；保存后即时生效，无需重启。</p></div>
        </header>
        <div class="cfg-stack">
          <div class="cfg-grid">
            <div class="cfg-group">
              <p class="cfg-group-title">基础轮询</p>
              <div class="cfg-fields">
                <label class="cfg-field" title="全局轮询间隔（所有大V的最低抓取频率）">
                  <span>轮询间隔<span class="cfg-unit">秒</span></span>
                  <input id="pc-interval" type="number" class="form-control" min="1" max="3600" value="${s.polling_config.interval_seconds}">
                </label>
                <label class="cfg-field" title="标记为「优先」的大V用更短间隔抓取，新帖更早送达">
                  <span>优先大V间隔<span class="cfg-unit">秒</span></span>
                  <input id="pc-priority" type="number" class="form-control" min="1" max="600" value="${s.polling_config.priority_interval_seconds}">
                </label>
                <label class="cfg-field" title="普通大V帖子按此周期合并推送摘要；0 = 实时单条推送">
                  <span>合并推送周期<span class="cfg-unit">秒</span></span>
                  <input id="pc-digest" type="number" class="form-control" min="0" max="86400" value="${s.polling_config.digest_interval_seconds}">
                </label>
              </div>
            </div>
            <div class="cfg-group">
              <p class="cfg-group-title">自适应降频 <span class="hint">无新帖自动拉长</span></p>
              <div class="cfg-fields">
                <label class="cfg-field" title="普通大V长期无新帖时封顶的空轮间隔，控制对平台的请求频率">
                  <span>普通大V空轮封顶<span class="cfg-unit">秒</span></span>
                  <input id="pc-nc" type="number" class="form-control" min="5" max="86400" value="${s.polling_config.normal_idle_cap_seconds}">
                </label>
                <label class="cfg-field" title="优先大V长期无新帖时封顶的空轮间隔">
                  <span>优先大V空轮封顶<span class="cfg-unit">秒</span></span>
                  <input id="pc-pc" type="number" class="form-control" min="5" max="86400" value="${s.polling_config.priority_idle_cap_seconds}">
                </label>
                <label class="cfg-field" title="X 直抓失败期间封顶的抓取间隔，失败期放慢以免空打接口">
                  <span>X失败封顶<span class="cfg-unit">秒</span></span>
                  <input id="pc-xc" type="number" class="form-control" min="5" max="86400" value="${s.polling_config.x_fallback_cap_seconds}">
                </label>
              </div>
            </div>
            <div class="cfg-group">
              <p class="cfg-group-title">雪球组合 <span class="hint">调仓实时推送</span></p>
              <div class="cfg-fields">
                <label class="cfg-field" title="组合抓取频率；无新帖时自动拉长（2 倍步进），调仓出现即恢复">
                  <span>组合基础间隔<span class="cfg-unit">秒</span></span>
                  <input id="pc-cb" type="number" class="form-control" min="5" max="3600" value="${s.polling_config.combination_base_seconds}">
                </label>
                <label class="cfg-field" title="组合长期无调仓时封顶的空轮间隔，避免空转刷接口">
                  <span>组合空轮封顶<span class="cfg-unit">秒</span></span>
                  <input id="pc-cc" type="number" class="form-control" min="5" max="86400" value="${s.polling_config.combination_idle_cap_seconds}">
                </label>
              </div>
            </div>
            <div class="cfg-group">
              <p class="cfg-group-title">次要大V <span class="hint">低频合并</span></p>
              <div class="cfg-fields">
                <label class="cfg-field" title="次要大V基础抓取间隔（低于普通大V频率）">
                  <span>抓取间隔<span class="cfg-unit">秒</span></span>
                  <input id="pc-si" type="number" class="form-control" min="60" max="86400" value="${s.polling_config.secondary_interval_seconds}">
                </label>
                <label class="cfg-field" title="次要大V长期无新帖时封顶的空轮间隔">
                  <span>空轮封顶<span class="cfg-unit">秒</span></span>
                  <input id="pc-sc" type="number" class="form-control" min="60" max="86400" value="${s.polling_config.secondary_idle_cap_seconds}">
                </label>
                <label class="cfg-field" title="次要大V帖子按此周期合并推送；0 = 实时推送">
                  <span>推送周期<span class="cfg-unit">秒</span></span>
                  <input id="pc-sd" type="number" class="form-control" min="0" max="86400" value="${s.polling_config.secondary_digest_interval_seconds}">
                </label>
                <label class="cfg-field" title="合并推送最低条数：周期内积压不足此数则不推送、继续攒，够数才推">
                  <span>最低条数<span class="cfg-unit">条</span></span>
                  <input id="pc-sd-min" type="number" class="form-control" min="1" max="100" value="${s.polling_config.secondary_min_digest_count ?? 1}">
                </label>
              </div>
            </div>
          </div>
          <div class="cfg-group">
            <p class="cfg-group-title">通道</p>
            <div class="cfg-flags">
              <label class="cfg-field cfg-check" title="X 内容自动翻译成中文（配置 TWITTER_COOKIE 后走 X 官方翻译，质量同网页版）">
                <input id="pc-translate" type="checkbox" ${s.polling_config.translate_twitter_content ? "checked" : ""}>
                <span class="cfg-flag-text">
                  <span>X 内容自动翻译成中文</span>
                  <span class="cfg-check-desc">抓取时保存译文和原文；用户可在推送设置里选看哪一种</span>
                </span>
              </label>
              <label class="cfg-field cfg-check" title="关闭后全部退回旧版 sendMessage + HTML，配图走相册">
                <input id="pc-tg-rich" type="checkbox" ${s.polling_config.telegram_rich_messages !== false ? "checked" : ""}>
                <span class="cfg-flag-text">
                  <span>Telegram Rich Message</span>
                  <span class="cfg-check-desc">标题分层、表格、图文一条；关掉则用原来的 HTML</span>
                </span>
              </label>
            </div>
          </div>
          <div class="cfg-group">
            <p class="cfg-group-title">保活与定时</p>
            <div class="cfg-fields">
              <label class="cfg-field" title="雪球保活探测间隔；0 = 关闭自动保活">
                <span>雪球探测<span class="cfg-unit">秒</span></span>
                <input id="pc-probe" type="number" class="form-control" min="0" max="86400" value="${s.polling_config.source_probe_interval_seconds}">
              </label>
              <label class="cfg-field" title="登录态自动保活间隔；0 = 关闭">
                <span>cookie保活<span class="cfg-unit">秒</span></span>
                <input id="pc-keepalive" type="number" class="form-control" min="0" max="86400" value="${s.polling_config.cookie_keepalive_interval_seconds}">
              </label>
              <label class="cfg-field" title="每日精选推送的小时（0-23，北京时间）">
                <span>每日精选<span class="cfg-unit">时</span></span>
                <input id="pc-daily" type="number" class="form-control" min="0" max="23" value="${s.polling_config.daily_report_hour}">
              </label>
            </div>
          </div>
        </div>
        <div class="cfg-save-row">
          <button type="button" class="btn-normal" id="pc-save" onclick="savePollingConfig()">保存抓取设置</button>
        </div>
        <p class="section-meta"><a href="/admin/knowledge" onclick="event.preventDefault();go('admin/knowledge')">IMA 与知识星球设置已移至研报库设置</a></p>
      </section>
    </div>
    <div id="st-cookies" class="settings-tab-panel" role="tabpanel" aria-labelledby="tab-cookies" style="display:none">
      <div id="cookie-repair-inline"></div>
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">雪球 Cookie</h2>
          <p class="section-meta">${cookieUpdatedLabel(xq)}${xq.preview ? ` · 预览 ${escapeHtml(xq.preview)}` : ""}${s.keepalive_interval_seconds > 0 ? ` · 每 ${Math.round(s.keepalive_interval_seconds / 3600)} 小时探测` : ""}。登录 xueqiu.com → F12 → Application → Cookies，复制整串后保存，即时生效。</p></div>
        </header>
        <label class="field-label" for="xq-cookie">雪球 Cookie</label>
        <textarea id="xq-cookie" class="form-control cookie-paste" rows="4" placeholder="xq_a_token=...; u=..."></textarea>
        <div class="toolbar" style="margin-top:12px">
          <button type="button" class="btn-normal" onclick="saveXueqiuCookie()">保存雪球 Cookie</button>
          <button type="button" class="btn-ghost" onclick="pasteCookieField('xq-cookie')">从剪贴板填入</button>
          ${xq.set && !xq.from_env ? `<button type="button" class="btn-ghost danger" onclick="clearSavedCookie('xueqiu','雪球')" aria-label="清除雪球 Cookie">清除</button>` : ""}
        </div>
      </section>
      <section class="section-panel">
        <header class="section-head"><div><h2 class="section-title">微博 Cookie</h2>
        <p class="section-meta">${cookieUpdatedLabel(s.weibo_cookie)}。用微博 App 扫码后自动保存，无需复制。</p></div></header>
        <div class="toolbar">
          <button type="button" class="btn-normal" id="wb-qr-start" onclick="startWeiboQr()">微博扫码登录</button>
          ${s.weibo_cookie?.set && !s.weibo_cookie.from_env ? `<button type="button" class="btn-ghost danger" onclick="clearSavedCookie('weibo','微博')" aria-label="清除微博 Cookie">清除</button>` : ""}
        </div>
        <div id="wb-qr-box" class="qr-box"></div>
      </section>
      <section class="section-panel">
        <header class="section-head">
          <div><h2 class="section-title">X Cookie</h2>
          <p class="section-meta">${cookieUpdatedLabel(tw)}${tw.preview ? ` · 预览 ${escapeHtml(tw.preview)}` : ""}。登录 x.com → F12 → Application → Cookies，复制整串（需含 auth_token 与 ct0），保存即时生效。</p></div>
        </header>
        <label class="field-label" for="tw-cookie">X Cookie</label>
        <textarea id="tw-cookie" class="form-control cookie-paste" rows="4" placeholder="auth_token=...; ct0=..."></textarea>
        <div class="toolbar" style="margin-top:12px">
          <button type="button" class="btn-normal" onclick="saveTwitterCookie()">保存 X Cookie</button>
          <button type="button" class="btn-ghost" onclick="pasteCookieField('tw-cookie')">从剪贴板填入</button>
          ${tw.set && !tw.from_env ? `<button type="button" class="btn-ghost danger" onclick="clearSavedCookie('twitter','X')" aria-label="清除 X Cookie">清除</button>` : ""}
        </div>
      </section>
      <p class="section-meta"><a href="/admin/knowledge" onclick="event.preventDefault();go('admin/knowledge')">IMA 与知识星球设置已移至研报库设置</a></p>
    </div>
    <div id="st-proxies" class="settings-tab-panel" role="tabpanel" aria-labelledby="tab-proxies" style="display:none"></div>`;
  renderStatsData(s);
  if (statsLoadError) {
    const error = $("#stats-poll-error");
    const retry = `<div><button type="button" class="btn-normal" onclick="loadAdminStats(${seq})">重试</button></div>`;
    if (error) error.innerHTML = `<div class="ima-folder-state ima-folder-error" role="alert">${escapeHtml(statsLoadError)}${retry}</div>`;
  }
  switchStatsTab(statsTabFromHash());
  return true;
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
      <div class="ks-tabs" role="tablist">
        <button type="button" class="ks-tab is-on" data-tab="collect" onclick="switchKnowledgeSettingsTab(this.dataset.tab)">采集</button>
        <button type="button" class="ks-tab" data-tab="zsxq" onclick="switchKnowledgeSettingsTab(this.dataset.tab)">星球</button>
        <button type="button" class="ks-tab" data-tab="storage" onclick="switchKnowledgeSettingsTab(this.dataset.tab)">存储</button>
        <button type="button" class="ks-tab" data-tab="local" onclick="switchKnowledgeSettingsTab(this.dataset.tab)">本地库</button>
      </div>
      <section class="section-panel ks-panel is-on" data-panel="collect">
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
      <section class="section-panel ks-panel" data-panel="zsxq">
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
    <section class="section-panel ks-panel" data-panel="local" id="local-libs-panel">
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
  switchKnowledgeSettingsTab(savedTab);
  if (imaCollector.running) startImaProgressPoll();
  else {
    stopImaProgressPoll();
    applyImaCollectorProgress(imaCollector);
  }
  startDashboardLiveTimer();
  return true;
}

function plazaSourceEffect(row) {
  if (row.mode === "hide") return "已手动隐藏";
  if (row.mode === "show") return "已手动显示";
  return row.enabled_kols > 0 ? "有启用大V，自动显示" : "启用大V 为 0，自动隐藏";
}

function plazaSourceRowsHtml(rows) {
  const modes = [["auto", "自动"], ["show", "显示"], ["hide", "隐藏"]];
  return (rows || []).map((row) => {
    const label = PLATFORM_LABELS[row.platform] || row.platform;
    const shown = row.visible ? "广场显示中" : "广场已隐藏";
    return `<div class="plaza-src" data-platform="${escapeHtml(row.platform)}">
      <div class="plaza-src-head">
        <span class="plaza-src-icon" data-platform="${escapeHtml(row.platform)}">${PLATFORM_ICONS[row.platform] || ""}</span>
        <div class="plaza-src-copy">
          <p class="plaza-src-name">${escapeHtml(label)}</p>
          <p class="plaza-src-meta">启用大V ${row.enabled_kols} · ${shown} · ${plazaSourceEffect(row)}</p>
        </div>
      </div>
      <div class="plaza-src-modes" role="radiogroup" aria-label="${escapeHtml(label)} 广场显示">
        ${modes.map(([value, text]) => `
          <button type="button" class="plaza-src-mode ${row.mode === value ? "selected" : ""}" role="radio" data-platform="${escapeHtml(row.platform)}" data-mode="${value}" aria-checked="${row.mode === value}" onclick="setPlazaSourceMode(this.dataset.platform,this.dataset.mode)">${text}</button>`).join("")}
      </div>
    </div>`;
  }).join("");
}

function applyPlazaSources(sources) {
  const box = $("#plaza-sources");
  if (box) box.innerHTML = plazaSourceRowsHtml(sources);
  if (state.user) {
    state.user.plaza_platforms = (sources || []).filter((row) => row.visible).map((row) => row.platform);
    const vis = new Set(state.user.plaza_platforms);
    if (Array.isArray(state.user.timeline_platforms)) {
      state.user.timeline_platforms = state.user.timeline_platforms.filter((p) => vis.has(p));
    }
  }
}

async function setPlazaSourceMode(platform, mode) {
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  const current = document.querySelector(`.plaza-src[data-platform="${CSS.escape(platform)}"] .plaza-src-mode.selected`);
  if (current && current.dataset.mode === mode) return;
  try {
    const data = await api("/api/admin/plaza-sources", {
      method: "PUT",
      body: JSON.stringify({ visibility: { [platform]: mode } }),
    });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    applyPlazaSources(data.sources);
    flash("广场显示已更新");
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  }
}

function staleEnabledKolRows(rows, nowMs) {
  const cutoff = (nowMs || Date.now()) - STALE_KOL_HOURS * 3600 * 1000;
  const live = (rows || []).filter((k) => k.enabled && (k.subscriber_count == null || Number(k.subscriber_count) > 0));
  const stale = live.filter((k) => {
    if (!k.last_post_at) return true;
    const ts = parseDbUtcMs(k.last_post_at);
    return ts == null || ts < cutoff;
  });
  stale.sort((a, b) => String(a.last_post_at || "").localeCompare(String(b.last_post_at || "")));
  return stale;
}

function staleEnabledKols(rows, nowMs) {
  return staleEnabledKolRows(rows, nowMs).slice(0, STALE_KOL_LIMIT);
}

function openAdminKolFromHealth(name) {
  state.adminKolsQ = String(name || "").trim();
  state.adminKolsPage = 0;
  go("admin/kols");
}

function sourceNeverStarted(src) {
  return !src.ok
    && !src.last_ok_at
    && !(Number(src.ok_24h) || 0)
    && !(Number(src.fail_24h) || 0)
    && !(Number(src.consecutive_fails) || 0);
}

function sourceCredentialGap(src, cookieItems) {
  const keys = new Set((cookieItems || []).map((item) => item.key));
  const plat = src.platform;
  if ((plat === "xueqiu" || plat === "combination") && (keys.has("xq-missing") || keys.has("xq-bad"))) return true;
  if (plat === "weibo" && keys.has("wb-bad")) return true;
  if (plat === "twitter" && (keys.has("x-bad") || keys.has("x-missing"))) return true;
  if (plat === "zsxq" && (keys.has("zq-missing") || keys.has("zq-bad"))) return true;
  return false;
}

function sourceStatusNote(src) {
  if (src.platform !== "twitter" || src.direct_mode !== "fallback") return "";
  return ` <span class="status-warn" title="${escapeHtml(src.direct_fallback_reason || "")}">直抓失败</span>`;
}

function sourceStatusCell(src, cookieItems) {
  const note = sourceStatusNote(src);
  if (src.ok) return `<td class="status-ok" data-label="状态">正常${note}</td>`;
  if (sourceCredentialGap(src, cookieItems)) {
    return `<td class="dash-status-cred" data-label="状态">凭据缺失${note}</td>`;
  }
  if (sourceNeverStarted(src)) {
    return `<td class="muted" data-label="状态">未开始${note}</td>`;
  }
  if (src.consecutive_fails >= 3) {
    return `<td class="status-fail" data-label="状态">持续失败${note}</td>`;
  }
  return `<td class="status-warn" data-label="状态">暂无成功${note}</td>`;
}

function sourceRowsHtml(sources, cookieItems) {
  const rows = sources || [];
  if (!rows.length) return '<tr class="ak-empty"><td colspan="4" class="muted">暂无数据源</td></tr>';
  return rows.map((src) => {
    const warn = src.warn_24h ? ` <span class="status-warn">⚠${src.warn_24h}</span>` : "";
    const counts = `<span class="muted dash-source-counts">${src.ok_24h} / ${src.fail_24h}${warn}</span>`;
    const hint = [
      src.consecutive_fails ? `连续失败 ${src.consecutive_fails}` : "",
      src.next_retry_at ? `下次重试 ${fmtTs(src.next_retry_at)}` : "",
      src.last_ok_at ? `最近成功 ${fmtTs(src.last_ok_at)}` : "",
    ].filter(Boolean).join(" · ");
    return `
    <tr${hint ? ` title="${escapeHtml(hint)}"` : ""}>
      <td data-label="平台">${PLATFORM_LABELS[src.platform] || escapeHtml(src.platform)}</td>
      ${sourceStatusCell(src, cookieItems)}
      <td class="ak-hide-mobile dash-source-rate" data-label="24h 成功率">${rateBar(src.success_rate_24h)}${counts}</td>
      ${sourceCauseCell(src, cookieItems)}
    </tr>`;
  }).join("");
}

function sourceCauseCell(src, cookieItems) {
  if (src.last_error) {
    return `<td class="muted dash-source-cause" data-label="最近错误" title="${escapeHtml(src.last_error)}">${escapeHtml(src.last_error.slice(0, 40))}</td>`;
  }
  if (sourceCredentialGap(src, cookieItems)) {
    return `<td class="dash-source-cause" data-label="最近错误"><button type="button" class="linkish" onclick="go('admin/stats?tab=cookies')">去更新 Cookie</button></td>`;
  }
  if (sourceNeverStarted(src)) {
    return `<td class="muted dash-source-cause ak-hide-mobile" data-label="最近错误">还没跑过</td>`;
  }
  return `<td class="muted dash-source-cause" data-label="最近错误">—</td>`;
}

function abnormalSourceEvents(events, limit) {
  return (events || []).filter((e) => e.status !== "ok").slice(0, limit || 5);
}

function sourceEventRowsHtml(events) {
  const rows = abnormalSourceEvents(events);
  if (!rows.length) return "";
  return `<div class="dash-events">${rows.map((e) => `<div class="dash-event">
    <span class="dash-event-dot ${escapeHtml(e.status)}"></span>
    <span class="muted dash-event-time">${escapeHtml(fmtDbTime(e.created_at))}</span>
    <span class="dash-event-platform">${PLATFORM_LABELS[e.platform] || escapeHtml(e.platform)}</span>
    <span class="${e.status === "warn" ? "status-warn" : "status-fail"}">${e.status === "warn" ? "警告" : "失败"}</span>
    <span class="muted dash-event-detail" title="${escapeHtml(e.detail || "")}">${escapeHtml(e.detail || "")}</span>
  </div>`).join("")}</div>`;
}

function dashboardFetchMetaHtml(s) {
  const items = [];
  items.push(s.last_poll_at ? `最近抓取 ${fmtTs(s.last_poll_at)}` : "尚未轮询");
  if (s.last_poll_duration_ms) items.push(`耗时 ${(Number(s.last_poll_duration_ms) / 1000).toFixed(1)} 秒`);
  if (s.enabled_kols != null) items.push(`活跃抓取 ${s.active_kols || 0}/${s.enabled_kols}`);
  items.push(`轮询 ${s.polling_interval_seconds || "—"} 秒`);
  items.push(s.retry_pending
    ? `<span class="status-warn">待重试 ${s.retry_pending} 条</span>`
    : `<span class="status-ok">重试空闲</span>`);
  const alerts = s.alerts || {};
  if (alerts.push_alert_last_at) items.push(`<span class="status-warn">推送告警 ${escapeHtml(fmtTs(alerts.push_alert_last_at))}</span>`);
  if (alerts.x_direct_alert_at) items.push(`<span class="status-warn">X失败告警 ${escapeHtml(fmtTs(alerts.x_direct_alert_at))}</span>`);
  if (alerts.cookie_keepalive_alert_at) items.push(`<span class="status-warn">cookie保活告警 ${escapeHtml(fmtTs(alerts.cookie_keepalive_alert_at))}</span>`);
  if (alerts.xueqiu_probe_alert_at) items.push(`<span class="status-warn">雪球探测告警 ${escapeHtml(fmtTs(alerts.xueqiu_probe_alert_at))}</span>`);
  return `<p class="section-meta dash-fetch-meta" id="dash-fetch-meta">${items.map((bit) => `<span>${bit}</span>`).join("")}</p>`;
}

function fmtRelativeFromMs(ms, nowMs) {
  if (ms == null) return "从未";
  const hours = Math.floor(Math.max(0, (nowMs || Date.now()) - ms) / 3600000);
  if (hours < 1) return "不到 1 小时前";
  if (hours < 48) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

function staleKolsHtml(rows) {
  const all = staleEnabledKolRows(rows);
  const stale = all.slice(0, STALE_KOL_LIMIT);
  if (!all.length) {
    return `<p class="muted" id="kol-health-empty">有订阅的大V 在 ${STALE_KOL_HOURS} 小时内都抓到过新帖</p>`;
  }
  const extra = all.length > stale.length ? `，列出 ${stale.length} 个` : "";
  const nowMs = Date.now();
  return `<p class="dash-stale-verdict" id="kol-health-verdict">${all.length} 个有订阅大V超过 ${STALE_KOL_HOURS} 小时没抓到新帖${extra}</p>
    <ul class="dash-stale-list">${stale.map((h) => {
      const when = h.last_post_at ? fmtRelativeFromMs(parseDbUtcMs(h.last_post_at), nowMs) : "从未";
      const plat = PLATFORM_LABELS[h.platform] || h.platform || "";
      const subs = Number(h.subscriber_count);
      const subBit = Number.isFinite(subs) && subs > 0 ? ` · ${subs} 订` : "";
      return `<li>
        <button type="button" class="linkish" data-name="${escapeHtml(h.name)}" onclick="openAdminKolFromHealth(this.dataset.name)">${escapeHtml(h.name)}</button>
        <span class="muted">${escapeHtml(plat)} · ${escapeHtml(when)}${escapeHtml(subBit)}</span>
      </li>`;
    }).join("")}</ul>`;
}

function dutyStripHtml(s) {
  const sources = s.sources || [];
  const cookies = cookieRepairItems(s);
  let never = 0;
  let cred = 0;
  let failing = 0;
  sources.forEach((src) => {
    if (src.ok) return;
    if (sourceCredentialGap(src, cookies)) cred += 1;
    else if (sourceNeverStarted(src)) never += 1;
    else failing += 1;
  });
  const staleAll = staleEnabledKolRows(s.kol_health).length;
  const pending = Number(s.pending_kol_requests) || 0;
  const bits = [];
  if (failing) bits.push(`<li class="is-fail">${failing} 条管线持续失败</li>`);
  if (cred) bits.push(`<li class="is-warn">${cred} 条凭据缺失</li>`);
  if (never) bits.push(`<li class="is-idle">${never} 条尚未开始抓取</li>`);
  if (staleAll) bits.push(`<li class="is-fail">${staleAll} 个有订阅大V停更</li>`);
  if (pending) bits.push(`<li class="is-warn"><button type="button" class="linkish" onclick="go('admin/requests')">${pending} 条待审批</button></li>`);
  if (!bits.length) bits.push(`<li class="is-ok">管线正常，没有停更例外</li>`);
  return `<ul class="dash-duty-strip" id="dash-duty-strip">${bits.join("")}</ul>`;
}

function renderStatsData(s) {
  const banner = cookieRepairBanner(s);
  const dashCookie = $("#dash-cookie-slot");
  if (dashCookie) dashCookie.innerHTML = banner;
  const cookieInline = $("#cookie-repair-inline");
  if (cookieInline) cookieInline.innerHTML = banner;
  const meta = $("#dash-fetch-meta");
  if (meta) meta.outerHTML = dashboardFetchMetaHtml(s);
  const pollErr = $("#stats-poll-error");
  if (pollErr) {
    pollErr.innerHTML = s.last_poll_error
      ? `<div class="notice">最近轮询异常：${escapeHtml(s.last_poll_error)}</div>`
      : "";
  }
  if (s.plaza_sources) applyPlazaSources(s.plaza_sources);
  const dutySlot = $("#dash-duty-strip-slot");
  if (dutySlot) dutySlot.innerHTML = dutyStripHtml(s);
  const tbody = $("#sources-table");
  if (tbody) tbody.innerHTML = sourceRowsHtml(s.sources, cookieRepairItems(s));
  const events = $("#dash-source-events");
  if (events) events.innerHTML = sourceEventRowsHtml(s.recent_source_events);
  const kh = $("#kol-health");
  if (kh) kh.innerHTML = staleKolsHtml(s.kol_health);
  const stalePanel = $("#dash-stale-panel");
  if (stalePanel) stalePanel.hidden = !staleEnabledKolRows(s.kol_health).length;
  const imaCollectorStatus = $("#ima-collector-status");
  if (imaCollectorStatus && s.ima_collector) imaCollectorStatus.textContent = imaCollectorStatusText(s.ima_collector);
  const imaGroupDiscoveryStatus = $("#ima-group-discovery-status");
  if (imaGroupDiscoveryStatus && s.ima_collector) {
    imaGroupDiscoveryStatus.innerHTML = imaGroupDiscoveryStatusText(s.ima_collector);
  }
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

async function runStorageConsistency() {
  const btn = document.getElementById("ima-consistency-run");
  const box = document.getElementById("ima-consistency");
  if (!box) return;
  if (btn) { btn.disabled = true; btn.textContent = "体检中…"; }
  try {
    await api("/api/admin/ima-storage/consistency/run", { method: "POST" });
    await new Promise((r) => setTimeout(r, 5000));
    const rep = await api("/api/admin/ima-storage/consistency");
    const items = [];
    if ((rep.corrupt_count ?? 0) > 0) items.push(`损坏 PDF ${rep.corrupt_count} 个（${(rep.corrupt || []).slice(0, 3).join("、")}…）`);
    if ((rep.dup_id_count ?? 0) > 0) items.push(`重复报告 id ${rep.dup_id_count} 个`);
    if ((rep.bad_name_count ?? 0) > 0) items.push(`命名不规范 ${rep.bad_name_count} 个`);
    if ((rep.empty_dir_count ?? 0) > 0) items.push(`空目录 ${rep.empty_dir_count} 个`);
    if ((rep.no_sidecar_count ?? 0) > 0) items.push(`无摘要元数据 ${rep.no_sidecar_count} 篇`);
    box.hidden = false;
    box.innerHTML = items.length
      ? `<p class="section-meta">体检发现：${items.join("；")}。${rep.files ?? ""} 个 PDF 已扫描。</p>`
      : `<p class="section-meta">体检通过：未发现异常。</p>`;
  } catch (err) {
    box.hidden = false;
    box.innerHTML = `<p class="muted">体检失败：${escapeHtml(err.message)}</p>`;
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "一致性体检"; }
  }
}

async function runStorageDedup() {
  try {
    const r = await api("/api/admin/ima-storage/dedup", { method: "POST" });
    flash(r.queued ? "去重任务已启动（低优先级，日志见存储机 ui_dedup.log）" : "去重任务下发失败", r.queued ? "ok" : "error");
  } catch (err) { flash(`下发失败：${err.message}`, "error"); }
}

async function loadStorageHealth() {
  const box = document.getElementById("ima-storage-health");
  const details = document.getElementById("ima-storage-details");
  if (!box) return;
  try {
    const h = await api("/api/admin/ima-storage/health");
    const st = h.storage || {};
    const disk = st.disk || {};
    const pct = Number(disk.pct) || 0;
    const color = pct >= 90 ? "var(--color-danger)" : pct >= 80 ? "var(--color-warning)" : "var(--color-success)";
    const wg = st.wg || {};
    const nfs = st.nfs || {};
    const cats = ((st.archive || {}).categories || []).slice(0, 8)
      .map((c) => `<li>${escapeHtml(c.name)}：${c.files} 篇 / ${(c.bytes / 1073741824).toFixed(2)} GB</li>`).join("");
    const alertsState = (await api("/api/admin/ima-storage/alerts")) || {};
    const cfg = alertsState.settings || {};
    const b = h.backup || {};
    const snapItems = (b.snapshots || []).map((s) => {
      const d = s.time ? new Date(s.time) : null;
      const when = d && !Number.isNaN(d.getTime()) ? d.toLocaleString() : escapeHtml(s.time || "未知时间");
      return `<li>${when} · <code>${escapeHtml(String(s.id || "").slice(0, 8))}</code></li>`;
    }).join("");
    const backupHtml = !b.configured
      ? `<p class="muted" style="color:var(--color-danger)">备份未生效：${escapeHtml(b.reason || "存储机 env 缺 RESTIC_REPOSITORY")}，需要配置备份目标</p>`
      : snapItems
        ? `<ul class="muted" style="margin:4px 0 0;padding-left:18px">${snapItems}</ul>`
        : `<p class="muted">备份目标已配置，但还没有成功快照（${escapeHtml(b.reason || "可点「立即备份」试一次")}）</p>`;
    box.innerHTML = `
      <p class="section-meta">磁盘 <strong style="color:${color}">${disk.used_gb ?? "—"} / ${disk.total_gb ?? "—"} GB（${pct}%）</strong>
       · 归档 ${(st.archive && st.archive.files) ?? "—"} 个 PDF
       · 中德链路 ${wg.ok ? `${wg.rtt_ms ?? "—"} ms` : "不通"} · 归档挂载 ${nfs.mounted ? "正常" : "异常"}</p>
      <div class="ima-storage-bar"><div style="width:${Math.min(pct, 100)}%;background:${color}"></div></div>`;
    if (details) {
      details.innerHTML = `
      ${cats ? `<ul class="muted" style="margin:4px 0 0;padding-left:18px">${cats}</ul>` : ""}
      <p class="section-meta" style="margin:10px 0 2px"><strong>备份</strong>（快照 · 上次成功 ${b.restic_last_success ? fmtTs(b.restic_last_success) : "无"}）</p>
      ${backupHtml}
      <div class="toolbar ima-storage-alerts">
        <label>告警阈值 磁盘≥<input id="ima-alert-warn" type="number" value="${cfg.disk_warn ?? 80}">% /
        <input id="ima-alert-crit" type="number" value="${cfg.disk_crit ?? 90}">%</label>
        <label>状态过期 ≥<input id="ima-alert-stale" type="number" value="${cfg.stale_minutes ?? 30}"> 分钟</label>
        <label><input id="ima-alert-notify" type="checkbox" ${cfg.notify_enabled ? "checked" : ""}> 推送通知</label>
        <button type="button" class="btn-ghost" onclick="saveStorageAlerts()">保存告警设置</button>
        <button type="button" class="btn-ghost" onclick="runStorageDedup()">立即去重</button>
      </div>`;
    }
  } catch (err) {
    box.innerHTML = `<p class="muted">存储健康加载失败：${escapeHtml(err.message)}</p>`;
  }
}

async function saveStorageAlerts() {
  const body = {
    disk_warn: Number((document.getElementById("ima-alert-warn") || {}).value) || 80,
    disk_crit: Number((document.getElementById("ima-alert-crit") || {}).value) || 90,
    stale_minutes: Number((document.getElementById("ima-alert-stale") || {}).value) || 30,
    notify_enabled: !!(document.getElementById("ima-alert-notify") || {}).checked,
  };
  try {
    await api("/api/admin/ima-storage/alerts", { method: "PUT", body: JSON.stringify(body) });
    flash("告警设置已保存");
    loadStorageHealth();
  } catch (err) { flash(`保存失败：${err.message}`, "error"); }
}

async function refreshImaStorage() {
  const btn = $("#ima-storage-refresh");
  if (btn?.disabled) return;
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/admin/ima-storage/refresh", { method: "POST" });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    const slot = $("#ima-storage-panel");
    if (slot) slot.outerHTML = imaStoragePanelHtml(data);
    loadStorageHealth();
    flash("存储状态已刷新");
  } catch (err) {
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(err.message, "error");
  } finally {
    if (btn && document.body.contains(btn)) btn.disabled = false;
  }
}

async function backupImaStorage() {
  const btn = $("#ima-storage-backup");
  if (btn?.disabled) return;
  const routeSeq = routeRenderSeq;
  const token = state.token;
  const sessionGeneration = imaMountState.sessionGeneration;
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/admin/ima-storage/backup", { method: "POST" });
    if (!sessionOwnerStillActive(routeSeq, token, sessionGeneration)) return;
    flash(data.status === "already_running" ? "备份已在进行" : "已发送备份命令，结果稍后看存储页签");
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
  mask.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  });
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

function proxyStatusLabel(status) {
  return { unknown: "未测", ok: "可用", dead: "失效" }[status] || "未知";
}

function proxyStatusClass(status) {
  return { ok: "status-ok", dead: "status-fail" }[status] || "";
}

function proxyOptionLabel(row) {
  const auth = row.username ? `${escapeHtml(row.username)}@` : "";
  return `#${row.id} ${row.protocol} ${auth}${escapeHtml(row.host)}:${row.port}`;
}

function proxyBusy(btn, on) {
  if (!btn) return false;
  if (on && btn.disabled) return true;
  btn.disabled = on;
  return false;
}

async function loadProxyAdmin() {
  const box = $("#st-proxies");
  if (!box) return;
  const drafts = {};
  document.querySelectorAll("textarea[id^='pp-import-']").forEach((el) => {
    if (el.value) drafts[el.id] = el.value;
  });
  try {
    const [routes, pools, proxies] = await Promise.all([
      api("/api/admin/proxy-routes"),
      api("/api/admin/proxy-pools"),
      api("/api/admin/proxies"),
    ]);
    box.innerHTML = renderProxyAdmin(routes, pools.items || [], proxies.items || []);
    Object.entries(drafts).forEach(([id, text]) => {
      const el = document.getElementById(id);
      if (el) el.value = text;
    });
    ["xueqiu", "combination", "weibo", "twitter"].forEach((p) => {
      const r = routes[p] || {};
      if (r.pool_id && $(`#pr-${p}-pool`)) $(`#pr-${p}-pool`).value = String(r.pool_id);
      if (r.proxy_id && $(`#pr-${p}-proxy`)) $(`#pr-${p}-proxy`).value = String(r.proxy_id);
      syncProxyRouteInputs(p);
    });
  } catch (err) {
    box.innerHTML = `<p class="muted">${escapeHtml(err.message || "加载代理失败")}</p>
      <div class="toolbar"><button type="button" class="btn-ghost" onclick="loadProxyAdmin()">重试</button></div>`;
  }
}

function renderProxyAdmin(routes, pools, proxies) {
  const platforms = ["xueqiu", "combination", "weibo", "twitter"];
  const poolOpts = pools.length
    ? pools.map((p) => `<option value="${p.id}">${escapeHtml(p.name)}（${p.proxy_count}）</option>`).join("")
    : `<option value="">先创建代理池</option>`;
  const proxyOpts = proxies.length
    ? proxies.map((p) => `<option value="${p.id}">${proxyOptionLabel(p)}</option>`).join("")
    : `<option value="">先导入或提取代理</option>`;
  const routeRows = platforms.map((p) => {
    const r = routes[p] || { mode: "direct" };
    const label = PLATFORM_LABELS[p];
    return `<div class="proxy-route">
      <label class="cfg-field">
        <span>${label}</span>
        <select id="pr-${p}-mode" class="form-control" onchange="syncProxyRouteInputs('${p}')">
          <option value="direct"${r.mode === "direct" ? " selected" : ""}>直连</option>
          <option value="pool"${r.mode === "pool" ? " selected" : ""}>指定池</option>
          <option value="proxy"${r.mode === "proxy" ? " selected" : ""}>指定代理</option>
        </select>
      </label>
      <label class="cfg-field" id="pr-${p}-pool-wrap"${r.mode === "pool" ? "" : " hidden"}>
        <span>代理池</span>
        <select id="pr-${p}-pool" class="form-control" aria-label="${label} 代理池">${poolOpts}</select>
      </label>
      <label class="cfg-field" id="pr-${p}-proxy-wrap"${r.mode === "proxy" ? "" : " hidden"}>
        <span>指定代理</span>
        <select id="pr-${p}-proxy" class="form-control" aria-label="${label} 指定代理">${proxyOpts}</select>
      </label>
    </div>`;
  }).join("");
  const poolCards = pools.map((p) => {
    const rows = proxies.filter((x) => x.pool_id === p.id);
    const lines = rows.map((x) => {
      const statusClass = proxyStatusClass(x.status);
      return `<tr>
      <td class="ak-hide-mobile" data-label="协议">${escapeHtml(x.protocol)}</td>
      <td data-label="地址">${escapeHtml(x.host)}:${x.port}</td>
      <td class="ak-hide-mobile" data-label="账号">${escapeHtml(x.username || "—")}</td>
      <td data-label="状态"${statusClass ? ` class="${statusClass}"` : ""}>${escapeHtml(proxyStatusLabel(x.status))}</td>
      <td class="ak-hide-mobile" data-label="来源">${x.source === "extract" ? "提取" : "手动"}</td>
      <td data-label="过期">${x.expires_at ? fmtTs(x.expires_at) : "—"}</td>
      <td class="ak-actions" data-label="操作">
        <button type="button" class="btn-sm" data-proxy-test="${x.id}" onclick="testProxyNode(${x.id})">测试</button>
        <button type="button" class="btn-sm danger" onclick="deleteProxyNode(${x.id})">删除</button>
      </td>
    </tr>`;
    }).join("");
    const extract = p.kind === "extract"
      ? `<p class="section-meta proxy-extract-url">提取 ${escapeHtml(p.extract_url || "未填")}${p.last_error ? ` · 上次错误 ${escapeHtml(p.last_error)}` : ""}</p>
         <div class="toolbar"><button type="button" class="btn-ghost" data-proxy-extract="${p.id}" onclick="extractProxyPool(${p.id})">立即提取</button></div>`
      : "";
    return `<section class="section-panel">
      <header class="section-head rc-list-head"><div>
        <h2 class="section-title">${escapeHtml(p.name)} <span class="hint">${p.kind === "extract" ? "提取池" : "静态池"} · ${escapeHtml(p.protocol)}</span></h2>
        ${extract}
      </div>
      <button type="button" class="btn-ghost danger" onclick="deleteProxyPool(${p.id})">删除池</button></header>
      <label class="form-label" for="pp-import-${p.id}"><span>导入节点</span>
        <textarea id="pp-import-${p.id}" class="form-control cookie-paste proxy-import" rows="3" placeholder="host:port 或 socks5://user:pass@host:port，一行一条"></textarea>
      </label>
      <div class="toolbar">
        <button type="button" class="btn-normal" data-proxy-import="${p.id}" onclick="importProxyPool(${p.id})">导入</button>
      </div>
      <div class="table-wrap proxy-nodes-wrap">
        <table class="ak-table proxy-nodes">
          <thead><tr><th>协议</th><th>地址</th><th>账号</th><th>状态</th><th>来源</th><th>过期</th><th>操作</th></tr></thead>
          <tbody>${lines || `<tr class="ak-empty"><td colspan="7" class="muted">还没有节点，先导入或提取。</td></tr>`}</tbody>
        </table>
      </div>
    </section>`;
  }).join("");
  return `
    <section class="section-panel">
      <header class="section-head"><div>
        <h2 class="section-title">抓取出口</h2>
        <p class="section-meta">按平台选择直连、指定池或指定代理。组合与雪球常同出口，但不强制绑定。池空时本轮抓取失败，不会偷偷直连。</p>
      </div></header>
      <div class="cfg-fields">${routeRows}</div>
      <div class="cfg-save-row"><button type="button" class="btn-normal" id="pr-save" onclick="saveProxyRoutes()">保存出口</button></div>
    </section>
    <section class="section-panel">
      <header class="section-head"><div>
        <h2 class="section-title">新建代理池</h2>
        <p class="section-meta">静态池粘贴导入；提取池填商家提取 URL（一行一个 IP），按过期秒数刷新。</p>
      </div></header>
      <div class="cfg-fields">
        <label class="cfg-field"><span>名称</span><input id="pp-name" class="form-control" maxlength="40" placeholder="海外S5"></label>
        <label class="cfg-field"><span>类型</span>
          <select id="pp-kind" class="form-control" onchange="syncProxyPoolForm()">
            <option value="static">静态</option>
            <option value="extract">提取 URL</option>
          </select>
        </label>
        <label class="cfg-field"><span>协议</span>
          <select id="pp-protocol" class="form-control">
            <option value="http">HTTP</option>
            <option value="socks5">SOCKS5</option>
          </select>
        </label>
        <label class="cfg-field" id="pp-extract-wrap" hidden><span>提取 URL</span><input id="pp-extract-url" class="form-control" placeholder="https://api.example.com/get?key="></label>
        <label class="cfg-field" id="pp-expire-wrap" hidden><span>过期<span class="cfg-unit">秒</span></span><input id="pp-expire" type="number" class="form-control" min="0" value="300"></label>
        <label class="cfg-field" id="pp-refresh-wrap" hidden><span>刷新<span class="cfg-unit">秒</span></span><input id="pp-refresh" type="number" class="form-control" min="0" value="180"></label>
      </div>
      <div class="cfg-save-row"><button type="button" class="btn-normal" id="pp-create" onclick="createProxyPool()">创建</button></div>
    </section>
    ${poolCards || `<p class="muted">还没有代理池。先创建一个，再导入或提取。</p>`}`;
}

function syncProxyRouteInputs(platform) {
  const mode = $(`#pr-${platform}-mode`)?.value;
  const poolWrap = $(`#pr-${platform}-pool-wrap`);
  const proxyWrap = $(`#pr-${platform}-proxy-wrap`);
  if (poolWrap) poolWrap.hidden = mode !== "pool";
  if (proxyWrap) proxyWrap.hidden = mode !== "proxy";
}

function syncProxyPoolForm() {
  const extract = $("#pp-kind")?.value === "extract";
  ["pp-extract-wrap", "pp-expire-wrap", "pp-refresh-wrap"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.hidden = !extract;
  });
}

async function saveProxyRoutes() {
  const body = {};
  for (const p of ["xueqiu", "combination", "weibo", "twitter"]) {
    const mode = $(`#pr-${p}-mode`).value;
    body[p] = { mode };
    if (mode === "pool") {
      const poolId = $(`#pr-${p}-pool`).value;
      if (!poolId) {
        flash("请先创建代理池", "error");
        return;
      }
      body[p].pool_id = Number(poolId);
    }
    if (mode === "proxy") {
      const proxyId = $(`#pr-${p}-proxy`).value;
      if (!proxyId) {
        flash("请先导入或提取代理", "error");
        return;
      }
      body[p].proxy_id = Number(proxyId);
    }
  }
  const btn = $("#pr-save");
  if (proxyBusy(btn, true)) return;
  try {
    await api("/api/admin/proxy-routes", { method: "PUT", body: JSON.stringify(body) });
    flash("抓取出口已保存");
    loadProxyAdmin();
  } catch (err) {
    flash(err.message || "保存失败", "error");
  } finally {
    if (btn && document.body.contains(btn)) btn.disabled = false;
  }
}

async function createProxyPool() {
  const name = $("#pp-name").value.trim();
  if (!name) {
    flash("请填写代理池名称", "error");
    return;
  }
  const kind = $("#pp-kind").value;
  if (kind === "extract" && !$("#pp-extract-url").value.trim()) {
    flash("提取池需要填写提取 URL", "error");
    return;
  }
  const btn = $("#pp-create");
  if (proxyBusy(btn, true)) return;
  try {
    await api("/api/admin/proxy-pools", {
      method: "POST",
      body: JSON.stringify({
        name,
        kind,
        protocol: $("#pp-protocol").value,
        extract_url: $("#pp-extract-url").value,
        expire_seconds: Number($("#pp-expire").value || 0),
        refresh_interval_seconds: Number($("#pp-refresh").value || 0),
      }),
    });
    flash("代理池已创建");
    loadProxyAdmin();
  } catch (err) {
    flash(err.message || "创建失败", "error");
  } finally {
    if (btn && document.body.contains(btn)) btn.disabled = false;
  }
}

async function importProxyPool(poolId) {
  const text = $(`#pp-import-${poolId}`)?.value || "";
  if (!text.trim()) {
    flash("请先粘贴要导入的代理", "error");
    return;
  }
  const btn = document.querySelector(`[data-proxy-import="${poolId}"]`);
  if (proxyBusy(btn, true)) return;
  try {
    const result = await api(`/api/admin/proxy-pools/${poolId}/import`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    const ta = $(`#pp-import-${poolId}`);
    if (ta) ta.value = "";
    flash(`导入 ${result.imported} 条`);
    loadProxyAdmin();
  } catch (err) {
    flash(err.message || "导入失败", "error");
  } finally {
    if (btn && document.body.contains(btn)) btn.disabled = false;
  }
}

async function extractProxyPool(poolId) {
  const btn = document.querySelector(`[data-proxy-extract="${poolId}"]`);
  if (proxyBusy(btn, true)) return;
  try {
    const result = await api(`/api/admin/proxy-pools/${poolId}/extract`, { method: "POST" });
    flash(`提取 ${result.imported} 条`);
    loadProxyAdmin();
  } catch (err) {
    flash(err.message || "提取失败", "error");
  } finally {
    if (btn && document.body.contains(btn)) btn.disabled = false;
  }
}

async function deleteProxyPool(poolId) {
  if (!confirm("删除这个代理池及其节点？")) return;
  try {
    await api(`/api/admin/proxy-pools/${poolId}`, { method: "DELETE" });
    flash("已删除");
    loadProxyAdmin();
  } catch (err) {
    flash(err.message || "删除失败", "error");
  }
}

async function deleteProxyNode(proxyId) {
  if (!confirm("删除后需要重新导入。确定删除这个节点？")) return;
  try {
    await api(`/api/admin/proxies/${proxyId}`, { method: "DELETE" });
    flash("已删除");
    loadProxyAdmin();
  } catch (err) {
    flash(err.message || "删除失败", "error");
  }
}

async function testProxyNode(proxyId) {
  const btn = document.querySelector(`[data-proxy-test="${proxyId}"]`);
  if (proxyBusy(btn, true)) return;
  try {
    const result = await api(`/api/admin/proxies/${proxyId}/test`, { method: "POST" });
    flash(result.ok ? "测试成功" : (result.error || `测试失败 ${result.status_code || ""}`), result.ok ? "success" : "error");
    await loadProxyAdmin();
  } catch (err) {
    flash(err.message || "测试失败", "error");
    if (btn && document.body.contains(btn)) btn.disabled = false;
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

function statCard(label, value) {
  return `
    <div class="dash-stat">
      <div class="dash-stat-label">${escapeHtml(label)}</div>
      <div class="dash-stat-value">${escapeHtml(String(value))}</div>
    </div>`;
}

async function loadAdminDashboard() {
  try {
    const [d, st] = await Promise.all([api("/api/admin/dashboard"), api("/api/stats")]);
    const u = d.users || {};
    const s = d.subscriptions || {};
    const p = d.posts || {};
    const pu = d.pushes || {};
    const CHANNEL_LABELS_LOOKUP = { telegram: "Telegram", feishu: "飞书", wecom: "企业微信" };
    const rate = pu.success_rate != null ? `${pu.success_rate}%` : "—";

    // 14 天推送趋势柱状图（纯 CSS，零依赖）
    const trend = pu.trend_14d || [];
    const maxPushed = Math.max(1, ...trend.map((t) => t.pushed));
    const trendHtml = trend.length
      ? `<div class="dash-trend" role="list" aria-label="近 14 天推送趋势">${trend.map((t) => {
          const fail = Math.max(0, t.pushed - t.ok);
          // 红/绿分别按失败数/成功数相对最大值定高，二者之和 = 总推送量高度，不会溢出
          const failPct = Math.floor((fail / maxPushed) * 100);
          const okPct = Math.floor((t.ok / maxPushed) * 100);
          const tip = `${t.date}：推送 ${t.pushed} 条，成功 ${t.ok}，失败 ${fail}`;
          return `<div class="dash-trend-col" role="listitem" title="${escapeHtml(tip)}" aria-label="${escapeHtml(tip)}">
            <div class="dash-trend-bar">
              <div class="dash-trend-fail" style="height:${failPct}%"></div>
              <div class="dash-trend-ok" style="height:${okPct}%"></div>
            </div>
            <div class="dash-trend-date">${escapeHtml(t.date.slice(5))}</div>
          </div>`;
        }).join("")}</div>`
      : "";

    // 平台来源分布
    const platformRows = Object.entries(p.by_platform || {}).map(([k, v]) => {
      const total = p.total || 1;
      const w = Math.round((v / total) * 100);
      return `<div class="dash-bar-row">
        <span class="dash-bar-label">${PLATFORM_LABELS[k] || escapeHtml(k)}</span>
        <div class="dash-bar-track"><div class="dash-bar-fill" style="width:${w}%"></div></div>
        <span class="dash-bar-value">${v}</span>
      </div>`;
    }).join("");

    // 渠道推送成功率
    const channelRows = Object.entries(pu.by_channel || {}).map(([k, v]) => {
      const r = v.total ? Math.round((v.ok / v.total) * 100) : 0;
      return `<div class="dash-bar-row">
        <span class="dash-bar-label">${CHANNEL_LABELS_LOOKUP[k] || escapeHtml(k)}</span>
        <div class="dash-bar-track"><div class="dash-bar-fill ${r < 90 ? "warn" : ""}" style="width:${r}%"></div></div>
        <span class="dash-bar-value">${v.ok}/${v.total}（${r}%）</span>
      </div>`;
    }).join("");

    const platformSection = platformRows
      ? `<section class="section-panel">
          <header class="section-head"><div><h2 class="section-title">帖子来源分布</h2></div></header>
          ${platformRows}
        </section>`
      : "";
    const channelSection = channelRows
      ? `<section class="section-panel">
          <header class="section-head"><div><h2 class="section-title">渠道推送成功率（7 天）</h2></div></header>
          ${channelRows}
        </section>`
      : "";
    const splitSection = (platformSection || channelSection)
      ? `<div class="dash-split">${platformSection}${channelSection}</div>`
      : "";
    const volumeStats = `<div class="dash-stats">
          ${statCard("近 7 天推送", pu.total_7d || 0)}
          ${statCard("推送成功率", rate)}
          ${statCard("绑定渠道用户", u.bound || 0)}
        </div>`;
    const volumeBody = trendHtml
      ? `<div class="dash-volume">${volumeStats}${trendHtml}</div>`
      : volumeStats;

    if (!routeStillActive(_adminRenderSeq)) return;
    setPageTitle("全景概览");
    $("#admin-body").innerHTML = `
      <div id="dash-cookie-slot"></div>
      <div class="dash-duty-grid">
        <section class="section-panel dash-source-panel">
          <header class="section-head">
            <div>
              <h2 class="section-title">数据源健康</h2>
              <div id="dash-duty-strip-slot"></div>
              ${dashboardFetchMetaHtml(st)}
            </div>
            <div class="toolbar"><button type="button" class="btn-ghost" onclick="refreshDashboardLive()">立即刷新</button></div>
          </header>
          <div id="stats-poll-error"></div>
          <div class="table-wrap">
            <table class="ak-table dash-source-table">
              <thead><tr>
                <th scope="col">平台</th><th scope="col">状态</th>
                <th class="ak-hide-mobile" scope="col">24h 成功率</th>
                <th scope="col">最近错误</th>
              </tr></thead>
              <tbody id="sources-table"></tbody>
            </table>
          </div>
          <div id="dash-source-events"></div>
        </section>
        <section class="section-panel dash-stale-panel" id="dash-stale-panel" hidden>
          <header class="section-head"><div><h2 class="section-title">停更大V</h2></div></header>
          <div id="kol-health"></div>
        </section>
      </div>
      <section class="section-panel dash-volume-panel">
        <header class="section-head"><div><h2 class="section-title">核心指标</h2>
        <p class="section-meta">今日新帖 ${p.today || 0} · 今日推送 ${pu.today || 0} · 7 日新用户 ${u.new_7d || 0} · 注册 ${u.total || 0}</p></div></header>
        ${volumeBody}
      </section>
      ${splitSection}`;
    renderStatsData(st);
    startDashboardLiveTimer();
  } catch (err) {
    if (!routeStillActive(_adminRenderSeq)) return;
    $("#admin-body").innerHTML = emptyState("加载失败: " + err.message,
      `<div><button class="btn-normal" onclick="loadAdminDashboard()">重试</button></div>`);
  }
}

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
    if (!routeStillActive(_adminRenderSeq)) return;
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
  if (!routeStillActive(_adminRenderSeq)) return;
  const selCount = _adminKolsSelected.size;
  const rows = kols.map((k) => {
    const tier = k.priority ? "优先" : k.secondary ? "次要" : "普通";
    const orig = k.platform === "weibo"
      ? (k.original_only ? '<span class="status-ok">是</span>' : "否")
      : "—";
    const tierBtns = k.priority
      ? `<button class="btn-sm" onclick="adminTogglePriority(${k.id}, false)">改普通</button>
                <button class="btn-sm" onclick="adminToggleSecondary(${k.id}, true)">设次要</button>`
      : k.secondary
        ? `<button class="btn-sm" onclick="adminToggleSecondary(${k.id}, false)">改普通</button>
                <button class="btn-sm" onclick="adminTogglePriority(${k.id}, true)">设优先</button>`
        : `<button class="btn-sm" onclick="adminTogglePriority(${k.id}, true)">设优先</button>
                <button class="btn-sm" onclick="adminToggleSecondary(${k.id}, true)">设次要</button>`;
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
              <td data-label="状态" class="${k.enabled ? "status-ok" : "status-fail"}">${k.enabled ? "启用" : "停用"}</td>
              <td class="ak-actions" data-label="操作">
                ${tierBtns}
                <button class="btn-sm" onclick="adminToggleKol(${k.id}, ${k.enabled ? 0 : 1})">${k.enabled ? "停用" : "启用"}</button>
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
          <thead><tr><th scope="col" style="width:32px"><input type="checkbox" id="ak-checkall" onchange="adminKolTogglePage(this)" aria-label="全选当前页"></th><th scope="col">ID</th><th scope="col">平台</th><th scope="col">昵称</th><th scope="col">分类</th><th scope="col">外部ID</th><th scope="col">档位</th><th scope="col">原创</th><th scope="col">可见性</th><th scope="col">状态</th><th scope="col">操作</th></tr></thead>
          <tbody>${rows || `<tr class="ak-empty"><td colspan="11" class="muted">${state.adminKolsQ || state.adminKolsCategory || state.adminKolsStatus !== "" || state.adminKolsPlatform ? "没有匹配的大V" : "还没有大V，先用上方表单添加"}</td></tr>`}</tbody>
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
  $("#admin-kols-tabs").innerHTML = PLATFORM_TABS.map((p) => platformTabHTML(p, state.adminKolsPlatform, "switchAdminKolsPlatform")).join("");
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
  const btn = $("#ad-batch-btn");
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/kols/batch", {
      method: "POST",
      body: JSON.stringify({
        lines,
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
  mask.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      tryClose();
      return;
    }
    if (e.key === "Tab") {
      const nodes = [...mask.querySelectorAll("button, input, select, textarea")].filter((el) => !el.disabled && !el.hidden && el.offsetParent);
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });
  mask.querySelector("[data-close]").addEventListener("click", tryClose);
  // 焦点管理：打开聚焦首个输入框；无论以哪种方式关闭，焦点都还原到触发按钮
  const trigger = document.activeElement;
  const firstInput = mask.querySelector("input, select, textarea, button");
  if (firstInput) firstInput.focus();
  const observer = new MutationObserver(() => {
    if (!document.body.contains(mask)) {
      observer.disconnect();
      if (trigger && trigger.isConnected) trigger.focus();
    }
  });
  observer.observe(document.body, { childList: true });
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

async function loadAdminRequests() {
  let requests, all;
  try {
    [requests, all] = await Promise.all([
      api("/api/admin/kol-requests?status=pending"),
      api("/api/admin/kol-requests"),
    ]);
  } catch (err) {
    if (!routeStillActive(_adminRenderSeq)) return;
    $("#admin-body").innerHTML = emptyState("加载失败: " + err.message);
    return;
  }
  const done = all.filter((r) => r.status !== "pending");
  const pendingRows = requests.length === 0
    ? `<tr><td colspan="8" class="muted">暂无待审批申请</td></tr>`
    : requests.map((r) => `
        <tr>
          <td>${r.id}</td><td>${PLATFORM_LABELS[r.platform] || r.platform}</td>
          <td>${escapeHtml(r.name || "（未填）")}</td><td>${escapeHtml(r.external_id)}</td>
          <td>${escapeHtml(r.category_name || "—")}</td>
          <td>${escapeHtml(r.requester || r.user_id)}</td><td>${escapeHtml(fmtDbTime(r.created_at))}</td>
          <td>
            <button class="btn-sm" onclick="adminApproveRequest(${r.id})">通过</button>
            <button class="btn-sm danger" onclick="adminRejectRequest(${r.id})">拒绝</button>
          </td>
        </tr>`).join("");
  const historyRows = done.length === 0
    ? `<tr><td colspan="8" class="muted">暂无处理记录</td></tr>`
    : done.map((r) => `
        <tr>
          <td>${r.id}</td><td>${PLATFORM_LABELS[r.platform] || r.platform}</td>
          <td>${escapeHtml(r.name || "（未填）")}</td><td>${escapeHtml(r.external_id)}</td>
          <td>${escapeHtml(r.category_name || "—")}</td>
          <td>${escapeHtml(r.requester || r.user_id)}</td>
          <td class="${r.status === "approved" ? "status-ok" : "status-fail"}">${r.status === "approved" ? "已通过" : "已拒绝"}</td>
          <td>${escapeHtml(fmtDbTime(r.handled_at))}</td>
        </tr>`).join("");
  if (!routeStillActive(_adminRenderSeq)) return;
  $("#admin-body").innerHTML = `
    <section class="section-panel">
      <header class="section-head"><div><h2 class="section-title">添加审批</h2>
      <p class="section-meta">用户申请添加的大V，审批通过后进入订阅广场。</p></div></header>
      <div class="table-wrap">
        <table>
          <thead><tr><th scope="col">ID</th><th scope="col">平台</th><th scope="col">昵称</th><th scope="col">外部ID</th><th scope="col">分类</th><th scope="col">申请人</th><th scope="col">申请时间</th><th scope="col">操作</th></tr></thead>
          <tbody>${pendingRows}</tbody>
        </table>
      </div>
    </section>
    <section class="section-panel">
      <header class="section-head"><div><h2 class="section-title">处理记录</h2></div></header>
      <div class="table-wrap">
        <table>
          <thead><tr><th scope="col">ID</th><th scope="col">平台</th><th scope="col">昵称</th><th scope="col">外部ID</th><th scope="col">分类</th><th scope="col">申请人</th><th scope="col">状态</th><th scope="col">处理时间</th></tr></thead>
          <tbody>${historyRows}</tbody>
        </table>
      </div>
    </section>`;
}

async function adminApproveRequest(id) {
  try {
    await api(`/api/admin/kol-requests/${id}/approve`, { method: "POST" });
    flash("已通过申请，大V已进入订阅广场");
    loadAdminRequests();
  } catch (err) {
    alert("操作失败: " + err.message);
  }
}

async function adminRejectRequest(id) {
  if (!confirm("确认拒绝该申请？")) return;
  try {
    await api(`/api/admin/kol-requests/${id}/reject`, { method: "POST" });
    flash("已拒绝该申请");
    loadAdminRequests();
  } catch (err) {
    alert("操作失败: " + err.message);
  }
}

const _codesUi = {
  note: "",
  count: 5,
  expires: 7,
  filter: "available",
  q: "",
  result: null,
};

function parseDbUtcMs(s) {
  if (!s) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})$/.exec(String(s));
  if (!m) return null;
  return Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]);
}

function codeStatus(c) {
  if (c.used_by) return "used";
  if (c.revoked_at) return "revoked";
  const exp = parseDbUtcMs(c.expires_at);
  if (exp != null && exp <= Date.now()) return "expired";
  return "available";
}

function codeStatusLabel(status) {
  return { available: "可用", used: "已用", revoked: "已作废", expired: "已过期" }[status] || status;
}

function codeStatusClass(status) {
  return { available: "status-ok", used: "status-fail", revoked: "status-fail", expired: "status-warn" }[status] || "";
}

function formatInviteCopy(codeList, expiresDays, note) {
  const head = expiresDays
    ? `V Push 邀请码（一次性，${expiresDays}天内有效）`
    : "V Push 邀请码（一次性）";
  const lines = [head, ...codeList];
  if (note) lines.push(`备注：${note}`);
  return lines.join("\n");
}

function formatInviteCopyUntil(codeList, expiresAt, note) {
  const head = expiresAt
    ? `V Push 邀请码（一次性，有效期至 ${fmtDbTime(expiresAt)})`
    : "V Push 邀请码（一次性）";
  const lines = [head, ...codeList];
  if (note) lines.push(`备注：${note}`);
  return lines.join("\n");
}

function copyDataAttr(text) {
  return encodeURIComponent(String(text ?? "")).replace(/'/g, "%27");
}

function copyText(text, okMsg) {
  if (!text) return;
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(
      () => flash(okMsg || "已复制"),
      () => alert("请手动复制：\n" + text),
    );
  } else {
    alert("请手动复制：\n" + text);
  }
}

let _adminCodesSelected = new Set();

function codeCanRevoke(c) {
  return c && !c.used_by && !c.revoked_at;
}

function codeCanPurge(c) {
  const st = codeStatus(c);
  return st === "used" || st === "revoked" || st === "expired";
}

function adminCodesSelectedRows() {
  const all = state.adminCodes || [];
  return all.filter((c) => _adminCodesSelected.has(c.code));
}

function adminCodesSyncBar() {
  const bar = $("#rc-batch-bar");
  if (!bar) return;
  const selected = adminCodesSelectedRows();
  bar.style.display = _adminCodesSelected.size ? "flex" : "none";
  const strong = bar.querySelector("strong");
  if (strong) {
    const visibleSelected = document.querySelectorAll(".rc-check:checked").length;
    strong.textContent = visibleSelected < _adminCodesSelected.size
      ? `已选 ${_adminCodesSelected.size} 个（当前显示 ${visibleSelected}）`
      : `已选 ${_adminCodesSelected.size} 个`;
  }
  const revokeBtn = $("#rc-batch-revoke");
  const purgeBtn = $("#rc-batch-purge");
  if (revokeBtn) revokeBtn.disabled = !selected.some(codeCanRevoke);
  if (purgeBtn) purgeBtn.disabled = !selected.some(codeCanPurge);
}

function adminCodesToggle(el) {
  const code = el.dataset.code;
  if (!code) return;
  if (el.checked) _adminCodesSelected.add(code);
  else _adminCodesSelected.delete(code);
  adminCodesSyncBar();
  adminCodesSyncBatchChecks();
  adminCodesSyncPageCheck();
}

function adminCodesTogglePage(el) {
  document.querySelectorAll(".rc-check").forEach((c) => {
    c.checked = el.checked;
    if (el.checked) _adminCodesSelected.add(c.dataset.code);
    else _adminCodesSelected.delete(c.dataset.code);
  });
  adminCodesSyncBatchChecks();
  adminCodesSyncPageCheck();
  adminCodesSyncBar();
}

function adminCodesSyncPageCheck() {
  const el = $("#rc-checkall");
  if (!el) return;
  const boxes = [...document.querySelectorAll(".rc-check")];
  el.checked = boxes.length > 0 && boxes.every((c) => c.checked);
  el.indeterminate = boxes.some((c) => c.checked) && !el.checked;
}

function adminCodesToggleBatch(el) {
  const batchId = el.dataset.batch;
  document.querySelectorAll(`.rc-check[data-batch="${batchId}"]`).forEach((c) => {
    c.checked = el.checked;
    if (el.checked) _adminCodesSelected.add(c.dataset.code);
    else _adminCodesSelected.delete(c.dataset.code);
  });
  el.indeterminate = false;
  adminCodesSyncBatchChecks();
  adminCodesSyncPageCheck();
  adminCodesSyncBar();
}

function adminCodesSyncBatchChecks() {
  document.querySelectorAll(".rc-batch-check").forEach((el) => {
    const boxes = [...document.querySelectorAll(`.rc-check[data-batch="${el.dataset.batch}"]`)];
    el.checked = boxes.length > 0 && boxes.every((c) => c.checked);
    el.indeterminate = boxes.some((c) => c.checked) && !el.checked;
  });
}

function adminCodesClearSelect() {
  _adminCodesSelected.clear();
  document.querySelectorAll(".rc-check").forEach((c) => { c.checked = false; });
  document.querySelectorAll(".rc-batch-check").forEach((c) => {
    c.checked = false;
    c.indeterminate = false;
  });
  adminCodesSyncPageCheck();
  adminCodesSyncBar();
}

function adminCodesCopySelected() {
  const codes = [..._adminCodesSelected];
  if (!codes.length) return;
  copyText(codes.join("\n"), `已复制 ${codes.length} 个邀请码`);
}

async function adminCodesBatch(action) {
  const selected = adminCodesSelectedRows();
  const codes = action === "revoke"
    ? selected.filter(codeCanRevoke).map((c) => c.code)
    : selected.filter(codeCanPurge).map((c) => c.code);
  if (!codes.length) return;
  const skipped = selected.length - codes.length;
  const skipTip = skipped ? `（另有 ${skipped} 个${action === "revoke" ? "不可作废" : "不可删除"}，已跳过）` : "";
  const ok = action === "revoke"
    ? confirm(`将作废选中的 ${codes.length} 个未使用邀请码${skipTip}，确认？`)
    : confirm(`将从列表删除选中的 ${codes.length} 个已用/已作废/已过期邀请码${skipTip}，不可恢复。确认？`);
  if (!ok) return;
  try {
    const data = await api("/api/admin/register-codes/batch", {
      method: "POST",
      body: JSON.stringify({ codes, action }),
    });
    const serverSkipped = data.skipped || 0;
    const msg = action === "revoke"
      ? (serverSkipped ? `已作废 ${data.count} 个，跳过 ${serverSkipped} 个` : `已作废 ${data.count} 个邀请码`)
      : (serverSkipped ? `已删除 ${data.count} 个，跳过 ${serverSkipped} 个` : `已删除 ${data.count} 个邀请码`);
    flash(msg);
    _adminCodesSelected.clear();
    loadAdminCodes();
  } catch (err) {
    flash(err.message, "error");
  }
}

function saveCodesForm() {
  const note = $("#rc-note");
  const count = $("#rc-count");
  const exp = $("#rc-expires");
  const q = $("#rc-q");
  if (note) _codesUi.note = note.value;
  if (count) _codesUi.count = Number(count.value) || 5;
  if (exp) _codesUi.expires = exp.value === "" ? null : Number(exp.value);
  if (q) _codesUi.q = q.value.trim();
}

function adminCodesPreset(note) {
  const el = $("#rc-note");
  if (el) el.value = note;
  _codesUi.note = note;
  adminCodesSyncPresets();
}

function adminCodesNoteInput() {
  const el = $("#rc-note");
  _codesUi.note = el ? el.value : "";
  adminCodesSyncPresets();
}

function adminCodesSyncPresets() {
  document.querySelectorAll(".rc-preset").forEach((b) => {
    b.classList.toggle("selected", b.dataset.note === _codesUi.note);
  });
}

async function loadAdminCodes(refetch = true) {
  if (refetch || !state.adminCodes) {
    state.adminCodes = await api("/api/admin/register-codes");
  }
  const known = new Set((state.adminCodes || []).map((c) => c.code));
  for (const code of [..._adminCodesSelected]) {
    if (!known.has(code)) _adminCodesSelected.delete(code);
  }
  if (!routeStillActive(_adminRenderSeq)) return;
  const filter = _codesUi.filter;
  const expVal = _codesUi.expires == null ? "" : String(_codesUi.expires);
  const result = _codesUi.result;
  const allCodes = state.adminCodes || [];
  const tabCounts = { available: 0, used: 0, revoked: 0, expired: 0, all: allCodes.length };
  for (const c of allCodes) tabCounts[codeStatus(c)] += 1;
  const filterBtn = (key, label) =>
    `<button type="button" class="settings-tab ${filter === key ? "active" : ""}" role="tab" aria-selected="${filter === key}" data-filter="${key}" onclick="saveCodesForm();_codesUi.filter='${key}';loadAdminCodes(false)">${label} ${tabCounts[key]}</button>`;

  $("#admin-body").innerHTML = `
    <section class="section-panel">
      <header class="section-head">
        <div><h2 class="section-title">生成注册邀请码</h2>
        <p class="section-meta">一次性邀请码，按批生成；用过即废，可设有效期。</p></div>
      </header>
      <div class="rc-generate">
        <label class="rc-field rc-field-note">
          <span>备注</span>
          <input id="rc-note" class="form-control" maxlength="40" placeholder="给谁、什么场合" value="${escapeHtml(_codesUi.note)}" oninput="adminCodesNoteInput()">
        </label>
        <div class="rc-field">
          <span>常用</span>
          <div class="rc-presets" role="group" aria-label="常用备注">
            <button type="button" class="rc-preset${_codesUi.note === "内部" ? " selected" : ""}" data-note="内部" onclick="adminCodesPreset('内部')">内部</button>
            <button type="button" class="rc-preset${_codesUi.note === "朋友" ? " selected" : ""}" data-note="朋友" onclick="adminCodesPreset('朋友')">朋友</button>
          </div>
        </div>
        <label class="rc-field rc-field-count">
          <span>数量</span>
          <input id="rc-count" class="form-control" type="number" min="1" max="100" value="${escapeHtml(String(_codesUi.count))}">
        </label>
        <label class="rc-field rc-field-expires">
          <span>有效期</span>
          <select id="rc-expires" class="form-control">
            <option value="1" ${expVal === "1" ? "selected" : ""}>1天</option>
            <option value="7" ${expVal === "7" ? "selected" : ""}>7天</option>
            <option value="30" ${expVal === "30" ? "selected" : ""}>30天</option>
            <option value="" ${expVal === "" ? "selected" : ""}>永不过期</option>
          </select>
        </label>
        <div class="rc-field-submit">
          <button class="btn-normal" onclick="adminGenerateCodes()">生成</button>
        </div>
      </div>
      ${result ? renderCodesResult(result) : ""}
    </section>
    <section class="section-panel">
      <header class="section-head rc-list-head">
        <div>
          <h2 class="section-title">注册码列表</h2>
          <p class="section-meta">${tabCounts.all} 个 · ${tabCounts.available} 可用</p>
        </div>
        <div class="search-bar rc-search">
          ${SEARCH_ICON}
          <input id="rc-q" type="search" placeholder="搜索码或备注" value="${escapeHtml(_codesUi.q)}" oninput="_codesUi.q=this.value;renderCodesList()">
        </div>
      </header>
      <div class="settings-tabs rc-tabs" role="tablist" aria-label="注册码状态">
        ${filterBtn("available", "可用")}
        ${filterBtn("used", "已用")}
        ${filterBtn("revoked", "已作废")}
        ${filterBtn("expired", "已过期")}
        ${filterBtn("all", "全部")}
      </div>
      <div class="toolbar admin-batch-bar" id="rc-batch-bar" style="margin-top:10px;display:${_adminCodesSelected.size ? "flex" : "none"};align-items:center;gap:8px;flex-wrap:wrap">
        <strong>已选 ${_adminCodesSelected.size} 个</strong>
        <button type="button" class="btn-sm" onclick="adminCodesCopySelected()">复制</button>
        <button type="button" class="btn-sm" id="rc-batch-revoke" onclick="adminCodesBatch('revoke')">作废未用</button>
        <button type="button" class="btn-sm danger" id="rc-batch-purge" onclick="adminCodesBatch('delete')">清掉废码</button>
        <button type="button" class="btn-sm" onclick="adminCodesClearSelect()">取消选择</button>
      </div>
      <div class="rc-list-toolbar">
        <label class="rc-checkall">
          <input type="checkbox" id="rc-checkall" onchange="adminCodesTogglePage(this)" aria-label="全选当前筛选">
          <span>全选当前筛选</span>
        </label>
      </div>
      <div id="rc-list"></div>
    </section>`;
  renderCodesList();
  adminCodesSyncBar();
}

function renderCodesList() {
  const codes = state.adminCodes || [];
  const filter = _codesUi.filter;
  const q = (_codesUi.q || "").trim().toLowerCase();
  const filtered = codes.filter((c) => {
    if (filter !== "all" && codeStatus(c) !== filter) return false;
    if (!q) return true;
    return String(c.code).toLowerCase().includes(q) || String(c.note || "").toLowerCase().includes(q);
  });
  const groups = [];
  const byBatch = new Map();
  for (const c of codes) {
    const id = c.batch_id || c.code;
    if (!byBatch.has(id)) byBatch.set(id, []);
    byBatch.get(id).push(c);
  }
  const visibleIds = new Set(filtered.map((c) => c.batch_id || c.code));
  for (const [id, rows] of byBatch) {
    if (!visibleIds.has(id)) continue;
    groups.push({ id, rows, visible: rows.filter((c) => filtered.includes(c)) });
  }
  groups.sort((a, b) => String(b.rows[0].created_at).localeCompare(String(a.rows[0].created_at)));
  const el = $("#rc-list");
  if (el) el.innerHTML = renderCodeGroups(groups, filter);
  adminCodesSyncBatchChecks();
  adminCodesSyncPageCheck();
  adminCodesSyncBar();
}

function renderCodesResult(result) {
  const days = result.expires_in_days;
  const copy = formatInviteCopy(result.codes, days, result.note);
  return `<div class="rc-result">
    <div class="rc-result-head">
      <strong>已生成 ${result.codes.length} 个</strong>
      <div class="rc-result-actions">
        <button class="btn-sm" data-copy="${copyDataAttr(copy)}" onclick="copyText(decodeURIComponent(this.getAttribute('data-copy')), '已复制本批邀请码')">复制全部</button>
        <button class="btn-sm danger" onclick="adminRevokeBatch('${escapeHtml(result.batch_id)}', true)">作废本批未用</button>
        <button class="btn-sm" onclick="_codesUi.result=null;loadAdminCodes()">关闭</button>
      </div>
    </div>
    <div class="rc-result-codes">${result.codes.map((code) =>
      `<div class="rc-result-row"><code>${escapeHtml(code)}</code><button class="btn-sm" data-code="${escapeHtml(code)}" onclick="copyText(this.dataset.code, '已复制')">复制</button></div>`
    ).join("")}</div>
  </div>`;
}

function renderCodeGroups(groups, filter) {
  if (groups.length === 0) {
    const empty =
      filter === "available"
        ? "没有可用注册码。在上方生成一批，复制后发给对方。"
        : filter === "used"
          ? "还没有人用过邀请码。"
          : "没有符合条件的注册码。";
    return `<p class="rc-empty muted">${empty}</p>`;
  }
  return groups.map((g) => {
    const all = g.rows;
    const notes = [...new Set(all.map((c) => c.note || ""))];
    const noteLabel = notes.length === 1 ? (notes[0] || "无备注") : "备注不一";
    const available = all.filter((c) => codeStatus(c) === "available");
    const usedN = all.filter((c) => codeStatus(c) === "used").length;
    const unusedOpen = all.filter((c) => !c.used_by && !c.revoked_at);
    const expLabel = all[0].expires_at ? `过期 ${escapeHtml(fmtDbTime(all[0].expires_at))}` : "永不过期";
    const creator = all[0].created_by_name ? ` · ${escapeHtml(all[0].created_by_name)}` : "";
    const copyCodes = available.map((c) => c.code);
    const copyNote = notes.length === 1 ? notes[0] : "";
    const copy = formatInviteCopyUntil(copyCodes, all[0].expires_at, copyNote);
    return `<div class="rc-batch">
      <div class="rc-batch-head">
        <div class="rc-batch-info">
          <div class="rc-batch-title">
            <input type="checkbox" class="rc-batch-check" data-batch="${escapeHtml(g.id)}" onchange="adminCodesToggleBatch(this)" aria-label="全选本批可见" title="全选本批当前可见的注册码">
            <strong>${escapeHtml(noteLabel)}</strong>
            <span class="rc-counts">${available.length} 可用 / ${usedN} 已用</span>
          </div>
          <p class="muted rc-batch-meta">${escapeHtml(fmtDbTime(all[0].created_at))} · ${expLabel}${creator}</p>
        </div>
        <div class="rc-batch-actions">
          <button class="btn-sm" ${copyCodes.length ? "" : "disabled"} data-copy="${copyDataAttr(copy)}" onclick="copyText(decodeURIComponent(this.getAttribute('data-copy')), '已复制未用码')">复制未用</button>
          <button class="btn-sm danger" ${unusedOpen.length ? "" : "disabled"} onclick="adminRevokeBatch('${escapeHtml(g.id)}')">作废未用</button>
        </div>
      </div>
      <div class="table-wrap">
        <table class="rc-table">
          <thead><tr><th scope="col">邀请码</th><th scope="col">备注</th><th scope="col">状态</th><th scope="col">使用者</th><th scope="col">时间</th><th scope="col">操作</th></tr></thead>
          <tbody>${g.visible.map((c) => renderCodeRow(c)).join("")}</tbody>
        </table>
      </div>
    </div>`;
  }).join("");
}

function renderCodeRow(c) {
  const st = codeStatus(c);
  const when = c.used_at ? fmtDbTime(c.used_at) : c.revoked_at ? fmtDbTime(c.revoked_at) : c.expires_at ? fmtDbTime(c.expires_at) : fmtDbTime(c.created_at);
  const canRevoke = st === "available" || st === "expired";
  const checked = _adminCodesSelected.has(c.code) ? "checked" : "";
  return `<tr>
    <td data-label="邀请码"><span class="rc-code"><input type="checkbox" class="rc-check" data-code="${escapeHtml(c.code)}" data-batch="${escapeHtml(c.batch_id || c.code)}" ${checked} onchange="adminCodesToggle(this)" aria-label="选择邀请码"><code>${escapeHtml(c.code)}</code><button class="btn-sm" data-code="${escapeHtml(c.code)}" onclick="copyText(this.dataset.code, '已复制')">复制</button></span></td>
    <td data-label="备注" class="rc-note-cell">${escapeHtml(c.note || "")}</td>
    <td data-label="状态" class="${codeStatusClass(st)}">${codeStatusLabel(st)}</td>
    <td data-label="使用者">${escapeHtml(c.used_by_name || "")}</td>
    <td data-label="时间">${escapeHtml(when)}</td>
    <td data-label="操作">${canRevoke ? `<button class="btn-sm danger" data-code="${escapeHtml(c.code)}" onclick="adminRevokeCode(this.dataset.code)">作废</button>` : ""}</td>
  </tr>`;
}

async function adminRevokeCode(code) {
  if (!confirm(`确认作废注册码 ${code}？作废后无法再使用。`)) return;
  try {
    await api(`/api/admin/register-codes/${encodeURIComponent(code)}/revoke`, { method: "POST" });
    flash(`已作废邀请码 ${code}`);
    loadAdminCodes();
  } catch (err) {
    alert("作废失败: " + err.message);
  }
}

async function adminRevokeBatch(batchId, fromResult) {
  if (!confirm("将作废本批所有未使用的邀请码，确认？")) return;
  try {
    await api(`/api/admin/register-code-batches/${encodeURIComponent(batchId)}/revoke-unused`, { method: "POST" });
    flash("已作废本批未用码");
    if (fromResult) _codesUi.result = null;
    loadAdminCodes();
  } catch (err) {
    alert("作废失败: " + err.message);
  }
}

async function adminGenerateCodes() {
  saveCodesForm();
  try {
    const expiresRaw = $("#rc-expires").value;
    const expires_in_days = expiresRaw === "" ? null : Number(expiresRaw);
    const data = await api("/api/admin/register-codes", {
      method: "POST",
      body: JSON.stringify({
        count: Number($("#rc-count").value) || 5,
        note: $("#rc-note").value.trim(),
        expires_in_days,
      }),
    });
    _codesUi.result = { ...data, expires_in_days };
    _codesUi.filter = "available";
    flash(`已生成 ${data.count} 个邀请码`);
    loadAdminCodes();
  } catch (err) {
    alert("生成失败: " + err.message);
  }
}

async function loadAdminVocab() {
  // 深链：/admin/vocab?tab=tags 进标签 Tab，其余值（含无参数）进分类 Tab
  const params = routeQuery();
  const tab = params.get("tab") === "tags" ? "tags" : "categories";
  if (!routeStillActive(_adminRenderSeq)) return;
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
  if (!routeStillActive(_adminRenderSeq)) return;
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
  const data = await api("/api/tags");
  const tags = Array.isArray(data?.tags) ? data.tags : [];
  const stockNames = Array.isArray(data?.stock_names) ? data.stock_names : [];
  const stockAliases = Array.isArray(data?.stock_aliases) ? data.stock_aliases : [];
  const excludedNames = Array.isArray(data?.excluded_stock_names) ? data.excluded_stock_names : [];
  const universe = data?.universe && typeof data.universe === "object" ? data.universe : {};
  const universeCount = Number(universe.count) || 0;
  const universeUpdated = universe.updated ? String(universe.updated) : "";
  const stats = data?.stats || { total: 0, processed: 0, tagged: 0, pending: 0 };
  if (!routeStillActive(_adminRenderSeq)) return;
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
        <p class="section-meta">合并种子黑话、解析 $标记$ 新股、去掉指数/ETF 误入的股票名，并清理过期标签与碎片别名。每日自动一次，也可立即执行。标记解析跟管理员「推送设置 → AI 摘要」同一套 LLM。</p></div>
      </header>
      <p class="section-meta" style="margin-top:8px" id="tag-maintain-meta">${escapeHtml(adminMaintainSummary(data))}</p>
      ${data.maintain && data.maintain.llm_ready ? "" : `<p class="section-meta">未检测到站点 LLM。请到「推送设置 → AI 摘要」配置 OpenAI 兼容接口，或设环境变量 LLM_API_KEY。点运行仍会合并种子、清碎片和误标。</p>`}
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
    <section class="section-panel">
      <header class="section-head"><div><h2 class="section-title">当前词表（${tags.length} 个）</h2></div></header>
      <div class="tag-vocab-preview">
        ${tags.length ? tags.map((r) => `<span class="cat cat-tag">${escapeHtml(r.tag)}</span>`).join("") : "（空）"}
      </div>
    </section>`;
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

let _adminPostsSeq = 0;
const _adminPosts = [];
let _adminPostsOffset = 0;
let _adminPostsHasMore = true;
const _adminPostsExpanded = new Set();
let _adminKolsOptions = null;

async function _adminKolsSelect() {
  // 大V下拉选项（按平台分组），只拉一次缓存
  if (_adminKolsOptions) return _adminKolsOptions;
  const kols = await api("/api/kols");
  const groups = {};
  for (const k of kols) {
    const g = PLATFORM_LABELS[k.platform] || k.platform || "其他";
    (groups[g] = groups[g] || []).push(k);
  }
  _adminKolsOptions = Object.entries(groups)
    .map(([g, list]) => `<optgroup label="${escapeHtml(g)}">${list.map((k) =>
      `<option value="${k.id}" ${state.adminPostsKolId == k.id ? "selected" : ""}>${escapeHtml(k.name)}</option>`).join("")}</optgroup>`)
    .join("");
  return _adminKolsOptions;
}

function renderAdminPosts() {
  const kolsHtml = _adminKolsOptions || `<option value="">全部大V</option>`;
  if (!routeStillActive(_adminRenderSeq)) return;
  $("#admin-body").innerHTML = `
    <section class="section-panel">
      <header class="section-head">
        <div><h2 class="section-title">帖子列表</h2><p class="section-meta">已加载 ${_adminPosts.length} 条 · 点击内容展开全文 · 按大V/平台/关键词筛选</p></div>
        <div class="toolbar" style="margin-top:12px">
          <input id="ad-posts-q" class="form-control" style="margin:0;width:240px" placeholder="搜索标题/内容关键词" value="${escapeHtml(state.adminPostsQ || "")}" onkeydown="if(event.key==='Enter')adminFilterPosts()">
          <select id="ad-posts-platform" class="form-control" style="margin:0;width:auto" onchange="adminFilterPosts()">
            <option value="">全部平台</option>
            <option value="xueqiu" ${state.adminPostsPlatform === "xueqiu" ? "selected" : ""}>雪球</option>
            <option value="weibo" ${state.adminPostsPlatform === "weibo" ? "selected" : ""}>微博</option>
            <option value="twitter" ${state.adminPostsPlatform === "twitter" ? "selected" : ""}>X</option>
            <option value="zsxq" ${state.adminPostsPlatform === "zsxq" ? "selected" : ""}>知识星球</option>
          </select>
          <select id="ad-posts-kol" class="form-control" style="margin:0;width:auto" onchange="adminFilterPosts()">${kolsHtml}</select>
          <button class="btn-normal" onclick="adminFilterPosts()">筛选</button>
        </div>
      </header>
      <div class="table-wrap">
        <table>
          <thead><tr><th scope="col">ID</th><th scope="col">大V</th><th scope="col">分类</th><th scope="col">内容</th><th scope="col">时间</th><th scope="col">链接</th></tr></thead>
          <tbody>${_adminPosts.map(postRowHtml).join("")}</tbody>
        </table>
      </div>
      ${_adminPostsHasMore
        ? `<div class="toolbar" style="margin-top:14px;justify-content:center"><button class="btn-normal" onclick="adminPostsLoadMore()">加载更多</button></div>`
        : `<p class="muted" style="text-align:center;margin-top:14px">已加载全部</p>`}
    </section>`;
}

function postRowHtml(p) {
  const expanded = _adminPostsExpanded.has(p.id);
  const body = (p.title ? p.title + "\n" : "") + (p.content || "");
  const safeUrl = /^https?:\/\//i.test(p.url || "") ? p.url : "";
  return `
    <tr${expanded ? ' style="background:var(--color-surface-accent-soft)"' : ""}>
      <td>${p.id}</td><td>${escapeHtml(p.kol_name)}</td>
      <td>${escapeHtml(p.category_name || "")}</td>
      <td class="post-cell" onclick="adminTogglePost(${p.id})" title="点击展开/收起全文" role="button" tabindex="0" aria-expanded="${expanded}" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();adminTogglePost(${p.id})}">
        <pre class="content-cell">${escapeHtml(body.slice(0, expanded ? 100000 : 120))}</pre>
        <span class="muted">${expanded ? "▲ 收起" : (body.length > 120 ? "▼ 展开全文" : "")}</span>
      </td>
      <td>${escapeHtml(p.published_at)}</td>
      <td>${safeUrl ? `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener">原文</a>` : ""}</td>
    </tr>
    ${expanded ? `<tr><td colspan="6"><div class="post-detail">
        <p class="muted" style="margin-bottom:8px">类型：${p.post_type === "reply" ? "回复" : "原帖"} · 平台：${escapeHtml(p.platform)} · 外部ID：${escapeHtml(p.external_id)} · 图片：${(p.images || []).length} 张</p>
        <pre class="content-cell">${escapeHtml(body)}</pre>
      </div></td></tr>` : ""}`;
}

async function loadAdminPosts(reset = true) {
  const seq = ++_adminPostsSeq;
  const params = new URLSearchParams({ limit: "100", offset: String(reset ? 0 : _adminPostsOffset) });
  if (state.adminPostsQ) params.set("q", state.adminPostsQ);
  if (state.adminPostsPlatform) params.set("platform", state.adminPostsPlatform);
  if (state.adminPostsKolId) params.set("kol_id", state.adminPostsKolId);
  const [posts, kolsHtml] = await Promise.all([api(`/api/posts?${params}`), _adminKolsSelect()]);
  if (seq !== _adminPostsSeq) return; // 筛选条件已变，丢弃过期响应
  if (reset) {
    _adminPosts.length = 0;
    _adminPostsOffset = 0;
    _adminPostsHasMore = true;
  }
  _adminPosts.push(...posts);
  _adminPostsOffset += posts.length;
  _adminPostsHasMore = posts.length >= 100;
  _adminKolsOptions = kolsHtml;
  renderAdminPosts();
}

function adminPostsLoadMore() {
  loadAdminPosts(false);
}

function adminTogglePost(id) {
  if (_adminPostsExpanded.has(id)) _adminPostsExpanded.delete(id);
  else _adminPostsExpanded.add(id);
  renderAdminPosts();
}

async function adminFilterPosts() {
  state.adminPostsQ = $("#ad-posts-q").value.trim();
  state.adminPostsPlatform = $("#ad-posts-platform").value;
  state.adminPostsKolId = $("#ad-posts-kol").value;
  loadAdminPosts(true);
}

let _adminLogsSeq = 0;
async function loadAdminLogs() {
  const seq = ++_adminLogsSeq;
  const users = await api("/api/users");
  const logs = await api(`/api/push-logs?limit=100${state.adminLogsFilter || ""}`);
  if (seq !== _adminLogsSeq) return; // 筛选条件已变，丢弃过期响应
  if (!routeStillActive(_adminRenderSeq)) return;
  $("#admin-body").innerHTML = `
    <section class="section-panel">
      <header class="section-head">
        <div><h2 class="section-title">推送记录</h2></div>
        <div class="toolbar" style="margin-top:12px">
          <select id="ad-logs-user" class="form-control" style="margin:0;width:auto">
            <option value="">全部用户</option>
            ${users.map((u) => `<option value="${u.id}" ${state.adminLogsUserId == u.id ? "selected" : ""}>${escapeHtml(u.username)}</option>`).join("")}
          </select>
          <select id="ad-logs-channel" class="form-control" style="margin:0;width:auto">
            <option value="">全部渠道</option>
            <option value="telegram" ${state.adminLogsChannel === "telegram" ? "selected" : ""}>Telegram</option>
            <option value="feishu" ${state.adminLogsChannel === "feishu" ? "selected" : ""}>飞书</option>
            <option value="wecom" ${state.adminLogsChannel === "wecom" ? "selected" : ""}>企业微信</option>
          </select>
          <select id="ad-logs-status" class="form-control" style="margin:0;width:auto">
            <option value="">全部状态</option>
            <option value="success" ${state.adminLogsStatus === "success" ? "selected" : ""}>成功</option>
            <option value="failed" ${state.adminLogsStatus === "failed" ? "selected" : ""}>失败</option>
          </select>
          <button class="btn-normal" onclick="adminFilterLogs()">筛选</button>
        </div>
      </header>
      <div class="table-wrap">
        <table>
          <thead><tr><th scope="col">时间</th><th scope="col">用户</th><th scope="col">大V</th><th scope="col">渠道</th><th scope="col">状态</th><th scope="col">错误</th></tr></thead>
          <tbody>${logs.map((l) => `
            <tr>
              <td>${escapeHtml(fmtDbTime(l.created_at))}</td>
              <td>${escapeHtml(l.user_name || "全局")}</td>
              <td>${escapeHtml(l.kol_name)}</td>
              <td>${l.channel}</td>
              <td class="${l.status === "success" ? "status-ok" : "status-fail"}">${escapeHtml(l.status)}</td>
              <td>${escapeHtml(l.error || "")}</td>
            </tr>`).join("")}</tbody>
        </table>
      </div>
    </section>`;
}

async function loadAdminAudit() {
  const logs = await api("/api/admin/logs?limit=100");
  if (!routeStillActive(_adminRenderSeq)) return;
  $("#admin-body").innerHTML = `
    <section class="section-panel">
      <header class="section-head">
        <div>
          <h2 class="section-title">系统日志</h2>
          <p class="section-meta">内存环形缓冲的最近 500 条日志，每 5 秒自动刷新；更完整历史见 docker logs（LOG_LEVEL=DEBUG 可开启更详细日志）。</p>
        </div>
        <div class="toolbar" style="margin-top:12px">
          <select id="syslog-level" class="form-control" style="width:auto" onchange="loadAdminSysLogsPanel()">
            <option value="">全部级别</option>
            <option value="ERROR">ERROR+</option>
            <option value="WARNING">WARNING+</option>
            <option value="INFO">INFO+</option>
            <option value="DEBUG">DEBUG（仅LOG_LEVEL=DEBUG时产生）</option>
          </select>
          <input id="syslog-q" class="form-control" style="width:220px" placeholder="关键词过滤（如 推送失败 / 大V名）" onkeydown="if(event.key==='Enter')loadAdminSysLogsPanel()">
          <button class="btn-normal" onclick="loadAdminSysLogsPanel()">刷新</button>
        </div>
      </header>
      <pre class="syslog" id="syslog-pre">加载中…</pre>
    </section>
    <section class="section-panel">
      <header class="section-head">
        <div>
          <h2 class="section-title">错误记录</h2>
          <p class="section-meta">WARNING 及以上日志持久化存储（跨重启保留最近 5000 条），即使环形缓冲滚动或重启后仍可查。</p>
        </div>
        <div class="toolbar" style="margin-top:12px">
          <select id="errlog-level" class="form-control" style="width:auto" onchange="loadAdminErrorLogs()">
            <option value="">全部级别</option>
            <option value="ERROR">ERROR+</option>
            <option value="WARNING">WARNING+</option>
          </select>
          <button class="btn-normal" onclick="loadAdminErrorLogs()">刷新</button>
        </div>
      </header>
      <div class="table-wrap">
        <table>
          <thead><tr><th scope="col">时间</th><th scope="col">级别</th><th scope="col">来源</th><th scope="col">内容</th></tr></thead>
          <tbody id="errlog-body"><tr><td colspan="4" class="muted">加载中…</td></tr></tbody>
        </table>
      </div>
    </section>
    <section class="section-panel">
      <header class="section-head"><div><h2 class="section-title">操作日志</h2>
      <p class="section-meta">管理员关键操作、以及用户知识库超额（操作 ima_quota，目标是用户名）。</p></div></header>
      <div class="table-wrap">
        <table>
          <thead><tr><th scope="col">时间</th><th scope="col">管理员</th><th scope="col">操作</th><th scope="col">目标</th><th scope="col">详情</th></tr></thead>
          <tbody>${logs.length === 0 ? `<tr><td colspan="5" class="muted">暂无记录</td></tr>` : logs.map((l) => `
            <tr>
              <td>${escapeHtml(fmtDbTime(l.created_at))}</td>
              <td>${escapeHtml(l.username || "")}</td>
              <td>${escapeHtml(l.action)}</td>
              <td>${escapeHtml(l.target)}</td>
              <td class="muted">${escapeHtml(l.detail)}</td>
            </tr>`).join("")}</tbody>
        </table>
      </div>
    </section>`;
  stopSysLogsTimer();
  sysLogsTimer = setInterval(loadAdminSysLogsPanel, 5000);
  loadAdminSysLogsPanel();
  loadAdminErrorLogs();
}

async function loadAdminErrorLogs() {
  try {
    const params = new URLSearchParams({ limit: "200" });
    const levelEl = $("#errlog-level");
    const level = levelEl ? levelEl.value : "";
    if (level) params.set("level", level);
    const data = await api(`/api/admin/error-logs?${params.toString()}`);
    const rows = data.logs || [];
    const body = $("#errlog-body");
    if (!body) return;
    body.innerHTML = rows.length
      ? rows.map((r) => `
          <tr>
            <td>${escapeHtml(fmtDbTime(r.created_at))}</td>
            <td class="${r.level === "ERROR" || r.level === "CRITICAL" ? "status-fail" : ""}">${escapeHtml(r.level)}</td>
            <td class="muted">${escapeHtml(r.logger)}</td>
            <td class="muted">${escapeHtml(r.message)}</td>
          </tr>`).join("")
      : `<tr><td colspan="4" class="muted">暂无错误记录 🎉</td></tr>`;
  } catch (err) {
    const body = $("#errlog-body");
    if (body) body.innerHTML = `<tr><td colspan="4" class="muted">加载失败: ${escapeHtml(err.message)}</td></tr>`;
  }
}

let sysLogsTimer = null;

function stopSysLogsTimer() {
  if (sysLogsTimer) {
    clearInterval(sysLogsTimer);
    sysLogsTimer = null;
  }
}

async function loadAdminSysLogsPanel() {
  try {
    const params = new URLSearchParams({ limit: "500" });
    const levelEl = $("#syslog-level");
    const qEl = $("#syslog-q");
    const level = levelEl ? levelEl.value : "";
    const q = qEl ? qEl.value.trim() : "";
    if (level) params.set("level", level);
    if (q) params.set("q", q);
    const data = await api(`/api/admin/system-logs?${params.toString()}`);
    const lines = data.lines || [];
    const el = $("#syslog-pre");
    if (el) el.textContent = lines.join("\n") || "（没有匹配的日志）";
  } catch (err) {
    const el = $("#syslog-pre");
    if (el) el.textContent = "加载失败: " + err.message;
  }
}

async function adminFilterLogs() {
  const params = new URLSearchParams({ limit: "100" });
  const userId = $("#ad-logs-user").value;
  const channel = $("#ad-logs-channel").value;
  const status = $("#ad-logs-status").value;
  if (userId) params.set("user_id", userId);
  if (channel) params.set("channel", channel);
  if (status) params.set("status", status);
  state.adminLogsFilter = `&${params.toString()}`;
  state.adminLogsUserId = userId;
  state.adminLogsChannel = channel;
  state.adminLogsStatus = status;
  loadAdminLogs();
}

function backupStatusHtml(s) {
  const parts = [];
  if (s.last_ok_at) {
    parts.push(`上次<span class="status-ok">成功</span> ${escapeHtml(s.last_ok_at)}`);
  }
  if (s.last_error) {
    parts.push(`上次<span class="status-fail">失败</span> ${escapeHtml(s.last_error)}`);
  }
  if (s.last_remote_name) parts.push(`远端 ${escapeHtml(s.last_remote_name)}`);
  if (s.next_run_at) parts.push(`下次 ${escapeHtml(s.next_run_at)}`);
  if (!parts.length) {
    return `<p class="section-meta backup-status" id="backup-status">尚未执行过定时备份</p>`;
  }
  return `<p class="section-meta backup-status" id="backup-status">${parts.join(" · ")}</p>`;
}

function backupWebDAVBody() {
  const body = {
    url: $("#bk-url").value.trim(),
    username: $("#bk-user").value.trim(),
    path: $("#bk-path").value.trim() || "/vpush-backups",
    hour: Number($("#bk-hour").value),
    keep: Number($("#bk-keep").value),
  };
  const password = $("#bk-pass").value;
  if (password) body.password = password;
  return body;
}

async function loadAdminBackup() {
  const s = await api("/api/admin/backup");
  if (!routeStillActive(_adminRenderSeq)) return;
  $("#admin-body").innerHTML = `
    <section class="section-panel backup-page">
      <header class="section-head">
        <div>
          <h2 class="section-title">本机备份</h2>
          <p class="section-meta">下载当前数据库，不经过 WebDAV。</p>
        </div>
      </header>
      <div class="toolbar backup-actions">
        <button class="btn-ghost" onclick="backupDownload()">下载当前数据库</button>
      </div>
    </section>
    <section class="section-panel backup-page">
      <header class="section-head">
        <div>
          <h2 class="section-title">WebDAV 定时</h2>
          <p class="section-meta">填好后由调度每天自动上传；密码只写不回显。</p>
        </div>
      </header>
      <label class="form-label">地址
        <input id="bk-url" class="form-control" type="url" autocomplete="off" placeholder="https://example.com/webdav" value="${escapeHtml(s.url || "")}">
      </label>
      <label class="form-label">用户名
        <input id="bk-user" class="form-control" autocomplete="off" value="${escapeHtml(s.username || "")}">
      </label>
      <label class="form-label">密码
        <input id="bk-pass" class="form-control" type="password" autocomplete="new-password" placeholder="${s.password_set ? "已设置" : "WebDAV 密码"}">
      </label>
      <div class="backup-grid">
        <label class="form-label backup-path">远端目录
          <input id="bk-path" class="form-control" autocomplete="off" placeholder="/vpush-backups" value="${escapeHtml(s.path || "/vpush-backups")}">
        </label>
        <label class="form-label backup-num">每天几点
          <input id="bk-hour" class="form-control" type="number" min="0" max="23" value="${s.hour ?? 3}">
        </label>
        <label class="form-label backup-num">保留份数
          <input id="bk-keep" class="form-control" type="number" min="1" max="90" value="${s.keep ?? 14}">
        </label>
      </div>
      ${backupStatusHtml(s)}
      <div class="cfg-save-row backup-actions">
        <button class="btn-normal" onclick="saveBackupWebDAV()">保存</button>
        <button class="btn-ghost" onclick="testBackupWebDAV()">测试连接</button>
      </div>
    </section>
    <section class="section-panel backup-page">
      <header class="section-head">
        <div>
          <h2 class="section-title">恢复</h2>
          <p class="section-meta">会覆盖当前账号、订阅和帖子。恢复失败时现库不变。</p>
        </div>
      </header>
      <div class="backup-stack">
        <div class="toolbar backup-actions">
          <button id="bk-restore-webdav" class="btn-ghost danger" onclick="backupRestoreWebDAV()">从 WebDAV 恢复最新一份</button>
        </div>
        <label class="form-label">本地 .db 文件
          <input id="bk-file" class="backup-file-input" type="file" accept=".db">
        </label>
        <div class="toolbar backup-actions">
          <button id="bk-restore-upload" class="btn-ghost danger" onclick="backupRestoreUpload()">用本地备份恢复</button>
        </div>
      </div>
    </section>`;
}

async function saveBackupWebDAV() {
  try {
    await api("/api/admin/backup/webdav", {
      method: "PUT",
      body: JSON.stringify(backupWebDAVBody()),
    });
    flash("WebDAV 配置已保存");
    $("#bk-pass").value = "";
    await loadAdminBackup();
  } catch (err) {
    flash(err.message, "error");
  }
}

async function testBackupWebDAV() {
  try {
    await api("/api/admin/backup/webdav/test", {
      method: "POST",
      body: JSON.stringify(backupWebDAVBody()),
    });
    flash("WebDAV 连接正常");
  } catch (err) {
    flash(err.message, "error");
  }
}

async function backupDownload() {
  const resp = await fetch("/api/admin/backup/download", {
    headers: { Authorization: `Bearer ${state.token}` },
  });
  if (resp.status === 401) {
    logout();
    return;
  }
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    flash(typeof data.detail === "string" ? data.detail : "下载失败", "error");
    return;
  }
  const blob = await resp.blob();
  const match = /filename="?([^";]+)"?/.exec(resp.headers.get("content-disposition") || "");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = match ? match[1] : "dav-backup.db";
  a.click();
  URL.revokeObjectURL(a.href);
}

async function backupRestoreWebDAV() {
  if (!confirm("确认用备份覆盖当前数据库？当前账号、订阅和帖子都会被替换。")) return;
  const btn = $("#bk-restore-webdav");
  if (btn) btn.disabled = true;
  try {
    await api("/api/admin/backup/restore/webdav", { method: "POST" });
    flash("已从 WebDAV 恢复");
    await loadAdminBackup();
  } catch (err) {
    flash(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function backupRestoreUpload() {
  if (!confirm("确认用备份覆盖当前数据库？当前账号、订阅和帖子都会被替换。")) return;
  const input = $("#bk-file");
  if (!input?.files?.[0]) {
    flash("请选择 .db 备份文件", "error");
    return;
  }
  const btn = $("#bk-restore-upload");
  if (btn) btn.disabled = true;
  try {
    const fd = new FormData();
    fd.append("file", input.files[0]);
    const resp = await fetch("/api/admin/backup/restore/upload", {
      method: "POST",
      headers: { Authorization: `Bearer ${state.token}` },
      body: fd,
    });
    if (resp.status === 401) {
      logout();
      return;
    }
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      flash(typeof data.detail === "string" ? data.detail : "恢复失败", "error");
      return;
    }
    flash("已从本地备份恢复");
    await loadAdminBackup();
  } catch (err) {
    flash(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function userHasBoundChannel(u) {
  return !!(u.telegram_bound || u.feishu_bound || u.wecom_bound || u.bark_bound || u.webpush_bound);
}

function userChannelIconsHtml(u) {
  const bound = {
    telegram: !!u.telegram_bound,
    feishu: !!u.feishu_bound,
    wecom: !!u.wecom_bound,
    bark: !!u.bark_bound,
    webpush: !!u.webpush_bound,
  };
  const names = USER_CHANNEL_KEYS.filter((ch) => bound[ch]).map((ch) => CHANNEL_LABELS[ch]);
  const aria = names.length ? `已绑定 ${names.join("、")}` : "未绑定推送渠道";
  return `<span class="user-channels" title="${escapeHtml(aria)}" aria-label="${escapeHtml(aria)}">${
    USER_CHANNEL_KEYS.map((ch) =>
      `<span class="user-ch ${bound[ch] ? "on" : "off"}" data-channel="${ch}">${CHANNEL_ICONS[ch]}</span>`
    ).join("")
  }</span>`;
}

function adminUsersFiltered() {
  const q = (state.adminUsersQ || "").trim().toLowerCase();
  const filter = state.adminUsersFilter || "all";
  return (state.adminUsers || []).filter((u) => {
    if (filter === "admin" && !u.is_admin) return false;
    if (filter === "unbound" && userHasBoundChannel(u)) return false;
    if (filter === "push-off" && u.notify_enabled) return false;
    if (filter === "inactive" && !u.inactive) return false;
    if (!q) return true;
    return [u.username, u.origin_label, u.register_code, u.register_note].some(
      (s) => String(s || "").toLowerCase().includes(q)
    );
  });
}

function adminUserBoundLabels(u) {
  return USER_CHANNEL_KEYS.filter((ch) => u[`${ch}_bound`]).map((ch) => CHANNEL_LABELS[ch]);
}

function adminUserOriginHtml(u) {
  const label = escapeHtml(u.origin_label || "网页");
  const note = escapeHtml(u.register_note || u.register_code || "");
  if (u.origin === "invite" && note) {
    return `<div class="user-origin"><span>${label}</span><span class="muted">${note}</span></div>`;
  }
  return `<div class="user-origin"><span>${label}</span></div>`;
}

function adminUserLoginHtml(u) {
  const login = u.has_password
    ? `<span class="status-ok">可登录</span>`
    : `<span class="muted">无密码</span>`;
  const seen = u.last_login_at
    ? escapeHtml(fmtDbTime(u.last_login_at))
    : "从未登录";
  return `<div class="user-login">${login}<span class="muted">${seen}</span></div>`;
}

function adminDeleteImpact(users) {
  const list = (users || []).filter(Boolean);
  const subs = list.reduce((n, u) => n + (Number(u.subscription_count) || 0), 0);
  const bound = list.filter(userHasBoundChannel).length;
  const parts = [`订阅 ${subs} 个`];
  if (list.length === 1) {
    const names = adminUserBoundLabels(list[0]);
    if (names.length) parts.push(`已绑 ${names.join("、")}`);
  } else if (bound) {
    parts.push(`${bound} 人已绑渠道`);
  }
  return parts.join(" · ");
}

let _adminUsersSelected = new Set();
let _inactivePolicyDraft = null;
let _inactivePolicySaving = false;
let _auPolicyOpen = false;
let _inactivePreview = { marked_count: 0, purge_count: 0 };
let _inactivePreviewTimer = 0;
let _inactivePreviewSeq = 0;

function inactivePolicySaved() {
  return state.inactivePolicy || { inactive_after_days: 90, inactive_purge_after_days: 30, customized: false };
}

function inactivePolicyDraft() {
  return _inactivePolicyDraft || inactivePolicySaved();
}

function inactivePolicyRuleLabel() {
  const saved = inactivePolicySaved();
  const n = Number(saved.inactive_after_days);
  const m = Number(saved.inactive_purge_after_days);
  return saved.customized ? `规则 ${n}+${m}` : `默认 ${n}+${m}`;
}

function inactivePolicyHint(n, m, preview) {
  n = Number(n);
  m = Number(m);
  preview = preview || _inactivePreview || {};
  const marked = Number(preview.marked_count);
  const doomed = Number(preview.purge_count);
  const blast = Number.isFinite(marked)
    ? (Number.isFinite(doomed) && doomed > 0 ? `现标 ${marked} 人，下次删 ${doomed} 人` : `现标 ${marked} 人`)
    : "";
  let core;
  if (!Number.isFinite(n) || n <= 0) core = "已关闭标记与删除";
  else if (!Number.isFinite(m) || m <= 0) core = "只标记，不自动删除";
  else if (!inactivePolicySaved().customized && n === 90 && m === 30) core = `未改过 · 默认 ${n}+${m}`;
  else core = `每天扫一次 · 满 ${n + m} 天删除`;
  return blast ? `${core} · ${blast}` : core;
}

function paintInactivePolicyHint() {
  const draft = inactivePolicyDraft();
  const text = inactivePolicyHint(draft.inactive_after_days, draft.inactive_purge_after_days);
  const hint = $("#au-inactive-hint");
  const summary = document.querySelector("details.au-policy > summary .muted");
  if (hint) hint.textContent = text;
  if (summary) summary.textContent = text;
}

function adminInactivePolicySyncSave(queuePreview) {
  const nEl = $("#au-inactive-n");
  const mEl = $("#au-inactive-m");
  const btn = $("#au-inactive-save");
  if (!nEl || !mEl) return;
  _inactivePolicyDraft = {
    inactive_after_days: nEl.value,
    inactive_purge_after_days: mEl.value,
  };
  paintInactivePolicyHint();
  const saved = inactivePolicySaved();
  const dirty =
    Number(nEl.value) !== Number(saved.inactive_after_days) ||
    Number(mEl.value) !== Number(saved.inactive_purge_after_days);
  if (btn) btn.disabled = !dirty || _inactivePolicySaving;
  if (queuePreview) adminInactivePolicyQueuePreview();
}

function adminInactivePolicyQueuePreview() {
  const seq = ++_inactivePreviewSeq;
  clearTimeout(_inactivePreviewTimer);
  _inactivePreviewTimer = setTimeout(() => adminRefreshInactivePreview(seq), 360);
}

async function adminRefreshInactivePreview(seq) {
  const draft = inactivePolicyDraft();
  const n = Number(draft.inactive_after_days);
  const m = Number(draft.inactive_purge_after_days);
  if (!Number.isInteger(n) || !Number.isInteger(m) || n < 0 || n > 3650 || m < 0 || m > 3650) return;
  try {
    const data = await api(
      `/api/admin/inactive-users-policy?inactive_after_days=${n}&inactive_purge_after_days=${m}`
    );
    if (seq && seq !== _inactivePreviewSeq) return;
    _inactivePreview = {
      marked_count: Number(data.marked_count) || 0,
      purge_count: Number(data.purge_count) || 0,
    };
    paintInactivePolicyHint();
  } catch {
    /* 输入过程中的预览失败不打断保存 */
  }
}

function adminInactivePolicyKeydown(event) {
  if (event.key !== "Enter") return;
  event.preventDefault();
  adminSaveInactivePolicy();
}

function adminUsersSyncBar() {
  const bar = $("#au-batch-bar");
  if (!bar) return;
  bar.style.display = _adminUsersSelected.size ? "flex" : "none";
  const strong = bar.querySelector("strong");
  if (strong) strong.textContent = `已选 ${_adminUsersSelected.size} 人`;
}

function adminUserToggleSelect(el) {
  const id = Number(el.dataset.id);
  if (el.checked) _adminUsersSelected.add(id);
  else _adminUsersSelected.delete(id);
  adminUsersSyncBar();
  const checkall = $("#au-checkall");
  const boxes = [...document.querySelectorAll(".au-check")];
  if (checkall) {
    checkall.checked = boxes.length > 0 && boxes.every((c) => c.checked);
    checkall.indeterminate = boxes.some((c) => c.checked) && !checkall.checked;
  }
}

function adminUserTogglePage(el) {
  document.querySelectorAll(".au-check").forEach((c) => {
    c.checked = el.checked;
    const id = Number(c.dataset.id);
    if (el.checked) _adminUsersSelected.add(id);
    else _adminUsersSelected.delete(id);
  });
  el.indeterminate = false;
  adminUsersSyncBar();
}

function adminUserClearSelect() {
  _adminUsersSelected.clear();
  document.querySelectorAll(".au-check").forEach((c) => { c.checked = false; });
  const checkall = $("#au-checkall");
  if (checkall) {
    checkall.checked = false;
    checkall.indeterminate = false;
  }
  adminUsersSyncBar();
}

async function adminUsersBatch(action) {
  const ids = [..._adminUsersSelected];
  if (!ids.length) return;
  let payloadIds = ids;
  if (action === "delete") {
    const picked = ids.map((id) => (state.adminUsers || []).find((u) => u.id === id)).filter(Boolean);
    const blocked = picked.filter((u) => u.is_admin || (state.user && u.id === state.user.id)).length;
    const doomed = picked.filter((u) => !u.is_admin && !(state.user && u.id === state.user.id));
    if (!doomed.length) {
      flash(blocked ? "选中的都是管理员，已跳过" : "没有可删除的用户", "error");
      return;
    }
    const extra = blocked ? `\n将跳过 ${blocked} 个管理员。` : "";
    if (!confirm(`确认删除选中的 ${doomed.length} 个用户？${extra}\n${adminDeleteImpact(doomed)}\n删除后不可恢复。`)) return;
    payloadIds = doomed.map((u) => u.id);
  }
  try {
    const data = await api("/api/admin/users/batch", {
      method: "POST",
      body: JSON.stringify({ ids: payloadIds, action }),
    });
    const n = data.count || 0;
    const skipped = data.skipped || 0;
    if (action === "delete") {
      flash(skipped ? `已删除 ${n} 人，跳过 ${skipped} 个管理员或无效项` : `已删除 ${n} 人`);
    } else if (action === "enable_notify") {
      flash(`已开启 ${n} 人推送`);
    } else if (action === "disable_notify") {
      flash(`已关闭 ${n} 人推送`);
    }
    _adminUsersSelected.clear();
    loadAdminUsers();
  } catch (err) {
    flash(err.message, "error");
  }
}

async function loadAdminUsers() {
  let users;
  let policy;
  let collector;
  let localLibs;
  try {
    [users, policy, collector, localLibs] = await Promise.all([
      api("/api/users"),
      api("/api/admin/inactive-users-policy"),
      api("/api/admin/ima-collector").catch(() => null),
      api("/api/admin/ima-local-libraries").catch(() => null),
    ]);
  } catch (err) {
    if (!routeStillActive(_adminRenderSeq)) return;
    $("#admin-body").innerHTML = emptyState("加载失败: " + err.message);
    return;
  }
  state.adminUsers = users;
  const imaGroups = ((collector && collector.config && collector.config.groups) || [])
    .filter((group) => group && group.id && group.enabled !== false);
  const localGroups = (((localLibs && localLibs.libraries) || []) || [])
    .map((lib) => ({
      id: String(lib.group_id || ""),
      name: String(lib.name || lib.slug || lib.group_id || ""),
      enabled: Boolean(lib.enabled) && !lib.error,
      local: true,
    }))
    .filter((group) => group.id && group.name);
  state.imaKbGroups = imaGroups.concat(localGroups);
  if (policy) {
    state.inactivePolicy = policy;
    _inactivePreview = {
      marked_count: Number(policy.marked_count) || 0,
      purge_count: Number(policy.purge_count) || 0,
    };
  }
  const known = new Set(users.map((u) => u.id));
  for (const id of [..._adminUsersSelected]) {
    if (!known.has(id)) _adminUsersSelected.delete(id);
  }
  renderAdminUsers();
}

function adminUsersApplyFilter(filter) {
  const q = $("#au-q");
  if (q) state.adminUsersQ = q.value.trim();
  if (filter) state.adminUsersFilter = filter;
  renderAdminUsers();
}

async function adminSaveInactivePolicy() {
  const nEl = $("#au-inactive-n");
  const mEl = $("#au-inactive-m");
  const btn = $("#au-inactive-save");
  if (!nEl || !mEl || _inactivePolicySaving) return;
  const n = Number(nEl.value);
  const m = Number(mEl.value);
  if (!Number.isInteger(n) || !Number.isInteger(m) || n < 0 || n > 3650 || m < 0 || m > 3650) {
    flash("天数须在 0–3650", "error");
    return;
  }
  const saved = inactivePolicySaved();
  if (n === Number(saved.inactive_after_days) && m === Number(saved.inactive_purge_after_days)) return;
  _inactivePolicySaving = true;
  if (btn) btn.disabled = true;
  try {
    const seq = ++_inactivePreviewSeq;
    const preview = await api(
      `/api/admin/inactive-users-policy?inactive_after_days=${n}&inactive_purge_after_days=${m}`
    );
    if (seq !== _inactivePreviewSeq) return;
    _inactivePreview = {
      marked_count: Number(preview.marked_count) || 0,
      purge_count: Number(preview.purge_count) || 0,
    };
    paintInactivePolicyHint();
    if (
      _inactivePreview.purge_count > 0 &&
      !confirm(`下次扫描将删除 ${_inactivePreview.purge_count} 个未激活账号。确认按 ${n}+${m} 天保存？`)
    ) {
      return;
    }
    state.inactivePolicy = await api("/api/admin/inactive-users-policy", {
      method: "PUT",
      body: JSON.stringify({ inactive_after_days: n, inactive_purge_after_days: m }),
    });
    _inactivePolicyDraft = null;
    flash("已保存未激活规则");
    await loadAdminUsers();
  } catch (err) {
    flash(err.message, "error");
  } finally {
    _inactivePolicySaving = false;
    adminInactivePolicySyncSave();
  }
}

function renderAdminUsers() {
  if (!routeStillActive(_adminRenderSeq)) return;
  const body = $("#admin-body");
  if (!body) return;
  const users = state.adminUsers || [];
  const filter = state.adminUsersFilter || "all";
  const filtered = adminUsersFiltered();
  const boundN = users.filter(userHasBoundChannel).length;
  const adminN = users.filter((u) => u.is_admin).length;
  const counts = {
    all: users.length,
    admin: adminN,
    unbound: users.filter((u) => !userHasBoundChannel(u)).length,
    "push-off": users.filter((u) => !u.notify_enabled).length,
    inactive: users.filter((u) => u.inactive).length,
  };
  const tab = (key, label) =>
    `<button class="settings-tab ${filter === key ? "active" : ""}" role="tab" aria-selected="${filter === key}" onclick="adminUsersApplyFilter('${key}')">${label} ${counts[key]}</button>`;
  const emptyMsg = users.length
    ? (filter === "inactive"
      ? "没有未激活账号。领码后从未登录、没绑渠道、没订阅的才会出现。"
      : "没有匹配的用户")
    : "还没有注册用户";
  const rows = filtered.map((u) => {
    const self = state.user && u.id === state.user.id;
    const pills = `${u.is_admin ? `<span class="user-pill">管理员</span>` : ""}${self ? `<span class="user-pill muted">本人</span>` : ""}${u.username_valid === false ? `<span class="user-pill warn">登录名不合规</span>` : ""}`;
    const push = u.inactive
      ? (u.days_until_purge == null
        ? `<span class="status-warn">未激活</span>`
        : `<span class="status-warn">未激活</span><span class="muted"> · ${Number(u.days_until_purge)} 天后删除</span>`)
      : u.notify_enabled
      ? `<span class="status-ok">开启</span>${u.dnd_enabled ? `<span class="muted"> · 免打扰</span>` : ""}`
      : `<span class="status-fail">关闭</span>`;
    return `<tr>
      <td><input type="checkbox" class="au-check" data-id="${u.id}" ${_adminUsersSelected.has(u.id) ? "checked" : ""} onchange="adminUserToggleSelect(this)" aria-label="选择用户"></td>
      <td>
        <div class="user-name">
          <strong>${escapeHtml(u.username)}</strong>
          ${pills}
        </div>
      </td>
      <td>${adminUserOriginHtml(u)}</td>
      <td>${adminUserLoginHtml(u)}</td>
      <td>${userChannelIconsHtml(u)}</td>
      <td>${Number(u.subscription_count) || 0}</td>
      <td>${push}</td>
      <td>
        <button class="btn-sm" onclick="adminOpenUser(${u.id})">管理</button>
        <button class="btn-sm" onclick="adminOpenUser(${u.id}, 'push')">测试推送</button>
      </td>
    </tr>`;
  }).join("");
  body.innerHTML = `
    <section class="section-panel">
      <header class="section-head au-head">
        <div>
          <h2 class="section-title">用户管理</h2>
          <p class="section-meta">${users.length} 人 · ${adminN} 管理员 · ${boundN} 已绑定渠道 · 未激活 ${counts.inactive} · ${escapeHtml(inactivePolicyRuleLabel())}</p>
        </div>
        <div class="search-bar au-search">
          ${SEARCH_ICON}
          <input id="au-q" type="search" placeholder="搜索用户名 / 来源 / 邀请码，回车" value="${escapeHtml(state.adminUsersQ || "")}" onkeydown="if(event.key==='Enter')adminUsersApplyFilter()">
        </div>
      </header>
      <div class="settings-tabs" role="tablist" aria-label="用户筛选">
        ${tab("all", "全部")}
        ${tab("admin", "管理员")}
        ${tab("unbound", "未绑定")}
        ${tab("push-off", "推送关闭")}
        ${tab("inactive", "未激活")}
      </div>
      <div class="toolbar admin-batch-bar" id="au-batch-bar" style="margin-top:10px;display:${_adminUsersSelected.size ? "flex" : "none"};align-items:center;gap:8px;flex-wrap:wrap">
        <strong>已选 ${_adminUsersSelected.size} 人</strong>
        <button type="button" class="btn-sm" onclick="adminUsersBatch('enable_notify')">开启推送</button>
        <button type="button" class="btn-sm" onclick="adminUsersBatch('disable_notify')">关闭推送</button>
        <button type="button" class="btn-sm danger" onclick="adminUsersBatch('delete')">删除</button>
        <button type="button" class="btn-sm" onclick="adminUserClearSelect()">取消选择</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th scope="col" style="width:32px"><input type="checkbox" id="au-checkall" onchange="adminUserTogglePage(this)" aria-label="全选当前筛选"></th>
            <th scope="col">用户</th>
            <th scope="col">来源</th>
            <th scope="col">登录</th>
            <th scope="col">渠道</th>
            <th scope="col">订阅</th>
            <th scope="col">推送</th>
            <th scope="col">操作</th>
          </tr></thead>
          <tbody>${rows || `<tr><td colspan="8" class="muted">${emptyMsg}</td></tr>`}</tbody>
        </table>
      </div>
      <details class="au-policy" ${_auPolicyOpen ? "open" : ""}>
        <summary>未激活清理规则<span class="muted">${escapeHtml(inactivePolicyHint(inactivePolicyDraft().inactive_after_days, inactivePolicyDraft().inactive_purge_after_days))}</span></summary>
        <p class="section-meta">领码或网页注册后从未登录，且没有渠道、订阅和推送记录。</p>
        <div class="rc-generate au-inactive-policy">
          <label class="rc-field rc-field-num">
            <span>列为未激活 <span class="cfg-unit">天</span></span>
            <input id="au-inactive-n" class="form-control" type="number" min="0" max="3650" inputmode="numeric" value="${escapeHtml(String(inactivePolicyDraft().inactive_after_days ?? 90))}" oninput="adminInactivePolicySyncSave(true)" onkeydown="adminInactivePolicyKeydown(event)" aria-describedby="au-inactive-hint">
          </label>
          <label class="rc-field rc-field-num">
            <span>之后删除 <span class="cfg-unit">天</span></span>
            <input id="au-inactive-m" class="form-control" type="number" min="0" max="3650" inputmode="numeric" value="${escapeHtml(String(inactivePolicyDraft().inactive_purge_after_days ?? 30))}" oninput="adminInactivePolicySyncSave(true)" onkeydown="adminInactivePolicyKeydown(event)" aria-describedby="au-inactive-hint">
          </label>
          <div class="rc-field-submit">
            <button type="button" class="btn-normal" id="au-inactive-save" onclick="adminSaveInactivePolicy()">保存</button>
          </div>
          <span class="muted rc-generate-hint" id="au-inactive-hint">${escapeHtml(inactivePolicyHint(inactivePolicyDraft().inactive_after_days, inactivePolicyDraft().inactive_purge_after_days))}</span>
        </div>
      </details>
    </section>`;
  const qEl = $("#au-q");
  if (qEl) qEl.value = state.adminUsersQ || "";
  const checkall = $("#au-checkall");
  const boxes = [...document.querySelectorAll(".au-check")];
  if (checkall) {
    checkall.checked = boxes.length > 0 && boxes.every((c) => _adminUsersSelected.has(Number(c.dataset.id)));
    checkall.indeterminate = boxes.some((c) => c.checked) && !checkall.checked;
  }
  const policy = body.querySelector("details.au-policy");
  if (policy) {
    policy.addEventListener("toggle", () => { _auPolicyOpen = policy.open; });
  }
  adminInactivePolicySyncSave();
}

function closeAdminModal() {
  document.querySelectorAll(".modal-mask").forEach((el) => el.remove());
}

function adminOpenUser(userId, focus) {
  const u = (state.adminUsers || []).find((row) => row.id === userId);
  if (!u) {
    flash("用户不存在或列表已过期", "error");
    return;
  }
  const self = state.user && u.id === state.user.id;
  const origin = escapeHtml(u.origin_label || "网页");
  const loginHint = u.has_password ? "可网页登录" : "无密码，不能网页登录";
  const lastSeen = u.last_login_at ? escapeHtml(fmtDbTime(u.last_login_at)) : "从未登录";
  const kbGroups = state.imaKbGroups || [];
  const kbGranted = new Set(u.ima_kb_groups || []);
  const kbSubscribed = new Set(u.ima_kb_subscribed || []);
  const kbList = kbGroups.length
    ? `<div id="um-kb" class="um-kb-list">${kbGroups.map((group) => {
        const id = String(group.id || "");
        const name = group.name || id;
        const isSub = kbSubscribed.has(id);
        return `<label class="um-kb-item" data-kb-name="${escapeHtml(name)}"${isSub ? ` data-kb-subscribed="1"` : ""}>
          <input type="checkbox" data-kb-group="${escapeHtml(id)}"${kbGranted.has(id) ? " checked" : ""}>
          <span>${escapeHtml(name)}</span>
          ${group.local ? `<span class="muted">本地库${group.enabled === false ? " · 未启用" : ""}</span>` : ""}
          ${isSub ? `<span class="muted">已订阅</span>` : ""}
        </label>`;
      }).join("")}</div>
      <div class="toolbar">
        <button class="btn-sm" onclick="adminSaveUserKnowledge(${u.id})">保存</button>
      </div>`
    : `<p class="muted">还没有配置研报库。</p>`;
  closeAdminModal();
  const mask = document.createElement("div");
  mask.className = "modal-mask";
  mask.innerHTML = `
    <div class="modal-card user-modal" role="dialog" aria-modal="true" aria-labelledby="um-title">
      <h3 id="um-title">管理用户 · ${escapeHtml(u.username)}</h3>
      <p class="muted um-meta">${origin} · ${loginHint} · ${lastSeen}<br>ID ${u.id} · 订阅 ${Number(u.subscription_count) || 0} · 注册 ${escapeHtml(fmtDbTime(u.created_at))}</p>
      <section class="um-block">
        <h4>改名</h4>
        ${u.username_valid === false ? `<p class="muted">当前登录名不合规，保存前请改成 6-30 位中文、字母、数字、下划线或连字符，须以中文或字母开头。</p>` : ""}
        <label class="form-label">用户名
          <div class="row">
            <input id="um-name" class="form-control" maxlength="30" value="${escapeHtml(u.username)}" autocomplete="username">
            <button class="btn-sm" onclick="adminSaveUsername(${u.id})">保存</button>
          </div>
        </label>
      </section>
      <section class="um-block">
        <h4>密码</h4>
        ${u.has_password ? "" : `<p class="muted">这个账号没有密码，不能网页登录。设了密码后才能用账号登录。</p>`}
        <label class="form-label">${u.has_password ? "新密码" : "设置密码"}
          <div class="row">
            <input id="um-pass" class="form-control" type="password" minlength="6" placeholder="至少 6 位" autocomplete="new-password">
            <button class="btn-sm" onclick="adminSavePassword(${u.id})">${u.has_password ? "重置" : "设置"}</button>
          </div>
        </label>
      </section>
      ${self ? "" : `<section class="um-block">
        <h4>权限</h4>
        <div class="toolbar">
          <button class="btn-sm" onclick="adminToggleAdmin(${u.id}, ${!u.is_admin})">${u.is_admin ? "取消管理员" : "设为管理员"}</button>
        </div>
      </section>`}
      ${u.is_admin ? "" : `<section class="um-block">
        <h4>研报库</h4>
        <p class="muted">勾选后即可阅读；若对方开了「匹配研报库」，每日更新后会按他的关键词推一条摘要。取消勾选立即看不到，也不会再推该库。</p>
        ${kbList}
      </section>`}
      <section class="um-block">
        <h4>测试推送</h4>
        <label class="form-label">内容
          <textarea id="um-push-msg" class="form-control" rows="2">这是一条测试推送</textarea>
        </label>
        <div class="toolbar">
          <button class="btn-sm" id="um-push-send" onclick="adminSendTestPush(${u.id})">发送测试</button>
        </div>
        <p id="um-push-result" class="muted um-push-result" hidden></p>
      </section>
      ${self || u.is_admin ? "" : `<section class="um-block user-modal-danger">
        <h4>删除</h4>
        <p class="muted">${escapeHtml(adminDeleteImpact([u]))}。删除后不可恢复。</p>
        <button class="btn-sm danger" onclick="adminDeleteUser(${u.id})">删除用户</button>
      </section>`}
      <div class="toolbar um-close">
        <button class="btn-sm" onclick="closeAdminModal()">关闭</button>
      </div>
    </div>`;
  mask.addEventListener("click", (e) => {
    if (e.target === mask) mask.remove();
  });
  mask.addEventListener("keydown", (e) => {
    if (e.key === "Escape") mask.remove();
  });
  document.body.appendChild(mask);
  const trigger = document.activeElement;
  const first = focus === "push" ? $("#um-push-msg") : $("#um-name");
  if (first) first.focus();
  const observer = new MutationObserver(() => {
    if (!document.body.contains(mask)) {
      observer.disconnect();
      if (trigger && trigger.isConnected) trigger.focus();
    }
  });
  observer.observe(document.body, { childList: true });
}

async function adminSaveUserKnowledge(userId) {
  const items = Array.from(document.querySelectorAll("#um-kb .um-kb-item"));
  const groupIds = [];
  const revoked = [];
  for (const item of items) {
    const input = item.querySelector("[data-kb-group]");
    const groupId = String(input?.dataset.kbGroup || "").trim();
    if (!groupId) continue;
    if (input.checked) groupIds.push(groupId);
    else if (item.dataset.kbSubscribed === "1") {
      revoked.push(String(item.dataset.kbName || groupId).trim());
    }
  }
  if (revoked.length && !confirm(`取消勾选后，对方会立刻看不到这些研报库：${revoked.join("、")}。确定保存？`)) return;
  try {
    await api(`/api/admin/users/${userId}/ima-kb`, {
      method: "PUT",
      body: JSON.stringify({ group_ids: groupIds }),
    });
    closeAdminModal();
    flash("已保存");
    loadAdminUsers();
  } catch (err) {
    flash(err.message, "error");
  }
}

async function adminSaveUsername(userId) {
  const input = $("#um-name");
  const trimmed = (input ? input.value : "").trim();
  const ruleErr = usernameRuleError(trimmed);
  if (ruleErr) {
    flash(ruleErr, "error");
    return;
  }
  try {
    await api(`/api/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ username: trimmed }),
    });
    if (state.user && userId === state.user.id) {
      state.user.username = trimmed;
      renderSidebar(state.user);
      renderTopbar(state.user);
    }
    closeAdminModal();
    flash(`已重命名用户「${trimmed}」`);
    loadAdminUsers();
  } catch (err) {
    flash(err.message, "error");
  }
}

async function adminSavePassword(userId) {
  const input = $("#um-pass");
  const pw = input ? input.value : "";
  if (pw.length < 6) {
    flash("密码至少 6 位", "error");
    return;
  }
  try {
    await api(`/api/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ password: pw }),
    });
    closeAdminModal();
    flash("密码已重置");
    loadAdminUsers();
  } catch (err) {
    flash(err.message, "error");
  }
}

async function adminSendTestPush(userId) {
  const btn = $("#um-push-send");
  const msgEl = $("#um-push-msg");
  const resultEl = $("#um-push-result");
  const msg = ((msgEl && msgEl.value) || "").trim() || "这是一条测试推送";
  if (btn) btn.disabled = true;
  try {
    const data = await api("/api/admin/test-push", {
      method: "POST",
      body: JSON.stringify({ user_id: userId, message: msg }),
    });
    const lines = (data.results || []).map((r) => {
      const label = CHANNEL_LABELS[r.channel] || r.channel;
      return r.ok ? `${label}：成功` : `${label}：失败：${r.error || ""}`;
    });
    if (resultEl) {
      resultEl.hidden = false;
      resultEl.textContent = lines.join("\n") || "没有返回渠道结果";
    }
    const failed = (data.results || []).some((r) => !r.ok);
    flash(failed ? "测试推送部分失败" : "测试推送已发送", failed ? "error" : "success");
  } catch (err) {
    flash(err.message, "error");
    if (resultEl) {
      resultEl.hidden = false;
      resultEl.textContent = err.message;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function adminDeleteUser(userId) {
  const user = (state.adminUsers || []).find((u) => u.id === userId);
  if (!user) {
    flash("用户不存在或列表已过期", "error");
    return;
  }
  if (user.is_admin) {
    flash("不能删除管理员", "error");
    return;
  }
  if (!confirm(`确认删除用户「${user.username}」？\n${adminDeleteImpact([user])}\n删除后不可恢复。`)) return;
  try {
    await api(`/api/users/${userId}`, { method: "DELETE" });
    closeAdminModal();
    flash(`已删除用户「${user ? user.username : userId}」`);
    loadAdminUsers();
  } catch (err) {
    flash(err.message, "error");
  }
}

async function adminToggleAdmin(userId, makeAdmin) {
  const user = (state.adminUsers || []).find((u) => u.id === userId);
  const name = user ? user.username : String(userId);
  if (!confirm(makeAdmin ? `确认把「${name}」设为管理员？` : `确认取消「${name}」的管理员权限？`)) return;
  try {
    await api(`/api/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ is_admin: makeAdmin }),
    });
    closeAdminModal();
    flash(makeAdmin ? `已将「${name}」设为管理员` : `已取消「${name}」的管理员权限`);
    loadAdminUsers();
  } catch (err) {
    flash(err.message, "error");
  }
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
  "timeline", "home", "combinations", "mysubs", "settings",
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
    else if (page === "combinations") await renderCombinations(renderSeq);
    else if (page === "mysubs") await renderMySubs(renderSeq);
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

applyTheme(); // 与 index.html 防闪脚本同一逻辑，兜底 + 同步 meta theme-color
router();