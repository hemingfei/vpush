# 存储机本地文件夹知识库挂载设计

日期：2026-08-29
状态：待确认

## 1. 结论

**现在不行。** 在存储 VPS 上直接 `mkdir` 不会变成 `/knowledge` 里的知识库。

当前知识库只认 IMA 采集源：主 VPS 的 `manifest.json` / `state.json`（以及可重建的 SQLite 读模型）里必须有 `group_id` + `media_id` 记录。磁盘上多出来的目录对阅读桌不可见。IMA 采集也不会去扫这些目录。

若要把存储机上的自建文件夹挂进知识库，必须新增一种 **本地库（local library）** 源。本文定义该源的目录契约、扫描、授权、与 IMA 隔离，以及存储 VPS 登录方式。

私钥正文不入库、不进 Compose、不进聊天记录。规格只记录路径、公钥和指纹。

## 2. 现状为什么挂不上

IMA 归档在存储机：

```text
/srv/vpush-ima/                          # NFS 导出根，UID 99 GID 100
  .vpush-ima-root
  <group_id>__<16位sha>/                 # IMA 库命名空间，禁止手改
    <MMDD|unknown>/
      <title>__<token>.pdf
```

主 VPS 通过 WireGuard 挂载：

```text
10.80.0.2:/srv/vpush-ima  →  /mnt/vpush-ima  →  容器 /data/ima-archive
```

阅读链路是：

```text
ACL/订阅 → catalog/list → manifest/state 或 SQLite → 相对路径 → authorized_archive_file()
```

因此：

- 在 `/srv/vpush-ima/随便一个名字/` 丢 PDF：NFS 能看见，`/knowledge` 看不见。
- 往现有 `<group_id>__<hash>/` 里塞文件：采集可能覆盖、改名或忽略，且没有 manifest 记录，阅读桌仍看不到。
- 没有 IMA `media_id` 的文件不能走现有下载器。

禁止把任意根目录子文件夹自动当成知识库。IMA 命名空间和健康/标记文件必须保持只读约定。

## 3. 目标

管理员在存储机预留目录里建一个文件夹并放入 PDF 后，可在 `/admin/knowledge` 启用该库，授权用户后出现在 `/knowledge`，走现有列表、搜索、阅读、ACL。

成功标准：

- 新建 `local/<slug>/` + 标记文件 + 若干 PDF 后，扫描一次即可列出。
- 搜索仍只覆盖标题、资料源、标签、摘要；本地库摘要默认为空，不索引 PDF 正文。
- IMA 采集不下载、不删除、不重命名 `local/` 下文件。
- 存储异常时只影响阅读，不影响推送和其他数据源。
- 未启用或未授权的本地库对普通用户不可见。

## 4. 范围

包含：

- 预留目录 `/srv/vpush-ima/local/<slug>/` 与标记文件契约。
- 主 VPS 经 NFS 扫描 PDF，写入 manifest/state（及 SQLite 读模型，若已上线）。
- 合成 `group_id = local-<slug>`，走现有 ACL/订阅。
- `/admin/knowledge` 显示已发现本地库、启用开关、立即扫描。
- 存储 VPS SSH 登录与密钥清单。

不包含：

- 把文件塞进现有 IMA 组目录并冒充 IMA 文档。
- 网页上传、WebDAV 写库、S3 导入。
- 非 PDF（含 doc/ppt/zip/txt-only）。
- 自动 OCR / 摘要生成 / PDF 全文检索。
- 把本地文件回传到 IMA 云。
- 改 NFS/WireGuard/TCP、改存储 puller、改 IMA 重试。

## 5. 目录契约

只扫描这一棵树：

```text
/srv/vpush-ima/local/<slug>/
  .vpush-local-library.json
  [可选 MMDD 子目录/]
  *.pdf
  nested/.../*.pdf
```

规则：

- `<slug>`：`[a-z0-9][a-z0-9-]{0,46}`，小写。目录名即 slug。
- 组 ID：`local-<slug>`，符合现有 `[A-Za-z0-9_-]{1,64}`。
- 必须有标记文件，否则忽略该目录。
- 符号链接、逃出 `local/<slug>` 的路径、以及 `.` 开头文件（标记除外）一律跳过。
- 属主必须是 `99:100`，目录 `0750`，文件 `0640`。SSH 以 root 创建后必须 `chown -R 99:100`。
- 禁止在 `/srv/vpush-ima/` 根下、IMA 组命名空间下、或 `.vpush-*` 健康/标记旁新建“知识库”。

标记文件：

```json
{
  "name": "内部纪要",
  "enabled": false,
  "tags": []
}
```

- `name`：展示名，必填，1–80 字。
- `enabled`：磁盘默认关闭；真正对外可见还要管理员在网页启用（两者都开才进 catalog）。
- `tags`：可选，应用到该库所有文档的默认标签。

新建示例（在存储 VPS 上）：

```bash
install -d -o 99 -g 100 -m 750 /srv/vpush-ima/local/neibu-jiyao
printf '%s\n' '{"name":"内部纪要","enabled":false,"tags":[]}' \
  > /srv/vpush-ima/local/neibu-jiyao/.vpush-local-library.json
chown 99:100 /srv/vpush-ima/local/neibu-jiyao/.vpush-local-library.json
chmod 640 /srv/vpush-ima/local/neibu-jiyao/.vpush-local-library.json
# 放入 PDF 后同样 chown 99:100 与 chmod 640
```

## 6. 扫描与索引

扫描只在主 VPS 上走 NFS，不在存储机再起采集进程。

触发：

- 管理员点「扫描本地库」。
- 现有 IMA 调度周期内附带一次廉价 `local/` 遍历（失败只记日志，不挡 IMA）。

每个 PDF：

- `media_id`：`loc` + 相对路径 SHA-256 的 20 位十六进制，满足现有 media_id 规则。
- `name`：文件名去掉 `.pdf`。
- `group_id` / `group_name`：`local-<slug>` / 标记里的 `name`。
- `day`：若某级父目录是四位数字 `MMDD` 则用它，否则 `unknown`。
- `abstract`：空。
- `has_pdf`：文件存在且可读。
- `pdf_path`：相对 `archive_root` 的路径，例如 `local/neibu-jiyao/0829/纪要.pdf`。
- `has_txt`：对应 `.txt` 存在则为真，不自动抽取。

删除检测：标记还在、PDF 已删 → 从索引去掉该文档，不删磁盘其他文件。整库目录或标记消失 → 组停用，已有 ACL 保留但 catalog 不再列出。

写入顺序：先更新 JSON manifest/state，再更新 SQLite 读模型。扫描不得调用 IMA API，不得经 puller 下载。

IMA 同步必须显式跳过 `local/`，也不得把 `local-*` 组当作 IMA `knowledge_base_id`。

## 7. 产品行为

- `/knowledge` 把本地库与 IMA 库同一套流：最新、分库、搜索、阅读。`source` 显示库名。
- 管理员在 `/admin/knowledge` 看到「本地库」列表：slug、名称、PDF 数、上次扫描、启用开关、ACL。不提供存储机 shell。
- 默认不启用。发现新目录不等于对用户可见。
- ACL/订阅复用 `ima_kb_acl` / `ima_kb_subscriptions`，`group_id` 用 `local-<slug>`。
- 阅读仍走 `archive_readable()` + `authorized_archive_file()`，拒绝绝对路径和越界路径。
- 手机端知识库行为不因本地库改变。

失败：

- NFS/标记根不可读：本地库扫描跳过，IMA 与其它功能继续。
- 单个 PDF 不可读：跳过该文件，继续其余。
- slug 非法或与现有 IMA `group_id` 冲突：该目录忽略并在管理页报错。`local-` 前缀专供本地库，IMA 组不得使用。

## 8. 存储 VPS 登录与密钥

生产存储机（Dedirock）：

| 项 | 值 |
|----|----|
| 公网 | `198.12.125.212` |
| 用户 | `root` |
| SSH 端口 | `22` |
| 认证 | 仅公钥，已关密码登录 |
| 系统 | Debian 13 |
| WireGuard | `10.80.0.2`（对端主 VPS `10.80.0.1`） |
| 归档根 | `/srv/vpush-ima` |
| NFS | 仅 WG 网段，`all_squash,anonuid=99,anongid=100` |
| 测试机 | Unraid `192.168.5.28` 不是生产 |

登录（从本机）：

```bash
ssh -i "/Volumes/main/存储VPS-SSH/id_ed25519_ima-storage" -p 22 root@198.12.125.212
```

密钥只放在本机加密卷，不要复制进仓库：

| 角色 | 私钥路径 | 公钥 | 指纹 |
|------|----------|------|------|
| 存储机恢复/日常 | `/Volumes/main/存储VPS-SSH/id_ed25519_ima-storage` | `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFaZM3A5hKYQkJFUCJ4+4aXN46/q6zI1MlRMKXTrJdO4 ima-storage-vps` | `SHA256:e+LpwT2x3xCzBldu2ZJPmRlVLVICsozalPK2U2lu/bY` |
| 本机默认运维钥 | `/Users/kale/.ssh/id_ed25519` | `ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOPyIwTWHbMEQiIyZT1kGpcq+Hi77EGWv236jUBBBfwU codex-stock-fupan-unraid` | `SHA256:Hjm0DGureqJxU8maLVC+CpR8PgjG2COuAwZADLRLNcg` |

约束：

- 关闭密码登录前，必须用**用户本人能碰到的私钥**实测成功。不能因为主 VPS 能登录就关密码。
- 恢复钥必须保持可访问：`/Volumes/main/存储VPS-SSH/id_ed25519_ima-storage`。
- `authorized_keys` 只保留恢复钥、本机运维钥、以及已验证的运维钥。不要为了挂本地库再开密码或改端口。
- 主机指纹见本机 `~/.ssh/known_hosts` 中 `198.12.125.212` 的 `ssh-ed25519` / `ecdsa-sha2-nistp256` 条目。
- 私钥文件权限保持 `0600`/`0700` 属主自己。不要把 PEM 写入本规格、Git、`docker-compose`、issue 或日志。
- IMA Cookie / Refresh Token / pull token **不要**拷到存储机。本地库不需要它们。

登录后只允许动 `local/`。不要改 `.vpush-ima-root`、不要手改 IMA 组目录、不要在同步期间调 TCP。

## 9. 验收

- 无标记目录：扫描忽略，catalog 不出现。
- 有标记但未网页启用：管理员能看见，普通用户没有。
- 启用并授权后：`/knowledge` 能按文件名搜索到 PDF，阅读器能打开。
- 删除一个 PDF 再扫描：列表消失，其它文件仍在。
- IMA 立即同步：`local/` 文件数量与内容不变。
- 用恢复钥从本机 SSH 登录成功；错误私钥被拒绝。
- 以 UID 99 经 NFS 可读 `local/<slug>/`；`0700 root:root` 的目录对容器不可读，视为配置错误。

## 10. 非目标

- 不把存储机变成通用网盘。
- 不在 `/knowledge` 暴露原始 POSIX 树。
- 不因为本地库去引入 FTS5、对象存储或新搜索服务。

## 11. 附录：摘要与标签 sidecar（2026-08-30 增补，用户已确认）

用户要求本地库文档与 IMA 文档有同等的摘要、标签体验。中金列表 API 自带官方摘要与分类标签，
采集侧把元数据落成 sidecar 文件，扫描入库时读取：

- sidecar 路径：`local/<slug>/.vpush-local-meta.jsonl`（`.` 开头，扫描器不当作文档，与标记文件同样只读不删）
- 每行一个 JSON：`{"id","title","summary","tags":[...],"day","authors"}`，`id` 为字符串报告 id
- 匹配规则：PDF 文件名 `*_<id>.pdf` 尾缀的 `<id>` 对应 sidecar 行
- 摘要：`summary` 写入该文档 `abstract`；无对应行则摘要为空（回退原 §6 行为）
- 标签：sidecar `tags`（≤5，来自 reportType + documentLabels + 行业名）与标记文件库级 `tags` 合并去重
- `day`/`title` 仅作 MMDD 目录与文件名的兜底，不覆盖现有磁盘事实
