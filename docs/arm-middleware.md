# V Push：ARM 中间层（NFS + 115 兼容）

日期：2026-09-19 · 状态：仓库已落地适配（**默认关**）· 现网仍只读浏览、不采集  
主机：Oracle-SJ-ARM（约 45G）· OpenList 实验根 `/lab-hot`（**不暴露 115**）

采集默认仍写存储机 POSIX/NFS 布局。打开中间层后，采集器只写 ARM staging；上传只走 puller；存储恢复后再做 NFS 兼容同步。生产 compose 不打开本开关。

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

### 4.3 旧 NFS 兼容布局（存储恢复后由同步器生成）

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
| puller 容器 | staging→115；清单；失败重试 | ARM 侧已上线 |
| OpenList | 只读浏览 hot | `/lab-hot` 日期入口；115 disabled |
| cicc 适配 | 写 staging 日期分片，默认关 | `scripts/cicc_report_collector.py` |
| ima 适配 | 同步输出 remap 进 staging，默认关 | `scripts/ima_to_arm_staging.py`（草稿） |
| nfs-sync（规划） | hot/权威 → 旧 NFS 布局 | 存储恢复后 |

## 6. 开关

- `VPUSH_ARM_MIDDLEWARE=0`（默认，或不设）：采集器保持原存储机行为
- `VPUSH_ARM_MIDDLEWARE=1` 或 `--arm-middleware`：输出改写到 ARM staging 日期布局；**不直接写 NFS/115**
- `VPUSH_ARM_STAGING_ROOT`：staging 根，默认 `/data/vpush-ima-cache/staging`
- `VPUSH_CICC_COOKIE_FILE`：覆盖中金 Cookie 文件路径（不要把 Cookie 写进仓库）
- 上传仅由 puller 负责；禁止采集器直写 OpenList/FUSE

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

离线自检（不访问中金）：`python3 cicc_report_collector.py --self-test`

手册见 [cicc-report-collector.md](cicc-report-collector.md)。

## 8. IMA 适配草稿（默认关）

`ima_phone_sync` 只换 Refresh Token，不落 PDF。凭据生效后 puller/采集写入的仍是存储机 `<group>/<MMDD>/`，进 ARM 前要 remap 到 `YYYY/MM/DD` 分片。

```bash
# 默认：什么都不做
python3 scripts/ima_to_arm_staging.py

# 只列将要复制的路径（不写盘、不读 IMA 凭据）
python3 scripts/ima_to_arm_staging.py --enable --dry-run --source /path/to/ima-archive
```

说明见 [scripts/ima_arm_staging_adapter.md](../scripts/ima_arm_staging_adapter.md)。

## 9. 成功标准（启用采集后才验收）

- 增量落入 staging → sqlite → 115 抽查可读
- 存储恢复后：旧 NFS 布局可被生产挂载读到同批文件
- ARM 缓存水位：≥30G 告警 / ≥35G 清理 staging+hot
- Cookie/配额熔断与现网一致，不绕过中金月度配额

## 10. 实施顺序

1. 本文档 + 仓库适配（本 PR；默认关）
2. 中金 → staging 适配（默认关）
3. IMA 输出适配草稿（默认关）
4. 存储恢复后：NFS 兼容同步器
5. 评估生产是否改挂 ARM 导出的 NFS，或继续挂原存储
