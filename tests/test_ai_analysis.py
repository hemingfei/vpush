"""AI 分析任务调度回归测试：新建/启用任务不得绕过计划时间立即运行。

背景 bug：create_ai_task 不写 next_run_at，get_due_ai_tasks 把
next_run_at IS NULL 视为立即到期，导致新任务创建后马上跑一次。
"""
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import DB
from app.ai_analysis import (
    AI_TASK_RETRY_DELAY_SECONDS,
    calculate_next_run,
    format_next_run,
    run_analysis_task,
)
from app.scheduler import build_ai_task_stop_alert

from test_api import auth_headers, make_client


def make_db() -> DB:
    tmp = tempfile.mkdtemp()
    return DB(Path(tmp) / "test.db")


def _create_task(db: DB, kol_id: int, name: str = "t") -> int:
    return db.create_ai_task(
        name=name, description="", target_kol_id=kol_id,
        time_range_start_days_offset=1, time_range_start_time="00:00",
        time_range_end_days_offset=0, time_range_end_time="00:00",
        selected_kol_ids=[kol_id], prompt_template="p",
        schedule_day_of_week="1,2,3,4,5", schedule_time="09:00",
    )


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


def test_llm_failure_retries_once_then_stops(monkeypatch):
    """LLM 失败：首次失败退避重试一次，重试仍失败停用任务且不再被调度命中。

    背景 bug：LLM 调用失败不更新 next_run_at，任务保持到期状态，
    调度器每个循环（约 30 秒）重复发起，无限打挂的 LLM 接口。
    """
    from app import ai_analysis as mod

    db = make_db()
    kol_id = db.add_kol("xueqiu", "A", "1")
    tid = _create_task(db, kol_id, "每日分析")
    # 目标 KOL 即分析结果落点；再补一个源 KOL 供查询（无帖子也能跑到 LLM 步骤）
    db.update_ai_task(tid, next_run_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    db.set_setting("llm_api_key", "test-key")

    monkeypatch.setattr(mod.llm, "_chat", lambda *a, **k: (None, {}))

    # 第一次失败：不放弃，安排 5 分钟后自动重试
    result = run_analysis_task(tid, db)
    assert result["success"] is False
    assert result["retries_exhausted"] is False
    task = db.get_ai_task(tid)
    assert task["enabled"] == 1
    assert task["fail_count"] == 1
    assert task["last_run_status"] == "failed"
    retry_at = datetime.fromisoformat(task["next_run_at"])
    now = datetime.now(timezone.utc)
    assert now < retry_at <= now + timedelta(seconds=AI_TASK_RETRY_DELAY_SECONDS + 30)
    assert db.get_due_ai_tasks(now.isoformat()) == [], "重试窗口内不得再次到期"

    # 第二次（重试）失败：停用任务，调度器不再命中
    result = run_analysis_task(tid, db)
    assert result["success"] is False
    assert result["retries_exhausted"] is True
    task = db.get_ai_task(tid)
    assert task["enabled"] == 0
    assert task["fail_count"] == 2
    assert db.get_due_ai_tasks(datetime.now(timezone.utc).isoformat()) == []


def test_success_resets_fail_count(monkeypatch):
    """失败一次后重试成功：任务恢复启用状态且失败计数清零。"""
    from app import ai_analysis as mod

    db = make_db()
    kol_id = db.add_kol("xueqiu", "A", "1")
    tid = _create_task(db, kol_id)
    db.update_ai_task(
        tid,
        fail_count=1,
        next_run_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    )
    db.set_setting("llm_api_key", "test-key")

    monkeypatch.setattr(
        mod.llm, "_chat",
        lambda *a, **k: ({"content": "测试报告"}, {"prompt_tokens": 10, "completion_tokens": 5}),
    )

    result = run_analysis_task(tid, db)
    assert result["success"] is True, result
    task = db.get_ai_task(tid)
    assert task["enabled"] == 1
    assert task["fail_count"] == 0
    assert task["last_run_status"] == "success"
    assert datetime.fromisoformat(task["next_run_at"]) > datetime.now(timezone.utc)


def test_stop_alert_builds_system_kol_post_with_cooldown():
    """重试耗尽告警：自动创建系统 KOL「系统通知」，同任务冷却期内只发一条。"""
    db = make_db()
    kol_id = db.add_kol("xueqiu", "A", "1")
    tid = _create_task(db, kol_id, "每日分析")

    post = build_ai_task_stop_alert(db, tid, "连接超时")
    assert post is not None
    assert post.kol_name == "系统通知"
    assert "已停止" in post.title
    assert "每日分析" in post.content
    assert "连接超时" in post.content
    # 系统 KOL 按约定存在（platform=system, external_id=system_alert）
    assert db.get_kol_by_external("system", "system_alert") is not None

    # 冷却期内第二次构造返回 None，不重复发
    assert build_ai_task_stop_alert(db, tid, "again") is None


def test_enable_endpoint_resets_fail_count():
    """重新启用任务时清零失败计数，重新保有「失败自动重试一次」的机会。"""
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kol_id = db.add_kol("xueqiu", "测试大V", "u1")
    tid = _create_task(db, kol_id)
    db.update_ai_task(tid, enabled=False, fail_count=2)

    resp = client.post(f"/api/admin/ai-analysis/tasks/{tid}/enable", headers=admin)
    assert resp.status_code == 200, resp.text

    task = db.get_ai_task(tid)
    assert task["enabled"] == 1
    assert task["fail_count"] == 0
