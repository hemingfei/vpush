"""AI分析核心逻辑"""
from __future__ import annotations
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from . import llm
from .db import DB
# 项目统一按北京时间（东八区）解释「本地墙钟」，不依赖部署环境的 TZ 环境变量
from .fetchers.base import CN_TZ

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

    表单时间一律按北京时间（东八区）理解，固定用 CN_TZ 换算，不依赖进程时区
    （旧实现 now_utc.astimezone() 跟随环境 TZ，部署漏配 TZ 时窗口会整体漂移）；
    返回带东八区时区的 aware datetime，由调用方按需转 UTC。
    """
    parts = hhmm.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        # API 校验层已拦一道；这里自保，防历史脏数据让 replace 抛裸 ValueError
        raise ValueError(f"非法时刻 {hhmm!r}：小时须 0-23、分钟须 0-59")
    local = now_utc.astimezone(CN_TZ) + timedelta(days=days_offset)
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0)


def calculate_time_range(task: dict, now: datetime) -> tuple[datetime, datetime]:
    """根据任务配置计算实际的开始/结束时间。

    表单时间按北京时间理解；posts 表 published_at 存北京时间裸字符串
    （YYYY-MM-DD HH:MM，全表统一），调用方以东八区墙钟字符串做比较，这里返回 aware UTC。
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
    if next_candidate <= now.astimezone(CN_TZ):
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


# 送入 LLM 的消息正文总字符预算：每帖虽截 2000 字，但条数不限，
# 窗口配宽/选人大多时 prompt 可达数 MB，必然超模型上下文
# → 两次尝试+重试耗尽 → 任务被自动停用。超预算按时间从旧到新丢弃（保最新）。
AI_PROMPT_TOTAL_CHAR_BUDGET = 24000


def format_messages_for_llm(posts: list[dict]) -> str:
    """将帖子列表格式化为LLM可读的文本

    调用方按时间升序传入（最新在末尾）；总量超过 AI_PROMPT_TOTAL_CHAR_BUDGET 时
    从最早的帖子开始丢弃（保最新），并在文末注明因长度截断了多少条。
    """
    if not posts:
        return "(无发言内容)"

    blocks = []
    for post in posts:
        platform = post.get("platform", "")
        kol_name = post.get("kol_name", "未知")
        published_at = post.get("published_at", "")
        fetched_at = post.get("fetched_at", "")
        title = (post.get("title") or "").strip()
        content = (post.get("content") or "").strip()

        time_str = published_at or fetched_at
        block = [f"--- [{platform}] {kol_name} @ {time_str} ---"]
        if title:
            block.append(f"标题: {title}")
        if content:
            block.append(f"内容: {content[:2000]}")  # 限制单条长度
        blocks.append("\n".join(block))

    # 总量预算：从最新（列表末尾）往前保留，预算耗尽即停；至少保留最新一条
    kept = []
    total = 0
    for block in reversed(blocks):
        cost = len(block) + 2  # +2 为块间空行分隔符
        if kept and total + cost > AI_PROMPT_TOTAL_CHAR_BUDGET:
            break
        total += cost
        kept.append(block)
    kept.reverse()
    dropped = len(blocks) - len(kept)
    if dropped > 0:
        kept.append(f"(注：发言较多，因长度限制已省略最早的 {dropped} 条)")
        logger.warning(
            "[AI Task] 消息正文超预算 %d 字符，从最早开始丢弃 %d 条（共 %d 条）",
            AI_PROMPT_TOTAL_CHAR_BUDGET, dropped, len(blocks),
        )

    return "\n\n".join(kept)


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
    
    # 格式化时间范围（按北京时间展示，与表单理解一致，不随进程时区漂移）
    time_range_str = (f"{start.astimezone(CN_TZ).strftime('%Y-%m-%d %H:%M')}"
                      f" ~ {end.astimezone(CN_TZ).strftime('%Y-%m-%d %H:%M')}")
    
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
        # 用东八区墙钟字符串做比较才能取到「对应时间段的消息」；
        # fetched_at 是抓取时间，会把窗口外发布、启动后才抓到的旧帖混进来。
        # 窗口串统一到分钟粒度（与 published_at 存储格式一致）：带秒比较会让
        # 恰好落在开始端点的帖子因串更短被排他（D6），两端语义不对称。
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
                 start_time.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M"),
                 end_time.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M"))
            )
            posts = [dict(row) for row in rows]

        # 记录本窗口内实际拿到的发言条数（0 也记录，便于排查「分析了个啥」）
        db.update_ai_log(log_id, post_count=len(posts))

        # 3. 窗口内 0 条消息：不调 LLM、不发空报告，直接落成功日志并排下次运行。
        # 否则空窗口任务每轮都白烧一次 LLM 调用（还可能因配额/网络失败被误停用）
        if not posts:
            next_run = calculate_next_run(task, now)
            db.update_ai_log(
                log_id, status="success", message="窗口内无发言，跳过分析",
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            db.update_ai_task(
                task_id,
                last_run_at=now.isoformat(),
                last_run_status="success",
                fail_count=0,
                next_run_at=next_run.isoformat() if next_run else None,
            )
            logger.info(f"[AI Task] 任务 {task_id} 窗口内无发言，跳过 LLM 调用")
            return {
                "success": True,
                "message": "窗口内无发言，跳过分析",
                "post_id": None,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "retries_exhausted": False,
            }

        # 4. 构建提示词
        prompt = build_prompt(task, posts, start_time, end_time)
        # 先落库,失败/超时也能在日志里看到当时发给大模型的内容
        db.update_ai_log(log_id, prompt_text=prompt)
        
        # 5. 调用LLM
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
        
        # LLM 返回后、发帖前重读任务 enabled：调度器取任务到线程真正执行可能间隔数十秒，
        # 期间管理员可能已禁用任务，此时不能照常把报告发出去。
        # 只记 skipped 日志：不发帖、不计失败（fail_count 不动），任务保持禁用，
        # 管理员重新启用时 api 侧会重算 next_run_at。
        latest_task = db.get_ai_task(task_id) or {}
        if not latest_task.get("enabled"):
            logger.warning(f"[AI Task] 任务 {task_id} 执行期间已被禁用，丢弃分析结果不发报告")
            db.update_ai_log(
                log_id, status="skipped", message="任务已禁用，跳过发布",
                prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            return {
                "success": False,
                "message": "任务已禁用，跳过发布",
                "post_id": None,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "retries_exhausted": False,
            }

        # 6. 保存为目标KOL的帖子
        analysis_content = llm._message_text(llm_result) if isinstance(llm_result, dict) else str(llm_result)

        # 发布时间取「大模型返回结果的时刻」而不是任务开始时刻：
        # LLM 调用可能耗时数分钟，用开始时间会让时间线里的报告出现在实际生成之前；
        # published_at 全表按北京时间展示，固定用 CN_TZ，不随进程时区漂移
        completed_at_local = datetime.now(timezone.utc).astimezone(CN_TZ)

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
        
        # 7. 更新日志和任务
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


