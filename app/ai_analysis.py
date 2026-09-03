"""AI分析核心逻辑"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from . import llm
from .db import DB

logger = logging.getLogger(__name__)

# 默认提示词模板
DEFAULT_PROMPT_TEMPLATE = """你是专业的财经内容分析师。请根据以下大V的发言生成一份简明扼要的分析报告。

时间范围：{time_range}
分析的大V：{kol_names}

发言内容：
{messages}

请生成一份结构清晰的分析报告，包含：
1. 整体观点总结
2. 重点提及的板块/个股
3. 风险提示（如适用）

请直接输出报告，无需寒暄。"""

# 失败重试策略：首次失败不放弃，退避 5 分钟后自动重试一次；
# 重试仍失败说明不是瞬时抖动，停用任务等人工介入，避免调度器每轮重复发起
AI_TASK_RETRY_DELAY_SECONDS = 300
AI_TASK_MAX_CONSECUTIVE_FAILS = 2


def parse_schedule_days(day_of_week_str: str) -> list[int]:
    """解析星期几配置字符串为 Python weekday() 整数列表（周一=0…周日=6）。

    表单约定是周日=0、周一=1…周六=6，这里做转换。
    """
    if not day_of_week_str:
        return []
    days = []
    for part in day_of_week_str.split(","):
        try:
            day = int(part.strip())
        except ValueError:
            continue
        if day == 0:
            days.append(6)
        elif 1 <= day <= 6:
            days.append(day - 1)
    return days


def _local_wall_time(now_utc: datetime, days_offset: int, hhmm: str) -> datetime:
    """把表单里的「N 天后的 HH:MM」换算为本地墙钟时间。

    部署约定 TZ=Asia/Shanghai（compose 已统一设置），表单时间一律按北京时间理解；
    返回带本地时区的 aware datetime，由调用方按需转 UTC。
    """
    parts = hhmm.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    local = now_utc.astimezone() + timedelta(days=days_offset)
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0)


def calculate_time_range(task: dict, now: datetime) -> tuple[datetime, datetime]:
    """根据任务配置计算实际的开始/结束时间。

    表单时间按本地时区理解；posts 表 published_at/fetched_at 存 UTC 或北京时间
    的裸字符串，调用方以本地墙钟字符串做比较，因此这里返回 aware UTC。
    """
    start = _local_wall_time(now, task["time_range_start_days_offset"], task["time_range_start_time"])
    end = _local_wall_time(now, task["time_range_end_days_offset"], task["time_range_end_time"])
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def calculate_next_run(task: dict, now: datetime) -> datetime | None:
    """计算任务的下次运行时间（schedule_time 按本地时区理解，返回 aware UTC）。"""
    schedule_days = parse_schedule_days(task["schedule_day_of_week"])
    if not schedule_days:
        return None

    # 先看今天：今天是调度日且时间未过，今天就是下次运行时间；否则从明天开始找
    next_candidate = _local_wall_time(now, 0, task["schedule_time"])
    if next_candidate <= now.astimezone():
        next_candidate += timedelta(days=1)

    for _ in range(14):  # 最多找两周
        if next_candidate.weekday() in schedule_days:
            return next_candidate.astimezone(timezone.utc)
        next_candidate += timedelta(days=1)

    return None


def format_next_run(task: dict, now: datetime) -> str | None:
    """计算任务下次运行时间并转为可存储的 ISO 字符串（UTC）。

    next_run_at 为空时调度器会把任务视为立即到期，创建/启用任务后必须写入该字段。
    """
    next_run = calculate_next_run(task, now)
    return next_run.isoformat() if next_run else None


def format_messages_for_llm(posts: list[dict]) -> str:
    """将帖子列表格式化为LLM可读的文本"""
    if not posts:
        return "(无发言内容)"
    
    lines = []
    for post in posts:
        platform = post.get("platform", "")
        kol_name = post.get("kol_name", "未知")
        published_at = post.get("published_at", "")
        fetched_at = post.get("fetched_at", "")
        title = (post.get("title") or "").strip()
        content = (post.get("content") or "").strip()
        
        time_str = published_at or fetched_at
        lines.append(f"--- [{platform}] {kol_name} @ {time_str} ---")
        if title:
            lines.append(f"标题: {title}")
        if content:
            lines.append(f"内容: {content[:2000]}")  # 限制长度
        lines.append("")
    
    return "\n".join(lines)


def build_prompt(task: dict, posts: list[dict], start: datetime, end: datetime) -> str:
    """构建完整的LLM提示词"""
    template = task["prompt_template"] or DEFAULT_PROMPT_TEMPLATE
    
    # 获取大V名称
    kol_names = []
    kol_ids = task["selected_kol_ids"]
    # 从posts中去重获取大V名
    seen_kols = set()
    for post in posts:
        kol_id = post.get("kol_id")
        kol_name = post.get("kol_name", "未知")
        if kol_id and kol_id not in seen_kols:
            seen_kols.add(kol_id)
            kol_names.append(kol_name)
    
    # 格式化时间范围（按本地时区展示，与表单理解一致）
    time_range_str = (f"{start.astimezone().strftime('%Y-%m-%d %H:%M')}"
                      f" ~ {end.astimezone().strftime('%Y-%m-%d %H:%M')}")
    
    # 格式化消息
    messages_str = format_messages_for_llm(posts)
    
    # 替换变量
    prompt = template
    prompt = prompt.replace("{time_range}", time_range_str)
    prompt = prompt.replace("{kol_names}", ", ".join(kol_names) if kol_names else "无")
    prompt = prompt.replace("{messages}", messages_str)
    
    return prompt


def extract_token_usage(usage: dict | None) -> tuple[int, int, int]:
    """从 LLM 返回的 usage 字典中提取 token 使用情况"""
    if not usage or not isinstance(usage, dict):
        return 0, 0, 0
    prompt_tokens = usage.get("prompt_tokens") or 0
    completion_tokens = usage.get("completion_tokens") or 0
    total_tokens = usage.get("total_tokens") or (prompt_tokens + completion_tokens)
    return prompt_tokens, completion_tokens, total_tokens


def _register_failure(db: DB, task: dict, now: datetime) -> bool:
    """记录一次运行失败并安排后续动作。

    首次失败：next_run_at 推到 5 分钟后，调度器到点自动重试一次；
    重试仍失败：停用任务（enabled=0）并按正常计划预留 next_run_at，
    彻底终结「失败 → 立即到期 → 再失败」的无限循环。
    返回 True 表示重试已耗尽、任务被停用，调用方应发送停用告警。
    """
    task_id = task["id"]
    fail_count = int(task.get("fail_count") or 0) + 1
    exhausted = fail_count >= AI_TASK_MAX_CONSECUTIVE_FAILS
    if exhausted:
        next_run = calculate_next_run(task, now)
        db.update_ai_task(
            task_id,
            enabled=False,
            fail_count=fail_count,
            last_run_at=now.isoformat(),
            last_run_status="failed",
            next_run_at=next_run.isoformat() if next_run else None,
        )
        logger.error(
            "[AI Task] 任务 %s（%s）自动重试后仍失败，已停用调度", task_id, task.get("name")
        )
    else:
        retry_at = now + timedelta(seconds=AI_TASK_RETRY_DELAY_SECONDS)
        db.update_ai_task(
            task_id,
            fail_count=fail_count,
            last_run_at=now.isoformat(),
            last_run_status="failed",
            next_run_at=retry_at.isoformat(),
        )
        logger.warning(
            "[AI Task] 任务 %s 运行失败，%d 分钟后自动重试（第 %d 次）",
            task_id, AI_TASK_RETRY_DELAY_SECONDS // 60, fail_count,
        )
    return exhausted


def _failed_result(message: str, *, retries_exhausted: bool = False,
                   prompt_tokens: int = 0, completion_tokens: int = 0,
                   total_tokens: int = 0) -> dict[str, Any]:
    return {
        "success": False,
        "message": message,
        "post_id": None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "retries_exhausted": retries_exhausted,
    }


def run_analysis_task(task_id: int, db: DB) -> dict[str, Any]:
    """执行一次分析任务

    Returns:
        dict with keys:
        success: bool
        message: str
        post_id: int | None (if created)
        prompt_tokens: int
        completion_tokens: int
        total_tokens: int
        retries_exhausted: bool (重试耗尽、任务已被停用，调用方应发送告警)
    """
    logger.info(f"[AI Task] 开始执行任务 {task_id}")
    task = db.get_ai_task(task_id)
    if not task:
        logger.error(f"[AI Task] 任务 {task_id} 不存在")
        return _failed_result(f"任务 {task_id} 不存在")
    
    logger.info(f"[AI Task] 任务详情: {task}")
    
    now = datetime.now(timezone.utc)
    start_time, end_time = calculate_time_range(task, now)
    logger.info(f"[AI Task] 时间范围: {start_time} 到 {end_time}")
    
    # 创建日志
    logger.info(f"[AI Task] 创建运行日志")
    log_id = db.create_ai_log(task_id, now.isoformat(), "running")
    logger.info(f"[AI Task] 日志 ID: {log_id}")
    
    try:
        # 1. 获取目标KOL信息
        target_kol = db.get_kol(task["target_kol_id"])
        if not target_kol:
            exhausted = _register_failure(db, task, now)
            db.update_ai_log(log_id, status="failed", message="目标KOL不存在", completed_at=now.isoformat())
            return _failed_result("目标KOL不存在", retries_exhausted=exhausted)
        
        # 2. 获取需要分析的帖子
        # published_at 是发帖时间的北京时间裸字符串（YYYY-MM-DD HH:MM，全表统一），
        # 用本地墙钟字符串做比较才能取到「对应时间段的消息」；
        # fetched_at 是抓取时间，会把窗口外发布、启动后才抓到的旧帖混进来。
        selected_kol_ids = task["selected_kol_ids"]
        posts = []
        if selected_kol_ids:
            placeholders = ", ".join("?" for _ in selected_kol_ids)
            rows = db._rows(
                f"""SELECT p.*, k.name as kol_name FROM posts p
                   JOIN kols k ON p.kol_id = k.id
                   WHERE p.kol_id IN ({placeholders})
                   AND p.post_type != 'ai_analysis'
                   AND COALESCE(p.blocked, 0) = 0
                   AND p.published_at >= ? AND p.published_at <= ?
                   ORDER BY p.published_at ASC""",
                (*selected_kol_ids,
                 start_time.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                 end_time.astimezone().strftime("%Y-%m-%d %H:%M:%S"))
            )
            posts = [dict(row) for row in rows]

        # 记录本窗口内实际拿到的发言条数（0 也记录，便于排查「分析了个啥」）
        db.update_ai_log(log_id, post_count=len(posts))
        
        # 3. 构建提示词
        prompt = build_prompt(task, posts, start_time, end_time)
        # 先落库,失败/超时也能在日志里看到当时发给大模型的内容
        db.update_ai_log(log_id, prompt_text=prompt)
        
        # 4. 调用LLM
        from .config import load_config
        config = load_config()
        
        llm_config = type('', (), {})()
        llm_config.api_key = db.get_setting("llm_api_key") or config.llm.api_key or ""
        llm_config.api_base = db.get_setting("llm_api_base") or config.llm.api_base or "https://api.openai.com/v1"
        llm_config.model = db.get_setting("llm_model") or config.llm.model or "gpt-4o-mini"
        llm_config.user_supplied = False
        
        logger.info(f"[AI Task] 读取 LLM 配置: api_base={llm_config.api_base}, model={llm_config.model}, api_key_set={bool(llm_config.api_key)}")
        
        if not llm_config.api_key:
            exhausted = _register_failure(db, task, now)
            db.update_ai_log(log_id, status="failed", message="LLM未配置", completed_at=now.isoformat())
            return _failed_result("LLM未配置", retries_exhausted=exhausted)
        
        llm_result, usage = llm._chat(
            llm_config,
            [
                {"role": "system", "content": "你是专业的内容分析师，生成简明扼要的报告。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=80000,
            timeout=300.0,
            return_usage=True
        )

        prompt_tokens, completion_tokens, total_tokens = extract_token_usage(usage)
        finish_reason = usage.get("finish_reason") if isinstance(usage, dict) else None
        truncated = finish_reason == "length"
        if truncated:
            logger.warning(f"[AI Task] 任务 {task_id} 输出因 max_tokens 上限被截断（finish_reason=length），报告不完整")

        if llm_result is None:
            exhausted = _register_failure(db, task, now)
            db.update_ai_log(
                log_id, status="failed", message="LLM调用失败",
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens,
                completed_at=datetime.now(timezone.utc).isoformat()
            )
            return _failed_result(
                "LLM调用失败",
                retries_exhausted=exhausted,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
        
        # 5. 保存为目标KOL的帖子
        analysis_content = llm._message_text(llm_result) if isinstance(llm_result, dict) else str(llm_result)

        # 发布时间取「大模型返回结果的时刻」而不是任务开始时刻：
        # LLM 调用可能耗时数分钟，用开始时间会让时间线里的报告出现在实际生成之前
        completed_at_local = datetime.now(timezone.utc).astimezone()

        # 生成一个唯一的external_id
        external_id = f"ai_analysis_{task_id}_{now.strftime('%Y%m%d_%H%M%S')}"

        # 先查询是否已存在（幂等）
        existing = db._rows(
            "SELECT id FROM posts WHERE platform = ? AND external_id = ?",
            (target_kol["platform"], external_id)
        )
        if existing:
            post_id = existing[0]["id"]
        else:
            # 创建帖子
            post_id = db.insert_post(
                platform=target_kol["platform"],
                kol_id=task["target_kol_id"],
                external_id=external_id,
                title=f"AI分析报告 - {task['name']}",
                content=analysis_content,
                url="",
                # published_at 约定为北京时间裸字符串（与其余帖子一致），前端按墙钟展示；
                # 带秒位：时间线按 published_at 排序，同分钟消息需要秒位保序
                published_at=completed_at_local.strftime("%Y-%m-%d %H:%M:%S"),
                post_type="ai_analysis"
            )
        
        # 6. 更新日志和任务
        success_msg = "分析完成（输出因 max_tokens 上限被截断，内容不完整）" if truncated else "分析完成"
        db.update_ai_log(
            log_id,
            status="success",
            message=success_msg,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            output_post_id=post_id,
            completed_at=datetime.now(timezone.utc).isoformat()
        )
        
        next_run = calculate_next_run(task, now)
        db.update_ai_task(
            task_id,
            last_run_at=now.isoformat(),
            last_run_status="success",
            fail_count=0,
            next_run_at=next_run.isoformat() if next_run else None
        )

        return {
            "success": True,
            "message": success_msg,
            "post_id": post_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "retries_exhausted": False,
        }

    except Exception as e:
        logger.exception(f"AI分析任务 {task_id} 执行失败")
        error_msg = str(e)[:500]
        exhausted = _register_failure(db, task, now)
        db.update_ai_log(
            log_id,
            status="failed",
            message=error_msg,
            completed_at=datetime.now(timezone.utc).isoformat()
        )
        return _failed_result(
            error_msg,
            retries_exhausted=exhausted,
        )


def run_due_analysis_tasks(db: DB) -> None:
    """运行所有到期的AI分析任务"""
    now = datetime.now(timezone.utc)
    tasks = db.get_due_ai_tasks(now.isoformat())
    for task in tasks:
        if task["enabled"]:
            run_analysis_task(task["id"], db)
