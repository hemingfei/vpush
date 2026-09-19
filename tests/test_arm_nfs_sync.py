"""ARM → NFS sync: default-off, path mapping, dry-run. No network, no cookies."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import arm_nfs_sync as nfs


@pytest.fixture(autouse=True)
def _isolate_nfs_env(monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_NFS_SYNC", raising=False)
    monkeypatch.delenv("VPUSH_NFS_SYNC_DEST", raising=False)
    monkeypatch.delenv("VPUSH_NFS_SYNC_SOURCE", raising=False)
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)


def _named_group_dir(group_id: str) -> str:
    digest = hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:16]
    return f"{group_id}__{digest}"


def _write_cicc_pdf(root: Path, *, year: str, month: str, day: str, name: str, category: str) -> Path:
    dest = root / "local" / "cicc-research" / year / month / day / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"%PDF-nfs")
    dest.with_suffix(".json").write_text(
        json.dumps({"id": "42", "category": category, "title": name}, ensure_ascii=False),
        encoding="utf-8",
    )
    return dest


def _write_ima_pdf(root: Path, group: str, *, year: str, month: str, day: str, name: str) -> Path:
    dest = root / "local" / "ima" / group / year / month / day / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"%PDF-ima")
    return dest


def test_disabled_exits_zero_and_writes_nothing(tmp_path, capsys, monkeypatch):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    pdf = _write_cicc_pdf(source, year="2026", month="08", day="01", name="标题_42.pdf", category="宏观经济")
    code = nfs.main(["--source", str(source), "--dest", str(dest)])
    assert code == 0
    out = capsys.readouterr().out
    assert "未启用" in out
    assert "VPUSH_ARM_NFS_SYNC=1" in out
    assert "VPUSH_ARM_MIDDLEWARE" in out
    assert not dest.exists()
    assert pdf.exists()


def test_middleware_flag_does_not_enable_nfs_sync(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    _write_cicc_pdf(source, year="2026", month="08", day="01", name="a_1.pdf", category="宏观经济")
    code = nfs.main(["--source", str(source), "--dest", str(dest)])
    assert code == 0
    assert "未启用" in capsys.readouterr().out
    assert not dest.exists()


@pytest.mark.parametrize("value,expected", [
    ("1", True),
    ("true", True),
    ("YES", True),
    ("on", True),
    ("0", False),
    ("", False),
])
def test_enable_env_gate(monkeypatch, value, expected):
    monkeypatch.setenv("VPUSH_ARM_NFS_SYNC", value)
    assert nfs.nfs_sync_enabled(False) is expected
    assert nfs.nfs_sync_enabled(True) is True


def test_enabled_without_dest_exits_2(tmp_path, capsys):
    code = nfs.main(["--enable", "--source", str(tmp_path / "hot")])
    assert code == 2
    assert "VPUSH_NFS_SYNC_DEST" in capsys.readouterr().out
    assert not list(tmp_path.rglob("*.pdf"))


def test_cicc_maps_date_shard_to_category_mmdd(tmp_path):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    pdf = _write_cicc_pdf(
        source, year="2026", month="08", day="01", name="标题 1_42.pdf", category="宏观经济",
    )
    planned, skipped = nfs.plan_copies(source, dest)
    assert skipped == []
    mapped = [item for item in planned if item.src == pdf]
    assert len(mapped) == 1
    assert mapped[0].dest == dest / "local" / "cicc-research" / "宏观经济" / "0801" / "标题 1_42.pdf"


def test_cicc_category_falls_back_to_jsonl(tmp_path):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    pdf = source / "local" / "cicc-research" / "2026" / "08" / "30" / "宁德_7.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF")
    jsonl = source / "local" / "cicc-research" / ".vpush-local-meta.jsonl"
    jsonl.write_text(
        json.dumps({"id": "7", "category": "公司研究", "title": "宁德"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    planned, skipped = nfs.plan_cicc(source, dest)
    assert skipped == []
    pdf_items = [item for item in planned if item.src == pdf]
    assert pdf_items[0].dest == dest / "local" / "cicc-research" / "公司研究" / "0830" / "宁德_7.pdf"


def test_cicc_skips_without_category(tmp_path):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    pdf = source / "local" / "cicc-research" / "2026" / "08" / "01" / "orphan_9.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF")
    planned, skipped = nfs.plan_cicc(source, dest)
    assert pdf in skipped
    assert all(item.src != pdf for item in planned)


def test_cicc_markers_are_planned(tmp_path):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    lib = source / "local" / "cicc-research" / ".vpush-local-library.json"
    meta = source / "local" / "cicc-research" / ".vpush-local-meta.jsonl"
    lib.parent.mkdir(parents=True)
    lib.write_text("{\"name\":\"中金点睛\"}\n", encoding="utf-8")
    meta.write_text("", encoding="utf-8")
    planned, _ = nfs.plan_cicc(source, dest)
    dests = {item.dest for item in planned}
    assert dest / "local" / "cicc-research" / ".vpush-local-library.json" in dests
    assert dest / "local" / "cicc-research" / ".vpush-local-meta.jsonl" in dests


def test_ima_legacy_maps_to_mmdd(tmp_path):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    pdf = _write_ima_pdf(source, "legacy", year="2026", month="09", day="18", name="研报.pdf")
    planned = nfs.plan_ima(source, dest)
    assert planned[0].src == pdf
    assert planned[0].dest == dest / "0918" / "研报.pdf"


def test_ima_named_group_uses_store_namespace(tmp_path):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    group = "7476629605476515"
    pdf = _write_ima_pdf(source, group, year="2026", month="09", day="18", name="demo.pdf")
    planned = nfs.plan_ima(source, dest)
    assert planned[0].src == pdf
    assert planned[0].dest == dest / _named_group_dir(group) / "0918" / "demo.pdf"
    assert nfs.ima_classic_group_dir(group) == _named_group_dir(group)


def test_ima_already_namespaced_group_kept(tmp_path):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    group = "7464__cafebabedeadbeef"
    pdf = _write_ima_pdf(source, group, year="2026", month="08", day="29", name="研报__aa.pdf")
    planned = nfs.plan_ima(source, dest)
    assert planned[0].src == pdf
    assert planned[0].dest == dest / group / "0829" / "研报__aa.pdf"


def test_ima_unknown_day_maps_to_unknown(tmp_path):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    pdf = _write_ima_pdf(source, "legacy", year="2026", month="unknown", day="unknown", name="a.pdf")
    planned = nfs.plan_ima(source, dest)
    assert planned[0].src == pdf
    assert planned[0].dest == dest / "unknown" / "a.pdf"


def test_dry_run_lists_without_writes(tmp_path, capsys):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    pdf = _write_cicc_pdf(source, year="2026", month="08", day="01", name="标题_42.pdf", category="宏观经济")
    code = nfs.main([
        "--enable", "--dry-run",
        "--source", str(source), "--dest", str(dest),
    ])
    assert code == 0
    out = capsys.readouterr().out
    expected = dest / "local" / "cicc-research" / "宏观经济" / "0801" / "标题_42.pdf"
    assert f"WOULD COPY {pdf} → {expected}" in out
    assert "不上传 115" in out
    assert not expected.exists()


def test_env_enable_and_dest(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("VPUSH_ARM_NFS_SYNC", "1")
    dest = tmp_path / "nfs"
    monkeypatch.setenv("VPUSH_NFS_SYNC_DEST", str(dest))
    source = tmp_path / "empty-hot"
    source.mkdir()
    code = nfs.main(["--source", str(source)])
    assert code == 0
    assert "无待同步" in capsys.readouterr().out
    assert not list(dest.rglob("*"))


def test_apply_hardlinks_or_copies(tmp_path, capsys):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    pdf = _write_cicc_pdf(source, year="2026", month="08", day="01", name="标题_42.pdf", category="宏观经济")
    ima = _write_ima_pdf(source, "legacy", year="2026", month="09", day="18", name="研报.pdf")
    lib = source / "local" / "cicc-research" / ".vpush-local-library.json"
    lib.write_text("{\"name\":\"中金点睛\"}\n", encoding="utf-8")
    code = nfs.main([
        "--enable", "--apply",
        "--source", str(source), "--dest", str(dest),
    ])
    assert code == 0
    cicc_dest = dest / "local" / "cicc-research" / "宏观经济" / "0801" / "标题_42.pdf"
    ima_dest = dest / "0918" / "研报.pdf"
    assert cicc_dest.read_bytes() == b"%PDF-nfs"
    assert ima_dest.read_bytes() == b"%PDF-ima"
    assert (dest / "local" / "cicc-research" / ".vpush-local-library.json").is_file()
    assert "115" in capsys.readouterr().out
    assert pdf.exists()


def test_apply_does_not_overwrite(tmp_path):
    source = tmp_path / "hot"
    dest = tmp_path / "nfs"
    _write_cicc_pdf(source, year="2026", month="08", day="01", name="标题_42.pdf", category="宏观经济")
    existing = dest / "local" / "cicc-research" / "宏观经济" / "0801" / "标题_42.pdf"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"%PDF-keep")
    nfs.main(["--enable", "--apply", "--source", str(source), "--dest", str(dest)])
    assert existing.read_bytes() == b"%PDF-keep"


def test_compose_still_default_off():
    root = Path(__file__).resolve().parents[1]
    for name in ("docker-compose.yml", "docker-compose.prod.yml", "docker-compose.unraid.yml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "VPUSH_ARM_MIDDLEWARE=1" not in text
        assert "VPUSH_ARM_NFS_SYNC=1" not in text


def test_ima_namespace_matches_document_store(tmp_path):
    from app.ima_documents import ImaDocumentStore

    group = "7476629605476515"
    store = ImaDocumentStore(tmp_path / "ima")
    assert nfs.ima_classic_group_dir(group) == store._group_namespace(group)
    assert nfs.ima_classic_group_dir("legacy") is None
    assert nfs.ima_classic_group_dir("legacy:pure") is None
