"""2026-10-13 下午风暴破案后的四项加固测试：

① 受限自动换 TOKEN（MxAutoRenewer：凭据/预算/冷却闸门）
② 风暴期退避钳制（连上即断→直接末档长退避；站住归零）
③ ack 序号事件帧（42/msg,<ack>[...] 解析 + 43 ACK 回复 + 非消息事件不入管道）
④ 断线重连回调（on_reconnected 只在第 2 次及以后的成功连接触发）

帧形态均取自 2026-10-13 生产日志原文（request/va 事件实测样本）。
"""
from __future__ import annotations

import asyncio
import os
import time
from types import SimpleNamespace

import pytest

import app.fetchers.mx.ws as mx_ws
from app.fetchers.mx.ws import MxWsClient
from app.services.mx_auto_renew import MxAutoRenewer


# ---------------------------------------------------------------------------
# ② 风暴期退避钳制 + on_storm 回调
# ---------------------------------------------------------------------------

def test_instant_kill_clamps_backoff_to_last_tier_and_fires_storm_once(monkeypatch):
    """连上即断：退避直接钳到末档（跳过快档）；连续 2 次触发 on_storm 且只触发一次。"""
    monkeypatch.setattr(mx_ws, "_reconnect_delay", lambda: 0.01)
    monkeypatch.setattr(mx_ws, "_revival_delay", lambda: 0.01)
    levels: list[int] = []
    monkeypatch.setattr(
        mx_ws, "_kick_backoff_delay", lambda level: (levels.append(level), 0.01)[1]
    )
    storms: list[str] = []
    give_ups: list[tuple] = []
    client = MxWsClient(
        SimpleNamespace(),
        lambda m: None,
        on_give_up=lambda r, t: give_ups.append((r, t)),
        on_storm=lambda reason: storms.append(reason),
    )
    attempts = {"n": 0}

    async def connect():
        attempts["n"] += 1
        client.connected = True
        if attempts["n"] <= 2:
            async def die_immediately():
                pass  # wait() 立即返回 = 连上即被处决（风暴形态）

            client._sio = SimpleNamespace(wait=die_immediately)
        else:
            async def hold_forever():
                await asyncio.Event().wait()

            client._sio = SimpleNamespace(wait=hold_forever)

    client.connect = connect

    async def scenario():
        task = asyncio.create_task(client.run_forever())
        await asyncio.sleep(0.3)
        assert attempts["n"] == 3
        assert client.connected is True
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    # 连上即断直接钳到末档（0 起，末档 = len-1）；第 2 杀后 kick_level 已越界
    # 进入复活路径，所以阶梯分支只走过一次——快档（第 0-2 档）全部跳过
    last = len(mx_ws.KICK_BACKOFF_LEVELS) - 1
    assert levels == [last]
    # 第 2 次连杀确认风暴形态，且每个风暴片段只通知一次
    assert len(storms) == 1 and "连上即断" in storms[0]
    assert give_ups == []


def test_standing_connection_resets_storm_state(monkeypatch):
    """连接站住后：风暴计数与已通知标记复位（下个风暴片段重新判定与通知）。"""
    monkeypatch.setattr(mx_ws, "_reconnect_delay", lambda: 0.01)
    monkeypatch.setattr(mx_ws, "_revival_delay", lambda: 0.01)
    monkeypatch.setattr(mx_ws, "_kick_backoff_delay", lambda level: 0.01)
    monkeypatch.setattr(mx_ws, "CONNECTION_GRACE_SECONDS", 0.05)
    storms: list[str] = []
    client = MxWsClient(
        SimpleNamespace(), lambda m: None, on_storm=lambda reason: storms.append(reason)
    )
    attempts = {"n": 0}

    async def connect():
        attempts["n"] += 1
        client.connected = True
        if attempts["n"] == 1:
            async def die_quickly():
                await asyncio.sleep(0.01)  # 存活 0.01s < 风暴阈值 → 连杀 #1

            client._sio = SimpleNamespace(wait=die_quickly)
        elif attempts["n"] == 2:
            async def stand():
                await asyncio.sleep(0.2)  # 存活 ≥ grace → 站住，额度归零

            client._sio = SimpleNamespace(wait=stand)
        elif attempts["n"] == 3:
            async def die_quickly_again():
                await asyncio.sleep(0.01)  # 新片段的连杀 #1（前次已站住复位）

            client._sio = SimpleNamespace(wait=die_quickly_again)
        else:
            async def hold_forever():
                await asyncio.Event().wait()

            client._sio = SimpleNamespace(wait=hold_forever)

    client.connect = connect

    async def scenario():
        task = asyncio.create_task(client.run_forever())
        await asyncio.sleep(0.4)
        assert attempts["n"] >= 3
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    # 站住复位后，第 3 次连接的单次连杀不构成「连续 2 次」，on_storm 不应触发
    assert storms == []


# ---------------------------------------------------------------------------
# ③ ack 序号事件帧
# ---------------------------------------------------------------------------

def _client_with_ws(sent: list):
    client = MxWsClient(SimpleNamespace(), lambda m: None)
    handled: list = []

    async def handle(data):
        handled.append(data)

    client._handle_message = handle

    async def send_str(frame: str):
        sent.append(frame)

    client._native_ws = SimpleNamespace(send_str=send_str)
    return client, handled


def test_dispatch_ack_numbered_request_replies_43_and_skips_pipeline():
    """42/msg,<ack>["request",...]：回 43 空 ACK，探测载荷不进消息管道。"""
    sent: list = []
    client, handled = _client_with_ws(sent)

    asyncio.run(
        client._dispatch_sio_event('42/msg,20672["request",{"url":"https://www.cz88.net/api"}]')
    )

    assert sent == ["43/msg,20672[null]"]
    assert handled == []


def test_dispatch_va_event_replies_ack_without_pipeline_noise():
    """va 事件（裸数字载荷）：回 ACK，且不再产生 {'raw': N} 假消息。"""
    sent: list = []
    client, handled = _client_with_ws(sent)

    asyncio.run(client._dispatch_sio_event('42/msg,21711["va",1791871929393]'))

    assert sent == ["43/msg,21711[null]"]
    assert handled == []


def test_dispatch_room_msg_forwarded_without_ack():
    """标准消息帧 42/msg,["room_msg",{...}]（无 ack 序号）：照旧透传，不回 ACK。"""
    sent: list = []
    client, handled = _client_with_ws(sent)

    asyncio.run(client._dispatch_sio_event('42/msg,["room_msg",{"rid":1,"msg":"x"}]'))

    assert sent == []
    assert handled == [{"rid": 1, "msg": "x"}]


def test_dispatch_room_msg_with_ack_gets_both_ack_and_forward():
    """带 ack 序号的消息帧：回 ACK 且照常进管道（ACK 是协议义务，与分发正交）。"""
    sent: list = []
    client, handled = _client_with_ws(sent)

    asyncio.run(client._dispatch_sio_event('42/msg,99["room_msg",{"rid":2}]'))

    assert sent == ["43/msg,99[null]"]
    assert handled == [{"rid": 2}]


def test_dispatch_default_ns_ack_form():
    """默认 ns（无 /msg 前缀）的 ack 帧规格形态 42<id>[...]：回 43<id>[null]；
    未识别事件仍按旧 catch-all 语义透传。"""
    sent: list = []
    client, handled = _client_with_ws(sent)

    asyncio.run(client._dispatch_sio_event('427["ping",{}]'))

    assert sent == ["437[null]"]
    assert handled == [{}]


def test_dispatch_unknown_payload_shape_ack_only():
    """载荷非 JSON 但带 ack 序号：仍尽协议义务回 ACK（空载荷），不炸链路。"""
    sent: list = []
    client, handled = _client_with_ws(sent)

    asyncio.run(client._dispatch_sio_event("42/msg,5[not-json"))

    assert sent == ["43/msg,5[null]"]
    assert handled == []


def test_send_sio_ack_tolerates_missing_ws():
    """传输句柄缺席（握手期/已掐断）：回 ACK 静默跳过，不抛异常。"""
    client = MxWsClient(SimpleNamespace(), lambda m: None)
    client._native_ws = None
    asyncio.run(client._send_sio_ack("/msg,", 1))  # 不应抛


# ---------------------------------------------------------------------------
# ④ on_reconnected：只在第 2 次及以后的成功连接触发
# ---------------------------------------------------------------------------

def test_on_reconnected_fires_from_second_successful_connect(monkeypatch):
    monkeypatch.setattr(mx_ws, "_reconnect_delay", lambda: 0.01)
    # 首连即断会走踢线阶梯（风暴钳制），退避延迟也要一并压到 0.01
    monkeypatch.setattr(mx_ws, "_kick_backoff_delay", lambda level: 0.01)
    reconnects: list[int] = []
    client = MxWsClient(
        SimpleNamespace(), lambda m: None, on_reconnected=lambda: reconnects.append(1)
    )
    attempts = {"n": 0}

    async def connect():
        attempts["n"] += 1
        client.connected = True
        if attempts["n"] == 1:
            async def die_once():
                pass

            client._sio = SimpleNamespace(wait=die_once)
        else:
            async def hold_forever():
                await asyncio.Event().wait()

            client._sio = SimpleNamespace(wait=hold_forever)

    client.connect = connect

    async def scenario():
        task = asyncio.create_task(client.run_forever())
        await asyncio.sleep(0.3)
        assert attempts["n"] == 2
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())

    # 首连不触发（启动序列已有 boot 同步），断线后重连恰好一次
    assert reconnects == [1]


# ---------------------------------------------------------------------------
# ① MxAutoRenewer：凭据/预算/冷却闸门
# ---------------------------------------------------------------------------

class _FakeDB:
    def __init__(self):
        self.d: dict = {}

    def get_setting(self, key):
        return self.d.get(key)

    def set_setting(self, key, value):
        self.d[key] = value


def _renewer(monkeypatch, **env):
    monkeypatch.setenv("MX_RENEW_JENKINS_USER", "u")
    monkeypatch.setenv("MX_RENEW_JENKINS_PASSWORD", "p")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    db = _FakeDB()
    renewer = MxAutoRenewer(db)
    calls: list[dict] = []

    def fake_post():
        calls.append({"t": time.time()})
        return {"ok": True, "detail": "HTTP 201"}

    renewer._jenkins_post_build = fake_post
    return renewer, calls


def test_auto_renew_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("MX_RENEW_JENKINS_USER", raising=False)
    monkeypatch.delenv("MX_RENEW_JENKINS_PASSWORD", raising=False)
    renewer = MxAutoRenewer(_FakeDB())
    result = asyncio.run(renewer.trigger("storm"))
    assert result["ok"] is False and "未启用" in result["detail"]


def test_auto_renew_kill_switch(monkeypatch):
    renewer, calls = _renewer(monkeypatch, MX_RENEW_DISABLED="1")
    result = asyncio.run(renewer.trigger("storm"))
    assert result["ok"] is False and calls == []


def test_auto_renew_budget_and_cooldown(monkeypatch):
    renewer, calls = _renewer(monkeypatch, MX_RENEW_DAILY_BUDGET="2", MX_RENEW_COOLDOWN_MIN="60")

    first = asyncio.run(renewer.trigger("风暴形态"))
    assert first["ok"] is True
    assert calls and renewer._used_today() == 1

    # 冷却期内：预算未满也拒绝
    second = asyncio.run(renewer.trigger("风暴形态"))
    assert second["ok"] is False and "冷却" in second["detail"]
    assert len(calls) == 1

    # 冷却已过：第 2 次放行
    renewer._db.set_setting(_last_key(), str(time.time() - 3601))
    third = asyncio.run(renewer.trigger("放弃重连"))
    assert third["ok"] is True
    assert renewer._used_today() == 2

    # 预算耗尽（冷却再过也不行）
    renewer._db.set_setting(_last_key(), str(time.time() - 3601))
    fourth = asyncio.run(renewer.trigger("放弃重连"))
    assert fourth["ok"] is False and "预算" in fourth["detail"]
    assert len(calls) == 2


def _last_key():
    from app.services.mx_auto_renew import _SETTING_LAST

    return _SETTING_LAST


def test_auto_renew_jenkins_failure_not_recorded(monkeypatch):
    """Jenkins 触发失败：不消耗预算（下次风暴还能再试）。"""
    renewer, calls = _renewer(monkeypatch)
    renewer._jenkins_post_build = lambda: {"ok": False, "detail": "HTTP 403"}

    result = asyncio.run(renewer.trigger("风暴形态"))

    assert result["ok"] is False
    assert renewer._used_today() == 0
    assert renewer._gate()[0] is True


def test_auto_renew_trigger_exception_is_swallowed(monkeypatch):
    renewer, _calls = _renewer(monkeypatch)

    def boom():
        raise RuntimeError("jenkins down")

    renewer._jenkins_post_build = boom
    result = asyncio.run(renewer.trigger("风暴形态"))
    assert result["ok"] is False and "触发异常" in result["detail"]
