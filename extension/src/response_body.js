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

// 登记写穿 storage.session 的字段（修复1：MV3 SW 在 requestWillBeSent 与
// loadingFinished 之间被 30s 回收时，内存登记蒸发=响应体帧静默丢失——
// session 级存储跨 SW 死亡存活、浏览器重启清零，正好是 in-flight 状态的
// 正确持久层；modern-web-guidance chrome-extensions 规则7 的落点）。
const PENDING_FIELD = "mx_resp_pending";

export function createResponseTracker({ cap = RESPONSE_BODY_MAX_BYTES, sessionStore = null } = {}) {
  // requestId -> {url, method, body(请求 postData)}；只在 in-flight 期间持有。
  // sessionStore 缺省 null（纯内存——旧调用方/单测形态不变）；生产 sw.js 传
  // chrome.storage.session 适配层，登记写穿。
  const pending = new Map();
  const persist = async () => {
    if (!sessionStore) return;
    try {
      await sessionStore.set({ [PENDING_FIELD]: [...pending.entries()] });
    } catch {
      // 写穿失败不阻塞采集主链路（最坏退化回旧内存态语义）
    }
  };

  return {
    /** requestWillBeSent：登记在途请求（只记关注的 HTTP 请求）。 */
    async track(requestId, request) {
      if (!requestId || !request?.url) return false;
      pending.set(requestId, {
        url: String(request.url || ""),
        method: String(request.method || "GET"),
        body: request.postData ?? null,
      });
      await persist();
      // 登记表无上限清理：loadingFailed/加载完成都会消费；长期在途的请求
      // 由网络栈生命周期保证有限（页面导航重 attach 时 clear 清表）。
      // 写穿落 session：SW 死于 requestWillBeSent 与 loadingFinished 之间
      // 时，重启经 restore() 装回，响应体帧不再静默丢失。
      return true;
    },

    /** loadingFinished：取回登记 + 留下可组装的请求面 + 写穿清账。 */
    async take(requestId) {
      if (!pending.has(requestId)) return null;
      const entry = pending.get(requestId);
      pending.delete(requestId);
      await persist();
      return entry;
    },

    /** SW 重启恢复：把 session 里存活的登记装回内存表（onStartup/顶层调用）。 */
    async restore() {
      if (!sessionStore) return 0;
      try {
        const got = await sessionStore.get([PENDING_FIELD]);
        const saved = got[PENDING_FIELD];
        if (Array.isArray(saved)) {
          for (const [k, v] of saved) if (!pending.has(k)) pending.set(k, v);
          return pending.size;
        }
      } catch {
        /* 空恢复 */
      }
      return 0;
    },

    /** 清空登记（debugger 重 attach = 新 Network 会话、新 requestId 空间：
     * 旧会话登记全部作废，不清会跨会话累积）。 */
    async clear() {
      pending.clear();
      await persist();
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
