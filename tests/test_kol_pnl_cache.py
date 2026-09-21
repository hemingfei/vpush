"""大V预估盈亏小时级缓存测试：db 读/写 + scheduler 开盘时段任务。

缓存键 (kol_id, days)，存整份预估盈亏 JSON + 计算时间戳；
任务在交易日窗口内每小时重算名单内全部大V × {30,60,90}。
"""
import json
import tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from test_api import make_client

from app.db import DB
from app.scheduler import Scheduler


def _scheduler(db) -> Scheduler:
    return Scheduler(
        db, {}, [],
        SimpleNamespace(),
        notifiers_config=SimpleNamespace(),
        xueqiu_config=SimpleNamespace(cookie=""),
        weibo_config=SimpleNamespace(cookie="", username="", password=""),
    )


def test_pnl_cache_roundtrip_and_upsert():
    """缓存读写：整份存取含时间戳；同键覆盖写更新内容与时间戳。"""
    db = DB(Path(tempfile.mkdtemp()) / "t.db")
    payload = {"kol": {"kol_id": 1}, "window_days": 30, "stocks": [{"target_name": "贵州茅台"}],
               "summary": {"losers": 1}}

    assert db.get_kol_pnl_cache(1, 30) is None  # 未写为 None

    db.upsert_kol_pnl_cache(1, 30, payload)
    hit = db.get_kol_pnl_cache(1, 30)
    assert hit is not None
    assert hit["payload"] == payload
    assert hit["computed_at"]  # 非空时间戳

    payload2 = {**payload, "summary": {"losers": 2}}
    db.upsert_kol_pnl_cache(1, 30, payload2)
    hit2 = db.get_kol_pnl_cache(1, 30)
    assert hit2["payload"]["summary"]["losers"] == 2  # 覆盖写
    assert hit2["computed_at"] >= hit["computed_at"]  # 时间戳推进（字典序可比）

    assert db.get_kol_pnl_cache(1, 90) is None  # 不同窗口互不干扰
    assert db.get_kol_pnl_cache(2, 30) is None


def test_pnl_refresh_task_recomputes_all_kols_and_windows(monkeypatch):
    """任务批量重算：范围内每个大V × {30,60,90} 各落一份缓存；单个失败不连坐。"""
    import json as _json

    from app import mx_kol_pnl as mp

    client = make_client()
    db = client.app.state.db
    k1 = db.add_kol("mx", "缓存大V一", "pc1")
    k2 = db.add_kol("mx", "缓存大V二", "pc2")
    db.set_setting("mx_view_kol_ids", _json.dumps([k1, k2]))
    scheduler = _scheduler(db)

    built = {"n": 0}

    def fake_pnl(database, kol_id, days=30, price_lookup=None):
        built["n"] += 1
        if kol_id == k2:
            raise RuntimeError("boom")  # 模拟单大V脏数据失败
        return {"kol": {"kol_id": kol_id}, "window_days": days, "stocks": [], "available": True}

    monkeypatch.setattr(mp, "build_kol_pnl", fake_pnl)
    # 传工作日窗口内时刻：任务按传参时钟判定（真实时钟跑测试会落在盘外）
    wed = datetime(2026, 9, 23, 10, 30, 0)
    count = scheduler._run_kol_pnl_refresh(now=wed)

    assert built["n"] == 4  # k1 三窗口各 1 次 + k2 首窗口抛错即 break（不连坐）
    assert count == 1  # 成功落库仅 k1（k2 抛错被跳过）
    assert db.get_kol_pnl_cache(k1, 30) is not None
    assert db.get_kol_pnl_cache(k1, 60) is not None
    assert db.get_kol_pnl_cache(k1, 90) is not None
    assert db.get_kol_pnl_cache(k2, 30) is None  # 失败的不落库


def test_pnl_refresh_task_skips_outside_trading_window(monkeypatch):
    """非交易日窗口（周末）任务跳过，不触发任何回放。"""
    import json as _json
    from datetime import datetime

    from app import mx_kol_pnl as mp

    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "周末大V", "pc3")
    db.set_setting("mx_view_kol_ids", _json.dumps([kol]))
    scheduler = _scheduler(db)

    built = {"n": 0}

    def fake_pnl(*a, **k):
        built["n"] += 1
        return {"kol": {"kol_id": kol}, "window_days": 30, "stocks": []}

    monkeypatch.setattr(mp, "build_kol_pnl", fake_pnl)
    # 周六 10:00（北京钟面）：窗口判定按传参注入的 now
    sat = datetime(2026, 9, 26, 10, 0, 0)  # 2026-09-26 是周六
    assert scheduler._kol_pnl_refresh_due(sat) is False
    assert scheduler._run_kol_pnl_refresh(now=sat) == 0
    assert built["n"] == 0


def test_pnl_refresh_task_runs_hourly_within_window(monkeypatch):
    """交易日窗口内：整点后首轮触发，settings 时间键控制一小时最多一次。"""
    import json as _json
    from datetime import datetime

    from app import mx_kol_pnl as mp

    client = make_client()
    db = client.app.state.db
    kol = db.add_kol("mx", "工作日大V", "pc4")
    db.set_setting("mx_view_kol_ids", _json.dumps([kol]))
    scheduler = _scheduler(db)

    # 交易日窗口（MX 早市 7:00-12:00 之间）：周三 10:30
    wed = datetime(2026, 9, 23, 10, 30, 0)
    assert scheduler._kol_pnl_refresh_due(wed) is True

    built = {"n": 0}

    def fake_pnl(database, kol_id, days=30, price_lookup=None):
        built["n"] += 1
        return {"kol": {"kol_id": kol_id}, "window_days": days, "stocks": []}

    monkeypatch.setattr(mp, "build_kol_pnl", fake_pnl)
    assert scheduler._run_kol_pnl_refresh(now=wed) == 1
    assert built["n"] == 3  # 1 大V × 3 窗口

    # 同小时内：时间键已记录，不再触发
    assert scheduler._kol_pnl_refresh_due(wed.replace(minute=50)) is False
    # 下一个整点：再次到期
    assert scheduler._kol_pnl_refresh_due(wed.replace(hour=11, minute=5)) is True


def test_pnl_refresh_task_respects_scope(monkeypatch):
    """任务范围与 holdings_kol_ids 同口径：名单外大V不重算。"""
    import json as _json

    from app import mx_kol_pnl as mp

    client = make_client()
    db = client.app.state.db
    k_in = db.add_kol("mx", "名单内", "pc5")
    k_out = db.add_kol("mx", "名单外", "pc6")
    db.set_setting("mx_view_kol_ids", _json.dumps([k_in]))
    scheduler = _scheduler(db)

    seen = {"ids": []}

    def fake_pnl(database, kol_id, days=30, price_lookup=None):
        seen["ids"].append(kol_id)
        return {"kol": {"kol_id": kol_id}, "window_days": days, "stocks": []}

    monkeypatch.setattr(mp, "build_kol_pnl", fake_pnl)
    scheduler._run_kol_pnl_refresh(now=datetime(2026, 9, 23, 10, 30, 0))
    assert set(seen["ids"]) == {k_in}
