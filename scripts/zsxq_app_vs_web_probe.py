"""App 通道 vs Web 通道 只读对比探针（本地一次性验证）。

来源配方（逆向 rb/a.java）：
  UA: xiaomiquan/5.27.3 Android/Phone/{RELEASE} {BRAND}_{MODEL}
  X-Request-Id: uuid4()
  X-Version: 2.81.0
  Cookie: zsxq_access_token=...

行为：每组只读 GET topics(count=5) 重复 REPEAT 次，若首个含附件主题则再各试一次
files/{id}/download_url。不入库、不下载附件、不打印 token。
用法：ZSXQ_ACCESS_TOKEN=... GROUP_ID=... .venv/bin/python scripts/zsxq_app_vs_web_probe.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode

import httpx

API_BASE = "https://api.zsxq.com/v2"
GROUP_ID = os.environ.get("GROUP_ID", "28888112822211")
REPEAT = int(os.environ.get("REPEAT", "3"))
DELAY = float(os.environ.get("DELAY", "1.0"))
APP_DEVICE = os.environ.get("APP_DEVICE", "16 OnePlus_PJD110")  # 真机品牌_型号，空格已压

WEB_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
APP_UA = f"xiaomiquan/5.27.3 Android/Phone/{APP_DEVICE.replace(' ', '_')}"


def token() -> str:
    raw = (os.environ.get("ZSXQ_COOKIE") or os.environ.get("ZSXQ_ACCESS_TOKEN") or "").strip()
    for part in raw.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name.strip() == "zsxq_access_token" and value:
            return value
    if raw and "=" not in raw:
        return raw
    raise SystemExit("缺少 ZSXQ_ACCESS_TOKEN")


def headers(flavor: str, tok: str) -> dict[str, str]:
    h = {"Accept": "application/json, text/plain, */*", "Cookie": f"zsxq_access_token={tok}"}
    if flavor == "app":
        h.update(
            {
                "User-Agent": APP_UA,
                "X-Request-Id": str(uuid.uuid4()),
                "X-Version": "2.81.0",
            }
        )
    else:
        h.update(
            {
                "User-Agent": WEB_UA,
                "Origin": "https://wx.zsxq.com",
                "Referer": "https://wx.zsxq.com/",
            }
        )
    return h


def get(client: httpx.Client, path: str, params: dict, flavor: str, tok: str) -> dict:
    url = f"{API_BASE}{path}?{urlencode(params)}"
    r = client.get(url, headers=headers(flavor, tok), timeout=20)
    try:
        data = r.json()
    except ValueError:
        return {"http": r.status_code, "ok": False, "err": "non-json"}
    return {
        "http": r.status_code,
        "succeeded": bool(data.get("succeeded")) if isinstance(data, dict) else None,
        "code": data.get("code") if isinstance(data, dict) else None,
        "info": (data.get("info") or "")[:80] if isinstance(data, dict) else None,
        "resp_keys": sorted(data.get("resp_data", {}).keys()) if isinstance(data, dict) and isinstance(data.get("resp_data"), dict) else None,
    }


def main() -> None:
    tok = token()
    out: dict = {"group_id": GROUP_ID, "app_ua": APP_UA, "results": []}
    with httpx.Client() as client:
        # 找首条含附件的主题（web 通道）
        first_file_id = ""
        for i in range(REPEAT):
            for flavor in ("web", "app"):
                r = get(client, f"/groups/{GROUP_ID}/topics", {"scope": "all", "count": 5}, flavor, tok)
                r["flavor"], r["round"] = flavor, i
                out["results"].append(r)
                if r.get("succeeded"):
                    # 再拿一次 body 找附件 id（仅 web 首轮）
                    url = f"{API_BASE}/groups/{GROUP_ID}/topics?{urlencode({'scope': 'all', 'count': 5})}"
                    resp = client.get(url, headers=headers(flavor, tok), timeout=20).json()
                    topics = (resp.get("resp_data") or {}).get("topics") or []
                    for t in topics:
                        for blk in ("talk", "question", "answer", "task", "solution"):
                            files = (t.get(blk) or {}).get("files") or []
                            if files:
                                first_file_id = str(files[0].get("file_id") or "")
                                break
                        if first_file_id:
                            out["first_file_id"] = first_file_id
                            break
                time.sleep(DELAY)
        # 附件下载 URL：两通道各试一次
        if first_file_id:
            for flavor in ("web", "app"):
                r = get(client, f"/files/{first_file_id}/download_url", {}, flavor, tok)
                r["flavor"], r["round"] = flavor, "file-probe"
                out["results"].append(r)
                time.sleep(DELAY)
    out_path = Path(os.environ["OUT_JSON"]) if os.environ.get("OUT_JSON") else Path(__file__).with_suffix(".json")
    out_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for r in out["results"]:
        print(f"{r['flavor']:>5} r{r['round']}: http={r.get('http')} ok={r.get('succeeded')} "
              f"code={r.get('code')} info={r.get('info')} keys={r.get('resp_keys')}")


if __name__ == "__main__":
    main()