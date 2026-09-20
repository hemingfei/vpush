# V Push：ARM 中间层（NFS + 115 兼容）

日期：2026-09-19 · 状态：仓库已落地适配（**默认关**，含 nfs-sync）· 现网仍只读浏览、不采集  
主机：Oracle-SJ-ARM（约 45G）· OpenList 实验根 `/lab-hot`（**不暴露 115**）

采集默认仍写存储机 POSIX/NFS 布局。打开中间层后，采集器只写 ARM staging；上传只走仓库内的 `scripts/puller_loop.py`（部署到 `/opt/vpush-ima-lab/scripts/`，宿主机 systemd）；存储恢复后再用 `arm_nfs_sync`（默认关）生成旧 NFS 布局。生产 compose 不打开中间层或 nfs-sync 开关，也不跑 puller。

## 1. 目标

把 ARM 做成采集与对象存储之间的中间层，同时兼容：

- **旧路径：** 生产 `vpush` 依赖的 POSIX/NFS（`/mnt/vpush-ima` → 原存储机布局）
- **新路径：** 115 对象仓（全量权威，实验根 `/vpush`，OpenList 暂不挂出）
- **读门面：** OpenList（现仅 Local 热缓存按 `YYYY/MM/DD` 浏览）

## 2. 非目标

- ARM 不存全库（~130G）；只存热缓存 + SQLite 清单
- **现在不开启中金/IMA 采集**（适配默认关闭，仓库不跑 live 采集）
- 不把 115 挂载暴露给 OpenList 用户
- 不改生产 `docker-compose*.yml` 默认行为

## 3. 数据流

```
采集器(中金/IMA)  --默认关-->  ARM /data/vpush-ima-cache/staging/
                                    |
                              puller_loop
                         /              \
                        v                v
              115 /vpush/...      （存储恢复后）NFS 兼容布局同步
              （对象权威）         → 供生产挂载或 ARM 再导出
                                    |
                              hot/ + lab.sqlite
                                    |
                              OpenList /lab-hot（只读浏览）
```

## 4. 目录契约

### 4.1 ARM 本地（权威清单在 SQLite）

```
/data/vpush-ima-cache/
  staging/local/cicc-research/YYYY/MM/DD/<sanitized>_<id>.pdf
  staging/local/cicc-research/YYYY/MM/DD/<sanitized>_<id>.json   # 可选 sidecar，对齐日后 lab.sqlite
  staging/local/ima/<group>/YYYY/MM/DD/<filename>.pdf
  hot/local/cicc-research/YYYY/MM/DD/...
  failed/...
  manifest/lab.sqlite
```

### 4.2 115（对象权威，OpenList 不暴露）

```
/vpush/local/cicc-research/YYYY/MM/DD/...
```

### 4.3 旧 NFS 兼容布局（存储恢复后由 `scripts/arm_nfs_sync.py` 生成，默认关）

与现网 `cicc_report_collector` 默认契约对齐，便于生产无改挂载：

```
.../local/cicc-research/<品类>/<MMDD>/<中文名>_<id>.pdf
.../local/cicc-research/.vpush-local-library.json
.../local/cicc-research/.vpush-local-meta.jsonl
```

IMA 现网落盘是 `<group_id>__<hash>/<MMDD>/`（无年份）。中间层负责 **staging 日期分片 ↔ 旧品类/MMDD 视图** 的映射（可硬链/拷贝/导出）。

## 5. 组件

| 组件 | 职责 | 现状 |
|---|---|---|
| puller_loop | staging→115；清单；失败重试 | **已入库（宿主机权威副本）** `scripts/puller_loop.py` + `lab_common.py` + `manifest.py`（拷到 `/opt/vpush-ima-lab/scripts/`；systemd，不是生产 compose）。`upload_ok` 为假则 raise，`call_with_retry` 处理 Multipart/空 filesha1，耗尽后进 `failed/` |
| OpenList | 只读浏览 hot | `/lab-hot` 日期入口；115 disabled |
| cicc 适配 | 写 staging 日期分片，默认关 | `scripts/cicc_report_collector.py` |
| cicc lab sync | ARM 限量 list+download → staging，默认关 | `scripts/cicc_arm_lab_sync.py` |
| ima live write | 新 PDF 直接写 staging 日期分片，默认关 | `app/ima_documents.py`（`VPUSH_ARM_MIDDLEWARE=1`） |
| ima lab sync | ARM 限量 list+download → staging，默认关 | `scripts/ima_arm_lab_sync.py` |
| ima remap | 旧归档树拷进 staging，默认关 | `scripts/ima_to_arm_staging.py`（不下载） |
| nfs-sync | hot/staging → 旧 NFS 布局 | **已落地（默认关）** `scripts/arm_nfs_sync.py`（`--enable` / `VPUSH_ARM_NFS_SYNC=1`；独立于中间层开关） |
| arm-lab-ops | 实验室看板 + 115 QR + 确认后的限量动作 + 同步/并发旋钮 | **phase 3** `arm-lab-ops/`（优先 Tailscale `:8055`；备选 loopback + SSH；不是生产后台；**不要**写进生产 compose） |

## 6. 开关

- `VPUSH_ARM_MIDDLEWARE=0`（默认，或不设）：采集器保持原存储机行为
- `VPUSH_ARM_MIDDLEWARE=1` 或 `--arm-middleware`：中金与 IMA **新下载**改写到 ARM staging 日期布局；**不直接写 NFS/115**
- `VPUSH_ARM_STAGING_ROOT`：staging 根，默认 `/data/vpush-ima-cache/staging`
- `VPUSH_CICC_COOKIE_FILE`：覆盖中金 Cookie 文件路径（不要把 Cookie 写进仓库）
- `CACHE_ROOT`（puller，默认 `/cache`）：宿主机 staging/hot/failed/manifest/logs。须与采集 `VPUSH_ARM_STAGING_ROOT` 指向同一棵 staging 树
- `P115_LAB_ROOT`（默认 `/vpush`）、`P115_COOKIES_FILE`（默认 `/secrets/115-cookies.txt`，**只是路径**）、`P115_DEVICE_TYPE`（默认 `harmony`）
- `VPUSH_ARM_NFS_SYNC=1` 或 `--enable`（`arm_nfs_sync.py`）：存储恢复后映射 hot → 旧 NFS；**独立于**中间层开关；默认 dry-run，须 `--dest` / `VPUSH_NFS_SYNC_DEST`
- 上传仅由 puller 负责；禁止采集器直写 OpenList/FUSE
- IMA 打开中间层后不走 `IMA_PULL_URL`（存储机 NFS puller）；旧归档 remap 仍用 `scripts/ima_to_arm_staging.py`
- **上传只走宿主机权威 `scripts/puller_loop.py`**（拷到 `/opt/vpush-ima-lab/scripts/`，`--once` 或循环）；`ima_arm_lab_sync` / `cicc_arm_lab_sync` / `arm_nfs_sync` 都不上传 115
- **不要把 `VPUSH_ARM_MIDDLEWARE=1` 写进生产 compose**（也不要写 `VPUSH_ARM_NFS_SYNC=1`）

CLI 兼容：不传新 flag、不设新环境变量时，`--root` 仍默认 `/srv/vpush-ima/local`，布局仍是 `<品类>/<MMDD>/`，属主 99:100 仅在该经典根且以 root 跑时执行。

## 7. 中金适配（默认关）

```bash
# 存储机（默认，勿开中间层）
python3 cicc_report_collector.py --days 7

# ARM 中间层（显式打开；仍不要对现网 CICC 跑采集，除非有意启用）
VPUSH_ARM_MIDDLEWARE=1 python3 cicc_report_collector.py --days 7
# 或
python3 cicc_report_collector.py --arm-middleware --days 7
```

中间层落盘：

```
$VPUSH_ARM_STAGING_ROOT/local/cicc-research/YYYY/MM/DD/<sanitized>_<id>.pdf
$VPUSH_ARM_STAGING_ROOT/local/cicc-research/YYYY/MM/DD/<sanitized>_<id>.json
```

ARM 实验室限量同步（默认关；启用后默认 dry-run；`--apply` 才下载；不上传 115）：

```bash
python3 scripts/cicc_arm_lab_sync.py
python3 scripts/cicc_arm_lab_sync.py --enable --dry-run --limit 3 --days 7
python3 scripts/cicc_arm_lab_sync.py --arm-middleware --apply --limit 3 --days 7
```

Cookie 走 `VPUSH_CICC_COOKIE_FILE` / `--cookie-file`（与采集器相同，不打日志）。配额/熔断不绕过。说明见 [cicc_arm_lab_sync.md](../scripts/cicc_arm_lab_sync.md)。

离线自检（不访问中金）：`python3 cicc_report_collector.py --self-test`

手册见 [cicc-report-collector.md](cicc-report-collector.md)。

## 8. IMA 适配（默认关）

三条路径，都默认关。前两条不读 IMA Cookie / Refresh Token；实验室限量同步才读凭据：

1. **Live write** — 新下载直接写 staging。开关：`VPUSH_ARM_MIDDLEWARE=1` 或 `--arm-middleware`。
2. **Remap** — `scripts/ima_to_arm_staging.py` 只拷已有归档树，不从 IMA 下载。
3. **Lab sync** — `scripts/ima_arm_lab_sync.py` 在 ARM 上 list + 限量 download → staging。默认关；启用后默认 dry-run。

未开中间层时，puller / 文档中心仍写存储机 `<group>/<MMDD>/`。**115 仍由 `scripts/puller_loop.py` 上传**，采集脚本不直写对象仓。

```bash
# live：离线打印落盘路径（不下载、不读凭据）
python3 -m app.arm_middleware --arm-middleware --print-dest --group legacy --day 0918 --name demo.pdf

# lab sync：默认什么都不做
python3 scripts/ima_arm_lab_sync.py

# lab sync：dry-run 列 media_id / title / dest（须凭据才能列 IMA）
python3 scripts/ima_arm_lab_sync.py --enable --dry-run --group legacy --limit 3 \
  --secrets /root/ima-pure-secrets.json

# remap：只列将要复制的路径（不写盘、不读 IMA 凭据）
python3 scripts/ima_to_arm_staging.py --enable --dry-run --source /path/to/ima-archive
```

Live / lab 落盘：

```
$VPUSH_ARM_STAGING_ROOT/local/ima/<group_id>/YYYY/MM/DD/<safe_filename>.pdf
```

日期优先 IMA 日目录 MMDD；否则北京时间 mtime/now。凭据文件须 0600，形状 `{"uid","refresh_token"}`。**不要把 `VPUSH_ARM_MIDDLEWARE=1` 写进生产 compose。**

说明见 [scripts/ima_arm_lab_sync.md](../scripts/ima_arm_lab_sync.md) 与 [scripts/ima_arm_staging_adapter.md](../scripts/ima_arm_staging_adapter.md)。

## 9. 成功标准（启用采集后才验收）

- 增量落入 staging → sqlite → 115 抽查可读
- 存储恢复后：旧 NFS 布局可被生产挂载读到同批文件
- ARM 缓存水位：≥30G 告警 / ≥35G 清理 staging+hot
- Cookie/配额熔断与现网一致，不绕过中金月度配额

## 10. 实施顺序

1. 本文档 + 仓库适配（已落地；默认关）
2. 中金 → staging 适配（已落地；默认关）
3. IMA live write + 旧树 remap + ARM lab sync（已落地；默认关）
4. 存储恢复后：NFS 兼容同步器 — **已落地（默认关）** `scripts/arm_nfs_sync.py`（见 [arm_nfs_sync.md](../scripts/arm_nfs_sync.md)）
5. 阅读台切流 — 运维决策，见下方决策记录（本仓库不改 live UI、不改生产 compose）
6. 实验室 puller 入库 — **已落地（宿主机原件）** `scripts/puller_loop.py` + `lab_common.py` + `manifest.py`（见 [puller_loop.md](../scripts/puller_loop.md)）；拷到 `/opt/vpush-ima-lab/scripts/`
7. 中金 ARM 限量同步 — **已落地（默认关）** `scripts/cicc_arm_lab_sync.py`
8. ARM 实验室运维面板 — **phase 3 已入库** `arm-lab-ops/`（状态 + 115 QR + 确认后的 IMA/CICC 限量触发与 failed 重入 + 同步时钟/并发旋钮；不是阅读台 / 生产后台）

ARM 实验室 `puller_loop` / 同步 timer 是**宿主机 systemd**（脚本在仓库，timer 由 ops 另做），不是生产 compose 服务。**不要把 `VPUSH_ARM_MIDDLEWARE=1` 写进生产 compose。**

### 10.1 阅读台切流决策记录（item 5）

**目标态已更新（2026-09-19 v2）：权威归档树迁 ARM 块卷，生产最终只挂 ARM 导出；存储机冻结为冷备。** 全量设计（容量/回填/切换窗口/风险）见 [ARM中间层架构.md](./ARM中间层架构.md)。本节保留 v1 历史记录：

| 选项 | 何时 | 本仓库 |
|---|---|---|
| 恢复原存储 NFS，生产继续挂它 | v1 历史默认（存储故障期） | 不改 reading UI / compose |
| 挂 ARM 导出的 NFS | **v2 目标态**（回填+试挂验收后切换） | 运维决策，按 v2 设计执行；不在常规 PR 启用 |

`arm_nfs_sync` 在 v2 中降级为 lab 存量合并/补采工具（一次性合入权威树），不再承担稳态写路径。

## 11. ARM 实验室运维面板（phase 3）

`arm-lab-ops/` 是给 Oracle-SJ-ARM 中间层用的薄运维 UI：看缓存水位、puller / timer、凭据是否在场，以及 **115 QR 写 Cookie**。Phase 2 增加 **IMA 同步摘要**、**failed 重入 staging**、以及 **确认后的限量 IMA/CICC dry-run/apply**。Phase 3 增加 **实验室旋钮**（每日同步时钟、IMA/CICC limit、IMA 并行、`PULLER_BATCH_SIZE`），写入 `$CACHE_ROOT/ops-lab-settings.json`。它不是阅读台，也不是生产 vpush 后台。**不要把本服务或 `VPUSH_ARM_MIDDLEWARE=1` 写进生产 compose。**

- **访问（口令仍要）：** Oracle-SJ-ARM 走 Tailscale。① 优先绑 Tailscale IPv4（`ARM_OPS_BIND=tailscale` 或 `tailscale ip -4` 的地址）`:8055`，同 tailnet 打开该 URL。② 备选 `127.0.0.1:8055` + `ssh -L 8055:127.0.0.1:8055`。③ **不要**在公网 NIC 发布 `0.0.0.0:8055`。uvicorn 绑 IP 不绑网卡名；compose 用 host 网络，见 `arm-lab-ops/docker-compose.snippet.yml`。也可用 `tailscale serve` 挂在 loopback 前面。
- **口令：** `ARM_OPS_PASSWORD` 或 `/secrets/arm-ops-password.txt`。Session Cookie `arm_ops`（HttpOnly, SameSite=Lax）。
- **115 QR：** 本面板拥有扫码写 `/secrets/115-cookies.txt`（0600）的路径；JSON **只回** `{ok, cookie_len}`，不回 Cookie 正文。设备默认 `harmony`，与 p115client apps 一致。缺 `p115client` 则扫码失败并保持关闭。
- **IMA：** 只显示 `{present, mtime, uid_len}`。**不做 IMA 扫码**——换票仍在 Mac 上走 `ima_phone_sync`，再把 `ima-pure.json` 放到 secrets。
- **同步摘要：** 解析最新 `$CACHE_ROOT/logs/ima-lab-sync-*.log`（每组 downloaded/skipped/failed、最后错误行已脱敏）；timer 用 `systemctl show` 看 IMA / CICC lab timer 的 active / next（best-effort）。可选 journal 片段。
- **实验室旋钮：** `GET/POST /api/settings`（POST 须 `confirm:true`）。JSON 在 `$CACHE_ROOT/ops-lab-settings.json`：`daily_sync_clock`（默认 03:00 Asia/Shanghai，两个 timer 一起响）、`ima_limit_per_group` / `cicc_limit`（默认 10，CLI 上限 20）、`ima_groups_parallel`（默认 true）、`puller_batch_size`（默认 40，另写 `ops-puller.env`）。宿主机 wrapper 样例：`arm-lab-ops/bin/{ima-lab-sync-all,cicc-lab-sync,apply-lab-sync-timers}.sh`。能调 `systemctl` 时尽量自动写 drop-in；否则 UI 给出宿主机命令。审计一行 `settings-save`，无 secrets。
- **failed 重入：** `POST /api/failed/requeue`（须登录 + `confirm:true`）。把 `$CACHE_ROOT/failed/` 下相对路径移回 `staging/`，去掉 `.retry.json`。审计写 `$CACHE_ROOT/logs/ops-audit.jsonl`（无 secrets）。
- **限量触发：** wrap `scripts/ima_arm_lab_sync.py` / `scripts/cicc_arm_lab_sync.py`。凭据走环境变量文件路径，**不把 secrets 放到命令行**。apply 须 `confirm:true`，`limit<=5`（默认 3）。IMA group 白名单：`legacy`、`7479082602225992`、`7476629605476515`、`7437050366161003`。CICC 缺 Cookie 文件返回明确 400；不绕过采集器配额/熔断。
- **水位：** 对照 `CACHE_WARN_GB=30` / `CACHE_FORCE_GB=35`（与 `lab_common` GC 旋钮一致）。
- **挂载：** phase 2 需要 `CACHE_ROOT` **rw**（requeue / audit）。host-network 容器 bind-mount `/opt/vpush-ima-lab/src`（ro）才能 exec 宿主机脚本（`VPUSH_SCRIPTS_ROOT=/opt/vpush-ima-lab/src/scripts`），并 bind-mount `/opt/vpush-ima-lab/venv`（ro）+ `VPUSH_PYTHON=/opt/vpush-ima-lab/venv/bin/python`（镜像 Python 缺 `app.*`）。凭据文件只在宿主机 `secrets/`，容器内 `/secrets`：`115-cookies.txt`、`cicc-cookies.txt`、`ima-pure.json`、`arm-ops-password.txt`（**不要提交**）。CICC Cookie 路径 `VPUSH_CICC_COOKIE_FILE=/secrets/cicc-cookies.txt`。
- **OpenList：** 看板上的 `/lab-hot` 链接来自 `OPENLIST_PUBLIC_URL`（只读浏览热缓存，不暴露 115）。实验室可钉 Tailscale IPv4（不要写进仓库）。
- **日跑 timer（宿主机 systemd，不是生产 compose）：** 样本 IMA `vpush-ima-lab-sync.timer` 10:30 / CICC `vpush-cicc-lab-sync.timer` 11:00 Asia/Shanghai。wrapper 读 `$CACHE_ROOT/ops-lab-settings.json` 的 LIMIT。**IMA 与 CICC 都默认 `DRY_RUN=1`（`--dry-run`）；unit 里显式 `DRY_RUN=0` 才 apply。** CICC 日志 `$CACHE_ROOT/logs/cicc-lab-sync-*.log`。面板保存时钟后可用 `bin/apply-lab-sync-timers.sh` 把两个 timer 改成同一时刻。样本见 `arm-lab-ops/systemd/`。

本地跑法、合入 compose 与 recreate 步骤见 [arm-lab-ops/README.md](../arm-lab-ops/README.md)。 snippet 见 [arm-lab-ops/docker-compose.snippet.yml](../arm-lab-ops/docker-compose.snippet.yml)。

## 12. Handoff

- [2026-09-19 交接：ARM 中间层 + 115 Lab + Ops 面板](handoff/2026-09-19-ARM-lab-middleware-ops.md)
