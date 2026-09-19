# V Push：ARM 中间层架构 v2（权威归档迁 ARM）

**状态：** 设计稿 2026-09-19 · 作者：ZCode（基于 Grok Build v1 交接与实测数据重设计） · 尚未实施
**前版：** `docs/ARM中间层架构-v1-20260919.md`（存储故障期临时桥接 → 演变为「ARM 唯一读源」，但缺回填与容量方案）
**实测基线（2026-09-19）：** 库体积 **118G**（生产 `df` 权威值）· ARM 单盘 46.6G 已用 4.8G、无块卷 · cache 仅 21M

## 0. 一句话目标

把**权威归档树**（经典布局，现 118G）搬到 ARM 的块卷上：生产只读挂 ARM 导出、IMA 下载手臂也在 ARM；存储机冻结为冷备；115 降级为树级统一异步备份。阅读路径零 115、零存储机。

### 与 v1 的关键分歧

v1 保留 staging→puller_loop→hot→arm_nfs_sync 作为主写路径，同时没回答「118G 存量怎么上 ARM、45G 盘装不下怎么办」。v2 的答案：

1. **树已在本地，中转层从「桥」变成「绕路」。** IMA 走经典 puller 直写树（代码零改），中金 collector 直写树（原生契约），staging/hot/nfs_sync 降级为 lab 工具与一次性存量合并。
2. **容量用 Oracle 块卷解决**（Always Free 桶 200G 含 boot，可挂 ~150G），回填用 rsync，两个 v1 缺失项都在 Phase 1 闭环。

## 1. 不变量（沿用 v1，一条不减）

- 生产 compose 永不出现 `VPUSH_ARM_MIDDLEWARE` / `VPUSH_ARM_NFS_SYNC`
- 115 永不进阅读路径；OpenList 不暴露 115；只读浏览走 `/lab-hot`
- secrets 全 600 / 目录 700，不进 git；Ops :8055 只走 Tailscale
- `arm_nfs_sync` / lab sync timer 默认关；开采/切流需 Kale 明确点头
- 不上 Memcached/Redis（缓存的是 PDF 文件，清单用 SQLite）

## 2. 角色拆分（v2）

| 角色 | 谁 | 做什么 | 不做什么 |
|---|---|---|---|
| 发现与索引 | 生产 VPS | IMA 账号同步发现新文档（现有逻辑不变）、知识库索引、读 PDF | 不下载 IMA CDN（交 puller）、不写树 |
| 权威归档 | ARM 块卷 `/srv/vpush-ima` | 经典布局唯一写目标；NFS 只读导出给生产 | 不 GC、不上 115 直读 |
| IMA 下载手臂 | ARM `ima_puller.py` :8743 | 收生产 POST，从 ima.qq.com 下载写树（现有代码零改） | 不做发现/去重（生产 DB 是权威） |
| 中金采集 | ARM `cicc_report_collector`（直写模式） | 采集→去水印→直写树 + sidecar | 不走 staging（除非 115/lab 需要） |
| 异地备份 | ARM `archive_115_backup`（P2 新增） | 树级增量 → 115，低频限速 skip-uploaded | 不给阅读台、不给 OpenList 用户 |
| 冷备 | 存储机 10.80.0.2 | 切流后冻结只读，30 天观察期后处置 | 不再接收任何写入 |
| Lab 工具链 | staging/hot/puller_loop/nfs_sync | OpenList `/lab-hot` 浏览、手工补采/修复 | 退出主写路径 |

## 3. 数据流（v2）

```
生产 vpush（IMA 发现，IMA_PULL_URL 指 ARM）
      │ POST dest + ima.qq.com 签名 URL
      ▼
ARM ima_puller :8743 ──下载──► /srv/vpush-ima（块卷，经典布局，0664）
                                    ▲
ARM cicc_report_collector ──直写────┘（含 .vpush-local-library.json / meta.jsonl sidecar）
                                    │
              ┌─────────────────────┼──────────────────┐
              ▼                     ▼                  ▼
   NFS ro 导出 → 生产挂载      archive_115_backup    /lab-hot（lab 视图，可选）
   (容器 /data/ima-archive)    （树级增量，低频）
```

IMA 生产端代码路径已核实（`app/ima_documents.py:1315`）：设了 `IMA_PULL_URL` 且中间层关 → 生产只 POST 不落盘，puller 返回 size/md5。因此切到 ARM 只需改生产两行 env，**代码零改动**。

## 4. 容量方案（v1 缺失项 #1）

- 现状 118G；增长估 ~15–25G/年（中金日更 + IMA，Phase 0 实测校准）
- Oracle Always Free 块存储桶 200G（含 boot 46.6G）→ **免费可挂 ~150G 块卷**；若 tenancy 非 Always Free，150G ≈ $3.8/月
- 118G + 2 年增长 ≈ 160G vs 153G 免费上限：先挂 150G，**df ≥85% 触发在线扩容**（Oracle 支持不停机扩；超出免费桶后按 $0.0255/GB/月）
- GC 问题随之消失：权威树永不清理；45G 根盘只放 staging/logs/docker（现 21M，水位 30/35G 维持不变）

## 5. 回填方案（v1 缺失项 #2）

```bash
# ARM 上执行（需 ARM↔存储机 SSH 互信，Grok 操作；密钥勿入 git）
rsync -a --info=progress2 --bwlimit=20000 \
  root@198.12.125.212:/srv/vpush-ima/ /srv/vpush-ima/
# 可重复跑（增量）；切换窗口内最后跑一轮 delta（分钟级）
```

验收：两侧 `find /srv/vpush-ima -type f | wc -l` 一致；随机抽 50 个文件 md5 一致；`.vpush-local-library.json`、`.vpush-local-meta.jsonl`、中金 sidecar `.json` 在列。`--bwlimit` 必须设（回填期间存储机还在服务生产读）。若 staging/hot 有 lab 时代存量，先 `arm_nfs_sync --apply --dest /srv/vpush-ima` 合入再回填。

## 6. 服务与网络前提

- **网络**：生产加入 Tailscale（或与 ARM 建 WireGuard）。NFS 与 8743 都**只绑内网地址**（沿用 ima-storage README 的门闩：`ss -tlnp | grep 8743` 不得出现公网 IP）。⚠️ 此前提 v1 未提，切流阻塞项。
- **NFS 导出**（ARM `/etc/exports`）：`/srv/vpush-ima <prod-tailnet-ip>(ro,fsid=0,no_subtree_check)`；puller 已 chmod 0664/0775，生产容器 uid 99 只读无碍；生产挂载参数建议 `ro,soft,timeo=100,retrans=2,actimeo=60`（v1 已指出现网 `timeo=50` 过激）。
- **ima_puller on ARM**：复用 `deploy/ima-storage/vpush-ima-puller.service` 模板，改 `--root /srv/vpush-ima --bind <ARM-tailnet-ip>`；token 沿用或新铸，存 `/opt/vpush-ima-lab/secrets/`。
- **cicc on ARM**：systemd 常驻（暂 stop），**不带 `--arm-middleware`**、直写 `/srv/vpush-ima`；需确认其 Cookie/去水印 overlay 路径在 ARM 可用（Phase 2 验收项）。

## 7. 切换窗口（分钟级、可回滚）

前提：Phase 1/2 全部验收通过 + Kale 明确「切」。

1. 存储机停写：`systemctl stop/disable` cicc collector 与 8743 puller
2. ARM 跑最后一轮 rsync delta
3. 生产改两行并重启 vpush：挂载源 → `ARM:/srv/vpush-ima`；`IMA_PULL_URL` → `http://<ARM>:8743/pull`
4. 验证：抽读新旧 PDF、`healthz` 改指 ARM puller、发一篇新 IMA 帖看落盘与索引
5. 启动 ARM cicc（采集延续，非新开；与「lab timer 停采」是两回事，Kale 确认即可）

**回滚**：改回挂载源 + `IMA_PULL_URL`，重启存储机写服务。损失仅窗口后新文件（反向 rsync 可补）。切流前存储机数据**保持原样不删**。

## 8. 稳态与 P2

- `archive_115_backup`：新小脚本，树级增量（sqlite 账本 key=relpath+size+mtime，复用 puller 的 115 client 与 `upload_ok`），每日低频限速。一个 job 覆盖全部来源，替代 v1 的「每源各自经 puller_loop 上 115」。
- 存储机：冻结只读，30 天观察期后退役或转纯冷备。
- 监控四件套：ARM df 85% 告警、puller `/healthz`、生产 NFS 挂载探活（canary 文件 stat）、115 账本落后量。
- staging/hot/`arm_nfs_sync`：保留代码与 Ops 入口，常驻服务不跑（nfs_sync 稳态无用武之地）。

## 9. 风险表

| 风险 | 缓解 |
|---|---|
| Tailscale 成为读路径依赖（tailnet 故障=读挂） | puller/NFS 只绑 tailnet 是安全前提；备选 direct WG；runbook 写死回滚步骤（改回存储机两行） |
| Oracle 免费实例/桶被回收 | 数据三副本（ARM/存储冻结/115）；评估转 PAYG（不回收、用量内免费）；ARM 持续有流量不易判 idle |
| 双写冲突 | 每源单一 writer：IMA=生产驱动 puller，中金=ARM cicc；lab sync timer 保持 disabled |
| 免费桶 150G vs 118G | 余量 ~30G；85% 触发扩容；Phase 0 实测日增量校准 |
| 回填拖垮存储机读 | `--bwlimit` + 错峰；rsync 增量可断点重跑 |

## 10. 实施清单（顺序即依赖）

- [ ] Phase 0 拆雷：Lab drop-in `DRY_RUN=0`→`1`；`docs/arm-middleware.md:191` 与 `scripts/arm_nfs_sync.py` docstring 改新口径；向 Grok 核实 `scripts/cache_gc.py`/`GC_*` 是否 Lab 本地未提交（是则回仓，否则改交接文档）；实测采集日增量
- [ ] Phase 1 容量：挂 ~150G 块卷 → `/srv/vpush-ima`；rsync 回填 + 抽样校验
- [ ] Phase 2 服务：生产入 tailnet；NFS ro 导出；puller systemd；cicc 部署待启；（可选）lab 存量合入
- [ ] Phase 3 切换：第 7 节五步，Kale 点头后执行
- [ ] Phase 4 稳态：115 统一备份 job；存储机冻结；监控四件套
