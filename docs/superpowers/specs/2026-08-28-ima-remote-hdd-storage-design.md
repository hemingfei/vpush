# IMA 远程 HDD 存储设计

日期：2026-08-28
状态：已确认，待书面规格复核

## 1. 目标与范围

将 V Push 的 IMA 知识库大文件迁移到同在洛杉矶的一台独立 HDD VPS，解决主 VPS 容量不足，同时保证存储 VPS 或两机网络异常时只降级知识库，不阻塞推送、订阅、后台和其他数据源。

已确认的存储 VPS：

- 1 vCPU
- 2 GB RAM
- 1 TB HDD
- 1 Gbps 端口
- 2 TB/月流量
- 独立 IPv4、KVM、root 权限

本次包含：

- WireGuard 点对点私网和 NFSv4 在线文件存储。
- IMA 本地索引与远程归档拆分。
- 存储可用性、容量和月流量状态。
- Restic 加密对象存储备份。
- 现有 IMA 文件的两阶段迁移、验证、回滚和故障演练。
- 10 人以内同时阅读的生产验收。

本次不包含：

- 第二台在线存储副本或知识库高可用。
- JuiceFS、SeaweedFS、Ceph、Redis 或 PostgreSQL 元数据服务。
- 多个 V Push 实例同时写入同一知识库。
- CDN、S3 直出或对象存储应用适配层。
- SQLite、日志或其他 V Push 数据迁移到 HDD VPS。

## 2. 已知现状

2026-08-28 生产实测：

- `/opt/vpush/data/ima` 约 3.0 GB。
- 约 2,508 个 PDF 和 2,508 个 TXT。
- `manifest.json` 约 4.8 MB，`state.json` 约 2.0 MB。
- 旧的全球投行知识库曾单独占用约 11 GB。
- 后续会继续增加大型知识库。
- 当前只有一个 V Push 应用实例，但有多人使用，预计同时打开知识库文档不超过 10 人。

当前 `ImaDocumentStore` 把 `manifest.json`、`state.json`、PDF 和 TXT 放在同一根目录。PDF 下载先写同目录 `.part` 临时文件，校验 PDF 与大小后 `os.replace`；TXT 也先写临时文件再原子替换。SQLite 位于 `/data/dav.db`，不属于 IMA 归档。

## 3. 方案选择

### 3.1 采用 NFSv4 + WireGuard + Restic

这是当前推荐方案：

- NFSv4 提供现有 Python `Path`、目录、`stat`、顺序 I/O 和 rename 所需的文件系统语义。
- WireGuard 避免把 NFS 暴露到公网。
- Restic 把单块 HDD 从唯一副本降级为在线副本，并提供客户端加密、增量和保留策略。
- 组件数量最少，适合一个 V Push 实例和 10 人以内并发。

### 3.2 暂不采用 JuiceFS

JuiceFS 适合多个应用节点、对象存储后端和更大规模共享挂载，但当前会额外引入 FUSE、元数据引擎、缓存管理和新的恢复链路。单台 HDD 后端也不会因 JuiceFS 自动获得高可用。

出现以下任一条件时重新评估 JuiceFS 或 S3 直存：

- 第二个 V Push 实例需要共同挂载和写入。
- 在线归档接近 800 GB，需要跨多个存储节点扩容。
- 超过 50 人持续并发下载，主 VPS 代理带宽成为瓶颈。
- 需要对象直出、CDN 或跨地域在线副本。

## 4. 目标拓扑

```text
用户
  │ HTTPS
  ▼
LA 主 VPS
  ├─ V Push 容器
  ├─ /opt/vpush/data/dav.db                 本地 SSD
  ├─ /opt/vpush/data/ima/manifest.json      本地 SSD
  ├─ /opt/vpush/data/ima/state.json         本地 SSD
  ├─ /opt/vpush/data/ima_storage_status.json 本地 SSD
  └─ /mnt/vpush-ima                         NFSv4 客户端
          │ WireGuard 10.80.0.0/30
          ▼
LA 存储 VPS
  ├─ /srv/vpush-ima                         1 TB HDD / ext4
  ├─ NFSv4 server
  ├─ Restic client
  └─ systemd health/backup timers
          │ HTTPS/S3
          ▼
独立 S3 兼容对象存储
```

主 VPS 的 Compose 保留 `./data:/data`，另加：

```yaml
- /mnt/vpush-ima:/data/ima-archive
```

应用设置：

```text
IMA_ARCHIVE_ROOT=/data/ima-archive
IMA_STORAGE_STATUS_PATH=/data/ima_storage_status.json
```

不配置 `IMA_ARCHIVE_ROOT` 时保持当前单根目录行为，兼容本地、测试和其他部署。

## 5. 存储模型拆分

### 5.1 本地索引根

`ImaDocumentStore` 的现有 `root` 继续作为索引根：

- `manifest.json`
- `state.json`
- 原子写入所需的同目录临时 JSON

索引根始终位于主 VPS 本地 SSD。列表、分组、日期、标签和 ACL 不依赖 NFS 成功。

### 5.2 远程归档根

新增可选 `archive_root`：

- PDF
- TXT
- PDF `.part` 临时文件
- TXT `.tmp` 临时文件
- 知识库和日期目录

`archive_root` 未指定时等于 `root`。所有现有 state 路径仍保存为相对路径，迁移前后不改变 group namespace、日期目录或文件名。

路径边界校验改为相对于 `archive_root`；仍拒绝绝对路径、越界路径和归档根符号链接。临时文件与目标文件必须位于同一个远程目录，以保留原子 rename。

### 5.3 存储标记

远程归档根必须存在：

```text
.vpush-ima-root
```

该文件只作为存储身份标记，不保存凭据。标记缺失时应用不得创建知识库目录、下载文件或把远端目录当作新的空归档。

## 6. 故障隔离

### 6.1 状态探测

主 VPS 的 systemd timer 每 60 秒执行独立探测：

- WireGuard peer 最近握手时间。
- NFS TCP 2049 可达。
- 挂载点和 `.vpush-ima-root` 可读。
- NFS 文件系统不是只读。
- HDD 使用率和 inode 使用率。
- `vnstat` 当月出站流量。

探测结果原子写入本地：

```json
{
  "checked_at": 1787890000,
  "available": true,
  "writable": true,
  "used_percent": 23,
  "inode_percent": 4,
  "monthly_tx_bytes": 123456789,
  "reason": ""
}
```

应用只读取该本地 JSON 决定是否访问归档。状态超过 180 秒未更新时按不可用处理。

### 6.2 应用行为

- 普通知识库列表继续从本地 manifest/state 返回。
- PDF/TXT 读取前检查归档状态；不可用时返回 HTTP 503 `知识库存储暂不可用`。
- IMA 同步在不可用、只读或容量阻断状态下跳过本轮，不清 manifest/state，不落到主 VPS 的空目录。
- `restore_original_filenames`、`rebuild_manifest_from_state`、全量 retag 等会访问归档的启动任务，在归档不可用时跳过并记录一次脱敏警告。
- `/healthz` 继续反映核心 V Push 健康，不因知识库存储失败而失败。
- 增加独立 IMA 存储状态到管理员采集状态；可提供无敏感信息的独立健康检查供外部监控使用。
- 状态从失败恢复后，读请求和下一轮同步自动恢复。

### 6.3 NFS 挂载语义

NFS 只承载可重新下载、以临时文件原子落盘的大文件，不承载 SQLite 或索引。为避免存储故障占满 FastAPI 文件线程，客户端使用有界失败挂载：

```text
nfsvers=4.2,proto=tcp,soft,timeo=50,retrans=2,
rsize=1048576,wsize=1048576,noatime,_netdev,nofail
```

`soft` 是针对可恢复归档的明确取舍，不得复用于数据库、manifest/state 或其他不可重建数据。写入失败时 `.part` 不登记为完成；读取中断只使当次请求失败。

主 VPS 开机时 NFS 不可用，V Push 仍可绑定一个无标记、不可写的本地占位目录启动。挂载恢复后由 host watcher 必要时重启一次 V Push，使 Docker bind mount 看到真实 NFS；正常运行中短暂断线恢复不要求重启。

## 7. 存储 VPS 配置

### 7.1 资源边界

现有 1 vCPU / 2 GB RAM 可满足 NFS、WireGuard 和低峰 Restic：

- 配置 1 GB swap，`vm.swappiness=10`。
- 数据盘使用 ext4 和 `noatime`。
- Restic 使用 `nice -n 10`、`ionice -c2 -n7` 和约 20 MB/s 上传限速。
- 不在备份时段执行全盘哈希、prune 和大规模 IMA 首次同步。

1 TB HDD 阈值：

- 70%：容量预警。
- 80%：阻止新的 IMA 文件下载，已有文件继续读。
- 90%：紧急告警并要求立即扩容或清理。

2 TB 月流量阈值：

- 60%（1.2 TB）：预警。
- 80%（1.6 TB）：紧急预警，检查用户下载和备份流量。
- 对象备份从存储 VPS 直接上传，不经主 VPS 中转。

### 7.2 NFS 权限

- `/srv/vpush-ima` 属主为 UID 99、GID 100。
- NFSv4 仅监听 WireGuard 地址。
- 仅允许主 VPS `10.80.0.1`。
- 导出使用 `rw,sync,root_squash,no_subtree_check`。
- 公网防火墙不开放 TCP/UDP 2049。
- SSH 只允许密钥登录；管理端口由防火墙限制。

虚拟 VPS 未必暴露 SMART。可用时监控 SMART；不可用时监控内核块设备 I/O 错误、ext4 错误、只读重挂载和供应商控制面磁盘状态。

## 8. 备份与恢复

### 8.1 归档备份

存储 VPS 每日低峰执行 Restic：

- 来源：`/srv/vpush-ima`。
- 目标：独立 S3 兼容对象存储的专用 bucket/prefix。
- Restic 仓库密码、S3 key 使用 root-only `0600` 文件。
- 默认压缩，上传限速约 20 MB/s，避免影响 NFS 阅读。
- 保留 30 个每日快照。
- 每周执行 `restic check --read-data-subset=5%`。
- 每月执行 `forget --keep-daily 30 --prune`，不每天 prune HDD。

### 8.2 主 VPS 备份

主 VPS 单独备份：

- SQLite 在线备份产物，不直接复制打开中的 `dav.db`。
- `manifest.json`、`state.json`。
- Compose、systemd 单元、WireGuard/NFS 配置和必要的部署配置。

主 VPS 与存储 VPS 使用独立 Restic snapshot 标签或 prefix，避免误删另一侧快照。

归档文件完成后不再原地修改，索引文件原子替换。两个 Restic 任务不要求全局停机事务：恢复后若索引引用的文件缺失，IMA 同步按现有完整性判断补下载；归档中多出未索引文件也不会被暴露。

### 8.3 恢复演练

- 首次上线必须恢复随机 10 份 PDF/TXT 和一份索引快照，并校验哈希。
- 每季度重复随机恢复抽检。
- 每次迁移、扩容或 Restic 仓库变更后立即做恢复抽检。
- 未通过恢复抽检前，不删除主 VPS 迁移前归档副本。

## 9. 迁移与回滚

### 9.1 准备

1. 发布存储根拆分代码，但不设置 `IMA_ARCHIVE_ROOT`，确认生产仍使用本地目录。
2. 配置存储 VPS ext4、WireGuard、NFSv4、Restic、vnstat 和 systemd timers。
3. 创建 `.vpush-ima-root`，验证 UID/GID 99:100 可创建、rename、读取和删除测试文件。
4. 完成 1 GB 顺序写、顺序读、1,000 次小文件 rename 和 10 路并发读测试。

### 9.2 两阶段复制

第一轮在线复制：

- 从 `/opt/vpush/data/ima/` 复制除 `manifest.json`、`state.json` 外的所有内容到 `/srv/vpush-ima/`。
- 不删除主 VPS 文件，不切换应用。

维护窗口：

1. 停止 IMA 同步并停止 V Push。
2. 创建 SQLite 在线备份和 manifest/state 副本。
3. 执行第二轮增量 rsync。
4. 使用 checksum dry-run 验证源和目标归档零差异。
5. 主 VPS 原目录整体保留为带时间戳的回滚副本；新建本地索引目录并放回 manifest/state。
6. 挂载 NFS，设置 `IMA_ARCHIVE_ROOT=/data/ima-archive`，启动 V Push。

现有数据约 3 GB，维护窗口主要由最终增量和校验决定；不承诺零停机。

### 9.3 上线验证

- `/healthz` 正常。
- IMA 存储状态正常、可写、容量和流量数据有效。
- 知识库列表、日期、标签和 ACL 与迁移前一致。
- 随机 10 份 TXT/PDF 可读，支持 PDF Range 请求。
- 10 路并发读取无 5xx，记录首字节和完整下载时间。
- 触发一个小范围 IMA 增量同步，文件只出现在远端归档，本地主 VPS归档不增长。
- 阻断存储 VPS 后，IMA 文件接口在 NFS 有界重试后返回 503，核心 health、推送和其他 API 正常。
- 恢复网络后，读取和下一轮同步恢复。
- Restic 首份快照和随机恢复抽检通过。

### 9.4 回滚

切换后 7 天内保留主 VPS 原归档。回滚：

1. 停止 V Push 和 IMA 同步。
2. 把远端新增文件增量 rsync 回本地回滚目录。
3. 取消 `IMA_ARCHIVE_ROOT` 和远端 bind mount。
4. 恢复本地单根目录并启动。
5. 验证 health、文档读取和增量同步。

稳定运行 7 天且对象备份恢复抽检通过后，才删除主 VPS 大文件回滚副本。

## 10. 监控与告警

存储状态采用状态转换告警，避免每分钟重复通知：

- WireGuard peer 失联。
- NFS 不可达、标记缺失或只读。
- 状态文件超过 180 秒未更新。
- HDD 70%/80%/90%。
- inode 80%/90%。
- 月流量 60%/80%。
- Restic 最近成功时间超过 30 小时。
- Restic check 失败。
- 内核 I/O/ext4 错误。

管理员状态只显示必要信息，不展示 NFS 地址、WireGuard key、S3 endpoint 或 Restic 凭据。日志错误继续经过现有脱敏路径。

## 11. 测试

### 11.1 应用测试

- 未配置 `IMA_ARCHIVE_ROOT` 时路径和现有行为不变。
- 配置独立 archive root 后，manifest/state 写本地，PDF/TXT 写远端。
- 相对 state 路径在拆分前后保持一致。
- archive root 标记缺失、状态过期、不可用、只读和容量阻断时不下载、不清索引、不写本地兜底目录。
- PDF/TXT 不可用返回 503；列表和核心 API 仍正常。
- `.part` 下载失败不登记完成，成功后同目录原子替换。
- 恢复状态后已有文件可读，缺失文件可补下载。
- archive root 符号链接和路径越界继续拒绝。

### 11.2 运维验证

- WireGuard 只允许两台 VPS 通信。
- 公网无法访问 NFS 2049。
- UID/GID 99:100 的 create/read/rename/delete 通过。
- fio 顺序读写和并发读结果有记录。
- NFS 故障、恢复、主 VPS 重启时存储缺失三种场景通过。
- Restic backup、retention、check 和随机恢复通过。
- `vnstat` 与供应商流量统计误差可接受。

## 12. 完成标准

- 当前全部 IMA 文件完整迁移，checksum 验证无差异。
- SQLite、manifest/state 仍在主 VPS 本地 SSD。
- 主 VPS 不再因 IMA PDF/TXT 增长而增加相应磁盘占用。
- 10 人以内并发阅读满足验收，无持续 5xx。
- 存储故障只降级知识库，核心 V Push 保持健康。
- 70%/80% 容量和 60%/80% 月流量策略生效。
- 独立对象存储存在可恢复的 30 日加密快照。
- 迁移回滚路径已实际验证，7 天后才清理主 VPS 旧归档。
