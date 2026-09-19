# ARM lab puller_loop（实验室 115 上传）

`scripts/puller_loop.py` 是 Oracle-SJ-ARM 上的 **lab-only** 上传器：从 staging 抽 PDF 上传 115，写 `lab.sqlite`，失败进 `failed/`。**不是**生产 compose 服务，**不要**在生产 `docker-compose*.yml` 里启用中间层或跑本脚本。

采集（中金 / IMA lab sync）只写 staging；115 只走本脚本。

## 部署到 ARM

仓库是权威副本。拷到宿主机（与现网 timer 同目录）：

```bash
install -m 755 scripts/puller_loop.py /opt/vpush-ima-lab/scripts/puller_loop.py
install -m 644 scripts/puller_retry.py /opt/vpush-ima-lab/scripts/puller_retry.py
# systemd timer 示例（ops 另做，不进生产 compose）：
# python3 /opt/vpush-ima-lab/scripts/puller_loop.py --apply --once
```

`puller_loop` 与 `puller_retry.py` 必须放在同一目录（或仓库根在 `PYTHONPATH`），以便 `call_with_retry` 可导入。

宿主机若已有较大的 `lab_common.py` / `manifest.py` / 115 SDK，**不必**整包进仓库。本脚本自带最小 `LabManifest`（`lab.sqlite`）。115 客户端按顺序解析：

1. 测试注入的 `uploader_factory`
2. `--uploader` / `VPUSH_115_UPLOAD_CMD`（模板含 `{src}` `{dest}`，stdout 可为 `{"upload_ok": true, "filesha1": "..."}`）
3. 可选 import `lab_upload` / `lab_common`（`VPUSH_ARM_LAB_PYTHONPATH` 或 `/opt/vpush-ima-lab/scripts/`）

没有客户端时 `--apply` 退出 2，不发起网络。默认 **dry-run** 只列 pending。

## 布局

```
/data/vpush-ima-cache/
  staging/local/cicc-research/YYYY/MM/DD/<file>.pdf
  staging/local/ima/<group>/YYYY/MM/DD/<file>.pdf
  hot/local/...          # 成功后硬链/拷贝，供 OpenList /lab-hot
  failed/local/...       # 重试耗尽
  manifest/lab.sqlite
```

115 对象键：`/vpush/` + `local/...`（与 [docs/arm-middleware.md](../docs/arm-middleware.md) §4.2 对齐）。

## 重试

每个文件走 `scripts/puller_retry.py` 的 `call_with_retry`（默认 3 次，退避 1s/2s）。上传函数必须返回 dict，且：

- `upload_ok` 为真才算成功
- `upload_ok` 假、或 `filesha1` 为空 / null，**抛错**，这样 `MultipartUploadAbort` / empty filesha1 会重试
- 不可重试错误（权限、401 等）立刻失败并移入 `failed/`

不读 IMA / 中金 Cookie，不写生产阅读台路径。

```bash
# 默认：只列，不上传
python3 scripts/puller_loop.py --staging-root /tmp/arm-staging

# ARM 一轮（须已配置 115 客户端）
python3 /opt/vpush-ima-lab/scripts/puller_loop.py --apply --once \
  --staging-root /data/vpush-ima-cache/staging
```

完整契约见 [docs/arm-middleware.md](../docs/arm-middleware.md)。
