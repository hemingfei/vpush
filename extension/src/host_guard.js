// 上行目标 host 校验（票 #16 交付物 8）。
//
// 语义对齐云端 app/url_safety.is_safe_http_url：环回/私网/链路本地/元数据
// 地址全拒——采集器持有设备密钥，被诱导指向内网地址等于把认证凭据+帧内容
// 送进内网。协议层额外收紧：仅 wss（生产），本地冒烟脚本用显式
// allowInsecureDev 开关放行 ws://环回（开关不进扩展默认路径）。
const PRIVATE_HOSTNAME_RE =
  /^(localhost$|127\.|10\.|0\.0\.0\.0$|169\.254\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[::1\]$|\[fc|\[fd|\[fe80)/i;

export function validateIngestHost(rawUrl, { allowInsecureDev = false } = {}) {
  let url;
  try {
    url = new URL(String(rawUrl || ""));
  } catch {
    throw new Error(`上行地址非法: ${JSON.stringify(rawUrl)}`);
  }
  const isLoopback =
    url.hostname === "localhost" ||
    url.hostname === "127.0.0.1" ||
    url.hostname === "[::1]" ||
    url.hostname === "0.0.0.0" ||
    url.hostname === "::1";
  if (allowInsecureDev) {
    // 开关只放行环回明文 ws（冒烟脚本连本地网关用）；其它明文目标仍拒
    if (url.protocol === "ws:" && isLoopback) return url;
  }
  if (url.protocol !== "wss:") {
    throw new Error(`上行仅允许 wss，实际协议: ${url.protocol}//${url.hostname}`);
  }
  if (!url.hostname || PRIVATE_HOSTNAME_RE.test(url.hostname)) {
    throw new Error(`拒绝内网/环回上行目标: ${url.hostname}`);
  }
  return url;
}
