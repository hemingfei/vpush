"""可选 LLM：站点默认来自环境变量，用户可自配覆盖。

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
USER_LLM_MAX_BYTES = 2 * 1024 * 1024


def normalize_llm_api_format(value: str | None) -> str:
    raw = str(value or "").strip().lower().replace("_", "-")
    if raw in ("responses", "openai-responses"):
        return "responses"
    return "chat"


def with_llm_overrides(llm_config, **over):
    if llm_config is None:
        return None
    from types import SimpleNamespace

    data = dict(vars(llm_config))
    data.update(over)
    return SimpleNamespace(**data)


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


def _completion_text(payload, api_format: str) -> str:
    if not isinstance(payload, dict):
        return ""
    if api_format == "responses":
        text = str(payload.get("output_text") or "").strip()
        if text:
            return text
        for item in payload.get("output") or []:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        t = str(block.get("text") or "").strip()
                        if t:
                            return t
            elif isinstance(content, str) and content.strip():
                return content.strip()
    message = ((payload.get("choices") or [{}])[0].get("message")) or {}
    return _message_text(message)


def _usage_total(payload) -> int | None:
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    for key in ("total_tokens", "total_token_count"):
        if usage.get(key) is not None:
            try:
                return int(usage[key])
            except (TypeError, ValueError):
                return None
    try:
        inp = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        out = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        return None
    return inp + out or None


def _chat(
    llm_config,
    messages,
    max_tokens,
    client=None,
    temperature=0.3,
    attempts: int = 2,
    response_format=None,
    timeout: float = DEFAULT_CHAT_TIMEOUT,
    meta: dict | None = None,
) -> str | None:
    """OpenAI 兼容 chat/completions 或 /responses；未配置或失败返回 None。"""
    values = _config_values(llm_config)
    if values is None:
        return None
    api_key, api_base, model = values
    api_format = normalize_llm_api_format(getattr(llm_config, "api_format", ""))
    import httpx

    user_supplied = bool(getattr(llm_config, "user_supplied", False))
    owns_client = client is None
    client = client or httpx.Client(timeout=timeout)
    try:
        last_err: Exception | None = None
        use_format = response_format
        for attempt in range(attempts):
            try:
                if api_format == "responses":
                    url = f"{api_base}/responses"
                    payload = {
                        "model": model,
                        "input": messages,
                        "temperature": temperature,
                        "max_output_tokens": max_tokens,
                    }
                    if use_format:
                        payload["text"] = {"format": use_format}
                else:
                    url = f"{api_base}/chat/completions"
                    payload = {
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    }
                    if use_format:
                        payload["response_format"] = use_format
                if user_supplied:
                    from .url_safety import safe_request_limited

                    resp = safe_request_limited(
                        client,
                        "POST",
                        url,
                        max_bytes=USER_LLM_MAX_BYTES,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        content=json.dumps(payload).encode(),
                        timeout=timeout,
                        follow_redirects=False,
                    )
                    if 300 <= resp.status_code < 400:
                        last_err = _RetryableError("LLM 拒绝跟随重定向")
                        break
                else:
                    resp = client.post(
                        url,
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=payload,
                    )
                if resp.status_code == 400 and use_format:
                    use_format = None
                    raise _RetryableError("LLM 不支持 response_format")
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise _RetryableError(f"LLM HTTP {resp.status_code}")
                resp.raise_for_status()
                try:
                    body = resp.json()
                except ValueError:
                    # 网关返回非 JSON（HTML 错误页等）：按瞬时错误走重试
                    raise _RetryableError(f"LLM 响应非 JSON: {resp.text[:120]}") from None
                text = _completion_text(body, api_format)
                if not text:
                    raise _RetryableError("LLM 返回空")
                if meta is not None:
                    usage = _usage_total(body)
                    if usage is not None:
                        meta["usage"] = usage
                return text
            except httpx.HTTPStatusError as exc:
                last_err = exc
                break
            except (httpx.TransportError, _RetryableError, ValueError) as exc:
                last_err = exc
            if attempt + 1 < attempts:
                time.sleep(2)
        logger.warning("LLM 请求失败: %s", last_err)
        return None
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

    user_supplied = bool(getattr(llm_config, "user_supplied", False))
    try:
        with httpx.Client(timeout=20) as client:
            if user_supplied:
                from .url_safety import safe_request_limited

                resp = safe_request_limited(
                    client,
                    "GET",
                    f"{api_base}/models",
                    max_bytes=USER_LLM_MAX_BYTES,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=20,
                    follow_redirects=False,
                )
                if 300 <= resp.status_code < 400:
                    logger.warning("LLM /models 拒绝跟随重定向")
                    return None
            else:
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


def probe_llm(llm_config, client=None) -> dict:
    """用当前配置打一条最短请求，返回 ok/耗时/用量。"""
    started = time.monotonic()
    meta: dict = {}
    text = _chat(
        llm_config,
        [{"role": "user", "content": "Reply with exactly: PONG"}],
        16,
        client=client,
        temperature=0,
        attempts=1,
        timeout=20,
        meta=meta,
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    if not text:
        return {"ok": False, "latency_ms": latency_ms, "error": "无响应或地址/Key/模型不正确"}
    result = {
        "ok": True,
        "latency_ms": latency_ms,
        "format": normalize_llm_api_format(getattr(llm_config, "api_format", "")),
        "model": getattr(llm_config, "model", "") or "",
    }
    if meta.get("usage") is not None:
        result["usage"] = {"total_tokens": meta["usage"]}
    return result


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


def summary_cache_key(posts, api_base: str, model: str, api_format: str = "chat") -> str:
    """摘要缓存键：平台+外部ID 有序拼接，同一批帖文（同配置）复用同一份摘要。"""
    ids = ",".join(f"{p.platform}:{p.external_id}" for p in posts)
    return f"{api_base}|{model}|{normalize_llm_api_format(api_format)}|{ids}"


def summarize_posts(posts, llm_config=None, client=None, cache=None) -> str | None:
    """生成摘要文本；未配置或失败返回 None（调用方降级为普通汇总）。

    推送摘要固定 Chat Completions（thinking/Responses 贵且慢）。
    cache: 可选 dict，以「配置+帖文ID列表」为键缓存摘要，同一批帖文只调一次
    大模型（批量推送时多个订阅用户共享同一份摘要）。
    """
    llm_config = with_llm_overrides(llm_config, api_format="chat")
    values = _config_values(llm_config)
    if values is None:
        return None
    _, api_base, model = values
    posts = sorted(posts, key=lambda p: (getattr(p, "post_type", "") or "") == "reply")
    content = "\n".join(_post_lines(posts))
    if not content.strip():
        return None
    key = summary_cache_key(posts, api_base, model, "chat") if cache is not None else None
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
    llm_config = with_llm_overrides(llm_config, api_format="chat")
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


# ---- 研报结构化抽取（批处理，失败降级为无结构化数据） ----

REPORT_EXTRACT_MAX_CHARS = 12000
REPORT_EXTRACT_TIMEOUT = 90

_REPORT_EXTRACT_PROMPT = (
    "从中文或英文研报文本中抽取结构化信息，只输出一个 JSON 对象（不要 markdown 代码块、不要解释），字段：\n"
    '{"rating": "评级原文（如 首次覆盖/维持/增持/Buy/Outperform，无则空串）", '
    '"target_price": "目标价原文（含币种或区间，无则空串）", '
    '"thesis": "简体中文的一句话核心逻辑，不超过80字，无则空串", '
    '"report_kind": "宏观/策略/行业/公司/固收 之一", '
    '"tickers": [{"code": "证券代码", "name": "证券简称", "stance": "推荐/受益/中性/风险提示"}]}\n'
    "证券代码保留市场常用格式：A 股用 6 位数字，美股如 NVDA，港股如 700.HK；"
    "只抽取文本明确提到的事实，不确定就留空；tickers 最多 8 个，按重要性排序。"
)

_REPORT_TITLE_RATINGS = (
    "Strong Buy",
    "Market Outperform",
    "Outperform",
    "Overweight",
    "Market Perform",
    "Equal-weight",
    "Underperform",
    "Underweight",
    "Neutral",
    "Hold",
    "Buy",
    "Sell",
    "跑赢行业",
    "首次覆盖",
    "买入",
    "增持",
    "推荐",
    "中性",
    "持有",
    "减持",
    "卖出",
)


def _report_title_rating(title: str) -> str:
    """只接受标题中独立出现的常见评级，避免从正文猜测。"""
    text = str(title or "")
    for rating in _REPORT_TITLE_RATINGS:
        if re.search(rf"(?<![A-Za-z]){re.escape(rating)}(?![A-Za-z])", text, re.IGNORECASE):
            return rating
    return ""


def _parse_report_extraction(content: str) -> dict:
    """容错解析 LLM 抽取输出：剥代码围栏、截取首尾大括号。"""
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("抽取结果不含 JSON 对象")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("抽取结果不是 JSON 对象")
    return data


def clean_report_extraction(data: dict, universe: dict[str, str]) -> dict:
    """规范化抽取字段；标的按词表白名单校验，词表没有的代码视为幻觉丢弃。"""
    rating = str(data.get("rating") or "").strip()[:24]
    target_price = str(data.get("target_price") or "").strip()[:64]
    thesis = " ".join(str(data.get("thesis") or "").split())[:200]
    report_kind = str(data.get("report_kind") or "").strip()[:12]
    tickers: list[dict] = []
    seen: set[str] = set()
    for item in data.get("tickers") or []:
        if not isinstance(item, dict):
            continue
        raw_code = str(item.get("code") or "").strip()
        normalized_code = raw_code.upper()
        a_share_match = re.fullmatch(
            r"(?:SH|SZ|BJ)?(\d{6})(?:[.:](?:SH|SZ|BJ|SS))?", normalized_code
        )
        a_share_code = a_share_match.group(1) if a_share_match else ""
        name = str(item.get("name") or "").strip()[:32]
        if a_share_code and (not universe or a_share_code in universe):
            # A 股词表命中：代码归一为 6 位，名称以词表为准
            code = a_share_code
        elif name and re.search(r"[A-Z]", normalized_code) and re.fullmatch(
            r"[A-Z0-9]{1,6}([.:][A-Z0-9]{1,4})?", normalized_code
        ):
            # 非词表代码（美股/港股等）：保留原代码形态，但须带名称且形态合规
            code = normalized_code[:16]
        else:
            # 词表未命中且形态可疑（幻觉）→ 丢弃
            continue
        if code in seen:
            continue
        seen.add(code)
        tickers.append(
            {
                "code": code,
                "name": universe.get(code) or name,
                "stance": str(item.get("stance") or "").strip()[:16],
            }
        )
        if len(tickers) >= 8:
            break
    status = "ok" if (rating or target_price or thesis or tickers) else "empty"
    return {
        "rating": rating,
        "target_price": target_price,
        "thesis": thesis,
        "report_kind": report_kind,
        "tickers": tickers,
        "status": status,
    }


def extract_report_structure(
    text: str,
    llm_config=None,
    model: str = "",
    universe: dict[str, str] | None = None,
    client=None,
    title: str = "",
) -> dict:
    """抽取单篇研报结构化信息；LLM 失败抛 RuntimeError，解析失败抛 ValueError。

    成功返回 {rating, target_price, thesis, report_kind, tickers, status}，
    文本过短或确认无结构信息时 status='empty'。
    """
    body = " ".join((text or "").split())
    report_title = " ".join((title or "").split())
    if len(body) < 200 and not report_title:
        return clean_report_extraction({}, universe or {})
    values = _config_values(llm_config)
    if values is None:
        raise RuntimeError("LLM 未配置")
    api_key, api_base, default_model = values
    from types import SimpleNamespace

    task_cfg = SimpleNamespace(
        api_key=api_key,
        api_base=api_base,
        user_supplied=False,
        model=(model or default_model),
    )
    content = _chat(
        task_cfg,
        [{
            "role": "user",
            "content": (
                f"{_REPORT_EXTRACT_PROMPT}\n\n"
                f"标题：{report_title}\n正文：{body[:REPORT_EXTRACT_MAX_CHARS]}"
            ),
        }],
        max_tokens=2000,
        client=client,
        temperature=0.1,
        attempts=1,
        timeout=REPORT_EXTRACT_TIMEOUT,
    )
    if not content:
        raise RuntimeError("LLM 抽取请求失败")
    parsed = _parse_report_extraction(content)
    if not str(parsed.get("rating") or "").strip():
        parsed["rating"] = _report_title_rating(report_title)
    return clean_report_extraction(parsed, universe or {})
