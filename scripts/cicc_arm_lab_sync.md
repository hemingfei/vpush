# CICC → ARM lab sync（实验室限量采集，默认关）

`scripts/cicc_arm_lab_sync.py` 是 Oracle-SJ-ARM 上的 **lab-only** 入口：从中金点睛列目录、限量下载 PDF 到 ARM staging。**默认什么都不做**。不改生产 compose，不碰 NFS，**不上传 115**。

115 对象仓仍由 **puller_loop** 从 staging 抽取。本脚本只负责把少量新 PDF 落到：

```
$VPUSH_ARM_STAGING_ROOT/local/cicc-research/YYYY/MM/DD/<sanitized>_<id>.pdf
$VPUSH_ARM_STAGING_ROOT/local/cicc-research/YYYY/MM/DD/<sanitized>_<id>.json
```

路径由 `scripts/cicc_report_collector.py` 的 `target_path(..., middleware=True)` / `write_arm_item_sidecar` 计算，与采集器中间层同一套布局。不要另造目录。

## 开关

| 条件 | 行为 |
|---|---|
| 默认（无 flag、无环境变量） | 打印未启用并退出 0；不读 Cookie、不列目录、不下载 |
| `--enable` / `--arm-middleware` 或 `VPUSH_ARM_MIDDLEWARE=1` | 打开中间层写入；**默认 dry-run** 只列 id / title / dest |
| `--apply`（须同时启用） | 取 PDF 落盘 staging |

启用后脚本会设置 `VPUSH_ARM_MIDDLEWARE=1`（以及可选 `VPUSH_ARM_STAGING_ROOT`），跑完恢复，避免泄漏到别的进程/测试。

**不要把 `VPUSH_ARM_MIDDLEWARE=1` 写进生产 `docker-compose*.yml`。**

```bash
# 默认：什么都不做
python3 scripts/cicc_arm_lab_sync.py

# dry-run（须 Cookie 才能列中金；测试用 fake session）
python3 scripts/cicc_arm_lab_sync.py --enable --dry-run --limit 3 --days 7

# 限量下载 3 篇到 staging（仍不上传 115）
python3 scripts/cicc_arm_lab_sync.py --arm-middleware --apply --limit 3 --days 7 \
  --cookie-file /root/cicc/cookies.txt
```

`--limit` 默认 3，上限 20。`--days` 默认 7（含今天，与采集器窗口一致）。`--categories` / `--keywords` 与采集器相同。

## Cookie

与采集器同一套约定（不要把 Cookie 写进仓库，不要打进日志）：

- `--cookie-file` 或 `VPUSH_CICC_COOKIE_FILE`
- 脚本默认 `/root/cicc/cookies.txt`（存储机采集器约定，一行原始 Cookie 头）
- **ARM 实验室 ops / timer** 用宿主机 `secrets/cicc-cookies.txt`（容器内 `/secrets/cicc-cookies.txt`）。口令与 Cookie 只放 `secrets/`，永远不要提交。

出错文案会 redact `Cookie:` 行。脚本从不 print Cookie 值。

## 配额 / 熔断

沿用 `cicc_report_collector.Session`：

- 默认 `--endpoint viewer`（`fetchPdf`，不计月度 300 篇配额）
- `--endpoint download` 走配额接口；命中 `400013` 时采集器 `write_paused("quota", ...)` 并退出
- 登录失效 `40010` / HTTP 401/412 同样 `write_paused("auth", ...)` 并退出

本脚本**不**吞掉这些 `SystemExit`，也**不**增加任何配额旁路。

## 与其它入口的关系

| 入口 | 作用 |
|---|---|
| 本脚本 | ARM 实验室限量 **下载** → staging |
| `scripts/cicc_report_collector.py --arm-middleware` | 同一套 staging 路径的全量/增量采集器 |
| **puller_loop** | staging → 115；本脚本不替代它 |

不写 OpenList / FUSE，不跑 NFS 兼容同步。完整契约见 [docs/arm-middleware.md](../docs/arm-middleware.md)。
