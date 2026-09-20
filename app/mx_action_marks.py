"""大V消息操作标注：授权用户人工标注「某消息是某个股的某操作」，修正自动解析。

标注对象是 (消息, 个股) 对：action 为操作词表内的词（建仓/加仓/低吸/减仓/
高抛/清仓）表示「该消息真实含义是这笔操作」，'none' 表示「该消息对该股
不是操作」（压制误判，如误提出建仓）。一条消息可含多笔操作（如「清仓
赛力斯和比亚迪」），同帖不同标的的标注各自独立、可同时生效。

生效规则（与待审标签大众评审同思路，但不落库裁决——预估持仓回放每次请求
全量重算，生效与否随标注与配置现算，改配置/改标注即刻反映，无需回溯补裁）：
- 管理员标注立即生效；同帖同一标的多位现任管理员标注不一致时，最近更新者优先；
- 授权用户（后台白名单）按「一致人数」生效：同一消息同一标的上标注出相同
  操作的人数达到 agree_n（默认 2）即生效；同时有两个及以上不同标注组达标
  （分歧）则该标的暂不生效，等管理员定夺；不同标的互不影响；
- 仅统计当前仍有标注权的人（现任管理员或白名单内），被移出白名单的
  旧标注不再计数，但其标注行保留（重新授权即恢复计数）。
"""
from __future__ import annotations

import json

# settings 键与默认值
MX_ACTION_MARK_USERS_KEY = "mx_action_mark_users"      # 授权标注用户名 JSON 数组
MX_ACTION_MARK_AGREE_N_KEY = "mx_action_mark_agree_n"  # 一致生效人数

DEFAULT_AGREE_N = 2
# 下限 2：低于 2 则单人标注即生效，违背「少数服从多数」的本意
MIN_AGREE_N, MAX_AGREE_N = 2, 10

# 「非操作」标注值：只压制自动信号，不注入人工事件
MARK_NONE = "none"


def get_mark_config(db) -> dict:
    """读标注配置：授权用户名列表（去重保序）+ 一致生效人数（缺省/越界回落默认）。"""
    try:
        raw = json.loads(str(db.get_setting(MX_ACTION_MARK_USERS_KEY) or "").strip() or "[]")
        names = [str(u).strip() for u in raw if str(u).strip()] if isinstance(raw, list) else []
    except ValueError:
        names = []
    usernames: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name.lower() not in seen:
            seen.add(name.lower())
            usernames.append(name)
    try:
        agree_n = int(str(db.get_setting(MX_ACTION_MARK_AGREE_N_KEY) or "").strip()
                      or DEFAULT_AGREE_N)
    except ValueError:
        agree_n = DEFAULT_AGREE_N
    agree_n = min(MAX_AGREE_N, max(MIN_AGREE_N, agree_n))
    return {"usernames": usernames, "agree_n": agree_n}


def save_mark_config(db, usernames, agree_n) -> tuple[dict | None, str | None]:
    """校验并保存配置；非法返回 (None, 错误信息)，合法返回 (清洗后配置, None)。"""
    clean: list[str] = []
    seen: set[str] = set()
    for name in [str(u or "").strip() for u in (usernames or [])]:
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        clean.append(name)
    missing = [u for u in clean if not db.get_user_by_username_ci(u)]
    if missing:
        return None, "用户不存在：" + "、".join(missing)
    try:
        agree_n = int(agree_n)
    except (TypeError, ValueError):
        return None, "一致生效人数必须是整数"
    if not MIN_AGREE_N <= agree_n <= MAX_AGREE_N:
        return None, f"一致生效人数需在 {MIN_AGREE_N}~{MAX_AGREE_N} 之间"
    db.set_setting(MX_ACTION_MARK_USERS_KEY, json.dumps(clean, ensure_ascii=False))
    db.set_setting(MX_ACTION_MARK_AGREE_N_KEY, str(agree_n))
    return {"usernames": clean, "agree_n": agree_n}, None


def can_mark(user: dict, config: dict) -> bool:
    """当前用户能否标注：管理员恒可；其余看是否在授权白名单（用户名不区分大小写）。"""
    if bool(user.get("is_admin")):
        return True
    name = str(user.get("username") or "").strip().lower()
    if not name:
        return False
    return name in {str(u).strip().lower() for u in config.get("usernames") or []}


def resolve_effective_marks(marks, config: dict) -> dict[int, list[dict]]:
    """纯函数：一批标注行 → 逐帖生效标注 {post_id: [{target_name, action, by_admin, voters}]}。

    marks 行需带 post_id/username/is_admin/target_name/action/updated_at。
    生效按标的独立判定（一帖多标各自成组）：同标的内管理员独裁优先（最新的
    现任管理员标注生效）；否则按操作分组，恰好一个组达到 agree_n 人生效，
    0 个或多个（分歧）该标的不生效；不同标的互不影响。
    """
    agree_n = max(MIN_AGREE_N, int(config.get("agree_n") or DEFAULT_AGREE_N))
    allowed = {str(u).strip().lower() for u in config.get("usernames") or []}
    by_post: dict[int, list] = {}
    for m in marks or []:
        by_post.setdefault(int(m["post_id"]), []).append(m)

    effective: dict[int, list[dict]] = {}
    for post_id, rows in by_post.items():
        eff_targets: list[dict] = []
        # 同帖按标的分组后逐标的走「管理员独裁 / 一致人数」的老规则
        by_target: dict[str, list] = {}
        for m in rows:
            by_target.setdefault(str(m["target_name"]), []).append(m)
        for target, trows in by_target.items():
            # 只有当前仍有标注权的人的标注计数：被移出白名单/降权后旧标注悬置
            valid = [m for m in trows
                     if bool(m.get("is_admin"))
                     or str(m.get("username") or "").strip().lower() in allowed]
            if not valid:
                continue
            admin_marks = [m for m in valid if bool(m.get("is_admin"))]
            if admin_marks:
                best = max(admin_marks,
                           key=lambda m: (str(m.get("updated_at") or ""), int(m.get("id") or 0)))
                eff_targets.append({
                    "target_name": target,
                    "action": str(best["action"]),
                    "by_admin": True,
                    "voters": [str(best.get("username") or "")],
                })
                continue
            groups: dict[str, list] = {}
            for m in valid:
                groups.setdefault(str(m["action"]), []).append(m)
            reached = [(action, voters) for action, voters in groups.items() if len(voters) >= agree_n]
            if len(reached) == 1:
                action, voters = reached[0]
                eff_targets.append({
                    "target_name": target,
                    "action": action,
                    "by_admin": False,
                    "voters": sorted(str(m.get("username") or "") for m in voters),
                })
        if eff_targets:
            effective[post_id] = eff_targets
    return effective


def effective_marks_for_kol(db, kol_id, since_day: str, config: dict | None = None) -> dict[int, list[dict]]:
    """单大V窗口内帖子的生效标注（预估持仓回放的第三信号源）。

    值为该帖的生效标注列表（一帖多标多生效），空列表帖不出现。
    """
    cfg = config or get_mark_config(db)
    marks = db.list_mx_action_marks_for_kol(kol_id, since_day)
    return resolve_effective_marks(marks, cfg)


def marks_summary_for_posts(db, post_ids, viewer: dict | None,
                            config: dict | None = None) -> dict[int, dict]:
    """逐帖标注汇总（弹窗与卡片角标数据源）。

    返回 {post_id: {marks: [...], effective: [...], my_marks: [...]}}；
    marks 按时间升序含标注人身份；effective 为该帖按标的各自生效的标注列表
    （空列表 = 全部未生效或分歧）；my_marks 为当前查看者在此帖的标注列表。
    """
    cfg = config or get_mark_config(db)
    ids = [int(p) for p in (post_ids or []) if p is not None]
    if not ids:
        return {}
    rows = db.list_mx_action_marks_for_posts(ids)
    by_post: dict[int, list] = {}
    for m in rows:
        by_post.setdefault(int(m["post_id"]), []).append(m)
    effective = resolve_effective_marks(rows, cfg)
    viewer_id = int(viewer["id"]) if viewer and viewer.get("id") else None
    out: dict[int, dict] = {}
    for post_id in ids:
        marks = by_post.get(post_id, [])
        mine = [m for m in marks if int(m["user_id"]) == viewer_id]
        out[post_id] = {
            "marks": [
                {
                    "user_id": int(m["user_id"]),
                    "is_mine": int(m["user_id"]) == viewer_id,
                    "username": str(m.get("username") or ""),
                    "is_admin": bool(m.get("is_admin")),
                    "target_name": str(m["target_name"]),
                    "action": str(m["action"]),
                    "updated_at": str(m.get("updated_at") or ""),
                }
                for m in marks
            ],
            "effective": effective.get(post_id, []),
            "my_marks": [
                {"target_name": str(m["target_name"]), "action": str(m["action"])}
                for m in mine
            ],
        }
    return out


def attach_mx_action_marks(db, posts, viewer: dict | None, config: dict | None = None) -> list:
    """给一批帖子行附加 mx_mark（仅 mx 帖且确有标注时挂键，其余不渲染）。

    卡片角标数据源：有生效标注逐条出「人工:操作」实心角标；有标注未生效出
    「标注中 n/N」虚线角标；agree_n 供角标展示生效门槛。
    """
    cfg = config or get_mark_config(db)
    rows = [r for r in (posts or [])
            if r.get("id") is not None and str(r.get("platform") or "") == "mx"]
    if not rows:
        return posts
    summaries = marks_summary_for_posts(db, [int(r["id"]) for r in rows], viewer, cfg)
    for row in rows:
        s = summaries.get(int(row["id"]))
        if s and (s["effective"] or s["marks"]):
            row["mx_mark"] = {
                "effective": s["effective"],
                "mine": bool(s["my_marks"]),
                "total": len(s["marks"]),
                "agree_n": int(cfg.get("agree_n") or DEFAULT_AGREE_N),
            }
    return posts
