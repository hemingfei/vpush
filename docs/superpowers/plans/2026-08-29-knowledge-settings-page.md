# 知识库设置独立页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or implement inline with TDD. Follow DESIGN.md Duty Console. End with DAV_UI_ONLY Chrome desktop/mobile regression.

**Goal:** 管理员 IMA/知识星球设置从数据源搬到 `/admin/knowledge`，并加上只读存储状态与刷新/备份请求。

**Architecture:** 搬家现有 markup 与字段 ID。采集/凭证 API 不动。`PUT /api/admin/polling-config` 按页拆字段。存储按钮只写请求文件，由 systemd path 启动现有 oneshot。

**Tech Stack:** 静态 SPA `app.js`/`style.css`、FastAPI、pytest 源码契约、systemd path、Playwright/Chrome 回归。

## File Map

- Modify `app/static/app.js`: NAV、`renderAdmin` loader、抽出知识库页、拆 `savePollingConfig`、cookie 保存按路由重载。
- Modify `app/static/style.css`: 知识库设置页复用 cfg/ima token，800px 单列，按钮 ≥44px。
- Modify `app/static/index.html` + `sw.js`: 资源版本。
- Modify `app/ima_storage.py` + `app/api.py`: public restic 字段；refresh/backup POST。
- Modify `deploy/ima-storage/*` + `tests/test_ima_storage_ops.py`: path units。
- Modify `tests/test_frontend_interactions.py` + `tests/test_ima_storage.py` + `tests/test_api.py`。

## Task 1: Frontend contracts

Failing tests for: NAV `admin/knowledge`；`loadAdminKnowledge` 含 IMA/星球/存储/手机同步；`loadAdminStats` 不再含这些区块但有迁出链接；空状态 `go('admin/knowledge')`；`savePollingConfig` 无 `zsxq_*`；新 `saveZsxqPollingConfig` 只有 `zsxq_*`。

## Task 2: Move UI

Implement the page with existing IDs/events. `reloadAdminSettingsPage()` 按路径调用 knowledge 或 stats。Cookie 的 ima/zsxq 不再 `replaceState` 到 cookies tab。

## Task 3: Storage APIs + path units

`public()` 增加 restic 三字段。POST refresh/backup 写请求文件。local 模式 409。

## Task 4: Verify

pytest 相关套件、`node --check`、Chrome 1440 浅/深 + 390 回归，删 harness。
