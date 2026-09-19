#!/usr/bin/env python3
"""ARM lab staging → 115 uploader (lab-only; not production compose).

Canonical copy of the Oracle-SJ-ARM host puller. Deploy to::

  /opt/vpush-ima-lab/scripts/puller_loop.py
  /opt/vpush-ima-lab/scripts/puller_retry.py

systemd timer on ARM invokes this; **do not** add it to production
``docker-compose*.yml`` and **do not** set ``VPUSH_ARM_MIDDLEWARE=1`` there.

Walks ``$VPUSH_ARM_STAGING_ROOT`` (default ``/data/vpush-ima-cache/staging``)
for ``local/**/*.pdf``, uploads through an injectable 115 client, and wraps
each attempt with ``call_with_retry``. The client must return
``{"upload_ok": true, ...}``; a missing/false ``upload_ok`` or empty
``filesha1`` raises so MultipartUploadAbort / empty-filesha1 flakes retry
2–3 times, then the file moves to ``failed/``.

Default is dry-run (list only, no upload). ``--apply`` uploads. Without a
host uploader or ``--uploader`` / ``VPUSH_115_UPLOAD_CMD``, ``--apply``
exits 2 (tests inject a fake). Does not read IMA / CICC cookies.

用法：
  python3 scripts/puller_loop.py
  python3 scripts/puller_loop.py --apply --staging-root /data/vpush-ima-cache/staging
  python3 /opt/vpush-ima-lab/scripts/puller_loop.py --apply --once
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for candidate in (str(HERE), str(ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

try:
    from puller_retry import call_with_retry
except ImportError:  # repo checkout: scripts/ is a package
    from scripts.puller_retry import call_with_retry

DEFAULT_CACHE_ROOT = Path("/data/vpush-ima-cache")
DEFAULT_STAGING_ROOT = DEFAULT_CACHE_ROOT / "staging"
DEFAULT_HOT_ROOT = DEFAULT_CACHE_ROOT / "hot"
DEFAULT_FAILED_ROOT = DEFAULT_CACHE_ROOT / "failed"
DEFAULT_MANIFEST = DEFAULT_CACHE_ROOT / "manifest" / "lab.sqlite"
DEFAULT_OBJECT_PREFIX = "/vpush"
ARM_LAB_SCRIPTS = Path("/opt/vpush-ima-lab/scripts")
PDF_GLOB = "local/**/*.pdf"


class UploadError(RuntimeError):
    """115 upload failed or returned a non-ok payload (retryable or not)."""


@dataclass(frozen=True)
class PlannedUpload:
    src: Path
    relpath: str
    dest_key: str
    size: int


class LabManifest:
    """Minimal ARM lab.sqlite: skip already-uploaded relpaths."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS objects (
                relpath TEXT PRIMARY KEY,
                size INTEGER NOT NULL,
                sha1 TEXT,
                dest TEXT,
                uploaded_at INTEGER NOT NULL
            )
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def has(self, relpath: str, size: int | None = None) -> bool:
        row = self.conn.execute(
            "SELECT size FROM objects WHERE relpath = ?",
            (relpath,),
        ).fetchone()
        if row is None:
            return False
        if size is None:
            return True
        return int(row[0]) == int(size)

    def record(self, relpath: str, *, size: int, sha1: str = "", dest: str = "") -> None:
        self.conn.execute(
            """
            INSERT INTO objects (relpath, size, sha1, dest, uploaded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(relpath) DO UPDATE SET
                size = excluded.size,
                sha1 = excluded.sha1,
                dest = excluded.dest,
                uploaded_at = excluded.uploaded_at
            """,
            (relpath, int(size), sha1 or "", dest or "", int(time.time())),
        )
        self.conn.commit()


def resolve_staging_root(cli_value: str | None = None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    env = os.environ.get("VPUSH_ARM_STAGING_ROOT", "").strip()
    return Path(env or DEFAULT_STAGING_ROOT).expanduser()


def resolve_cache_sibling(staging_root: Path, name: str, cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).expanduser()
    env_key = {
        "hot": "VPUSH_ARM_HOT_ROOT",
        "failed": "VPUSH_ARM_FAILED_ROOT",
        "manifest": "VPUSH_ARM_MANIFEST",
    }.get(name)
    if env_key:
        env = os.environ.get(env_key, "").strip()
        if env:
            return Path(env).expanduser()
    parent = staging_root.parent
    if name == "manifest":
        return parent / "manifest" / "lab.sqlite"
    return parent / name


def arm_relpath(path: Path) -> str:
    """staging 下的 ``local/...`` 相对路径；找不到 local 则只留文件名。"""
    parts = path.parts
    if "local" in parts:
        return "/".join(parts[parts.index("local") :])
    return path.name


def object_key(relpath: str, prefix: str = DEFAULT_OBJECT_PREFIX) -> str:
    rel = str(relpath).lstrip("/")
    base = str(prefix or DEFAULT_OBJECT_PREFIX).rstrip("/")
    return f"{base}/{rel}"


def file_sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_staging_pdfs(staging_root: Path) -> list[Path]:
    if not staging_root.is_dir():
        return []
    found = [
        path
        for path in staging_root.glob(PDF_GLOB)
        if path.is_file() and not path.name.startswith(".")
    ]
    return sorted(found)


def plan_uploads(
    staging_root: Path,
    *,
    manifest: LabManifest | None = None,
    limit: int = 0,
    object_prefix: str = DEFAULT_OBJECT_PREFIX,
) -> list[PlannedUpload]:
    planned: list[PlannedUpload] = []
    for src in iter_staging_pdfs(staging_root):
        relpath = arm_relpath(src)
        size = src.stat().st_size
        if manifest is not None and manifest.has(relpath, size):
            continue
        planned.append(
            PlannedUpload(
                src=src,
                relpath=relpath,
                dest_key=object_key(relpath, object_prefix),
                size=size,
            )
        )
        if limit and len(planned) >= limit:
            break
    return planned


def _is_empty_filesha1(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"", "null", "none", "nil"}


def require_upload_ok(result: Any) -> dict[str, Any]:
    """Raise unless the 115 client returned a successful ``upload_ok`` payload.

    Empty ``filesha1`` is treated as failure so ``call_with_retry`` can retry
    MultipartUploadAbort / empty-filesha1 flakes.
    """
    if not isinstance(result, dict):
        raise UploadError(f"upload returned non-dict: {result!r}")
    error = result.get("error") or result.get("reason") or result.get("message") or ""
    sha = result.get("filesha1")
    if _is_empty_filesha1(sha):
        raise UploadError(str(error or "empty filesha1"))
    if not result.get("upload_ok"):
        raise UploadError(str(error or "upload_ok is false"))
    return result


def upload_or_raise(uploader: Callable[[Path, str], Any], src: Path, dest_key: str) -> dict[str, Any]:
    return require_upload_ok(uploader(src, dest_key))


def upload_with_retry(
    uploader: Callable[[Path, str], Any],
    src: Path,
    dest_key: str,
    *,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    return call_with_retry(lambda: upload_or_raise(uploader, src, dest_key), sleeper=sleeper)


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for index in range(1, 1000):
        candidate = dest.with_name(f"{stem}.fail{index}{suffix}")
        if not candidate.exists():
            return candidate
    return dest.with_name(f"{stem}.fail{int(time.time())}{suffix}")


def move_to_failed(src: Path, staging_root: Path, failed_root: Path) -> Path:
    try:
        rel = src.relative_to(staging_root)
    except ValueError:
        rel = Path(src.name)
    dest = _unique_dest(failed_root / rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    sidecar = src.with_suffix(".json")
    if sidecar.is_file():
        shutil.move(str(sidecar), str(dest.with_suffix(".json")))
    return dest


def promote_to_hot(src: Path, staging_root: Path, hot_root: Path) -> Path:
    try:
        rel = src.relative_to(staging_root)
    except ValueError:
        rel = Path(src.name)
    dest = hot_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        try:
            os.link(src, dest)
        except OSError:
            shutil.copy2(src, dest)
    sidecar = src.with_suffix(".json")
    hot_sidecar = dest.with_suffix(".json")
    if sidecar.is_file() and not hot_sidecar.exists():
        try:
            os.link(sidecar, hot_sidecar)
        except OSError:
            shutil.copy2(sidecar, hot_sidecar)
    return dest


def process_one(
    item: PlannedUpload,
    *,
    uploader: Callable[[Path, str], Any],
    staging_root: Path,
    failed_root: Path,
    hot_root: Path | None,
    manifest: LabManifest,
    sleeper: Callable[[float], None] = time.sleep,
) -> str:
    """Upload one PDF with retry. Returns uploaded / failed / skipped."""
    if not item.src.is_file():
        return "skipped"
    try:
        result = upload_with_retry(uploader, item.src, item.dest_key, sleeper=sleeper)
        sha = str(result.get("filesha1") or file_sha1(item.src))
        dest = str(result.get("dest") or item.dest_key)
        manifest.record(item.relpath, size=item.size, sha1=sha, dest=dest)
        if hot_root is not None:
            promote_to_hot(item.src, staging_root, hot_root)
        return "uploaded"
    except Exception as exc:
        dest = move_to_failed(item.src, staging_root, failed_root)
        print(f"FAIL {item.relpath} → {dest} error={exc}")
        return "failed"


def _load_host_uploader() -> Callable[[Path, str], Any] | None:
    """Optional ARM-host 115 client (lab_upload / lab_common). Not vendored."""
    extra = os.environ.get("VPUSH_ARM_LAB_PYTHONPATH", "").strip()
    search = [p for p in (extra, str(ARM_LAB_SCRIPTS), str(HERE)) if p]
    for path in search:
        if path not in sys.path:
            sys.path.insert(0, path)
    for mod_name, attr in (
        ("lab_upload", "upload"),
        ("lab_upload", "upload_file"),
        ("lab_common", "upload"),
        ("lab_common", "upload_file"),
    ):
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        fn = getattr(mod, attr, None)
        if callable(fn):
            return fn
    return None


def _cmd_uploader(template: str) -> Callable[[Path, str], Any]:
    """Run a host command. ``{src}`` / ``{dest}`` placeholders. Never logs secrets."""

    def upload(src: Path, dest_key: str) -> dict[str, Any]:
        cmd = template.format(src=str(src), dest=dest_key)
        proc = subprocess.run(
            cmd,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
        )
        payload: dict[str, Any] = {}
        stdout = (proc.stdout or "").strip()
        if stdout:
            try:
                parsed = json.loads(stdout)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                payload = parsed
        if proc.returncode != 0 and not payload:
            err = (proc.stderr or stdout or f"exit {proc.returncode}").strip()
            raise UploadError(err.splitlines()[0][:300] if err else f"exit {proc.returncode}")
        if "upload_ok" not in payload:
            payload["upload_ok"] = proc.returncode == 0
        if proc.returncode != 0:
            payload.setdefault("error", (proc.stderr or stdout or f"exit {proc.returncode}").strip()[:300])
        return payload

    return upload


def resolve_uploader(
    factory: Callable[[], Callable[[Path, str], Any]] | None = None,
    *,
    upload_cmd: str | None = None,
) -> Callable[[Path, str], Any] | None:
    if factory is not None:
        return factory()
    cmd = (upload_cmd or os.environ.get("VPUSH_115_UPLOAD_CMD", "")).strip()
    if cmd:
        return _cmd_uploader(cmd)
    return _load_host_uploader()


def main(
    argv: list[str] | None = None,
    *,
    uploader_factory: Callable[[], Callable[[Path, str], Any]] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只列 pending PDF / dest key，不上传（默认）",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="真正上传 115；须提供 host uploader、--uploader 命令或测试 factory",
    )
    ap.add_argument(
        "--once",
        action="store_true",
        help="扫一轮后退出（默认；给 ARM systemd timer）",
    )
    ap.add_argument(
        "--loop",
        action="store_true",
        help="循环扫描（宿主机 daemon；默认关）",
    )
    ap.add_argument("--interval", type=int, default=60, help="--loop 间隔秒（默认 60）")
    ap.add_argument("--limit", type=int, default=0, help="本轮最多处理 N 个 PDF（0=不限）")
    ap.add_argument(
        "--staging-root",
        default=None,
        help=f"ARM staging 根，默认 VPUSH_ARM_STAGING_ROOT 或 {DEFAULT_STAGING_ROOT}",
    )
    ap.add_argument("--hot-root", default=None, help="成功后硬链/拷到 hot（默认 cache/hot）")
    ap.add_argument("--failed-root", default=None, help="重试耗尽后移入 failed/")
    ap.add_argument("--manifest", default=None, help="lab.sqlite 路径（默认 cache/manifest/lab.sqlite）")
    ap.add_argument(
        "--uploader",
        default=None,
        help="115 上传命令模板，含 {src} {dest}；或设 VPUSH_115_UPLOAD_CMD",
    )
    ap.add_argument(
        "--object-prefix",
        default=DEFAULT_OBJECT_PREFIX,
        help="115 对象前缀（默认 /vpush）",
    )
    args = ap.parse_args(argv)

    dry_run = True
    if args.apply:
        dry_run = False
    if args.dry_run:
        dry_run = True

    staging_root = resolve_staging_root(args.staging_root)
    failed_root = resolve_cache_sibling(staging_root, "failed", args.failed_root)
    hot_root = resolve_cache_sibling(staging_root, "hot", args.hot_root)
    manifest_path = resolve_cache_sibling(staging_root, "manifest", args.manifest)
    wait = sleeper or time.sleep

    def one_pass() -> int:
        manifest = None
        # Dry-run must not mkdir host cache paths (e.g. /data/vpush-ima-cache).
        if (not dry_run) or manifest_path.is_file():
            manifest = LabManifest(manifest_path)
        try:
            planned = plan_uploads(
                staging_root,
                manifest=manifest,
                limit=max(0, int(args.limit or 0)),
                object_prefix=args.object_prefix,
            )
            if not planned:
                print(f"无待上传 PDF（staging={staging_root}）")
                return 0
            if dry_run:
                for item in planned:
                    print(f"WOULD UPLOAD {item.src} → {item.dest_key}")
                print(
                    f"dry-run {len(planned)} 个文件（ARM lab puller；"
                    "生产 compose 不要启用 middleware / 不要跑本脚本）"
                )
                return 0
            uploader = resolve_uploader(uploader_factory, upload_cmd=args.uploader)
            if uploader is None:
                print(
                    "没有 115 uploader（测试注入 factory，或 ARM 宿主机 "
                    "lab_upload/lab_common，或 --uploader / VPUSH_115_UPLOAD_CMD）。"
                    "未上传。用法见 scripts/puller_loop.md。"
                )
                return 2
            stats = {"uploaded": 0, "failed": 0, "skipped": 0}
            for item in planned:
                action = process_one(
                    item,
                    uploader=uploader,
                    staging_root=staging_root,
                    failed_root=failed_root,
                    hot_root=hot_root,
                    manifest=manifest,
                    sleeper=wait,
                )
                stats[action] = stats.get(action, 0) + 1
                if action == "uploaded":
                    print(f"UPLOAD {item.relpath} → {item.dest_key}")
            print(
                f"apply uploaded={stats['uploaded']} skipped={stats['skipped']} "
                f"failed={stats['failed']}"
            )
            return 1 if stats["failed"] else 0
        finally:
            if manifest is not None:
                manifest.close()

    if args.loop and not args.once:
        while True:
            code = one_pass()
            if code == 2:
                return 2
            wait(max(1, int(args.interval)))
    return one_pass()


if __name__ == "__main__":
    raise SystemExit(main())
