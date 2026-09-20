"""ARM 中间层适配：默认关；路径选择；IMA live write / remap 不读凭据。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import arm_middleware
from app.ima_documents import ImaDocumentConfig, ImaDocumentStore, ImaPureClient
from scripts import cicc_report_collector as cicc
from scripts import ima_to_arm_staging as ima

TZ_BJ = timezone(timedelta(hours=8))


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
    monkeypatch.delenv("CACHE_ROOT", raising=False)
    assert cicc.middleware_enabled(False) is False
    assert cicc.resolve_output_root(None, middleware=False) == Path(cicc.DEFAULT_STORAGE_ROOT)
    assert cicc.resolve_cookie_file(None) == Path(cicc.DEFAULT_COOKIE_FILE)
    assert cicc.should_fix_owner(Path(cicc.DEFAULT_ARM_STAGING_ROOT)) is False
    assert cicc.resolve_paused_file(middleware=False) == Path(cicc.CLASSIC_PAUSED_FILE)
    assert cicc.resolve_paused_file() == Path(cicc.CLASSIC_PAUSED_FILE)


def test_paused_file_uses_cache_root_when_middleware_on(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setenv("CACHE_ROOT", str(cache))
    monkeypatch.setenv("VPUSH_ARM_STAGING_ROOT", str(cache / "staging"))
    paused = cicc.resolve_paused_file()
    assert paused == cache / ".cicc" / "paused.json"
    assert "/srv/vpush-ima" not in paused.as_posix()
    cicc.write_paused("quota", "code 400013 本月配额已满")
    assert paused.is_file()
    data = __import__("json").loads(paused.read_text(encoding="utf-8"))
    assert data["reason"] == "quota"
    assert not Path("/srv/vpush-ima").exists()


def test_paused_file_uses_staging_root_without_cache_root(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.delenv("CACHE_ROOT", raising=False)
    monkeypatch.setenv("VPUSH_ARM_STAGING_ROOT", str(staging))
    paused = cicc.resolve_paused_file()
    assert paused == staging / ".cicc" / "paused.json"
    cicc.write_paused("auth", "code 40010 登录态失效")
    assert paused.is_file()
    assert not Path("/srv/vpush-ima").exists()


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


def test_ima_remap_arm_middleware_alias_is_enable(tmp_path, capsys):
    source = tmp_path / "ima"
    pdf = source / "kb__x" / "0918" / "a.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-x")
    staging = tmp_path / "staging"
    code = ima.main([
        "--arm-middleware", "--dry-run", "--year", "2026",
        "--source", str(source), "--staging-root", str(staging),
    ])
    assert code == 0
    dest = staging / "local" / "ima" / "kb__x" / "2026" / "09" / "18" / "a.pdf"
    assert f"WOULD COPY {pdf} → {dest}" in capsys.readouterr().out
    assert not dest.exists()


def _ts_ms(year: int, month: int, day: int) -> str:
    return str(int(datetime(year, month, day, 12, 0, tzinfo=TZ_BJ).timestamp() * 1000))


def test_ima_live_path_helpers_default_off(monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    monkeypatch.delenv("VPUSH_ARM_STAGING_ROOT", raising=False)
    assert arm_middleware.middleware_enabled() is False
    assert arm_middleware.resolve_staging_root() == Path(arm_middleware.DEFAULT_ARM_STAGING_ROOT)
    dest = arm_middleware.ima_live_destination(
        {"group_id": "legacy", "day": "0918", "name": "demo.pdf", "ts": _ts_ms(2026, 9, 18)},
        now=datetime(2026, 9, 19, 8, 0, tzinfo=TZ_BJ),
    )
    assert dest == Path(
        "/data/vpush-ima-cache/staging/local/ima/legacy/2026/09/18/demo.pdf"
    )


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_ima_live_enable_gates(monkeypatch, value):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", value)
    assert arm_middleware.middleware_enabled() is True
    assert arm_middleware.middleware_enabled(False) is True


@pytest.mark.parametrize("value", ["0", "false", "", "no"])
def test_ima_live_disabled_values(monkeypatch, value):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", value)
    assert arm_middleware.middleware_enabled() is False
    assert arm_middleware.middleware_enabled(True) is True


def test_ima_live_date_prefers_mmdd_then_beijing_now():
    ts = str(int(datetime(2025, 12, 1, 12, 0, tzinfo=TZ_BJ).timestamp() * 1000))
    assert arm_middleware.ima_date_parts("0918", ts) == ("2025", "09", "18")
    now = datetime(2026, 9, 18, 15, 0, tzinfo=TZ_BJ)
    assert arm_middleware.ima_date_parts("unknown", 0, now=now) == ("2026", "09", "18")
    assert arm_middleware.ima_date_parts("", 0, now=now) == ("2026", "09", "18")
    assert arm_middleware.ima_date_parts("0918", 0, now=now) == ("2026", "09", "18")
    ts_now = str(int(now.timestamp() * 1000))
    assert arm_middleware.ima_date_parts("unknown", ts_now) == ("2026", "09", "18")


def test_ima_store_classic_path_unchanged_when_middleware_off(tmp_path, monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    monkeypatch.delenv("VPUSH_ARM_STAGING_ROOT", raising=False)
    store = ImaDocumentStore(tmp_path / "ima")
    legacy = store.pdf_path({"media_id": "file_a", "name": "demo.pdf", "day": "0918"})
    assert legacy == (tmp_path / "ima" / "0918" / "demo.pdf").resolve()
    named = store.pdf_path({
        "media_id": "file_b",
        "name": "demo.pdf",
        "day": "0918",
        "group_id": "7476629605476515",
    })
    assert named.parent.name == "0918"
    assert named.name == "demo.pdf"
    assert "local/ima" not in str(named)


def test_ima_store_live_path_uses_date_shards(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setenv("VPUSH_ARM_STAGING_ROOT", str(staging))
    store = ImaDocumentStore(tmp_path / "ima")
    ts = str(int(datetime(2026, 9, 18, 12, 0, tzinfo=TZ_BJ).timestamp() * 1000))
    dest = store.pdf_path({
        "media_id": "file_a",
        "name": "研报.pdf",
        "day": "0918",
        "group_id": "legacy",
        "ts": ts,
    })
    assert dest == staging.resolve() / "local" / "ima" / "legacy" / "2026" / "09" / "18" / "研报.pdf"
    assert dest.is_relative_to(staging.resolve())
    assert not dest.is_relative_to((tmp_path / "ima").resolve())
    assert store.archive_relative(dest) == "local/ima/legacy/2026/09/18/研报.pdf"


def test_ima_store_live_path_named_group_and_collision(tmp_path, monkeypatch):
    staging = tmp_path / "staging"
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setenv("VPUSH_ARM_STAGING_ROOT", str(staging))
    store = ImaDocumentStore(tmp_path / "ima")
    first = store.pdf_path({
        "media_id": "file_first",
        "name": "report.pdf",
        "day": "0918",
        "group_id": "7476629605476515",
        "ts": _ts_ms(2026, 9, 18),
    })
    occupied = {store.archive_relative(first)}
    second = store.pdf_path({
        "media_id": "file_second",
        "name": "report.pdf",
        "day": "0918",
        "group_id": "7476629605476515",
        "ts": _ts_ms(2026, 9, 18),
    }, occupied=occupied)
    assert first == staging.resolve() / "local" / "ima" / "7476629605476515" / "2026" / "09" / "18" / "report.pdf"
    assert second != first
    assert second.parent == first.parent
    assert second.name.endswith(".pdf")
    assert "__" in second.name


def test_ima_print_dest_cli_default_off(monkeypatch, capsys):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    code = arm_middleware.main([
        "--print-dest", "--group", "legacy", "--day", "0918", "--name", "demo.pdf",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "未启用" in out
    assert "local/ima" not in out


def test_ima_print_dest_cli_lists_staging(monkeypatch, capsys, tmp_path):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    staging = tmp_path / "staging"
    code = arm_middleware.main([
        "--arm-middleware", "--print-dest",
        "--group", "legacy", "--day", "0918", "--name", "demo.pdf",
        "--ts", str(int(datetime(2026, 9, 18, 12, 0, tzinfo=TZ_BJ).timestamp() * 1000)),
        "--staging-root", str(staging),
    ])
    assert code == 0
    assert capsys.readouterr().out.strip() == str(
        staging / "local" / "ima" / "legacy" / "2026" / "09" / "18" / "demo.pdf"
    )


def test_ima_download_skips_puller_when_middleware_on(tmp_path, monkeypatch):
    from app import ima_documents

    seen = {}

    class FakeResponse:
        def __init__(self):
            self._data = b"%PDF-1.7xxxx"

        def read(self, n):
            chunk = self._data[:n]
            self._data = self._data[n:]
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=120):
        seen["url"] = req.full_url
        return FakeResponse()

    staging = tmp_path / "staging"
    dest = staging / "local" / "ima" / "legacy" / "2026" / "09" / "18" / "a.pdf"
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setenv("VPUSH_ARM_STAGING_ROOT", str(staging))
    monkeypatch.setenv("IMA_PULL_URL", "http://10.80.0.2:8743/pull")
    monkeypatch.setenv("IMA_PULL_TOKEN", "tok")
    monkeypatch.delenv("IMA_ARCHIVE_ROOT", raising=False)
    monkeypatch.setattr(ima_documents.urllib.request, "urlopen", fake_urlopen)
    ImaPureClient(ImaDocumentConfig(refresh_token="refresh")).download(
        {"jump_url_info": {"url": "https://res-skb.ima.qq.com/file.pdf?sign=1"}},
        dest,
    )
    assert seen["url"] == "https://res-skb.ima.qq.com/file.pdf?sign=1"
    assert "/pull" not in seen["url"]
    assert dest.read_bytes().startswith(b"%PDF-1.7")


def test_ima_restore_skips_when_middleware_on(tmp_path, monkeypatch):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setenv("VPUSH_ARM_STAGING_ROOT", str(tmp_path / "staging"))
    store = ImaDocumentStore(tmp_path / "ima")
    assert store.restore_original_filenames() == {"renamed": 0}
