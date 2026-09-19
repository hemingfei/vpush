"""ARM lab puller_loop: retry wiring, failed/, dry-run. No network."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import puller_loop as puller


@pytest.fixture(autouse=True)
def _isolate_puller_env(monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_STAGING_ROOT", raising=False)
    monkeypatch.delenv("VPUSH_ARM_HOT_ROOT", raising=False)
    monkeypatch.delenv("VPUSH_ARM_FAILED_ROOT", raising=False)
    monkeypatch.delenv("VPUSH_ARM_MANIFEST", raising=False)
    monkeypatch.delenv("VPUSH_115_UPLOAD_CMD", raising=False)
    monkeypatch.delenv("VPUSH_ARM_LAB_PYTHONPATH", raising=False)
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)


def _write_pdf(root: Path, rel: str, payload: bytes = b"%PDF-lab") -> Path:
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return dest


def test_require_upload_ok_raises_on_false_and_empty_filesha1():
    with pytest.raises(puller.UploadError, match="upload_ok"):
        puller.require_upload_ok({"upload_ok": False})
    with pytest.raises(puller.UploadError, match="MultipartUploadAbort"):
        puller.require_upload_ok({"upload_ok": False, "error": "MultipartUploadAbort"})
    with pytest.raises(puller.UploadError, match="empty filesha1"):
        puller.require_upload_ok({"upload_ok": True, "filesha1": ""})
    with pytest.raises(puller.UploadError, match="empty filesha1"):
        puller.require_upload_ok({"upload_ok": True, "filesha1": "null"})
    assert puller.require_upload_ok({"upload_ok": True})["upload_ok"] is True
    assert puller.require_upload_ok({"upload_ok": True, "filesha1": "abc"})["upload_ok"] is True


def test_upload_with_retry_retries_non_ok_then_succeeds():
    sleeps: list[float] = []
    state = {"n": 0}

    def flaky(src: Path, dest_key: str):
        state["n"] += 1
        if state["n"] < 3:
            return {"upload_ok": False, "error": "MultipartUploadAbort"}
        return {"upload_ok": True, "filesha1": "deadbeef", "dest": dest_key}

    result = puller.upload_with_retry(flaky, Path("/tmp/x.pdf"), "/vpush/local/x.pdf", sleeper=sleeps.append)
    assert result["upload_ok"] is True
    assert state["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_empty_filesha1_retries_then_raises():
    sleeps: list[float] = []
    state = {"n": 0}

    def always_empty(src: Path, dest_key: str):
        state["n"] += 1
        return {"upload_ok": True, "filesha1": ""}

    with pytest.raises(puller.UploadError, match="filesha1"):
        puller.upload_with_retry(
            always_empty, Path("/tmp/x.pdf"), "/vpush/local/x.pdf", sleeper=sleeps.append
        )
    assert state["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_non_retryable_raises_immediately():
    sleeps: list[float] = []
    state = {"n": 0}

    def boom(src: Path, dest_key: str):
        state["n"] += 1
        return {"upload_ok": False, "error": "401 unauthorized"}

    with pytest.raises(puller.UploadError, match="401"):
        puller.upload_with_retry(boom, Path("/tmp/x.pdf"), "/vpush/x", sleeper=sleeps.append)
    assert state["n"] == 1
    assert sleeps == []


def test_plan_skips_manifest_hits(tmp_path):
    staging = tmp_path / "staging"
    pdf = _write_pdf(staging, "local/cicc-research/2026/08/01/研报_42.pdf")
    _write_pdf(staging, "local/ima/legacy/2026/09/18/a.pdf")
    manifest = puller.LabManifest(tmp_path / "lab.sqlite")
    planned = puller.plan_uploads(staging, manifest=manifest)
    assert [item.relpath for item in planned] == [
        "local/cicc-research/2026/08/01/研报_42.pdf",
        "local/ima/legacy/2026/09/18/a.pdf",
    ]
    assert planned[0].dest_key == "/vpush/local/cicc-research/2026/08/01/研报_42.pdf"
    manifest.record("local/cicc-research/2026/08/01/研报_42.pdf", size=pdf.stat().st_size)
    planned2 = puller.plan_uploads(staging, manifest=manifest)
    assert [item.relpath for item in planned2] == ["local/ima/legacy/2026/09/18/a.pdf"]
    manifest.close()


def test_dry_run_does_not_create_missing_manifest(tmp_path, capsys):
    staging = tmp_path / "no-such-staging"
    manifest = tmp_path / "does-not-exist" / "lab.sqlite"
    code = puller.main(["--staging-root", str(staging), "--manifest", str(manifest)])
    assert code == 0
    assert "无待上传" in capsys.readouterr().out
    assert not manifest.parent.exists()


def test_dry_run_lists_and_does_not_upload(tmp_path, capsys):
    staging = tmp_path / "cache" / "staging"
    _write_pdf(staging, "local/cicc-research/2026/08/01/a_1.pdf")
    called = {"n": 0}

    def factory():
        def upload(src, dest):
            called["n"] += 1
            raise AssertionError("dry-run must not upload")
        return upload

    code = puller.main(
        ["--staging-root", str(staging), "--manifest", str(tmp_path / "m.sqlite")],
        uploader_factory=factory,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "WOULD UPLOAD" in out
    assert "/vpush/local/cicc-research/2026/08/01/a_1.pdf" in out
    assert called["n"] == 0
    assert (staging / "local/cicc-research/2026/08/01/a_1.pdf").exists()


def test_apply_without_uploader_exits_2(tmp_path, capsys):
    staging = tmp_path / "staging"
    _write_pdf(staging, "local/ima/legacy/2026/09/18/a.pdf")
    code = puller.main([
        "--apply",
        "--staging-root", str(staging),
        "--manifest", str(tmp_path / "m.sqlite"),
        "--failed-root", str(tmp_path / "failed"),
        "--hot-root", str(tmp_path / "hot"),
    ])
    assert code == 2
    assert "uploader" in capsys.readouterr().out
    assert (staging / "local/ima/legacy/2026/09/18/a.pdf").exists()


def test_apply_retries_then_promotes_and_records(tmp_path, capsys):
    staging = tmp_path / "staging"
    src = _write_pdf(staging, "local/cicc-research/2026/08/01/a_1.pdf", b"%PDF-ok")
    src.with_suffix(".json").write_text(json.dumps({"id": "1"}), encoding="utf-8")
    hot = tmp_path / "hot"
    failed = tmp_path / "failed"
    manifest_path = tmp_path / "lab.sqlite"
    state = {"n": 0}
    sleeps: list[float] = []

    def factory():
        def upload(path: Path, dest_key: str):
            state["n"] += 1
            if state["n"] < 2:
                return {"upload_ok": False, "error": "empty filesha1"}
            return {"upload_ok": True, "filesha1": "abc123", "dest": dest_key}
        return upload

    code = puller.main(
        [
            "--apply",
            "--staging-root", str(staging),
            "--hot-root", str(hot),
            "--failed-root", str(failed),
            "--manifest", str(manifest_path),
        ],
        uploader_factory=factory,
        sleeper=sleeps.append,
    )
    assert code == 0
    assert state["n"] == 2
    assert sleeps == [1.0]
    assert src.exists()
    assert (hot / "local/cicc-research/2026/08/01/a_1.pdf").read_bytes() == b"%PDF-ok"
    assert (hot / "local/cicc-research/2026/08/01/a_1.json").exists()
    assert not list(failed.rglob("*.pdf"))
    manifest = puller.LabManifest(manifest_path)
    assert manifest.has("local/cicc-research/2026/08/01/a_1.pdf", src.stat().st_size)
    manifest.close()
    assert "UPLOAD" in capsys.readouterr().out


def test_apply_moves_to_failed_after_retries(tmp_path):
    staging = tmp_path / "staging"
    src = _write_pdf(staging, "local/ima/legacy/2026/09/18/b.pdf")
    failed = tmp_path / "failed"
    sleeps: list[float] = []

    def factory():
        def upload(path: Path, dest_key: str):
            return {"upload_ok": False, "error": "MultipartUploadAbort: part timeout"}
        return upload

    code = puller.main(
        [
            "--apply",
            "--staging-root", str(staging),
            "--failed-root", str(failed),
            "--hot-root", str(tmp_path / "hot"),
            "--manifest", str(tmp_path / "m.sqlite"),
        ],
        uploader_factory=factory,
        sleeper=sleeps.append,
    )
    assert code == 1
    assert sleeps == [1.0, 2.0]
    assert not src.exists()
    moved = failed / "local/ima/legacy/2026/09/18/b.pdf"
    assert moved.is_file()


def test_compose_still_default_off():
    root = Path(__file__).resolve().parents[1]
    for name in ("docker-compose.yml", "docker-compose.prod.yml", "docker-compose.unraid.yml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "VPUSH_ARM_MIDDLEWARE=1" not in text
        assert "puller_loop" not in text
        assert "VPUSH_115_UPLOAD_CMD" not in text
