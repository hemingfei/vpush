"""行为器当日计划持久化的纯逻辑测试（票 #17 交付物 ②）。

语义红线（票 #17 交付物 2，权威源 app/services/mx_window.py）：窗口/间隔的随机分布、当日计划
「同日重启不漂移」——数值与语义照搬 app.services.mx_window，不重新发明。
差异只在存储介质：云端存 settings 键 mx_daily_plan（scheduler.py:129），
本地 agent 无云端 DB——存 agent 数据目录下的 JSON 文件，序列化格式
复用 dumps_plan/loads_plan。
"""
from __future__ import annotations

import json
from datetime import date, datetime

from agent.daily_plan import DailyPlanStore, get_today_plan
from app.services.mx_window import CN_TZ, MXDailyPlan


def _plan_for(day: date) -> MXDailyPlan:
    return MXDailyPlan(
        day=day,
        windows=(
            (datetime(2026, 11, 14, 7, 5, tzinfo=CN_TZ),
             datetime(2026, 11, 14, 11, 45, tzinfo=CN_TZ)),
            (datetime(2026, 11, 14, 12, 35, tzinfo=CN_TZ),
             datetime(2026, 11, 14, 16, 10, tzinfo=CN_TZ)),
            (datetime(2026, 11, 14, 19, 2, tzinfo=CN_TZ),
             datetime(2026, 11, 14, 23, 40, tzinfo=CN_TZ)),
        ),
        fallback_slots=(datetime(2026, 11, 14, 8, 0, tzinfo=CN_TZ),),
        force_close_at=datetime(2026, 11, 14, 23, 45, tzinfo=CN_TZ),
    )


def test_store_roundtrip_same_day(tmp_path):
    """同一天写入后再读：得到同一份计划——「重启不漂移」。"""
    store = DailyPlanStore(tmp_path / "plans")
    plan = _plan_for(date(2026, 11, 14))
    saved = store.load_or_build(date(2026, 11, 14), builder=lambda d: plan)
    assert saved is plan
    # 新实例（模拟重启）：同一文件、同一计划
    store2 = DailyPlanStore(tmp_path / "plans")
    loaded = store2.load_or_build(date(2026, 11, 14), builder=lambda d: plan)
    assert loaded == plan


def test_store_new_day_rebuilds(tmp_path):
    """跨天：旧计划文件不匹配新日期 → 重新生成并覆盖（云端 loads_plan 同语义）。"""
    store = DailyPlanStore(tmp_path / "plans")
    plan14 = _plan_for(date(2026, 11, 14))
    store.load_or_build(date(2026, 11, 14), builder=lambda d: plan14)
    plan15 = _plan_for(date(2026, 11, 15))
    got = store.load_or_build(date(2026, 11, 15), builder=lambda d: plan15)
    assert got is plan15


def test_store_file_format_is_dumps_plan(tmp_path):
    """文件内容即云端 dumps_plan 的 JSON 串（键格式复用，loads_plan 可直接读回）。"""
    from app.services.mx_window import loads_plan

    store = DailyPlanStore(tmp_path / "plans")
    plan = _plan_for(date(2026, 11, 14))
    store.load_or_build(date(2026, 11, 14), builder=lambda d: plan)
    raw = (tmp_path / "plans" / "mx_daily_plan_2026-11-14.json").read_text(encoding="utf-8")
    # 坏数据容错之外的形状断言：与云端 settings 存储串同构
    assert loads_plan(raw, date(2026, 11, 14)) is not None
    data = json.loads(raw)
    assert data["day"] == "2026-11-14"
    assert len(data["windows"]) == 3


def test_store_corrupt_file_rebuilds(tmp_path):
    """坏文件只损失「重启后计划复用」：重新生成覆盖，绝不阻塞当日窗口管理
    （mx_window.loads_plan docstring 的容错边界原文）。"""
    d = tmp_path / "plans"
    d.mkdir()
    (d / "mx_daily_plan_2026-11-14.json").write_text("{bad", encoding="utf-8")
    plan = _plan_for(date(2026, 11, 14))
    got = DailyPlanStore(d).load_or_build(date(2026, 11, 14), builder=lambda day: plan)
    assert got is plan


def test_get_today_plan_uses_cn_timezone_day(tmp_path):
    """「今天」按 CN_TZ（UTC+8）取日——与 mx_window.CN_TZ 同口径，不落机器本地时区。"""
    calls: list[date] = []

    def builder(day: date) -> MXDailyPlan:
        calls.append(day)
        return _plan_for(day)

    get_today_plan(store_dir=tmp_path / "plans", now=datetime(2026, 11, 14, 23, 30, tzinfo=CN_TZ), builder=builder)
    assert calls == [date(2026, 11, 14)]
