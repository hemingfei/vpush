// 上行信封构造 + 持久化单调 seq（票 #16 交付物 3）。
//
// 信封形态以云网关为契约真相源（app/services/mx_gateway.py handle_envelope
// + FRAME_TYPES）：
//   {seq, ts, account, type: ws_in|ws_out|http|lifecycle, payload}
// - lifecycle 分支读 envelope.event / envelope.detail（非 payload）；
// - ws_in/ws_out/http 的 payload 直接进网关；http 记事件不进解析链。
// seq 的持久化是硬需求：网关按 (account, seq) 24h 幂等窗去重，幂等窗的存在
// 是为了吸收断线重传——前提是重传的帧 seq 与首发一致；而 SW 随时被杀，内存
// 计数器（spike sw.js:27）重启归零会让补传帧撞旧 seq 被吞 → 消息丢失。
// 故 seq 必须经 seqStore（生产=chrome.storage.local）跨 SW 重启单调。
const FRAME_TYPES = new Set(["ws_in", "ws_out", "http", "lifecycle"]);

export function createEnvelopeFactory({ getAccount, seqStore }) {
  // SW 启动即可能要发包（lifecycle: startup/attached），load 是懒等的：
  // 第一次 build 时 seq 还没 load 完就入等待队列，保证不并发抢号。
  let current = Promise.resolve(null);
  let loaded = null;

  async function nextSeq() {
    // 串行化：每个 build 排队等上一个完成，号不重不跳
    const prev = current;
    const p = (async () => {
      await prev;
      if (loaded === null) loaded = (await seqStore.load()) || 0;
      loaded += 1;
      await seqStore.save(loaded);
      return loaded;
    })();
    current = p;
    return p;
  }

  return {
    async build(type, payload) {
      if (!FRAME_TYPES.has(type)) {
        throw new Error(`非法帧类型: ${type}（合法集 ws_in|ws_out|http|lifecycle）`);
      }
      const seq = await nextSeq();
      // account 每帧读取（getAccount 端口）：接力切换备用账号补位时，后续
      // 信封带新标签——云端跨账号模糊去重按 (account, 标签) 判定同账号豁免
      const account = await getAccount();
      // http 帧 payload 序列化为 JSON 字符串：网关 http 分支只认 str payload
      // （非 str 直接丢），http_frame 事件按 len(payload) 记账。ws_in/ws_out
      // 的 payload 本就是帧字符串原文，不受影响。
      const wire = type === "http" && typeof payload !== "string" ? JSON.stringify(payload) : payload;
      return { seq, ts: Date.now(), account, type, payload: wire };
    },
    async buildLifecycle(event, detail = "") {
      const seq = await nextSeq();
      const account = await getAccount();
      return { seq, ts: Date.now(), account, type: "lifecycle", event, detail };
    },
  };
}
