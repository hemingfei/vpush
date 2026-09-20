/* V Push Service Worker —— network-first：静态外壳离线可用，API 永不缓存 */
const CACHE = "dav-shell-1d9bfef98674";
const SHELL = [
  "/",
  "/app.7e6a7c5c766c.js",
  // asset-modules:start
  "/core/dialog.075fc1993221.js",
  "/core/html.d1ec10740d9a.js",
  "/core/icons.b58671861ee1.js",
  "/core/lightbox.0e237146334b.js",
  "/core/platforms.ceefb616ae24.js",
  "/views/admin/cicc.0512f9b9f513.js",
  "/views/admin/codes.41b293a5ecef.js",
  "/views/admin/dashboard.ff94aaad0fbd.js",
  "/views/admin/ima-collector.f634462dbe33.js",
  "/views/admin/infra.51c6aa28633d.js",
  "/views/admin/knowledge.e86cdc614317.js",
  "/views/admin/kol.6a6d4a7ef6b6.js",
  "/views/admin/news.16e537fdddc8.js",
  "/views/admin/users.0455773c50b9.js",
  "/views/feishu-personal.b1fa15996a32.js",
  "/views/holdings.20e894e0b2fc.js",
  "/views/ima.f224615607ed.js",
  "/views/market.28072c6a16c9.js",
  "/views/mx-kol-holdings.a9a786db4166.js",
  "/views/mx-views.33ff2b196773.js",
  "/views/news.8e88e9b6eddc.js",
  "/views/post-card-export.f5ba5e33ac87.js",
  "/views/push-settings.ebbe7b79714e.js",
  // asset-modules:end
  "/style.7a55bfdc082a.css",
  "/mx-views.a4d27abe74d0.css",
  "/holdings.1cc2d89cea11.css",
  "/mx-kol-holdings.8db7299fa8d6.css",
  "/vendor/design-tokens.949f5654f701.css",
  "/logo-mark.svg",
  "/icon-192.png",
  "/icon-512.png",
  "/icon-192-dark.png",
  "/icon-512-dark.png",
  "/manifest.webmanifest",
  "/manifest-dark.webmanifest",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE)
      .then((c) => c.addAll(SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  let url;
  try {
    url = new URL(e.request.url);
  } catch {
    return;
  }
  if (e.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // 动态数据永不缓存
  if (e.request.mode === "navigate") {
    e.respondWith(networkFirstNavigate(e.request));
    return;
  }
  e.respondWith(networkFirst(e.request));
});

self.addEventListener("push", (e) => {
  let data = {};
  try {
    data = e.data ? e.data.json() : {};
  } catch {
    data = { body: e.data ? e.data.text() : "" };
  }
  e.waitUntil(self.registration.showNotification(data.title || "VPush", {
    body: data.body || "",
    icon: "/icon-192.png",
    badge: "/icon-192.png",
    data: { url: data.url || "/" },
    tag: data.tag || "vpush",
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if ("focus" in client) {
        await client.focus();
        if ("navigate" in client && url) await client.navigate(url);
        return;
      }
    }
    await self.clients.openWindow(url);
  })());
});

async function networkFirstNavigate(req) {
  try {
    const fresh = await fetch(req, { cache: "reload" });
    if (fresh && fresh.ok) return fresh;
  } catch {
    /* 离线 */
  }
  return (await caches.match("/")) || Response.error();
}

async function networkFirst(req) {
  let fresh;
  try {
    // cache:"reload" 绕过 HTTP 缓存：CF 会给裸 URL 模块强加 4h 浏览器缓存，
    // 不绕过的话「网络优先」会被浏览器缓存短路，发版后模块最长滞后 4 小时
    fresh = await fetch(req, { cache: "reload" });
  } catch {
    const cached = await caches.match(req, { ignoreSearch: true });
    return cached || Response.error();
  }
  if (fresh && fresh.ok && fresh.type === "basic") {
    // 后台写缓存：Cache.put 对 206（大文件 Range）等响应会抛错，
    // 绝不能影响已经拿到的网络响应
    let cacheKey;
    try {
      // 用裸路径作缓存键，避免 ?v= 版本号 query 撑爆缓存
      cacheKey = new Request(new URL(req.url).pathname);
    } catch {
      return fresh;
    }
    caches.open(CACHE)
      .then((cache) => cache.put(cacheKey, fresh.clone()))
      .catch(() => {});
  }
  return fresh;
}
