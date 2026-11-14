// 重连退避账目（修复2/3：connectGateway 竞态孤儿连接 + 退避不跨 SW 死亡）。
//
// 语义（modern-web-guidance chrome-extensions 审计 2026-11-14 落地）：
//   - 档位与下刻门持久到 chrome.storage.session：SW 被 30s 闲置回收后再唤醒，
//     不从 0 档重新快连（平台故障风暴时会变成每 30s 一发的重连鼓点）；
//     浏览器重启（session 清零）从 0 档开始是正确语义——新会话没有历史风暴。
//   - acquire() 是互斥门 + 真退避：门内（早于 nextAt）返回 null，调用方直接
//     放弃本次尝试；放行时布下刻门（下轮尝试必须等门开）。sw.js 侧另有
//     connecting 同步互斥位挡同一微任务批内的并发入口，两层合起来消灭孤儿
//     连接（旧 socket 的 onclose 再触发新连接）。
//   - 档位阶梯与旧 sw.js 逐值对齐：第 n 次失败后等 base*2^n（penaltyMs 读
//     bump 前档位），成功 reset 归零。旧 setTimeout 重连在 SW 死亡后失效、
//     退化成 ≤30s 的 alarm 敲门——保留该快路径，alarm 仍是 SW 死亡后的兜底。
//
// 本模块只做账目（档位/门/时间源）；store 是端口（chrome.storage.session
// 形态：get(keys)->{k:v} / set(obj)），测试与冒烟用内存替身。
export const RECONNECT_BASE_MS = 2000; // 指数退避基数（spike 固定 2s 的产品化）
export const RECONNECT_MAX_MS = 120000;
export const MAX_ATTEMPTS = 6; // base 2s × 2^6 = 120s 顶格；再高没有增益

const ATTEMPTS_FIELD = "mx_reconnect_attempts";
const NEXT_AT_FIELD = "mx_reconnect_next_at";

export function createConnState({ store, now = () => Date.now() }) {
  const delayFor = (attempts) =>
    Math.min(RECONNECT_BASE_MS * 2 ** attempts, RECONNECT_MAX_MS);
  // 账目操作串行化（envelope nextSeq 同款惯用法）：acquire 的读门→布门、
  // bump 的读档→抬档都是 read-modify-write，并发交错会让双方都在对方
  // 落账前读到旧值（同刻三发全放行/丢一次计数）——排队消除
  let chain = Promise.resolve();
  const serialized = (job) => {
    const p = chain.then(job);
    chain = p.catch(() => {});
    return p;
  };
  return {
    /** 请求放行一次连接尝试：门内返回 null（调用方放弃）；放行则按当前档位
     * 布下刻门。同刻多入口竞态时只有先到的能拿到（其余 null）。 */
    acquire() {
      return serialized(async () => {
        const got = await store.get([ATTEMPTS_FIELD, NEXT_AT_FIELD]);
        const attempts = got[ATTEMPTS_FIELD] || 0;
        const t = now();
        if (t < (got[NEXT_AT_FIELD] || 0)) return null;
        await store.set({ [NEXT_AT_FIELD]: t + delayFor(attempts) });
        return { attempts };
      });
    },

    /** 连接失败/关闭记账：档位 +1（下一轮 acquire 布更长门）。 */
    bump() {
      return serialized(async () => {
        const got = await store.get([ATTEMPTS_FIELD]);
        await store.set({
          [ATTEMPTS_FIELD]: Math.min((got[ATTEMPTS_FIELD] || 0) + 1, MAX_ATTEMPTS),
        });
      });
    },

    /** 连接成功清账：档位与下刻门全清。 */
    reset() {
      return serialized(() =>
        store.set({ [ATTEMPTS_FIELD]: 0, [NEXT_AT_FIELD]: 0 })
      );
    },

    /** 当前档位的失败等待时长（sw.js onclose 用 bump 前档位算重连延时）。 */
    async penaltyMs() {
      const got = await store.get([ATTEMPTS_FIELD]);
      return delayFor(got[ATTEMPTS_FIELD] || 0);
    },

    /** 观测面（status 消息/排障）。 */
    async snapshot() {
      const got = await store.get([ATTEMPTS_FIELD, NEXT_AT_FIELD]);
      const nextAt = got[NEXT_AT_FIELD] || 0;
      return {
        attempts: got[ATTEMPTS_FIELD] || 0,
        nextAt,
        nextInMs: Math.max(0, nextAt - now()),
      };
    },
  };
}
