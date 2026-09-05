# 中金研报采集 → 存储机自建库 运行手册

日期：2026-08-29 · 脚本：`scripts/cicc_report_collector.py` · 部署位置：存储 VPS `/root/cicc/`

## 链路

```
CICC 研报站(research.cicc.com, 需登录) → 存储VPS 采集脚本
  → /srv/vpush-ima/local/cicc-research/<品类名>/<MMDD>/<研报中文原名>_<id>.pdf
  → （主VPS 扫描 local/ 后进入 /knowledge，见本地库规格）
```

- **单库「中金点睛」**（2026-08-30 用户确认）：磁盘 `local/cicc-research/<网页品类名>/<MMDD>/`，
  品类信息保留在子目录 + 每篇文档标签（reportType/documentLabels）中；历史 11 个 `cicc-*` 品类库
  由 `cicc_meta_backfill.py` 步骤 0 幂等归并进单库。
- sidecar `.vpush-local-meta.jsonl`：官方摘要 + 标签（≤5）+ 作者 + 日期，按文件名尾缀 `_报告id` 匹配，
  规格见本地库设计文档 §11。
- 目录契约遵循 `docs/superpowers/specs/2026-08-29-local-storage-library-mount-design.md`：
  标记 `.vpush-local-library.json`（`enabled:false`，需管理页启用）、属主 99:100、目录 0750、文件 0640。
- 文件名 = 研报中文原名（非法字符换空格，超 200 字节截断）+ `_报告id`；`MMDD/` 取发布时间（北京时间）。

## API 要点（已验证）

| 用途 | 接口 |
|------|------|
| 分类树 | `GET /reports/api/v3/param` |
| 列表 | `POST /reports/api/v3/page`（body 见脚本 DEFAULT_BODY，`portalCategoryId`/`pubTimeStart`/`page`/`size`） |
| 详情 | `GET /reports/api/v3/detail?id=<列表项id>` → `signatureUrl` |
| 下载（默认，**不计配额**） | `GET <signatureUrl>` = `/reports/api/v3/fetchPdf/<token>` → PDF 二进制（在线阅读流） |
| 下载（旧，计配额） | `GET /reports/api/v3/download/<列表项id>` → PDF 二进制 |

- 鉴权：Cookie `SESSION` + `route`；请求头 `X-Time` = `floor(ms/10)` 拼 `(值%97)` 两位校验（防重放签名，错了返回 40000/40012）。
- `code 40010` = 登录态失效 → 更新 Cookie 重跑；单篇 40001「研报不存在」= 权限外，跳过。
- **去水印 + 无损压缩**：下载后落盘前内存处理（`strip_watermark`，2026-08-29 上线；2026-09-01 补压缩守卫）。中金经 iTextSharp 注入两类贴图水印
  （756×192 身份贴片=账号邮箱+时间戳、380×138 页中灰色大 logo），按图片尺寸识别、抹掉 `/ImN Do`
  绘制指令并清空图流；文本层/图表/页眉 logo 不受影响。
  压缩**纯无损**：`garbage=4, deflate, objstms` 重压流并回收未引用对象，**不重采样/重编码任何图片**
  （实测正文图 >300ppi 部分仅占体积 ~9%，有损降采样最多再省 ~5%，不采纳；如需 300ppi 降采样另议）。
  守卫：未剥水印且重压不省空间时保留原字节（体积只减不增）。fetchPdf 路径文件本身无下载水印、更小。
  依赖 VPS `apt install python3-fitz`（已装）；未装或处理异常自动跳过、保留原文，不阻断采集。
  `--self-test` 含去水印用例（构造水印图 PDF，断言渲染全白）。存量已入库的带水印文件不受影响，如需回刷另行处理。
- **`400013` = 本月下载数量达上限**（仅旧下载接口 `/v3/download/<id>` 触发；零售账户月配额 300 篇，2026-08-29 当天约下满 300 篇即触发）。
- **配额绕开（2026-09-01 上线）**：默认改走**在线阅读流** `GET /reports/api/v3/detail?id=` → `signatureUrl`（`/v3/fetchPdf/<token>`，带 `X-Time`）。实测：写不写入「我的下载」记录（`/v3/download/list` 309→309），即**不计月度下载配额**；内容与 download 版逐页一致、文本相同，且自带水印更少（少每页 1 张下载水印图）；detail 为读操作也不占配额。`--endpoint download` 可切回旧接口（计配额，触发 400013 会优雅退出）。水印剥离对两条路径都生效。

## 日常操作（存储 VPS root@198.12.125.212）

> 常规触发/进度已迁移到 vpush 管理页「知识库设置 → 中金」页签（见下节），日常无需 SSH。

```bash
# 更新登录态（浏览器 F12 复制 Cookie 整串）
vi /root/cicc/cookies.txt && chmod 600 /root/cicc/cookies.txt

# 增量（最近7天，已存在自动跳过）
nohup python3 -u /root/cicc/cicc_report_collector.py --days 7 > /root/cicc/incr.log 2>&1 &

# 今年回补（推荐，~4900 篇，3 路并行按品类分组，互不抢文件）
nohup python3 -u cicc_report_collector.py --since 2026-01-01 --categories 公司研究 > y2026_company.log 2>&1 &
nohup python3 -u cicc_report_collector.py --since 2026-01-01 --categories 行业研究,固定收益 > y2026_ind_bond.log 2>&1 &
nohup python3 -u cicc_report_collector.py --since 2026-01-01 --categories 宏观经济,市场策略,全球研究,量化及ESG,大宗商品,外汇研究,中金研究院,其他 > y2026_rest.log 2>&1 &

# 采完后的 gs 压缩回刷（低优先级，质量守卫：新件<原90%且页数+文本一致才替换）
nohup nice -n 19 ionice -c2 -n7 python3 -u pdf_backfill_compress.py --root /srv/vpush-ima/local/cicc-research --strip-watermark > compress_cicc.log 2>&1 &

# 全量回补（多年历史，>=5万篇，除非确定需要否则不建议）
nohup python3 -u /root/cicc/cicc_report_collector.py --all > /root/cicc/backfill.log 2>&1 &

tail -f /root/cicc/*.log     # 进度
```

状态文件 `/root/cicc/state.json` 已废弃（2026-09 起靠磁盘文件名幂等，可删）。

## vpush 管理页控制（2026-09 上线）

采集/压缩由 vpush「知识库设置 → 中金」页签远程控制，无需登录存储机。通道与既有
`.vpush-storage-health.json` 同款：主 VPS 容器经 NFS 读写归档内控制目录，存储机 systemd 消费，
无新网络服务、容器内不放 SSH 密钥。

```text
主 VPS 容器(vpush)                       存储机(198.12.125.212)
  /api/admin/cicc/* ──写──▶ local/.cicc/commands/<ms>-<mode>.json
       ▲                        │ vpush-cicc-dispatch.path 消费
       └──读── local/.cicc/status.json ◀── vpush-cicc-status.timer（60s）
               local/.cicc/incremental.enabled ◀── vpush-cicc-incremental.timer（03:00 北京时间）
```

- 页签能力：状态/库存/日志尾部、增量采集（近3天）、今年回补、全量回补、停止、压缩回刷、
  每日增量开关。
- 存储机单元与脚本：`scripts/vps/cicc-*.py`（canonical）+ `deploy/ima-storage/vpush-cicc-*.path/.service/.timer`，
  安装方式：`bash scripts/vps/install_cicc_batch1.sh` 开始，见 deploy/ima-storage/README「中金采集控制单元」。
- 幂等保护：已有采集进程在跑时 incr/year/all 会被拒绝（ledger 记 `collector_already_running`）；
  stop 仅杀采集进程，已下载文件保留，重跑自动续传。
- 命令失败由每分钟 dispatch timer 重扫，最多尝试 3 次；超过 24 小时的命令拒绝执行。
- incr/year/all 等待采集器真实退出后写结果；品类和关键词通过 JSON 文件传递，逗号不会改变关键词边界。
- API（仅管理员）：`GET /api/admin/cicc/status`、`POST /api/admin/cicc/trigger {mode}`、
  `PUT /api/admin/cicc/schedule {enabled}`；依赖 `IMA_ARCHIVE_ROOT` 指向 NFS 归档。

## PDF 去水印与压缩策略

中金新增文件在采集落盘前调用 `strip_watermark`；存量与后续增量由独立任务
`vpush-cicc-pdf-daily.timer` 每天北京时间 06:15 处理：

- 根目录固定为 `/srv/vpush-ima/local/cicc-research`，不扫描其他本地知识库。
- 先识别并移除中金 756×192 / 380×138 贴图水印，要求页数、书签、页面框/旋转和逐页文本层一致；
  去水印允许预期的渲染变化。
- 再运行 v3 压缩：小于原件 90%、至少节省 256 KiB，且 96dpi RGB 全页渲染逐像素一致才采用。
- 使用独立 root-scoped 状态；文件被覆写后自动重检。中金 daily 与全站 hourly 共用全局锁，在单核存储机上不会并行跑。
- 后台「压缩」按钮与 timer 使用同一入口：
  `pdf_backfill_compress.py --root /srv/vpush-ima/local/cicc-research --strip-watermark`。
- 2026-09-02 存量核查：5,108 份中 4,667 份只有已清空的水印 image 空流，441 份无目标资源，
  **活跃水印为 0**；不做无意义的存量重写。首次 daily 只建立 v3 状态，后续处理新增或被覆写文件。

全站非中金 IMA 增量仍由 `scripts/pdf_backfill_compress.py` 的默认根目录处理：

- **IMA-flat-v3**：检测完整嵌入的微软雅黑，优先用 PyMuPDF `subset_fonts()` 无损子集化；
  其他 PDF 或子集化未达到门槛时才走 Ghostscript `/prepress`。
- **采用门槛**：压缩后小于原件 90%、至少节省 256 KiB，并且页数、所有页面框/旋转、书签、逐页文本层
  和 96dpi RGB 全页渲染逐像素一致。签名、表单、批注、附件、图层、链接或 tagged PDF 一律保留原件；
  投行原版已优化或整页 JPEG 的文件会自动跳过，不降低 DPI。验证器不可用/异常只记临时失败，下小时重试。
- **状态与并发**：状态按 root 隔离；全站使用 `compress_state.json`，其他 `--root` 使用独立哈希文件。
  每条记录包含 path + size + mtime_ns + inode + strategy_version；同路径被 puller 覆写或策略升级后自动重检。
  puller 与压缩器在最终替换时共同锁住父目录，替换前复核源指纹；状态和 PDF 都使用 fsync + 原子替换。
- **调度**：`vpush-compress-hourly.timer` 每小时低优先级运行一次（`nice 19 + ionice`）。全库无任务空扫约 3 秒；
  新文件仍跳过 120 秒，避免与下载进程冲突。
- 安装/迁移：`bash scripts/vps/install_compress_hourly.sh`（会删除旧 monthly unit）。
- 手动试跑：`python3 -u /root/cicc/pdf_backfill_compress.py --dry-run --limit 20`。
- 手动执行：`nice -n 19 ionice -c2 -n7 python3 -u /root/cicc/pdf_backfill_compress.py`。

2026-09-01 基准：38 个遗漏的 IMA-flat 大文件 655.3MB → 117.0MB，逐页文本完全一致；
最大样本及 KR 样本的 96dpi 渲染逐像素一致。Ghostscript 处理 KR 虽更小，但会损坏部分复制/搜索文本，
因此 v3 使用 RGB 全页像素校验，且不能放宽文本层校验。

## 全站 PDF 去重（2026-08-30）

- `scripts/pdf_dedup_hardlink.py`（VPS `/root/cicc/`）：同体积 → 不同 inode 才计算 sha256 → 多余路径换成
  指向「mtime 最老」正本的**硬链接**。两条路径都保留（ima 索引/访问零变化），存储只占一份；
  已共享 inode 的路径跳过，与压缩任务共用进程锁；替换时与 DMIT、ima-puller、压缩器共用归档根
  `.vpush-pdf.lock` POSIX 锁，跨 NFS 主机互斥。排除 `local/`；幂等可重跑。
  - dry-run：`python3 -u /root/cicc/pdf_dedup_hardlink.py`；执行：加 `--apply`（建议 nice -n 19）
- `vpush-cicc-dedup.timer` 每月 1 日北京时间 04:10 自动运行，避开 04:00 整点压缩后做存量收尾。
- 2026-08-30 首跑：465 组重复、合并 467 个文件、释放 1.34GB（多为同研报重复上传，文件名带 `(1)`/`(2)`）。
  已各自压过的副本字节不同（gs 内嵌时间戳）合不了，属预期。压缩回刷跑完后可再跑一次去重收尾。

## 已知边界

- **月度下载配额**（400013）只作用于旧 `/v3/download/<id>` 接口；默认 `viewer` 路径（fetchPdf 在线阅读流）实测不写下载记录、不触发配额。若未来 fetchPdf 也被纳入配额，切换 `--endpoint download` 并等配额重置即可（断点续传不受影响）。
- fetchPdf 的 token 由 detail 实时签发，不做缓存；同一报告反复拉取不重复计数（实测）。
- 本地库扫描（主VPS 读 `local/` 入 /knowledge）**尚未实现**（规格状态「待确认」）；当前落盘即入库位，功能上线后即可见。
- CICC 列表 `totalElements` 上限显示 9999；按品类+日期窗口分页可绕开。
- 匿名访问只有首页推荐可用，列表/详情/下载全部需要登录。
