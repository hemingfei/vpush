# 交接：雪球 App 身份通道（替换 WAF 解算方案）

> 交接日期：2026-09-23
> 来源：雪球 Android 14.96.3 逆向 + 真机动态验证（完整报告见 `~/Bloomberg/xq/雪球_14.96.3_逆向分析报告.md`）
> 资产位置：`scripts/xq_app/`
> 验收命令：`.venv/bin/python scripts/xq_app/verify.py`

---

## 1. 一句话交接

**V Push 现在抓雪球走的是 WAF 保护路径、依赖手工 cookie + waf-bot 解算；换成 App 身份通道后，两样都不再需要。**

改动核心是两点：**换域名路径**（`xueqiu.com/statuses/*` → `api.xueqiu.com/v4/statuses/*`）+ **换身份**（浏览器匿名 cookie → App 隐式账号 token，可纯脚本自动注册）。

---

## 2. 现状与痛点

| 文件 | 现状 | 痛点 |
|---|---|---|
| `app/fetchers/xueqiu.py:28` | `XUEQIU_TIMELINE_URL = "https://xueqiu.com/statuses/user_timeline.json"` | 走网页路径，命中阿里云 WAF 挑战；靠 `merge_waf_cookie()` 合并 waf-bot 解算出的 cookie |
| `app/fetchers/xueqiu.py:316` | `_refresh_cookie()` 直接抛错 | cookie 失效必须人工到后台更新 |
| `app/fetchers/combination.py:32-36` | `xueqiu.com/cubes/*` 系列接口 | 依赖同一套 cookie；有 `_warm()` 预热 + tads 挑战页处理逻辑 |
| `waf-bot/` | jsdom 解算 `md5__1038` 签名，watchdog 定时刷新 `/data/waf_cookies.json` | 额外进程 + 共享文件 + 定时任务，链路长 |

---

## 3. 核心结论（均已实测）

### 3.1 WAF 按域名+路径分级，App 路径不在覆盖范围内

同一时刻、同一 IP、同一 token 的对照实测：

| 路径 | 形态 | 速率实测 |
|---|---|---|
| `xueqiu.com/statuses/hot/listV2.json` | ⛔ WAF 挑战 | 40 QPS → 20/20 全被挑战 |
| `api.xueqiu.com/v4/statuses/public_timeline_by_category.json` | ✅ 直接给数据 | **201.5 QPS → 120/120 全通** |
| `xueqiu.com/cubes/rebalancing/history.json` | ✅ 直接给数据 | **155.8 QPS → 60/60 全通** |
| `xueqiu.com/cubes/show.json` | ✅ 直接给数据 | — |

App 拉社区数据走的是 `api.xueqiu.com/v4/statuses/*`，不是网页的 `/statuses/*`（真机 `okhttp.log` 实证）。

### 3.2 App 会自动注册「隐式账号」，身份高于网页匿名

App 首启 `POST /uc_passport/provider/oauth/app_anonymous_id`（SM4 加密请求体）自动注册账号。JWT 解码对比：

| token 来源 | JWT `uid` | 组合调仓 | 用户时间线 |
|---|---|---|---|
| **App 隐式账号** | 9073115145 等（真实 uid） | ✅ | ✅ |
| 浏览器 `/hq` 匿名 | **-1** | ❌ `10022` | ❌ `10022` |

**这是现有 `xueqiu.py` 抓不到数据的根因之一** —— 它用的是浏览器匿名 cookie。

### 3.3 token 与 UA 绑定，X-Device-ID 反而不重要

| 组合 | 结果 |
|---|---|
| App token + App UA | ✅ 200 |
| App token + App UA，**不带** X-Device-ID | ✅ 200 |
| App token + **浏览器 UA** | ❌ 400 `400016` |
| 浏览器 token + App UA | ❌ 400 `10022` |

必须成对使用：`User-Agent: Xueqiu Android 14.96.3` + App token。

### 3.4 注册可纯脚本复现，且幂等

加密链逆向自 `com/xueqiu/enc/`：**SM2 密钥对 → `/ee2e/public_key.json` 交换 → ECDH → SM3 派生 SM4 密钥 → SM4/CBC/PKCS7 加密请求体（大写 hex）**。

- 同一 `deviceId` 反复注册 → 返回**同一 uid 与同一 access_token**（幂等）
- 换新 `deviceId` → 得到全新隐式账号
- **结论：token 永不失效，无需人工维护**

---

## 4. 资产清单

| 文件 | 用途 | 依赖 |
|---|---|---|
| `scripts/xq_app/xq_crypto.py` | SM2 曲线运算 + ECDH + SM3/SM4 封装，带自检 | `gmssl` |
| `scripts/xq_app/xq_register.py` | `register(device_id)` → token 全套；`device_id_from_android_id()` 构造设备指纹 | 上面 + `curl_cffi` |
| `scripts/xq_app/xq_client.py` | 抓取客户端：组合排行榜/详情/调仓/净值 + 社区公开流/用户时间线/评论 | 上面两个 |
| `scripts/xq_app/xq_waf.py` | **备用**：WAF 挑战解算器（复用 `waf-bot/solver.js`），仅在 App 通道出问题时启用 | `curl_cffi` + node |
| `scripts/xq_app/verify.py` | 端到端验收（10 项，含反例校验） | 全部 |

**新增依赖**：`gmssl`（需加入 `requirements.txt`；项目现有 `cryptography` 不支持国密）。

> 已装到 `.venv` 供验证使用，`requirements.txt` 未改动，由你决定何时落库。

用法：

```python
from xq_client import XueqiuClient

# 全自动：自动协商 + 注册 + 拿 token
xq = XueqiuClient(auto_register=True)
xq.discover_cubes(count=20)               # 组合排行榜
xq.cube_rebalancing("ZH123456", all_pages=True)   # 调仓历史（自动翻页）
xq.cube_nav("ZH123456")                   # 净值曲线（约 560KB/组合）
xq.public_timeline(count=20)              # 社区公开流
xq.user_timeline(1247347556, count=20)    # 指定用户时间线
```

---

## 5. 集成方案

### 5.1 `app/fetchers/xueqiu.py`（社区动态）

```python
# ① 改域名路径（关键）
XUEQIU_TIMELINE_URL = "https://api.xueqiu.com/v4/statuses/user_timeline.json"

# ② 身份改为 App 隐式账号（替代 DB 里的手工 cookie + merge_waf_cookie）
from scripts.xq_app.xq_register import register, device_id_from_android_id
cred = register(device_id_from_android_id("Xiaomi", ANDROID_ID))  # 幂等，可缓存
cookie = cred["cookie"]          # xq_a_token=...;xq_id_token=...;u=...

# ③ 请求头固定为 App 身份
headers = {
    "User-Agent": "Xueqiu Android 14.96.3",      # 必须与 token 配套
    "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.6,zh;q=0.4",
    "X-Device-ID": device_id,
    "X-Device-OS": "Android 16",
    "X-Device-Model-Name": "OnePlus_PJD110",
}
```

- `_refresh_cookie()` 可以改为**调用 `register()` 重新取 token**，不再需要人工介入（幂等，返回同一账号）
- `merge_waf_cookie()` / `WAF_COOKIE_FILE` 在本路径下**不再需要**（可保留为 fallback）
- `_is_waf_html()` 检测可保留作为防御，但正常情况下不会触发

### 5.2 `app/fetchers/combination.py`（组合调仓）

接口 host 保持不变（`xueqiu.com/cubes/*` 实测无 WAF 挑战），**只需换身份**：

- 把浏览器 cookie 换成 App 隐式账号 token（否则返回 `10022`）
- `_warm()` 预热逻辑在有 App token 后可能不再需要（**已验证**：EdgeOne 未再触发，见 §8）
- `CUBE_NAV_URL` 用的是 `/cubes/nav_daily/all.json`，我实测的是 RN 路径 `/cube/center/cube/v2/navDaily/all.json`（返回 1513 个净值点）；**已验证两者等价**（同一组合同日 `rate`/`unit_nav` 一致，见 §8）

### 5.3 数据源状态监控

现有「数据源稳定性监控」可直接复用 —— 把 `xueqiu_session_dead()` 的判定加上 `10022`/`400016`（现在只判 401/403）。

---

## 6. 验收标准

```bash
.venv/bin/python scripts/xq_app/verify.py
```

预期 10 项全 ✅（已在 2026-09-23 跑通）：

```
✅ SM2 曲线阶 n·G == ∞      ✅ ECDH 对称性           ✅ 公钥编码长度 130
✅ 隐式账号注册（uid != -1）  ✅ 组合排行榜            ✅ 组合调仓历史
✅ 组合净值曲线（1513 点）    ✅ 社区公开流            ✅ 用户时间线
✅ 对照组：浏览器匿名 token 应被拒（10022/400016）
```

集成后再跑一次现有的雪球抓取测试，确认 `xueqiu.py` 不再依赖 `waf_cookies.json`。

---

## 7. 边界与风险

**必须遵守**：

1. **UA 与 token 必须成对**——混用必定失败（`400016` / `10022`）。
2. **不要伪造 `X-Device-ID` 与真实设备不一致**——客户端会把不一致上报到风控日志（`illegal device id`）。虽实测服务端不校验该头，但保持一致性成本为零。
3. **不要打 `/djapi`、`/xqapi`**——这两个前缀命中 SM4 加密白名单，属于账号/交易域。
4. **登录态接口风险高**——本方案用的是**隐式账号**（非用户真实账号）。若要抓需要真实登录的数据（自选、持仓），风控后果会绑定到账号。
5. **限流不是瓶颈，但别浪费**——实测 200 QPS 无限制，建议仍按 1–2 QPS 走，留余量。

**不要做**：

- 不要为了让 App 通道跑通而继续维护 `waf-bot` 的 cookie 文件（App 通道不用它）
- 不要把 `xq_waf.py` 当作主路径（它是解算器，慢：单次 5.7 秒，且与 URL 绑定）

---

## 8. 未验证事项（交给你）

| # | 事项 | 说明 |
|---|---|---|
| 1 | ~~四个 `CUBE_*` 接口~~ ✅ **已验证** | 2026-09-23 晚，App 隐式账号（uid≠-1）下四个全部可用，**无需改 host**：`xueqiu.com/cubes/nav_daily/all.json?cube_symbol=ZH2223199` → 200 application/json，1513 个净值点（首点 `{date:1263196800000, unit_nav:1.0}`），与 RN 路径 `/cube/center/cube/v2/navDaily/all.json` 同日 `rate`/`unit_nav` 逐日一致（仅 `search.json` 少 `symbol`/`stock_name` 两键，不影响抓取）；`cubes/search.json?q=套利` → 200；`cubes/show.json` → 200；`stock.xueqiu.com/v5/stock/quote.json` → 200（该 host 本就不在挑战域） |
| 2 | EdgeOne tads 挑战 ✅ **已验证** | 带 App token 的 `xueqiu.com/cubes/*` 直接返回 JSON，未再出现挑战页；网页 cookie 路径下 `combination.py:292` 的检测/预热仍保留为 fallback |
| 3 | 长周期稳定性 | 隐式账号在数天/数周连续抓取下的表现未观察 |
| 4 | 评论接口 | `xq_client.comments()` 返回 `count` 正确但 `comments: []` 为空，疑似需真实登录或该帖受限，未深究 |
| 5 | 设备指纹池 | 同一 deviceId 可反复注册（幂等）；是否需要多设备指纹轮换用于分散风控，取决于你的抓取强度 |
| 6 | token 长期有效期 | 未观察隐式账号 token 多久过期。已在 `_refresh_cookie()` 接自动重注册（命中 `10022`/`400016`/401/403 时触发，见 `xueqiu_session_dead()`）作兑底 |

---

## 9. 关键事实速查

```
接口 host 分组
  行情      stock.xueqiu.com/v5/*        匿名可抓，无 WAF
  社区      api.xueqiu.com/v4/statuses/* App 路径，无 WAF（需 App token）
  社区(旧)  xueqiu.com/statuses/*        ⛔ WAF 挑战，不要用
  组合      xueqiu.com/cubes/*           无 WAF（需 App token）

身份
  App UA    "Xueqiu Android 14.96.3"
  注册      POST api.xueqiu.com/uc_passport/provider/oauth/app_anonymous_id
  密钥      POST api.xueqiu.com/ee2e/public_key.json
  设备指纹  "1" + 厂商大写(去.) + md5(androidId)

错误码
  10022 / 400016   需要有效 App 身份 token（不是限流）
  400022           加密协商或请求头不完整（缺 Cookie 头 / charset / _t / _s）
  900002           服务端无法解密（SM4 密钥或编码错误）
```
