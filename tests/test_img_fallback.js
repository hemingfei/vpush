/* 图片失效兜底逻辑的独立验证：从 app/static/app.js 切出真实函数源码，
   配最小 DOM 桩运行，模拟「直连失败 → 代理失败 → 死链记忆 → 重渲染跳过」全链路。 */
const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(path.join(__dirname, "..", "app", "static", "app.js"), "utf8");

// 按函数名 + 花括号配对切源码（这些函数内无未配对的花括号字符串，可安全配对）
function extractFn(name) {
  const start = SRC.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`function ${name} not found`);
  let depth = 0;
  for (let i = SRC.indexOf("{", start); i < SRC.length; i++) {
    if (SRC[i] === "{") depth++;
    else if (SRC[i] === "}") {
      depth--;
      if (depth === 0) return SRC.slice(start, i + 1);
    }
  }
  throw new Error(`unbalanced braces in ${name}`);
}

const code = [
  "const _deadImgUrls = new Set();",
  extractFn("escapeHtml"),
  extractFn("avatarText"),
  extractFn("imgProxyUrl"),
  extractFn("rememberDeadUrl"),
  extractFn("originalUrlFromProxySrc"),
  extractFn("markImgDead"),
  extractFn("imgOnError"),
  extractFn("avatarImgError"),
  extractFn("avatarHtml"),
].join("\n");

// ---- 最小 DOM 桩 ----
function makeParent() {
  const box = {
    children: [],
    appendChild(c) { box.children.push(c); c.parentElement = box; },
    querySelector(sel) {
      return box.children.find((c) => `.${c.className}` === sel) || null;
    },
  };
  return box;
}

function makeImg(opts = {}) {
  const attrs = { src: opts.src || "" };
  const classes = opts.classes || [];
  const anchor = opts.anchor; // closest('.post-img-link') 的返回
  const img = {
    _attrs: attrs,
    dataset: {},
    style: {},
    className: classes.join(" "),
    classList: { contains: (c) => classes.includes(c) },
    // 真实 DOM 里 img.src = x 会同步更新 attribute，桩里也要接通
    get src() { return attrs.src; },
    set src(v) { attrs.src = String(v); },
    getAttribute(n) { return n in attrs ? attrs[n] : null; },
    setAttribute(n, v) { attrs[n] = v; },
    closest(sel) { return sel === ".post-img-link" ? (anchor || null) : null; },
    remove() { img.removed = true; if (anchor) anchor.removed = true; },
    replaceWith(node) { img.replacedWith = node; img.removed = true; },
    removed: false,
    replacedWith: null,
    parentElement: opts.parentElement || null,
  };
  if (anchor) anchor.querySelectorImg = img;
  return img;
}

const sandbox = new Function(
  "location", "document",
  `${code}
  return { _deadImgUrls, imgOnError, markImgDead, avatarImgError, avatarHtml, imgProxyUrl, originalUrlFromProxySrc };`
);

global.document = { createElement: () => ({ className: "", textContent: "", setAttribute() {} }) };

let failures = 0;
function check(name, cond) {
  console.log(`${cond ? "PASS" : "FAIL"}  ${name}`);
  if (!cond) failures++;
}

// ---- 场景 1：信息流缩略图，直连失败 → 换代理且 onerror 保持绑定 ----
sandbox({ origin: "http://x" }, global.document).imgOnError && (() => {
  const api = sandbox({ origin: "http://x" }, global.document);
  const anchor = { removed: false, remove() { anchor.removed = true; img.removed = true; } };
  const raw = "https://img.meituan.net/portalweb/cc2814bfbae4a95559fa54c4189041421162095.gif";
  const img = makeImg({ src: raw, anchor });
  api.imgOnError(img);
  check("直连失败后 src 换成代理地址", img._attrs.src === `/api/img-proxy?url=${encodeURIComponent(raw)}`);
  check("onerror 保持绑定（代理失败要有第二次回调）", img.onerror === api.imgOnError);
  check("死链名单暂未收录（代理还没失败）", !api._deadImgUrls.has(raw));

  // ---- 场景 2：代理也失败 → 记录原始 URL + 整块移除缩略图 ----
  img.onerror(img); // 代理地址失败再回调
  check("代理失败后死链名单记录原始 URL", api._deadImgUrls.has(raw));
  check("失效缩略图连锚点一起移除", anchor.removed === true && img.removed === true);
  check("dataset.dead 标记", img.dataset.dead === "1");

  // ---- 场景 3：重渲染期过滤——avatarHtml / 名单驱动 ----
  check("死链头像 URL 不再渲染 <img>", !api.avatarHtml("张三", raw).includes("<img"));
  check("正常头像 URL 仍渲染 <img>", api.avatarHtml("张三", "https://x/a.jpg").includes("<img"));
  check("无头像时渲染色块", api.avatarHtml("张三", "").startsWith("<div"));

  // ---- 场景 4：头像加载失败 → 记名单 + 换首字色块 ----
  const av = makeImg({ src: "https://pbs.twimg.com/dead.jpg" });
  av.dataset.avName = "李四";
  api.avatarImgError(av);
  check("头像失败记录死链", api._deadImgUrls.has("https://pbs.twimg.com/dead.jpg"));
  check("头像被替换成色块", av.removed === true && av.replacedWith && av.replacedWith.textContent === "李");

  // ---- 场景 5：灯箱内失效 → 隐藏 + 提示，不移除；重复失败只留一条提示 ----
  const box = makeParent();
  const lb = makeImg({ src: `/api/img-proxy?url=${encodeURIComponent("https://x/dead.gif")}`, classes: ["lightbox-img"], parentElement: box });
  api.imgOnError(lb);
  check("灯箱失效图隐藏", lb.style.display === "none");
  check("灯箱出现失效提示", box.children.length === 1 && box.children[0].textContent === "图片已失效");
  api.imgOnError(lb); // 重复触发
  check("提示不重复堆叠", box.children.length === 1);
  check("代理 URL 能还原出原始地址", api.originalUrlFromProxySrc(`/api/img-proxy?url=${encodeURIComponent("https://a/b.png")}`) === "https://a/b.png");
  check("非代理地址原样返回", api.originalUrlFromProxySrc("https://a/b.png") === "https://a/b.png");
})();

process.exit(failures ? 1 : 0);
