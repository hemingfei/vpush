# 飞书文档时间线设计

## 目标

把飞书 Wiki / Docx 对话文档收进现有研报库，按时间线阅读。不进动态推送。

## 设计决定

- 独立云文档应用：`FEISHU_DOCS_APP_*`，与消息推送 `FEISHU_APP_*` 分开。
- 管理员在「研报库设置 → 飞书文档」OAuth（PKCE S256）后粘贴 `https://*.feishu.cn/{wiki|docx}/{token}`。
- 只支持飞书 / Lark HTTPS 的 `/wiki/{token}` 与 `/docx/{token}`。Wiki 节点必须是 docx。
- 采集按 `revision_id` 增量；归档到 `IMA_ARCHIVE_ROOT/feishu-documents/{source_key_hash}/versions/{content_hash}/`。
- 时间线：时间戳分段、说话人、`A 回复 B`、首段时间戳前的提示、表格单元格去重。同分钟多条保留。
- 读模型复用 IMA catalog。飞书组（`feishu-*`）默认对所有登录用户开放，无需 ACL。
- 前端打开 `type=feishu_timeline` 时渲染时间线，不走 PDF 预览。图片走已登录 blob 接口。
- 失败保留 last-good 归档与读模型。软删除隐藏来源，磁盘版本不删。

## 非目标

- 不推送到动态 / Telegram / 飞书消息。
- 不支持 spreadsheet、bitable、幻灯片、公开分享链、非 docx wiki。
- 不把飞书 OAuth token 写入日志或 `.env` 以外的明文配置。

## 验收

- 登录用户在研报库看到飞书时间线，可按来源/日期/最新优先浏览。无需 ACL。
- 管理员可添加、启停、立即同步、移除来源；未配置应用时不能开始授权。
