# IMA 文档中心接入设计

> 日期：2026-08-25
> 状态：已获用户确认，待实现

## 目标

将已验证的 IMA 纯 VPS PDF collector 接入 VPUSH，作为独立的 IMA 文档中心。PDF/TXT 不进入动态推送流；所有登录用户可以浏览已归档文件，只有管理员可以配置凭据和触发同步。

## 方案

保留现有 `ImaFetcher` 的 Cookie/OpenAPI 动态抓取兼容路径，新增独立文档服务。文档服务复用纯 VPS 协议实现：分页读取知识库清单，按 `media_id` 增量调用 `get_media`，下载短时签名 PDF，生成 TXT，并将 manifest/state 写入 VPUSH 数据目录。VPUSH 内置每日任务，不增加外部 cron。

## 配置

管理员在现有「数据源 → Cookie 管理 → ima」区域配置纯 VPS 模式：

- `IMA UID`：默认 `001aa361168019ef`，允许管理员修改。该值可从 IMA 登录 Cookie 中的 `IMA-UID` 字段确认。
- `Refresh Token`：首次由管理员粘贴；保存后只显示掩码，不通过 GET/API 原文返回。不要从聊天或日志复制旧 token，重新登录后粘贴新 token。
- `知识库 ID`：默认 `7464369361259867`，可修改。
- `根文件夹 ID`：默认 `folder_7489327974078249`，可修改。
- `同步间隔`：默认 1 小时，最小 30 分钟；每次仅下载新条目，避免频繁触发接口。
- `立即同步`：管理员手动启动一次，服务端使用锁防止并发运行。

Refresh token 不写入源码、compose、日志或前端初始值。环境变量可作为部署兜底；数据库设置只保存服务端使用的凭据，API 永不返回原文。

## 数据与 API

数据目录：`<DB_PATH 所在目录>/ima/`。

- `manifest.json`：当前知识库条目元数据。
- `state.json`：每个 `media_id` 的 PDF/TXT 相对路径、大小、MD5、字符数、下载时间。
- `<day>/<safe-name>.pdf` 与 `<day>/<safe-name>.txt`：归档文件。

用户 API：

- `GET /api/ima-documents`：登录后读取已完成归档，支持 `q` 与 `day` 筛选。
- `GET /api/ima-documents/{media_id}/text`：登录后读取 TXT。
- `GET /api/ima-documents/{media_id}/pdf`：登录后读取 PDF，支持 inline/download。

管理员 API：

- `GET /api/admin/ima-collector`：返回掩码配置与运行状态。
- `PUT /api/admin/ima-collector`：保存非空配置字段和 token。
- `POST /api/admin/ima-collector/sync`：启动一次后台同步。

所有文件访问通过 manifest/state 的 `media_id` 解析，禁止客户端传入文件路径。下载状态与错误只记录摘要，不记录 token、cookie 或签名 URL。

## 界面

桌面侧栏新增「IMA 文档」。移动端增加同一入口。文档列表按日期分组，支持标题搜索和日期筛选；详情页默认显示 TXT，提供 PDF 预览和下载。PDF 由已认证的前端 fetch 转成 Blob URL，避免受保护接口被 iframe 直接访问时丢失 Bearer token。

后台 IMA 配置区增加纯 VPS 字段、采集状态、成功/失败统计和立即同步按钮。旧 Cookie/OpenAPI 配置保持原样。

## 更新策略与风控

默认每小时检查一次清单，最小可调到 30 分钟；单次只下载新增条目。清单本身仍需遍历根文件夹和日期文件夹，使用 30 分钟以下间隔没有必要。同步使用全局锁，失败使用单文件隔离，不重复下载已完成 PDF/TXT。管理员手动同步仍遵守锁和最小间隔，不允许连续触发；通过增量状态避免重复请求。

## 测试

先写测试验证：

1. 默认配置包含目标知识库和根文件夹 ID，但 refresh token 不会出现在公开状态。
2. manifest/state 只允许安全的相对归档路径。
3. 已完成 `media_id` 不重复下载，缺 PDF 或 TXT 时可恢复。
4. 用户 API 需要登录，管理员 API 需要管理员权限。
5. PDF/TXT 接口返回正确媒体类型，未知 ID 返回 404。
6. 手动同步在锁占用时返回明确状态，不启动第二个任务。
