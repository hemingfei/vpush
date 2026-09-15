"""待审标签大众评审：普通用户点开待审标签投票，按票型自动裁决。

裁决规则（管理员后台可配）：
- 一致裁决（unanimous_n，默认 2）：投票人数达到该值且全部同向时立即裁决
  （全通过→通过，全拒绝→拒绝）；票型分裂则继续收集更多用户的投票；
- 最终裁决（max_voters，默认 10）：投票人数达到该值时按多数裁决，
  通过票多于拒绝票才通过；平票与少数派一并裁决为拒绝（保守口径：
  标签上帖是持久写入，不因平票而通过）。

管理员在弹窗里的通过/拒绝不走投票，直接生效（与后台审核队列同口径）。
开关关闭时普通用户只读，仅管理员可裁决。
"""
from __future__ import annotations

# settings 键与默认值
TAG_REVIEW_PUBLIC_VOTING_KEY = "tag_review_public_voting"      # "1"/"0"，默认开
TAG_REVIEW_UNANIMOUS_N_KEY = "tag_review_unanimous_n"          # 一致裁决人数，默认 2
TAG_REVIEW_MAX_VOTERS_KEY = "tag_review_max_voters"            # 最终裁决人数，默认 10

DEFAULT_UNANIMOUS_N = 2
DEFAULT_MAX_VOTERS = 10

# 保存时的合法区间（管理员误配 0/负数会让规则退化成单人定终局或永不裁决）
MIN_UNANIMOUS_N, MAX_UNANIMOUS_N = 1, 50
MIN_MAX_VOTERS, MAX_MAX_VOTERS = 1, 200

VOTE_APPROVE = "approve"
VOTE_REJECT = "reject"


def get_review_config(db) -> dict:
    """读大众评审配置：开关、一致裁决人数、最终裁决人数（缺省用内置默认）。"""
    try:
        unanimous_n = int(str(db.get_setting(TAG_REVIEW_UNANIMOUS_N_KEY) or "").strip()
                           or DEFAULT_UNANIMOUS_N)
    except ValueError:
        unanimous_n = DEFAULT_UNANIMOUS_N
    try:
        max_voters = int(str(db.get_setting(TAG_REVIEW_MAX_VOTERS_KEY) or "").strip()
                         or DEFAULT_MAX_VOTERS)
    except ValueError:
        max_voters = DEFAULT_MAX_VOTERS
    return {
        "public_voting": str(db.get_setting(TAG_REVIEW_PUBLIC_VOTING_KEY) or "1") == "1",
        "unanimous_n": unanimous_n,
        "max_voters": max_voters,
    }


def save_review_config(db, public_voting: bool, unanimous_n: int, max_voters: int) -> dict:
    """校验并保存配置，返回清洗后的值；非法返回 (None, 错误信息)。"""
    try:
        unanimous_n = int(unanimous_n)
        max_voters = int(max_voters)
    except (TypeError, ValueError):
        return None, "裁决人数必须是整数"
    if not MIN_UNANIMOUS_N <= unanimous_n <= MAX_UNANIMOUS_N:
        return None, f"一致裁决人数需在 {MIN_UNANIMOUS_N}~{MAX_UNANIMOUS_N} 之间"
    if not MIN_MAX_VOTERS <= max_voters <= MAX_MAX_VOTERS:
        return None, f"最终裁决人数需在 {MIN_MAX_VOTERS}~{MAX_MAX_VOTERS} 之间"
    if max_voters < unanimous_n:
        return None, "最终裁决人数不能小于一致裁决人数"
    db.set_setting(TAG_REVIEW_PUBLIC_VOTING_KEY, "1" if bool(public_voting) else "0")
    db.set_setting(TAG_REVIEW_UNANIMOUS_N_KEY, str(unanimous_n))
    db.set_setting(TAG_REVIEW_MAX_VOTERS_KEY, str(max_voters))
    clean = {
        "public_voting": bool(public_voting),
        "unanimous_n": unanimous_n,
        "max_voters": max_voters,
    }
    return clean, None


def resolve_vote_decision(approve: int, reject: int, config: dict) -> str | None:
    """按当前票型判定是否触发裁决，返回 "approved"/"rejected" 或 None（继续收集）。

    一致裁决优先：票数达到 unanimous_n 且全部同向立即定局；否则票数达到
    max_voters 按多数定局（平票/少数派判拒绝）。
    """
    approve = max(0, int(approve))
    reject = max(0, int(reject))
    total = approve + reject
    if total <= 0:
        return None
    unanimous_n = max(1, int(config.get("unanimous_n") or DEFAULT_UNANIMOUS_N))
    max_voters = max(1, int(config.get("max_voters") or DEFAULT_MAX_VOTERS))
    if total >= unanimous_n and (approve == 0 or reject == 0):
        return VOTE_APPROVE if approve else VOTE_REJECT
    if total >= max_voters:
        return VOTE_APPROVE if approve > reject else VOTE_REJECT
    return None
