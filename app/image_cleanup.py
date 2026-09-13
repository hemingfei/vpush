"""帖子本地图片清理：按大V+月数删除老帖的本地缓存图片，并可顺带清理无引用孤儿文件。

背景：帖子有 posts_retention_days 定期删除（删行不删图），帖子图片又统一落
本地缓存（mx/zsxq/xq 三个目录，文件名为远端 URL 的 sha1），磁盘只增不减。

口径：
- 只删磁盘文件，不改 posts.images——旧帖图片失效由前端 imgOnError 死链兜底
- 「老图」按帖子发布时间判定（解析失败回退 fetched_at，再失败跳过不清理）
- 同一文件被多个帖子共用（sha1 同名）时，只要还有范围外引用就保留
- 孤儿 = 磁盘上有、但任何在库帖子都不再引用的文件，无法归属大V，按文件
  mtime 套同一个月数阈值全局清理
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .avatar_cache import PLATFORM_IMAGE_DIRS
from .fetchers.base import CN_TZ, parse_published_at

# 帖子图片本地缓存：URL 前缀 → 数据目录下的文件夹，由权威映射 PLATFORM_IMAGE_DIRS
# 派生（avatar_cache.py 定义，采集/补缓存/清理/静态挂载共用同一份）
POST_IMAGE_DIRS = {prefix: folder for folder, prefix in PLATFORM_IMAGE_DIRS.values()}

# 与 avatar_cache 的 sha1 键同形态：<16位hex>.<图片扩展名>；顺带挡住路径穿越
FILE_NAME_RE = re.compile(r"^[0-9a-f]{16}\.(jpg|png|webp|gif)$")

# 「N 个月」按 30 天折算：避免引入日历月依赖，管理端文案统一为「N 个月前」
DAYS_PER_MONTH = 30


def _data_dir(db) -> Path:
    return Path(db.path).parent


def _parse_local_image(entry) -> tuple[str, str] | None:
    """images 数组条目 → (folder, 文件名)；非本地缓存形态（远端 URL 等）返回 None。"""
    url = str(entry or "").strip()
    for prefix, folder in POST_IMAGE_DIRS.items():
        if not url.startswith(prefix + "/"):
            continue
        name = url[len(prefix) + 1:]
        return (folder, name) if FILE_NAME_RE.match(name) else None
    return None


def _has_local_prefix(entry) -> bool:
    url = str(entry or "").strip()
    return any(url.startswith(prefix + "/") for prefix in POST_IMAGE_DIRS)


def _row_images(raw) -> list:
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    if isinstance(raw, list):
        return raw
    return []


def _post_age_class(row, cutoff: datetime) -> str | None:
    """帖子时间分类：'old'（早于 cutoff）/ 'recent' / None（无法判定，不参与清理）。"""
    dt = parse_published_at(str(row.get("published_at") or ""))
    if dt is None:
        raw = str(row.get("fetched_at") or "").strip()
        try:
            # fetched_at 是 SQLite datetime('now') 的 naive UTC 串
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            ).astimezone(CN_TZ)
        except ValueError:
            return None
    return "old" if dt < cutoff else "recent"


def _scan(db, cutoff: datetime, kol_ids: set | None = None):
    """一遍扫出：全量引用集 / 范围内外引用集 / 按KOL归属 / 跳过计数。

    引用按「帖」记账而非按「文件」：同一文件既有范围内引用又有范围外引用
    （如甲乙各发过一次共用图、只清甲）时，文件级的集合差会把范围外引用抹掉，
    必须逐帖归侧。refs_all 恒收全量引用，作孤儿判定白名单。kol_ids 限定清理
    范围：仅这些大V的老帖计入 scoped_refs，其余（未选大V/近期/时间不明）计入
    unscoped_refs 起保护作用。
    """
    refs_all = {folder: set() for folder in POST_IMAGE_DIRS.values()}
    scoped_refs = {folder: set() for folder in POST_IMAGE_DIRS.values()}
    unscoped_refs = {folder: set() for folder in POST_IMAGE_DIRS.values()}
    by_kol: dict[int, set] = {}
    undated = invalid = 0
    # 与 fetchers/zsxq.purge_unreferenced_zsxq_files 同口径：服务模块直用 db._rows
    for row in db._rows(
        "SELECT id, kol_id, platform, published_at, fetched_at, images "
        "FROM posts WHERE images != ''"
    ):
        entries = _row_images(row.get("images"))
        parsed = []
        for entry in entries:
            got = _parse_local_image(entry)
            if got is None:
                if _has_local_prefix(entry):
                    invalid += 1
                continue
            parsed.append(got)
        for folder, name in parsed:
            refs_all[folder].add(name)
        if not parsed:
            continue
        age = _post_age_class(row, cutoff)
        if age is None:
            undated += 1
        kol_id = row.get("kol_id")
        if age == "old" and (kol_ids is None or kol_id in kol_ids):
            for folder, name in parsed:
                scoped_refs[folder].add(name)
                by_kol.setdefault(kol_id, set()).add((folder, name))
        else:
            for folder, name in parsed:
                unscoped_refs[folder].add(name)
    return refs_all, scoped_refs, unscoped_refs, by_kol, undated, invalid


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _orphan_paths(data_dir: Path, refs_all, cutoff: datetime) -> list[Path]:
    """磁盘上存在、无任何帖子引用、且 mtime 早于 cutoff 的图片文件。"""
    out = []
    for folder in POST_IMAGE_DIRS.values():
        d = data_dir / folder
        if not d.is_dir():
            continue
        for path in d.iterdir():
            if not path.is_file() or not FILE_NAME_RE.match(path.name):
                continue
            if path.name in refs_all.get(folder, ()):
                continue
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=CN_TZ)
            except OSError:
                continue
            if mtime < cutoff:
                out.append(path)
    return out


def _empty_result(months: int) -> dict:
    return {
        "months": months,
        "kols": [],
        "orphans": {"images": 0, "bytes": 0},
        "skipped_undated": 0,
        "skipped_invalid": 0,
    }


def preview_image_cleanup(db, months: int) -> dict:
    """按大V聚合「N 个月前老图」的归属统计，并给出孤儿图总量；不做任何删除。"""
    db_path = str(getattr(db, "path", "") or "")
    if not db_path or db_path == ":memory:":
        return _empty_result(months)
    cutoff = datetime.now(tz=CN_TZ) - timedelta(days=months * DAYS_PER_MONTH)
    data_dir = _data_dir(db)
    refs_all, _scoped, _unscoped, by_kol, undated, invalid = _scan(db, cutoff)
    kol_meta = {row["id"]: row for row in db._rows("SELECT id, name, platform FROM kols")}
    kols = []
    for kol_id, files in by_kol.items():
        meta = kol_meta.get(kol_id) or {}
        kols.append({
            "kol_id": kol_id,
            "kol_name": meta.get("name") or f"KOL {kol_id}",
            "platform": meta.get("platform") or "",
            "images": len(files),
            "bytes": sum(_file_size(data_dir / folder / name) for folder, name in files),
        })
    kols.sort(key=lambda item: (-item["bytes"], -item["images"]))
    orphans = _orphan_paths(data_dir, refs_all, cutoff)
    return {
        "months": months,
        "kols": kols,
        "orphans": {
            "images": len(orphans),
            "bytes": sum(_file_size(p) for p in orphans),
        },
        "skipped_undated": undated,
        "skipped_invalid": invalid,
    }


def run_image_cleanup(db, months: int, kol_ids: list[int], include_orphans: bool = False) -> dict:
    """删除选中大V N 个月前老图的本地文件；共用图仍有范围外引用时保留。"""
    cutoff = datetime.now(tz=CN_TZ) - timedelta(days=months * DAYS_PER_MONTH)
    data_dir = _data_dir(db)
    refs_all, scoped_refs, unscoped_refs, _by_kol, undated, invalid = _scan(
        db, cutoff, kol_ids=set(kol_ids) if kol_ids else None
    )
    deleted = freed = 0
    kept_shared: set = set()
    if kol_ids:
        kept_shared = {
            (folder, name)
            for folder in scoped_refs
            for name in scoped_refs[folder]
            if name in unscoped_refs[folder]
        }
        targets = {
            (folder, name)
            for folder in scoped_refs
            for name in scoped_refs[folder]
        } - kept_shared
        for folder, name in targets:
            path = data_dir / folder / name
            size = _file_size(path)
            try:
                path.unlink()
            except OSError:
                continue
            deleted += 1
            freed += size
    orphan_deleted = orphan_bytes = 0
    if include_orphans:
        for path in _orphan_paths(data_dir, refs_all, cutoff):
            size = _file_size(path)
            try:
                path.unlink()
            except OSError:
                continue
            orphan_deleted += 1
            orphan_bytes += size
    return {
        "months": months,
        "deleted_files": deleted,
        "freed_bytes": freed,
        "kept_shared": len(kept_shared),
        "orphan_files": orphan_deleted,
        "orphan_bytes": orphan_bytes,
        "skipped_undated": undated,
        "skipped_invalid": invalid,
    }
