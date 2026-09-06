const ICON_ATTRS = 'class="pt-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"';

const GRID_ICON = `<svg ${ICON_ATTRS}><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg>`;
const XUEQIU_ICON = `<img class="pt-icon" src="/xueqiu-mark.png" width="16" height="16" alt="" draggable="false" aria-hidden="true">`;
const COMBINATION_ICON = `<svg viewBox="0 0 24 24" class="pt-icon" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4z"/><path d="m3.3 7 8.7 5 8.7-5M12 22V12"/></svg>`;
const WEIBO_ICON = `<svg ${ICON_ATTRS}><path d="M10.1 20.3c-4 .4-7.4-1.4-7.7-4-.3-2.6 2.8-5 6.7-5.4 4-.4 7.4 1.4 7.7 4 .3 2.6-2.8 5-6.7 5.4zM19 12.8c-.3-.1-.6-.2-.4-.6.4-1 .4-1.8 0-2.4-.8-1.1-2.9-1.1-5.4 0 0 0-.8.3-.6-.3.4-1.2.3-2.2-.3-2.8-1.3-1.3-4.9 0-7.9 3.1C1.3 10.9 0 13.3 0 15.3c0 4 5.1 6.4 10.1 6.4 6.5 0 10.9-3.8 10.9-6.8 0-1.8-1.6-2.9-2.9-3.3z"/></svg>`;
const TWITTER_ICON = `<svg ${ICON_ATTRS}><path d="M14.2 10.2 23 0h-2.1l-7.6 8.8L7.3 0H.3l9.2 13.3L.3 24h2.1l8-9.3 6.4 9.3h7l-9.6-13.8zm-2.8 3.3-.9-1.3L3.1 1.6h3.2l6 8.5.9 1.3 7.8 11.1h-3.2l-6.4-9z"/></svg>`;
const ZSXQ_ICON = `<svg ${ICON_ATTRS} viewBox="0 0 26 26" fill-rule="evenodd"><path d="M13 0a1.6 1.6 0 1 1 0 3.2A9.8 9.8 0 1 0 22.8 13a1.6 1.6 0 1 1 3.2 0A13 13 0 1 1 13 0zm8 2a3 3 0 1 1 0 6 3 3 0 0 1 0-6z"/></svg>`;
const TRUTH_ICON = `<svg ${ICON_ATTRS} viewBox="3.6 4.85 16 16"><rect x="4.4" y="6.4" width="3.6" height="3.2"/><rect x="9.7" y="6.4" width="9.2" height="3.2"/><rect x="9.7" y="10.4" width="3.7" height="8.9"/><rect x="15.3" y="15.6" width="3.5" height="3.1" rx=".4" opacity=".62"/></svg>`;

export const PLATFORM_BADGES = {
  "": { label: "全部", shortLabel: "全部", icon: GRID_ICON },
  xueqiu: { label: "雪球", shortLabel: "雪球", icon: XUEQIU_ICON },
  combination: { label: "雪球组合", shortLabel: "组合", icon: COMBINATION_ICON },
  weibo: { label: "微博", shortLabel: "微博", icon: WEIBO_ICON },
  twitter: { label: "X", shortLabel: "X", icon: TWITTER_ICON },
  zsxq: { label: "知识星球", shortLabel: "星球", icon: ZSXQ_ICON },
  truth: { label: "Truth Social", shortLabel: "Truth", icon: TRUTH_ICON },
};

export const PLATFORM_LABELS = Object.fromEntries(
  Object.entries(PLATFORM_BADGES).filter(([key]) => key).map(([key, badge]) => [key, badge.label])
);
export const PLATFORM_SHORT_LABELS = Object.fromEntries(
  Object.entries(PLATFORM_BADGES).filter(([key]) => key).map(([key, badge]) => [key, badge.shortLabel])
);
export const PLATFORM_ICONS = Object.fromEntries(
  Object.entries(PLATFORM_BADGES).map(([key, badge]) => [key, badge.icon])
);
export const PLATFORM_TABS = Object.keys(PLATFORM_BADGES);
