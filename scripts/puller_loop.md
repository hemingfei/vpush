# ARM lab puller_loop（实验室 115 上传）

`scripts/puller_loop.py` 是 Oracle-SJ-ARM `/opt/vpush-ima-lab/scripts/` 的**权威副本**（连同 `lab_common.py`、`manifest.py`）。从 `CACHE_ROOT/staging` 抽文件上传 115（`P115_LAB_ROOT`，默认 `/vpush`），写 `lab.sqlite`，失败进 `failed/`，成功拷到 `hot/`。**不是**生产 compose 服务，**不要**在生产 `docker-compose*.yml` 里启用中间层或跑本脚本。

采集（中金 / IMA lab sync）只写 staging；115 只走本脚本。

## 部署到 ARM

仓库与宿主机应对齐。拷到现网目录：

```bash
install -m 755 scripts/puller_loop.py /opt/vpush-ima-lab/scripts/puller_loop.py
install -m 644 scripts/puller_retry.py /opt/vpush-ima-lab/scripts/puller_retry.py
install -m 644 scripts/lab_common.py /opt/vpush-ima-lab/scripts/lab_common.py
install -m 644 scripts/manifest.py /opt/vpush-ima-lab/scripts/manifest.py
# systemd（ops 另做，不进生产 compose）：
# python3 /opt/vpush-ima-lab/scripts/puller_loop.py          # 循环 poll
# python3 /opt/vpush-ima-lab/scripts/puller_loop.py --once   # timer 一轮
```

四份脚本须在同一目录（宿主机 `sys.path` 是该目录），以便 `from puller_retry` / `lab_common` / `manifest` 导入。

## 环境（与现网一致）

| 变量 | 默认 | 含义 |
|---|---|---|
| `CACHE_ROOT` | `/cache` | `staging/` `hot/` `failed/` `manifest/` `logs/` |
| `P115_LAB_ROOT` | `/vpush` | 115 对象根 |
| `P115_COOKIES_FILE` | `/secrets/115-cookies.txt` | **路径**；脚本只 `read_text`，从不把 Cookie 打进日志 |
| `P115_DEVICE_TYPE` | `harmony` | p115client app |
| `PULLER_POLL_SECONDS` | `5` | 循环间隔 |
| `PULLER_STABLE_SECONDS` | `3` | 文件 mtime 稳定后才传 |
| `PULLER_BATCH_SIZE` | `20` | 每 tick 最多几个 |
| `PULLER_KEEP_HOT` | `true` | 成功后 `copy2` 到 `hot/` |
| `PULLER_BACKOFF_SECONDS` | `60,300,1800` | 失败后再试间隔 |

采集中间层默认写 `VPUSH_ARM_STAGING_ROOT`（`/data/vpush-ima-cache/staging`）。实验室须让 **puller 的 `CACHE_ROOT/staging` 与采集 staging 是同一棵树**（bind-mount 或改环境变量）。不要改生产 compose。

Cookie 文件不进仓库。`lab_common.load_cookies` 只从上述路径读；`redact` / `safe_exc` 会抹掉 `UID=` / `refresh_token=` 等形态。

## 上传与重试

每个文件：`client.upload_file` → 若 `lab_common.upload_ok(result)` 为假则 **raise**（`RuntimeError` 带 errno/body）→ `call_with_retry`（`scripts/puller_retry.py`，默认 3 次，退避 1s/2s）。这样 `MultipartUploadAbort` / empty `filesha1` 会重试；耗尽后 `on_fail` 移入 `failed/` 并写 `.retry.json`。Cookie 类错误会重建 client 再试一轮。

不实现第二套 puller，不直写 OpenList / NFS。

```bash
# ARM 一轮（须 CACHE_ROOT + /secrets/115-cookies.txt + p115client）
python3 /opt/vpush-ima-lab/scripts/puller_loop.py --once
```

完整契约见 [docs/arm-middleware.md](../docs/arm-middleware.md)。
