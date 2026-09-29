# MX 平台半自动换 TOKEN 脚本

> `python scripts/mx_login.py` —— 拉验证码 → 人工/OCR 输码 → 登录 → 写回 vpush。
> 取代旧流程「浏览器登录 → F12 抠 token → 后台手粘」，把每次换 token 的成本
> 从几分钟降到约 15 秒（输一次验证码）。
>
> 协议事实来自 2026-09-02 官方网页端抓包（`mx-官方网页端抓包核对-2026-09-02.md`）
> 与 2026-09-29 前端 bundle 静态分析（见下文第四节）。

## 一、为什么是「半自动」

- **图形验证码是唯一硬卡点**：登录必须过 `GET /master-api/api/code` 的图形
  验证码，没有可靠的免人方案（OCR 有失败率，连续登录失败本身是风控信号）。
- **2 天轮换是防风控卫生要求，不是平台强制过期**（`mx-防风控优化措施.md`），
  本就该保持人工低频触发，**不做无人值守自动定时登录**。
- 凭据只从根目录 `.env` 读（`MX_ACCOUNT` / `MX_PASSWORD`），源码、日志、文档
  不落任何凭据；AI 代理不经手密码——与 `mx-定期抓包巡检手册.md` 的
  「登录必须由账号持有人完成、AI 不接触凭据」口径一致（脚本代替人输密码，
  AI 只看到验证码与脱敏 token）。

## 二、用法

```bash
# 常规（交互输验证码；--write auto：有 VPUSH_URL 走 api，否则 print）
python scripts/mx_login.py

# ddddocr 自动识别（可选依赖：pip install ddddocr）。注意：平台实测（2026-09-29）
# 下发 SVG 矢量验证码（路径绘制、防 OCR），ddddocr 不能直接吃 SVG——--ocr 需先
# 栅格化，当前以人工输码 / 两段式为主
python scripts/mx_login.py --ocr

# 平台换登录域名时指定 origin（默认取 config api_base 的域名）
python scripts/mx_login.py --origin https://mx.2026.foodtop1.com

# 两段式（外部识码/无交互终端；第一步不需要账密）
python scripts/mx_login.py --show-captcha                     # 出图 + captcha-key
python scripts/mx_login.py --captcha-key <key> --code <答案>   # 用该答案直接登录
```

环境变量（`.env`，参考 `.env.example`）：

| 键 | 用途 |
|---|---|
| `MX_ACCOUNT` / `MX_PASSWORD` | MX 平台账密（必填） |
| `MX_LOGIN_ORIGIN` | 登录域名覆盖 |
| `VPUSH_URL` / `VPUSH_ADMIN_USER` / `VPUSH_ADMIN_PASSWORD` | `--write api` 推送凭据 |

## 三、写回三模式

| 模式 | 行为 | 适用 |
|---|---|---|
| `api`（auto 默认尝试） | `POST /api/auth/login` + `PUT /api/admin/sources/mx`——与后台手粘**完全同一条热应用链路**（触发 `on_mx_config_changed` 重建抓取器/重启 WS）；`--no-hot-apply` 时 body 带 `hot_apply=false` 只保存不热应用，由调用方重启容器生效 | 生产开了 Turnstile 时会被 403，回落 print |
| `config` | 直写本机 `config.yaml` + DB `mx_token_updated_at` | 与服务同机且不便走 API；**不热应用**，需重启或后台点「登录」 |
| `print` | 打印完整 token（Windows 顺带复制剪贴板） | 兜底，手粘后台 |

## 四、登录协议事实（2026-09-29 前端 bundle 静态分析）

- `GET {origin}/master-api/api/code?tt=<ms>`：query 只带 `tt`（登录前无 token
  参数）；响应 `data` 密文解密后 `{code, captcha, key}`，`captcha` 为
  `data:image` base64（官方直接塞 `<img src>`），`key` 绑定该张验证码。
- `POST {origin}/master-api/api/login`：body 明文
  `{user, password, code_key, code, device:"web-browser", ad:true, h5:true, tt}`；
  响应 `data` 解密后 `{code, token, info, hosturl}`，`code===200` 且有 `token`
  即成功；**`hosturl` 为平台动态下发的业务接口域，官方登录后会切换**。
- 头形态与 `client.py` 一致（`ad`/`i`/`version` 常量头、XHR 差异项、
  curl_cffi chrome146 impersonate）；登录前 `token` 头为空串（官方 fetch 一致）。
- **域名轮转**：2026-09-29 实测根域 `mx.2026.naaifu.cn` 已变为跳转页，指向
  `mx.2026.foodtop1.com`。脚本登录后用官方冷启动的 `user/info` 只读探针验证
  新 token 在当前 `api_base` 是否可用；不可用时按 `hosturl` / 登录域名探测
  切换 `api_base`/`ws_url`（保持 `/business-api/5` 后缀），并随写回一并下发。

## 五、实现与测试

- 核心：`app/fetchers/mx/login.py`（`fetch_captcha` / `classify_captcha` /
  `rasterize_svg` / `login`，`MXLoginError` 只带平台 msg，绝不拼接请求体）。
- CLI：`scripts/mx_login.py`（`run_login_flow` 重试循环、探针与切换、三模式写回）。
- 测试：`tests/test_mx_login_script.py`——协议字段逐项断言、密码不进任何
  输出/异常文本、写回 body 只含 token（及探针触发的 api_base/ws_url）、
  Turnstile 403 提示、两段式两条命令。

## 六、无人值守（Jenkins 定时 + AI 视觉识码）

架构：Jenkins 定时触发（每 2 天）→ `docker run python:3.12-slim` 内
`pip install -r requirements.txt` → `python scripts/mx_login.py --ai-ocr
--no-hot-apply --origin https://mx.2026.foodtop1.com` → SVG 验证码经 resvg-py
栅格化 → 视觉模型（OpenAI 兼容，`MX_VISION_*` 三键，须具备视觉能力）识码 →
登录 → 探针校验 → `VPUSH_URL` 管理 API 自动写回（`--no-hot-apply`：只保存
不热应用）→ 写回成功后流水线在宿主机 `docker restart vpush` 冷启动生效。
失败（识码连续错/接口异常）退出码非 0，Jenkins 标红；配了
`BARK_*`/`FEISHU_WEBHOOK_URL` 时脚本还会直接推告警（webhook 走
`app.url_safety` 安全体，仅公网地址）。

**写回后重启而非热应用（2026-09-29 起）**：无人值守写回带 `hot_apply=false`
（端点默认热应用，仅脚本显式关闭）——vpush 只保存新 token，随后流水线在
宿主机 `docker restart vpush`（容器名以 `docker ps` 为准）冷启动生效。
重启落在工作日 08:00-22:00 且 TOKEN 未超 49h 时效门槛时，窗口循环 30s 内
自动补登一次（官方冷启动序列 + 新 token）；周末/超龄则等下个运行时段。
若重启步骤失败：新 token 已落盘但运行中的服务仍持旧 token（内存态），
下次服务重启生效；急用可到后台重存一次配置立即热应用，或手动「登录」。

凭据全部放 Jenkins 凭据库（Secret Text），仓库与聊天不落任何凭据：
`mx-account`、`mx-password`、`mx-vision-api-base`、`mx-vision-api-key`、
`mx-vision-model`、`vpush-url`、`vpush-admin-user`、`vpush-admin-password`、
`mx-notify-webhook-url`、`mx-notify-webhook-secret`。

**结果回调**：脚本自身在成功（token 写回完成）与失败（登录熔断/写回失败）时
回调 vpush 的 KOL webhook（`MX_NOTIFY_WEBHOOK_URL`/`_SECRET`，飞书同款签名
`sign = base64(hmac_sha256(key="{ts}\n{secret}))`，走 url_safety 安全体）——
Jenkins 凭据注入后即推到订阅了该 KOL 的手机。未配置时失败回落 Bark/飞书。
容器拉起/pip 安装等脚本外的基础设施级失败不触发回调，由 Jenkins 标红兜底。

防风控口径与风险边界：

- 每 2 天一次的低频轮换与人工节奏一致；识码错误自动换码重试，上限
  `--attempts`（默认 3），不做无限重试——连续登录失败本身是风控信号；
- 视觉模型有误读率（实测约一成），单次失败属正常，靠重试与告警兜底；
- 登录请求与现网同一 Chrome impersonate 人格与头形态（见第四节）。

基础设施现状（2026-09-29 搭建，jenkins.hegame.tech）：任务 `vpush-mx-token`
照本 Jenkins 家规实现——流水线内 `ssh root@172.22.0.1` 到宿主机，curl 拉
仓库 tarball 后 `docker run python:3.12-slim` 执行；随「写回后重启」口径，
任务需同步两处：脚本命令追加 `--no-hot-apply`，`docker run` 退出码 0 后
同一 ssh 会话追加 `docker restart vpush`（重启失败跟随该 stage 标红，
token 已落盘不丢）。凭据由 Jenkins
credentials() 注入、经 stdin 写宿主机临时 env-file 交给
`docker run --env-file`（不落在进程命令行），跑完即删。**不要**在流水线
environment 块里覆写 PATH 指向 /var/jenkins_home/bin 再直接调 docker——
实测该写法会导致构建启动即消亡（nextBuildNumber 递增但无构建目录）。
定时 `30 8 1,3,5,...,29 * *`（隔天 8:30 固定触发）+ 流水线首阶段
**真随机延迟 0–30 分钟**（`/dev/urandom` 取秒数，每次执行点都不同，实际落在
8:30–9:00 窗口内）；手动「立即构建」自动跳过延迟（按构建原因识别
TimerTrigger）。总超时 40 分钟容纳 sleep。构建保留 30 次。8 个 Secret Text
凭据：mx-account / mx-password / mx-vision-api-{base,key} / mx-vision-model /
vpush-{url,admin-user,admin-password}。
