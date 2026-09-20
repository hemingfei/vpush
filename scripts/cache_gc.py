#!/usr/bin/env python3
"""Cache GC for /cache (ARM lab).

If /cache used >= CACHE_WARN_GB (default 30) log a warning.
If /cache used >= CACHE_FORCE_GB (default 35) delete oldest files in hot/
(and staging/ only after lab.sqlite says uploaded/hot).

Never delete failed/ unless --purge-failed (or GC_PURGE_FAILED=1).
Never delete un-uploaded staging unless --allow-unuploaded-staging
(or GC_ALLOW_UNUPLOADED_STAGING=1). min-age alone is not enough.
Never delete manifest/ or logs/.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab_common import (  # noqa: E402
    RETRY_SUFFIX,
    atomic_write_json,
    cache_root,
    ensure_cache_dirs,
    env_bool,
    env_float,
    env_int,
    force_bytes,
    fs_usage,
    gb,
    iso_now,
    skip_file,
    tree_bytes,
    warn_bytes,
)

SKIP_RECENT_SECONDS_DEFAULT = 60
_UPLOADED_STATUSES = ("uploaded", "hot")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )


def load_uploaded_rels() -> tuple[set[str], bool]:
    """rel_path values marked uploaded/hot. Fail closed: empty + ok=False."""
    try:
        from manifest import get_conn

        rels: set[str] = set()
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT rel_path FROM files WHERE status IN (?, ?)",
                _UPLOADED_STATUSES,
            ).fetchall()
            for row in rows:
                rels.add(str(row["rel_path"]).lstrip("/"))
        return rels, True
    except Exception as exc:
        logging.warning("manifest unread; protecting all staging/: %s", exc)
        return set(), False


def collect_files(dirs: list[Path], min_age: int) -> list[tuple[float, int, Path]]:
    now = time.time()
    found: list[tuple[float, int, Path]] = []
    for root in dirs:
        if not root.is_dir():
            continue
        for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
            for name in filenames:
                fp = Path(dirpath) / name
                if skip_file(fp) or fp.is_symlink() or not fp.is_file():
                    continue
                try:
                    st = fp.stat()
                except OSError:
                    continue
                if min_age > 0 and (now - st.st_mtime) < min_age:
                    continue
                found.append((st.st_mtime, st.st_size, fp))
    found.sort(key=lambda t: (t[0], t[1], t[2].as_posix()))
    return found


def unlink_empty_parents(path: Path, stop_at: Path) -> None:
    parent = path.parent
    stop = stop_at.resolve()
    while parent != stop and str(parent).startswith(str(stop)):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def snapshot(root: Path) -> dict:
    paths = ensure_cache_dirs(root)
    usage = {
        "cache_bytes": tree_bytes(root),
        "staging_bytes": tree_bytes(paths["staging"]),
        "hot_bytes": tree_bytes(paths["hot"]),
        "failed_bytes": tree_bytes(paths["failed"]),
        "manifest_bytes": tree_bytes(paths["manifest"]),
        "logs_bytes": tree_bytes(paths["logs"]),
        "fs": fs_usage(root),
    }
    usage["cache_gb"] = gb(usage["cache_bytes"])
    usage["fs_used_gb"] = gb(usage["fs"]["used"])
    usage["fs_free_gb"] = gb(usage["fs"]["free"])
    return usage


def _under(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except OSError:
        return False


def staging_rel(path: Path, staging_root: Path) -> str | None:
    try:
        return path.resolve().relative_to(staging_root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def protect_reason(
    path: Path,
    *,
    paths: dict[str, Path],
    uploaded_rels: set[str],
    manifest_ok: bool,
    purge_failed: bool,
    allow_unuploaded: bool,
) -> str | None:
    """Return a reason to skip deletion, or None if the file may be GC'd."""
    if _under(path, paths["hot"]):
        return None
    if _under(path, paths["failed"]):
        return None if purge_failed else "failed_protected"
    if not _under(path, paths["staging"]):
        return "outside_victims"
    if allow_unuploaded:
        return None
    if not manifest_ok:
        return "manifest_unread"
    rel = staging_rel(path, paths["staging"])
    if rel is None:
        return "staging_escape"
    if rel not in uploaded_rels:
        return "not_uploaded"
    return None


def run_gc(
    root: Path,
    warn: int,
    force: int,
    purge_failed: bool,
    dry_run: bool,
    min_age: int,
    target: int | None = None,
    allow_unuploaded: bool = False,
) -> dict:
    paths = ensure_cache_dirs(root)
    before = snapshot(root)
    used = int(before["cache_bytes"])
    result: dict = {
        "ts": iso_now(),
        "ok": True,
        "dry_run": dry_run,
        "warn_bytes": warn,
        "force_bytes": force,
        "purge_failed": purge_failed,
        "allow_unuploaded_staging": allow_unuploaded,
        "before": before,
        "deleted": [],
        "deleted_bytes": 0,
        "protected": [],
        "protected_bytes": 0,
        "warned": used >= warn,
        "forced": used >= force,
        "message": None,
        "manifest_ok": True,
    }

    if used >= warn:
        logging.warning(
            "cache used %.3fG >= warn %.3fG (force %.3fG)",
            gb(used),
            gb(warn),
            gb(force),
        )
        result["message"] = "warn"
    else:
        logging.info("cache used %.3fG < warn %.3fG", gb(used), gb(warn))
        result["message"] = "ok"

    if used < force:
        result["after"] = before
        return result

    target_bytes = warn if target is None else target
    logging.warning(
        "cache used %.3fG >= force %.3fG; deleting oldest hot then uploaded staging until <= %.3fG%s",
        gb(used),
        gb(force),
        gb(target_bytes),
        " (dry-run)" if dry_run else "",
    )

    uploaded_rels, manifest_ok = load_uploaded_rels()
    result["manifest_ok"] = manifest_ok
    result["uploaded_rel_count"] = len(uploaded_rels)

    victims_dirs = [paths["hot"], paths["staging"]]
    if purge_failed:
        victims_dirs.append(paths["failed"])
        logging.warning("purge-failed enabled: failed/ is eligible")

    files = collect_files(victims_dirs, min_age=min_age)

    def rank(p: Path) -> int:
        posix = p.as_posix()
        if posix.startswith(paths["hot"].as_posix()):
            return 0
        if posix.startswith(paths["staging"].as_posix()):
            return 1
        return 2

    files.sort(key=lambda t: (t[0], rank(t[2]), t[1]))

    deleted_bytes = 0
    deleted: list[dict] = []
    protected: list[dict] = []
    protected_bytes = 0
    remaining = used
    for mtime, size, fp in files:
        if remaining <= target_bytes:
            break
        rel = str(fp.relative_to(root))
        reason = protect_reason(
            fp,
            paths=paths,
            uploaded_rels=uploaded_rels,
            manifest_ok=manifest_ok,
            purge_failed=purge_failed,
            allow_unuploaded=allow_unuploaded,
        )
        if reason:
            protected.append({"path": rel, "size": size, "reason": reason})
            protected_bytes += size
            logging.info("protect %s (%s) reason=%s", rel, size, reason)
            continue
        entry = {"path": rel, "size": size, "mtime": int(mtime)}
        if dry_run:
            deleted.append(entry)
            deleted_bytes += size
            remaining -= size
            logging.info("dry-run would delete %s (%s bytes)", rel, size)
            continue
        try:
            fp.unlink()
            sidecar = fp.with_name(fp.name + RETRY_SUFFIX)
            if sidecar.is_file():
                try:
                    sidecar.unlink()
                except OSError:
                    pass
            if _under(fp, paths["hot"]):
                stop_at = paths["hot"]
            elif _under(fp, paths["staging"]):
                stop_at = paths["staging"]
            else:
                stop_at = paths["failed"]
            unlink_empty_parents(fp, stop_at)
            deleted.append(entry)
            deleted_bytes += size
            remaining -= size
            logging.info("deleted %s (%s bytes)", rel, size)
        except OSError as exc:
            logging.error("delete failed %s: %s", rel, exc)

    after = snapshot(root)
    result["deleted"] = deleted
    result["deleted_bytes"] = deleted_bytes
    result["protected"] = protected
    result["protected_bytes"] = protected_bytes
    result["after"] = after
    after_used = int(after["cache_bytes"])
    if after_used >= force and not dry_run:
        result["ok"] = False
        result["message"] = "still_over_force"
        logging.error(
            "GC done but cache still %.3fG >= force %.3fG "
            "(failed=%.3fG protected_staging=%.3fG; "
            "--purge-failed / wait for puller / do not pass --allow-unuploaded-staging)",
            gb(after_used),
            gb(force),
            gb(int(after["failed_bytes"])),
            gb(protected_bytes),
        )
    else:
        result["message"] = "forced_cleaned"
        logging.info(
            "GC %s deleted=%s bytes=%.3fG protected=%s cache_now=%.3fG",
            "dry-run" if dry_run else "ok",
            len(deleted),
            gb(deleted_bytes),
            len(protected),
            gb(after_used),
        )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GC /cache hot + uploaded staging by age")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--purge-failed",
        action="store_true",
        help="also delete oldest files under failed/ (off by default)",
    )
    parser.add_argument(
        "--allow-unuploaded-staging",
        action="store_true",
        help="dangerous: allow deleting staging files not marked uploaded/hot",
    )
    parser.add_argument("--warn-gb", type=float, default=None)
    parser.add_argument("--force-gb", type=float, default=None)
    parser.add_argument("--min-age-seconds", type=int, default=None)
    args = parser.parse_args(argv)
    setup_logging()

    root = cache_root()
    warn = int((args.warn_gb if args.warn_gb is not None else env_float("CACHE_WARN_GB", 30.0)) * (1024**3))
    force = int((args.force_gb if args.force_gb is not None else env_float("CACHE_FORCE_GB", 35.0)) * (1024**3))
    if args.warn_gb is None and args.force_gb is None:
        warn = warn_bytes()
        force = force_bytes()
    purge = args.purge_failed or env_bool("GC_PURGE_FAILED", False)
    allow_unuploaded = args.allow_unuploaded_staging or env_bool(
        "GC_ALLOW_UNUPLOADED_STAGING", False
    )
    min_age = args.min_age_seconds
    if min_age is None:
        min_age = env_int("GC_MIN_AGE_SECONDS", SKIP_RECENT_SECONDS_DEFAULT)

    result = run_gc(
        root=root,
        warn=warn,
        force=force,
        purge_failed=purge,
        dry_run=args.dry_run,
        min_age=min_age,
        allow_unuploaded=allow_unuploaded,
    )
    try:
        atomic_write_json(root / "manifest" / "gc-last.json", result)
    except OSError as exc:
        logging.warning("could not write gc-last.json: %s", exc)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
