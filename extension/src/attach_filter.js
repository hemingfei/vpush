// attach 过滤判定（票 #16 交付物 2 的配置面）。
//
// spike 继承的两条设计决策（票 #16 不得回退）在此落点：
// ①attach 过滤配置每次事件时 await storage 读取——SW 被杀重启后顶层一次性
//   读到的可能是启动竞态里的旧值/空值（spike sw.js:20-23 的教训）；storage
//   写入即时生效，配置变更不 reload SW（重启窗口丢事件）。
// ②MX 域名会漂移（当前 https://mx.2026.foodtop1.com），attach 前缀必须可配
//   （storage.mx_site_prefix，options 页写入）。
//
// HTTP 过滤正则与 mx_room_switch_capture 的 API_RE 同源（spike sw.js:114）：
// 只关心 /api/ 与 socket.io 两类——页面静态资源不是采集对象。
const DEFAULT_SITE_PREFIX = "https://mx.2026.foodtop1.com/";
const HTTP_URL_RE = /\/api\/|socket\.io/;

export async function shouldCaptureTab(storage, tab) {
  if (!tab || typeof tab.id !== "number" || tab.id < 0) return false; // devtools 等无页面目标
  const cfg = await storage.get(["mx_site_prefix"]);
  const prefix = cfg.mx_site_prefix || DEFAULT_SITE_PREFIX;
  return String(tab.url || "").startsWith(prefix);
}

export function shouldCaptureHttp(url) {
  return HTTP_URL_RE.test(String(url || ""));
}
