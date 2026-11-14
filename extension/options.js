// options 页（票 #16 交付物 1/6 的接线面）。
//
// 设计决策（spike 继承，不得回退）：配置写入 chrome.storage.local 即时生效，
// **绝不调用 chrome.runtime.reload()**——SW 重启窗口会丢采集事件（重启期
// 间的 debugger 事件无人监听）；SW 在每次事件时 await 读 storage，所以这里
// 只管写。
const $ = (id) => document.getElementById(id);

async function refreshStatus() {
  const reply = await chrome.runtime.sendMessage({ cmd: "status" });
  $("out").textContent = JSON.stringify(reply, null, 2);
  $("pair").disabled = reply.state !== "needs_pair";
  $("code").disabled = reply.state !== "needs_pair";
}

// 初始回填当前配置
chrome.storage.local.get(["mx_gateway_url", "mx_site_prefix"]).then((got) => {
  $("gateway").value = got.mx_gateway_url || "";
  $("sitePrefix").value = got.mx_site_prefix || "";
});

$("saveGateway").onclick = async () => {
  const url = $("gateway").value.trim();
  if (!url) return;
  await chrome.storage.local.set({ mx_gateway_url: url });
  refreshStatus();
};

$("testGateway").onclick = async () => {
  await chrome.storage.local.set({ mx_gateway_url: $("gateway").value.trim() });
  const res = await chrome.runtime.sendMessage({ cmd: "testGateway" });
  $("out").textContent = res.ok
    ? `地址合法：${res.url}`
    : `地址被拒：${res.error}`;
};

$("pair").onclick = async () => {
  const code = $("code").value.trim();
  if (code.length !== 8) {
    $("out").textContent = "配对码必须 8 位";
    return;
  }
  const res = await chrome.runtime.sendMessage({ cmd: "pair", code });
  $("out").textContent = res.ok
    ? "配对成功，设备密钥已保存，采集连接已启动"
    : `配对失败：${res.error}`;
  refreshStatus();
};

$("forget").onclick = async () => {
  await chrome.runtime.sendMessage({ cmd: "forget" });
  refreshStatus();
};

$("savePrefix").onclick = async () => {
  const prefix = $("sitePrefix").value.trim();
  if (!prefix) return;
  await chrome.storage.local.set({ mx_site_prefix: prefix });
  $("out").textContent = "前缀已保存（即时生效，无需重启）";
};

$("refresh").onclick = refreshStatus;
refreshStatus();
