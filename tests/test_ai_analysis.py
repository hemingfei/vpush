"""AI 分析任务调度回归测试：新建/启用任务不得绕过计划时间立即运行。

背景 bug：create_ai_task 不写 next_run_at，get_due_ai_tasks 把
next_run_at IS NULL 视为立即到期，导致新任务创建后马上跑一次。
"""
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import DB
from app.ai_analysis import calculate_next_run, format_next_run

from test_api import auth_headers, make_client


def make_db() -> DB:
    tmp = tempfile.mkdtemp()
    return DB(Path(tmp) / "test.db")


def _task_payload(kol_id: int) -> dict:
    return {
        "name": "每日分析",
        "description": "",
        "target_kol_id": kol_id,
        "time_range_start_days_offset": 1,
        "time_range_start_time": "00:00",
        "time_range_end_days_offset": 0,
        "time_range_end_time": "00:00",
        "selected_kol_ids": [kol_id],
        "prompt_template": "测试提示词",
        "schedule_day_of_week": "1,2,3,4,5",
        "schedule_time": "09:00",
    }


def test_calculate_next_run_is_strictly_future():
    """schedule_time 已过/未过，下次运行时间都必须晚于当前时刻。"""
    task = {"schedule_day_of_week": "1,2,3,4,5", "schedule_time": "09:00"}
    now = datetime.now(timezone.utc)
    nxt = calculate_next_run(task, now)
    assert nxt is not None
    assert nxt > now


def test_format_next_run_none_for_empty_schedule_days():
    task = {"schedule_day_of_week": "", "schedule_time": "09:00"}
    assert format_next_run(task, datetime.now(timezone.utc)) is None


def test_create_ai_task_sets_future_next_run():
    """创建任务后必须带未来的 next_run_at，且不再被到期查询命中。"""
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kol_id = db.add_kol("xueqiu", "测试大V", "u1")

    resp = client.post(
        "/api/admin/ai-analysis/tasks", headers=admin, json=_task_payload(kol_id)
    )
    assert resp.status_code == 200, resp.text
    task = db.get_ai_task(resp.json()["id"])

    assert task["next_run_at"], "新建任务必须初始化 next_run_at"
    now = datetime.now(timezone.utc)
    assert datetime.fromisoformat(task["next_run_at"]) > now
    assert db.get_due_ai_tasks(now.isoformat()) == []


def test_create_ai_task_v2_sets_future_next_run():
    """第二个创建入口 /admin/ai-tasks 同样要初始化 next_run_at。"""
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kol_id = db.add_kol("xueqiu", "测试大V", "u1")

    resp = client.post(
        "/api/admin/ai-tasks", headers=admin, json=_task_payload(kol_id)
    )
    assert resp.status_code == 200, resp.text
    task = resp.json()["task"]

    assert task["next_run_at"], "新建任务必须初始化 next_run_at"
    assert datetime.fromisoformat(task["next_run_at"]) > datetime.now(timezone.utc)


def test_enable_ai_task_recomputes_stale_next_run():
    """启用任务时重算 next_run_at，遗留的过期时间不得触发立即运行。"""
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kol_id = db.add_kol("xueqiu", "测试大V", "u1")
    tid = db.create_ai_task(
        name="t", description="", target_kol_id=kol_id,
        time_range_start_days_offset=1, time_range_start_time="00:00",
        time_range_end_days_offset=0, time_range_end_time="00:00",
        selected_kol_ids=[kol_id], prompt_template="p",
        schedule_day_of_week="1,2,3,4,5", schedule_time="09:00",
    )
    past = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    db.update_ai_task(tid, enabled=False, next_run_at=past)

    resp = client.post(f"/api/admin/ai-analysis/tasks/{tid}/enable", headers=admin)
    assert resp.status_code == 200, resp.text

    task = db.get_ai_task(tid)
    assert task["enabled"] == 1
    assert datetime.fromisoformat(task["next_run_at"]) > datetime.now(timezone.utc)


def test_backfilled_null_next_run_is_no_longer_due():
    """调度器补算逻辑的前置语义：补算并写入后，到期查询不再命中。"""
    db = make_db()
    kol_id = db.add_kol("xueqiu", "A", "1")
    tid = db.create_ai_task(
        name="t", description="", target_kol_id=kol_id,
        time_range_start_days_offset=1, time_range_start_time="00:00",
        time_range_end_days_offset=0, time_range_end_time="00:00",
        selected_kol_ids=[kol_id], prompt_template="p",
        schedule_day_of_week="6", schedule_time="18:00",
    )
    now = datetime.now(timezone.utc)
    # 老数据：next_run_at 为 NULL 时会被到期查询命中（调度器靠补算兜底）
    assert db.get_due_ai_tasks(now.isoformat())[0]["id"] == tid

    task = db.get_ai_task(tid)
    next_run_at = format_next_run(task, now)
    assert next_run_at is not None
    db.update_ai_task(tid, next_run_at=next_run_at)
    assert db.get_due_ai_tasks(datetime.now(timezone.utc).isoformat()) == []
