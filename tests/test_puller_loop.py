"""ARM host puller_loop / lab_common / manifest: retry wiring, fakes, no network."""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import lab_common  # noqa: E402
import manifest  # noqa: E402
import puller_loop as puller  # noqa: E402
import puller_retry as retry  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_puller_env(monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    monkeypatch.setenv("CACHE_ROOT", str(cache))
    monkeypatch.setenv("P115_COOKIES_FILE", str(tmp_path / "missing-115-cookies.txt"))
    monkeypatch.setenv("P115_LAB_ROOT", "/vpush")
    monkeypatch.setenv("PULLER_STABLE_SECONDS", "0")
    monkeypatch.setenv("PULLER_BATCH_SIZE", "20")
    monkeypatch.setenv("PULLER_KEEP_HOT", "1")
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    yield


def _write_pdf(root: Path, rel: str, payload: bytes = b"%PDF-lab") -> Path:
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return dest


class FakeClient:
    def __init__(self, results: list):
        self.results = list(results)
        self.uploads: list[tuple] = []

    def fs_dir_getid2(self, body):
        return {"state": True, "data": {"file_id": 7}}

    def fs_files(self, body):
        return {"data": []}

    def fs_mkdir(self, body):
        return {"cid": 8}

    def upload_file(self, src, pid=None, filename=None):
        self.uploads.append((src, pid, filename))
        if not self.results:
            raise AssertionError("unexpected extra upload_file call")
        item = self.results.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _puller_with_client(client) -> puller.Puller:
    worker = puller.Puller()
    worker.client = client
    worker.stable_secs = 0
    return worker


def _patch_retry_sleeper(monkeypatch, sleeps: list[float]) -> None:
    """call_with_retry binds time.sleep at import; inject sleeper without editing host code."""
    orig = puller.call_with_retry

    def wrapped(fn, **kwargs):
        kwargs.setdefault("sleeper", sleeps.append)
        return orig(fn, **kwargs)

    monkeypatch.setattr(puller, "call_with_retry", wrapped)


@pytest.mark.parametrize("payload,expected", [
    ({"state": True, "file_id": 1}, True),
    ({"state": True}, True),
    ({"pickcode": "x", "state": False}, True),
    ({"errno": 99, "state": False}, False),
    ({"errno": 1, "state": False, "error": "empty filesha1"}, False),
    ("not-a-dict", False),
    (None, False),
])
def test_upload_ok_matches_host(payload, expected):
    assert lab_common.upload_ok(payload) is expected


def test_non_ok_result_raises_so_retry_can_see_filesha1():
    sleeps: list[float] = []
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        result = {"state": False, "errno": 1, "error": "empty filesha1"}
        if not lab_common.upload_ok(result):
            raise RuntimeError(f"upload rejected errno=1 body={result!r}")
        return result

    with pytest.raises(RuntimeError, match="filesha1"):
        retry.call_with_retry(flaky, sleeper=sleeps.append)
    assert state["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_upload_one_retries_multipart_then_records(tmp_path, monkeypatch):
    sleeps: list[float] = []
    _patch_retry_sleeper(monkeypatch, sleeps)
    staging = lab_common.cache_root() / "staging"
    src = _write_pdf(staging, "local/cicc-research/2026/08/01/a_1.pdf", b"%PDF-ok")
    client = FakeClient([
        RuntimeError("115 MultipartUploadAbort: part timeout"),
        {"state": True, "file_id": 99, "pickcode": "pc"},
    ])
    worker = _puller_with_client(client)
    rel = lab_common.rel_under(src, worker.staging)
    assert worker.upload_one(src, rel, attempts=1, source="staging") is True
    assert len(client.uploads) == 2
    assert sleeps == [1.0]
    assert not src.exists()
    hot = worker.hot / rel
    assert hot.read_bytes() == b"%PDF-ok"
    assert stat.S_IMODE(hot.stat().st_mode) == 0o664
    row = manifest.get_by_rel(rel.as_posix())
    assert row is not None
    assert row["status"] == "hot"
    assert row["remote_cid"] == "99"


def test_upload_one_empty_filesha1_retries_then_failed(tmp_path, monkeypatch):
    sleeps: list[float] = []
    _patch_retry_sleeper(monkeypatch, sleeps)
    staging = lab_common.cache_root() / "staging"
    src = _write_pdf(staging, "local/ima/legacy/2026/09/18/b.pdf")
    reject = {"state": False, "errno": 1, "error": "empty filesha1"}
    client = FakeClient([reject, reject, reject])
    worker = _puller_with_client(client)
    rel = lab_common.rel_under(src, worker.staging)
    assert worker.upload_one(src, rel, attempts=1, source="staging") is False
    assert len(client.uploads) == 3
    assert sleeps == [1.0, 2.0]
    assert not src.exists()
    failed = worker.failed / rel
    assert failed.is_file()
    assert (failed.parent / (failed.name + lab_common.RETRY_SUFFIX)).is_file()
    row = manifest.get_by_rel(rel.as_posix())
    assert row is not None
    assert row["status"] == "failed"


def test_non_retryable_fails_immediately(tmp_path, monkeypatch):
    sleeps: list[float] = []
    _patch_retry_sleeper(monkeypatch, sleeps)
    staging = lab_common.cache_root() / "staging"
    src = _write_pdf(staging, "local/ima/legacy/2026/09/18/c.pdf")
    client = FakeClient([RuntimeError("401 unauthorized")])
    worker = _puller_with_client(client)
    rel = lab_common.rel_under(src, worker.staging)
    assert worker.upload_one(src, rel, attempts=1, source="staging") is False
    assert len(client.uploads) == 1
    assert sleeps == []
    assert (worker.failed / rel).is_file()


def test_discover_skips_already_uploaded(tmp_path):
    staging = lab_common.cache_root() / "staging"
    src = _write_pdf(staging, "local/cicc-research/2026/08/01/done.pdf")
    sha = lab_common.file_sha1(src)
    manifest.mark_uploaded(lab_common.rel_under(src, staging).as_posix(), sha1=sha, size=src.stat().st_size)
    worker = _puller_with_client(FakeClient([]))
    assert worker.discover_batch() == []
    assert worker.skipped == 1
    assert not src.exists()
    assert (worker.hot / "local/cicc-research/2026/08/01/done.pdf").is_file()


def test_process_staging_uploads_pending(tmp_path, monkeypatch):
    _patch_retry_sleeper(monkeypatch, [])
    staging = lab_common.cache_root() / "staging"
    _write_pdf(staging, "local/cicc-research/2026/08/01/new.pdf")
    client = FakeClient([{"state": True, "file_id": 3, "pickcode": "z"}])
    worker = _puller_with_client(client)
    assert worker.process_staging() == 1
    assert worker.uploaded == 1
    assert client.uploads


def test_redact_and_load_cookies_never_echo_values(tmp_path, capsys):
    raw = "UID=fixture-not-real; CID=fixture-not-real"
    assert "fixture-not-real" not in lab_common.redact(raw)
    assert "UID=<redacted>" in lab_common.redact(raw)
    cookie = tmp_path / "115-cookies.txt"
    cookie.write_text("offline-fixture-not-a-real-cookie", encoding="utf-8")
    assert lab_common.load_cookies(cookie) == "offline-fixture-not-a-real-cookie"
    with pytest.raises(SystemExit) as exc:
        lab_common.load_cookies(tmp_path / "absent.txt")
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "cookies file missing" in err
    assert "offline-fixture-not-a-real-cookie" not in err


def test_cookies_loaded_from_secrets_path_only():
    text = (SCRIPTS / "lab_common.py").read_text(encoding="utf-8")
    assert 'env_str("P115_COOKIES_FILE", "/secrets/115-cookies.txt")' in text
    assert "load_cookies" in text
    assert "UID=; CID=" not in text
    assert "make_client" in (SCRIPTS / "lab_common.py").read_text(encoding="utf-8")


def test_cicc_research_rel_date_shard():
    from datetime import UTC, datetime

    when = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    assert lab_common.cicc_research_rel("id-42", when=when) == (
        "local/cicc-research/2026/08/01/id-42.pdf"
    )


def test_manifest_is_done_and_counts(tmp_path):
    manifest.upsert_file("local/a.pdf", sha1="aaa", size=3, status="staging")
    assert manifest.is_done("local/a.pdf") is False
    manifest.mark_uploaded("local/a.pdf", sha1="aaa", size=3)
    assert manifest.is_done("local/a.pdf", sha1="aaa") is True
    assert manifest.is_done("local/a.pdf", sha1="bbb") is False
    counts = manifest.counts_by_status()
    assert counts["hot"] == 1


def test_to_hot_chmods_file_0664_and_parents_at_least_0775(tmp_path):
    staging = lab_common.cache_root() / "staging"
    src = _write_pdf(staging, "local/ima/legacy/2026/09/19/locked.pdf", b"%PDF-ima")
    src.chmod(0o600)
    worker = _puller_with_client(FakeClient([]))
    worker.hot.chmod(0o755)
    rel = lab_common.rel_under(src, worker.staging)
    worker.to_hot(src, rel)
    dest = worker.hot / rel
    assert dest.is_file()
    assert dest.read_bytes() == b"%PDF-ima"
    assert stat.S_IMODE(dest.stat().st_mode) == puller.HOT_FILE_MODE
    parent = dest.parent
    while True:
        mode = stat.S_IMODE(parent.stat().st_mode)
        assert mode & puller.HOT_DIR_MODE == puller.HOT_DIR_MODE
        if parent == worker.hot:
            break
        parent = parent.parent


def test_ensure_hot_modes_is_umask_friendly(tmp_path):
    dest = tmp_path / "hot" / "local" / "a.pdf"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"%PDF")
    dest.chmod(0o600)
    dest.parent.chmod(0o700)
    (tmp_path / "hot").chmod(0o755)
    puller.ensure_hot_modes(dest, stop_at=tmp_path / "hot")
    assert stat.S_IMODE(dest.stat().st_mode) == 0o664
    assert stat.S_IMODE(dest.parent.stat().st_mode) & 0o775 == 0o775
    assert stat.S_IMODE((tmp_path / "hot").stat().st_mode) & 0o775 == 0o775


def test_resolve_batch_size_prefers_settings_json(tmp_path, monkeypatch):
    cache = lab_common.cache_root()
    cache.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("PULLER_BATCH_SIZE", "20")
    assert puller.resolve_batch_size() == 20
    (cache / puller.OPS_LAB_SETTINGS_NAME).write_text(
        json.dumps({"puller_batch_size": 40}),
        encoding="utf-8",
    )
    assert puller.resolve_batch_size() == 40
    (cache / puller.OPS_LAB_SETTINGS_NAME).write_text(
        json.dumps({"puller_batch_size": 999}),
        encoding="utf-8",
    )
    assert puller.resolve_batch_size() == puller.PULLER_BATCH_MAX


def test_compose_still_default_off():
    root = Path(__file__).resolve().parents[1]
    for name in ("docker-compose.yml", "docker-compose.prod.yml", "docker-compose.unraid.yml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "VPUSH_ARM_MIDDLEWARE=1" not in text
        assert "puller_loop" not in text
        assert "P115_COOKIES_FILE" not in text
        assert "CACHE_ROOT=/cache" not in text
