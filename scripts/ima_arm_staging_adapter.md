# IMA → ARM staging

两条路径，都默认关。都不读 IMA Cookie / Refresh Token / `ima_phone_sync.env`，都不写 NFS / 115 / OpenList。

| 路径 | 作用 | 入口 |
|---|---|---|
| **Live write** | 新 PDF 下载直接落入 staging 日期分片 | `app/ima_documents.py`（`ImaDocumentStore.pdf_path` / `ImaPureClient.download`） |
| **Remap** | 把已有 `/srv/vpush-ima` 归档树拷进 staging | `scripts/ima_to_arm_staging.py`（本脚本，不采集） |

## Live write（新下载）

开关与中金相同：`--arm-middleware` / `VPUSH_ARM_MIDDLEWARE=1`。打开后，文档中心下载目的地改为：

```
$VPUSH_ARM_STAGING_ROOT/local/ima/<group_id>/YYYY/MM/DD/<safe_filename>.pdf
```

- staging 根默认 `/data/vpush-ima-cache/staging`，可用 `VPUSH_ARM_STAGING_ROOT` 覆盖
- 日期优先 IMA 日目录 MMDD + 媒体创建年（北京时间）；没有日目录则用北京时间 mtime/now
- 未设开关时行为不变（仍写 `IMA_ARCHIVE_ROOT` 的 `<group>__<hash>/<MMDD>/` 或 legacy `<MMDD>/`）
- 打开后不走 `IMA_PULL_URL`（那是存储机 NFS puller）

离线看路径（不下载、不读凭据）：

```bash
python3 -m app.arm_middleware --arm-middleware --print-dest --group legacy --day 0918 --name demo.pdf
VPUSH_ARM_MIDDLEWARE=1 python3 -m app.arm_middleware --print-dest --group legacy --day 0918 --name demo.pdf
```

实验室限量跑：设 `VPUSH_ARM_MIDDLEWARE=1`（及可选 `VPUSH_ARM_STAGING_ROOT`）后走现有 IMA 同步即可。不要在生产 compose 里打开。

## Remap（旧归档）

`ima_phone_sync` 只把手机上的 Refresh Token 同步到 VPS，**不落 PDF**。凭据生效后，未开 live write 时 puller / 文档中心仍按存储机契约写入：

```
/srv/vpush-ima/<group_id>__<hash>/<MMDD|unknown>/<title>__<token>.pdf
```

`MMDD` 没有年份。本脚本把已有树 remap 到日期分片：

```
$VPUSH_ARM_STAGING_ROOT/local/ima/<group>/YYYY/MM/DD/<filename>.pdf
```

年份默认取文件 mtime（北京时间）；可用 `--year YYYY` 固定。`unknown` 日目录映射为 `YYYY/unknown`。

跳过 `local/`（中金/自建库）和点文件。不扫描 115、不写 OpenList。

### 开关

| 条件 | 行为 |
|---|---|
| 默认（无 flag、无环境变量） | 打印未启用并退出 0，不读源目录、不复制 |
| `--enable` / `--arm-middleware` 或 `VPUSH_ARM_MIDDLEWARE=1` | 规划 remap；**默认 `--dry-run`** 只列 `src → dest` |
| `--apply`（须同时启用） | 按规划复制（同盘优先硬链，否则 copy2） |

`--source` 默认 `/srv/vpush-ima`。`--staging-root` 默认 `$VPUSH_ARM_STAGING_ROOT` 或 `/data/vpush-ima-cache/staging`。

```bash
python3 scripts/ima_to_arm_staging.py
python3 scripts/ima_to_arm_staging.py --enable --dry-run --source /tmp/ima-fixture
python3 scripts/ima_to_arm_staging.py --arm-middleware --dry-run --source /tmp/ima-fixture
```

未启用时不要对生产归档跑 `--apply`。本脚本不是采集器，不能代替 live write，也不能代替 puller 上传 115。
