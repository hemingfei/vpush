"""MX 会话中段「真人点房间」活动模拟测试（app/services/mx_activity.py）。

背景（2026-10-13）：WS 会话连上后 vpush 完全静默（只答心跳/ACK），而官方
网页端会话中每次点选房间必发 room/view + room/notice（抓包场景 S2）。本套
用例覆盖：请求链形态、节奏与闸门、失败顺延、TOKEN 过期上抛，以及调度器
接线（tick 触发 / 连接重置 / 开窗恢复上次房间）。
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import MxConfig
from app.db import DB
from app.fetchers.mx.client import MXClient, MXTokenExpiredError
from app.services.mx_activity import ACTIVITY_INTERVAL_RANGE, LAST_ROOM_SETTING_KEY, MXRoomActivity


def make_db() -> DB:
    tmp = tempfile.mkdtemp()
    return DB(Path(tmp) / "test.db")


def make_kols(db, rids=("101", "102")):
    for rid in rids:
        db.add_kol("mx", f"房间{rid}", rid)
    return [k for k in db.list_kols(platform="mx") if k.get("enabled")]


class RecordingClient:
    """记录 view/notice 调用顺序的假客户端。"""

    def __init__(self, fail_view=False, token_expired=False):
        self.calls: list[tuple[str, int]] = []
        self._fail_view = fail_view
        self._token_expired = token_expired

    def room_view(self, room_id):
        self.calls.append(("view", room_id))
        if self._token_expired:
            raise MXTokenExpiredError("MX token expired")
        if self._fail_view:
            raise RuntimeError("view failed")

    def room_notice(self, room_id):
        self.calls.append(("notice", room_id))


def due_activity(client, db):
    """已到期的活动模拟器（绕过随机首延迟）。"""
    activity = MXRoomActivity(client, db)
    activity._next_fire = time.monotonic() - 1
    return activity


# ---- client.room_notice 请求契约 ----

def test_room_notice_request_contract():
    """room/notice：POST {base}/api/room/notice，body {"rid","tt"}，token 头携带。"""
    recorded = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": 200, "msg": "success"}

    class FakeSession:
        def request(self, method, url, headers=None, data=None, timeout=None):
            recorded.update(method=method, url=url, headers=headers, data=data)
            return FakeResponse()

    client = MXClient("https://mx.test/business-api/5", "tok", session=FakeSession())
    result = client.room_notice(16125)

    assert recorded["method"] == "POST"
    assert recorded["url"] == "https://mx.test/business-api/5/api/room/notice"
    assert json.loads(recorded["data"])["rid"] == 16125
    assert isinstance(json.loads(recorded["data"])["tt"], int)
    assert recorded["headers"]["token"] == "tok"
    assert result == {"code": 200, "msg": "success"}


# ---- 节奏与闸门 ----

def test_click_sends_view_then_notice_and_excludes_last_room(monkeypatch):
    """到期点房间：view→notice 成对、排除上一个、刷新 mx_last_room 与节奏。"""
    monkeypatch.setenv("MX_ACTIVITY_SIM", "1")
    db = make_db()
    make_kols(db)
    client = RecordingClient()
    activity = due_activity(client, db)

    first = asyncio.run(activity.maybe_click(session_active=True, ws_connected=True))
    assert first  # 返回房间描述
    assert client.calls[0][0] == "view" and client.calls[1][0] == "notice"
    assert client.calls[0][1] == client.calls[1][1]  # 同一房间成对
    first_rid = str(client.calls[0][1])
    assert db.get_setting(LAST_ROOM_SETTING_KEY) == first_rid

    # 第二次点房间必须换一个（仅两个房间时唯一选择是另一个）
    activity._next_fire = time.monotonic() - 1
    second = asyncio.run(activity.maybe_click(session_active=True, ws_connected=True))
    assert second
    assert str(client.calls[2][1]) != first_rid
    assert db.get_setting(LAST_ROOM_SETTING_KEY) == str(client.calls[2][1])

    # 节奏顺延到区间内
    delta = activity._next_fire - time.monotonic()
    assert ACTIVITY_INTERVAL_RANGE[0] * 0.9 <= delta <= ACTIVITY_INTERVAL_RANGE[1] + 5


def test_click_gated_by_switch_and_connection(monkeypatch):
    """开关关闭 / 会话不活 / WS 不在线：不点房间；闸门不满足不消费到期状态。"""
    db = make_db()
    make_kols(db)
    client = RecordingClient()

    monkeypatch.setenv("MX_ACTIVITY_SIM", "0")
    activity = due_activity(client, db)
    assert asyncio.run(activity.maybe_click(session_active=True, ws_connected=True)) == ""
    assert client.calls == []

    monkeypatch.setenv("MX_ACTIVITY_SIM", "1")
    assert asyncio.run(activity.maybe_click(session_active=False, ws_connected=True)) == ""
    assert asyncio.run(activity.maybe_click(session_active=True, ws_connected=False)) == ""
    assert client.calls == []
    assert time.monotonic() >= activity._next_fire  # 仍是到期态，恢复在线即补点


def test_click_not_due_is_noop(monkeypatch):
    monkeypatch.setenv("MX_ACTIVITY_SIM", "1")
    db = make_db()
    make_kols(db)
    client = RecordingClient()
    activity = MXRoomActivity(client, db)  # 刚武装：必然未到期
    assert asyncio.run(activity.maybe_click(session_active=True, ws_connected=True)) == ""
    assert client.calls == []


def test_click_failure_reschedules_without_raising(monkeypatch):
    """单次网络失败只顺延节奏，不向调度循环抛异常。"""
    monkeypatch.setenv("MX_ACTIVITY_SIM", "1")
    db = make_db()
    make_kols(db)
    client = RecordingClient(fail_view=True)
    activity = due_activity(client, db)

    assert asyncio.run(activity.maybe_click(session_active=True, ws_connected=True)) == ""
    assert [c[0] for c in client.calls] == ["view"]
    assert activity._next_fire - time.monotonic() > ACTIVITY_INTERVAL_RANGE[0] - 5


def test_click_token_expired_propagates(monkeypatch):
    """TOKEN 过期必须向上抛：调用方据此走统一熔断，绝不继续打。"""
    monkeypatch.setenv("MX_ACTIVITY_SIM", "1")
    db = make_db()
    make_kols(db)
    client = RecordingClient(token_expired=True)
    activity = due_activity(client, db)

    with pytest.raises(MXTokenExpiredError):
        asyncio.run(activity.maybe_click(session_active=True, ws_connected=True))


def test_click_without_rooms_skips_and_reschedules(monkeypatch):
    monkeypatch.setenv("MX_ACTIVITY_SIM", "1")
    db = make_db()
    client = RecordingClient()
    activity = due_activity(client, db)

    assert asyncio.run(activity.maybe_click(session_active=True, ws_connected=True)) == ""
    assert client.calls == []
    assert activity._next_fire - time.monotonic() > 0


# ---- 调度器接线 ----

def _make_scheduler(db):
    from app.scheduler import Scheduler

    return Scheduler(
        db,
        fetchers={},
        notifiers=[],
        polling_config=SimpleNamespace(
            interval_seconds=180,
            priority_interval_seconds=60,
            notify_on_start=False,
        ),
        notifiers_config=None,
        mx_config=MxConfig(enabled=True, token="t"),
    )


def _wire_session(scheduler, client, connected=True):
    """把调度器置于「WS 已连接」状态，并注入假抓取器（会话任务须在事件循环内创建）。"""
    fetcher = SimpleNamespace(
        ws_client=SimpleNamespace(connected=connected),
        mx_client=client,
    )
    scheduler.fetchers["mx"] = fetcher
    return fetcher


def _fake_session_task(scheduler):
    scheduler._mx_ws_task = asyncio.create_task(asyncio.sleep(3600))


def test_tick_fires_activity_click_when_connected(monkeypatch):
    monkeypatch.setenv("MX_ACTIVITY_SIM", "1")
    db = make_db()
    make_kols(db)
    scheduler = _make_scheduler(db)
    client = RecordingClient()
    _wire_session(scheduler, client)

    async def scenario():
        _fake_session_task(scheduler)
        activity = due_activity(client, db)
        scheduler._mx_activity = activity
        await scheduler._mx_maybe_activity_click()

    asyncio.run(scenario())
    assert [c[0] for c in client.calls] == ["view", "notice"]
    scheduler._mx_ws_task.cancel()


def test_tick_skips_when_disconnected_or_token_expired(monkeypatch):
    monkeypatch.setenv("MX_ACTIVITY_SIM", "1")
    db = make_db()
    make_kols(db)
    client = RecordingClient()
    scheduler = _make_scheduler(db)
    _wire_session(scheduler, client, connected=False)

    async def scenario():
        _fake_session_task(scheduler)
        scheduler._mx_activity = due_activity(client, db)
        await scheduler._mx_maybe_activity_click()  # WS 未连接：不点
        scheduler.fetchers["mx"].ws_client.connected = True
        scheduler._mx_token_expired = True
        await scheduler._mx_maybe_activity_click()  # TOKEN 熔断：不点

    asyncio.run(scenario())
    assert client.calls == []
    scheduler._mx_ws_task.cancel()


def test_tick_lazily_creates_activity_on_first_due_tick(monkeypatch):
    """会话期间首个到期 tick 自建模拟器（连接时被置 None 后的重建路径）。"""
    monkeypatch.setenv("MX_ACTIVITY_SIM", "1")
    db = make_db()
    make_kols(db)
    client = RecordingClient()
    scheduler = _make_scheduler(db)
    _wire_session(scheduler, client)
    assert scheduler._mx_activity is None

    async def scenario():
        _fake_session_task(scheduler)
        # 模拟 5-10 分钟后的 tick：直接把（尚未存在的）活动对象的到期时刻放到过去
        scheduler._mx_activity = None
        # 首个 tick：创建但未到期 → 不点
        await scheduler._mx_maybe_activity_click()
        assert scheduler._mx_activity is not None
        assert client.calls == []
        # 到期后的 tick：点房间
        scheduler._mx_activity._next_fire = time.monotonic() - 1
        await scheduler._mx_maybe_activity_click()

    asyncio.run(scenario())
    assert [c[0] for c in client.calls] == ["view", "notice"]
    scheduler._mx_ws_task.cancel()


def test_ws_connect_resets_activity_schedule(monkeypatch):
    """新会话（connect 唯一入口）重置模拟器：点房间节奏重新随机排布。"""
    db = make_db()
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=True)
    scheduler._mx_ws_on_message = lambda post: None

    async def fake_start_ws(*args, **kwargs):
        await asyncio.sleep(3600)

    scheduler.fetchers["mx"] = SimpleNamespace(start_ws=fake_start_ws)
    scheduler._mx_activity = MXRoomActivity(RecordingClient(), db)

    async def scenario():
        await scheduler.mx_ws_control("connect", source="auto")

    asyncio.run(scenario())
    assert scheduler._mx_activity is None
    assert scheduler._mx_ws_task is not None
    scheduler._mx_ws_task.cancel()


# ---- 开窗恢复上次房间（官方冷启动 S1-6） ----

class RestoreFetcher:
    """假抓取器：fetch 记录入参、返回 posts；mx_client 记录 notice。"""

    def __init__(self, posts=None, fail=False, token_expired=False):
        self.fetched: list = []
        self.notices: list[int] = []
        self._posts = posts or []
        self._fail = fail
        self._token_expired = token_expired
        self.mx_client = SimpleNamespace(
            room_notice=lambda rid: self.notices.append(rid)
        )

    def fetch(self, kol):
        self.fetched.append(kol["external_id"])
        if self._token_expired:
            raise MXTokenExpiredError("MX token expired")
        if self._fail:
            raise RuntimeError("fetch failed")
        return self._posts


def test_restore_replays_last_room_chain():
    """有 mx_last_room 记录：fetch（view+msg/list）+ room/notice 对该房间补发。"""
    db = make_db()
    make_kols(db)
    db.set_setting(LAST_ROOM_SETTING_KEY, "102")
    fetcher = RestoreFetcher()
    scheduler = _make_scheduler(db)
    scheduler.fetchers["mx"] = fetcher

    ok, detail = asyncio.run(scheduler._mx_restore_last_room())

    assert ok is True
    assert fetcher.fetched == ["102"]
    assert fetcher.notices == [102]
    assert db.get_setting(LAST_ROOM_SETTING_KEY) == "102"
    assert "房间102" in detail


def test_restore_falls_back_to_random_and_persists():
    """无记录时随机挑启用房间，并把选择持久化为「上次房间」。"""
    db = make_db()
    make_kols(db)
    fetcher = RestoreFetcher()
    scheduler = _make_scheduler(db)
    scheduler.fetchers["mx"] = fetcher

    ok, _ = asyncio.run(scheduler._mx_restore_last_room())

    assert ok is True
    assert len(fetcher.fetched) == 1
    assert db.get_setting(LAST_ROOM_SETTING_KEY) == fetcher.fetched[0]


def test_restore_survives_fetch_failure():
    db = make_db()
    make_kols(db)
    fetcher = RestoreFetcher(fail=True)
    scheduler = _make_scheduler(db)
    scheduler.fetchers["mx"] = fetcher

    ok, detail = asyncio.run(scheduler._mx_restore_last_room())

    assert ok is False
    assert detail  # 失败原因进登录报告


def test_restore_token_expired_propagates():
    db = make_db()
    make_kols(db)
    fetcher = RestoreFetcher(token_expired=True)
    scheduler = _make_scheduler(db)
    scheduler.fetchers["mx"] = fetcher

    with pytest.raises(MXTokenExpiredError):
        asyncio.run(scheduler._mx_restore_last_room())


def test_session_start_records_restore_step():
    """开窗登录报告含「恢复房间」步骤（ws_enabled=False 时亦不缺席）。"""
    db = make_db()
    make_kols(db)
    scheduler = _make_scheduler(db)
    scheduler.mx_config = MxConfig(enabled=True, token="t", ws_enabled=False)
    scheduler._mx_sync_service = None
    scheduler.fetchers["mx"] = RestoreFetcher()

    import app.scheduler as scheduler_module

    asyncio.run(scheduler._mx_session_start())

    report = scheduler_module._mx_login_report
    assert report is not None and report["source"] == "auto"
    restore = next(s for s in report["steps"] if s["name"] == "恢复房间")
    assert restore["ok"] is True
