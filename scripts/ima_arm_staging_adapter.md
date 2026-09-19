# IMA → ARM staging 适配（草稿，默认关）

`scripts/ima_to_arm_staging.py` 不采集、不上传、不读 IMA Cookie / Refresh Token / `ima_phone_sync.env`。

## 为什么要 remap

`scripts/ima_phone_sync.py` 只把手机上的 Refresh Token 同步到 VPS，**不落 PDF**。凭据生效后，IMA puller / 文档中心仍按存储机契约写入：

```
/srv/vpush-ima/<group_id>__<hash>/<MMDD|unknown>/<title>__<token>.pdf
```

`MMDD` 没有年份。ARM staging / OpenList `/lab-hot` / 日后 `lab.sqlite` 要的是日期分片：

```
$VPUSH_ARM_STAGING_ROOT/local/ima/<group>/YYYY/MM/DD/<filename>.pdf
```

年份默认取文件 mtime（北京时间）；可用 `--year YYYY` 固定。`unknown` 日目录映射为 `YYYY/unknown`。

跳过 `local/`（中金/自建库）和点文件。不扫描 115、不写 OpenList。

## 开关

| 条件 | 行为 |
|---|---|
| 默认（无 flag、无环境变量） | 打印未启用并退出 0，不读源目录、不复制 |
| `--enable` 或 `VPUSH_ARM_MIDDLEWARE=1` | 规划 remap；**默认 `--dry-run`** 只列 `src → dest` |
| `--apply`（须同时启用） | 按规划复制（同盘优先硬链，否则 copy2） |

`--source` 默认 `/srv/vpush-ima`。`--staging-root` 默认 `$VPUSH_ARM_STAGING_ROOT` 或 `/data/vpush-ima-cache/staging`。

```bash
python3 scripts/ima_to_arm_staging.py
python3 scripts/ima_to_arm_staging.py --enable --dry-run --source /tmp/ima-fixture
```

未启用时不要对生产归档跑 `--apply`。本脚本不是采集器，不能代替 puller 上传 115。
