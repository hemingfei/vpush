// 配对/认证客户端状态机（票 #16 交付物 6）。
//
// 网关契约（app/services/mx_gateway.py mx_ingest 端点 + MxIngestGateway）：
// 浏览器 WebSocket API 不能自定义 header → 连接后首帧认证：
//   {"op":"pair","code":"8位码"} 一次性 → {ok:true, device_key}，码作废；
//   {"op":"auth","key":"设备密钥"} → {ok:true} / 拒绝时 {ok:false}+close 4003。
// 吊销时存量连接直接被服务端 close(4003)（fire-and-forget，无前置帧）——
// 客户端把 4003 唯一解释为「密钥已失效」：清 chrome.storage.local 的
// device_key，状态回 needs_pair，等待人工重新配对（自动重试死密钥只会
// 反复 4003，且网关有断连告警，重试没有意义）。
//
// storage 是端口（chrome.storage.local 形态：get(keys)->{k:v} / set(obj) /
// remove(keys)），测试用内存替身，冒烟脚本用 node 替身。
export const DEVICE_KEY_FIELD = "mx_device_key";

export function createAuthClient({ storage }) {
  async function storedKey() {
    const got = await storage.get([DEVICE_KEY_FIELD]);
    return got[DEVICE_KEY_FIELD] || null;
  }
  return {
    async state() {
      return (await storedKey()) ? "has_key" : "needs_pair";
    },

    async pair(ws, code) {
      const reply = await ws.send(JSON.stringify({ op: "pair", code: String(code).trim() }));
      if (reply && reply.ok && reply.device_key) {
        await storage.set({ [DEVICE_KEY_FIELD]: reply.device_key });
        return { ok: true };
      }
      // 配对失败保留人工可读错误（options 页展示），不写任何密钥
      return { ok: false, error: (reply && reply.error) || "配对失败" };
    },

    async auth(ws) {
      const key = await storedKey();
      if (!key) return { ok: false, error: "本地无设备密钥，需先配对" };
      const reply = await ws.send(JSON.stringify({ op: "auth", key }));
      if (reply && reply.ok) return { ok: true };
      // 拒绝语义 = 密钥无效或已吊销（网关两种拒绝同路径 close 4003）：
      // 清密钥转 needs_pair，等人工重新配对
      if (ws.closeCode === 4003) {
        await storage.remove([DEVICE_KEY_FIELD]);
        return { ok: false, error: (reply && reply.error) || "设备密钥无效或已吊销", revoked: true };
      }
      return { ok: false, error: (reply && reply.error) || "认证失败" };
    },

    async onServerClose(code) {
      // 4003 = 吊销（唯一会以 4003 关闭的路径是吊销/无效密钥）；其余
      // close code（1006 网络断、4001 首帧错误等）不动密钥——断线自动重连
      if (code === 4003) await storage.remove([DEVICE_KEY_FIELD]);
    },

    async forget() {
      await storage.remove([DEVICE_KEY_FIELD]);
    },
  };
}
