#!/usr/bin/env python3
"""从 ima 托管组的 PDF 首页提取真实标题 → 组目录 titles.json（应用侧展示名覆盖）。

用法：python3 ima_titles_extract.py <组目录，如 /srv/vpush-ima/7479…__4129…>
变体后缀（保留多版本，标题后附加区分）：
  _original   英文原版 → 提取页首英文标题（最多 3 行，遇作者大写行/日期/链接停止）
  _summary    摘要版   → 提取页 1 首个中文标题行
  _bilingual  双语版   → 同 original 规则 + 「（双语）」
幂等：已处理且 mtime 未变的文件跳过（state 存组目录 titles.state.json）。
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time

import fitz

CJK = re.compile(r"[\u4e00-\u9fff]{4,}")
AUTHOR_LIKE = re.compile(r"^[A-Z][A-Z\s,\.&]{3,}$")
DATE_LIKE = re.compile(r"\b(AUG|SEP|OCT|NOV|DEC|JAN|FEB|MAR|APR|MAY|JUL|20\d\d)\b")
URL_LIKE = re.compile(r"https?://|semianalysis\.com", re.I)
MAX_TITLE_LINES = 3
MAX_TITLE_CHARS = 120

VARIANTS = (
    ("_summary", "summary"),
    ("_bilingual", "bilingual"),
    ("_original", "original"),
)


def variant_of(stem: str) -> str:
    for suffix, kind in VARIANTS:
        if stem.endswith(suffix):
            return kind
    return ""


def extract_title(page_text: str, kind: str) -> str:
    lines = [l.strip() for l in page_text.splitlines() if l.strip()]
    if not lines:
        return ""
    if kind == "summary":
        for line in lines:
            if CJK.search(line) and "要点" not in line:
                return line[:MAX_TITLE_CHARS]
        return ""
    title: list[str] = []
    for line in lines:
        if URL_LIKE.search(line):
            break
        if title and (AUTHOR_LIKE.match(line) or DATE_LIKE.search(line)):
            break
        title.append(line)
        if len(title) >= MAX_TITLE_LINES:
            break
    return " ".join(title)[:MAX_TITLE_CHARS]


def main() -> None:
    group_dir = os.path.abspath(sys.argv[1])
    state_path = os.path.join(group_dir, "titles.state.json")
    out_path = os.path.join(group_dir, "titles.json")
    state: dict = {}
    try:
        with open(state_path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        pass
    overrides: dict = {}
    try:
        with open(out_path, encoding="utf-8") as f:
            overrides = json.load(f)
    except (OSError, ValueError):
        pass
    done = 0
    for path in sorted(glob.glob(os.path.join(group_dir, "*", "*.pdf"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem in overrides:
            continue
        key = f"{path}:{int(os.path.getmtime(path))}"
        if state.get(stem) == key:
            continue
        kind = variant_of(stem)
        try:
            with fitz.open(path) as doc:
                title = extract_title(doc[0].get_text(), kind)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN {stem[:50]}: {exc}", file=sys.stderr)
            continue
        if not title:
            continue
        if kind == "summary":
            display = f"{title}（摘要）"
        elif kind == "bilingual":
            display = f"{title}（双语）"
        else:
            display = title
        overrides[stem] = display
        state[stem] = key
        done += 1
        if done % 100 == 0:
            print(f"... 已提取 {done}", flush=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_path)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f)
    print(f"完成：新增标题 {done}，titles.json 共 {len(overrides)} 条 → {out_path}")


if __name__ == "__main__":
    main()
