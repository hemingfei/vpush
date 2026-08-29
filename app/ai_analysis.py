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


def parse_schedule_days(day_of_week_str: str) -> list[int]:
    """解析星期几配置字符串为整数列表"""
    if not day_of_week_str:
        return []
    days = []
    for part in day_of_week_str.split(","):
        try:
            day = int(part.strip())
            if 0 <= day <= 6:
                days.append(day)
        except ValueError:
            continue
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

    # 从明天开始找下一个符合的星期几
    next_candidate = _local_wall_time(now, 1, task["schedule_time"])

    for _ in range(14):  # 最多找两周
        if next_candidate.weekday() in schedule_days:
            return next_candidate.astimezone(timezone.utc)
        next_candidate += timedelta(days=1)

    return None


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
    """
    logger.info(f"[AI Task] 开始执行任务 {task_id}")
    task = db.get_ai_task(task_id)
    if not task:
        logger.error(f"[AI Task] 任务 {task_id} 不存在")
        return {
            "success": False,
            "message": f"任务 {task_id} 不存在",
            "post_id": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    
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
            db.update_ai_log(log_id, status="failed", message="目标KOL不存在", completed_at=now.isoformat())
            return {
                "success": False,
                "message": "目标KOL不存在",
                "post_id": None,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        
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
            db.update_ai_log(log_id, status="failed", message="LLM未配置", completed_at=now.isoformat())
            return {
                "success": False,
                "message": "LLM未配置",
                "post_id": None,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
        
        llm_result, usage = llm._chat(
            llm_config,
            [
                {"role": "system", "content": "你是专业的内容分析师，生成简明扼要的报告。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000,
            return_usage=True
        )

        prompt_tokens, completion_tokens, total_tokens = extract_token_usage(usage)

        if llm_result is None:
            db.update_ai_log(
                log_id, status="failed", message="LLM调用失败",
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens,
                completed_at=datetime.now(timezone.utc).isoformat()
            )
            return {
                "success": False,
                "message": "LLM调用失败",
                "post_id": None,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }
        
        # 5. 保存为目标KOL的帖子
        analysis_content = llm._message_text(llm_result) if isinstance(llm_result, dict) else str(llm_result)
        
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
                published_at=now.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                post_type="ai_analysis"
            )
        
        # 6. 更新日志和任务
        db.update_ai_log(
            log_id,
            status="success",
            message="分析完成",
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
            next_run_at=next_run.isoformat() if next_run else None
        )
        
        return {
            "success": True,
            "message": "分析完成",
            "post_id": post_id,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
    
    except Exception as e:
        logger.exception(f"AI分析任务 {task_id} 执行失败")
        error_msg = str(e)[:500]
        db.update_ai_log(
            log_id,
            status="failed",
            message=error_msg,
            completed_at=datetime.now(timezone.utc).isoformat()
        )
        next_run = calculate_next_run(task, now)
        db.update_ai_task(
            task_id,
            last_run_at=now.isoformat(),
            last_run_status="failed",
            next_run_at=next_run.isoformat() if next_run else None
        )
        return {
            "success": False,
            "message": error_msg,
            "post_id": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }


def run_due_analysis_tasks(db: DB) -> None:
    """运行所有到期的AI分析任务"""
    now = datetime.now(timezone.utc)
    tasks = db.get_due_ai_tasks(now.isoformat())
    for task in tasks:
        if task["enabled"]:
            run_analysis_task(task["id"], db)
