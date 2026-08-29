#!/usr/bin/env python3
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("VPUSH_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.environ.get("VPUSH_TOKEN", "")
if not TOKEN:
    sys.stderr.write("VPUSH_TOKEN is required\n")
    raise SystemExit(2)
HEADERS = {"Authorization": "Bearer " + TOKEN}


def fetch_json(route: str):
    request = urllib.request.Request(BASE + route, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


catalog = fetch_json("/api/ima-documents/catalog")
subscribed = catalog.get("subscribed") or []
group_id = str(subscribed[0].get("id") or "") if subscribed else ""
ROUTES = [
    "/api/ima-documents/catalog",
    "/api/ima-documents?limit=50&offset=0",
    "/api/ima-documents?q=新能源&limit=50&offset=0",
    "/api/ima-documents?q=AI&limit=50&offset=0",
]
if group_id:
    ROUTES.append("/api/ima-documents?" + urllib.parse.urlencode({
        "group": group_id, "limit": 50, "offset": 0,
    }))

for route in ROUTES:
    samples = []
    for _ in range(20):
        started = time.perf_counter()
        fetch_json(route)
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    print(
        f"{route} min={min(samples):.1f} "
        f"median={statistics.median(samples):.1f} "
        f"p95={p95:.1f} max={max(samples):.1f} ms"
    )
