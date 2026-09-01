"""全球顶级投行研报：采集后把英文文件名译成中文展示名。"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

logger = logging.getLogger(__name__)

BANK_NAME_HINT = "全球顶级投行"
MIN_SORT = "2026-07-01"
BATCH = 12
MAX_PER_RUN = 240
CJK = re.compile(r"[\u4e00-\u9fff]")
DATE_SUFFIX = re.compile(r"-(\d{6})\.pdf$", re.I)
TITLE_TRANSLATION_TIMEOUT = 20
TITLE_TRANSLATION_BUDGET_SECONDS = 180
PROMPT = (
    "把投行研报英文文件名译成中文展示名。规则："
    "1. 券商用中文（高盛/野村/摩根士丹利/摩根大通/瑞银/德意志银行/伯恩斯坦/花旗/美银证券/汇丰/麦格理等）"
    "2. 保留股票代码括号 3. 保留末尾 -YYMMDD.pdf "
    "4. 格式：券商-公司（代码）中文标题-YYMMDD.pdf "
    "5. 只输出 JSON 字符串数组，与输入同序、同长度。\n输入：\n"
)


def _stem(name: str) -> str:
    return str(name or "").removesuffix(".pdf").removesuffix(".PDF")


def _has_cjk(text: str) -> bool:
    return bool(CJK.search(text or ""))


def _normalized_translation(source: str, translated: str) -> str:
    value = str(translated or "").strip()
    if not value or not _has_cjk(value):
        return ""
    source_suffix = DATE_SUFFIX.search(source)
    value = value.removesuffix(".pdf").removesuffix(".PDF")
    value = re.sub(r"-\d{1,6}$", "", value)
    if source_suffix:
        value = f"{value}-{source_suffix.group(1)}"
    return f"{value}.pdf"


def _group_dir(archive_root, group_id: str) -> str:
    root = str(archive_root)
    prefix = str(group_id or "")
    try:
        names = os.listdir(root)
    except OSError:
        return ""
    for name in names:
        if name.startswith(prefix):
            path = os.path.join(root, name)
            if os.path.isdir(path):
                return path
    return ""


def _load_overrides(path: str) -> dict[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): str(v) for k, v in data.items() if v} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_overrides(path: str, data: dict[str, str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _parse_list(text: str, n: int) -> list[str] | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").split("\n", 1)[-1]
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.S)
        if not m:
            return None
        try:
            out = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(out, list) or len(out) != n:
        return None
    return [str(x).strip() for x in out]


def refresh_bank_titles_zh(service: Any, *, llm_config=None, chat=None, limit: int = MAX_PER_RUN) -> int:
    """把尚未中文化的投行标题写入 titles.json 并回写读索引。失败返回 0。"""
    from .llm import _chat
    from .scheduler import _system_llm_config

    cfg = llm_config if llm_config is not None else _system_llm_config(
        service.db,
        getattr(service, "llm_config", None),
    )
    if cfg is None:
        return 0
    chat_fn = chat or (lambda titles: _parse_list(
        _chat(
            cfg,
            [{"role": "user", "content": PROMPT + json.dumps(titles, ensure_ascii=False)}],
            2200,
            temperature=0.2,
            timeout=TITLE_TRANSLATION_TIMEOUT,
        ) or "",
        len(titles),
    ))
    deadline = time.monotonic() + TITLE_TRANSLATION_BUDGET_SECONDS
    remaining = max(0, int(limit))
    groups = [
        group for group in service.config().groups
        if BANK_NAME_HINT in str(group.name or "")
    ]
    if not groups:
        return 0
    done = 0
    for group in groups:
        group_dir = _group_dir(service.store.archive_root, group.id)
        if not group_dir:
            continue
        titles_path = os.path.join(group_dir, "titles.json")
        overrides = _load_overrides(titles_path)
        rows = service.db._rows(
            "SELECT media_id, name FROM ima_document_index "
            "WHERE group_id = ? AND sort_date >= ? ORDER BY sort_date, name",
            (group.id, MIN_SORT),
        )
        pending: dict[str, dict[str, Any]] = {}
        for row in rows:
            name = str(row["name"] or "")
            stem = _stem(name)
            override = str(overrides.get(stem) or "")
            if override and _has_cjk(override):
                service.db._execute(
                    "UPDATE ima_document_index SET name = ?, name_folded = ? WHERE group_id = ? AND media_id = ?",
                    (override, override.casefold(), group.id, str(row["media_id"] or "")),
                )
                continue
            if not name or _has_cjk(name):
                continue
            item = pending.setdefault(stem, {"source": name, "media_ids": []})
            item["media_ids"].append(str(row["media_id"] or ""))
        entries = list(pending.values())[:remaining]
        for i in range(0, len(entries), BATCH):
            if remaining <= 0 or time.monotonic() >= deadline:
                break
            chunk = entries[i : i + min(BATCH, remaining)]
            translated = chat_fn([item["source"] for item in chunk])
            if not translated:
                logger.warning("投行标题翻译批次失败 group=%s offset=%s", group.id[:16], i)
                break
            for item, raw_zh in zip(chunk, translated):
                zh = _normalized_translation(item["source"], raw_zh)
                if not zh:
                    continue
                stem = _stem(item["source"])
                overrides[stem] = zh
                for media_id in item["media_ids"]:
                    service.db._execute(
                        "UPDATE ima_document_index SET name = ?, name_folded = ? "
                        "WHERE group_id = ? AND media_id = ?",
                        (zh, zh.casefold(), group.id, media_id),
                    )
                    done += 1
                remaining -= 1
            _save_overrides(titles_path, overrides)
    if done:
        logger.info("投行标题已译 %s 条", done)
    return done
