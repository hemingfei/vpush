"""大V预估盈亏的行情接入层：名称→代码、远程价格查询、本地缓存。

行情源按 docs/price-query-api.md 契约接入（批量 POST /api/v1/prices，
逐 item 独立成败）。PRICE_API_BASE / PRICE_API_TOKEN 为空即桩模式：
不发起任何网络请求，get_prices 全部未命中——盈亏页显示「行情数据未接入」。
接入真实源时只需填这两个常量，其余链路（缓存/重试/调用方）零改动。

缓存语义（db.kol_price_cache）：
- 历史 (code, at) 永久缓存：上游契约保证同一时刻价不可变；
- 最新价（at=""）TTL 300s：过期重查，避免陈旧现价污染浮动盈亏。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import httpx

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))

# 接入真实行情源时改这里（唯一改动点）。BASE 形如 https://host/api/v1
PRICE_API_BASE = ""
PRICE_API_TOKEN = ""

BATCH_MAX = 50          # 契约：单次批量上限
LATEST_TTL = 300.0      # 最新价缓存 TTL（秒）
_HTTP_TIMEOUT = 8.0


@lru_cache(maxsize=1)
def name_to_symbol() -> dict[str, str]:
    """A 股正式简称 → 交易所前缀代码（如 贵州茅台 → sh600519）。

    基于全市场名单 a_share_names.json 构建（管理员手改的常用表不参与——
    预估持仓的 target_name 一律是正式简称）。重名概率极低，取首个出现；
    北交所代码以 bj 开头，行情源可选支持，查不到走 item error。
    """
    from .stock_universe import _load_payload, _normalize_name

    out: dict[str, str] = {}
    for item in _load_payload().get("items") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        name = _normalize_name(item.get("name") or "")
        if len(code) < 6 or not name:
            continue
        out.setdefault(name, code.lower())
    return out


def resolve_codes(names) -> dict[str, str]:
    """批量名称 → 代码，解析不到的名称不进结果（调用方按缺失处理）。

    键侧与查询侧都走 _normalize_name：词表构建时去了空格/全角字母，
    查询侧只 strip 的话「贵州 茅台」这类带空格的名称永远解析不到。
    """
    table = name_to_symbol()
    from .stock_universe import _normalize_name
    out: dict[str, str] = {}
    for n in names:
        key = _normalize_name(str(n or ""))
        if key and key in table and key not in out:
            out[key] = table[key]
    return out


def _normalize_at(at: str) -> str:
    """occurred_at（YYYY-MM-DD HH:MM[:SS]）→ 契约的 YYYY-MM-DDTHH:MM:SS。"""
    s = str(at or "").strip()
    if not s:
        return ""
    s = s.replace(" ", "T", 1)
    if len(s) == 16:  # 缺秒
        s += ":00"
    return s


def fetch_remote(requests: list[dict]) -> dict[tuple[str, str], dict]:
    """远程批量查价（契约见 docs/price-query-api.md §2.3）。

    requests: [{"code", "at"}]，at="" 表示最新价。
    返回 {(code, at): {"price", "actual_at", "name"}}，仅含成功项；
    网络失败/桩模式返回 {}（调用方把缺失视为查不到，不重试炸接口）。
    """
    if not PRICE_API_BASE or not requests:
        return {}
    out: dict[tuple[str, str], dict] = {}
    with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
        for i in range(0, len(requests), BATCH_MAX):
            chunk = requests[i:i + BATCH_MAX]
            try:
                resp = client.post(
                    f"{PRICE_API_BASE.rstrip('/')}/prices",
                    json={"items": [{"code": r["code"], "at": r["at"]} for r in chunk]},
                    headers={"Authorization": f"Bearer {PRICE_API_TOKEN}"} if PRICE_API_TOKEN else {},
                )
                resp.raise_for_status()
                items = (resp.json() or {}).get("items") or []
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("price fetch failed chunk=%d items: %s", i, exc)
                continue  # 单批失败只影响该批：已缓存项照用，其余按缺失处理
            if len(items) != len(chunk):  # 契约要求一一对齐，防御性丢弃
                logger.warning("price fetch chunk size mismatch: %d != %d", len(items), len(chunk))
                continue
            for req, item in zip(chunk, items):
                if not isinstance(item, dict) or item.get("status") != "ok":
                    continue
                try:
                    price = float(item["price"])
                except (KeyError, TypeError, ValueError):
                    continue
                if price <= 0:
                    continue
                out[(req["code"], req["at"])] = {
                    "price": price,
                    "actual_at": str(item.get("actual_at") or ""),
                    "name": str(item.get("name") or ""),
                }
    return out


def get_prices(db, requests: list[dict]) -> dict[tuple[str, str], dict]:
    """带缓存的批量取价：去重 → 本地缓存 → 未命中批量调远程 → 回填。

    requests: [{"code", "at"}]（at 归一后）。返回 {(code, at): {"price", ...}}，
    只含拿到价格的项——调用方按缺失降级，不抛异常。
    """
    uniq: dict[tuple[str, str], None] = {}
    for r in requests or []:
        key = (str(r.get("code") or ""), _normalize_at(str(r.get("at") or "")))
        if key[0]:
            uniq.setdefault(key, None)
    if not uniq:
        return {}

    now = time.time()
    cached = db.get_kol_price_cache(list(uniq.keys()))
    miss: list[dict] = []
    for key in uniq:
        hit = cached.get(key)
        # 历史价（at 非空）永久有效；最新价（at 为空）TTL 内才算命中
        if hit and (key[1] or now - hit["fetched_ts"] <= LATEST_TTL):
            continue
        miss.append({"code": key[0], "at": key[1]})
    if miss:
        fresh = fetch_remote(miss)
        if fresh:
            db.upsert_kol_price_cache(
                [{"code": k[0], "at": k[1], "price": v["price"], "actual_at": v["actual_at"]}
                 for k, v in fresh.items()]
            )
            cached.update(fresh)
        # 最新价重查失败时丢弃过期缓存行：陈旧现价会污染浮动盈亏，
        # 宁可按「查不到」降级也不回退几小时前的旧值（与整体缺失降级哲学一致）
        for r in miss:
            if not r["at"] and (r["code"], r["at"]) not in fresh:
                cached.pop((r["code"], r["at"]), None)
    return {k: v for k, v in cached.items() if k in uniq}
