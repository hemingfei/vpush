#!/usr/bin/env python3
"""IMA list 分页诊断：只读追踪 get_knowledge_list 游标序列，定位 repeated cursor。

用法（生产容器内）：
    docker exec vpush python3 - < scripts/ima_list_probe.py [group_id]

不打印 token/cookie；游标只输出指纹。仅做 list 请求，不写任何数据。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

sys.path.insert(0, "/app")

from app.db import DB  # noqa: E402
from app.ima_documents import ImaDocumentConfig, ImaPureClient, BASE  # noqa: E402

DB_PATH = "/data/dav.db"
MAX_PAGES = 400


def trace_folder(client: ImaPureClient, kb_id: str, folder_id: str) -> None:
    cursor = ""
    seen: set[str] = set()
    page = 0
    total = 0
    started = time.monotonic()
    while True:
        if cursor in seen:
            print(f"    !! REPEATED cursor fp={cursor[:10] or '(empty)'} len={len(cursor)} at page={page}")
            return
        seen.add(cursor)
        body = {"knowledge_base_id": kb_id, "folder_id": folder_id, "limit": "50"}
        if cursor:
            body["cursor"] = cursor
        request = urllib.request.Request(
            BASE + "/knowledge_tab_reader/get_knowledge_list",
            data=json.dumps(body, ensure_ascii=False).encode(),
            method="POST",
            headers=client._headers(client._token()),
        )
        data, _ = client._open_json(request)
        payload = client._payload(data)
        if not isinstance(payload, dict):
            print(f"    !! invalid payload at page={page}")
            return
        page_items = payload.get("knowledge_list") or []
        total += len(page_items)
        page += 1
        next_cursor = str(payload.get("next_cursor") or "")
        print(
            f"    page={page} items={len(page_items)} next_fp={next_cursor[:10] or '(end)'}"
            f" next_len={len(next_cursor)} elapsed={time.monotonic() - started:.1f}s"
        )
        if not next_cursor:
            print(f"    done pages={page} items={total}")
            return
        if next_cursor in seen:
            print(f"    !! REPEATED next_cursor fp={next_cursor[:10]} len={len(next_cursor)} at page={page}")
            return
        cursor = next_cursor
        if page >= MAX_PAGES:
            print(f"    !! 达到 {MAX_PAGES} 页上限，停止")
            return


def main() -> None:
    group_id = sys.argv[1] if len(sys.argv) > 1 else ""
    db = DB(DB_PATH)
    try:
        cfg = ImaDocumentConfig.from_db(db)
        if not cfg.groups:
            print("no groups configured")
            return
        target = next((g for g in cfg.groups if g.id == group_id), None)
        if target is None:
            ids = ", ".join(f"{g.id}({g.name})" for g in cfg.groups)
            print(f"group {group_id or '(空)'} 不在配置中；可用: {ids}")
            return
        client = ImaPureClient(cfg, target)
        folders = client.list_items(
            target.root_folder_id or ";".join(target.mount_folder_ids),
            folders_only=True,
        )
        print(f"group={target.id} name={target.name} mount_folders={len(folders)}")
        for folder in folders[:20]:
            folder_id = str(folder.get("id") or "")
            title = str(folder.get("title") or folder.get("name") or "")[:30]
            print(f"  folder {folder_id} {title}")
            trace_folder(client, target.knowledge_base_id, folder_id)
    finally:
        db.close()


if __name__ == "__main__":
    main()
