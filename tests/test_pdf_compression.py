"""PDF v3 compression state, migration, and replacement safety."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pdf_backfill_compress.py"
INSTALLER = ROOT / "scripts" / "vps" / "install_compress_hourly.sh"
SPEC = importlib.util.spec_from_file_location("pdf_backfill_compress", SCRIPT)
compressor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(compressor)


def _pdf(path: Path, body: bytes = b"payload", *, marker: bool = False) -> None:
    data = b"%PDF-1.7\n" + body
    if marker:
        data += compressor.IMA_FLAT_MARKER
    path.write_bytes(data)
    old = time.time() - compressor.FRESH_SEC - 10
    os.utime(path, (old, old))


def test_legacy_state_rechecks_large_ima_flat_only(tmp_path, monkeypatch):
    ordinary = tmp_path / "ordinary.pdf"
    ima = tmp_path / "ima.pdf"
    small_ima = tmp_path / "small-ima.pdf"
    _pdf(ordinary)
    _pdf(ima, b"x" * compressor.IMA_FLAT_MIN_BYTES)
    _pdf(small_ima, marker=True)
    state = tmp_path / "state.json"
    state.write_text(json.dumps([str(ordinary), str(ima), str(small_ima)]))
    monkeypatch.setattr(
        compressor, "is_ima_flat_path",
        lambda path, size: path == str(ima) and size >= compressor.IMA_FLAT_MIN_BYTES,
    )

    files = compressor.scan_files(str(tmp_path))
    records, migrated = compressor.load_state(str(state), str(tmp_path), files)

    assert migrated is True
    assert str(ordinary) in records
    assert str(small_ima) in records
    assert str(ima) not in records
    assert compressor.record_matches(records[str(ordinary)], ordinary.stat())


def test_default_state_isolated_per_root(tmp_path):
    full = compressor.default_state_path(compressor.ROOT)
    local = compressor.default_state_path(str(tmp_path / "local"))

    assert full == compressor.STATE
    assert local != full
    assert local.endswith(".json")


def test_v2_state_for_other_root_is_not_reused(tmp_path):
    file_path = tmp_path / "report.pdf"
    _pdf(file_path)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "version": compressor.STRATEGY_VERSION,
        "root": "/different/root",
        "files": {str(file_path): compressor.state_record(file_path.stat(), "legacy_v1")},
    }))

    records, migrated = compressor.load_state(
        str(state), str(tmp_path), compressor.scan_files(str(tmp_path)))

    assert records == {}
    assert migrated is True


def test_v2_state_migrates_without_reprocessing(tmp_path):
    file_path = tmp_path / "report.pdf"
    _pdf(file_path)
    old_record = compressor.state_record(file_path.stat(), "legacy_v1")
    old_record["strategy_version"] = 2
    state = tmp_path / "state.json"
    state.write_text(json.dumps({
        "version": 2,
        "root": str(tmp_path),
        "files": {str(file_path): old_record},
    }))

    records, migrated = compressor.load_state(
        str(state), str(tmp_path), compressor.scan_files(str(tmp_path)))

    assert migrated is True
    assert compressor.record_matches(records[str(file_path)], file_path.stat())


def test_record_invalidates_when_file_is_replaced(tmp_path):
    path = tmp_path / "report.pdf"
    _pdf(path, b"old")
    record = compressor.state_record(path.stat(), "ratio_rejected")

    replacement = tmp_path / "replacement.pdf"
    _pdf(replacement, b"new content")
    os.replace(replacement, path)

    assert not compressor.record_matches(record, path.stat())


def test_directory_lock_blocks_other_process(tmp_path):
    path = tmp_path / "report.pdf"
    _pdf(path)
    code = (
        "import fcntl, os, sys; "
        "fd=os.open(sys.argv[1], os.O_RDONLY); "
        "fcntl.flock(fd, fcntl.LOCK_EX); print('locked', flush=True); "
        "sys.stdin.read(1)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "locked"

        def release():
            time.sleep(0.2)
            process.stdin.write("x")
            process.stdin.flush()

        threading.Thread(target=release, daemon=True).start()
        started = time.monotonic()
        with compressor.path_lock(str(path)):
            pass
        assert time.monotonic() - started >= 0.15
    finally:
        if process.poll() is None:
            process.stdin.write("x")
            process.stdin.flush()
        process.wait(timeout=5)


def test_replace_pdf_refuses_changed_source(tmp_path):
    path = tmp_path / "report.pdf"
    _pdf(path, b"old")
    original = path.stat()
    _pdf(path, b"new")

    replaced, reason, replaced_stat = compressor.replace_pdf(
        path, b"%PDF-1.7\ncompressed", original)

    assert (replaced, reason, replaced_stat) == (False, "source_changed", None)
    assert path.read_bytes().endswith(b"new")


def test_replace_pdf_returns_replaced_file_fingerprint(tmp_path):
    path = tmp_path / "report.pdf"
    _pdf(path, b"old")
    original = path.stat()

    replaced, reason, replaced_stat = compressor.replace_pdf(
        path, b"%PDF-1.7\ncompressed", original)

    assert (replaced, reason) == (True, "")
    assert replaced_stat is not None
    assert replaced_stat.st_ino == path.stat().st_ino
    assert replaced_stat.st_size == path.stat().st_size
    assert path.read_bytes().endswith(b"compressed")


def test_run_records_rejection_and_retries_transient_error(tmp_path, monkeypatch):
    rejected = tmp_path / "rejected.pdf"
    transient = tmp_path / "transient.pdf"
    _pdf(rejected)
    _pdf(transient)
    state = tmp_path / "state.json"

    def fake_compress(data):
        if data.endswith(b"payload"):
            fake_compress.calls += 1
            if fake_compress.calls == 1:
                return data, "ratio_rejected"
        return data, "gs_error"

    fake_compress.calls = 0
    monkeypatch.setattr(compressor, "compress_pdf_result", fake_compress)
    compressor.run(Namespace(root=str(tmp_path), state=str(state), limit=0, dry_run=False))

    payload = json.loads(state.read_text())
    records = payload["files"]
    assert payload["version"] == compressor.STRATEGY_VERSION
    assert payload["root"] == str(tmp_path)
    assert len(records) == 1
    assert next(iter(records.values()))["result"] == "ratio_rejected"


def test_run_retries_verifier_failures(tmp_path, monkeypatch):
    transient = tmp_path / "transient.pdf"
    _pdf(transient)
    state = tmp_path / "state.json"
    monkeypatch.setattr(
        compressor, "compress_pdf_result", lambda data: (data, "verify_error"))

    compressor.run(Namespace(root=str(tmp_path), state=str(state), limit=0, dry_run=False))

    assert json.loads(state.read_text())["files"] == {}


def test_run_strips_watermark_even_when_compression_is_rejected(tmp_path, monkeypatch):
    report = tmp_path / "report.pdf"
    _pdf(report, b"watermarked")
    state = tmp_path / "state.json"
    stripped = b"%PDF-1.7\nclean"
    monkeypatch.setattr(
        compressor, "strip_watermark_result",
        lambda data: (stripped, "watermark_stripped"),
    )
    monkeypatch.setattr(
        compressor, "compress_pdf_result", lambda data: (data, "ratio_rejected"))

    compressor.run(Namespace(
        root=str(tmp_path), state=str(state), limit=0, dry_run=False,
        strip_watermark=True,
    ))

    assert report.read_bytes() == stripped
    record = json.loads(state.read_text())["files"][str(report)]
    assert record["result"] == "watermark_stripped"


def test_run_retries_watermark_failures(tmp_path, monkeypatch):
    report = tmp_path / "report.pdf"
    _pdf(report)
    state = tmp_path / "state.json"
    monkeypatch.setattr(
        compressor, "strip_watermark_result",
        lambda data: (data, "watermark_error"),
    )

    compressor.run(Namespace(
        root=str(tmp_path), state=str(state), limit=0, dry_run=False,
        strip_watermark=True,
    ))

    assert json.loads(state.read_text())["files"] == {}


def test_hourly_timer_installer_keeps_jobs_low_priority():
    text = INSTALLER.read_text()
    assert "OnCalendar=hourly" in text
    assert "nice -n 19" in text
    assert "ionice -c2 -n7" in text
    assert "vpush-compress-hourly.timer" in text
    assert "disable --now vpush-compress-monthly.timer" in text
    assert "stop vpush-compress-monthly.service" in text
    assert "stop vpush-compress-hourly.service" in text
    assert "scripts/cicc_report_collector.py" in text
    assert "scripts/pdf_backfill_compress.py" in text
    assert "scripts/vps/ima-puller.py" in text
    assert "scripts/vps/cicc-dispatch.py" in text
    assert "vpush-cicc-pdf-daily.timer" in text
    assert "06:15:00 Asia/Shanghai" in text
    assert "/srv/vpush-ima/local/cicc-research --strip-watermark" in text


def test_atomic_state_write_round_trip(tmp_path):
    state = tmp_path / "state.json"
    payload = {"version": compressor.STRATEGY_VERSION, "root": str(tmp_path),
               "files": {"/x.pdf": {"size": 1}}}

    compressor.atomic_write_json(str(state), payload)

    assert json.loads(state.read_text()) == payload
    assert not list(tmp_path.glob(".compress-state-*"))
