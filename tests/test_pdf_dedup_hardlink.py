"""PDF hardlink deduplication safety and idempotency."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pdf_dedup_hardlink.py"
SPEC = importlib.util.spec_from_file_location("pdf_dedup_hardlink", SCRIPT)
dedup = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(dedup)


def _pdf(path: Path, body: bytes) -> None:
    path.write_bytes(b"%PDF-1.7\n" + body)
    old = time.time() - dedup.FRESH_SEC - 10
    os.utime(path, (old, old))


def _no_xattrs(monkeypatch) -> None:
    monkeypatch.setattr(dedup, "file_xattrs", lambda _path: {})


def test_apply_merges_distinct_inodes_and_second_run_is_idempotent(
    tmp_path, monkeypatch
):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    _pdf(first, b"same")
    _pdf(second, b"same")
    assert first.stat().st_ino != second.stat().st_ino
    monkeypatch.setattr(dedup, "EXCLUDE", ())
    _no_xattrs(monkeypatch)

    stats = dedup.run(str(tmp_path), True)
    again = dedup.run(str(tmp_path), True)

    assert first.stat().st_ino == second.stat().st_ino
    assert stats["linked"] == 1
    assert stats["bytes"] == first.stat().st_size
    assert again["linked"] == 0
    assert not list(tmp_path.glob("*.dedup-tmp"))
    assert not list(tmp_path.glob(".dedup-*"))


def test_cleanup_only_removes_temp_with_live_pdf_inode(tmp_path, monkeypatch):
    report = tmp_path / "report.pdf"
    _pdf(report, b"same")
    safe = tmp_path / "report.pdf.dedup-tmp"
    unsafe = tmp_path / "orphan.pdf.dedup-tmp"
    os.link(report, safe)
    unsafe.write_bytes(b"orphan")
    monkeypatch.setattr(dedup, "EXCLUDE", ())
    _no_xattrs(monkeypatch)

    stats = dedup.run(str(tmp_path), True)

    assert stats["cleaned"] == 1
    assert not safe.exists()
    assert unsafe.exists()
    assert report.read_bytes().endswith(b"same")


def test_cleanup_recognizes_new_temp_name(tmp_path, monkeypatch):
    report = tmp_path / "report.pdf"
    _pdf(report, b"same")
    temp = tmp_path / ".dedup-123-deadbeefdeadbeef"
    os.link(report, temp)
    monkeypatch.setattr(dedup, "EXCLUDE", ())
    _no_xattrs(monkeypatch)

    stats = dedup.run(str(tmp_path), True)

    assert stats["cleaned"] == 1
    assert not temp.exists()
    assert report.exists()


def test_different_xattrs_are_not_merged(tmp_path, monkeypatch):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    _pdf(first, b"same")
    _pdf(second, b"same")
    monkeypatch.setattr(dedup, "EXCLUDE", ())
    monkeypatch.setattr(
        dedup,
        "file_xattrs",
        lambda path: {"user.dedup-test": Path(path).name.encode()},
    )

    stats = dedup.run(str(tmp_path), True)

    assert stats["linked"] == 0
    assert stats["skip_meta"] == 1
    assert first.stat().st_ino != second.stat().st_ino


def test_partial_link_failure_is_counted_per_path(tmp_path, monkeypatch):
    keep = tmp_path / "a.pdf"
    duplicate = tmp_path / "b.pdf"
    linked_duplicate = tmp_path / "c.pdf"
    _pdf(keep, b"same")
    _pdf(duplicate, b"same")
    os.link(duplicate, linked_duplicate)
    monkeypatch.setattr(dedup, "EXCLUDE", ())
    _no_xattrs(monkeypatch)
    real_link_path = dedup.link_path
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected")
        return real_link_path(source, destination)

    monkeypatch.setattr(dedup, "link_path", fail_second)

    stats = dedup.run(str(tmp_path), True)

    assert stats["linked"] == 1
    assert stats["race"] == 1
    assert keep.stat().st_ino in {
        duplicate.stat().st_ino,
        linked_duplicate.stat().st_ino,
    }
    assert duplicate.read_bytes() == linked_duplicate.read_bytes() == keep.read_bytes()


def test_main_dry_run_does_not_create_lock_file(tmp_path):
    report = tmp_path / "report.pdf"
    _pdf(report, b"same")
    lock = tmp_path / "missing" / "compress_global.lock"

    code = (
        "import importlib.util,sys;"
        f"s=importlib.util.spec_from_file_location('dedup',{str(SCRIPT)!r});"
        "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
        f"m.GLOBAL_LOCK={str(lock)!r};sys.argv=['dedup','--root',{str(tmp_path)!r}];"
        "m.main()"
    )
    subprocess.run([sys.executable, "-c", code], check=True)

    assert not lock.exists()


def test_dry_run_does_not_replace_files(tmp_path, monkeypatch):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    _pdf(first, b"same")
    _pdf(second, b"same")
    before = (first.stat().st_ino, second.stat().st_ino)
    monkeypatch.setattr(dedup, "EXCLUDE", ())
    _no_xattrs(monkeypatch)

    stats = dedup.run(str(tmp_path), False)

    assert stats["linked"] == 1
    assert (first.stat().st_ino, second.stat().st_ino) == before
