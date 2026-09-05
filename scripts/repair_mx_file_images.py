#!/usr/bin/env python3
"""修复 MX 平台历史坏数据：file 图片消息被旧代码存成原始 JSON 正文。

旧版 MX 解析器不认识 type=file 的消息段（即使是 .png 图片链接），正文解析为空时
还会把原始 msg JSON 整段当正文入库。这些行已按 external_id 入库去重，轮询不会
重新解析，只能离线修复。

本脚本用当前解析逻辑重解每条 MX 消息（优先取 detail 里的原始 msg；没有 detail
时识别 content 本身就是 msg JSON 数组的行），与库中原值比较：
  - 解析结果与原值一致 → 不动；
  - 正文或图片有差异 → 更新 content 与 images（图片走本地缓存，幂等）；
  - 重解后既无正文也无图片 → 新代码本不会入库这类消息，--drop-empty 时删除。

用法：python scripts/repair_mx_file_images.py [db_path] [--drop-empty] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.fetchers.mx.fetcher import MxFetcher


def typed_msg_parts(text):
    """msg 字符串若为「消息数组」形态（list[dict 且带 type]）则返回该列表，否则 None。"""
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(parsed, list) and parsed and all(isinstance(i, dict) and "type" in i for i in parsed):
        return parsed
    return None


def resolve_msg_str(row):
    """找出该行应重解的 msg 字符串；没有可重解的消息数组时返回 None。"""
    try:
        detail = json.loads(row["detail"]) if row["detail"] else None
    except json.JSONDecodeError:
        detail = None
    if isinstance(detail, dict):
        msg = detail.get("msg") or detail.get("message") or ""
        if typed_msg_parts(msg) is not None:
            return msg
    # detail 缺失或不是消息数组：content 可能就是旧代码兜底存的原始 msg/整包 JSON
    if typed_msg_parts(row["content"]) is not None:
        return row["content"]
    try:
        parsed = json.loads(row["content"])
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        msg = parsed.get("msg") or parsed.get("message") or ""
        if typed_msg_parts(msg) is not None:
            return msg
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="修复 MX file 图片消息的历史坏数据")
    ap.add_argument("db", nargs="?", default="data/dav.db", help="SQLite 数据库路径")
    ap.add_argument("--drop-empty", action="store_true", help="删除重解后既无正文也无图片的行")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = ap.parse_args()

    db_path = str(Path(args.db).resolve())
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    # 只用 DB 路径做图片本地缓存（cache_image_file 只读 db.path），不触碰应用层连接
    fetcher = MxFetcher(
        SimpleNamespace(api_base="", token="", page_size=50, max_history_pages=1, ws_enabled=False),
        SimpleNamespace(path=db_path),
    )

    rows = conn.execute(
        "SELECT id, external_id, content, images, detail FROM posts WHERE platform='mx' ORDER BY id"
    ).fetchall()

    updated = dropped = 0
    for row in rows:
        msg_str = resolve_msg_str(row)
        if msg_str is None:
            continue
        content, images, _files = fetcher._parse_msg_content(msg_str)
        old_images = json.loads(row["images"]) if row["images"] else []
        if row["content"] == content and old_images == images:
            continue
        if not content and not images:
            # 旧代码兜底存进来的纯垃圾 JSON，新代码本不会入库
            print(f"  [空] id={row['id']} external_id={row['external_id']} 重解后无正文无图片")
            if args.drop_empty and not args.dry_run:
                conn.execute("DELETE FROM posts WHERE id=?", (row["id"],))
            dropped += 1
            continue
        print(f"  [修] id={row['id']} external_id={row['external_id']}")
        print(f"      旧 content: {row['content'][:80]!r}")
        print(f"      新 content: {content[:80]!r}  images: {images}")
        if not args.dry_run:
            conn.execute(
                "UPDATE posts SET content=?, images=? WHERE id=?",
                (content, json.dumps(images, ensure_ascii=False) if images else "", row["id"]),
            )
        updated += 1

    if not args.dry_run:
        conn.commit()
    conn.close()
    print(f"\n扫描 {len(rows)} 条 MX 帖子：修复 {updated} 条，"
          f"{'删除 ' + str(dropped) + ' 条' if args.drop_empty else '空内容待删 ' + str(dropped) + ' 条（--drop-empty 删除）'}"
          + ("（dry-run 未写库）" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
