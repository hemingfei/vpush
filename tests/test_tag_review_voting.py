"""待审标签大众评审：配置校验、票型裁决规则、一人一票、条件裁决与用户端 API。

规则口径：一致裁决（unanimous_n 人全部同向）立即定局；票型分裂继续收集，
达到 max_voters 人按多数定局，平票判拒绝（标签上帖是持久写入，保守不通过）。
管理员在弹窗投票直判立即生效（与后台审核队列同口径），不经过大众票型。
"""
import pytest

from app.tag_review_voting import (
    DEFAULT_MAX_VOTERS,
    DEFAULT_UNANIMOUS_N,
    VOTE_APPROVE,
    VOTE_REJECT,
    get_review_config,
    resolve_vote_decision,
    save_review_config,
)
from test_api import auth_headers, make_client, user_headers


_seed_seq = [0]


def _seed_post_and_review(client, tag="华正新材", kind="stock"):
    state = client.app.state
    _seed_seq[0] += 1
    n = _seed_seq[0]
    kid = state.db.add_kol("mx", f"评审测试{n}", f"voting-{n}")
    pid = state.db.insert_post(
        "mx", kid, f"ext-vote-{n}", "标题", "弥补一下华正",
        "https://example.com/p/1", "2026-09-15 10:00:00",
    )
    assert state.db.add_pending_tag_review(pid, tag, kind, "low", source="mx_view", direction="bull")
    rows = state.db.attach_pending_tags([state.db.get_post(pid)])
    rid = rows[0]["pending_tags"][0]["id"]
    return pid, rid


# ---- 裁决规则纯函数 ----

def test_resolve_no_votes_and_below_unanimous():
    cfg = {"unanimous_n": 2, "max_voters": 10}
    assert resolve_vote_decision(0, 0, cfg) is None
    # 单票未达一致人数：继续收集
    assert resolve_vote_decision(1, 0, cfg) is None
    assert resolve_vote_decision(0, 1, cfg) is None


def test_resolve_unanimous_decides_immediately():
    cfg = {"unanimous_n": 2, "max_voters": 10}
    assert resolve_vote_decision(2, 0, cfg) == VOTE_APPROVE
    assert resolve_vote_decision(0, 2, cfg) == VOTE_REJECT
    assert resolve_vote_decision(3, 0, cfg) == VOTE_APPROVE


def test_resolve_split_keeps_collecting():
    cfg = {"unanimous_n": 2, "max_voters": 10}
    assert resolve_vote_decision(1, 1, cfg) is None
    assert resolve_vote_decision(2, 1, cfg) is None
    assert resolve_vote_decision(3, 5, cfg) is None


def test_resolve_max_voters_majority_and_tie():
    cfg = {"unanimous_n": 2, "max_voters": 10}
    assert resolve_vote_decision(6, 4, cfg) == VOTE_APPROVE
    assert resolve_vote_decision(4, 6, cfg) == VOTE_REJECT
    # 平票保守判拒绝：上帖是持久写入，不因平票通过
    assert resolve_vote_decision(5, 5, cfg) == VOTE_REJECT
    # 达到上限且全一致 → 同向定局
    assert resolve_vote_decision(10, 0, cfg) == VOTE_APPROVE


def test_resolve_ignores_bad_config_values():
    # 缺失/非法配置按默认与下限兜底，不抛异常
    assert resolve_vote_decision(2, 0, {}) == VOTE_APPROVE
    assert resolve_vote_decision(1, 0, {}) is None  # 默认 unanimous_n=2
    assert resolve_vote_decision(0, 1, {"unanimous_n": 0, "max_voters": 0}) is None


# ---- 配置读写与校验 ----

def test_config_defaults_and_roundtrip(tmp_path):
    from app.db import DB

    db = DB(str(tmp_path / "cfg.db"))
    cfg = get_review_config(db)
    assert cfg == {
        "public_voting": True,
        "unanimous_n": DEFAULT_UNANIMOUS_N,
        "max_voters": DEFAULT_MAX_VOTERS,
    }
    clean, err = save_review_config(db, False, 3, 7)
    assert err is None and clean == {"public_voting": False, "unanimous_n": 3, "max_voters": 7}
    assert get_review_config(db) == clean
    db.close()


def test_config_validation_rejects_bad_ranges(tmp_path):
    from app.db import DB

    db = DB(str(tmp_path / "cfg2.db"))
    assert save_review_config(db, True, 5, 3)[1]  # 最终人数 < 一致人数
    assert save_review_config(db, True, 0, 10)[1]
    assert save_review_config(db, True, 2, 999)[1]
    assert save_review_config(db, True, "abc", 10)[1]
    # 非法保存不落库
    assert get_review_config(db)["public_voting"] is True
    db.close()


# ---- db 层：一人一票 + 条件裁决 ----

def test_vote_one_per_user_immutable(tmp_path):
    from app.db import DB

    db = DB(str(tmp_path / "vote.db"))
    kid = db.add_kol("mx", "K", "k-1")
    pid = db.insert_post("mx", kid, "e-1", "t", "c", "u", "2026-09-15 10:00:00")
    db.add_pending_tag_review(pid, "个股", "topic", "low")
    rid = db.list_tag_reviews("pending")[0]["id"]
    assert db.add_tag_review_vote(rid, 101, VOTE_APPROVE) is True
    # 重复提交：忽略不改投
    assert db.add_tag_review_vote(rid, 101, VOTE_APPROVE) is False
    assert db.add_tag_review_vote(rid, 101, VOTE_REJECT) is False
    assert db.tag_review_vote_summary(rid) == {"approve": 1, "reject": 0, "total": 1}
    assert db.tag_review_vote_summary(rid, user_id=101)["my_vote"] == VOTE_APPROVE
    assert db.tag_review_vote_summary(rid, user_id=202)["my_vote"] is None
    db.close()


def test_decide_only_from_pending(tmp_path):
    from app.db import DB

    db = DB(str(tmp_path / "decide.db"))
    kid = db.add_kol("mx", "K", "k-2")
    pid = db.insert_post("mx", kid, "e-2", "t", "c", "u", "2026-09-15 10:00:00")
    db.add_pending_tag_review(pid, "个股", "topic", "low")
    rid = db.list_tag_reviews("pending")[0]["id"]
    review = db.decide_tag_review(rid, "rejected")
    assert review is not None and review["tag"] == "个股"
    assert db.get_tag_review(rid)["status"] == "rejected"
    # 已裁决后再裁：返回 None（防并发翻转）
    assert db.decide_tag_review(rid, "approved") is None
    assert db.get_tag_review(rid)["status"] == "rejected"
    assert db.decide_tag_review(99999, "approved") is None
    db.close()


# ---- 用户端 API ----

def test_tag_review_detail_requires_auth_and_exists():
    client = make_client()
    pid, rid = _seed_post_and_review(client)
    assert client.get(f"/api/tag-reviews/{rid}").status_code == 401
    user = user_headers(client, "reader1")
    resp = client.get(f"/api/tag-reviews/{rid}", headers=user)
    assert resp.status_code == 200
    body = resp.json()
    assert body["tag"] == "华正新材" and body["status"] == "pending"
    assert body["votes"] == {"approve": 0, "reject": 0, "total": 0}
    assert body["my_vote"] is None and body["can_vote"] is True
    assert body["post"]["kol_name"] and "弥补一下华正" in body["post"]["excerpt"]
    assert client.get("/api/tag-reviews/99999", headers=user).status_code == 404


def test_user_votes_unanimous_approve_appends_tag():
    client = make_client()
    pid, rid = _seed_post_and_review(client)
    first = user_headers(client, "voter1")
    second = user_headers(client, "voter2")
    # 第一票：未达一致人数，仍 pending
    r1 = client.post(f"/api/tag-reviews/{rid}/vote", headers=first, json={"action": "approve"})
    assert r1.status_code == 200
    body = r1.json()
    assert body["status"] == "pending" and body["votes"]["total"] == 1
    assert body["my_vote"] == "approve"
    # 第二票同向：一致裁决为通过，标签上帖
    r2 = client.post(f"/api/tag-reviews/{rid}/vote", headers=second, json={"action": "approve"})
    body = r2.json()
    assert body["status"] == "approved" and body["can_vote"] is False
    db = client.app.state.db
    assert "华正新材" in db.get_post_tags(pid)
    # 裁决后继续投 → 409；pending_tags 不再下发
    assert client.post(
        f"/api/tag-reviews/{rid}/vote", headers=first, json={"action": "approve"}
    ).status_code == 409
    assert db.attach_pending_tags([db.get_post(pid)])[0]["pending_tags"] == []


def test_user_votes_split_then_majority_reject():
    client = make_client()
    pid, rid = _seed_post_and_review(client, tag="某某题材", kind="topic")
    admin = auth_headers(client)
    # 一致人数抬到 3：1:1 分裂不触发一致裁决；上限 4：投满 4 人强制终裁
    # （uni > max 是矛盾配置，保存接口会 400，见 test_admin_config_api_auth_and_validation）
    assert client.put(
        "/api/admin/tag-review/config", headers=admin,
        json={"public_voting": True, "unanimous_n": 3, "max_voters": 4},
    ).status_code == 200
    u1 = user_headers(client, "voter1")
    u2 = user_headers(client, "voter2")
    u3 = user_headers(client, "voter3")
    u4 = user_headers(client, "voter4")
    client.post(f"/api/tag-reviews/{rid}/vote", headers=u1, json={"action": "approve"})
    split = client.post(f"/api/tag-reviews/{rid}/vote", headers=u2, json={"action": "reject"})
    # 1:1 票型分裂 → 继续收集
    assert split.json()["status"] == "pending"
    # 重复投票不改投
    again = client.post(f"/api/tag-reviews/{rid}/vote", headers=u1, json={"action": "reject"})
    assert again.json()["my_vote"] == "approve"
    assert again.json()["votes"] == {"approve": 1, "reject": 1, "total": 2}
    third = client.post(f"/api/tag-reviews/{rid}/vote", headers=u3, json={"action": "approve"})
    # 2:1，总票数 3 未达上限 → 仍 pending
    assert third.json()["status"] == "pending"
    final = client.post(f"/api/tag-reviews/{rid}/vote", headers=u4, json={"action": "reject"})
    # 投满 4 人触发终裁：2:2 平票 → 保守拒绝
    assert final.json()["status"] == "rejected"
    assert "某某题材" not in client.app.state.db.get_post_tags(pid)

    # 多数裁决通过：上限收到 3，票型 2:1 → 通过并上帖
    assert client.put(
        "/api/admin/tag-review/config", headers=admin,
        json={"public_voting": True, "unanimous_n": 3, "max_voters": 3},
    ).status_code == 200
    pid2, rid2 = _seed_post_and_review(client, tag="另一题材", kind="topic")
    v1 = user_headers(client, "voter5")
    v2 = user_headers(client, "voter6")
    v3 = user_headers(client, "voter7")
    client.post(f"/api/tag-reviews/{rid2}/vote", headers=v1, json={"action": "approve"})
    client.post(f"/api/tag-reviews/{rid2}/vote", headers=v2, json={"action": "reject"})
    last = client.post(f"/api/tag-reviews/{rid2}/vote", headers=v3, json={"action": "approve"})
    assert last.json()["status"] == "approved"
    assert "另一题材" in client.app.state.db.get_post_tags(pid2)


def test_admin_vote_decides_directly():
    client = make_client()
    pid, rid = _seed_post_and_review(client)
    admin = auth_headers(client)
    resp = client.post(f"/api/tag-reviews/{rid}/vote", headers=admin, json={"action": "approve"})
    body = resp.json()
    assert body["status"] == "approved"
    assert "华正新材" in client.app.state.db.get_post_tags(pid)
    # 管理员直判不落投票表
    assert client.app.state.db.tag_review_vote_summary(rid)["total"] == 0

    # 拒绝直判
    pid2, rid2 = _seed_post_and_review(client, tag="另一标签", kind="topic")
    resp = client.post(f"/api/tag-reviews/{rid2}/vote", headers=admin, json={"action": "reject"})
    assert resp.json()["status"] == "rejected"
    assert "另一标签" not in client.app.state.db.get_post_tags(pid2)


def test_public_voting_disabled_blocks_users_only():
    client = make_client()
    pid, rid = _seed_post_and_review(client)
    admin = auth_headers(client)
    user = user_headers(client, "voter1")
    assert client.put(
        "/api/admin/tag-review/config", headers=admin,
        json={"public_voting": False, "unanimous_n": 2, "max_voters": 10},
    ).status_code == 200
    detail = client.get(f"/api/tag-reviews/{rid}", headers=user).json()
    assert detail["can_vote"] is False
    resp = client.post(f"/api/tag-reviews/{rid}/vote", headers=user, json={"action": "approve"})
    assert resp.status_code == 403
    # 管理员不受开关影响
    resp = client.post(f"/api/tag-reviews/{rid}/vote", headers=admin, json={"action": "reject"})
    assert resp.status_code == 200 and resp.json()["status"] == "rejected"


def test_vote_action_validation():
    client = make_client()
    pid, rid = _seed_post_and_review(client)
    user = user_headers(client, "voter1")
    assert client.post(
        f"/api/tag-reviews/{rid}/vote", headers=user, json={"action": "maybe"}
    ).status_code == 422
    assert client.post(
        f"/api/tag-reviews/{rid}/vote", headers=user, json={"action": "approve"}
    ).status_code == 200


# ---- 管理端配置 API ----

def test_admin_config_api_auth_and_validation():
    client = make_client()
    user = user_headers(client, "plainuser")
    assert client.get("/api/admin/tag-review/config", headers=user).status_code == 403
    admin = auth_headers(client)
    resp = client.get("/api/admin/tag-review/config", headers=admin)
    assert resp.status_code == 200
    assert resp.json() == {
        "public_voting": True, "unanimous_n": 2, "max_voters": 10,
    }
    ok = client.put(
        "/api/admin/tag-review/config", headers=admin,
        json={"public_voting": True, "unanimous_n": 3, "max_voters": 5},
    )
    assert ok.status_code == 200 and ok.json()["config"]["unanimous_n"] == 3
    assert client.get("/api/admin/tag-review/config", headers=admin).json()["max_voters"] == 5
    bad = client.put(
        "/api/admin/tag-review/config", headers=admin,
        json={"public_voting": True, "unanimous_n": 9, "max_voters": 5},
    )
    assert bad.status_code == 400


def test_admin_tag_detail_includes_vote_counts():
    client = make_client()
    pid, rid = _seed_post_and_review(client)
    u1 = user_headers(client, "voter1")
    u2 = user_headers(client, "voter2")
    client.post(f"/api/tag-reviews/{rid}/vote", headers=u1, json={"action": "approve"})
    client.post(f"/api/tag-reviews/{rid}/vote", headers=u2, json={"action": "reject"})
    admin = auth_headers(client)
    detail = client.get(f"/api/admin/posts/{pid}/tag-detail", headers=admin).json()
    pending = [r for r in detail["pending_reviews"] if r["id"] == rid]
    assert pending and pending[0]["votes"] == {"approve": 1, "reject": 1}


def test_config_tightening_retro_decides_overflowed_pending():
    """阈值收紧时回溯补裁决：分裂且已投满的 pending 不会再有新票触发判定，
    保存配置时必须按新阈值补一次，否则永久挂起只能管理员直判。"""
    client = make_client()
    pid, rid = _seed_post_and_review(client)
    admin = auth_headers(client)
    # 先放宽到 max_voters=5，投 4 票分裂（2/2）——未达 5 不裁决
    assert client.put(
        "/api/admin/tag-review/config", headers=admin,
        json={"public_voting": True, "unanimous_n": 2, "max_voters": 5},
    ).status_code == 200
    votes = ["approve", "reject", "approve", "reject"]
    first_voter = None
    for i, v in enumerate(votes):
        u = user_headers(client, f"retro_voter{i}")
        if i == 0:
            first_voter = u
        r = client.post(f"/api/tag-reviews/{rid}/vote", headers=u, json={"action": v})
        assert r.status_code == 200 and r.json()["status"] == "pending"

    # 收紧到 max_voters=4：4 票已满、2/2 平票按保守口径判拒绝，就地定局
    r = client.put(
        "/api/admin/tag-review/config", headers=admin,
        json={"public_voting": True, "unanimous_n": 2, "max_voters": 4},
    )
    assert r.status_code == 200, r.text
    assert r.json()["retro_decided"] == 1
    detail = client.get(f"/api/tag-reviews/{rid}", headers=first_voter).json()
    assert detail["status"] == "rejected"

    # 再保存一次（无新增超限 pending）：回溯数 0，不重复裁决
    r = client.put(
        "/api/admin/tag-review/config", headers=admin,
        json={"public_voting": True, "unanimous_n": 2, "max_voters": 4},
    )
    assert r.json()["retro_decided"] == 0


@pytest.mark.parametrize("approve,reject,cfg,expected", [
    (1, 1, {"unanimous_n": 2, "max_voters": 10}, None),
    (0, 2, {"unanimous_n": 2, "max_voters": 10}, VOTE_REJECT),
    (2, 0, {"unanimous_n": 2, "max_voters": 10}, VOTE_APPROVE),
    (6, 3, {"unanimous_n": 2, "max_voters": 10}, None),   # 总票数 9 未达上限继续收
    (7, 3, {"unanimous_n": 2, "max_voters": 10}, VOTE_APPROVE),  # 总票数 10 达上限按多数
    (5, 5, {"unanimous_n": 2, "max_voters": 10}, VOTE_REJECT),
])
def test_resolve_parametrized(approve, reject, cfg, expected):
    assert resolve_vote_decision(approve, reject, cfg) == expected
