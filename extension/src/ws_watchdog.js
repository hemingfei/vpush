// 页面 WS 静默看门狗（票 #23 防线二）。
//
// 背景（2026-11-17 断流 4.3h 实锤）：页面自己的 WS 死亡且页面 JS 无自愈
// 重连——页面/扩展网关/agent 三处全绿无告警。网关侧 CONNECTING 黑洞
// （6f4d629）是同族问题的「扩展↔vpush」段形态；本模块看护最后一段
// 「页面↔MX」：连引擎心跳帧都收不到 = 页面 WS 已死的权威信号。
//
// 纯逻辑（阈值判定 + 随机采样）：Chrome API 接线在 sw.js——
//   - debugger onEvent 里所有 WS 帧（含引擎帧：2/3 ping-pong 心跳停
//     是连接死的最权威信号，业务帧静默可能是真没人说话）刷 lastFrameAt；
//   - keepalive alarm（30s tick）判定静默超阈值 → chrome.tabs.reload；
//   - 阈值每次触发后重新随机采样（3-10 分钟），reload 的自愈节奏本身
//     不可预测（拟人化：与 agent 侧 50-90min reload 哲学同源）。
// 状态写穿 chrome.storage.session（SW 死亡后账目存活；浏览器重启清零
// = 新会话无历史静默，语义正确——与 conn_state 同口径）。

// 静默阈值区间（毫秒）：用户口径 3-10 分钟。
export const SILENCE_THRESHOLD_RANGE_MS = [3 * 60 * 1000, 10 * 60 * 1000];

const LAST_FRAME_FIELD = "mx_last_ws_frame_at";
const THRESHOLD_FIELD = "mx_ws_silence_threshold";
const RELOADED_FOR_SILENCE_FIELD = "mx_ws_silence_reloaded";

export function createWsWatchdog({ store, now = () => Date.now(), random = Math.random }) {
  // 账目操作串行化（conn_state 同款惯用法）：读-改-写并发交错防护
  let chain = Promise.resolve();
  const serialized = (job) => {
    const p = chain.then(job);
    chain = p.catch(() => {});
    return p;
  };

  const sampleThreshold = () =>
    random() * (SILENCE_THRESHOLD_RANGE_MS[1] - SILENCE_THRESHOLD_RANGE_MS[0]) +
    SILENCE_THRESHOLD_RANGE_MS[0];

  return {
    /** 页面 WS 收到帧（含引擎帧）时刷时间戳。清「已 reload」标记——新帧
     * 到达 = 页面 WS 已恢复说话，下次静默允许再次触发 reload（防重入的
     * 反向面：恢复后新静默期要能再救）。SW 被杀后恢复靠 storage 账目。 */
    noteFrame() {
      return serialized(async () => {
        await store.set({
          [LAST_FRAME_FIELD]: now(),
          [RELOADED_FOR_SILENCE_FIELD]: false,
        });
      });
    },

    /** attach 成功基线：新 attach 的页面 WS 尚未收帧，从当前时刻起算
     * 静默（不是从 1970 起算秒触发）。 */
    noteAttached() {
      return serialized(async () => {
        const got = await store.get([LAST_FRAME_FIELD]);
        if (!got[LAST_FRAME_FIELD]) {
          await store.set({ [LAST_FRAME_FIELD]: now() });
        }
      });
    },

    /** 判定是否该 reload：静默超随机阈值且本静默期未 reload 过。
     * 阈值不存在时惰性采样（首个判定期落账），触发 reload 时重采样——
     * 每次「静默事件」用不同阈值，自愈节奏不可预测。 */
    shouldReload() {
      return serialized(async () => {
        const got = await store.get([
          LAST_FRAME_FIELD,
          THRESHOLD_FIELD,
          RELOADED_FOR_SILENCE_FIELD,
        ]);
        const last = got[LAST_FRAME_FIELD] || 0;
        let threshold = got[THRESHOLD_FIELD];
        if (!threshold) {
          threshold = sampleThreshold();
          await store.set({ [THRESHOLD_FIELD]: threshold });
        }
        if (got[RELOADED_FOR_SILENCE_FIELD]) return false; // 本静默期已救过
        return now() - last > threshold;
      });
    },

    /** reload 已执行：记账防重入 + 重采样下一静默期阈值。 */
    markReloaded() {
      return serialized(async () => {
        await store.set({
          [RELOADED_FOR_SILENCE_FIELD]: true,
          [THRESHOLD_FIELD]: sampleThreshold(),
        });
      });
    },

    /** 观测面（status 消息/排障）。 */
    async snapshot() {
      const got = await store.get([
        LAST_FRAME_FIELD,
        THRESHOLD_FIELD,
        RELOADED_FOR_SILENCE_FIELD,
      ]);
      const t = now();
      const last = got[LAST_FRAME_FIELD] || 0;
      return {
        lastFrameAt: last,
        silenceMs: Math.max(0, t - last),
        thresholdMs: got[THRESHOLD_FIELD] || null,
        reloadedForSilence: Boolean(got[RELOADED_FOR_SILENCE_FIELD]),
      };
    },
  };
}
