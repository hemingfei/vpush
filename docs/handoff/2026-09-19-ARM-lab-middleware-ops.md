# 2026-09-19 交接：ARM 中间层 + 115 Lab + Ops 面板（供 Agent Code Review）

- **作者语境**：VPUSH运营（Kale / icekale）当日实验工作
- **仓库**：https://github.com/icekale/vpush
- **主分支 tip（当日收工）**：`b05df4d33e27e0fe05ec7276b2079bcc3f64b77d`（含 PR #18）
- **范围**：Lab-only。**生产 vpush.net 未切中间层**；存储 NFS 仍暂停（ima-storage 503）。
- **时区**：Asia/Shanghai（下文时间均为上海时间除非标注 UTC）

---

## 1. 一句话目标

在 Oracle-SJ-ARM 上跑通 **采集 → ARM staging → puller → 115 权威存储 → lab-hot/OpenList 可读**，并做薄运维面板；代码默认关闭，不改变生产/存储机行为，等存储恢复后再谈生产接入。

---

## 2. 架构（Lab）

```
IMA / 中金采集（default-off）
        │
        ▼
ARM staging  /data/vpush-ima-cache/staging/local/{ima|cicc-research}/YYYY/MM/DD/...
        │
        ▼
puller（Docker）──上传──► 115  /vpush/local/...
        │
        ├── hot copy ──► /data/vpush-ima-cache/hot/local/...  (mode 0664)
        └── OpenList  /lab-hot（本地 hot）+ 可选 /vpush（115）
```

- **中间层开关**：`VPUSH_ARM_MIDDLEWARE=1` 或 CLI `--enable` / `--arm-middleware`；**默认关**。
- **账本**：SQLite（puller manifest）；未上 Redis/Postgres。
- **NFS 兼容同步**：`scripts/arm_nfs_sync.py` 草稿，default-off；生产切流前不做。

### Lab 主机要点

| 项 | 值 |
|---|---|
| Host | Oracle-SJ-ARM（约 4C/24G） |
| Cache | `/data/vpush-ima-cache` |
| Lab compose | `/opt/vpush-ima-lab` |
| Repo checkout | `/opt/vpush-ima-lab/src` @ main |
| Ops 面板 | Tailscale `http://100.112.25.21:8055` |
| OpenList | `http://100.112.25.21:5244`（`/lab-hot`） |
| Secrets（host，chmod 600，勿进 git） | `secrets/115-cookies.txt`, `ima-pure.json`, `cicc-cookies.txt`, `arm-ops-password.txt` |
| 日定时 | IMA + 中金 **03:00** 并行；wrapper 读 `ops-lab-settings.json` |

---

## 3. 当日合并 PR（review 入口）

按依赖顺序阅读（全部已 merge 进 `main`）：

| PR | SHA（merge） | 标题 | Review 重点 |
|---:|---|---|---|
| [#10](https://github.com/icekale/vpush/pull/10) | `ab61dc54…` | ARM 中间层适配（默认关） | CICC collector 路径、sidecar、开关门闩 |
| [#11](https://github.com/icekale/vpush/pull/11) | `1bd54adc…` | IMA live → ARM staging | `app/arm_middleware.py`、`ima_documents` 写路径、跳过 IMA_PULL_URL |
| [#12](https://github.com/icekale/vpush/pull/12) | `685c8a58…` | IMA lab sync CLI | `scripts/ima_arm_lab_sync.py` limit/增量 |
| [#13](https://github.com/icekale/vpush/pull/13) | `63358ca2…` | NFS sync 草稿 + puller retry | `arm_nfs_sync.py`、`puller_retry.py` |
| [#14](https://github.com/icekale/vpush/pull/14) | `d8caf228…` | vendor puller_loop + CICC lab sync | `scripts/puller_loop.py`、`cicc_arm_lab_sync.py` |
| [#15](https://github.com/icekale/vpush/pull/15) | `48a01c99…` | Ops panel phase-1 | auth、status、115 QR → secrets |
| [#16](https://github.com/icekale/vpush/pull/16) | `41ea792e…` | Ops phase-2 | sync 摘要、failed requeue、confirm 触发 |
| [#17](https://github.com/icekale/vpush/pull/17) | `710d11dc…` | 回写 live compose mounts | venv/`VPUSH_PYTHON`、CICC cookie 路径、timer 文档 |
| [#18](https://github.com/icekale/vpush/pull/18) | `b05df4d3…` | 实验室旋钮 + hot 0664 | settings UI、`ops-lab-settings.json`、`to_hot` chmod |

**建议 diff 命令：**

```bash
git fetch origin
git log --oneline ab61dc54^..b05df4d   # 当日主线
# 或按 PR：
gh pr diff 10 --repo icekale/vpush
# …
gh pr diff 18 --repo icekale/vpush
```

---

## 4. 关键路径清单（按模块）

### 4.1 中间层与采集适配

- `app/arm_middleware.py` — staging 根、IMA 日期分片、开关
- `app/ima_documents.py` — middleware on 时写 staging、跳过 puller URL
- `scripts/cicc_report_collector.py` — `--arm-middleware` / 环境变量、日期分片、sidecar
- `scripts/ima_to_arm_staging.py` — 离线适配
- `scripts/ima_arm_lab_sync.py` — Lab 限量 IMA sync（`--enable --apply --limit`，上限 20）
- `scripts/cicc_arm_lab_sync.py` — Lab 限量中金 sync（viewer 默认、不绕配额熔断）
- `scripts/arm_nfs_sync.py` — NFS 兼容（default-off）
- `docs/arm-middleware.md` /（历史）`docs/ARM中间层架构.md`

### 4.2 Puller / 115

- `scripts/puller_loop.py` — staging→115；`to_hot` 后 **0664** / 目录 **0775**；可读 `ops-lab-settings.json` 的 `puller_batch_size`
- `scripts/puller_retry.py` — multipart 可重试错误
- `scripts/lab_common.py` / `manifest.py`（若存在）— 缓存目录与 SQLite

### 4.3 Ops 面板（`arm-lab-ops/`）

- `ops_app.py` / `ops_auth.py` / `ops_status.py` / `ops_qr115.py` / `ops_actions.py`
- `ops_lab_knobs.py` / `ops_settings.py` — 实验室旋钮
- `templates/dashboard.html` — 含「实验室旋钮」、sync/失败队列/触发
- `bin/ima-lab-sync-all.sh` / `bin/cicc-lab-sync.sh` / `bin/apply-lab-sync-timers.sh`
- `docker-compose.snippet.yml` — **须** rw CACHE、src+venv ro、`VPUSH_PYTHON`、secrets、Tailscale bind
- `systemd/*` — timer 样例

### 4.4 测试

- `tests/test_arm_middleware.py`
- `tests/test_arm_lab_ops.py` / `test_arm_lab_ops_phase2.py` / `test_arm_lab_ops_settings.py`
- `tests/test_puller_loop.py`

当日收工前设置相关：**68 passed**（cloud agent 报告）；以 `pytest tests/test_arm_*.py tests/test_puller_loop.py` 复跑为准。

---

## 5. 安全与门闩（Review 必看）

1. **默认关闭**：无 `VPUSH_ARM_MIDDLEWARE` / `--enable` 不得写 ARM staging；生产 compose 未启用。
2. **确认门闩**：面板 apply / requeue / 改设置需 `confirm:true`；apply limit≤5（面板触发）；定时 wrapper limit 来自 settings（默认 10，硬顶 20）。
3. **密钥**：Cookie/token **永不**进 argv 明文日志、永不 commit；面板 redact；QR 只写 secrets 文件。
4. **中金配额**：不绕过 collector pause/quota；lab 默认 viewer 端点。
5. **Path traversal**：failed requeue 拒绝 `..` / 绝对路径。
6. **生产边界**：禁止把 lab compose/ops 挂到公网 NIC；仅 Tailscale bind。

---

## 6. 已做验收（勿重复当「未测」）

| 项 | 结果 |
|---|---|
| IMA/中金限量 apply → staging → puller → 115/hot | 通过（多次；含 group `7479082602225992` 与中金新 id） |
| V Push **模拟读** hot + `app.arm_middleware` 路径 | 通过（非生产挂载） |
| Ops phase-2 requeue / dry-run | 通过；IMA 干跑需 host venv（`VPUSH_PYTHON`） |
| hot 既有文件 chmod 0664 | 已在 ARM 执行；新文件靠 puller `to_hot` |
| 日定时 | 03:00 并行；settings 可改 |

**未做 / 明确非目标：**

- 生产开启 `VPUSH_ARM_MIDDLEWARE`
- vpush.net 从 115/OpenList 读知识库（仍依赖暂停中的 NFS）
- Redis / Postgres
- puller **多线程上传**（仍单线程 loop；仅 batch=40）
- 容器内 `systemctl` 探测 timer（常 FileNotFound；改时钟靠 host helper）

---

## 7. 建议 Review Checklist

请其他 agent **按项打勾并记风险**，优先找：默认关闭被破坏、密钥泄漏、路径穿越、配额绕过、生产误触。

- [ ] #10–#11：middleware 门闩；关闭时路径与线上一致
- [ ] #12/#14：lab sync CLI 上限、secrets 文件权限假设、错误不带 token
- [ ] #13：retry 分类是否过宽/过窄；NFS sync 是否可能被误开
- [ ] #14 `puller_loop`：上传正确性、失败进 `failed/`、hot chmod、settings 热读
- [ ] #15–#16：auth cookie、QR 只写文件、requeue 安全、subprocess 超时与 redact
- [ ] #17–#18：compose snippet 与 live 一致；settings 校验（limit 1–20）；timer apply 失败时的 fallback 文案
- [ ] 测试是否覆盖门闩与 path escape；有无缺集成测说明

---

## 8. 给 Reviewer 的复现命令（只读 / lab）

```bash
# 单测
cd <vpush checkout>
pytest -q tests/test_arm_middleware.py tests/test_arm_lab_ops.py \
  tests/test_arm_lab_ops_phase2.py tests/test_arm_lab_ops_settings.py \
  tests/test_puller_loop.py

# 只读看开关
python -c "from app.arm_middleware import middleware_enabled; print(middleware_enabled())"
```

ARM 上（需 SSH，**勿打印 secrets**）：

- 面板：`http://100.112.25.21:8055`
- 设置文件：`/data/vpush-ima-cache/ops-lab-settings.json`
- 日志：`/data/vpush-ima-cache/logs/{ima,cicc}-lab-sync-*.log`、`ops-audit.jsonl`、`vpush-sim-*.json`

---

## 9. 后续（产品，非本次必须 review）

1. 存储机恢复 → 再议生产中间层开关与读路径  
2. 可选：puller 上传并发  
3. 可选：容器能安全 apply systemd timer（挂载或 host agent）  
4. 面板改时钟后确认 host timer 与 settings 一致  

---

## 10. 联系与角色

- 运营 Agent：VPUSH运营（本交接撰写方）  
- 用户：Kale（GitHub icekale）  
- 相关队友：网络资产管理（到期/台账）、Grok Build（重活）— **代码审查请直接对着本仓库 PR #10–#18**

**机密**：交接文档不含 Cookie/密码；若 review 需要凭据形态，只描述路径与权限，不要向聊天回显内容。
