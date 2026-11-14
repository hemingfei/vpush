"""行为器生命周期结构化日志的纯逻辑测试（票 #17 交付物 ⑥）。

user story 19（行为器侧）：启动/开关浏览器/登录成败/切房/接力切换等
事件结构化记录、可查询。形态：JSONL 文件（一行一事件），t/kind/account/
detail 字段固定；「可查询」= 可按 kind 过滤、按时间排序。
"""
from __future__ import annotations

import json

from agent.lifecycle import LifecycleLog, query_events

# ---- 写入与读回 ----

def test_write_and_query_roundtrip(tmp_path):
    log = LifecycleLog(tmp_path / "lifecycle.jsonl")
    log.record("agent_start", account=None, detail="行为器启动")
    log.record("login_ok", account="hemingfei", detail="seed 免登成功")
    log.record("room_switch", account="hemingfei", detail="点开 格兰投研888")
    events = query_events(tmp_path / "lifecycle.jsonl")
    assert [e["kind"] for e in events] == ["agent_start", "login_ok", "room_switch"]
    assert events[1]["account"] == "hemingfei"
    # 每行时间戳单调不减
    assert all(events[i]["t"] <= events[i + 1]["t"] for i in range(len(events) - 1))


def test_query_filter_by_kind(tmp_path):
    """可查询：按 kind 过滤（排障场景「只看接力切换/登录失败」）。"""
    log = LifecycleLog(tmp_path / "lifecycle.jsonl")
    log.record("login_ok", account="a", detail="1")
    log.record("relay_switch", account="b", detail="2")
    log.record("login_fail", account="a", detail="3")
    log.record("relay_switch", account="a", detail="4")
    relay = query_events(tmp_path / "lifecycle.jsonl", kind="relay_switch")
    assert [e["detail"] for e in relay] == ["2", "4"]


def test_query_corrupt_lines_skipped(tmp_path):
    """坏行跳过不炸：日志是排障资产，单行损坏不该让查询整段失败。"""
    path = tmp_path / "lifecycle.jsonl"
    log = LifecycleLog(path)
    log.record("agent_start", account=None, detail="ok")
    with open(path, "a", encoding="utf-8") as f:
        f.write("{broken\n")
    log2 = LifecycleLog(path)
    log2.record("login_ok", account="a", detail="after")
    events = query_events(path)
    assert [e["kind"] for e in events] == ["agent_start", "login_ok"]


def test_record_never_writes_password(tmp_path):
    """凭据红线：record 接口无密码参数位——带敏感键的调用直接 TypeError，
    把「不小心把 token 传进日志」变成硬失败而非静默入库。"""
    path = tmp_path / "lifecycle.jsonl"
    log = LifecycleLog(path)
    log.record("login_fail", account="hemingfei", detail="验证码错")
    import pytest

    with pytest.raises(TypeError):
        log.record("login_fail", account="hemingfei", detail="x",
                   password="should-not-exist")
    with pytest.raises(TypeError):
        log.record("login_ok", account="hemingfei", detail="x",
                   token="secret-tok")
    raw = path.read_text(encoding="utf-8")
    assert "should-not-exist" not in raw
    assert "secret-tok" not in raw
    for line in raw.splitlines():
        data = json.loads(line)
        assert "password" not in data and "token" not in data


def test_lifecycle_event_vocabulary(tmp_path):
    """事件词汇表固定（排障/对账按 kind 查询的契约面）：启动/开浏览器/
    关浏览器/登录成败/切房/接力切换/日切。"""
    log = LifecycleLog(tmp_path / "lifecycle.jsonl")
    for kind in ("agent_start", "browser_open", "browser_close",
                 "login_ok", "login_fail", "room_switch",
                 "relay_switch", "new_day_reset"):
        log.record(kind, account="hemingfei", detail=kind)
    assert len(query_events(tmp_path / "lifecycle.jsonl")) == 8
