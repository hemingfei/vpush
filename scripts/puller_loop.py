#!/usr/bin/env python3
"""Watch /cache/staging and upload to P115_LAB_ROOT (/vpush) via p115client.

Scale: scan staging only (never walk hot/), skip via lab.sqlite, batch=20,
rotating /cache/logs/puller.log. Never logs cookies.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from puller_retry import call_with_retry
from lab_common import (  # noqa: E402
    RETRY_SUFFIX,
    append_jsonl,
    atomic_write_json,
    cache_root,
    classify_error,
    device_type,
    ensure_cache_dirs,
    ensure_remote_dir,
    env_bool,
    env_int,
    env_str,
    file_sha1,
    iso_now,
    lab_root,
    make_client,
    rel_under,
    safe_exc,
    skip_file,
    upload_ok,
    utcnow,
)
from manifest import (  # noqa: E402
    db_path,
    ensure_inbox,
    get_by_rel,
    is_done,
    mark_failed,
    mark_uploaded,
    mark_uploading,
    upsert_file,
)

STOP = False


def _stop(signum, _frame) -> None:
    global STOP
    STOP = True
    logging.info("stop signal %s", signum)


def parse_backoff(raw: str) -> list[int]:
    vals = [int(x.strip()) for x in raw.split(",") if x.strip()]
    return vals or [60, 300, 1800]


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(
            RotatingFileHandler(
                log_dir / "puller.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
        handlers=handlers,
        force=True,
    )


def stable(path: Path, secs: int) -> bool:
    try:
        st = path.stat()
    except OSError:
        return False
    return st.st_size > 0 and (time.time() - st.st_mtime) >= secs


def list_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out = [p for p in root.rglob("*") if p.is_file() and not p.is_symlink() and not skip_file(p)]
    out.sort(key=lambda p: p.as_posix())
    return out


def sidecar(path: Path) -> Path:
    return path.with_name(path.name + RETRY_SUFFIX)


def read_sidecar(path: Path) -> dict:
    import json

    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def backoff(attempts: int, schedule: list[int]) -> int:
    return schedule[min(max(attempts - 1, 0), len(schedule) - 1)]


def remote_of(rel: Path, root: str) -> str:
    return f"{root}/{rel.as_posix().lstrip('/')}"


def prune(path: Path, stop_at: Path) -> None:
    parent, stop = path.parent, stop_at.resolve()
    while parent != stop and parent.is_relative_to(stop):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def meta_from(up: object) -> tuple[str | None, str | None]:
    if not isinstance(up, dict):
        return None, None
    cid = up.get("file_id") or up.get("fid") or up.get("fileid") or up.get("cid")
    pick = up.get("pickcode") or up.get("pick_code")
    data = up.get("data")
    if isinstance(data, dict):
        cid = cid or data.get("file_id") or data.get("fid") or data.get("fileid")
        pick = pick or data.get("pickcode") or data.get("pick_code")
    return (str(cid) if cid is not None else None, str(pick) if pick else None)


def fmt_ts(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Puller:
    def __init__(self) -> None:
        paths = ensure_cache_dirs()
        ensure_inbox()
        self.cache = cache_root()
        self.staging = paths["staging"]
        self.hot = paths["hot"]
        self.failed = paths["failed"]
        self.manifest = paths["manifest"]
        self.logs = paths["logs"]
        self.root = lab_root()
        self.keep_hot = env_bool("PULLER_KEEP_HOT", True)
        self.poll = env_int("PULLER_POLL_SECONDS", 5)
        self.stable_secs = env_int("PULLER_STABLE_SECONDS", 3)
        self.batch_size = env_int("PULLER_BATCH_SIZE", 20)
        self.backoff_sched = parse_backoff(env_str("PULLER_BACKOFF_SECONDS", "60,300,1800"))
        self.client = None
        self.dir_cids: dict[str, int] = {}
        self.uploaded = 0
        self.failed_n = 0
        self.skipped = 0
        self.tick_ok = self.tick_fail = self.tick_skip = 0
        self.last_ok: dict | None = None
        self.last_error: dict | None = None
        _ = db_path()

    def client_get(self, force: bool = False):
        if self.client is None or force:
            self.client = make_client()
            self.dir_cids = {}
        return self.client

    def cid_for(self, remote_dir: str) -> int:
        if remote_dir not in self.dir_cids:
            self.dir_cids[remote_dir] = ensure_remote_dir(self.client_get(), remote_dir)
        return self.dir_cids[remote_dir]

    def save_state(self, extra: dict | None = None) -> None:
        row = {
            "ts": iso_now(),
            "ok": True,
            "device_type": device_type(),
            "lab_root": self.root,
            "uploaded_count": self.uploaded,
            "failed_count": self.failed_n,
            "skipped_count": self.skipped,
            "batch_size": self.batch_size,
            "sqlite": str(db_path()),
            "last_ok": self.last_ok,
            "last_error": self.last_error,
            "poll_seconds": self.poll,
            "keep_hot": self.keep_hot,
            "tick_ok": self.tick_ok,
            "tick_fail": self.tick_fail,
            "tick_skip": self.tick_skip,
        }
        if extra:
            row.update(extra)
        atomic_write_json(self.manifest / "puller-heartbeat.json", row)

    def to_hot(self, src: Path, rel: Path) -> None:
        if not self.keep_hot:
            return
        dest = self.hot / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            logging.warning("hot copy failed rel=%s err=%s", rel.as_posix(), safe_exc(exc))

    def on_ok(self, src: Path, rel: Path, remote: str, size: int, attempts: int, source: str, up=None) -> None:
        sha = None
        try:
            sha = file_sha1(src)
        except OSError:
            pass
        cid, pick = meta_from(up)
        self.to_hot(src, rel)
        try:
            src.unlink()
        except OSError as exc:
            logging.warning("unlink failed rel=%s err=%s", rel.as_posix(), safe_exc(exc))
        sc = sidecar(src)
        if sc.is_file():
            try:
                sc.unlink()
            except OSError:
                pass
        prune(src, self.staging if source == "staging" else self.failed)
        mark_uploaded(
            rel.as_posix(),
            remote_cid=cid,
            remote_pickcode=pick,
            sha1=sha,
            size=size,
            keep_hot=self.keep_hot,
        )
        self.uploaded += 1
        self.tick_ok += 1
        row = {
            "ts": iso_now(),
            "ok": True,
            "relpath": rel.as_posix(),
            "remote_path": remote,
            "size": size,
            "sha1": sha,
            "attempts": attempts,
            "source": source,
            "remote_cid": cid,
        }
        self.last_ok, self.last_error = row, None
        append_jsonl(self.manifest / "uploads.jsonl", row)
        self.save_state()
        logging.info("uploaded rel=%s remote=%s size=%s attempts=%s", rel.as_posix(), remote, size, attempts)

    def on_fail(self, src: Path, rel: Path, err: BaseException, attempts: int, source: str) -> None:
        kind, msg = classify_error(err)
        dest = self.failed / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dest.resolve():
            if dest.exists():
                stamp = utcnow().strftime("%Y%m%d-%H%M%S")
                dest = dest.with_name(f"{dest.stem}.dup-{stamp}{dest.suffix}")
            try:
                shutil.move(str(src), str(dest))
            except OSError as move_exc:
                logging.error("move to failed/ failed rel=%s err=%s", rel.as_posix(), safe_exc(move_exc))
                dest = src
        attempts = max(attempts, 1)
        delay = backoff(attempts, self.backoff_sched)
        next_at = utcnow().timestamp() + delay
        meta = {
            "relpath": rel.as_posix(),
            "attempts": attempts,
            "backoff_seconds": delay,
            "next_retry_at": fmt_ts(next_at),
            "next_retry_ts": next_at,
            "last_error": msg,
            "error_kind": kind,
            "last_failed_at": iso_now(),
            "size": dest.stat().st_size if dest.is_file() else None,
            "source": source,
        }
        old = read_sidecar(sidecar(dest))
        meta["first_failed_at"] = old.get("first_failed_at") or iso_now()
        atomic_write_json(sidecar(dest), meta)
        if source == "staging":
            prune(src, self.staging)
        mark_failed(rel.as_posix(), msg, attempts=attempts)
        self.failed_n += 1
        self.tick_fail += 1
        self.last_error = meta
        append_jsonl(self.manifest / "uploads.jsonl", {**meta, "ok": False, "ts": iso_now()})
        self.save_state()
        logging.error(
            "upload failed rel=%s kind=%s attempts=%s retry_in=%ss err=%s",
            rel.as_posix(),
            kind,
            attempts,
            delay,
            msg,
        )
        if kind == "cookie":
            self.client = None

    def upload_one(self, src: Path, rel: Path, attempts: int, source: str) -> bool:
        remote = remote_of(rel, self.root)
        remote_dir = remote.rsplit("/", 1)[0]
        size = src.stat().st_size
        mark_uploading(rel.as_posix())
        try:
            cid = self.cid_for(remote_dir)
            def _do_up():
                client = self.client_get()
                result = client.upload_file(str(src), pid=cid, filename=src.name)
                if not upload_ok(result):
                    errno = result.get("errno") if isinstance(result, dict) else None
                    raise RuntimeError(
                        f"upload rejected errno={errno} body={result!r}"
                    )
                return result
            up = call_with_retry(_do_up)
            self.on_ok(src, rel, remote, size, attempts, source, up=up)
            return True
        except SystemExit:
            raise
        except Exception as exc:
            kind, _ = classify_error(exc)
            if kind == "cookie":
                try:
                    self.client_get(force=True)
                    cid = self.cid_for(remote_dir)
                    def _do_up2():
                        client = self.client_get()
                        result = client.upload_file(str(src), pid=cid, filename=src.name)
                        if not upload_ok(result):
                            errno = result.get("errno") if isinstance(result, dict) else None
                            raise RuntimeError(
                                f"upload rejected errno={errno} body={result!r}"
                            )
                        return result
                    up = call_with_retry(_do_up2)
                    if upload_ok(up):
                        self.on_ok(src, rel, remote, size, attempts, source, up=up)
                        return True
                except Exception as exc2:
                    self.on_fail(src, rel, exc2, attempts, source)
                    return False
            self.on_fail(src, rel, exc, attempts, source)
            return False

    def discover_batch(self) -> list[tuple[Path, Path, int]]:
        batch: list[tuple[Path, Path, int]] = []
        for src in list_files(self.staging):
            if STOP or len(batch) >= self.batch_size:
                break
            if not stable(src, self.stable_secs):
                continue
            try:
                rel = rel_under(src, self.staging)
            except ValueError:
                logging.warning("skip outside staging: %s", src)
                continue
            rel_s = rel.as_posix()
            try:
                sha = file_sha1(src)
            except OSError:
                sha = None
            if is_done(rel_s, sha1=sha):
                logging.info("skip already-uploaded rel=%s", rel_s)
                self.skipped += 1
                self.tick_skip += 1
                if self.keep_hot:
                    self.to_hot(src, rel)
                try:
                    src.unlink()
                    prune(src, self.staging)
                except OSError:
                    pass
                continue
            row = get_by_rel(rel_s)
            if row is None:
                upsert_file(rel_s, sha1=sha, size=src.stat().st_size, status="staging")
            attempts = int((row or {}).get("attempts") or 0) + 1
            batch.append((src, rel, attempts))
        return batch

    def process_staging(self) -> int:
        n = 0
        for src, rel, attempts in self.discover_batch():
            if STOP:
                break
            n += 1
            self.upload_one(src, rel, attempts, "staging")
        return n

    def process_retries(self) -> int:
        n = 0
        now = time.time()
        if not self.failed.is_dir():
            return 0
        files = [
            p
            for p in list_files(self.failed)
            if not p.name.endswith(RETRY_SUFFIX)
        ]
        for src in files:
            if STOP or n >= self.batch_size:
                break
            meta = read_sidecar(sidecar(src))
            next_ts = float(meta.get("next_retry_ts") or 0)
            if next_ts and next_ts > now:
                continue
            if not stable(src, self.stable_secs):
                continue
            try:
                rel = Path(str(meta.get("relpath") or rel_under(src, self.failed).as_posix()))
            except ValueError:
                continue
            attempts = int(meta.get("attempts") or 0) + 1
            n += 1
            logging.info("retry rel=%s attempts=%s", rel.as_posix(), attempts)
            self.upload_one(src, rel, attempts, "failed")
        return n

    def tick(self) -> None:
        self.tick_ok = self.tick_fail = self.tick_skip = 0
        t0 = time.time()
        try:
            self.client_get()
        except SystemExit as exc:
            logging.error("client init failed code=%s", exc.code)
            self.save_state({"ok": False, "last_error": {"error_kind": "cookie", "last_error": "client init failed"}})
            return
        except Exception as exc:
            kind, msg = classify_error(exc)
            logging.error("client init failed kind=%s err=%s", kind, msg)
            self.save_state({"ok": False, "last_error": {"error_kind": kind, "last_error": msg}})
            return
        self.process_retries()
        self.process_staging()
        elapsed = max(time.time() - t0, 0.001)
        logging.info(
            "tick throughput ok=%s fail=%s skip=%s elapsed=%.2fs rate=%.2f/s",
            self.tick_ok,
            self.tick_fail,
            self.tick_skip,
            elapsed,
            self.tick_ok / elapsed,
        )
        self.save_state()

    def run(self, once: bool = False) -> int:
        logging.info(
            "puller_loop start lab_root=%s device=%s staging=%s keep_hot=%s poll=%ss batch=%s backoff=%s sqlite=%s",
            self.root,
            device_type(),
            self.staging,
            self.keep_hot,
            self.poll,
            self.batch_size,
            self.backoff_sched,
            db_path(),
        )
        self.save_state({"phase": "start"})
        if once:
            self.tick()
            logging.info(
                "puller_loop once done uploaded=%s failed=%s skipped=%s",
                self.uploaded,
                self.failed_n,
                self.skipped,
            )
            return 0
        while not STOP:
            self.tick()
            for _ in range(max(self.poll, 1)):
                if STOP:
                    break
                time.sleep(1)
        logging.info(
            "puller_loop stopped uploaded=%s failed=%s skipped=%s",
            self.uploaded,
            self.failed_n,
            self.skipped,
        )
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="115 lab puller loop (scale)")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    paths = ensure_cache_dirs()
    setup_logging(paths["logs"])
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    raise SystemExit(Puller().run(once=args.once))


if __name__ == "__main__":
    main()
