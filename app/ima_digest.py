"""标的聚合编译：把同一标的历史研报的要点汇编成一篇持续更新的中文综述。

与 report_extractions（逐篇抽取）的区别：这里编译的是"跨文档"产物——同一标的
谁给了什么评级/目标价、观点怎么演变，因此按聚合单元缓存，源研报没变就不重编。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from .llm import (
    _chat,
    _config_values,
    _parse_report_extraction,
    report_rating_zh,
)

DIGEST_KIND = "ticker"
DIGEST_MAX_TOKENS = 3000
DIGEST_TIMEOUT = 120
# 参与编译的研报上限：热门标的历史很长，prompt 只需近期观点（老观点已进综述文本）。
DIGEST_MAX_REPORTS = 40
DIGEST_THESIS_CHARS = 300

_DIGEST_PROMPT = (
    "你是投研编辑。下面是同一标的（{code} {name}）的多篇研报要点，按时间从新到旧排列。\n"
    "请把它们交叉汇编成一篇中文综述，而不是逐篇摘要。要求：\n"
    "1. consensus：2-4 句「当前共识」，含最新评级/目标价区间与多空分歧。\n"
    "2. evolution：按时间列出观点演变，只保留实质变化，相同观点合并；date 用 YYYY-MM-DD。\n"
    "3. divergence：机构之间的分歧，以及明确的负面/风险表述。\n"
    "只输出一个 JSON 对象（不要 markdown 代码块、不要解释），字段：\n"
    '{{"consensus": "...", "evolution": [{{"date": "YYYY-MM-DD", "point": "..."}}], "divergence": "..."}}\n'
    "资料没有的信息写空字符串或空数组，不要编造。"
)


def _source_lines(reports: list[dict], limit: int = DIGEST_MAX_REPORTS) -> list[str]:
    """把研报行渲染成 prompt 行：日期 | 标题 | 评级/目标价 | 中文要点。"""
    lines: list[str] = []
    for row in reports[:limit]:
        thesis = " ".join(str(row.get("thesis") or "").split())
        if not thesis:
            continue
        rating = report_rating_zh(str(row.get("rating") or ""))
        target = str(row.get("target_price") or "").strip()
        head = " | ".join(
            part
            for part in (
                str(row.get("sort_date") or row.get("day") or "无日期"),
                " ".join(str(row.get("name") or "").split())[:80],
                " ".join(part for part in (rating, f"目标价 {target}" if target else "") if part),
            )
            if part
        )
        lines.append(f"{head} | {thesis[:DIGEST_THESIS_CHARS]}")
    return lines


def clean_ticker_digest(data: dict) -> dict:
    """规范化编译输出，保证前端拿到的三个字段一定存在。"""
    evolution = []
    for item in data.get("evolution") or []:
        if not isinstance(item, dict):
            continue
        point = " ".join(str(item.get("point") or "").split())
        if point:
            evolution.append(
                {
                    "date": str(item.get("date") or "").strip()[:10],
                    "point": point[:400],
                }
            )
    return {
        "consensus": " ".join(str(data.get("consensus") or "").split())[:1200],
        "evolution": evolution[:24],
        "divergence": " ".join(str(data.get("divergence") or "").split())[:1200],
    }


def compile_ticker_digest(
    reports: list[dict],
    code: str,
    llm_config=None,
    *,
    name: str = "",
    model: str = "",
    client=None,
) -> dict:
    """编译单个标的的综述；LLM 未配置/请求失败抛 RuntimeError，解析失败抛 ValueError。

    返回 {digest: dict, model: str, source_count: int}。
    """
    lines = _source_lines(reports)
    if not lines:
        raise ValueError("该标的没有可编译的中文要点")
    values = _config_values(llm_config)
    if values is None:
        raise RuntimeError("LLM 未配置")
    api_key, api_base, default_model = values
    task_cfg = SimpleNamespace(
        api_key=api_key,
        api_base=api_base,
        user_supplied=False,
        model=(model or default_model),
    )
    content = _chat(
        task_cfg,
        [
            {
                "role": "user",
                "content": (
                    f"{_DIGEST_PROMPT.format(code=code, name=name)}\n\n"
                    "研报要点：\n" + "\n".join(lines)
                ),
            }
        ],
        max_tokens=DIGEST_MAX_TOKENS,
        client=client,
        temperature=0.2,
        attempts=1,
        timeout=DIGEST_TIMEOUT,
    )
    if not content:
        raise RuntimeError("LLM 编译请求失败")
    return {
        "digest": clean_ticker_digest(_parse_report_extraction(content)),
        "model": task_cfg.model,
        "source_count": len(lines),
    }


def compile_and_store(
    db,
    code: str,
    llm_config=None,
    *,
    name: str = "",
    signature: str = "",
    group_ids=None,
    source_count: int = 0,
    client=None,
    model: str = "",
) -> dict:
    """编译一个标的并落库；失败时按 failed 落行（避免每轮重试同一条）。

    返回落库的行内容（含 status）。
    """
    reports = db.ima_ticker_reports(code, group_ids)
    try:
        built = compile_ticker_digest(
            reports, code, llm_config, name=name, model=model, client=client
        )
    except Exception as error:
        db.save_ima_digest(
            code,
            name=name,
            signature=signature,
            source_count=source_count,
            digest="",
            model=model,
            status=f"failed:{type(error).__name__}",
        )
        raise
    digest_text = json.dumps(built["digest"], ensure_ascii=False)
    db.save_ima_digest(
        code,
        name=name,
        signature=signature,
        source_count=source_count,
        digest=digest_text,
        model=built["model"],
        status="ok",
    )
    return {
        "code": code,
        "name": name,
        "signature": signature,
        "source_count": source_count,
        "digest": digest_text,
        "model": built["model"],
        "status": "ok",
    }


def digest_view(row: dict) -> dict:
    """DB 行 → 接口视图：digest 文本解析回结构化对象（坏数据降级为原始文本）。"""
    if not row:
        return {}
    raw = str(row.get("digest") or "")
    parsed: dict = {}
    if raw:
        try:
            parsed = clean_ticker_digest(json.loads(raw))
        except ValueError:
            parsed = {"consensus": raw[:1200], "evolution": [], "divergence": ""}
    return {
        "code": str(row.get("code") or ""),
        "name": str(row.get("name") or ""),
        "source_count": int(row.get("source_count") or 0),
        "model": str(row.get("model") or ""),
        "status": str(row.get("status") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        **parsed,
    }
