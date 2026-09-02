# 系统 KOL Webhook 接入文档

> 本文档面向**外部平台/程序的开发者**：你只需拿到管理员提供的 Webhook 地址，按本文规范 POST 消息，即可让对应的 KOL（如「AI 分析报告」）在平台上发帖，并自动推送给所有订阅者。

---

## 1. 你会拿到什么

管理员会在后台为你开启一个专属 Webhook，并提供一个形如下面的地址：

```
https://<域名>/api/kol-webhook/<token>
```

- 这个地址**本身就是凭据**，调用无需任何登录态或账号体系。
- ⚠️ **请妥善保管该地址**：任何持有它的人都能以该 KOL 的名义发帖。只走 HTTPS、不要写进前端页面或公开仓库。泄露后请立即联系管理员重新生成（旧地址会立即失效）。
- 地址支持一个 KOL 独立一条，不同 KOL 的地址互不相通。

---

## 2. 调用规范

| 项目 | 说明 |
| --- | --- |
| 请求方法 | `POST` |
| URL | `https://<域名>/api/kol-webhook/<token>` |
| Content-Type | `application/json` |
| 请求体 | JSON 对象，支持三种格式（见第 3 节） |
| 成功响应 | HTTP 200，`{"code": 0, "msg": "success", "post_id": 123}` |

**最小可用示例（curl）：**

```bash
curl -X POST 'https://<域名>/api/kol-webhook/<token>' \
  -H 'Content-Type: application/json' \
  -d '{"msg_type":"text","content":{"text":"大家好"}}'
```

---

## 3. 请求体格式（三选一）

### 3.1 简化格式（推荐）

```json
{
  "text": "正文内容，必填",
  "title": "可选标题",
  "images": ["https://example.com/a.png", "https://example.com/b.png"]
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `text` | ✅ | 正文，非空字符串，上限 **8000 字符** |
| `title` | ❌ | 标题，超过 200 字符自动截断 |
| `images` | ❌ | 图片 URL 数组，最多取前 **9** 张 |

### 3.2 飞书文本格式

与飞书自定义机器人请求体完全兼容，已有对接飞书的程序可零改造接入：

```json
{
  "msg_type": "text",
  "content": { "text": "大家好" }
}
```

### 3.3 飞书富文本格式（post）

```json
{
  "msg_type": "post",
  "content": {
    "post": {
      "zh_cn": {
        "title": "标题",
        "content": [
          [ { "tag": "text", "text": "第一行" } ],
          [ { "tag": "a", "text": "点这里", "href": "https://example.com" } ]
        ]
      }
    }
  }
}
```

说明：

- 只提取文本与链接，链接渲染为 `文本 (链接)` 的形式。
- `image_key`（飞书图片）会被忽略，请改用简化格式的 `images` 传图片 URL。
- 标题超过 200 字符自动截断。

---

## 4. 幂等：`msg_id`（建议必带）

请求体可附加 `msg_id` 字段（也可叫 `external_id`，最长 128 字符）：

```json
{ "text": "正文", "msg_id": "your-platform-20260902-0001" }
```

- 同一地址下相同 `msg_id` 的消息**只发一条**，重复调用安全，响应会带 `"duplicate": true`。
- **强烈建议**：外部平台生成唯一 ID（如 `业务名-日期-序号`）并带上。这样网络超时、重试时不会造成重复发帖。
- 不带 `msg_id` 时，每次调用都视为新消息。

---

## 5. 签名校验（可选，按需开启）

如果管理员为该 Webhook 配置了**签名密钥**，请求体必须额外携带 `timestamp` 和 `sign`，否则返回 403。算法与飞书自定义机器人相同：

```
timestamp = 当前 Unix 秒级时间戳
string_to_sign = f"{timestamp}\n{密钥}"
sign = base64( hmac_sha256(key=string_to_sign, message=空) )
```

> 注意飞书的特殊之处：`string_to_sign` 是作为 HMAC 的 **key**，待签内容为空。

**Python 示例：**

```python
import base64, hashlib, hmac, json, time, urllib.request

url = "https://<域名>/api/kol-webhook/<token>"
secret = "管理员提供的签名密钥"          # 未配签名密钥则省略 timestamp/sign

timestamp = str(int(time.time()))
string_to_sign = f"{timestamp}\n{secret}"
sign = base64.b64encode(
    hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
).decode("utf-8")

payload = {
    "msg_type": "text",
    "content": {"text": "大家好"},
    "timestamp": timestamp,
    "sign": sign,
    "msg_id": "your-platform-20260902-0001",
}
req = urllib.request.Request(
    url, data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"}, method="POST",
)
print(urllib.request.urlopen(req).read().decode())
```

**Node.js 示例：**

```js
const crypto = require("crypto");

const timestamp = Math.floor(Date.now() / 1000).toString();
const stringToSign = `${timestamp}\n${secret}`;
const sign = crypto.createHmac("sha256", stringToSign).update("").digest("base64");
// payload = { msg_type: "text", content: { text: "大家好" }, timestamp, sign, msg_id }
```

约束：

- `timestamp` 与服务器时间偏差须在 **1 小时内**（防重放），请每次发送前现算，不要缓存。
- `timestamp` 传数字或字符串均可。

---

## 6. 限制与配额

| 项目 | 上限 | 超限行为 |
| --- | --- | --- |
| 发送频率 | 每 token 每 60 秒 **100 条**（对齐飞书） | HTTP 429 |
| 正文长度 | **8000** 字符 | HTTP 400 |
| 标题长度 | 200 字符 | 自动截断，不报错 |
| 图片数量 | 9 张 | 多余的丢弃，不报错 |

---

## 7. 响应与错误码

**成功（HTTP 200）：**

```json
{ "code": 0, "msg": "success", "post_id": 123 }
```

重复消息（`msg_id` 已发过）：

```json
{ "code": 0, "msg": "success", "duplicate": true }
```

**失败：** 返回非 200 状态码，响应体为 `{"detail": "错误原因"}`。

| HTTP 状态码 | 场景 |
| --- | --- |
| 400 | 请求体不是合法 JSON / 不是 JSON 对象 / 消息内容为空 / 正文超 8000 字符 |
| 403 | 签名校验失败（密钥不对或时间戳偏差超 1 小时） |
| 404 | 地址不存在或已被停用（token 错误、Webhook 被关闭或轮换） |
| 429 | 触发限流（每分钟超 100 条），请稍后重试 |

**重试建议：**

- 收到 `429` / `5xx` / 网络超时时可安全重试，**重试时保持同一个 `msg_id`**，即可保证「至少成功一次、绝不重复」。
- `404` 表示地址已失效，不要重试，联系管理员重新获取。
- `400` 属于请求本身问题，修正后再发。

---

## 8. 消息发出后会发生什么

1. 系统立即以该 KOL 的名义创建帖子（发布时间为当前北京时间）。
2. 帖子按各用户的订阅关系**实时推送**（Telegram / 飞书 / 企业微信 / 浏览器 Push 等渠道），用户的免打扰、次要内容合并、推送重试等策略与普通帖子完全一致。
3. 帖子同步出现在平台站内该 KOL 的动态里，可被搜索、打标。

---

## 9. 对接检查清单

- [ ] 已从管理员处拿到 Webhook 地址，并确认已「启用」
- [ ] 用 curl 发一条测试消息，收到 `{"code": 0, ...}`
- [ ] 请求体带上唯一 `msg_id`
- [ ] 若配了签名密钥：每次现算 `timestamp` + `sign`
- [ ] 发送侧做好 429/超时重试（同 `msg_id`），发送频率控制在每分钟 100 条以内
- [ ] Webhook 地址已作为机密保存（不入库明文、不进前端代码/日志）

---

## 附：管理员侧操作（供内部参考，外部对接方无需关心）

管理后台「大V管理」→ 系统 KOL 行点「Webhook」→ 勾选「启用 Webhook」→ 复制生成的地址。可选设置签名密钥；「重新生成 Token」使旧地址立即失效。相关管理 API：`GET/PUT /api/admin/kols/{id}/webhook`、`POST /api/admin/kols/{id}/webhook/regenerate`。
