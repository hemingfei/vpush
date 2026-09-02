# 飞书文档时间线实施计划

> **For agentic workers:** 本计划对应已落地实现。新增行为先补测试。

**Goal:** 飞书 Wiki/Docx 进入研报库时间线，ACL 与 IMA 共用。

**Architecture:** `FeishuDocumentSyncService` 独立 OAuth/采集循环；归档在 IMA archive；读模型走 `publish_external_document`。

## File map

- Create: `app/feishu_documents.py`
- Create: `tests/test_feishu_documents.py`
- Modify: `app/db.py` `app/api.py` `app/main.py` `app/config.py` `app/ima_documents.py` `app/ima_search.py`
- Modify: `app/static/app.js` `app/static/style.css` `app/static/index.html` `app/static/sw.js`
- Modify: `.env.example` `docker-compose.yml` `docker-compose.prod.yml`
- Modify: `PRODUCT.md` `README.md` `docs/管理员手册.md`

## Tasks

- [x] URL 解析、时间线归一化、OAuth PKCE、加密凭据
- [x] 同步、last-good、只读存储拒绝、同轮串行
- [x] 研报库时间线阅读器与设置页「飞书文档」
- [x] ACL 复用 IMA；未授权 404
- [x] HTTP/前端回归测试
- [x] 产品文档与本规格

## 非目标

不改动态推送，不新增依赖，不把 token 写入仓库。
