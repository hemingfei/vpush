# IMA → ARM lab sync（实验室限量采集，默认关）

`scripts/ima_arm_lab_sync.py` 是 Oracle-SJ-ARM 上的 **lab-only** 入口：从 IMA 列目录、限量下载 PDF 到 ARM staging。**默认什么都不做**。不改生产 compose，不碰 NFS，**不上传 115**。

115 对象仓仍由 **puller_loop** 从 staging 抽取。本脚本只负责把少量新 PDF 落到：

```
$VPUSH_ARM_STAGING_ROOT/local/ima/<group>/YYYY/MM/DD/<safe_filename>.pdf
```

路径由 `ImaDocumentStore.pdf_path` + `app/arm_middleware.py` 计算，与 live write 同一套布局。不要另造目录。

## 开关

| 条件 | 行为 |
|---|---|
| 默认（无 flag、无环境变量） | 打印未启用并退出 0；不读 secrets、不列目录、不下载 |
| `--enable` / `--arm-middleware` 或 `VPUSH_ARM_MIDDLEWARE=1` | 打开中间层写入；**默认 dry-run** 只列 `media_id` / title / dest |
| `--apply`（须同时启用） | `get_media` + `download`，落盘 staging |

启用后脚本会设置 `VPUSH_ARM_MIDDLEWARE=1`（以及可选 `VPUSH_ARM_STAGING_ROOT`），这样 `pdf_path` / `download` 走 staging，不走 `IMA_PULL_URL`。

**不要把 `VPUSH_ARM_MIDDLEWARE=1` 写进生产 `docker-compose*.yml`。**

```bash
# 默认：什么都不做
python3 scripts/ima_arm_lab_sync.py

# 离线看用法提示后，实验室 dry-run（需凭据才能列 IMA；测试用 fake client）
python3 scripts/ima_arm_lab_sync.py --enable --dry-run --group legacy --limit 3

# 限量下载 3 篇到 staging（仍不上传 115）
python3 scripts/ima_arm_lab_sync.py --arm-middleware --apply --group legacy --limit 3 \
  --secrets /root/ima-pure-secrets.json
```

`--group` 可以是 `legacy` 或知识库 id。`--day 0918` 只取该 IMA 日目录；不传则按现有 listing 启发式取**最新月文件夹**，再取其中最新 `MMDD`。`--limit` 默认 3，上限 20。

可选：`IMA_KB_ID`、`IMA_ROOT_FOLDER_ID`、`--staging-root` / `VPUSH_ARM_STAGING_ROOT`。

## 凭据

二选一（环境变量优先于文件）：

- `IMA_UID` + `IMA_REFRESH_TOKEN`
- `--secrets` 或 `IMA_PURE_SECRETS_FILE`，JSON 形状：`{"uid","refresh_token"}`

secrets 文件权限必须是 **0600**（组/其他可读会拒绝）。不要把凭据提交进仓库，不要把 token 打进日志或终端。脚本出错时会 redact `refresh_token` / `token` 等字段。ARM 实验室把文件放在宿主机 `secrets/ima-pure.json`（容器内 `/secrets/ima-pure.json`）。

```bash
install -m 600 /dev/null /root/ima-pure-secrets.json
# 手工写入 {"uid":"...","refresh_token":"..."} 后保持 0600
```

## 与其它入口的关系

| 入口 | 作用 |
|---|---|
| 本脚本 | ARM 实验室限量 **下载** → staging |
| `app/ima_documents.py` live write | 文档中心同步在中间层打开时写同一套 staging 路径 |
| `scripts/ima_to_arm_staging.py` | 只 remap 旧归档树，**不下载** |
| `scripts/ima_phone_sync.py` | 只换 Refresh Token，不落 PDF |
| **puller_loop** | staging → 115；本脚本不替代它 |

不写 OpenList / FUSE，不跑 NFS 兼容同步。完整契约见 [docs/arm-middleware.md](../docs/arm-middleware.md)。
