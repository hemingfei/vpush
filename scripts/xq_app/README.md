# scripts/xq_app — 雪球 App 身份通道

用雪球 **App 的域名路径 + App 隐式账号 token** 抓数据，绕开 `xueqiu.com/statuses/*` 上的 WAF 挑战。

**接手先读**：[`docs/handoff/2026-09-23-xueqiu-app-identity-channel.md`](../../docs/handoff/2026-09-23-xueqiu-app-identity-channel.md)

## 快速验证

```bash
.venv/bin/pip install gmssl          # 唯一新增依赖
.venv/bin/python scripts/xq_app/verify.py
```

预期 10 项全 ✅。

## 快速使用

```python
import sys; sys.path.insert(0, "scripts/xq_app")
from xq_client import XueqiuClient

xq = XueqiuClient(auto_register=True)     # 自动协商 + 注册 + 拿 token
xq.discover_cubes(count=20)               # 组合排行榜
xq.cube_rebalancing("ZH123456", all_pages=True)   # 调仓历史
xq.cube_nav("ZH123456")                   # 净值曲线
xq.public_timeline(count=20)              # 社区公开流
xq.user_timeline(1247347556, count=20)    # 用户时间线
```

## 文件

| 文件 | 作用 |
|---|---|
| `xq_crypto.py` | SM2 曲线运算 + ECDH + SM3/SM4 封装（纯 Python 曲线运算 + gmssl 对称算法） |
| `xq_register.py` | 隐式账号注册；`register(device_id)` 是唯一对外入口，幂等 |
| `xq_client.py` | 抓取客户端；`auto_register=True` 全程免配置 |
| `xq_waf.py` | **备用**：WAF 挑战解算器（依赖 `waf-bot/solver.js`，单次约 5.7 秒），仅当 App 通道失效时启用 |
| `verify.py` | 端到端验收脚本 |

## 三条硬规则

1. `User-Agent: Xueqiu Android 14.96.3` 与 App token **必须成对使用**，混用必失败。
2. 社区数据必须走 `api.xueqiu.com/v4/statuses/*`，**不要**走 `xueqiu.com/statuses/*`（WAF 保护）。
3. 别碰 `/djapi`、`/xqapi`（SM4 加密白名单，账号/交易域）。
