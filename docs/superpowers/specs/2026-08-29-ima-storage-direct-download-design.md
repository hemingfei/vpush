# IMA 存储机直下 PDF 设计

日期：2026-08-29
状态：已确认，待实施

## 1. 目标与范围

DMIT 主 VPS 只负责 IMA 列目录和 `get_media`（拿签名链接 + `X-IMA-*` 头），存储 VPS 负责对 CDN `GET` 并把 PDF 写到本地 `/srv/vpush-ima`。目的是把 PDF 公网下行和写盘从 1 核 uvicorn 里拿掉，同时不把 IMA token / refresh 放到存储机。

本次包含：

- 存储机上一个只走 WireGuard 的同步拉取服务（无队列）。
- DMIT `ImaPureClient.download()` 在配置了拉取地址时改走该服务。
- CDN `403` 视为链接过期，DMIT 重新 `get_media` 再拉一次。
- 路径锁死、主机名白名单、token、不记录签名 URL。

本次不包含：

- 把列目录、token、state.json、网站读文件搬到存储机。
- 取消 NFSv4（网站读 PDF 仍是 DMIT → NFS → `/srv/vpush-ima`）。
- 对象存储、Restic、JuiceFS、多实例写入。
- TXT 抽取、改文件名扫描、IMA 页大小。

## 2. 已证实前提

2026-08-29 用同一条 `get_media` 签名链接实测：

- 主机：`res-skb.ima.qq.com`
- 查询参数：`media_id`、`media_title`、`sign`、`t`
- 下载头：`X-IMA-Create-URL-Time`、`X-IMA-Platform`、`X-IMA-Resource-Category`、`X-IMA-Sign`、`X-IMA-Trace-ID`、`X-IMA-UID-SHA256`
- 无 Cookie、无 `Authorization`、未绑 IP
- DMIT 与存储机均为 `206 application/pdf %PDF-1.7`

因此存储机直下在授权上可行。真正的登录授权仍只在 DMIT 的 `get_media`。

## 3. 方案

采用**同步 RPC，不要队列**：

```text
DMIT uvicorn 下载线程
  get_media  →  url + headers
  POST http://10.80.0.2:8743/pull   （WireGuard，立刻等结果）
存储 puller
  校验 token / 路径 / https / *.ima.qq.com
  GET CDN（带原 headers + User-Agent okhttp/4.12.0）
  写 /srv/vpush-ima/<dest>.part → os.replace
  返回 {size, md5}
DMIT
  写 state.json（本地 SSD）
用户读 PDF
  仍经 NFS 挂载 /mnt/vpush-ima
```

不排队的原因：签名链接有时效。`get_media` 之后立即拉，链接不落盘、不进日志。

`IMA_PULL_URL` 为空时保持现状（本机 urllib 写 `destination`），本地测试与未切换的环境不变。

## 4. 协议

`POST /pull`

请求：

```json
{
  "dest": "7479082602225992__412935b875c244ff/0829/Report.pdf",
  "url": "https://res-skb.ima.qq.com/...",
  "headers": {"X-IMA-Sign": "..."},
  "expected_size": 12345
}
```

成功 `200`：`{"size":12345,"md5":"..."}`

失败：

| 码 | 何时 |
|----|------|
| 400 | `dest` 逃逸、不是 `.pdf`、url 非法 |
| 401 | token 不对 |
| 403 | CDN 返回 403（调用方重签） |
| 413 | JSON 大于 1MB |
| 415 | 不是 `%PDF-1.` |
| 409 | 大小与 `expected_size` 不符 |
| 502 | CDN 网络错误 |
| 507 | 写盘失败 |

`GET /healthz` → `200` `ok`

鉴权：`Authorization: Bearer <token>`。监听 `10.80.0.2:8743`，不绑公网。

`dest` 必须相对 `/srv/vpush-ima`，解析后 `relative_to(root)`，禁止符号链接父目录，只允许 `.pdf`。

`url` 必须 `https`，hostname 以 `.ima.qq.com` 结尾。单文件上限 200MB。超时 120 秒（与现网 `urlopen` 一致）。

## 5. 应用侧

- `ImaPureClient.download()`：若 `IMA_PULL_URL` 有值，把 `destination` 相对 `IMA_ARCHIVE_ROOT` 的路径 POST 给 puller；否则走现有本机下载。
- `_fetch`：puller 模式下不要在 DMIT 上 `mkdir`（目录由存储机创建）。CDN/puller `403` 时再 `get_media` + `download` 一次，第二次仍失败则记这条失败。
- token / refresh 仍只在 DMIT。
- 8 路线程保持在 DMIT，每条线程同步等 puller；存储机并发来自 ThreadingHTTPServer。

## 6. 运维

- 新单元：`vpush-ima-puller.service`，UID `99` GID `100`，读 `/etc/vpush/ima-pull.token`。
- 脚本：`app/ima_puller.py` 只依赖标准库，安装到 `/usr/local/lib/vpush-ima/ima-puller.py`。
- DMIT `/opt/vpush/.env`：`IMA_PULL_URL=http://10.80.0.2:8743/pull`、`IMA_PULL_TOKEN=...`（不进 Git）。
- NFS、健康探针、Restic 不变。
- 回滚：去掉 `IMA_PULL_URL` 并重启容器，下载回到 DMIT 写 NFS。

## 7. 风险

- 存储机新出口 IP 可能被 IMA 限速；先保持 8 路，出现 429/51 再降。
- NFS 属性缓存可能让 DMIT 短暂看不到新文件；远程模式 `is_complete` 已不按 NFS `stat` 判断待下载，state 写完即可。
- puller 若被打成开放代理会去任意 URL：必须校验 token + `*.ima.qq.com`。
