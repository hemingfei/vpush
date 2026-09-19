# ARM → NFS 兼容同步（默认关）

`scripts/arm_nfs_sync.py` 在**存储恢复后**把 ARM hot（或 staging）日期分片映射成生产挂载用的旧 POSIX/NFS 布局。**默认什么都不做。** 不读 IMA / 115 Cookie，**不上传 115**。

开关 **独立于** `VPUSH_ARM_MIDDLEWARE`。不要在生产 compose 里设置 `VPUSH_ARM_NFS_SYNC=1` 或 `VPUSH_ARM_MIDDLEWARE=1`。

## 布局

源（`--source`，默认 `/data/vpush-ima-cache/hot`；也可指向 staging）：

```
<source>/local/cicc-research/YYYY/MM/DD/<sanitized>_<id>.pdf
<source>/local/cicc-research/YYYY/MM/DD/<sanitized>_<id>.json   # 品类 sidecar
<source>/local/ima/<group>/YYYY/MM/DD/<filename>.pdf
```

目标（`--dest` 或 `VPUSH_NFS_SYNC_DEST`，例如未来 NFS 挂载点）：

```
<dest>/local/cicc-research/<品类>/<MMDD>/<filename>.pdf
<dest>/local/cicc-research/.vpush-local-library.json
<dest>/local/cicc-research/.vpush-local-meta.jsonl
<dest>/<group_id>__<hash>/<MMDD>/<filename>.pdf    # IMA 命名组
<dest>/<MMDD>/<filename>.pdf                       # IMA legacy
```

CICC 品类优先读 PDF 旁 `.json` 的 `category`，否则按文件名 `_*_<id>.pdf` 查源侧 `.vpush-local-meta.jsonl`。没有品类则跳过该 PDF。IMA 命名组目录与 `ImaDocumentStore._group_namespace` 一致（`sha256(group_id)[:16]`）；ARM 文件夹若已是 `__<16hex>`（旧树 remap）则原样保留。

`--apply` 同盘优先硬链，失败则 `copy2`。已存在的目标不覆盖。

## 开关

| 条件 | 行为 |
|---|---|
| 默认（无 flag、无 `VPUSH_ARM_NFS_SYNC`） | 打印未启用并退出 0；不读源、不写盘 |
| `--enable` 或 `VPUSH_ARM_NFS_SYNC=1` | 规划映射；**默认 dry-run**；须同时给 `--dest` 或 `VPUSH_NFS_SYNC_DEST` |
| `--apply`（须同时启用） | 硬链/拷贝 |

`VPUSH_ARM_MIDDLEWARE=1` **不会**打开本脚本。

```bash
# 默认：什么都不做
python3 scripts/arm_nfs_sync.py

# dry-run（不写盘）
python3 scripts/arm_nfs_sync.py --enable --dry-run \
  --source /data/vpush-ima-cache/hot --dest /mnt/vpush-ima

# 真正落盘（仍不上传 115）
VPUSH_ARM_NFS_SYNC=1 VPUSH_NFS_SYNC_DEST=/mnt/vpush-ima \
  python3 scripts/arm_nfs_sync.py --apply
```

生产阅读台是否改挂这份导出，见 [docs/arm-middleware.md](../docs/arm-middleware.md) §10 决策记录：优先恢复原存储 NFS。
