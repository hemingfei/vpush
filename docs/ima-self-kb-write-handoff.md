# IMA 自建库写入交接

日期：2026-08-29  
仓库：`icekale/vpush`（本地 `dav-subscription`）  
当前发布：`v1.12.91` / `main` @ `bc38023`  
交接范围：判断「自建库能否自动化建库 / 建文件夹 / 上传到指定目录」，以及该走哪条通道。

本文不写 token、cookie、签名 URL、SSH 私钥。生产密钥只在 VPS SQLite / `.env`，不要进 Git、日志、命令行参数。

---

## 一句话结论

- **订阅库（VIP 研报）只读采集已经通。** 这是现在的 vpush 知识库。
- **往订阅库里建文件夹、塞文件：OpenAPI 做不到，安卓协议也没证据能做。**
- **自建库的建库 / 建文件夹 / 上传：官方 OpenAPI 能无人值守。** 现有代码还没接写接口。
- **不要用现有安卓 `ImaPureClient` 去做写入。** 它只复现了读。

---

## 现在线上在干什么

vpush 知识库是 **订阅库归档**，不是 IMA 网盘客户端。

生产采集走安卓协议（refresh token → 加密 `get_media` → 签名 COS URL → PDF 落到远程 HDD）。入口：

| 层 | 路径 |
|---|---|
| 采集客户端 | `app/ima_documents.py` → `ImaPureClient` |
| 产品权限 | `app/ima_kb.py` + `app/db.py` 的 `ima_kb_acl` / `ima_kb_subscriptions` |
| 大 V 动态抓取（另一条，别混） | `app/fetchers/ima.py` |

已实现的读能力：

1. `POST /oversea/auth_login/refresh`
2. `POST /knowledge_tab_reader/search_knowledge_base`（自动发现）
3. `POST /knowledge_tab_reader/get_knowledge_list`（列目录）
4. 加密 `POST /s/file_manager/get_media`（拿下载 URL）

旧发现接口 `/knowledge_tab_reader/list_knowledge_bases` **已经 404**。不要改回去。2026-08-27 线上实测：`search_knowledge_base` 200，发现成功；抓取设置里若还显示「自动发现失败：IMA HTTP 404」，是旧 `last_result`，刷新即可。

权限（和采集无关）：

- 管理员看全部已注册库。
- 普通用户：`ima_kb_acl` 有自己 → 可订；再加 `ima_kb_subscriptions` → 才能读。缺一即 404。
- 后台入口：用户弹窗「知识库」勾选 → `PUT /api/admin/users/{id}/ima-kb`。
- 抓取设置的「启用 / folder_ids」只控制采不采，不控制谁能看见。

---

## 两条通道，不要混

```
安卓协议（refresh token）          官方 OpenAPI（clientid + apikey）
  已逆向：只读下载                   官方文档：自建库读写
  订阅库 PDF 归档靠这条              自建库建库/建文件夹/上传靠这条
  写接口未 hook                     订阅库原文 220030 门控
```

### A. 安卓协议（现有知识库采集）

凭证：`ima_pure_uid` + `ima_pure_refresh_token`（SQLite，手机同步脚本写入）。  
BASE：`https://ima.qq.com/cgi-bin`  
加密：AES-128-GCM + RSA-OAEP-SHA256，16-byte AES key。  
手机只负责换票：`scripts/ima_phone_sync.py` / `scripts/ima_phone_sync.command`。

**没有** `create_folder` / `create_knowledge_base` / 上传。要走这条写，必须再 hook 一次 App 创建/上传，不能从现有下载客户端猜。

### B. OpenAPI（自建库自动化该走这条）

凭证：`IMA_OPENAPI_CLIENTID` + `IMA_OPENAPI_APIKEY`  
生成：https://ima.qq.com/agent-interface  
后台键：`ima_openapi_clientid` / `ima_openapi_apikey`  
BASE：`https://ima.qq.com/openapi/wiki/v1`  
头：`ima-openapi-clientid` / `ima-openapi-apikey`

现有代码只用它 **读**：`get_knowledge_list`、`get_media_info`。见 `app/fetchers/ima.py`。

官方写链路（社区/技能文档，未在本仓库接上）：

| 动作 | 接口 |
|---|---|
| 建库 | `create_knowledge_base` |
| 建文件夹 | `create_folder` |
| 上传到库/指定文件夹 | `check_repeated_names` → `create_media` → COS 直传 → `add_knowledge`（带 `folder_id`） |
| 网页入库 | `import_urls` |

这是固定 apikey，适合 cron。不需要每次扫码，不需要安卓 refresh token。

**实测门控（`docs/research/2026-08-20-ima-fulltext-recon.md`）：**

| 操作 | 自建库 | 订阅库 |
|---|---|---|
| 列表 | 可 | 网页 Cookie 元数据全；OpenAPI 列表经常对不上订阅库数字 ID |
| 原文 / 文件 | `get_media_info` 返回 `url_info.url` | `220030`「没有权限通过 skill 获取订阅知识库的文件」；data 为空 |
| 建库 / 建文件夹 / 上传 | 官方支持 | 产品不允许 |

`220030` 是产品门控，不是会话过期。换 cookie、伪装 UA、改 `CLIENT-TYPE` 都救不了。

---

## 建议接手任务（如果要做自建库写入）

目标默认是：**对本账号自建库做无人值守建库 / 建文件夹 / 上传到指定 folder_id**。不要碰订阅 VIP 研报库。

1. 确认后台已有 OpenAPI 凭证（Cookie 管理，不是 Refresh Token）。没有就去 agent-interface 生成，填 `clientid + apikey`。
2. 先只读冒烟：`get_knowledge_list` 能看见自建库。看不见订阅库是正常的。
3. 接最小写路径，不要先做 UI：
   - `create_knowledge_base`
   - `create_folder`
   - 上传四步（检查重名 → 建 media → COS → `add_knowledge`）
4. 用一个空的自建测试库验证，不要往生产研报库写。
5. 再决定要不要进 vpush 管理页。采集器 `ImaPureClient` 保持只读。

不要做：

- 用安卓 `get_media` 加密通道去上传。
- 往「八大顶级投行研报 VIP」等订阅库上传。
- 把 OpenAPI 凭证写进 Git / 命令行 / 日志。
- 把自建库写入和现有 PDF 归档采集揉成一套调度。

参考（第三方，非本仓库代码）：

- https://ima.qq.com/agent-interface
- OpenAPI 技能文档里的 kb-api（`create_folder` / `create_media` / `add_knowledge`）
- 本仓库：`app/fetchers/ima.py`、`docs/research/2026-08-20-ima-fulltext-recon.md`

---

## 生产注意（只读采集，别弄坏）

- 知识库 PDF 在远程 HDD，不在主 VPS 本地盘。`IMA_ARCHIVE_ROOT` / `IMA_PULL_URL` 相关约定见项目记忆，改采集前先问。
- `folder_ids=[]` 表示不挂载；缺字段才回退 `root_folder_id`。空数组不要当成「挂根」。
- 「全球顶级投行研报库」禁止再挂根。
- 同步只下 PDF；标签用标题+摘要，不抽 TXT。
- Refresh Token 轮换：手机登录 IMA 后双击 `scripts/ima_phone_sync.command`。

未跟踪、不要当交接材料提交：`.cursor/`、`docs/research/` 里的 mitm/字符串大文件、`work/`、探针脚本。
