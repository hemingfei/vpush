"""IMA → ARM lab sync: default-off, dry-run planning, staging dest. No network."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.ima_documents import ImaDocumentStore, ImaGroupConfig
from scripts import ima_arm_lab_sync as lab

TZ_BJ = timezone(timedelta(hours=8))
PLACEHOLDER_UID = "lab-uid"
PLACEHOLDER_TOKEN = "lab-placeholder-token"


def _ts_ms(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, 12, 0, tzinfo=TZ_BJ).timestamp() * 1000)


def _folder(folder_id: str, name: str) -> dict:
    return {"media_type": 99, "folder_info": {"folder_id": folder_id, "name": name}}


def _pdf(media_id: str, name: str, *, ts: int | None = None, size: int = 12) -> dict:
    item = {"media_id": media_id, "name": name, "file_size": size}
    if ts is not None:
        item["create_time"] = ts
    return item


class FakeClient:
    def __init__(self, listings: dict[str, list[dict]], *, group=None, config=None):
        self.listings = listings
        self.group = group
        self.config = config
        self.list_calls: list[tuple[str, bool]] = []
        self.get_media_calls: list[str] = []
        self.download_calls: list[tuple[str, Path]] = []

    def list_items(self, folder_id: str, *, folders_only: bool = False, max_pages=None):
        self.list_calls.append((folder_id, folders_only))
        items = list(self.listings.get(folder_id, []))
        if folders_only:
            return [item for item in items if item.get("media_type") == 99]
        return items

    def get_media(self, media_id: str) -> dict:
        self.get_media_calls.append(media_id)
        raise AssertionError("dry-run must not call get_media")

    def download(self, media: dict, dest: Path, expected_size: int = 0) -> dict:
        self.download_calls.append((str(media.get("media_id") or ""), dest))
        raise AssertionError("dry-run must not download")


def _tree() -> dict[str, list[dict]]:
    ts = _ts_ms(2026, 9, 18)
    return {
        "kb": [
            _folder("aug", "2026年8月"),
            _folder("sep", "2026年9月（最新）"),
        ],
        "aug": [_folder("0831", "0831")],
        "0831": [_pdf("pdf_aug", "八月.pdf", ts=_ts_ms(2026, 8, 31))],
        "sep": [_folder("0918", "0918"), _folder("0917", "0917")],
        "0918": [
            _pdf("pdf_a", "研报A.pdf", ts=ts),
            _pdf("pdf_b", "研报B.pdf", ts=ts),
            _pdf("pdf_c", "研报C.pdf", ts=ts),
            _pdf("pdf_d", "研报D.pdf", ts=ts),
        ],
        "0917": [_pdf("pdf_old", "研报旧.pdf", ts=_ts_ms(2026, 9, 17))],
    }


def _group(group_id: str = "legacy", kb: str = "kb", root: str = "kb") -> ImaGroupConfig:
    return ImaGroupConfig(id=group_id, name=group_id, knowledge_base_id=kb, root_folder_id=root)


def _write_secrets(path: Path, *, mode: int = 0o600) -> Path:
    path.write_text(
        json.dumps({"uid": PLACEHOLDER_UID, "refresh_token": PLACEHOLDER_TOKEN}),
        encoding="utf-8",
    )
    path.chmod(mode)
    return path


def test_disabled_exits_zero_and_reads_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    monkeypatch.delenv("IMA_UID", raising=False)
    monkeypatch.delenv("IMA_REFRESH_TOKEN", raising=False)
    missing = tmp_path / "missing-secrets.json"
    code = lab.main(["--secrets", str(missing), "--group", "legacy"])
    assert code == 0
    out = capsys.readouterr().out
    assert "未启用" in out
    assert "VPUSH_ARM_MIDDLEWARE=1" in out
    assert not missing.exists()


@pytest.mark.parametrize("value,expected", [
    ("1", True),
    ("true", True),
    ("YES", True),
    ("0", False),
    ("", False),
])
def test_enable_env_gate(monkeypatch, value, expected):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", value)
    assert lab.middleware_enabled(False) is expected
    assert lab.middleware_enabled(True) is True


def test_env_enable_without_cli_flag(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setenv("IMA_UID", PLACEHOLDER_UID)
    monkeypatch.setenv("IMA_REFRESH_TOKEN", PLACEHOLDER_TOKEN)
    monkeypatch.setenv("IMA_KB_ID", "kb")
    monkeypatch.setenv("IMA_ROOT_FOLDER_ID", "kb")
    staging = tmp_path / "staging"
    index = tmp_path / "index"
    listings = {"kb": []}

    def factory(config, group):
        return FakeClient(listings, group=group, config=config)

    code = lab.main(
        ["--group", "legacy", "--staging-root", str(staging), "--index-root", str(index)],
        client_factory=factory,
    )
    assert code == 0
    assert "无待同步" in capsys.readouterr().out
    assert not list(staging.rglob("*.pdf"))


def test_dry_run_plans_dest_under_staging(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    monkeypatch.setenv("IMA_UID", PLACEHOLDER_UID)
    monkeypatch.setenv("IMA_REFRESH_TOKEN", PLACEHOLDER_TOKEN)
    monkeypatch.setenv("IMA_KB_ID", "kb")
    monkeypatch.setenv("IMA_ROOT_FOLDER_ID", "kb")
    staging = tmp_path / "staging"
    index = tmp_path / "index"
    client = FakeClient(_tree())

    def factory(config, group):
        client.group = group
        client.config = config
        return client

    code = lab.main(
        [
            "--enable",
            "--dry-run",
            "--group",
            "legacy",
            "--limit",
            "3",
            "--staging-root",
            str(staging),
            "--index-root",
            str(index),
        ],
        client_factory=factory,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert client.get_media_calls == []
    assert client.download_calls == []
    dest_a = staging / "local" / "ima" / "legacy" / "2026" / "09" / "18" / "研报A.pdf"
    assert "WOULD SYNC" in out
    assert "media_id=pdf_a" in out
    assert "title=研报A.pdf" in out
    assert str(dest_a) in out
    assert "pdf_d" not in out
    assert PLACEHOLDER_TOKEN not in out
    assert not dest_a.exists()
    assert dest_a.is_relative_to(staging)


def test_plan_items_uses_store_pdf_path(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setenv("VPUSH_ARM_STAGING_ROOT", str(staging))
    store = ImaDocumentStore(tmp_path / "ima")
    ts = str(_ts_ms(2026, 9, 18))
    records = [
        {
            "media_id": "pdf_a",
            "name": "研报A.pdf",
            "day": "0918",
            "ts": ts,
            "group_id": "legacy",
            "size": 12,
        }
    ]
    planned = lab.plan_items(records, store, limit=3)
    assert len(planned) == 1
    expected = store.pdf_path(records[0])
    assert planned[0].dest == expected
    assert planned[0].dest == staging.resolve() / "local" / "ima" / "legacy" / "2026" / "09" / "18" / "研报A.pdf"
    assert "local/ima/legacy/2026/09/18" in planned[0].dest.as_posix()


def test_collect_newest_month_then_newest_day_respects_limit():
    client = FakeClient(_tree())
    records = lab.collect_lab_records(client, _group(), limit=3)
    assert [item["media_id"] for item in records] == ["pdf_a", "pdf_b", "pdf_c"]
    assert all(item["day"] == "0918" for item in records)
    listed = {folder_id for folder_id, _ in client.list_calls}
    assert "sep" in listed
    assert "0918" in listed
    assert "0831" not in listed


def test_collect_day_filter_uses_matching_month():
    client = FakeClient(_tree())
    records = lab.collect_lab_records(client, _group(), day="0831", limit=3)
    assert [item["media_id"] for item in records] == ["pdf_aug"]
    assert records[0]["day"] == "0831"


def test_named_group_dest_slug(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setenv("VPUSH_ARM_STAGING_ROOT", str(staging))
    store = ImaDocumentStore(tmp_path / "ima")
    records = [
        {
            "media_id": "pdf_a",
            "name": "g.pdf",
            "day": "0918",
            "ts": str(_ts_ms(2026, 9, 18)),
            "group_id": "7476629605476515",
            "size": 4,
        }
    ]
    planned = lab.plan_items(records, store)
    assert planned[0].dest.parent == (
        staging.resolve() / "local" / "ima" / "7476629605476515" / "2026" / "09" / "18"
    )


def test_secrets_file_requires_0600(tmp_path, monkeypatch):
    monkeypatch.delenv("IMA_UID", raising=False)
    monkeypatch.delenv("IMA_REFRESH_TOKEN", raising=False)
    loose = _write_secrets(tmp_path / "secrets.json", mode=0o644)
    with pytest.raises(lab.LabSyncError, match="0600"):
        lab.load_secrets(loose)
    tight = _write_secrets(tmp_path / "ok.json", mode=0o600)
    creds = lab.load_secrets(tight)
    assert creds.uid == PLACEHOLDER_UID
    assert creds.refresh_token == PLACEHOLDER_TOKEN


def test_secrets_not_printed_on_apply_failure(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("IMA_UID", PLACEHOLDER_UID)
    monkeypatch.setenv("IMA_REFRESH_TOKEN", PLACEHOLDER_TOKEN)
    monkeypatch.setenv("IMA_KB_ID", "kb")
    monkeypatch.setenv("IMA_ROOT_FOLDER_ID", "kb")
    staging = tmp_path / "staging"
    index = tmp_path / "index"
    client = FakeClient(_tree())

    def boom_get(media_id: str) -> dict:
        client.get_media_calls.append(media_id)
        raise RuntimeError(f'refresh_token={PLACEHOLDER_TOKEN} media={media_id}')

    client.get_media = boom_get  # type: ignore[method-assign]
    client.download = lambda *a, **k: {"size": 1}  # type: ignore[method-assign]

    def factory(config, group):
        return client

    code = lab.main(
        [
            "--enable",
            "--apply",
            "--group",
            "legacy",
            "--limit",
            "1",
            "--staging-root",
            str(staging),
            "--index-root",
            str(index),
        ],
        client_factory=factory,
    )
    assert code == 1
    out = capsys.readouterr().out
    assert PLACEHOLDER_TOKEN not in out
    assert "refresh_token=<redacted>" in out or "<redacted>" in out


def test_apply_downloads_via_client(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("IMA_UID", PLACEHOLDER_UID)
    monkeypatch.setenv("IMA_REFRESH_TOKEN", PLACEHOLDER_TOKEN)
    monkeypatch.setenv("IMA_KB_ID", "kb")
    monkeypatch.setenv("IMA_ROOT_FOLDER_ID", "kb")
    staging = tmp_path / "staging"
    index = tmp_path / "index"
    client = FakeClient(_tree())

    def get_media(media_id: str) -> dict:
        client.get_media_calls.append(media_id)
        return {"media_id": media_id, "jump_url_info": {"url": "https://example.invalid/x.pdf"}}

    def download(media: dict, dest: Path, expected_size: int = 0) -> dict:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF-1.7-lab")
        client.download_calls.append((media["media_id"], dest))
        return {"size": dest.stat().st_size, "md5": "abc"}

    client.get_media = get_media  # type: ignore[method-assign]
    client.download = download  # type: ignore[method-assign]

    code = lab.main(
        [
            "--arm-middleware",
            "--apply",
            "--group",
            "legacy",
            "--limit",
            "1",
            "--day",
            "0918",
            "--staging-root",
            str(staging),
            "--index-root",
            str(index),
        ],
        client_factory=lambda config, group: client,
    )
    assert code == 0
    dest = staging / "local" / "ima" / "legacy" / "2026" / "09" / "18" / "研报A.pdf"
    assert dest.read_bytes() == b"%PDF-1.7-lab"
    assert client.get_media_calls == ["pdf_a"]
    assert client.download_calls[0][0] == "pdf_a"
    out = capsys.readouterr().out
    assert PLACEHOLDER_TOKEN not in out
    assert "puller_loop" in out


def test_bad_day_exits_without_network(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("IMA_UID", raising=False)
    monkeypatch.delenv("IMA_REFRESH_TOKEN", raising=False)
    called = {"n": 0}

    def factory(config, group):
        called["n"] += 1
        return FakeClient({})

    code = lab.main(
        [
            "--enable",
            "--day",
            "9/18",
            "--staging-root",
            str(tmp_path / "s"),
            "--index-root",
            str(tmp_path / "i"),
        ],
        client_factory=factory,
    )
    assert code == 2
    assert "MMDD" in capsys.readouterr().out
    assert called["n"] == 0


def test_compose_still_default_off():
    root = Path(__file__).resolve().parents[1]
    for name in ("docker-compose.yml", "docker-compose.prod.yml", "docker-compose.unraid.yml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "VPUSH_ARM_MIDDLEWARE=1" not in text
