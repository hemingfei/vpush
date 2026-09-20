"""ARM cache_gc: watermark, protect un-uploaded staging. No network."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cache_gc  # noqa: E402
import manifest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    monkeypatch.setenv("CACHE_ROOT", str(cache))
    monkeypatch.delenv("GC_PURGE_FAILED", raising=False)
    monkeypatch.delenv("GC_ALLOW_UNUPLOADED_STAGING", raising=False)
    monkeypatch.delenv("GC_MIN_AGE_SECONDS", raising=False)
    yield cache


def _write(root: Path, rel: str, size: int, mtime: int | None = None) -> Path:
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(dest, (mtime, mtime))
    return dest


def test_below_force_does_not_delete(_isolate_cache):
    cache = _isolate_cache
    hot = _write(cache, "hot/local/keep.pdf", 8_000, mtime=1)
    result = cache_gc.run_gc(
        root=cache, warn=80_000, force=200_000, purge_failed=False, dry_run=False, min_age=0
    )
    assert result["ok"] is True
    assert result["forced"] is False
    assert result["deleted"] == []
    assert hot.is_file()


def test_force_deletes_uploaded_hot_keeps_pending(_isolate_cache):
    cache = _isolate_cache
    uploaded = _write(cache, "hot/local/done.pdf", 100_000, mtime=1)
    pending = _write(cache, "hot/local/pending.pdf", 10_000, mtime=2)
    manifest.mark_uploaded("local/done.pdf", sha1="done", size=100_000)
    result = cache_gc.run_gc(
        root=cache, warn=20_000, force=40_000, purge_failed=False, dry_run=False, min_age=0
    )
    assert uploaded.is_file() is False
    assert pending.is_file()
    assert "hot_not_uploaded" in {row["reason"] for row in result["protected"]}


def test_skips_unuploaded_hot(_isolate_cache):
    cache = _isolate_cache
    pending = _write(cache, "hot/local/pending.pdf", 100_000, mtime=1)
    result = cache_gc.run_gc(
        root=cache, warn=20_000, force=40_000, purge_failed=False, dry_run=False, min_age=0
    )
    assert pending.is_file()
    reasons = {row["reason"] for row in result["protected"]}
    assert "hot_not_uploaded" in reasons
    assert result["ok"] is False
    assert result["message"] == "still_over_force"


def test_skips_unuploaded_staging(_isolate_cache):
    cache = _isolate_cache
    pending = _write(cache, "staging/local/pending.pdf", 100_000, mtime=1)
    result = cache_gc.run_gc(
        root=cache, warn=20_000, force=40_000, purge_failed=False, dry_run=False, min_age=0
    )
    assert pending.is_file()
    reasons = {row["reason"] for row in result["protected"]}
    assert "not_uploaded" in reasons
    assert result["ok"] is False
    assert result["message"] == "still_over_force"


def test_deletes_uploaded_staging(_isolate_cache):
    cache = _isolate_cache
    done = _write(cache, "staging/local/done.pdf", 100_000, mtime=1)
    manifest.mark_uploaded("local/done.pdf", sha1="abc", size=100_000)
    result = cache_gc.run_gc(
        root=cache, warn=20_000, force=40_000, purge_failed=False, dry_run=False, min_age=0
    )
    assert done.is_file() is False
    assert result["deleted"]
    assert result["protected"] == []


def test_dry_run_leaves_hot(_isolate_cache):
    cache = _isolate_cache
    hot = _write(cache, "hot/local/a.pdf", 100_000, mtime=1)
    manifest.mark_uploaded("local/a.pdf", sha1="abc", size=100_000)
    result = cache_gc.run_gc(
        root=cache, warn=20_000, force=40_000, purge_failed=False, dry_run=True, min_age=0
    )
    assert hot.is_file()
    assert result["deleted"]
    assert result["ok"] is True


def test_min_age_skips_recent_hot(_isolate_cache):
    cache = _isolate_cache
    hot = _write(cache, "hot/local/fresh.pdf", 100_000)
    result = cache_gc.run_gc(
        root=cache, warn=20_000, force=40_000, purge_failed=False, dry_run=False, min_age=3600
    )
    assert hot.is_file()
    assert result["deleted"] == []


def test_failed_protected_unless_purge(_isolate_cache):
    cache = _isolate_cache
    failed = _write(cache, "failed/local/x.pdf", 100_000, mtime=1)
    result = cache_gc.run_gc(
        root=cache, warn=20_000, force=40_000, purge_failed=False, dry_run=False, min_age=0
    )
    assert failed.is_file()
    result2 = cache_gc.run_gc(
        root=cache, warn=20_000, force=40_000, purge_failed=True, dry_run=False, min_age=0
    )
    assert failed.is_file() is False
    assert result2["deleted"]


def test_allow_unuploaded_staging_is_opt_in(_isolate_cache):
    cache = _isolate_cache
    pending = _write(cache, "staging/local/pending.pdf", 100_000, mtime=1)
    result = cache_gc.run_gc(
        root=cache,
        warn=20_000,
        force=40_000,
        purge_failed=False,
        dry_run=False,
        min_age=0,
        allow_unuploaded=True,
    )
    assert pending.is_file() is False
    assert result["deleted"]


def test_manifest_unread_protects_staging(monkeypatch, _isolate_cache):
    cache = _isolate_cache
    pending = _write(cache, "staging/local/pending.pdf", 100_000, mtime=1)

    monkeypatch.setattr(cache_gc, "load_uploaded_rels", lambda: (set(), False))
    result = cache_gc.run_gc(
        root=cache, warn=20_000, force=40_000, purge_failed=False, dry_run=False, min_age=0
    )
    assert pending.is_file()
    assert any(row["reason"] == "manifest_unread" for row in result["protected"])


def test_cli_writes_gc_last(_isolate_cache):
    cache = _isolate_cache
    _write(cache, "hot/local/a.pdf", 50, mtime=1)
    code = cache_gc.main(["--dry-run", "--warn-gb", "30", "--force-gb", "35", "--min-age-seconds", "0"])
    assert code == 0
    assert (cache / "manifest" / "gc-last.json").is_file()
