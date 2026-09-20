from __future__ import annotations

import urllib.request

from app.archive_guard import (
    CircuitBreaker,
    archive_fetch_url,
    archive_list_url,
    fetch_missing_archive_file,
    is_remote_nfs,
    list_archive_prefix,
    path_without_stat,
    reset_arm_circuit,
)
from app.cicc_collector import CiccControl, CiccIsolatedError
from app.ima_documents import ImaDocumentStore, archive_lock
from app.ima_storage import ImaStorageStatus


MOUNTS = """
/dev/sda1 / ext4 rw 0 0
10.80.0.2:/srv/vpush-ima /mnt/vpush-ima nfs4 rw,relatime 0 0
/dev/sdb1 /data ext4 rw 0 0
"""


def test_is_remote_nfs_uses_longest_mount():
    assert is_remote_nfs("/mnt/vpush-ima", MOUNTS) is True
    assert is_remote_nfs("/mnt/vpush-ima/local/.cicc", MOUNTS) is True
    assert is_remote_nfs("/data/ima", MOUNTS) is False
    assert is_remote_nfs("/tmp", MOUNTS) is False


def test_path_without_stat_is_absolute(tmp_path):
    path = path_without_stat(tmp_path / "nested")
    assert path.is_absolute()
    assert path.name == "nested"


def test_circuit_opens_after_failures():
    breaker = CircuitBreaker(failures=2, cooldown=60)
    assert breaker.allow() is True
    breaker.failure()
    assert breaker.allow() is True
    breaker.failure()
    assert breaker.allow() is False
    breaker.reset()
    assert breaker.allow() is True


def test_archive_fetch_url_rewrites_pull(monkeypatch):
    monkeypatch.delenv("IMA_FETCH_URL", raising=False)
    monkeypatch.delenv("IMA_LIST_URL", raising=False)
    monkeypatch.setenv("IMA_PULL_URL", "http://100.112.25.21:8743/pull")
    assert archive_fetch_url() == "http://100.112.25.21:8743/file"
    assert archive_list_url() == "http://100.112.25.21:8743/list"


def test_fetch_missing_skips_nfs(tmp_path, monkeypatch):
    monkeypatch.setenv("IMA_PULL_URL", "http://10.80.0.2:8743/pull")
    monkeypatch.setenv("IMA_PULL_TOKEN", "tok")
    monkeypatch.setattr(
        "app.archive_guard.is_remote_nfs",
        lambda path, mounts_text=None: True,
    )
    assert fetch_missing_archive_file(tmp_path, "g/a.pdf") is None


def test_fetch_missing_writes_local_file(tmp_path, monkeypatch):
    reset_arm_circuit()
    monkeypatch.setenv("IMA_PULL_URL", "http://100.112.25.21:8743/pull")
    monkeypatch.setenv("IMA_PULL_TOKEN", "tok")
    monkeypatch.setattr("app.archive_guard.is_remote_nfs", lambda *args, **kwargs: False)

    class Resp:
        def read(self):
            return b"%PDF-1.7fetch"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=5):
        assert "dest=g%2Fa.pdf" in req.full_url or "dest=g/a.pdf" in req.full_url
        assert req.get_header("Authorization") == "Bearer tok"
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    path = fetch_missing_archive_file(tmp_path, "g/a.pdf")
    assert path is not None
    assert path.read_bytes() == b"%PDF-1.7fetch"


def test_fetch_missing_allows_local_json(tmp_path, monkeypatch):
    reset_arm_circuit()
    monkeypatch.setenv("IMA_PULL_URL", "http://100.112.25.21:8743/pull")
    monkeypatch.setenv("IMA_PULL_TOKEN", "tok")
    monkeypatch.setattr("app.archive_guard.is_remote_nfs", lambda *args, **kwargs: False)

    class Resp:
        def read(self):
            return b'{"id":"1"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=5: Resp())
    path = fetch_missing_archive_file(tmp_path, "local/cicc-research/a.json")
    assert path is not None
    assert path.read_bytes() == b'{"id":"1"}'
    assert fetch_missing_archive_file(tmp_path, "secrets.json") is None


def test_list_archive_prefix_filters_escape(monkeypatch):
    reset_arm_circuit()
    monkeypatch.setenv("IMA_PULL_URL", "http://100.112.25.21:8743/pull")
    monkeypatch.setenv("IMA_PULL_TOKEN", "tok")

    class Resp:
        def read(self):
            return (
                b'{"files":[{"dest":"local/cicc-research/a.pdf","size":3},'
                b'{"dest":"../etc/passwd","size":1}]}'
            )

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=5: Resp())
    files = list_archive_prefix("local/cicc-research")
    assert files == [{"dest": "local/cicc-research/a.pdf", "size": 3}]


def test_store_refuses_nfs_without_statting(tmp_path, monkeypatch):
    archive = tmp_path / "nfs-archive"
    monkeypatch.setattr("app.ima_documents.is_remote_nfs", lambda path, mounts_text=None: True)
    store = ImaDocumentStore(
        tmp_path / "index",
        archive_root=archive,
        storage_status=ImaStorageStatus(None, remote=True),
    )
    assert store._nfs_isolated is True
    assert store.archive_nfs_isolated() is True
    assert store.archive_readable() is False
    assert store.archive_writable() is False
    assert store.authorized_archive_file("0918/a.pdf") is None
    assert not archive.exists()


def test_authorized_archive_file_fetches_when_status_unreadble(tmp_path, monkeypatch):
    reset_arm_circuit()
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / ".vpush-ima-root").touch()
    monkeypatch.setenv("IMA_PULL_URL", "http://100.112.25.21:8743/pull")
    monkeypatch.setenv("IMA_PULL_TOKEN", "tok")
    monkeypatch.setattr("app.ima_documents.is_remote_nfs", lambda *args, **kwargs: False)
    monkeypatch.setattr("app.archive_guard.is_remote_nfs", lambda *args, **kwargs: False)

    class Resp:
        def read(self):
            return b"%PDF-1.7arm"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=5: Resp())
    status = ImaStorageStatus(tmp_path / "missing-status.json", remote=True)
    store = ImaDocumentStore(
        tmp_path / "index",
        archive_root=archive,
        storage_status=status,
    )
    assert store.archive_readable() is False
    got = store.authorized_archive_file("7479/0920/a.pdf")
    assert got is not None
    assert got.read_bytes() == b"%PDF-1.7arm"


def test_archive_lock_refuses_nfs(tmp_path, monkeypatch):
    monkeypatch.setattr("app.ima_documents.is_remote_nfs", lambda path, mounts_text=None: True)
    try:
        with archive_lock(tmp_path):
            raise AssertionError("lock must not run")
    except RuntimeError as exc:
        assert "NFS" in str(exc)


def test_cicc_isolated_does_not_touch_tree(tmp_path, monkeypatch):
    monkeypatch.setattr("app.cicc_collector.is_remote_nfs", lambda path, mounts_text=None: True)
    ctl = CiccControl(str(tmp_path / "archive"))
    assert ctl.isolated() is True
    data = ctl.status()
    assert data["available"] is False
    assert data["reason"] == "isolated"
    assert ctl.schedule_enabled() is False
    try:
        ctl.trigger("incr", "kale")
        raise AssertionError("trigger must refuse")
    except CiccIsolatedError:
        pass
    assert not (tmp_path / "archive" / "local" / ".cicc" / "commands").exists()


def test_cicc_status_missing_file_still_available_when_local(tmp_path):
    ctl = CiccControl(str(tmp_path / "archive"))
    data = ctl.status()
    assert data["available"] is True
    assert data["stale"] is True
