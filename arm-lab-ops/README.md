# ARM lab ops panel（phase 3）

Oracle-SJ-ARM 中间层的薄运维面板：**看缓存 / puller / 同步摘要 / 失败队列**，给 **115 扫码写 Cookie**，**确认后的限量 IMA/CICC 触发** 与 **failed → staging 重入**，以及 **实验室同步时钟 / 并发旋钮**。

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
# ARM compose sets this to the host venv; local can omit (uses sys.executable).
# export VPUSH_PYTHON=/opt/vpush-ima-lab/venv/bin/python
export OPENLIST_PUBLIC_URL=http://127.0.0.1:5244/lab-hot
mkdir -p "$CACHE_ROOT"/{staging,hot,failed,logs,manifest} /tmp/secrets
chmod 700 /tmp/secrets

python ops_app.py
# 或：uvicorn ops_app:app --host 127.0.0.1 --port 8055
```

也可以把口令写成 `/secrets/arm-ops-password.txt`（第一行，建议 `0600`）。变量名：`ARM_OPS_PASSWORD` / `ARM_OPS_PASSWORD_FILE`。

没有 `p115client` 时面板仍能看状态；点「开始扫码」会失败并保持关闭（不自己打 115 HTTP）。

## ARM 部署（宿主机 systemd）

puller 与 ops 走宿主机 systemd，和 `vpush-ima-pull` / cache-gc / 日同步 timer 同一套。实验室 compose **只留 OpenList**。**不要**写进生产 `docker-compose*.yml`，也不要再启 `arm-lab-ops` / `vpush-ima-lab-puller-1` 容器。

Cookie / token / 口令文件只放宿主机 **`/opt/vpush-ima-lab/secrets/`**，**永远不要提交**。建议 `0700` 目录、`0600` 文件：

| 宿主机路径 | 用途 |
|---|---|
| `/opt/vpush-ima-lab/secrets/arm-ops-password.txt` | 面板口令 |
| `/opt/vpush-ima-lab/secrets/115-cookies.txt` | 115 QR / puller |
| `/opt/vpush-ima-lab/secrets/cicc-cookies.txt` | CICC lab sync |
| `/opt/vpush-ima-lab/secrets/ima-pure.json` | IMA lab sync `{"uid","refresh_token"}` |

```bash
# 在 ARM 上，一次
install -d -m 700 /opt/vpush-ima-lab/secrets
install -m 600 /dev/null /opt/vpush-ima-lab/secrets/arm-ops-password.txt
# 手工写入口令，保持 0600
# Cookie / IMA JSON 已有则复用到 secrets/，不要拷进 git：
#   /opt/vpush-ima-lab/secrets/115-cookies.txt
#   /opt/vpush-ima-lab/secrets/cicc-cookies.txt
#   /opt/vpush-ima-lab/secrets/ima-pure.json

# 实验室 .env（不要提交）可钉 Tailscale IPv4：
#   ARM_OPS_BIND=<tailscale-ipv4>
#   OPENLIST_PUBLIC_URL=http://<tailscale-ipv4>:5244/lab-hot

# 面板依赖进宿主机 venv（不再用 ops 镜像）
/opt/vpush-ima-lab/venv/bin/pip install -r /opt/vpush-ima-lab/src/arm-lab-ops/requirements.txt
/opt/vpush-ima-lab/venv/bin/pip install p115client

install -m 644 arm-lab-ops/systemd/vpush-arm-lab-ops.service \
  arm-lab-ops/systemd/vpush-ima-lab-puller.service /etc/systemd/system/
# puller 四份脚本须在同一目录，见 scripts/puller_loop.md
systemctl daemon-reload
# 若 cache / secrets 曾是 root 容器在写：
#   chown -R ubuntu:ubuntu /data/vpush-ima-cache
#   chown ubuntu:ubuntu /opt/vpush-ima-lab/secrets/*
systemctl enable --now vpush-ima-lab-puller.service vpush-arm-lab-ops.service

# 停掉实验室 compose 里的两份容器；OpenList 留下
cd /opt/vpush-ima-lab
docker stop arm-lab-ops vpush-ima-lab-puller-1
docker rm arm-lab-ops vpush-ima-lab-puller-1
```

`git pull` 后重启 unit（puller 若仍用 `/opt/vpush-ima-lab/scripts/` 副本，先按 `scripts/puller_loop.md` 再 install 一遍）：

```bash
cd /opt/vpush-ima-lab/src
git pull
systemctl restart vpush-arm-lab-ops.service
systemctl restart vpush-ima-lab-puller.service
```

Phase 2 要 **重入 failed** 以及写 `logs/ops-audit.jsonl`，所以进程对 **`CACHE_ROOT` 需要 rw**。unit 直接读宿主机路径，不再 bind-mount，也不再挂 `docker.sock`。

`VPUSH_SCRIPTS_ROOT` 默认 `/opt/vpush-ima-lab/src/scripts`（找不到再试仓库 `../scripts`）。**必须**设 `VPUSH_PYTHON=/opt/vpush-ima-lab/venv/bin/python`——样本 unit 已写死。

Puller 健康信息按顺序尝试：`PULLER_HEALTH_URL` → `PULLER_HEALTH_FILE`（默认 `$CACHE_ROOT/logs/health.json`）→ `systemctl show vpush-ima-lab-puller.service` → `$CACHE_ROOT/logs/` 尾部 + IMA / CICC timer（active / next，best-effort）。只有显式设了 `PULLER_CONTAINER_NAME` 才再去看 docker。

同步摘要读最新 `$CACHE_ROOT/logs/ima-lab-sync-*.log`，并尝试 `journalctl -u vpush-ima-lab-sync.service` 一小段（失败则忽略）。CICC 日跑日志在 `$CACHE_ROOT/logs/cicc-lab-sync-*.log`。

## 宿主机日跑 timer（实验室，不是生产 compose）

IMA 已在 ARM 上：`vpush-ima-lab-sync.timer` **10:30 Asia/Shanghai** → 宿主机 `bin/ima-lab-sync-all.sh`。CICC 按同样风格安装，**11:00 Asia/Shanghai**。样本 unit / wrapper 在 [`systemd/`](systemd/) 与 [`bin/cicc-lab-sync.sh`](bin/cicc-lab-sync.sh)。看板上保存时钟后，`apply-lab-sync-timers.sh` 会用 drop-in 把两个 timer 改成同一时刻（默认旋钮 03:00）。wrapper 在 `$CACHE_ROOT/ops-lab-settings.json` 存在时读 LIMIT / 并行。

| 单元 | 时刻 | 包装脚本 | 行为 |
|---|---|---|---|
| `vpush-ima-lab-sync.{service,timer}` | 10:30 Asia/Shanghai | `bin/ima-lab-sync-all.sh`（宿主机已有） | 调 `scripts/ima_arm_lab_sync.py --enable`（4 个白名单 group）；**默认 `DRY_RUN=1`（走 `--dry-run`）**；`DRY_RUN=0` 才 `--apply`；日志 `$CACHE_ROOT/logs/ima-lab-sync-*.log` |
| `vpush-cicc-lab-sync.{service,timer}` | 11:00 Asia/Shanghai | `bin/cicc-lab-sync.sh` | 调 `scripts/cicc_arm_lab_sync.py --enable --limit N`；**默认 `DRY_RUN=1`（走 `--dry-run`）**；Cookie `VPUSH_CICC_COOKIE_FILE`（宿主机 `secrets/cicc-cookies.txt`）；日志 `$CACHE_ROOT/logs/cicc-lab-sync-*.log` |

安装 CICC 样本（路径按现网 `/opt/vpush-ima-lab`）：

```bash
install -d -m 755 /opt/vpush-ima-lab/bin
install -m 755 arm-lab-ops/bin/cicc-lab-sync.sh /opt/vpush-ima-lab/bin/cicc-lab-sync.sh
install -m 644 arm-lab-ops/systemd/vpush-cicc-lab-sync.service \
  arm-lab-ops/systemd/vpush-cicc-lab-sync.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vpush-cicc-lab-sync.timer
# IMA 与 CICC 样本 unit 都默认 DRY_RUN=1；确认 dry-run 后再把 unit 里 DRY_RUN 改成 0
```

不要把 Cookie 写进 unit 或仓库。**IMA 与 CICC wrapper 都默认 `DRY_RUN=1` → `--dry-run`；只有把 `DRY_RUN=0` 写进 unit 才真正 `--apply`。** 日跑要真正落盘时必须显式改 unit。

## 页面与 API

| 路径 | 说明 |
|---|---|
| `GET /login` `POST /login` | 口令；Session Cookie `arm_ops`（HttpOnly, SameSite=Lax） |
| `GET /` | 看板（状态 + 确认后的动作 + 实验室旋钮） |
| `GET /api/status` | 同一份 JSON（须登录）；含 sync 摘要、failed 列表、水位、上次任务、IMA/CICC timer next |
| `GET /api/settings` | 实验室旋钮 + 只读下次 timer fire（须登录） |
| `POST /api/settings` | `{confirm:true, daily_sync_clock, ima_limit_per_group, cicc_limit, ima_groups_parallel, puller_batch_size}` |
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

扫码开始有轻量限流（每分钟 5 次）。Apply / requeue / **保存旋钮** 须 `confirm: true`。脚本超时默认 120s（`ARM_OPS_SYNC_TIMEOUT`）。

## 实验室旋钮（phase 3）

看板「实验室旋钮」写入 **`$CACHE_ROOT/ops-lab-settings.json`**（不是 secrets；默认 `0664`）。缺省与现网一致：

| 字段 | 默认 | 说明 |
|---|---|---|
| `daily_sync_clock` | `03:00` | Asia/Shanghai；IMA + CICC 两个 timer 同一时刻 |
| `ima_limit_per_group` | `10` | CLI 上限 20 |
| `cicc_limit` | `10` | CLI 上限 20 |
| `ima_groups_parallel` | `true` | 宿主机 wrapper 用后台 job 跑各组 |
| `puller_batch_size` | `40` | 同时写 `$CACHE_ROOT/ops-puller.env` 的 `PULLER_BATCH_SIZE=` |

`scripts/puller_loop.py` 每个 tick 读 settings JSON（有则覆盖环境变量）。宿主机 puller unit 也可：

```ini
EnvironmentFile=-/data/vpush-ima-cache/ops-puller.env
```

把 [`bin/ima-lab-sync-all.sh`](bin/ima-lab-sync-all.sh)、[`bin/cicc-lab-sync.sh`](bin/cicc-lab-sync.sh)、[`bin/apply-lab-sync-timers.sh`](bin/apply-lab-sync-timers.sh) 装到 `/opt/vpush-ima-lab/bin/`。timer / 日同步 wrapper 应读这份 JSON 的 LIMIT，而不是写死 10。

保存时钟时，面板会尽量自动改写两个 systemd timer（与 status 一样先探测 `systemctl`）：

1. 若 `ARM_OPS_TIMER_HELPER`（或 `/opt/vpush-ima-lab/bin/apply-lab-sync-timers.sh`）可执行，则调用它（drop-in + `daemon-reload` + restart）。
2. 否则尝试写 `/etc/systemd/system/<unit>.d/ops-schedule.conf`（先清空再设 `OnCalendar=*-*-* HH:MM:00 Asia/Shanghai`）。
3. Docker / 无 systemd 时只存 JSON，并在 UI 显示 **宿主机 apply** 命令：

```bash
sudo /opt/vpush-ima-lab/bin/apply-lab-sync-timers.sh 03:00 Asia/Shanghai
```

Timer 名默认 `vpush-ima-lab-sync.timer` / `vpush-cicc-lab-sync.timer`（`ARM_OPS_TIMER_UNIT` / `ARM_OPS_CICC_TIMER_UNIT`）。看板上的 next fire 只读，来自 `systemctl show`。

**不要**把口令 / Cookie / refresh_token 写进 settings JSON 或审计。审计仍是 `$CACHE_ROOT/logs/ops-audit.jsonl` 一行 `settings-save`。

缓存水位对照 `CACHE_WARN_GB`（默认 30）/ `CACHE_FORCE_GB`（默认 35），与 `lab_common` GC 旋钮一致。

## 安全

- 不要把 Cookie / token 打进日志或 JSON
- 不要把 secrets 放到脚本命令行；用已有环境变量 / 文件路径
- 实验室信任同站 Session，不做额外 CSRF token
- 口令文件与 Cookie 文件不要进 git
- 优先只绑 Tailscale IP；公网 NIC 上的 `0.0.0.0:8055` 等于把实验室口令挂到网上
