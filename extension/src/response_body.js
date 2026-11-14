// HTTP 响应体采集（票 #16 交付物 2 补齐：requestWillBeSent + getResponseBody）。
//
// 设计：chrome.debugger Network 域里响应体要在 Network.loadingFinished 后才能
// Network.getResponseBody 取回（loading 阶段取会报错）。扩展侧的管线：
//   requestWillBeSent（shouldCaptureHttp 命中）→ 登记 requestId
//   Network.loadingFinished → getResponseBody → 组装 http 信封 payload
//
// 纯逻辑（登记/超限截断/组装）在本模块（node --test 覆盖）；chrome.debugger
// 调用留在 sw.js（真实 GUI 会话由 48h 挂机验收覆盖，不进 CI）。
//
// 响应体大小上限 64KB：上行帧走 wss 单帧，超长体截断并打 truncated 标记
// （网关侧 http 帧只记事件不进解析链，体积失控的收益近零、风险是撑爆
// 缓冲与 seq 语义——5000 帧上限 10MB storage 限额）。

export const RESPONSE_BODY_MAX_BYTES = 64 * 1024;

export function createResponseTracker({ cap = RESPONSE_BODY_MAX_BYTES } = {}) {
  // requestId -> {url, method, body(请求 postData)}；只在 in-flight 期间持有
  const pending = new Map();

  return {
    /** requestWillBeSent：登记在途请求（只记关注的 HTTP 请求）。 */
    track(requestId, request) {
      if (!requestId || !request?.url) return false;
      pending.set(requestId, {
        url: String(request.url || ""),
        method: String(request.method || "GET"),
        body: request.postData ?? null,
      });
      // 登记表无上限清理：loadingFailed/加载完成都会消费；长期在途的请求
      // 由网络栈生命周期保证有限（页面导航重 attach 时 SW 重建表自然清空）
      return true;
    },

    /** loadingFinished：取回登记 + 留下可组装的请求面。 */
    take(requestId) {
      if (!pending.has(requestId)) return null;
      const entry = pending.get(requestId);
      pending.delete(requestId);
      return entry;
    },

    /** 在途登记数（观测面）。 */
    size() {
      return pending.size;
    },

    /** 组装 http 信封 payload（含响应体截断语义）。 */
    buildPayload(entry, responseBody) {
      const capped = capBody(responseBody ?? "", cap);
      return {
        url: entry.url,
        method: entry.method,
        body: entry.body,
        responseBody: capped.text,
        responseBodyTruncated: capped.truncated,
      };
    },
  };
}

/** 响应体截断：按 UTF-16 code unit 计（chrome.storage/wss 帧体积的近似口径），
 * 超限截断 + truncated 标记；base64 体（binary）按原样截断字符串。 */
export function capBody(text, cap = RESPONSE_BODY_MAX_BYTES) {
  const s = String(text ?? "");
  if (s.length <= cap) return { text: s, truncated: false };
  return { text: s.slice(0, cap), truncated: true };
}
