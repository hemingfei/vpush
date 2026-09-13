"""版本更新检查：请求路径永不访问外网（GitHub 检查只在后台单飞线程里跑）。

背景：阿里云到 api.github.com 经常连不通，旧实现缓存过期后在请求线程里
同步 httpx.get（timeout=10），并发 version 请求全部挂住并占满浏览器连接槽，
把管理页所有接口一起拖卡。
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from app import version as version_mod
from app.db import DB


@pytest.fixture
def db(tmp_path):
    return DB(tmp_path / "version-test.db")


def test_cache_hit_returns_without_network(db, monkeypatch):
    db.set_setting(
        "version_check_cache",
        json.dumps({"latest": "1.12.180", "checked_at": time.time()}),
    )
    # 缓存有效时连后台刷新都不该踢：外网函数一旦被调用就让测试爆红
    monkeypatch.setattr(
        version_mod, "_fetch_latest_version", lambda: pytest.fail("must not fetch")
    )
    assert version_mod.latest_github_version(db) == ("1.12.180", True)


def test_stale_cache_returns_old_value_and_refreshes_in_background(db, monkeypatch):
    import time as _time

    db.set_setting(
        "version_check_cache",
        json.dumps({"latest": "1.12.180", "checked_at": _time.time() - version_mod.VERSION_CHECK_TTL - 1}),
    )
    refresh_done = threading.Event()

    def fake_fetch() -> str:
        refresh_done.set()
        return "1.12.190"

    monkeypatch.setattr(version_mod, "_fetch_latest_version", fake_fetch)
    started = time.perf_counter()
    latest, has = version_mod.latest_github_version(db)
    elapsed = time.perf_counter() - started
    # 立即返回旧值（不等待外网）
    assert (latest, has) == ("1.12.180", True)
    assert elapsed < 0.5
    assert refresh_done.wait(timeout=2)
    # 后台刷新落地后，下一次调用拿到新值
    deadline = time.perf_counter() + 2
    while time.perf_counter() < deadline:
        if version_mod.latest_github_version(db) == ("1.12.190", True):
            break
        time.sleep(0.02)
    assert version_mod.latest_github_version(db) == ("1.12.190", True)


def test_missing_cache_returns_empty_and_kicks_refresh(db, monkeypatch):
    fetch_called = threading.Event()

    def fake_fetch() -> str:
        fetch_called.set()
        return "1.12.190"

    monkeypatch.setattr(version_mod, "_fetch_latest_version", fake_fetch)
    assert version_mod.latest_github_version(db) == ("", False)
    assert fetch_called.wait(timeout=2)


def test_background_refresh_is_single_flight(db, monkeypatch):
    db.set_setting(
        "version_check_cache",
        json.dumps({"latest": "1.12.180", "checked_at": time.time() - version_mod.VERSION_CHECK_TTL - 1}),
    )
    started_fetches = threading.Event()
    release = threading.Event()
    count = {"n": 0}
    guard = threading.Lock()

    def slow_fetch() -> str:
        with guard:
            count["n"] += 1
        started_fetches.set()
        release.wait(timeout=2)
        return "1.12.190"

    monkeypatch.setattr(version_mod, "_fetch_latest_version", slow_fetch)
    # 并发 5 个请求：只有一个允许进外网刷新，其余立即拿旧值返回
    results = [version_mod.latest_github_version(db) for _ in range(5)]
    assert all(r == ("1.12.180", True) for r in results)
    assert started_fetches.wait(timeout=2)
    deadline = time.perf_counter() + 0.5
    while time.perf_counter() < deadline and count["n"] < 1:
        time.sleep(0.01)
    release.set()
    assert count["n"] == 1
