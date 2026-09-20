# ARM lab cache_gc（水位清理）

`scripts/cache_gc.py` 是 Oracle-SJ-ARM `/opt/vpush-ima-lab/scripts/cache_gc.py` 的权威副本。`vpush-cache-gc.timer` 每 30 分钟跑一次。**不是**生产 compose 服务。

## 行为

| 水位 | 默认 | 行为 |
|---|---|---|
| warn | 30G | 只告警，写 `$CACHE_ROOT/manifest/gc-last.json` |
| force | 35G | 从最旧开始删 **hot/**，再删 **已上传的 staging/**，直到回到 warn |

保护：

- **未上传的 staging 不删。** 只认 `lab.sqlite` 里 `status` 为 `uploaded` / `hot` 的相对路径。清单读不到则整棵 staging 保护。`min-age-seconds`（默认 60）只防新文件，不够单独当门闩。
- `failed/` 默认不删；`--purge-failed` / `GC_PURGE_FAILED=1` 才纳入。
- 永不删 `manifest/`、`logs/`。
- `--allow-unuploaded-staging` / `GC_ALLOW_UNUPLOADED_STAGING=1` 是紧急阀，平时不要开。

## 部署

```bash
install -m 755 scripts/cache_gc.py /opt/vpush-ima-lab/scripts/cache_gc.py
# 样例 unit：arm-lab-ops/systemd/vpush-cache-gc.{service,timer}
# 宿主机已接线：CACHE_ROOT=/data/vpush-ima-cache，venv python，每 30 分钟
```

```bash
# 只看将删什么
CACHE_ROOT=/data/vpush-ima-cache python3 scripts/cache_gc.py --dry-run --warn-gb 30 --force-gb 35
```

同目录还要有 `lab_common.py`、`manifest.py`。不要改生产 compose。
