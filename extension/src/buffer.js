// 断线缓冲账目（票 #16 交付物 5）。
//
// 语义（spec 决策值）：断线期间帧入本地缓冲，重连后按 seq 升序补传；缓冲
// 上限 5000，超限丢最旧（保最近的房间消息，越新的消息越接近实时推送价值），
// 每次丢弃累计计数，经 lifecycle 帧 buffer_overflow 上报云端告警与排障
// （user story 8/9/19）。
//
// 本模块只做「账目」（容量/顺序/丢弃计数）；持久化由调用方选择的 store 适配
// （生产 = chrome.storage.local 存数组，量级 5000×~1KB 在 storage.local 10MB
// 限额内；IndexedDB 是 ADR 后续路线，账目语义不变）。
export const BUFFER_CAP = 5000;

export function createBuffer({ cap = BUFFER_CAP } = {}) {
  let items = [];
  let dropped = 0;
  return {
    push(item) {
      items.push(item);
      if (items.length > cap) {
        items.shift(); // 丢最旧（FIFO）：越新的帧越接近实时价值
        dropped += 1;
      }
      return items.length;
    },
    items() {
      return items.slice();
    },
    drain() {
      const out = items;
      items = [];
      return out;
    },
    size() {
      return items.length;
    },
    droppedTotal() {
      return dropped;
    },
    resetDropped() {
      // 上报后清零（buffer_overflow lifecycle 帧发过即清，避免重复上报）
      dropped = 0;
      return dropped;
    },
  };
}
