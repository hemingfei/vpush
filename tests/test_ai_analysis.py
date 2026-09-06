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
from app.fetchers.base import CN_TZ
from app.scheduler import build_ai_task_stop_alert, end_ai_task_run, try_begin_ai_task_run

from test_api import auth_headers, make_client


def make_db() -> DB:
    tmp = tempfile.mkdtemp()
    return DB(Path(tmp) / "test.db")


def _cn_minute_str(dt_utc: datetime) -> str:
    """把 UTC 时刻转成 posts.published_at 的存储格式（北京时间裸字符串，分钟粒度）。"""
    return dt_utc.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M")


def _create_task(db: DB, kol_id: int, name: str = "t",
                 start_offset: int = 1, end_offset: int = 0) -> int:
    return db.create_ai_task(
        name=name, description="", target_kol_id=kol_id,
        time_range_start_days_offset=start_offset, time_range_start_time="00:00",
        time_range_end_days_offset=end_offset, time_range_end_time="00:00",
        selected_kol_ids=[kol_id], prompt_template="p",
        schedule_day_of_week="1,2,3,4,5", schedule_time="09:00",
    )


def _insert_post(db: DB, kol_id: int, external_id: str, content: str, published_at: str) -> None:
    db.insert_post(
        platform="xueqiu", kol_id=kol_id, external_id=external_id,
        title="", content=content, url="", published_at=published_at,
    )


def _task_payload(kol_id: int) -> dict:
    return {
        "name": "每日分析",
        "description": "",
        "target_kol_id": kol_id,
        "time_range_start_days_offset": -1,
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
    tid = _create_task(db, kol_id, "每日分析", start_offset=-1, end_offset=1)
    # 窗口内放一条发言才能走到 LLM 步骤（0 条消息会在 LLM 之前短路跳过）
    _insert_post(db, kol_id, "p1", "窗口内的发言", _cn_minute_str(datetime.now(timezone.utc)))
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
    tid = _create_task(db, kol_id, start_offset=-1, end_offset=1)
    # 窗口内放一条发言才能走到 LLM 成功路径（0 条消息现在会短路跳过 LLM）
    _insert_post(db, kol_id, "p1", "窗口内的发言", _cn_minute_str(datetime.now(timezone.utc)))
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


def test_try_begin_ai_task_run_mutex():
    """D1：同任务并发占用第二次必须失败；end 释放后可再次占用。"""
    tid = 20260906  # 互斥是纯集合操作，用不落库的假任务 ID 即可
    try:
        assert try_begin_ai_task_run(tid) is True
        assert try_begin_ai_task_run(tid) is False, "任务运行中，第二次占用必须被拒"
    finally:
        end_ai_task_run(tid)
    assert try_begin_ai_task_run(tid) is True, "释放后应可再次占用"
    end_ai_task_run(tid)
    # 清理：不得污染调度器的全局集合
    from app.scheduler import _ai_task_running
    assert tid not in _ai_task_running


def test_empty_window_skips_llm_and_logs_success(monkeypatch):
    """D3：窗口内 0 条消息 → 不调 LLM、不发空报告，落 success 日志并排下次运行。"""
    from app import ai_analysis as mod

    db = make_db()
    kol_id = db.add_kol("xueqiu", "A", "1")
    tid = _create_task(db, kol_id, "每日分析", start_offset=-1, end_offset=1)
    db.update_ai_task(
        tid,
        fail_count=1,
        next_run_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    )
    db.set_setting("llm_api_key", "test-key")

    def _forbidden(*a, **k):
        raise AssertionError("0 条消息不应调用 LLM")

    monkeypatch.setattr(mod.llm, "_chat", _forbidden)

    result = run_analysis_task(tid, db)
    assert result["success"] is True
    assert result["post_id"] is None

    log = db.get_ai_logs_for_task(tid)[0]
    assert log["status"] == "success"
    assert log["post_count"] == 0

    # 成功语义：失败计数清零、按计划推进下次运行，不会每轮重复到期
    task = db.get_ai_task(tid)
    assert task["fail_count"] == 0
    assert task["last_run_status"] == "success"
    assert datetime.fromisoformat(task["next_run_at"]) > datetime.now(timezone.utc)
    posts = db._rows("SELECT id FROM posts WHERE post_type = 'ai_analysis'")
    assert posts == [], "空窗口不得产出报告帖"


def test_task_disabled_during_llm_call_skips_report(monkeypatch):
    """D2：LLM 调用期间任务被禁用 → 丢弃结果不发报告、不计失败。"""
    from app import ai_analysis as mod

    db = make_db()
    kol_id = db.add_kol("xueqiu", "A", "1")
    tid = _create_task(db, kol_id, "每日分析", start_offset=-1, end_offset=1)
    _insert_post(db, kol_id, "p1", "窗口内的发言", _cn_minute_str(datetime.now(timezone.utc)))
    db.update_ai_task(tid, next_run_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    db.set_setting("llm_api_key", "test-key")

    def fake_chat(*a, **k):
        # 模拟 LLM 慢调用（数十秒）期间管理员禁用了任务
        db.update_ai_task(tid, enabled=False)
        return ({"content": "迟到的报告"}, {"prompt_tokens": 7, "completion_tokens": 3})

    monkeypatch.setattr(mod.llm, "_chat", fake_chat)

    result = run_analysis_task(tid, db)
    assert result["success"] is False
    assert result["post_id"] is None
    assert result["retries_exhausted"] is False, "禁用不算运行失败，不得触发停用告警"

    log = db.get_ai_logs_for_task(tid)[0]
    assert log["status"] == "skipped"

    # 不计失败：fail_count 不动，也没有报告帖产出
    task = db.get_ai_task(tid)
    assert task["fail_count"] == 0
    posts = db._rows("SELECT id FROM posts WHERE post_type = 'ai_analysis'")
    assert posts == []


def test_prompt_budget_drops_oldest_keeps_newest():
    """D4：消息正文超总预算 → 从最早开始丢弃（保最新），并在文末注明截断条数。"""
    from app.ai_analysis import AI_PROMPT_TOTAL_CHAR_BUDGET, format_messages_for_llm

    # 每条约 320 字符，150 条 ≈ 48k 字符，必然超过 24000 预算
    posts = [
        {"platform": "xueqiu", "kol_name": "V", "published_at": f"2026-09-01 09:{i % 60:02d}",
         "content": f"发言{i} " + "x" * 300}
        for i in range(150)
    ]
    body = format_messages_for_llm(posts)

    assert "已省略最早的" in body, "发生截断时必须在正文注明"
    dropped = int(body.split("已省略最早的 ")[1].split(" 条")[0])
    assert 0 < dropped < 150, "至少保留最新一条，且确实丢弃了部分"
    assert len(body) < AI_PROMPT_TOTAL_CHAR_BUDGET + 100, "拼接结果须落在预算附近以内"
    assert "发言149" in body, "最新帖必须保留"
    assert "发言0 " not in body, "最旧帖应被丢弃"


def test_local_wall_time_fixed_to_cn_tz():
    """D5：表单时间固定按东八区解释，不随部署进程时区漂移。"""
    from app.ai_analysis import _local_wall_time

    now_utc = datetime(2026, 9, 6, 20, 30, tzinfo=timezone.utc)  # 北京时间 09-07 04:30
    lt = _local_wall_time(now_utc, 0, "09:00")
    assert lt.utcoffset() == timedelta(hours=8)
    assert lt.strftime("%Y-%m-%d %H:%M") == "2026-09-07 09:00"
    nxt = _local_wall_time(now_utc, 1, "00:00")
    assert nxt.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M") == "2026-09-08 00:00"


def test_boundary_post_at_window_start_included(monkeypatch):
    """D6：published_at 恰好等于窗口起点（分钟粒度）的帖子必须被包含。

    旧行为：窗口串带秒（...00:00:00），起点帖子串（...00:00）更短，
    字符串比较被判小 → 开始端点排他，两端语义不对称。
    """
    from app import ai_analysis as mod

    db = make_db()
    kol_id = db.add_kol("xueqiu", "A", "1")
    tid = _create_task(db, kol_id, "边界", start_offset=0, end_offset=1)
    # start = 今天 00:00（北京时间）；帖子恰好发布于起点分钟
    start_cn = (datetime.now(timezone.utc).astimezone(CN_TZ)
                .replace(hour=0, minute=0, second=0, microsecond=0))
    _insert_post(db, kol_id, "p_start", "起点帖", start_cn.strftime("%Y-%m-%d %H:%M"))
    # 模板须含 {messages} 占位符，便于断言帖子确实进入了 LLM 输入
    db.update_ai_task(
        tid,
        prompt_template="时间范围：{time_range}\n发言：{messages}",
        next_run_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    )
    db.set_setting("llm_api_key", "test-key")

    captured = {}

    def fake_chat(config, messages, **k):
        captured["content"] = messages[-1]["content"]
        return ({"content": "报告"}, {})

    monkeypatch.setattr(mod.llm, "_chat", fake_chat)

    result = run_analysis_task(tid, db)
    assert result["success"] is True, result
    log = db.get_ai_logs_for_task(tid)[0]
    assert log["post_count"] == 1, "恰好等于窗口起点的帖子应被包含"
    assert "起点帖" in captured["content"]
