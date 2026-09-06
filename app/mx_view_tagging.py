"""智囊团观点回流打标：把快照研判出的板块/个股多空观点回写到证据帖的标签体系。

挂点在 mx_view_analysis.run_snapshot_batch 的观点落库之后（live/手动跑批/
历史回填共用同一条路），每条已校验观点 × 每个证据帖：

- 个股名在有效名单（常用名表 ∪ 别名正式名 ∪ 全市场简称，去排除项）内且
  confidence=high：直写股票标签，并登记来源 source=mx_view、观点方向；
- 个股名名单外（两字名未入常用表、非 A 股名等）：不直写，进 post_tag_reviews
  待审——兼做名字发现，管理员通过后标签上帖；
- 题材名在题材参考表（mx_view_analysis 的 topic_hints）内且 high：直写话题标签；
  新题材跳过（题材候选审核流负责名字本身，采纳后后续快照自动打上）；
- 操作（建仓/加仓/…，校验层已保证在操作词表内）且 high：直写操作标签；
- confidence=low 的观点一律不直写，按类型进待审。

写入用 merge_post_view_tags（不置 llm_tagged，不偷 LLM 打标游标的帖子）；
零 LLM 调用，merge 去重 + 同帖同标签 UNIQUE 天然幂等，回填重放安全。
方向不进标签文本（标签体系保持极性无关），多空维度活在登记表里：
查看弹窗/审核队列/帖子标签徽标按 source 与 direction 区分展示。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 回流打标开关（settings 键）：默认关，管理后台「打标」页开启后下一快照生效
MX_VIEW_TAGGING_ENABLED_KEY = "mx_view_tagging_enabled"


def get_view_tagging_enabled(db) -> bool:
    return str(db.get_setting(MX_VIEW_TAGGING_ENABLED_KEY) or "0") == "1"


def set_view_tagging_enabled(db, enabled: bool) -> None:
    db.set_setting(MX_VIEW_TAGGING_ENABLED_KEY, "1" if bool(enabled) else "0")


def _valid_stock_universe(db) -> set[str]:
    """直写股票标签的有效名单：常用名表 ∪ 别名正式名 ∪ 全市场简称（去排除项）。

    与 mx_llm_tagging._tag_inputs 的 valid_stocks 同口径。
    """
    from .stock_universe import aliases_for_tagging, names_for_plain_text_tagging

    excluded = db.get_stock_name_exclusions()
    names = names_for_plain_text_tagging(db.get_stock_names(), excluded)
    aliases = aliases_for_tagging(db.get_stock_aliases(), excluded)
    return set(names) | {a["stock"] for a in aliases}


def apply_view_tags(db, opinions, topic_hints=None) -> dict:
    """把一批已校验观点回写到证据帖标签，返回 {posts, applied, reviews} 计数。

    opinions 为 validate_opinions 校验后的观点（target 名已过黑话归一、合并
    名已拆分）；topic_hints 为题材参考表（测试可显式传入，线上由调用方传
    run_snapshot_batch 已加载的同一份，避免两处读 settings 不一致）。
    """
    from .stock_universe import bundled_plain_names

    valid_stocks = _valid_stock_universe(db)
    excluded = set(db.get_stock_name_exclusions())
    valid_stocks |= {n for n in bundled_plain_names() if n not in excluded}
    hints = {str(h).strip() for h in (topic_hints or []) if str(h).strip()}

    writes: dict[int, list[str]] = {}          # pid -> 待合并标签（保序去重）
    applied: dict[tuple[int, str], tuple[str, str]] = {}   # (pid, tag) -> (kind, direction)
    reviews: dict[tuple[int, str], list] = {}  # (pid, tag) -> [kind, direction]

    for op in opinions or []:
        try:
            post_ids = [int(p) for p in (op.get("evidence_post_ids") or [])]
        except (TypeError, ValueError):
            continue
        ttype = str(op.get("target_type") or "")
        name = str(op.get("target_name") or "").strip()
        if not name or not post_ids:
            continue
        high = str(op.get("confidence") or "high") == "high"
        direction = str(op.get("direction") or "")
        direction = direction if direction in ("bull", "bear") else ""
        kind = "stock" if ttype == "stock" else "topic" if ttype == "topic" else ""
        if not kind:
            continue

        if kind == "stock":
            write_now = high and name in valid_stocks
        else:
            # 题材：参考表内 high 直写；新题材一律跳过（题材候选审核流负责）
            write_now = high and name in hints
        if write_now:
            for pid in post_ids:
                tags = writes.setdefault(pid, [])
                if name not in tags:
                    tags.append(name)
                applied.setdefault((pid, name), (kind, direction))
        elif kind == "stock" or (kind == "topic" and name in hints):
            # 个股一律「不能直写就进审」（名单外/low）；题材仅参考表内 low 进审
            for pid in post_ids:
                slot = reviews.setdefault((pid, name), [kind, ""])
                if not slot[1] and direction:
                    slot[1] = direction

        action = str(op.get("action") or "").strip()
        if high and action:
            for pid in post_ids:
                tags = writes.setdefault(pid, [])
                if action not in tags:
                    tags.append(action)
                applied.setdefault((pid, action), ("action", direction))

    for pid, tags in writes.items():
        db.merge_post_view_tags(pid, tags)
    for (pid, tag), (kind, direction) in applied.items():
        db.record_applied_tag(pid, tag, kind, source="mx_view", direction=direction)
    review_logged = 0
    for (pid, tag), (kind, direction) in reviews.items():
        if db.add_pending_tag_review(pid, tag, kind, "low", source="mx_view", direction=direction):
            review_logged += 1
    summary = {"posts": len(writes), "applied": len(applied), "reviews": review_logged}
    if summary["posts"] or summary["reviews"]:
        logger.info(
            "智囊团观点回流打标：帖 %d 条，直写标签 %d 个，进审核 %d 个",
            summary["posts"], summary["applied"], summary["reviews"],
        )
    return summary
