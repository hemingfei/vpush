#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雪球数据抓取客户端：社区 + 组合调仓

【核心机制（2026-09-22 实测）】

雪球对同一份数据在不同域名/路径上的防护等级完全不同：

    xueqiu.com/statuses/hot/listV2.json   → WAF 挑战（网页路径，40 QPS 全被拦）
    api.xueqiu.com/v4/statuses/...        → 直接给数据（App 路径，201 QPS 全通）

更关键的是「隐式账号」：App 首次启动会 POST /uc_passport/provider/oauth/app_anonymous_id
（请求体 SM4 加密）自动注册一个 uid != -1 的隐式账号，用它签发的 token 可以访问
网页匿名（uid=-1）访问不了的数据：

    token 来源            JWT uid          组合调仓   社区时间线
    App 隐式账号          9073115145(示例)  ✅          ✅
    浏览器 /hq 匿名       -1                ❌ 10022    ❌

且 **token 与 UA 绑定**：App token 必须配 App UA，浏览器 token 配 App UA 同样被拒。

【如何拿到 App token】
    adb logcat -s OkHttp:V      # App 启动即打印 Cookie 头（release 包日志未关）
    → 取 xq_a_token / xq_id_token / u 三项

用法：
    xq = XueqiuClient(app_token=open("app_cookie.txt").read().strip())
    for rb in xq.cube_rebalancing("ZH123456", all_pages=True):
        print(rb["created_at"], [c["stock_name"] for c in rb["changes"]])
"""
from __future__ import annotations

import json
import time
from typing import Any

from curl_cffi import requests

APP_UA = "Xueqiu Android 14.96.3"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

API_HOST = "https://api.xueqiu.com"
WEB_HOST = "https://xueqiu.com"

DEFAULT_GAP = 0.3


def parse_cookie(raw: str) -> dict:
    return {k: v for k, v in (p.strip().split("=", 1) for p in raw.split(";") if "=" in p)}


class XueqiuClient:
    """默认走 App 身份（App UA + App token）——这是唯一能拿到组合调仓与社区数据的姿势。"""

    def __init__(self, app_token: str | dict | None = None,
                 device_id: str | None = None,
                 auto_register: bool = False,
                 gap: float = DEFAULT_GAP, verbose: bool = False):
        self.gap = gap
        self.verbose = verbose
        self.session = requests.Session(impersonate="chrome")
        self.session.headers.update({
            "User-Agent": APP_UA,
            "Accept-Language": "en-US,en;q=0.8,zh-CN;q=0.6,zh;q=0.4",
        })
        if device_id:
            self.session.headers["X-Device-ID"] = device_id
        self.credential: dict | None = None
        self.has_app_identity = False

        # 无 token 时可就地注册一个隐式账号（纯脚本，零真机依赖）
        if not app_token and auto_register:
            try:
                from .xq_register import device_id_from_android_id, register
            except ImportError:
                from xq_register import device_id_from_android_id, register
            import hashlib
            dev = device_id or device_id_from_android_id(
                "Xiaomi", hashlib.md5(b"xq-auto").hexdigest()[:16])
            self.session.headers["X-Device-ID"] = dev
            self.credential = register(dev, verbose=verbose)
            app_token = self.credential["cookie"]
            self._log(f"已注册隐式账号 uid={self.credential['uid']}")

        if app_token:
            self.session.cookies.update(app_token if isinstance(app_token, dict) else parse_cookie(app_token))
            self.has_app_identity = True

    # ---------- 会话 ----------

    def bootstrap_anonymous(self) -> None:
        """浏览器式匿名 token（uid=-1）。仅够访问行情等公开接口，拿不到组合/社区。"""
        self.session.get(
            "https://xueqiu.com/hq",
            headers={"User-Agent": BROWSER_UA,
                     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
            timeout=25, allow_redirects=True)
        self._log(f"匿名 cookies: {[c.name for c in self.session.cookies.jar]}")

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[xq] {msg}", flush=True)

    def _get(self, path: str, params: dict | None = None, host: str = API_HOST) -> Any:
        time.sleep(self.gap)
        r = self.session.get(f"{host}{path}", params=params, timeout=25)
        if "renderData" in r.text:
            raise RuntimeError(f"命中 WAF 挑战（路径选择有误）: {host}{path}")
        try:
            return r.json()
        except ValueError:
            r.raise_for_status()
            return r.text

    @staticmethod
    def _err(data: Any) -> str | None:
        if isinstance(data, dict):
            code = data.get("error_code") or data.get("resultCode")
            if code in ("10022", "400016", 10022, 400016):
                return f"需要 App 身份的 token（{code}），当前可能是浏览器匿名 token"
        return None

    # ---------- 组合 ----------

    def discover_cubes(self, category: int = 12, market: str = "cn",
                       profit: str = "monthly_gain", sort: str = "best_benefit",
                       count: int = 20, page: int = 1) -> list[dict]:
        """组合排行榜。profit: monthly_gain/daily_gain/annualized_gain_rate；sort: best_benefit/grow_fast/win_market"""
        d = self._get("/cubes/discover/rank/cube/list.json",
                      {"category": category, "market": market, "profit": profit,
                       "sort": sort, "count": count, "page": page}, host=WEB_HOST)
        if (e := self._err(d)):
            self._log(e)
        return d.get("list", []) if isinstance(d, dict) else []

    def discover_recommended(self, recommend_type: int = 1, count: int = 20) -> list[dict]:
        """推荐位：1今日热门 2省心组合 3短线王 4回撤小 5刚调仓"""
        d = self._get("/cubes/discover/rank/cube/list.json",
                      {"category": 14, "recommend_type": recommend_type,
                       "count": count, "page": 1}, host=WEB_HOST)
        return d.get("list", []) if isinstance(d, dict) else []

    def cube_detail(self, symbol: str) -> dict:
        return self._get("/cubes/show.json", {"symbol": symbol}, host=WEB_HOST)

    def cube_nav(self, symbol: str) -> Any:
        """净值历史（单次约 560 KB）。"""
        return self._get("/cube/center/cube/v2/navDaily/all.json",
                         {"cube_symbol": symbol}, host=WEB_HOST)

    def cube_rebalancing(self, symbol: str, page: int = 1, count: int = 20,
                         all_pages: bool = False, max_pages: int = 100) -> list[dict]:
        """调仓历史（扁平化）。all_pages=True 自动翻页。"""
        out: list[dict] = []
        total = None
        while page <= (max_pages if all_pages else page):
            d = self._get("/cubes/rebalancing/history.json",
                          {"cube_symbol": symbol, "page": page, "count": count}, host=WEB_HOST)
            if (e := self._err(d)):
                raise PermissionError(f"{symbol}: {e}")
            rows = d.get("list", []) if isinstance(d, dict) else []
            total = d.get("totalCount", 0) if isinstance(d, dict) else 0
            out.extend(self._flatten(r, symbol) for r in rows)
            if not all_pages or not rows or (total and page * count >= total):
                break
            page += 1
        return out

    @staticmethod
    def _flatten(row: dict, symbol: str) -> dict:
        return {
            "cube_symbol": symbol,
            "rebalancing_id": row.get("id"),
            "created_at": row.get("created_at"),
            "status": row.get("status"),
            "cash": row.get("cash"),
            "new_buy_count": row.get("new_buy_count"),
            "changes": [{
                "stock_name": h.get("stock_name"),
                "stock_symbol": h.get("stock_symbol"),
                "prev_weight": h.get("prev_weight"),
                "weight": h.get("weight"),
                "target_weight": h.get("target_weight"),
                "price": h.get("price"),
                "proactive": h.get("proactive"),
            } for h in (row.get("rebalancing_histories") or [])],
        }

    # ---------- 社区 ----------

    def public_timeline(self, category: int = -1, count: int = 20,
                        since_id: int = -1, max_id: int = -1) -> list[dict]:
        d = self._get("/v4/statuses/public_timeline_by_category.json",
                      {"since_id": since_id, "max_id": max_id, "count": count, "category": category})
        rows = d.get("list", []) if isinstance(d, dict) else []
        return [self._unwrap(r) for r in rows]

    def user_timeline(self, user_id: int | str, page: int = 1, count: int = 20) -> list[dict]:
        d = self._get("/v4/statuses/user_timeline.json",
                      {"user_id": user_id, "page": page, "count": count})
        rows = d.get("statuses", []) if isinstance(d, dict) else []
        return [self._unwrap(r) for r in rows]

    def comments(self, status_id: int | str, count: int = 20, page: int = 1) -> dict:
        return self._get("/statuses/comments.json", {"id": status_id, "count": count, "page": page})

    @staticmethod
    def _unwrap(row: dict) -> dict:
        inner = row.get("data")
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except ValueError:
                inner = None
        if isinstance(inner, dict):
            inner.setdefault("id", row.get("id"))
            return inner
        return row


if __name__ == "__main__":
    import os
    tok = os.environ.get("XQ_APP_TOKEN") or (open("real_cookie.txt").read().strip()
                                            if os.path.exists("real_cookie.txt") else None)
    xq = XueqiuClient(app_token=tok, verbose=True, auto_register=not tok)
    print(f"App 身份: {xq.has_app_identity}\n")

    cubes = xq.discover_cubes(count=5)
    print("=== 组合排行榜 ===")
    for c in cubes:
        print(f"  {c.get('symbol')}  {c.get('name')[:16]:18s} 净值={c.get('net_value')} 月收益={c.get('monthly_gain')}%")

    if cubes:
        sym = cubes[0]["symbol"]
        print(f"\n=== {sym} 调仓历史 ===")
        for rb in xq.cube_rebalancing(sym, count=5):
            print(f"  [ts {rb['created_at']}] {rb['status']} 变更 {len(rb['changes'])} 项")
            for ch in rb["changes"][:3]:
                print(f"      {ch['stock_name']}({ch['stock_symbol']}) "
                      f"{ch['prev_weight']}% → {ch['weight']}% @ {ch['price']}")

    print("\n=== 社区公开流 ===")
    for s in xq.public_timeline(count=3):
        u = (s.get("user") or {}).get("screen_name", "?")
        txt = str(s.get("title") or s.get("text") or "")[:60].replace("\n", " ")
        print(f"  {u}: {txt}")
