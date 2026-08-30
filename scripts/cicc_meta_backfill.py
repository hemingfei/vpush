#!/usr/bin/env python3
"""中金元数据回填 + 品类库归并（幂等）。

步骤：
0) 把历史 11 个品类库 local/cicc-* 归并进单库 local/cicc-research/<品类名>/<MMDD>/，
   写「中金点睛」标记文件（已归并则无操作）；
1) 只调列表 API（不占下载配额）按年度窗口分页，把官方摘要/标签落成单库 sidecar
   .vpush-local-meta.jsonl，匹配 `*_<id>.pdf`。

用法（存储 VPS）：python3 -u cicc_meta_backfill.py [--since 2026-01-01]
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://www.research.cicc.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
LOCAL = Path("/srv/vpush-ima/local")
SLUG, LIB_NAME = "cicc-research", "中金点睛"
# 历史 slug → 品类目录名（网页原名）；未知 slug 回退读旧标记文件的 name
LEGACY = {
    "cicc-macro": "宏观经济", "cicc-strategy": "市场策略", "cicc-global": "全球研究",
    "cicc-industry": "行业研究", "cicc-company": "公司研究", "cicc-quant-esg": "量化及ESG",
    "cicc-commodity": "大宗商品", "cicc-fx": "外汇研究", "cicc-bond": "固定收益",
    "cicc-institute": "中金研究院", "cicc-other": "其他",
}
BODY = {"input": "", "searchField": "titleSeg", "analyst": {"value": "", "name": ""},
        "author": [], "pubTimeStart": None, "pubTimeEnd": None,
        "stock": {"value": "", "name": ""}, "portalCategoryId": "",
        "subPortalCategoryId": {}, "industriesIds": "", "subIndustriesIds": {},
        "reportNumCode": "", "level": [""], "levelChange": [""], "cusPageRange": "",
        "currencyIds": "", "commodityType": "", "page": 1, "size": 50,
        "authorId": "", "secCode": "", "minPageCount": "", "maxPageCount": ""}


def x_time() -> str:
    u = int(time.time() * 1000) // 10
    return str(u) + str(u % 97).zfill(2)


def request(cookie: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(BASE + path, method="POST" if body is not None else "GET")
    for k, v in [("User-Agent", UA), ("Cookie", cookie), ("X-Time", x_time()),
                 ("Referer", BASE + "/zh_CN/reportList"), ("Origin", BASE)]:
        req.add_header(k, v)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=data, timeout=60) as resp:
        obj = json.loads(resp.read())
    if obj.get("code") != 0:
        sys.exit(f"API code={obj.get('code')} msg={obj.get('msg')}")
    return obj["data"]


def fix_owner(path: Path, *, dirs: bool = False) -> None:
    if os.geteuid() != 0:
        return
    os.chown(path, 99, 100)
    os.chmod(path, 0o750 if dirs else 0o640)


def merge_legacy() -> int:
    """把 local/cicc-* 移入 local/cicc-research/<品类>/<MMDD>/，返回移动的 PDF 数。"""
    target = LOCAL / SLUG
    target.mkdir(parents=True, exist_ok=True)
    fix_owner(target, dirs=True)
    marker = target / ".vpush-local-library.json"
    if not marker.exists():
        marker.write_text(json.dumps(
            {"name": LIB_NAME, "enabled": False, "tags": ["中金研报"]},
            ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        fix_owner(marker)
    moved = 0
    for d in sorted(LOCAL.glob("cicc-*")):
        if not d.is_dir() or d.name == SLUG:
            continue
        cat = LEGACY.get(d.name)
        m = d / ".vpush-local-library.json"
        if not cat and m.exists():
            try:
                cat = json.loads(m.read_text(encoding="utf-8")).get("name")
            except (json.JSONDecodeError, OSError):
                pass
        cat = cat or d.name
        for pdf in d.rglob("*.pdf"):
            dst = target / cat / pdf.relative_to(d)
            dst.parent.mkdir(parents=True, exist_ok=True)
            fix_owner(dst.parent, dirs=True)
            os.replace(pdf, dst)  # 同一文件系统，原子
            moved += 1
        old_sidecar = d / ".vpush-local-meta.jsonl"
        if old_sidecar.exists() and not (target / ".vpush-local-meta.jsonl").exists():
            os.replace(old_sidecar, target / ".vpush-local-meta.jsonl")
        if m.exists():
            m.unlink()
        for dirpath, _, _ in sorted(os.walk(d, topdown=False), reverse=True):
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                print(f"WARN {d} 非空残留，未删除", file=sys.stderr)
        print(f"[归并] {d.name} -> {target / cat}（{moved} 累计）")
    return moved


def load_sidecar(path: Path) -> dict:
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                    rows[row["id"]] = row
                except json.JSONDecodeError:
                    pass
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-01-01")
    ap.add_argument("--cookie-file", default="/root/cicc/cookies.txt")
    args = ap.parse_args()
    cookie = Path(args.cookie_file).read_text(encoding="utf-8").strip()

    moved = merge_legacy()
    lib = LOCAL / SLUG
    sidecar = lib / ".vpush-local-meta.jsonl"
    rows = load_sidecar(sidecar)

    param = request(cookie, "/reports/api/v3/param")
    id_name = {}
    for node in param["treeData"] + param["industriesData"]:
        id_name[node["id"]] = node["name"]
        for ch in node.get("children") or []:
            id_name[ch["id"]] = ch["name"]

    for cat in param["treeData"]:
        page, seen = 1, 0
        while True:
            body = dict(BODY, portalCategoryId=str(cat["id"]), pubTimeStart=args.since, page=page)
            data = request(cookie, "/reports/api/v3/page", body)
            items = data.get("content") or []
            if not items:
                break
            for it in items:
                tags = []
                for t in [it.get("reportType")] + list(it.get("documentLabels") or []):
                    if t and t not in tags:
                        tags.append(t)
                for pid in it.get("portalCategoryIds") or []:
                    n = id_name.get(pid)
                    if n and n not in tags:
                        tags.append(n)
                day = (it.get("publishTime") or "")[:10]
                rows[str(it["id"])] = {
                    "id": str(it["id"]),
                    "title": it["title"],
                    "summary": (it.get("summary") or "")[:2000],
                    "tags": tags[:5],
                    "day": day.replace("-", "")[4:] if len(day) >= 10 else "unknown",
                    # 真实发布日期（YYYY-MM-DD）：扫描器读成 pub_date，作跨年排序键
                    "publish": day if len(day) >= 10 else "",
                    "authors": " ".join(a["name"] for a in it.get("analysts") or []),
                }
                seen += 1
            if len(items) < 50:
                break
            page += 1
            time.sleep(1.0)
        print(f"[{cat['name']}] 列表 {seen} 篇")
        time.sleep(0.5)

    tmp = lib / ".vpush-local-meta.jsonl.tmp"
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()),
                   encoding="utf-8")
    os.replace(tmp, sidecar)
    fix_owner(sidecar)
    print(f"归并移动 {moved} 个 PDF；sidecar 共 {len(rows)} 条 -> {sidecar}")


if __name__ == "__main__":
    main()
