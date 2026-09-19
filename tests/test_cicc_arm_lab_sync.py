"""CICC → ARM lab sync: default-off, dry-run planning, staging dest. No network."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from scripts import cicc_arm_lab_sync as lab
from scripts import cicc_report_collector as cicc


@pytest.fixture(autouse=True)
def _isolate_lab_env(monkeypatch):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "")
    monkeypatch.delenv("VPUSH_ARM_STAGING_ROOT", raising=False)
    monkeypatch.delenv("VPUSH_CICC_COOKIE_FILE", raising=False)


PLACEHOLDER_COOKIE = "offline-fixture-not-a-real-cookie"


class FakeSess:
    def __init__(self):
        self.requests: list[str] = []

    def request(self, *args, **kwargs):
        raise AssertionError("lab tests must not call Session.request")


def _param() -> dict:
    return {"treeData": [{"id": 1, "name": "宏观经济"}, {"id": 2, "name": "公司研究"}]}


def _row(rid: int, title: str, publish: str = "2026-08-01T00:00:00Z") -> dict:
    return {"id": rid, "title": title, "publishTime": publish, "summary": "摘要"}


class FakePages:
    def __init__(self, pages: dict[int, list[dict]]):
        self.pages = pages
        self.calls: list[tuple] = []

    def __call__(self, sess, cat_id, page, start, end):
        self.calls.append((cat_id, page, start, end))
        return {"content": list(self.pages.get(page, []))}


def test_disabled_exits_zero_and_reads_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    missing = tmp_path / "missing-cookies.txt"
    code = lab.main(["--cookie-file", str(missing), "--limit", "3"])
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


def test_date_window_matches_collector_days():
    start, end = lab.date_window(7, today=date(2026, 9, 19))
    assert end == "2026-09-19"
    assert start == "2026-09-13"
    assert lab.date_window(0, today=date(2026, 9, 19)) == (None, "2026-09-19")
    assert lab.date_window(1, today=date(2026, 9, 19)) == ("2026-09-19", "2026-09-19")


def test_plan_item_uses_collector_middleware_path(tmp_path):
    item = _row(42, "标题/1")
    planned = lab.plan_item(item, root=tmp_path, category="宏观经济")
    assert planned is not None
    assert planned.dest == cicc.target_path(
        tmp_path, "宏观经济", "2026-08-01T00:00:00Z", "标题/1", 42, middleware=True,
    )
    assert planned.dest == tmp_path / "local" / "cicc-research" / "2026" / "08" / "01" / "标题 1_42.pdf"


def test_env_enable_dry_run_plans_without_download(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    staging = tmp_path / "staging"
    pages = FakePages({1: [_row(42, "研报A"), _row(43, "研报B"), _row(44, "研报C"), _row(45, "研报D")]})
    downloads: list[int] = []

    code = lab.main(
        ["--dry-run", "--limit", "3", "--days", "7", "--staging-root", str(staging)],
        session_factory=FakeSess,
        fetch_param_fn=lambda sess: _param(),
        list_page_fn=pages,
        download_fn=lambda sess, rid: downloads.append(rid) or b"%PDF",
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "WOULD SYNC" in out
    assert "研报A" in out
    dest = staging / "local" / "cicc-research" / "2026" / "08" / "01" / "研报A_42.pdf"
    assert str(dest) in out
    assert "研报D" not in out
    assert downloads == []
    assert not dest.exists()
    assert pages.calls
    _cat, _page, start, end = pages.calls[0]
    assert start == lab.date_window(7)[0]
    assert end == lab.date_window(7)[1]


def test_arm_middleware_alias_and_missing_cookie(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    missing = tmp_path / "no-cookie.txt"
    code = lab.main([
        "--arm-middleware",
        "--cookie-file", str(missing),
        "--staging-root", str(tmp_path / "s"),
    ])
    assert code == 2
    out = capsys.readouterr().out
    assert "Cookie 文件不存在" in out
    assert PLACEHOLDER_COOKIE not in out
    assert str(missing) in out


def test_enabled_does_not_log_cookie_value(tmp_path, capsys, monkeypatch):
    cookie = tmp_path / "cookies.txt"
    secret = "SECRET_CICC_COOKIE=super-secret-value"
    cookie.write_text(secret, encoding="utf-8")
    monkeypatch.setenv("VPUSH_CICC_COOKIE_FILE", str(cookie))
    pages = FakePages({1: [_row(7, "宁德")]})

    def factory():
        return FakeSess()

    code = lab.main(
        ["--enable", "--dry-run", "--limit", "1", "--staging-root", str(tmp_path / "s")],
        session_factory=factory,
        fetch_param_fn=lambda sess: _param(),
        list_page_fn=pages,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert secret not in out
    assert "super-secret-value" not in out


def test_apply_downloads_via_injected_fetch(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    staging = tmp_path / "staging"
    pages = FakePages({1: [_row(42, "match 标题")]})
    downloads: list[int] = []

    def download(sess, rid):
        downloads.append(rid)
        return b"%PDF-arm-lab"

    code = lab.main(
        ["--apply", "--limit", "1", "--days", "7", "--staging-root", str(staging)],
        session_factory=FakeSess,
        fetch_param_fn=lambda sess: _param(),
        list_page_fn=pages,
        download_fn=download,
    )
    assert code == 0
    dest = staging / "local" / "cicc-research" / "2026" / "08" / "01" / "match 标题_42.pdf"
    assert dest.read_bytes() == b"%PDF-arm-lab"
    sidecar = dest.with_suffix(".json")
    assert sidecar.is_file()
    assert downloads == [42]
    out = capsys.readouterr().out
    assert "puller_loop" in out
    assert PLACEHOLDER_COOKIE not in out


def test_quota_systemexit_is_not_swallowed(tmp_path, monkeypatch):
    monkeypatch.setenv("VPUSH_ARM_MIDDLEWARE", "1")
    monkeypatch.setattr(cicc, "PAUSED_FILE", str(tmp_path / "paused.json"))
    pages = FakePages({1: [_row(99, "配额篇")]})

    def download(sess, rid):
        cicc.write_paused("quota", "code 400013 本月配额已满")
        raise SystemExit("本月研报下载数量已达上限（code 400013）：等配额重置后重跑即可续传。")

    with pytest.raises(SystemExit, match="400013"):
        lab.main(
            ["--apply", "--limit", "1", "--staging-root", str(tmp_path / "s")],
            session_factory=FakeSess,
            fetch_param_fn=lambda sess: _param(),
            list_page_fn=pages,
            download_fn=download,
        )
    dest = tmp_path / "s" / "local" / "cicc-research" / "2026" / "08" / "01" / "配额篇_99.pdf"
    assert not dest.exists()


def test_compose_still_default_off():
    root = Path(__file__).resolve().parents[1]
    for name in ("docker-compose.yml", "docker-compose.prod.yml", "docker-compose.unraid.yml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "VPUSH_ARM_MIDDLEWARE=1" not in text


def test_main_restores_middleware_env(tmp_path, monkeypatch):
    monkeypatch.delenv("VPUSH_ARM_MIDDLEWARE", raising=False)
    lab.main(
        ["--enable", "--dry-run", "--staging-root", str(tmp_path / "s")],
        session_factory=FakeSess,
        fetch_param_fn=lambda sess: {"treeData": []},
        list_page_fn=FakePages({}),
    )
    assert os.environ.get("VPUSH_ARM_MIDDLEWARE") in (None, "")
