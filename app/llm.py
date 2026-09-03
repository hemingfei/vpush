"""可选 LLM：站点默认 Grok（管理员推送设置），用户可自配覆盖。

设计要点：
- 失败静默降级：任何异常只记日志并返回 None，调用方回退原逻辑；
- 只传帖文标题/大V/平台/摘要，不传用户隐私字段。
"""
from __future__ import annotations

import json
import logging
import re
import time

logger = logging.getLogger(__name__)

# 摘要通常几秒到十几秒；标记解析走 thinking + JSON，16 条实测约 150s。
DEFAULT_CHAT_TIMEOUT = 60
MARK_RESOLVE_TIMEOUT = 180

class _RetryableError(Exception):
    """瞬时错误（429/5xx/空响应），可重试一次。"""


def _config_values(llm_config):
    api_key = getattr(llm_config, "api_key", "") if llm_config else ""
    if not api_key:
        return None
    api_base = (getattr(llm_config, "api_base", "") or "https://api.openai.com/v1").rstrip("/")
    if getattr(llm_config, "user_supplied", False):
        from .url_safety import is_allowed_user_llm_base

        if not is_allowed_user_llm_base(api_base):
            logger.warning("拒绝不安全的用户 LLM 地址")
            return None
    return api_key, api_base, getattr(llm_config, "model", "") or "gpt-4o-mini"


def _message_text(message: dict) -> str:
    """取出模型正文；thinking 模型常把结果放在 reasoning_content。"""
    content = (message or {}).get("content")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        content = "".join(parts)
    text = str(content or "").strip()
    if text:
        return text
    return str((message or {}).get("reasoning_content") or "").strip()


def _chat(
    llm_config,
    messages,
    max_tokens,
    client=None,
    temperature=0.3,
    attempts: int = 2,
    response_format=None,
    timeout: float = DEFAULT_CHAT_TIMEOUT,
    return_usage: bool = False,
) -> str | tuple[str, dict] | None:
    """OpenAI 兼容 chat/completions；未配置或失败返回 None。

    return_usage=True 时成功返回 (文本, usage 字典)，失败返回 (None, {})，
    供需要统计 token 的调用方（如 AI 分析任务）使用。
    """
    values = _config_values(llm_config)
    if values is None:
        return (None, {}) if return_usage else None
    api_key, api_base, model = values
    import httpx

    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        last_err: Exception | None = None
        use_format = response_format
        use_max_tokens = max_tokens is not None
        attempt = 0
        while attempt < attempts:
            try:
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                # 部分服务端（如火山方舟）会校验 max_tokens 并对超限值返回 400，
                # 触发后降级为不传该字段，由服务端按模型自身的输出上限处理
                if use_max_tokens:
                    payload["max_tokens"] = max_tokens
                if use_format:
                    payload["response_format"] = use_format
                resp = client.post(
                    f"{api_base}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
                if resp.status_code == 400 and use_format:
                    use_format = None
                    # 参数降级不消耗重试次数
                    attempt -= 1
                    raise _RetryableError("LLM 不支持 response_format")
                if resp.status_code == 400 and use_max_tokens:
                    use_max_tokens = False
                    # 参数降级不消耗重试次数
                    attempt -= 1
                    raise _RetryableError(f"LLM 拒绝请求参数（可能 max_tokens 超限）: {resp.text[:200]}")
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise _RetryableError(f"LLM HTTP {resp.status_code}")
                resp.raise_for_status()
                try:
                    data = resp.json()
                except ValueError:
                    # 网关返回非 JSON（HTML 错误页等）：按瞬时错误走重试
                    raise _RetryableError(f"LLM 响应非 JSON: {resp.text[:120]}") from None
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                finish_reason = choice.get("finish_reason")
                text = _message_text(message)
                if not text:
                    raise _RetryableError("LLM 返回空")
                if finish_reason == "length":
                    logger.warning("LLM 输出因 max_tokens 上限被截断（finish_reason=length），内容不完整")
                if return_usage:
                    usage = dict(data.get("usage") or {})
                    usage["finish_reason"] = finish_reason
                    return text, usage
                return text
            except httpx.HTTPStatusError as exc:
                last_err = exc
                break
            except (httpx.TransportError, _RetryableError) as exc:
                last_err = exc
            if attempt + 1 < attempts:
                time.sleep(2)
            attempt += 1
        logger.warning("LLM 请求失败: %s", last_err)
        return (None, {}) if return_usage else None
    finally:
        if owns_client:
            client.close()


def list_models(llm_config) -> list[str] | None:
    """GET {base}/models，OpenAI 兼容。失败返回 None。"""
    values = _config_values(llm_config)
    if values is None:
        return None
    api_key, api_base, _model = values
    import httpx

    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(
                f"{api_base}/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code >= 400:
            logger.warning("LLM /models HTTP %s", resp.status_code)
            return None
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM /models 失败: %s", exc)
        return None
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return None
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        if isinstance(row, str):
            item = row.strip()
        elif isinstance(row, dict):
            item = str(row.get("id") or "").strip()
        else:
            continue
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    out.sort()
    return out


SUMMARY_SYSTEM_PROMPT = (
    "你是信息摘要助手。把下面用户订阅的社交动态整理成简洁的中文要点。"
    "要求：按重要性排序，每条要点一行，以「- 」开头；"
    "先写一句总览（共 N 条，涉及哪些大V/话题），再列要点；"
    "保留关键数字与结论，去掉寒暄与无关细节；不要添加原文没有的信息。"
)


def _post_lines(posts) -> list[str]:
    from .fetchers.base import digest_body

    # 帖少给全文（更完整上下文），帖多控制每条预算，总量仍 ≤ 12000
    per_post = 2000 if len(posts) <= 2 else 400
    lines = []
    for post in posts:
        platform = getattr(post, "platform", "")
        kol = getattr(post, "kol_name", "") or ""
        mark = "[原帖]" if (getattr(post, "post_type", "") or "") != "reply" else "[回复]"
        body = digest_body(post, full=False, max_chars=per_post)
        lines.append(f"{mark}[{platform}] {kol}：{body}")
    return lines


def summary_cache_key(posts, api_base: str, model: str) -> str:
    """摘要缓存键：平台+外部ID 有序拼接，同一批帖文（同配置）复用同一份摘要。"""
    ids = ",".join(f"{p.platform}:{p.external_id}" for p in posts)
    return f"{api_base}|{model}|{ids}"


def summarize_posts(posts, llm_config=None, client=None, cache=None) -> str | None:
    """生成摘要文本；未配置或失败返回 None（调用方降级为普通汇总）。

    cache: 可选 dict，以「配置+帖文ID列表」为键缓存摘要，同一批帖文只调一次
    大模型（批量推送时多个订阅用户共享同一份摘要）。
    """
    values = _config_values(llm_config)
    if values is None:
        return None
    _, api_base, model = values
    posts = sorted(posts, key=lambda p: (getattr(p, "post_type", "") or "") == "reply")
    content = "\n".join(_post_lines(posts))
    if not content.strip():
        return None
    key = summary_cache_key(posts, api_base, model) if cache is not None else None
    if key is not None and key in cache:
        return cache[key]
    if not any(
        (getattr(p, "content", "") or "").strip() or (getattr(p, "title", "") or "").strip()
        for p in posts
    ):
        return None
    text = _chat(
        llm_config,
        [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"共 {len(posts)} 条动态，请整理要点：\n{content[:12000]}"},
        ],
        min(8000, max(2000, 200 + 120 * len(posts))),
        client=client,
    )
    if text is None:
        return None
    if key is not None:
        cache[key] = text
    return text


# ---- 每日精选综述 ----

from dataclasses import dataclass, field


@dataclass
class DailyPoint:
    """综述里的一个要点：text 是正文，post_indexes 是依据的帖子在输入列表中的下标。"""

    text: str
    post_indexes: list[int] = field(default_factory=list)


@dataclass
class DailySummary:
    """每日精选综述：总览 + 按重要性/话题组织的要点列表。"""

    overview: str
    points: list[DailyPoint] = field(default_factory=list)


DAILY_SUMMARY_SYSTEM_PROMPT = (
    "你是财经内容主编，负责把用户今天订阅的社交动态综合整理成一份信息量充足的每日综述。"
    "要求："
    "1. 先写一句总览（如内容丰富可再加一句补充），点明今天共多少条动态、涉及哪些大V、当天主线话题；"
    "2. 把全部内容综合成要点，最多 8 条：重要观点单独成条，同类话题合并成一条；"
    "   覆盖当天值得关注的全部动态，不要因为追求精简而漏掉重要内容；"
    "3. 每条要点 100~150 字：点明是谁（大V名）说的、核心观点与关键数字，"
    "   并补一句关键依据（怎么说的/为什么/影响）；细节论证过程可省略；"
    "4. 每条要点单独一行、以「- 」开头，末尾标注依据的帖子序号，格式（[N]）或（[N][M]），对应输入行开头的序号；"
    "5. 保留关键数字与结论，去掉寒暄与无关细节；不要添加原文没有的信息，不要臆测。"
    "输出除总览和要点外不要任何解释；不要把要点写成连续段落。"
)


def _daily_lines(posts) -> list[str]:
    """把一批贴文转成「序号. [原帖|回复][平台] KOL：正文摘要」的行，供每日综述。"""
    from .fetchers.base import digest_body

    per_post = 2000 if len(posts) <= 2 else 600  # 每日综述输出更宽，输入预算同步放宽
    lines = []
    for idx, post in enumerate(posts, start=1):
        platform = getattr(post, "platform", "") or ""
        kol = getattr(post, "kol_name", "") or ""
        mark = "[原帖]" if (getattr(post, "post_type", "") or "") != "reply" else "[回复]"
        body = digest_body(post, full=False, max_chars=per_post)
        lines.append(f"{idx}. {mark}[{platform}] {kol}：{body}")
    return lines


def _parse_daily_summary(text: str, post_count: int) -> DailySummary | None:
    """宽松解析每日综述：首段（首个要点前的非列表行）为总览，列表行为要点。

    要点行接受「- / • / * / 1.」等常见列表前缀；行尾形如（[1]）或（[1][3]）的
    数字标记解析为帖子下标（容忍后面带句号/逗号等标点，LLM 常顺手加）。序号必须
    落在 1..post_count 内，越界/非数字丢弃；要点无有效序号则保留但不带链接。
    解析失败或没有要点时返回 None（调用方降级为原始列表）。
    """
    if not text:
        return None
    lines = text.strip().splitlines()
    overview_lines: list[str] = []
    points: list[DailyPoint] = []
    cite_re = re.compile(r"（((?:\[\d+\])+)）")

    def _indexes_from(body: str) -> tuple[str, list[int]]:
        indexes: list[int] = []
        tail = body
        while True:
            idx_match = re.search(r"（((?:\[\d+\])+)）[。．.，,；;！!？?]?\s*$", tail)
            if not idx_match:
                break
            for num_str in re.findall(r"\[(\d+)\]", idx_match.group(1)):
                num = int(num_str)
                if 1 <= num <= post_count and num - 1 not in indexes:
                    indexes.append(num - 1)
            tail = tail[: idx_match.start()].rstrip("。．.，,；;！!？? ").rstrip()
        return tail or body, indexes

    for line in lines:
        stripped = line.strip()
        match = re.match(r"^(?:[-•*]\s+|[-•*]|\d+[.、]\s+)(.*)$", stripped, re.DOTALL)
        if match:
            body = match.group(1).strip()
            if not body:
                continue
            tail, indexes = _indexes_from(body)
            points.append(DailyPoint(text=tail or body, post_indexes=indexes))
        elif stripped:
            overview_lines.append(stripped)
    # grok-4.6 常把要点写成带（[N]）的段落而不是「- 」列表
    if not points:
        blob = " ".join(overview_lines).strip()
        cited = list(cite_re.finditer(blob))
        if cited:
            overview_end = cited[0].start()
            lead = blob[:overview_end].strip()
            overview_lines = [lead] if lead else []
            starts = [0] + [m.end() for m in cited[:-1]]
            for start, match in zip(starts, cited):
                chunk = blob[start:match.end()].strip()
                tail, indexes = _indexes_from(chunk)
                if tail:
                    points.append(DailyPoint(text=tail, post_indexes=indexes))
    # 解析层强制上限：模型可能输出超过 8 条，只保留前八条（顺序与引用序号不变）
    points = points[:8]
    if not points:
        logger.warning("LLM 每日综述无要点，降级为原始列表")
        return None
    overview = " ".join(overview_lines).strip()
    return DailySummary(overview=overview, points=points)


def render_daily_summary(summary: DailySummary, posts=None) -> str:
    """把综述渲染成纯文本：标题 + 总览 + 编号要点。

    posts 可选：传入后每条要点末尾附依据帖子的原文链接（取第一个依据帖），
    不传则纯文本不带链接（保持旧行为）。
    """
    lines = ["📊 今日大V精选（LLM 梳理）"]
    if summary.overview:
        lines += ["", summary.overview]
    for idx, point in enumerate(summary.points, start=1):
        line = f"{idx}. {point.text}"
        url = _point_source_url(posts, point.post_indexes)
        if url:
            line += f"（🔗 {url}）"
        lines.append(line)
    return "\n".join(lines)


def _point_source_url(posts, post_indexes) -> str:
    """取要点依据的第一个帖子链接；posts 为 None 或帖子无链接时返回空串。"""
    if not posts or not post_indexes:
        return ""
    for idx in post_indexes:
        if 0 <= idx < len(posts):
            url = (getattr(posts[idx], "url", "") or "").strip()
            if url:
                return url
    return ""


def summarize_daily(posts, llm_config=None, client=None) -> DailySummary | None:
    """生成每日精选综述；未配置或失败返回 None（调用方降级为原始列表）。

    与 summarize_posts 同款降级/重试策略；只传帖文标题/大V/平台/摘要，不传用户隐私字段。
    """
    content = "\n".join(_daily_lines(posts))
    if not content.strip():
        return None
    text = _chat(
        llm_config,
        [
            {"role": "system", "content": DAILY_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": f"共 {len(posts)} 条动态，请整理成每日综述：\n{content[:12000]}"},
        ],
        4000,
        client=client,
        # grok-4.6 thinking + 长提示经常超过默认 60s，超时会降级成原文列表
        timeout=MARK_RESOLVE_TIMEOUT,
        attempts=1,
    )
    return _parse_daily_summary(text or "", len(posts))


# ---- 股票黑话别名识别（每日一次低频任务） ----

ALIAS_SYSTEM_PROMPT = (
    "你是财经社区黑话翻译器。用户会给你一份帖子中高频出现的候选词列表，"
    "以及一份已知股票名列表。请判断哪些候选词是某只已知股票的别名/昵称"
    "（如「宁王」→「宁德时代」、「药茅」→「恒瑞医药」）。"
    "只输出 JSON 数组，每个元素："
    '{"alias": "候选词", "stock": "对应已知股票名", "confidence": "high|medium|none"}。'
    "confidence 为 high（确定是别名）或 medium（很可能是，但需留意）；"
    "不是股票别名的标 none 或直接省略。除 JSON 外不要输出任何内容。"
)


def suggest_stock_aliases(candidates, known_stocks, llm_config=None, client=None) -> list[dict]:
    """让 LLM 判断候选词是否为已知股票别名，返回 [{"alias","stock","confidence"}]。

    未配置 LLM 或任何失败返回 []（调用方跳过本次识别）；confidence 为
    high/medium 的条目保留（调度层只采纳 high 自动写入），none 丢弃。
    """
    if not candidates:
        return []
    text = _chat(
        llm_config,
        [
            {"role": "system", "content": ALIAS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"候选词（可能含股票别名）：{json.dumps(candidates[:100], ensure_ascii=False)}\n"
                    f"已知股票名：{json.dumps(known_stocks, ensure_ascii=False)}"
                ),
            },
        ],
        2000,
        client=client,
        temperature=0,
        attempts=1,
        response_format={"type": "json_object"},
    )
    if not text:
        return []
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        logger.warning("LLM 别名识别无 JSON 数组: %.100s", text)
        return []
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return []
    result = []
    known_lower = {str(s).lower() for s in known_stocks}
    for item in parsed if isinstance(parsed, list) else []:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("alias") or "").strip()
        stock = str(item.get("stock") or "").strip()
        confidence = str(item.get("confidence") or "none").strip().lower()
        if alias and stock and stock.lower() in known_lower and confidence in ("high", "medium"):
            result.append({"alias": alias, "stock": stock, "confidence": confidence})
    logger.info("LLM 别名识别候选=%d 采纳=%d", len(candidates), len(result))
    return result


# ---- 股票标记解析（$标记$ → 官方名/戏称） ----

MARK_RESOLVE_SYSTEM_PROMPT = (
    "你是 A 股股票名称解析器。用户给你一批雪球帖子里的股票标记，"
    "格式为「名称(代码)」，例如 涂改液(SZ000858)。"
    "请判断每个名称是该股票的正式名称还是网友戏称/简称："
    "若名称是正式名（如 中际旭创、盐湖股份），输出 official 为该名称、is_alias 为 false；"
    "若名称是戏称/简称（如 涂改液=五粮液、贵州茅坑=贵州茅台、兆易=兆易创新），"
    "输出 official 为正式名、is_alias 为 true。"
    "只输出 JSON 数组，每个元素："
    '{"name": "标记里的名称", "code": "代码", "official": "正式名称", "is_alias": true|false}。'
    "名称或代码无法对应任何已知股票时输出 is_alias 为 false、official 为该名称即可（视为正式名兜底）。"
    "除 JSON 外不要输出任何内容。"
)


def resolve_stock_marks(marks, llm_config=None, client=None) -> list[dict]:
    """让 LLM 解析一批 $股票名(代码)$ 标记，区分正式名与戏称/简称。

    输入 marks: [(name, code), ...]（已去重）；输出：
    [{"name", "code", "official", "is_alias": bool}, ...]
    is_alias=false → 官方名进股票名表；is_alias=true → 戏称进别名表。
    未配置 LLM 或任何失败返回 []（静默跳过本轮）。
    """
    if not marks:
        return []
    text = _chat(
        llm_config,
        [
            {"role": "system", "content": MARK_RESOLVE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "股票标记列表：\n"
                + "\n".join(f"{name}({code})" for name, code in marks),
            },
        ],
        2000,
        client=client,
        temperature=0,
        attempts=2,
        response_format={"type": "json_object"},
        timeout=MARK_RESOLVE_TIMEOUT,
    )
    if not text:
        return []
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        logger.warning("LLM 标记解析无 JSON 数组: %.100s", text)
        return []
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return []
    valid_prefixes = ("SH", "SZ", "BJ")
    result = []
    for item in parsed if isinstance(parsed, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        code = str(item.get("code") or "").strip().upper()
        official = str(item.get("official") or "").strip()
        is_alias = bool(item.get("is_alias"))
        if not name or not official:
            continue
        if code and not code.startswith(valid_prefixes):
            continue
        result.append(
            {"name": name, "code": code, "official": official, "is_alias": is_alias}
        )
    logger.info("LLM 标记解析 marks=%d 解析=%d", len(marks), len(result))
    return result


# ---- MX 消息批量打标（话题/股票/操作 + 黑话映射，app/mx_llm_tagging.py 调用） ----

# 与标记解析同量级：thinking + 40 条消息的三类标签 JSON 输出
TAG_CHAT_TIMEOUT = 180
TAG_BATCH_MAX_TOKENS = 6000
# 单条消息送入 LLM 的正文截断长度（MX 群消息多为短句，500 字足够上下文）
TAG_INPUT_TEXT_MAX = 500

# 规则与少样本示例是稳定部分（利于 prompt cache）；词表/股票参考由
# build_tag_system_prompt() 每次调用时拼在尾部（管理员改词表下一批即生效）
TAG_SYSTEM_PROMPT_HEADER = (
    "你是 A 股财经社区的贴文打标器。社区发言大量使用黑话、戏称、简称甚至错别字指代"
    "股票，请给每条消息打标签，并整理出你用到的黑话映射。\n"
    "\n"
    "【判定规则】\n"
    "1. 股票（≤2）：official 必须是真实存在的股票正式简称。你熟知 A 股所有股票的正式"
    "名称、简称和昵称，可以立刻判断一句话里提到的股票是哪只；黑话/简称/昵称/错别字"
    "一律还原成正式简称（如 宁王→宁德时代）。没有明确指向的股票不要输出。\n"
    "2. 话题（≤3）：只能从「话题词表」里选，不要发明新话题。\n"
    "3. 操作（≤2）：只能从「操作词表」里选；只有明确表达买卖动作时才输出（如“加了点/减了/"
    "做了个T/先看着”）；仅描述持仓现状不算操作。\n"
    "4. confidence 两档：high=有明确依据（名称、代码、公认黑话、明确上下文）；low=拼写相近"
    "但不确定、需要脑补、泛泛提及。拿不准一律 low。\n"
    "5. jargon：把你在本条消息中用到的黑话/简称/错别字映射列出来，kind 三选一：\n"
    "   - general：社区通用黑话，其他作者也这么用（如 宁王→宁德时代）\n"
    "   - context：仅当前这条消息的语境成立，不能推广（如某作者这条消息里用“芒果”指芒果超媒）\n"
    "   - typo：错别字/音近字（如 申领环境→申菱环境）\n"
    "   只有确定是 general 才标 general，拿不准标 context。\n"
    "6. 宁缺毋滥：没有把握的维度输出空数组；每条消息都必须输出，消息 id 原样带回。\n"
    "7. 只输出一个 JSON 对象，不要输出任何其他内容。格式：\n"
    '{"results":[{"id":101,"topics":[{"name":"话题","confidence":"high|low"}],'
    '"stocks":[{"official":"正式简称","raw":"原文词","confidence":"high|low"}],'
    '"actions":[{"name":"操作","confidence":"high|low"}],'
    '"jargon":[{"raw":"原文词","official":"正式名","kind":"general|context|typo"}]}]}\n'
    "\n"
    "【示例】\n"
    "输入消息：\n"
    '[{"id":101,"author":"修心见道","text":"申领环境，又红5以上减的，均线低吃回来，做了个T"},\n'
    ' {"id":102,"author":"修心见道","text":"芒果都绿了，真牛逼。"},\n'
    ' {"id":103,"author":"轻舟","text":"轻神农，明天看看大盘再说"}]\n'
    "输出：\n"
    '{"results":[\n'
    ' {"id":101,"topics":[{"name":"个股","confidence":"high"}],\n'
    '  "stocks":[{"official":"申菱环境","raw":"申领环境","confidence":"high"}],\n'
    '  "actions":[{"name":"做T","confidence":"high"},{"name":"减仓","confidence":"low"}],\n'
    '  "jargon":[{"raw":"申领环境","official":"申菱环境","kind":"typo"}]},\n'
    ' {"id":102,"topics":[{"name":"个股","confidence":"low"}],\n'
    '  "stocks":[{"official":"芒果超媒","raw":"芒果","confidence":"high"}],\n'
    '  "actions":[],"jargon":[{"raw":"芒果","official":"芒果超媒","kind":"context"}]},\n'
    ' {"id":103,"topics":[{"name":"大盘","confidence":"high"}],\n'
    '  "stocks":[{"official":"神农种业","raw":"神农","confidence":"high"}],\n'
    '  "actions":[{"name":"建仓","confidence":"low"}],\n'
    '  "jargon":[{"raw":"神农","official":"神农种业","kind":"context"}]}]}\n'
)


def build_tag_system_prompt(tag_rules, action_tags, stock_names, aliases=None) -> str:
    """拼装打标系统提示词：稳定规则/示例 + 当次生效的话题词表/操作词表/股票参考。"""
    topic_lines = []
    for rule in tag_rules or []:
        if not isinstance(rule, dict):
            continue
        tag = str(rule.get("tag") or "").strip()
        if not tag:
            continue
        keywords = [str(k).strip() for k in (rule.get("keywords") or []) if str(k).strip()]
        topic_lines.append(f"{tag}: {'、'.join(keywords)}" if keywords else tag)
    actions = [str(a).strip() for a in (action_tags or []) if str(a).strip()]
    names = [str(n).strip() for n in (stock_names or []) if str(n).strip()]
    alias_pairs = []
    for item in aliases or []:
        if not isinstance(item, dict):
            continue
        alias = str(item.get("alias") or "").strip()
        stock = str(item.get("stock") or "").strip()
        if alias and stock:
            alias_pairs.append(f"{alias}={stock}")
    parts = [TAG_SYSTEM_PROMPT_HEADER, "【话题词表】"]
    parts.append("\n".join(topic_lines) if topic_lines else "（空）")
    parts.append("\n【操作词表】\n" + ("、".join(actions) if actions else "（空）"))
    parts.append(
        "\n【已知股票与黑话参考】（可输出参考之外的 A 股正式简称）\n"
        + ("、".join(names) if names else "（空）")
    )
    if alias_pairs:
        parts.append("\n" + "\n".join(alias_pairs))
    return "\n".join(parts)


def _tag_confidence(value) -> str:
    return "high" if str(value or "").strip().lower() == "high" else "low"


def _normalize_tag_items(raw) -> list[dict]:
    """话题/操作条目归一：[{name, confidence}]，name 非空才保留。"""
    items: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        items.append({"name": name, "confidence": _tag_confidence(item.get("confidence"))})
    return items


def _normalize_stock_items(raw) -> list[dict]:
    items: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        official = str(item.get("official") or "").strip()
        if not official:
            continue
        items.append(
            {
                "official": official,
                "raw": str(item.get("raw") or "").strip(),
                "confidence": _tag_confidence(item.get("confidence")),
            }
        )
    return items


def _normalize_jargon(raw) -> list[dict]:
    items: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        raw_term = str(item.get("raw") or "").strip()
        official = str(item.get("official") or "").strip()
        if not raw_term or not official:
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in ("general", "context", "typo"):
            kind = "context"  # 未知 kind 按最保守处理，防止语境映射被全局化
        items.append({"raw": raw_term, "official": official, "kind": kind})
    return items


def tag_posts_llm(
    posts,
    tag_rules,
    action_tags,
    stock_names,
    aliases=None,
    llm_config=None,
    client=None,
) -> dict[int, dict] | None:
    """让 LLM 给一批 MX 消息打话题/股票/操作三类标签并整理黑话映射。

    posts: [{id, kol_name, title, content}, ...]（list_mx_posts_after 的行，id 升序）。
    返回 {post_id: {"topics","stocks","actions","jargon"}}（仅做结构归一，词表/
    全市场校验由调用方完成）；任何失败返回 None（整批失败语义）。
    """
    rows = list(posts or [])
    if not rows:
        return {}
    id_set = set()
    messages = []
    for row in rows:
        try:
            pid = int(row["id"])
        except (KeyError, TypeError, ValueError):
            continue
        id_set.add(pid)
        text = " ".join(
            (
                str(row.get("title") or "").strip(),
                str(row.get("content") or "").strip(),
            )
        ).strip()[:TAG_INPUT_TEXT_MAX]
        messages.append(
            {"id": pid, "author": str(row.get("kol_name") or ""), "text": text}
        )
    if not messages:
        return {}
    system = build_tag_system_prompt(tag_rules, action_tags, stock_names, aliases)
    text = _chat(
        llm_config,
        [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": "消息列表：\n"
                + json.dumps(messages, ensure_ascii=False),
            },
        ],
        TAG_BATCH_MAX_TOKENS,
        client=client,
        temperature=0,
        attempts=2,
        response_format={"type": "json_object"},
        timeout=TAG_CHAT_TIMEOUT,
    )
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        logger.warning("LLM 打标无 JSON 对象: %.100s", text)
        return None
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        logger.warning("LLM 打标 JSON 解析失败: %.100s", text)
        return None
    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list):
        logger.warning("LLM 打标缺少 results 数组: %.100s", text)
        return None
    out: dict[int, dict] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            pid = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if pid not in id_set or pid in out:
            continue
        out[pid] = {
            "topics": _normalize_tag_items(item.get("topics")),
            "stocks": _normalize_stock_items(item.get("stocks")),
            "actions": _normalize_tag_items(item.get("actions")),
            "jargon": _normalize_jargon(item.get("jargon")),
        }
    logger.info("LLM 打标 posts=%d 解析=%d", len(messages), len(out))
    return out
