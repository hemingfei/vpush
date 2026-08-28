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


def calculate_time_range(task: dict, now: datetime) -> tuple[datetime, datetime]:
    """根据任务配置计算实际的开始/结束时间"""
    # 计算开始时间
    start_offset = timedelta(days=task["time_range_start_days_offset"])
    start_time_parts = task["time_range_start_time"].split(":")
    start_hour = int(start_time_parts[0])
    start_minute = int(start_time_parts[1]) if len(start_time_parts) > 1 else 0
    start = now + start_offset
    start = start.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    
    # 计算结束时间
    end_offset = timedelta(days=task["time_range_end_days_offset"])
    end_time_parts = task["time_range_end_time"].split(":")
    end_hour = int(end_time_parts[0])
    end_minute = int(end_time_parts[1]) if len(end_time_parts) > 1 else 0
    end = now + end_offset
    end = end.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    
    return start, end


def calculate_next_run(task: dict, now: datetime) -> datetime | None:
    """计算任务的下次运行时间"""
    schedule_days = parse_schedule_days(task["schedule_day_of_week"])
    if not schedule_days:
        return None
    
    schedule_time_parts = task["schedule_time"].split(":")
    schedule_hour = int(schedule_time_parts[0])
    schedule_minute = int(schedule_time_parts[1]) if len(schedule_time_parts) > 1 else 0
    
    # 从明天开始找下一个符合的星期几
    next_candidate = now + timedelta(days=1)
    next_candidate = next_candidate.replace(hour=schedule_hour, minute=schedule_minute, 
                                           second=0, microsecond=0)
    
    for _ in range(14):  # 最多找两周
        if next_candidate.weekday() in schedule_days:
            return next_candidate
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
    
    # 格式化时间范围
    time_range_str = f"{start.strftime('%Y-%m-%d %H:%M')} ~ {end.strftime('%Y-%m-%d %H:%M')}"
    
    # 格式化消息
    messages_str = format_messages_for_llm(posts)
    
    # 替换变量
    prompt = template
    prompt = prompt.replace("{time_range}", time_range_str)
    prompt = prompt.replace("{kol_names}", ", ".join(kol_names) if kol_names else "无")
    prompt = prompt.replace("{messages}", messages_str)
    
    return prompt


def extract_token_usage(llm_result: dict | None) -> tuple[int, int, int]:
    """从LLM结果中提取token使用情况"""
    if not llm_result or not isinstance(llm_result, dict):
        return 0, 0, 0
    usage = llm_result.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens") or 0
    completion_tokens = usage.get("completion_tokens") or 0
    total_tokens = usage.get("total_tokens") or (prompt_tokens + completion_tokens)
    return prompt_tokens, completion_tokens, total_tokens


def run_analysis_task(task_id: int, db: DB) -> dict[str, Any]:
    """执行一次分析任务
    
    Returns:
        dict with keys:
        - success: bool
        - message: str
        - post_id: int | None (if created)
        - prompt_tokens: int
        - completion_tokens: int
        - total_tokens: int
    """
    task = db.get_ai_task(task_id)
    if not task:
        return {
            "success": False,
            "message": f"任务 {task_id} 不存在",
            "post_id": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    
    now = datetime.now(timezone.utc)
    start_time, end_time = calculate_time_range(task, now)
    
    # 创建日志
    log_id = db.create_ai_log(task_id, now.isoformat(), "running")
    
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
        selected_kol_ids = task["selected_kol_ids"]
        posts = []
        if selected_kol_ids:
            placeholders = ", ".join("?" for _ in selected_kol_ids)
            rows = db._rows(
                f"""SELECT p.*, k.name as kol_name FROM posts p
                   JOIN kols k ON p.kol_id = k.id
                   WHERE p.kol_id IN ({placeholders})
                   AND p.fetched_at >= ? AND p.fetched_at <= ?
                   ORDER BY p.fetched_at ASC""",
                (*selected_kol_ids, start_time.isoformat(), end_time.isoformat())
            )
            posts = [dict(row) for row in rows]
        
        # 3. 构建提示词
        prompt = build_prompt(task, posts, start_time, end_time)
        
        # 4. 调用LLM
        llm_config = type('', (), {})()
        llm_config.api_key = db.get_setting("llm_api_key") or ""
        llm_config.api_base = db.get_setting("llm_api_base") or ""
        llm_config.model = db.get_setting("llm_model") or "gpt-4o-mini"
        llm_config.user_supplied = False
        
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
        
        llm_result = llm._chat(
            llm_config,
            [
                {"role": "system", "content": "你是专业的内容分析师，生成简明扼要的报告。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        
        prompt_tokens, completion_tokens, total_tokens = extract_token_usage(llm_result)
        
        if llm_result is None:
            db.update_ai_log(
                log_id, status="failed", message="LLM调用失败",
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens,
                completed_at=now.isoformat()
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
                published_at=now.isoformat(),
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
            completed_at=now.isoformat()
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
