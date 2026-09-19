"""ARM 中间层适配：默认关；路径选择；IMA stub 不读凭据。"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import cicc_report_collector as cicc
from scripts import ima_to_arm_staging as ima


def test_classic_target_path_unchanged():
    path = cicc.target_path(
        Path("/srv/vpush-ima/local"), "宏观经济",
        "2026-08-01T00:00:00Z", "标题/1", 42,
    )
    assert path == Path("/srv/vpush-ima/local/cicc-research/宏观经济/0801/标题 1_42.pdf")


def test_middleware_target_path_uses_date_shards():
    path = cicc.target_path(
        Path("/data/vpush-ima-cache/staging"), "宏观经济",
        "2026-08-01T00:00:00Z", "标题/1", 42, middleware=True,
    )
    assert path == Path(
        "/data/vpush-ima-cache/staging/local/cicc-research/2026/08/01/标题 1_42.pdf"
    )


def test_middleware_target_path_uses_beijing_calendar_day():
    path = cicc.target_path(
        Path("/s"), "公司研究", "2026-08-29T17:43:03Z", "宁德时代", 7,
        middleware=True,
    )
    assert path == Path("/s/local/cicc-research/2026/08/30/宁德时代_7.pdf")
    classic = cicc.target_path(
        Path("/srv/vpush-ima/local"), "公司研究", "2026-08-29T17:43:03Z", "宁德时代", 7,
    )
    assert classic == Path("/srv/vpush-ima/local/cicc-research/公司研究/0830/宁德时代_7.pdf")


def test_defaults_stay_on_storage_host(monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    monkeypatch.delenv("VPUSH_ARM_STAGING_ROOT", raising=False)
    monkeypatch.delenv("VPUSH_CICC_COOKIE_FILE", raising=False)
    assert cicc.middleware_enabled(False) is False
    assert cicc.resolve_output_root(None, middleware=False) == Path(cicc.DEFAULT_STORAGE_ROOT)
    assert cicc.resolve_cookie_file(None) == Path(cicc.DEFAULT_COOKIE_FILE)
    assert cicc.should_fix_owner(Path(cicc.DEFAULT_ARM_STAGING_ROOT)) is False


def test_middleware_overrides_root_and_cookie_via_env(monkeypatch):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setenv("VPUSH_ARM_STAGING_ROOT", "/tmp/arm-staging")
    monkeypatch.setenv("VPUSH_CICC_COOKIE_FILE", "/tmp/cicc-cookies.txt")
    assert cicc.middleware_enabled(False) is True
    assert cicc.resolve_output_root(None, middleware=True) == Path("/tmp/arm-staging")
    assert cicc.resolve_cookie_file(None) == Path("/tmp/cicc-cookies.txt")
    assert cicc.resolve_output_root("/explicit", middleware=True) == Path("/explicit")
    assert cicc.resolve_cookie_file("/explicit-cookie") == Path("/explicit-cookie")


def test_arm_sidecar_relpath_and_fields(tmp_path):
    pdf = tmp_path / "local" / "cicc-research" / "2026" / "08" / "01" / "标题 1_42.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-fixture")
    row = {"id": "42", "title": "标题 1", "publish": "2026-08-01", "tags": ["宏观经济"]}
    cicc.write_arm_item_sidecar(pdf, row, "宏观经济")
    data = __import__("json").loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["id"] == "42"
    assert data["category"] == "宏观经济"
    assert data["relpath"] == "local/cicc-research/2026/08/01/标题 1_42.pdf"


def test_compose_defaults_do_not_enable_arm():
    root = Path(__file__).resolve().parents[1]
    for name in ("docker-compose.yml", "docker-compose.prod.yml", "docker-compose.unraid.yml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "VPUSH_ARM_MIDDLEWARE=1" not in text
        assert "VPUSH_ARM_STAGING_ROOT" not in text


def test_ima_stub_disabled_does_nothing(tmp_path, capsys):
    source = tmp_path / "ima"
    group = source / "kb__abcd" / "0829"
    group.mkdir(parents=True)
    (group / "note__deadbeef.pdf").write_bytes(b"%PDF-x")
    code = ima.main(["--source", str(source), "--staging-root", str(tmp_path / "staging")])
    assert code == 0
    out = capsys.readouterr().out
    assert "未启用" in out
    assert not list((tmp_path / "staging").rglob("*.pdf"))


def test_ima_stub_dry_run_lists_remap_without_credentials(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("IMA_COOKIE", raising=False)
    monkeypatch.delenv("IMA_REFRESH_TOKEN", raising=False)
    source = tmp_path / "ima"
    pdf = source / "7464__cafe" / "0829" / "研报__aa11bb22.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-x")
    staging = tmp_path / "staging"
    code = ima.main([
        "--enable", "--dry-run", "--year", "2026",
        "--source", str(source), "--staging-root", str(staging),
    ])
    assert code == 0
    out = capsys.readouterr().out
    dest = staging / "local" / "ima" / "7464__cafe" / "2026" / "08" / "29" / "研报__aa11bb22.pdf"
    assert f"WOULD COPY {pdf} → {dest}" in out
    assert not dest.exists()


def test_ima_stub_skips_local_library_and_unknown_maps(tmp_path):
    source = tmp_path / "ima"
    (source / "local" / "cicc-research" / "宏观经济" / "0829").mkdir(parents=True)
    (source / "local" / "cicc-research" / "宏观经济" / "0829" / "skip.pdf").write_bytes(b"%PDF")
    unknown = source / "kb__x" / "unknown" / "a.pdf"
    unknown.parent.mkdir(parents=True)
    unknown.write_bytes(b"%PDF")
    planned = ima.plan_copies(source, tmp_path / "staging", year="2026")
    assert len(planned) == 1
    assert planned[0][1] == (
        tmp_path / "staging" / "local" / "ima" / "kb__x" / "2026" / "unknown" / "unknown" / "a.pdf"
    )


def test_ima_env_enable_without_cli_flag(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    source = tmp_path / "empty"
    source.mkdir()
    code = ima.main(["--source", str(source), "--staging-root", str(tmp_path / "s")])
    assert code == 0
    assert "无待映射" in capsys.readouterr().out


@pytest.mark.parametrize("name,expected", [
    ("0829", ("08", "29")),
    ("unknown", ("unknown", "unknown")),
    ("宏观经济", None),
])
def test_ima_map_day_dir(name, expected):
    assert ima.map_day_dir(name) == expected
