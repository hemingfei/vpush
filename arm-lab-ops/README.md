# ARM lab ops panel（phase 1）

Oracle-SJ-ARM 中间层的薄运维面板：**看缓存 / puller / 凭据是否在场，给 115 扫码写 Cookie**。

不是阅读台，不是生产 vpush 后台。Phase 1 **没有**破坏性 apply 按钮，也 **没有** IMA 扫码（IMA 仍走 Mac `ima_phone_sync`）。

默认只绑 **`127.0.0.1:8055`**。从笔记本进去：

```bash
ssh -L 8055:127.0.0.1:8055 oracle-sj-arm
# 浏览器打开 http://127.0.0.1:8055
```

**不要**把服务默认改成 `0.0.0.0`。compose 示例用 host 网络 + loopback；若改端口映射，host 侧仍须 `127.0.0.1:8055`。

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
export OPENLIST_PUBLIC_URL=http://127.0.0.1:5244/lab-hot
mkdir -p "$CACHE_ROOT"/{staging,hot,failed,logs} /tmp/secrets
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

卷：

| 挂载 | 权限 | 用途 |
|---|---|---|
| `/data/vpush-ima-cache` | ro | staging / hot / failed / logs |
| `/secrets` | rw | 仅 QR 成功时改写 `115-cookies.txt`（0600） |
| `/var/run/docker.sock` | 可选 ro | 看 puller 容器；没有则走 health JSON / 日志 / systemd timer |

Puller 健康信息按顺序尝试：`PULLER_HEALTH_URL` → `PULLER_HEALTH_FILE`（默认 `$CACHE_ROOT/logs/health.json`，可接现有 `healthcheck.py` 输出）→ docker.sock / `docker ps` → `$CACHE_ROOT/logs/` 尾部 + `systemctl is-active vpush-ima-lab-sync.timer`。

## 页面与 API

| 路径 | 说明 |
|---|---|
| `GET /login` `POST /login` | 口令；Session Cookie `arm_ops`（HttpOnly, SameSite=Lax） |
| `GET /` | 只读看板 |
| `GET /api/status` | 同一份 JSON（须登录） |
| `POST /api/115/qr/start` | `device_type` 默认 `harmony`，与 p115client apps 一致 |
| `GET /api/115/qr/status?session_id=` | 轮询；成功只回 `{ok:true, cookie_len}` |

状态里的敏感字段：

- IMA：`{present, mtime, uid_len}`，**从不**回 `refresh_token`
- 115：`{present, mtime, length}`，**从不**回 Cookie 正文
- 日志 / health JSON 会抹 `UID=` / `refresh_token=` 等形态

扫码开始有轻量限流（每分钟 5 次）。Phase 1 没有 dry-run / apply。

## 安全

- 不要把 Cookie / token 打进日志
- 实验室信任同站 Session，不做额外 CSRF token
- 口令文件与 Cookie 文件不要进 git
- 绑定保持 loopback；公网暴露本面板等于把实验室口令挂到网上
