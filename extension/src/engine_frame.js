// 引擎帧过滤（Engine.IO 心跳/握手/命名空间连接确认）——采集器侧第一道防线。
//
// 判定必须与云网关逐字节对齐（app/services/mx_gateway.py 的 ENGINE_FRAME_RE
// = ^(?:[023]|4[01])，测试=契约）：凡是网关会防御性丢弃的帧，扩展侧就不该
// 上行（spec user story 21——心跳噪音不上云端，省上行流量与幂等窗占用）。
// 对齐的代价是 "40" 前缀的第三字符变体（如 "40x"）也判引擎帧——防御性丢弃
// 语义，非法形态本就不是业务帧。
//
// 引擎帧知识：SIO 帧首字符是类型字节；2/3=ping/pong 心跳，0=connect（0{...}
// 握手参数），40/41=命名空间 connect/disconnect（41 带 ns 时如 "41/msg"，
// 故用前缀匹配而非全等——spike sw.js:109 全等判定的已知缺陷，实测抓包存在
// "40/msg" 带命名空间形态）。
const ENGINE_FRAME_RE = /^(?:[023]|4[01])/;

export function isEngineFrame(data) {
  // 空/非字符串帧与网关同口径不认为业务 payload（网关对非字符串/空直接
  // return 不进解析链），扩展侧直接过滤不上行
  if (typeof data !== "string" || data === "") return true;
  return ENGINE_FRAME_RE.test(data);
}
