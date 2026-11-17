// CDP relay 采集通道（票 #23 追加：chrome.debugger 名额被外部 CDP 客户端
// （agent 的 Playwright connect_over_cdp flat-session attach）占住时的
// fallback 采集内核）。
//
// 背景与三道墙（2026-11-17 16:23 起实锤，逐墙实测）：
// 1. chrome.debugger target attach 是单名额——agent 的 Playwright 先挂时
//    扩展永远报 "Another debugger already attached" 收不到帧；
// 2. page 的 devtools ws 端点（ws://127.0.0.1:9223/devtools/page/<id>）
//    与 flat session 机制并存（Playwright 持有时外部直连 Network.enable
//    实测收帧），但 SW 里的 new WebSocket 必带 Origin: chrome-extension://
//    ——被 CDP 服务端的 Origin 校验拒（CSRF 防御，浏览器外客户端无
//    Origin 头故能连）；
// 3. MV3 SW 对 http://127.0.0.1 的 fetch 被 Private Network Access 拦截。
// 破局：scripts/mx_cdp_relay.py 本地桥（无 Origin 的 python websockets
// 客户端）——连 page ws + Network.enable，把 Network.webSocketFrame*
// 事件原样转发到 ws://127.0.0.1:9333。SW 连 relay 收帧（自己的服务器，
// 无 Origin 约束）。
//
// 安全边界：仅环回（127.0.0.1:9333 固定端口）。manifest CSP/host_
// permissions 已收窄放行该 origin（1.2.x）。
//
// 纯逻辑（URL/解包）；ws 生命周期接线在 sw.js。

// relay 端点（固定环回）
export const RELAY_WS_URL = "ws://127.0.0.1:9333";

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
