# 知识库设置独立页设计

日期：2026-08-29
状态：已确认，待书面规格复核

## 1. 目标与范围

把管理员的 IMA 与知识星球设置从「数据源」拆成独立页面，让知识库采集、凭证和存储状态有固定入口，不再和雪球/微博/X 轮询挤在「抓取设置」里。

页面继续是值班台：灰底白面、1px 描边、可扫、控件稳定。采集业务逻辑、知识库阅读桌、普通用户「推送设置」不变。

## 2. 已确认决策

- 做法：搬家现有表单，采集/凭证 API 不动；只为存储增加刷新和备份。
- 入口：侧栏「数据与日志 → 知识库设置」，路由 `/admin/knowledge`，仅管理员。
- 页内：一页三段长页，顺序为 IMA → 知识星球 → 存储。不用页内 tab，不用左右栏。
- 保存分块：IMA 采集、IMA 凭证、星球 Cookie、星球抓取各用现有保存；不做一个超级保存。
- 手机同步：说明如何在本机跑 `scripts/ima_phone_sync.command`，并显示 Refresh Token 是否已保存。网页不 SSH、不跑 adb、不新建同步日志表。
- 存储：只读状态（含 Restic 上次成功/检查摘要）+「刷新状态」「立即备份归档」。不做网页重挂载或重建容器。
- 数据源：IMA/星球整段搬走，抓取设置和 Cookie 管理各留一行链接到本页。雪球/微博/X、代理、广场保留。

## 3. 范围

包含：

- 新路由 `/admin/knowledge` 与侧栏项。
- 将下列区块从 `admin/stats` 搬到本页，保留现有字段 ID、onclick 和 payload 形状：
  - IMA 文档采集（UID、间隔、Refresh Token、共享知识库/文件夹、保存采集配置、立即同步、采集/存储状态行）
  - IMA 凭证（网页 Cookie、OpenAPI Client ID / API Key）
  - 知识星球抓取（翻页、间隔、预缓存、评论、App 通道、设备标识、附件缓存清理）
  - 知识星球 Cookie
- 手机同步说明 + Refresh Token `set` 状态。
- 存储只读面板 + 刷新/备份按钮及对应管理接口。
- 数据源旧入口删除对应区块并加链接；知识库空状态「去配置采集」改为进入本页。
- 数据源「保存抓取设置」不再提交 `zsxq_*`；本页「保存星球设置」只提交 `zsxq_*`。
- 前端契约测试与存储接口测试；递增静态资源版本。

不包含：

- 网页触发 NFS 重挂载、`docker compose` 重建、改 Restic/WireGuard 密钥。
- 普通用户设置页、知识库阅读桌、订阅/授权链。
- 新聚合「知识库设置」API、新颜色/组件库、JuiceFS/CDN。
- 把本机同步脚本改成服务端任务。

## 4. 信息架构

侧栏「数据与日志」现有项后插入：

```text
数据源
知识库设置   ← /admin/knowledge
帖子
…
```

`/admin/knowledge` 三段：

1. **IMA**
   - 凭证（从 Cookie 管理搬来）
   - 连接与同步、共享知识库与文件夹（从抓取设置搬来）
   - 保存采集配置、立即同步、状态行
   - 手机同步：README 已有步骤的精简说明 + Refresh Token 已保存/未保存
2. **知识星球**
   - Cookie（从 Cookie 管理搬来）
   - 抓取字段与缓存清理（从抓取设置搬来）
   - 保存星球设置
3. **存储**
   - 只读：`status`、可用/可写、用量、inode、流量档、Restic 上次成功时间、上次检查时间与是否通过
   - 刷新状态、立即备份归档

数据源页：

- 抓取设置只留全局轮询、雪球组合、次要大V、通道、保活。
- Cookie 管理只留雪球、微博、X。
- 两处 section-meta 或一行 muted 链接：「IMA 与知识星球设置已移至知识库设置」。

## 5. 数据流与接口

### 5.1 沿用

| 操作 | 接口 |
|---|---|
| 保存/读取 IMA 采集、发现、同步 | 现有 `/api/admin/ima-collector*` |
| 保存 IMA 凭证 | 现有 IMA credentials |
| 保存/清除知识星球 Cookie | 现有 zsxq cookie |
| 保存星球抓取 | 现有 `PUT /api/admin/polling-config`，body **只含** `zsxq_*` |
| 保存数据源抓取 | 同一 PUT，body **不含** `zsxq_*`（后端对缺失字段本就不改） |
| 清理星球缓存 | 现有 purge |

字段 ID（`ima-pure-*`、`pc-zq-*`、`ima-cookie`、`zq-cookie` 等）保持不变，前端测试继续按 ID 锁定。

本页若轮询采集状态：只更新状态文字，不重绘 `#ima-kb-list` / `#ima-folder-tree` 未保存勾选。保存后焦点恢复规则与现页相同。

### 5.2 新增存储接口

应用进程不直接 `systemctl` 宿主机或 SSH 到存储机。用请求文件 + 宿主机 systemd path：

- `POST /api/admin/ima-storage/refresh`（管理员）  
  在主 VPS 数据目录写入刷新请求文件（bind mount 内、无密钥）。主 VPS path unit 启动 `vpush-ima-main-health.service`。接口随后读取本地 status JSON，返回 `ImaStorageStatus.public()` 的扩展允许列表。
- `POST /api/admin/ima-storage/backup`（管理员）  
  在归档挂载根写入备份请求文件（无密钥）。存储 VPS path unit 启动 `vpush-ima-restic-backup.service`。已有备份在跑时返回「已启动/进行中」，不重复排队。归档不可写或远程归档未启用时 409/503，文案「当前部署未启用远程归档」或「知识库存储暂不可用」，不 500 整页。

`public()` 与主 VPS 聚合 status JSON 允许增加：`restic_last_success`、`restic_last_check_at`、`restic_last_check_ok`（Unix 时间或 boolean），从存储机 health JSON 原样拷贝。禁止路径、IP、仓库 URL、密码。未配置远程归档时 `status` 仍为 `local`，按钮按未启用处理。

请求文件与 path unit（`deploy/ima-storage/`，权限 `0640`，属主 `99:100`）：

- 刷新：主 VPS `/opt/vpush/data/.vpush-ima-refresh-request` → 启动 `vpush-ima-main-health.service`
- 备份：归档根 `.vpush-backup-request` → 启动 `vpush-ima-restic-backup.service`

不把主机密钥写进应用配置。

## 6. 视觉与响应式

- 复用 `section-panel`、`cfg-group`、`cfg-fields`、`cfg-foot`、`form-control`、`btn-normal`、`btn-ghost` 和 DESIGN.md token。
- `max-width: 800px` 单列；操作按钮高度至少 44px。
- 不新增阴影、渐变、品牌色块。
- 递增 `index.html` 资源版本与 `sw.js` cache 名称。

## 7. 错误与权限

- 非管理员访问 `/admin/knowledge` 与现有后台页相同（重定向或 404，不新造规则）。
- 保存/同步失败走现有 `api()` flash。
- 刷新/备份失败只返回短原因，日志脱敏，响应无主机路径。
- 备份按钮在请求期间禁用，避免连点。

## 8. 测试

- `tests/test_frontend_interactions.py`：新路由与侧栏文案；本页含 IMA/星球/存储三段；`admin/stats` 抓取/Cookie 不再含这些区块但含迁出链接；空状态 `go('admin/knowledge')`；数据源保存函数不读 `pc-zq-*`，星球保存只读 `pc-zq-*`。
- 存储接口：刷新/备份成功、进行中、未启用；`public()` 无密钥字段。
- 既有 IMA、星球、Cookie、polling 测试保持通过。
- `node --check` 静态 JS。

## 9. 验收

- 管理员能从侧栏进入本页，配完 IMA 凭证和采集、星球 Cookie 和抓取，而不打开数据源抓取/Cookie 里的对应表单。
- 数据源保存轮询不会改掉星球抓取值。
- 存储面板能显示公开状态；刷新会更新检查时间；备份在已启用远程归档时能请求启动。
- 桌面/手机单列可用，未保存的文件夹勾选不被状态轮询清掉。
