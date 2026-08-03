const $ = (sel) => document.querySelector(sel);

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || resp.statusText);
  }
  return resp.json();
}

const PLATFORM_LABELS = { xueqiu: "雪球", weibo: "微博", twitter: "X" };
const PAGE_TITLES = { kols: "订阅管理", posts: "帖子", logs: "推送记录" };

async function loadKols() {
  const kols = await api("/api/kols");
  $("#kol-body").innerHTML = kols.map((k) => `
    <tr>
      <td>${k.id}</td>
      <td>${PLATFORM_LABELS[k.platform] || k.platform}</td>
      <td>${escapeHtml(k.name)}</td>
      <td>${escapeHtml(k.external_id)}</td>
      <td class="${k.enabled ? "ok" : ""}">${k.enabled ? "启用" : "停用"}</td>
      <td class="row">
        <button onclick="toggleKol(${k.id}, ${k.enabled ? 0 : 1})">${k.enabled ? "停用" : "启用"}</button>
        <button onclick="deleteKol(${k.id})">删除</button>
      </td>
    </tr>`).join("");
}

async function loadPosts() {
  const platform = $("#post-platform").value;
  const url = "/api/posts?limit=100" + (platform ? `&platform=${platform}` : "");
  const posts = await api(url);
  $("#post-list").innerHTML = posts.map((p) => `
    <li>
      <a href="${escapeHtml(p.url)}" target="_blank" rel="noopener">
        <strong>${escapeHtml(p.title || "（无标题）")}</strong>
      </a>
      <span>${PLATFORM_LABELS[p.platform] || p.platform} · ${escapeHtml(p.kol_name)} · ${escapeHtml(p.published_at)}</span>
      <p>${escapeHtml(p.content || "")}</p>
    </li>`).join("");
}

async function loadLogs() {
  const logs = await api("/api/push-logs?limit=100");
  $("#log-body").innerHTML = logs.map((l) => `
    <tr>
      <td>${escapeHtml(l.created_at)}</td>
      <td>${escapeHtml(l.kol_name)}</td>
      <td>${escapeHtml(l.title || "")}</td>
      <td>${l.channel}</td>
      <td class="${l.status === "success" ? "ok" : "fail"}">${l.status}</td>
      <td>${escapeHtml(l.error || "")}</td>
    </tr>`).join("");
}

async function toggleKol(id, enabled) {
  await api(`/api/kols/${id}`, { method: "PUT", body: JSON.stringify({ enabled: !!enabled }) });
  loadKols();
}

async function deleteKol(id) {
  if (!confirm("确认删除该大V？")) return;
  await api(`/api/kols/${id}`, { method: "DELETE" });
  loadKols();
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

document.querySelectorAll(".menu-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".menu-item").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`#page-${btn.dataset.page}`).classList.add("active");
    $("#page-title").textContent = PAGE_TITLES[btn.dataset.page] || btn.dataset.page;
  });
});

$("#kol-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/kols", {
      method: "POST",
      body: JSON.stringify({
        platform: $("#platform").value,
        name: $("#name").value,
        external_id: $("#external-id").value,
      }),
    });
    $("#name").value = "";
    $("#external-id").value = "";
    loadKols();
  } catch (err) {
    alert("添加失败: " + err.message);
  }
});

$("#refresh-posts").addEventListener("click", loadPosts);
$("#refresh-logs").addEventListener("click", loadLogs);

loadKols();
loadPosts();
loadLogs();
