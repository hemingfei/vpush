// CDP 直连采集通道（票 #23 追加：chrome.debugger 名额被外部 CDP 客户端
// （agent 的 Playwright connect_over_cdp）占住时的 fallback 采集内核）。
//
// 背景（2026-11-17 16:23 起实锤）：扩展 attach 依赖 chrome.debugger 的
// 单名额——agent 先挂时扩展永远报 "Another debugger already attached"
// 收不到帧，而 CDP 协议层天然多客户端并存（同机实测：Playwright 持有
// 时外部 CDP 直连 Network.enable 35s 收 11 条帧含业务 room_msg）。
// 外部 CDP 直连 = ws://127.0.0.1:9223/devtools/page/<id>，与扩展通道
// 平行，帧事件形态与 chrome.debugger onEvent 相同（Network.webSocket
// FrameReceived/Sent 的 params 结构一致）。
//
// 安全边界：仅环回（127.0.0.1:9223 固定端口，host_guard 之外的硬编码
// 白名单）——本机 agent 的调试端口。manifest CSP/host_permissions 已
// 相应收窄放行该 origin（1.2.0）。
//
// 纯逻辑（本模块只管通道选择/URL 构造/报文解包）；ws 生命周期接线在
// sw.js（cdpSock 变量 + onmessage 分派进同一 onEvent 处理器）。

// 目标页 devtools WS 的 URL 构造（/json/list 的 webSocketDebuggerUrl 原样用）
export function pickPageTarget(targets, sitePrefix) {
  for (const t of targets) {
    if (t?.type !== "page") continue;
    const url = String(t.url || "");
    if (sitePrefix && url.startsWith(sitePrefix) && t.webSocketDebuggerUrl) {
      return t;
    }
  }
  return null;
}

// CDP 报文 → chrome.debugger onEvent 同构事件（Network.webSocketFrame*）
export function cdpMessageToEvent(text) {
  let msg;
  try {
    msg = JSON.parse(text);
  } catch {
    return null;
  }
  const method = msg?.method || "";
  if (method === "Network.webSocketFrameReceived" || method === "Network.webSocketFrameSent") {
    return { source: { tabId: -1 }, method, params: msg.params };
  }
  return null;
}

// 本地 CDP HTTP 面的目标清单端点（固定环回，不读配置——agent 端口即 9223）
export const LOCAL_CDP_LIST_URL = "http://127.0.0.1:9223/json/list";
