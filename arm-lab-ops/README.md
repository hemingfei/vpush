# ARM lab ops panel（phase 2）

Oracle-SJ-ARM 中间层的薄运维面板：**看缓存 / puller / 同步摘要 / 失败队列**，给 **115 扫码写 Cookie**，以及 **确认后的限量 IMA/CICC 触发** 与 **failed → staging 重入**。

不是阅读台，不是生产 vpush 后台。**没有** IMA 扫码（IMA 仍走 Mac `ima_phone_sync`）。**不要**在生产 compose 里启用本服务或打开 `VPUSH_ARM_MIDDLEWARE`。

Oracle-SJ-ARM 在 Tailscale 上。访问顺序：

1. **优先：** 绑 Tailscale IPv4（`tailscale0` / `tailscale ip -4`）端口 **8055**。口令仍要。同 tailnet 打开 `http://<tailscale-ipv4>:8055`。
2. **备选：** `127.0.0.1:8055` + `ssh -L 8055:127.0.0.1:8055 oracle-sj-arm`。
3. **不要**在公网 NIC 上发布 `0.0.0.0:8055`。

uvicorn 只能绑 IP，不能绑网卡名。设 `ARM_OPS_BIND=tailscale`（或 `tailscale0`）时，启动会跑 `tailscale ip -4`，不行再读 `tailscale0`。解析失败则退回 `127.0.0.1` 并打警告。也可把 `ARM_OPS_BIND` 写成已经查到的 IPv4。

```bash
# ARM 上查地址后绑它（host 网络 / 直接跑进程）
export ARM_OPS_BIND="$(tailscale ip -4)"   # 或 ARM_OPS_BIND=tailscale
python ops_app.py

# 备选：loopback + 隧道
export ARM_OPS_BIND=127.0.0.1
python ops_app.py
ssh -L 8055:127.0.0.1:8055 oracle-sj-arm
```

没有 tailscale CLI、又想从 tailnet 进来时，可 loopback + `tailscale serve --bg 8055`。

## 本地跑

口令来自环境变量或文件（二选一，**不要提交**）：

```bash
cd arm-lab-ops
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
# 115 扫码需要：
pip install p115client

export ARM_OPS_PASSWORD='lab-only'
export CACHE_ROOT=/tmp/vpush-ima-cache
export P115_COOKIES_FILE=/tmp/secrets/115-cookies.txt
export IMA_PURE_SECRETS_FILE=/tmp/secrets/ima-pure.json
export VPUSH_CICC_COOKIE_FILE=/tmp/secrets/cicc-cookies.txt
export VPUSH_SCRIPTS_ROOT="$(pwd)/../scripts"
export OPENLIST_PUBLIC_URL=http://127.0.0.1:5244/lab-hot
mkdir -p "$CACHE_ROOT"/{staging,hot,failed,logs,manifest} /tmp/secrets
chmod 700 /tmp/secrets

python ops_app.py
# 或：uvicorn ops_app:app --host 127.0.0.1 --port 8055
```

也可以把口令写成 `/secrets/arm-ops-password.txt`（第一行，建议 `0600`）。变量名：`ARM_OPS_PASSWORD` / `ARM_OPS_PASSWORD_FILE`。

没有 `p115client` 时面板仍能看状态；点「开始扫码」会失败并保持关闭（不自己打 115 HTTP）。

## ARM 部署

仓库目录拷到 `/opt/vpush-ima-lab/arm-lab-ops/`，把 [`docker-compose.snippet.yml`](docker-compose.snippet.yml) 并进实验室 compose（**不要**写进生产 `docker-compose*.yml`）。

```bash
# 在 ARM 上，一次
install -d -m 700 /secrets
install -m 600 /dev/null /secrets/arm-ops-password.txt
# 手工写入口令，保持 0600
# 115 Cookie / IMA JSON 已有则复用：
#   /secrets/115-cookies.txt
#   /secrets/ima-pure.json

cd /opt/vpush-ima-lab
# 将 snippet 的 arm-lab-ops service 合入现有 compose 后：
docker compose build arm-lab-ops
docker compose up -d arm-lab-ops
```

Phase 2 要 **重入 failed** 以及写 `logs/ops-audit.jsonl`，所以 **`CACHE_ROOT` 需要 rw**（phase 1 常见 ro 不够）。也可以只把 `failed/` + `staging/` + `logs/` 以 rw 挂进去；推荐整棵 cache rw。

触发 IMA/CICC 脚本时，host-network 容器通过 bind-mount `/opt/vpush-ima-lab/src` 执行宿主机脚本。`VPUSH_SCRIPTS_ROOT` 默认 `/opt/vpush-ima-lab/src/scripts`（找不到再试仓库 `../scripts`）。容器自带 Python 若缺 `app.*` 依赖，设 `VPUSH_PYTHON` 指向宿主机 venv。

卷：

| 挂载 | 权限 | 用途 |
|---|---|---|
| `/data/vpush-ima-cache` | **rw（phase 2）** | staging / hot / failed / logs；requeue 要写 staging+failed+audit |
| `/opt/vpush-ima-lab/src` | ro | `scripts/ima_arm_lab_sync.py` / `cicc_arm_lab_sync.py` |
| `/secrets` | rw | 仅 QR 成功时改写 `115-cookies.txt`（0600） |
| `/root/cicc` | 可选 ro | CICC Cookie；缺则 CICC 触发返回明确 400 |
| `/var/run/docker.sock` | 可选 ro | 看 puller 容器；没有则走 health JSON / 日志 / systemd timer |

Puller 健康信息按顺序尝试：`PULLER_HEALTH_URL` → `PULLER_HEALTH_FILE`（默认 `$CACHE_ROOT/logs/health.json`）→ docker.sock / `docker ps` → `$CACHE_ROOT/logs/` 尾部 + `systemctl show vpush-ima-lab-sync.timer`（active / next run，best-effort）。

同步摘要读最新 `$CACHE_ROOT/logs/ima-lab-sync-*.log`，并尝试 `journalctl -u vpush-ima-lab-sync.service` 一小段（失败则忽略）。

## 页面与 API

| 路径 | 说明 |
|---|---|
| `GET /login` `POST /login` | 口令；Session Cookie `arm_ops`（HttpOnly, SameSite=Lax） |
| `GET /` | 看板（状态 + 确认后的动作） |
| `GET /api/status` | 同一份 JSON（须登录）；含 sync 摘要、failed 列表、水位、上次任务 |
| `POST /api/115/qr/start` | `device_type` 默认 `harmony`，与 p115client apps 一致 |
| `GET /api/115/qr/status?session_id=` | 轮询；成功只回 `{ok:true, cookie_len}` |
| `POST /api/failed/requeue` | `{confirm:true, paths:[rel…] 或 all:true}`；移回 staging，去掉 `.retry.json` |
| `POST /api/sync/ima/dry-run` | `--enable --dry-run --limit N --group G`（凭据走 `IMA_PURE_SECRETS_FILE`） |
| `POST /api/sync/ima/apply` | 须 `confirm:true`；`limit<=5`（默认 3）；group 白名单 |
| `POST /api/sync/cicc/dry-run` | 同上；缺 Cookie 文件明确 400；不绕过采集器配额/熔断 |
| `POST /api/sync/cicc/apply` | 须 `confirm:true`；`limit<=5` |

IMA group 白名单：`legacy`、`7479082602225992`、`7476629605476515`、`7437050366161003`。

状态里的敏感字段：

- IMA：`{present, mtime, uid_len}`，**从不**回 `refresh_token`
- 115 / CICC：`{present, mtime, length}`，**从不**回 Cookie 正文
- 日志 / health / job 输出会抹 `UID=` / `refresh_token=` 等形态
- 审计 `$CACHE_ROOT/logs/ops-audit.jsonl` 只记 action / count / ts，不含 secrets

扫码开始有轻量限流（每分钟 5 次）。Apply / requeue 须 `confirm: true`。脚本超时默认 120s（`ARM_OPS_SYNC_TIMEOUT`）。

缓存水位对照 `CACHE_WARN_GB`（默认 30）/ `CACHE_FORCE_GB`（默认 35），与 `lab_common` GC 旋钮一致。

## 安全

- 不要把 Cookie / token 打进日志或 JSON
- 不要把 secrets 放到脚本命令行；用已有环境变量 / 文件路径
- 实验室信任同站 Session，不做额外 CSRF token
- 口令文件与 Cookie 文件不要进 git
- 优先只绑 Tailscale IP；公网 NIC 上的 `0.0.0.0:8055` 等于把实验室口令挂到网上
