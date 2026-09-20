# V Push：ARM 中间层（采集 + 对接 vpush）

**状态：** 2026-09-20 Kale 口径（以此为准）
**作废：** v3「ARM 只做备份」；「生产继续挂存储机、ARM 回写存储 NFS」。

## 0. 一句话

**ARM = 采集 + 中间层。vpush 只连 ARM。**
存储机和 115 是冷备份，不是现网读源，也不是采集主通道。

## 1. 分层

| 层 | 谁 | 干什么 |
|---|---|---|
| 现网 | **vpush → 只连 ARM** | 展示、下载、IMA pull、中金命令，都不直接碰存储机 / 115 |
| 工作机 | **ARM** | 采集（**只增量**）、热缓存、NFS/门面给 vpush |
| 冷备份 | 存储机 NFS、115、OpenList 其他池 | ARM **定期把增量推出去**；ARM **不回拉旧日期** |

```
IMA / 中金 ──采集──► ARM staging/hot ──NFS 仅实验室──► 本机 Tailscale
                         │
vpush（本机盘）───────────┤  只走 HTTP ima-pull :8743 / GET /file
                         │
                         ├──► 存储机 NFS     （冷备份，生产不挂）
                         └──► 115            （冷备份）
```

## 2. 现网对照（2026-09-20）

| 组件 | 状态 |
|---|---|
| 生产 vpush | 归档必须是**本机盘**；`IMA_PULL_URL` 仍指存储 8743 ← 网络通了改 ARM HTTP，**不改挂载** |
| ARM ima-pull | **active** `100.112.25.21:8743` → `/srv/vpush-ima`（另有 `GET /file`） |
| ARM puller_loop | 在跑 → 115 + hot |
| OpenList | `/lab-hot` Local；`/vpush` 115 Cloud |
| ARM nfs-kernel-server | Tailscale `100.64.0.0/10` 导出 `/srv/vpush-ima`（实验室用，生产不挂） |
| 采集 timer | IMA apply 已开；CICC 仍 DRY_RUN / disabled |

## 3. 生产隔离（存储/ARM 挂了也不能拖垮 vpush）

**生产主机禁止内核挂载远程 NFS（ARM 和存储都不挂）。**
存储机挂了把 DMIT 拖进 D-state，就是硬 NFS + `main-health` 每分钟 `stat`/`mount` 造成的。再把 ARM 用同样方式挂上去，ARM 一挂生产照样死。

| 通道 | 怎么连 | 对端挂了会怎样 |
|---|---|---|
| 归档盘 | **本机目录**（`IMA_ARCHIVE_HOST_PATH` 必须是本地盘） | 无影响 |
| 采集 / 缺文件 | HTTP `IMA_PULL_URL` / `GET /file`，超时 + 熔断 | IMA/中金降级，站点其余正常 |
| 中金命令 | 只写本机 `.cicc`；路径若是 NFS **直接拒绝** | 管理页 503，不卡 uvicorn |
| 健康检查 | 默认 `IMA_ALLOW_NFS_REMOUNT=0`，不 `mount`、不碰 NFS 树 | 写本地 status JSON，结束 |

ARM 上的 NFS 导出只给实验室/本机 Tailscale 用，**不是**生产 bind-mount。不要开 `IMA_ALLOW_NFS_REMOUNT=1`，不要跑 `vpush-ima-recover` 那种自动 `mount` + recreate。

不要在生产 compose 开 `VPUSH_ARM_MIDDLEWARE`（那会让 vpush 容器自己写 ARM staging 路径，容器里没有这棵盘）。

以后才要动代码的情况：vpush 直读 OpenList/115、或日期分片布局。不要做「ARM 从冷池回拉旧日期」。

## 4. 只增量

ARM **不拉旧日期、不回填 118G**。`ima_to_arm_staging` 全库 remap、存储机 rsync 进 ARM、按历史 MMDD 扫目录，都不做。

采集窗口：中金 `--days`（现网默认近 7 天）；IMA 只跟最新日目录 / `--limit`。切到 ARM 之后，vpush 现网是热窗口 + **切点之后的新文件**。更老的留在存储机/115 冷备份，不经 ARM 拉回来。

## 5. 接下来

1. 生产保持本地 `IMA_ARCHIVE_HOST_PATH`，停掉自动 NFS remount / recover。
2. 网络打通后只改 `IMA_PULL_URL` / `IMA_PULL_TOKEN` / `IMA_FETCH_URL` 指向 ARM HTTP，**不改挂载**。
3. ARM 开**增量**采集；存储机采集停掉（防中金双采）。存储机和 115 只收 ARM 推出去的增量冷备份。

## 6. 不变量

- 生产 compose 不写 `VPUSH_ARM_MIDDLEWARE` / `VPUSH_ARM_NFS_SYNC`
- **生产主机不挂远程 NFS**（ARM / 存储都不挂）；对端挂了只允许 HTTP 超时失败
- Ops / ima-pull / NFS 导出只走 Tailscale 或 WG，不绑公网
- secrets 600，不进 git
- ARM 只增量，不拉旧日期、不回填全库
- 中金配额/熔断不绕过
