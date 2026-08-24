"""从新浪行情节点刷新 app/resources/a_share_names.json。"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.stock_universe import _normalize_name  # noqa: E402
from app.tagging import is_equity_code, is_equity_name  # noqa: E402

OUT = ROOT / "app" / "resources" / "a_share_names.json"
COUNT_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount"
DATA_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeDataSimple"


def _to_code(symbol: str, code: str) -> str:
    raw = (symbol or "").strip().lower()
    digits = (code or "").strip().zfill(6)
    if raw.startswith("sh"):
        return "SH" + digits
    if raw.startswith("sz"):
        return "SZ" + digits
    if raw.startswith("bj"):
        return "BJ" + digits
    if digits.startswith(("60", "68")):
        return "SH" + digits
    if digits.startswith(("4", "8", "9")):
        return "BJ" + digits
    return "SZ" + digits


def main() -> int:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://vip.stock.finance.sina.com.cn/",
    }
    with httpx.Client(headers=headers, timeout=20) as client:
        count_text = client.get(COUNT_URL, params={"node": "hs_a"}).text
        match = re.search(r"\d+", count_text or "")
        total = int(match.group(0)) if match else 0
        rows: list[dict] = []
        page = 1
        while total and len(rows) < total:
            resp = client.get(
                DATA_URL,
                params={"page": page, "num": 80, "sort": "symbol", "asc": 1, "node": "hs_a"},
            )
            resp.raise_for_status()
            chunk = resp.json()
            if not isinstance(chunk, list) or not chunk:
                break
            rows.extend(chunk)
            page += 1
            time.sleep(0.05)

    items = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        name = _normalize_name(row.get("name") or "")
        code = _to_code(str(row.get("symbol") or ""), str(row.get("code") or ""))
        if not name or not is_equity_code(code) or not is_equity_name(name):
            continue
        key = (name, code)
        if key in seen:
            continue
        seen.add(key)
        items.append({"code": code, "name": name})
    OUT.write_text(
        json.dumps(
            {"updated": date.today().isoformat(), "source": "sina.hs_a", "items": items},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(items)} names → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
