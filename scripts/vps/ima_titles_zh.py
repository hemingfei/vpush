#!/usr/bin/env python3
"""把「全球顶级投行研报库」英文文件名译成中文展示名，写入 titles.json 并回写读索引。

只处理 sort_date >= 2026-07-01、标题尚无汉字的条目；已在 titles.json 里的跳过。
用法（容器内）：
  python3 ima_titles_zh.py --limit 5
  python3 ima_titles_zh.py --workers 8
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

CJK = re.compile(r"[\u4e00-\u9fff]")
GROUP_ID = "7479082602225992"
MIN_SORT = "2026-07-01"
BATCH = 12

PROMPT = """把投行研报英文文件名译成中文展示名。规则：
1. 券商用中文（高盛/野村/摩根士丹利/摩根大通/瑞银/德意志银行/伯恩斯坦/花旗/美银证券/汇丰/麦格理等）
2. 保留股票代码括号，如（300274）（0700.HK）（AFXG.DE）
3. 保留末尾日期后缀 -YYMMDD.pdf（没有则加 .pdf）
4. 格式：券商-公司（代码）中文标题-YYMMDD.pdf
5. 只输出 JSON 字符串数组，与输入同序、同长度，不要解释。
输入：
"""


def stem_of(name: str) -> str:
    return str(name or "").removesuffix(".pdf").removesuffix(".PDF")


def has_cjk(text: str) -> bool:
    return bool(CJK.search(text or ""))


def llm_endpoint() -> tuple[str, str, str] | None:
    db_path = os.environ.get("DB_PATH", "/data/dav.db")
    try:
        from app.db import DB, user_plain_secret

        db = DB(db_path, credential_key=os.environ.get("FEISHU_CREDENTIAL_KEY") or "")
        for user in db.list_users():
            if not user.get("is_admin") or not user.get("llm_api_key"):
                continue
            key = user_plain_secret(user, "llm_api_key", db)
            base = (user.get("llm_api_base") or "").strip().rstrip("/")
            model = (user.get("llm_model") or "").strip() or "grok-4.6"
            if key and base:
                return key, base, model
    except Exception as exc:  # noqa: BLE001
        print(f"读站点 LLM 失败，改用环境变量: {exc}", file=sys.stderr)
    key = os.environ.get("LLM_API_KEY") or ""
    if not key:
        return None
    base = (os.environ.get("LLM_API_BASE") or "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL") or "gpt-4o-mini"
    return key, base, model


def chat(titles: list[str], endpoint: tuple[str, str, str]) -> list[str] | None:
    api_key, base, model = endpoint
    body = json.dumps({
        "model": model,
        "temperature": 0.2,
        "max_tokens": 2200,
        "messages": [
            {"role": "user", "content": PROMPT + json.dumps(titles, ensure_ascii=False)},
        ],
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            payload = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"LLM 失败: {exc}", file=sys.stderr)
        return None
    text = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1]
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return None
        try:
            out = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(out, list) or len(out) != len(titles):
        print(f"LLM 条数不符 {len(out) if isinstance(out, list) else type(out)}", file=sys.stderr)
        return None
    return [str(x).strip() for x in out]


def translate_chunk(chunk: list, endpoint: tuple[str, str, str]) -> list:
    titles = [item[1] for item in chunk]
    translated = chat(titles, endpoint)
    if not translated:
        time.sleep(1)
        translated = chat(titles, endpoint)
    if not translated:
        return []
    return list(zip(chunk, translated))


def load_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.environ.get("DB_PATH", "/data/dav.db"))
    p.add_argument("--archive", default=os.environ.get("IMA_ARCHIVE_ROOT", "/data/ima-archive"))
    p.add_argument("--group-id", default=GROUP_ID)
    p.add_argument("--min-sort", default=MIN_SORT)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--apply-index", action="store_true", default=True)
    args = p.parse_args()
    group_dirs = [
        os.path.join(args.archive, name)
        for name in os.listdir(args.archive)
        if name.startswith(args.group_id)
    ]
    if not group_dirs:
        print("找不到组目录", file=sys.stderr)
        return 1
    group_dir = group_dirs[0]
    titles_path = os.path.join(group_dir, "titles.json")
    overrides = load_json(titles_path)
    con = sqlite3.connect(args.db, check_same_thread=False)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "select media_id, day, name from ima_document_index "
        "where group_id=? and sort_date>=? order by sort_date, name",
        (args.group_id, args.min_sort),
    ).fetchall()
    pending = []
    for row in rows:
        name = str(row["name"] or "")
        stem = stem_of(name)
        if not name or has_cjk(name) or has_cjk(str(overrides.get(stem) or "")):
            continue
        pending.append((row["media_id"], name, stem))
    if args.limit:
        pending = pending[: args.limit]
    endpoint = llm_endpoint()
    if not endpoint:
        print("缺少可用 LLM", file=sys.stderr)
        return 1
    print(f"LLM {endpoint[2]} @ {endpoint[1]}  workers={args.workers}", flush=True)
    print(f"待译 {len(pending)}，已有覆盖 {len(overrides)} → {titles_path}", flush=True)
    chunks = [pending[i : i + BATCH] for i in range(0, len(pending), BATCH)]
    lock = threading.Lock()
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futs = [pool.submit(translate_chunk, chunk, endpoint) for chunk in chunks]
        for fut in as_completed(futs):
            pairs = fut.result()
            if not pairs:
                continue
            with lock:
                for (media_id, src, stem), zh in pairs:
                    if not zh or not has_cjk(zh):
                        continue
                    if not zh.lower().endswith(".pdf"):
                        zh = zh + ".pdf"
                    overrides[stem] = zh
                    if args.apply_index:
                        con.execute(
                            "update ima_document_index set name=?, name_folded=? "
                            "where group_id=? and media_id=?",
                            (zh, zh.casefold(), args.group_id, media_id),
                        )
                    done += 1
                    print(f"OK {src[:70]}\n → {zh[:70]}", flush=True)
                con.commit()
                save_json(titles_path, overrides)
    print(f"完成：新译 {done}，titles.json {len(overrides)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
