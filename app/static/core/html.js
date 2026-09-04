export function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

export function imgProxyUrl(url) {
  return `/api/img-proxy?url=${encodeURIComponent(url)}`;
}

export function imgOnError(img) {
  // 第三方图床直连失败（大陆访问 X 图床被墙等）→ 经服务端代理转发
  if (!img || img.dataset.proxied) return;
  const src = img.getAttribute("src") || "";
  if (src.startsWith("/api/img-proxy")) return;
  img.dataset.proxied = "1";
  img.src = imgProxyUrl(src);
  img.onerror = null;
}
