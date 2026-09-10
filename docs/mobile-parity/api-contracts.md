# API 合同采集记录

客户端复用现有 FastAPI `/api`。所有需要登录的请求使用 `Authorization: Bearer <token>`；token 只保存在 Android 安全存储，不放 URL、通知 payload 或日志。阶段 0 的真实响应 fixture 尚未采集，下面记录已核实的路径和必须保留的语义。

## 通用语义

| 响应 | 客户端行为 |
| --- | --- |
| 2xx | 解码页面模型；写操作只有在服务端成功后更新本地确认状态 |
| 400/422 | 保留 FastAPI `detail` 字符串或结构化校验错误，显示人话，不拼接 `[object Object]` |
| 401 `/auth/*` | 显示登录/注册业务错误，不清理当前会话 |
| 401 其他接口 | 仅当响应属于发起请求时的当前 session generation 才清理会话并回登录 |
| 403 | 显示权限/功能关闭状态，不能误显示为空列表 |
| 429 | 显示限流原因和稍后重试入口；不自动高频重试 |
| 5xx / 网络错误 | 页面显示失败和重试，取消请求不显示错误 |
| 二进制 | 先验证内容类型/魔数；PDF 非 `%PDF-` 视为失败，不直接交给阅读器 |

## 首批接口

认证：`GET /auth/turnstile`、`POST /auth/login`、`POST /auth/register`、`GET /me`。

动态：`GET /my/feed`、`GET /live/wscn`、`GET /market/indices`、`GET /kols/{kol_id}`、`GET /kols/{kol_id}/posts`、`GET /kols/{kol_id}/holdings`、`GET /kols/{kol_id}/nav`。

广场：`GET /catalog`、`GET /recommendations`、`GET /my/subscriptions`、`POST /subscriptions`、`PUT /subscriptions/{kol_id}`、`PUT /subscriptions/{kol_id}/favorite`、`PUT /subscriptions/{kol_id}/secondary`、`PUT /subscriptions/{kol_id}/hide-images`、`DELETE /subscriptions/{kol_id}`、`POST /kol-requests`、`GET /my/kol-requests`。

新闻：`GET /news/sources`、`GET /news`、`POST /news/seen`、`GET /news/{article_id}`、`GET /news/{article_id}/images/{index}`。

研报：`GET /ima-documents/catalog`、`GET /ima-documents`、`POST/DELETE /ima-documents/groups/{group_id}/subscribe`、`GET /ima-documents/{media_id}`、`POST /ima-documents/{media_id}/translate`、`GET /ima-documents/{media_id}/timeline`、`GET /ima-documents/timeline/all`、`GET /ima-documents/{media_id}/assets/{asset_id}`、`GET /ima-documents/{media_id}/text`、`GET /ima-documents/{media_id}/pdf`。

设置/绑定：`PUT /me`、`POST /me/password`、`POST /me/llm-models`、`POST /me/llm-test`、`POST/DELETE /me/webpush`、`POST/GET /me/feishu-personal/register...`、`DELETE /me/feishu-personal`。

Android 设备归属：`PUT /me/android-devices/{installation_id}`、`DELETE /me/android-devices/{installation_id}`。注册请求包含 `token`（1-4096 字符）、`provider`（`fcm`、`huawei`、`xiaomi`、`oppo`、`vivo`、`meizu` 或 `other`）以及可选的设备型号和 App 版本；响应只返回安装标识、provider 和设备数量，不回显 token。安装标识只允许 8-128 位字母、数字、点、下划线和连字符；同一标识再次注册会更新归属，注销只删除当前用户拥有的记录。`GET /me` 返回 `android_device_count`，不返回设备 token。

管理员：沿用当前 `app/api.py` 中所有 `/admin/*` 路由，阶段 0 对每个管理容器补齐方法、参数、角色和分页 fixture；不根据页面名称猜测响应字段。

## Fixture 规则

- fixture 文件只保存脱敏 JSON/二进制元数据，不保存登录 token、cookie、二维码绑定码、外部个人资料或可复用的私密链接。
- 每个 fixture 文件名使用 `coverage-id__status.json`；请求 query/body 写在同名 `.request.json`。
- 分页至少保留：首批、重复边界、空页、错误页和无下一页响应。
- 接口字段变更时同时更新 fixture、模型测试和 `coverage.csv`，不要以宽松 `Map<String, dynamic>` 掩盖合同漂移。
