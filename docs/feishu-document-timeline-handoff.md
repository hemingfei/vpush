# 飞书文档时间线交接

日期：2026-09-02
仓库：`icekale/vpush`（本地 `dav-subscription`）
发布：`v1.12.132` / `main` @ `98692a489153003bc4cb70cca7dd428a05d0b41f`
规格：`docs/superpowers/specs/2026-09-02-feishu-document-timeline-design.md`
计划：`docs/superpowers/plans/2026-09-02-feishu-document-timeline.md`（`docs/superpowers/` gitignore，已 `git add -f`）

本文不写 app secret、OAuth token、Fernet 密钥。生产密钥只在 VPS `.env` / SQLite。

---

## 一句话结论

- **代码已合进 main、打了 `v1.12.132`、overlay 到生产。** 后台会出现「研报库设置 → 飞书文档」。
- **生产还不能用。** `FEISHU_DOCS_APP_ID/SECRET` 为空，页面会显示「应用未配置」。
- **下一步只剩运维：** 飞开放平台建独立云文档应用 → 填 env → 管理员 OAuth → 粘贴 Wiki/Docx 链接 → 给用户 ACL。
- 不要和消息推送 `FEISHU_APP_*` 混用。

---

## 产品边界

飞书 Wiki/Docx 对话文档 → 研报库时间线。**不进动态 / Telegram / 飞书消息。**

不支持：spreadsheet、bitable、幻灯片、公开分享链、非 docx wiki。

飞书组 `feishu-*` 默认对所有登录用户开放（catalog 直接进 subscribed，读文档不查 ACL）。IMA 订阅库仍走 ACL。

---

## 代码在哪

| 层 | 路径 |
|---|---|
| 采集 / OAuth / 时间线归一化 | `app/feishu_documents.py`（`FeishuDocumentSyncService`） |
| 配置 | `app/config.py` → `FeishuDocumentsConfig` |
| 启动线程 | `app/main.py`（`DAV_UI_ONLY` 时不跑） |
| 管理 API | `app/api.py` `/api/admin/feishu-documents*` |
| 阅读 | 研报库 catalog/list；`type=feishu_timeline`；`GET /api/ima-documents/timeline/all` |
| 表 | `feishu_document_oauth`、`feishu_document_oauth_sessions`、`feishu_document_sources` |
| 读飞书来源 | `app/db.py` 的 GET/LIST 必须走 `_read_only_rows`（否则 catalog/list 会被 `DB._lock` 卡住） |
| 前端 | `app/static/app.js` 设置页 tab「飞书文档」；时间线阅读器 |
| 测试 | `tests/test_feishu_documents.py`；前端 tab 顺序在 `tests/test_frontend_interactions.py` |

归档：`IMA_ARCHIVE_ROOT/feishu-documents/{source_key_hash}/versions/{content_hash}/`
增量键：飞书 `revision_id`。失败保留 last-good。软删除不删磁盘。

---

## 环境变量

与 `FEISHU_APP_ID/SECRET`（机器人推送）分开。

| 变量 | 作用 |
|---|---|
| `FEISHU_DOCS_APP_ID` / `FEISHU_DOCS_APP_SECRET` | 云文档应用 |
| `FEISHU_DOCS_REDIRECT_URI` | 须与开放平台一致。生产应为 `https://vpush.net/api/admin/feishu-documents/oauth/callback` |
| `FEISHU_DOCS_SCOPES` | 默认 `wiki:node:read docx:document:readonly docs:document.media:download offline_access`，须与应用已开通权限一致 |
| `FEISHU_DOCS_INTERVAL_SECONDS` | 默认 60，最小 15 |
| `FEISHU_CREDENTIAL_KEY` | 已有。同时加密文档 OAuth token；换密钥要重新授权 |

Compose 已透传（`docker-compose.yml` / `docker-compose.prod.yml`）。生产 `/opt/vpush/.env` 里 ID/密钥仍空。

---

## 管理端流程

1. env 配齐后重启 / recreate `vpush`（单进程，不要再起一个打 SQLite）。
2. 管理员打开「研报库设置 → 飞书文档」→ OAuth（PKCE S256）。
3. 粘贴 `https://*.feishu.cn/{wiki\|docx}/{token}`。Wiki 节点必须是 docx。
4. 可启停、立即同步、移除（软删）。
5. 不用配 ACL。登录用户研报库直接看到飞书组。

API：

- `GET/POST /api/admin/feishu-documents`
- `POST /api/admin/feishu-documents/oauth/start`
- `GET|POST /api/admin/feishu-documents/oauth/callback`
- `PATCH /api/admin/feishu-documents/{id}`
- `POST /api/admin/feishu-documents/{id}/sync`
- `DELETE /api/admin/feishu-documents/{id}`

---

## 生产现状（2026-09-02）

- GitHub：`origin/main` `98692a4`，tag `v1.12.132`，Actions `33641005875` 成功。
- VPS overlay：容器 `1.12.132`，`app/feishu_documents.py` 在；`https://vpush.net/healthz` 200。
- 回滚镜像：`dav-subscription-vpush:rollback-feishu-docs-20260902-221741`
- 备份：`/opt/vpush/app-before-v1.12.132-20260902-221741.tgz`
- **飞书应用未配。** 配好前不要当功能坏了。
- **归档盘当前未挂上。** 存储机公网 `198.12.125.212`，WG `10.80.0.2`；VPS `10.80.0.1`。NFS 必须走 WG，不要改成公网。VPS↔存储机当时 70%–100% 丢包，`/mnt/vpush-ima` 空。飞书归档也落在这颗盘上，盘没挂时同步会因存储不可写失败。网络交接另写，别和这条混。

Overlay：同步 `app/` 到 `/opt/vpush/src/app`，`docker build -f /opt/vpush/src/Dockerfile.overlay`。SSH `root@179.255.150.134`，钥匙 `~/.ssh/vpush_prod_key`。

---

## 验证

```bash
.venv/bin/python -m pytest tests/test_feishu_documents.py tests/test_frontend_interactions.py tests/test_config.py tests/test_error_redaction.py -q
```

合入前全量曾 `1804 passed`。关键用例：未授信 URL 拒绝；ACL 未授权 404；授权后目录在 `subscribed`；tab 顺序 collect < feishu < zsxq。

---

## 不要做

- 不要把文档 OAuth 接到 `FEISHU_APP_*`。
- 不要推送到动态。
- 不要把 token 写入仓库 / 日志。
- 不要为飞书 GET/LIST 改回 `DB._rows`（会阻塞研报库读）。
- 不要在链路不稳时反复 recreate 带 NFS volume 的 `vpush`。
