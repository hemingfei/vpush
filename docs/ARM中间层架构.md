# V Push：ARM 中间层架构 v3（中间层终态，不迁移读源）

**状态：** 2026-09-20 定稿 · 尚未提交实施变更（本次只改 ARM 实验机与文档）
**历史：** v1 = 存储故障期桥接（`ARM中间层架构-v1-20260919.md`）；v2 = 权威树迁 ARM 块卷（**已取消**，见 git 历史 24730837）

## 0. 决策记录

- **2026-09-20，Kale：** 付费账户，不挂 OCI 块卷，只用自带 40G 盘；**ARM 只做中间层**。v2 的「权威树迁 ARM / 生产只挂 ARM 导出」连同回填、NFS 导出、切换窗口全部取消。
- 生产读源与采集主通道**保持现状**（存储机），生产零改动。

## 1. 实测基线（2026-09-19/20）

- **存储机 dedirock-828467392：采集链路完全存活。** cicc dispatch/status 每分钟、incremental 每小时、pdf-daily 每天、dedup 每周、compress-hourly 每小时、ima-storage-health 每 5 分钟；8743 puller active（只绑 10.80.0.2）；近 7 天新增 1055 个文件。
- 生产：挂 `10.80.0.2:/srv/vpush-ima`（118G，1008G 盘），零改动需求。
- ARM：单盘 46.6G（用 4.8G）；cache 现 20M；115 账本仅 **19 条**（lab 时代经手量）——**115 无全库副本，存储树为物理单点**。

## 2. 终态角色

| 角色 | 谁 | 说明 |
|---|---|---|
| 生产读源 + 采集主通道 | 存储机 | cicc 定时器 + 8743 puller 照旧，**零改动** |
| 采集（灾备/补采） | ARM lab sync | timer disabled + `DRY_RUN=1` 双保险；手动限量命令见 v1 交接 §6.2；平时不开，避免与存储机重复采集 |
| 115 备份通道 | ARM | puller_loop 容器（staging→115+hot，skip uploaded）+ cache_gc 水位（warn 30G / force 35G） |
| lab 视图 | OpenList `/lab-hot` + Ops :8055（Tailscale） | 只读浏览，不暴露 115 |
| 115 | 仅异步备份 | 永不进阅读路径；Cookie 失效不挡阅读 |

```
存储机树（权威，自采自写）
   │（P2 可选：增量镜像 rsync → ARM staging）
   ▼
ARM puller_loop ──► 115 /vpush/...（低频、断点、skip uploaded）
   └──► hot/（40G 滚动窗口，cache_gc 水位清理）
生产：照旧挂存储机 NFS，不知道 ARM 存在
```

## 3. 本次已就位（ARM，2026-09-19/20）

- 拆雷：两个采集 unit drop-in 改为 `Environment=DRY_RUN=1`（timer 本就 disabled，双保险）
- venv 补 `pymupdf`：cicc 灾备采集的去水印依赖就绪（aarch64）
- **GC 定时接线**：`vpush-cache-gc.timer` 每 30 分钟，`cache_gc.py --warn-gb 30 --force-gb 35`，dry-run 实测通过（此前 cache_gc 从未被调度）
- 清理 v2 遗留：卸载 nfs-kernel-server、删除 `vpush-ima-pull.service` 与 `ima-pull-arm.token`
- 仓库：v2 设计稿留档于 git 历史（24730837）；`docs/arm-middleware.md` §10.1 与 `arm_nfs_sync.py` docstring 口径修正继续有效（arm_nfs_sync 定位=存量合并/补采工具）

## 4. 开放决策（待 Kale）

1. **P2 · DR 回灌**：118G 是否分批经 ARM 回灌 115（数天~数周低频传输；当前 115 仅 19 个文件，存储树物理单点）。若做，顺带决定稳态「增量镜像」job（存储树 → ARM staging → puller 上 115），需注意 GC 水位与上传完成状态的无竞态次序（先传后清，`min-age-seconds` 只防新文件误删，不够）。
2. **Lab 本地脚本回仓**：`cache_gc.py`、`chinese_pdf.py`、`healthcheck.py`、`upload_once.py` 等 ~9 个脚本只存在于 `/opt/vpush-ima-lab/scripts/`，仓库没有（交接文档曾误标为仓库路径）。建议 Grok 提交入库或文档化。

## 5. 不变量（沿用，一条不减）

- 生产 compose 永不出现 `VPUSH_ARM_MIDDLEWARE` / `VPUSH_ARM_NFS_SYNC`
- 115 永不进阅读路径；OpenList 不暴露 115；Ops :8055 只走 Tailscale
- secrets 600 / 目录 700，不进 git
- 采集 timer 默认停，开采需 Kale 明确点头；`IMA_PULL_URL` 保持指向存储机 8743
- 不上 Memcached/Redis（缓存的是 PDF 文件，清单用 SQLite）
