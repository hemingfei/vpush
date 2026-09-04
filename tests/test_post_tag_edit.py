"""帖子标签人工编辑回归测试：标签审核批量通过/拒绝 + 消息详情手动加/删标签。

覆盖：批量接口的成败明细（重复/已满回滚 pending）、单条加删标签的
去重与上限口径、404/400 边界、非管理员越权拒绝，以及 db 层增删辅助。
"""
import pytest

from app.db import POST_TAGS_MAX
from test_api import auth_headers, make_client, user_headers


def _seed_post(client, tags=None, platform="mx"):
    state = client.app.state
    kid = state.db.add_kol(platform, "标签测试", "tagedit-1")
    pid = state.db.insert_post(
        platform, kid, "ext-1", "标题", "正文内容",
        "https://example.com/p/1", "2026-09-01 10:00:00", tags=tags,
    )
    return pid


def _seed_review(client, pid, tag, kind="topic"):
    client.app.state.db.add_pending_tag_review(pid, tag, kind, "low")


# ---- 管理端 API：批量通过/拒绝 ----

def test_batch_reject_marks_all_rejected():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    pid = _seed_post(client)
    _seed_review(client, pid, "宏观")
    _seed_review(client, pid, "降息")
    ids = [r["id"] for r in db.list_tag_reviews("pending")]

    resp = client.post(
        "/api/admin/post-tag-reviews/batch", headers=admin,
        json={"ids": ids, "action": "reject"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert sorted(data["ok"]) == sorted(ids) and data["failed"] == []
    assert db.list_tag_reviews("pending") == []
    assert len(db.list_tag_reviews("rejected")) == 2


def test_batch_approve_appends_tags_and_dedupes():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    pid = _seed_post(client, tags=["已有"])
    _seed_review(client, pid, "宏观")
    # 帖上已存在的标签现在不会经 add_pending_tag_review 登记（db 层已拦截），
    # 直插一行模拟历史遗留/并发窗口，验证接口侧仍兜底：追加失败回滚 pending
    db._conn.execute(
        "INSERT INTO post_tag_reviews (post_id, tag, kind, confidence) "
        "VALUES (?, '已有', 'topic', 'low')",
        (pid,),
    )
    db._conn.commit()
    reviews = {r["tag"]: r for r in db.list_tag_reviews("pending")}
    r_new = reviews["宏观"]
    r_dup = db._conn.execute(
        "SELECT id FROM post_tag_reviews WHERE post_id=? AND tag='已有'", (pid,)
    ).fetchone()

    resp = client.post(
        "/api/admin/post-tag-reviews/batch", headers=admin,
        json={"ids": [r_new["id"], r_dup["id"]], "action": "approve"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ok"] == [r_new["id"]]
    assert len(data["failed"]) == 1
    assert data["failed"][0]["id"] == r_dup["id"]
    assert "已在消息标签里" in data["failed"][0]["reason"]
    # 成功的进 approved；失败的回滚 pending，但因标签已在帖上不进队列
    assert [r["id"] for r in db.list_tag_reviews("approved")] == [r_new["id"]]
    assert db.list_tag_reviews("pending") == []
    dup_status = db._conn.execute(
        "SELECT status FROM post_tag_reviews WHERE id=?", (r_dup["id"],)
    ).fetchone()[0]
    assert dup_status == "pending"
    assert db.get_post_tags(pid) == ["已有", "宏观"]


def test_batch_approve_respects_tag_cap():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    pid = _seed_post(client, tags=[f"标签{i}" for i in range(POST_TAGS_MAX)])
    _seed_review(client, pid, "溢出")

    resp = client.post(
        "/api/admin/post-tag-reviews/batch", headers=admin,
        json={"ids": [db.list_tag_reviews("pending")[0]["id"]], "action": "approve"},
    )
    assert resp.status_code == 200
    failed = resp.json()["failed"]
    assert len(failed) == 1 and str(POST_TAGS_MAX) in failed[0]["reason"]
    assert len(db.list_tag_reviews("pending")) == 1


def test_batch_empty_ids_rejected():
    client = make_client()
    admin = auth_headers(client)
    resp = client.post(
        "/api/admin/post-tag-reviews/batch", headers=admin,
        json={"ids": [], "action": "approve"},
    )
    assert resp.status_code == 400


def test_batch_unknown_id_listed_as_failed():
    client = make_client()
    admin = auth_headers(client)
    resp = client.post(
        "/api/admin/post-tag-reviews/batch", headers=admin,
        json={"ids": [99999], "action": "reject"},
    )
    assert resp.status_code == 200
    assert resp.json()["failed"][0]["id"] == 99999


def test_approve_gives_specific_failure_reasons():
    """通过失败的 409 文案要指明确切原因，不再把已满/已存在/已删混在一句话里。"""
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    pid = _seed_post(client, tags=[f"标签{i}" for i in range(POST_TAGS_MAX)])

    # 已满 15 个：提示具体上限
    _seed_review(client, pid, "新标签")
    rid = db.list_tag_reviews("pending")[0]["id"]
    resp = client.post(f"/api/admin/post-tag-reviews/{rid}/approve", headers=admin)
    assert resp.status_code == 409, resp.text
    assert f"已达上限 {POST_TAGS_MAX}" in resp.json()["detail"]
    # 回滚 pending；标签未上帖，仍会列出
    assert [r["id"] for r in db.list_tag_reviews("pending")] == [rid]

    # 待审标签已在帖上（历史遗留/并发窗口）：直插模拟，提示「已在消息标签里」
    db._conn.execute(
        "INSERT INTO post_tag_reviews (post_id, tag, kind, confidence) "
        "VALUES (?, '标签3', 'topic', 'low')",
        (pid,),
    )
    db._conn.commit()
    rid_dup = db._conn.execute(
        "SELECT id FROM post_tag_reviews WHERE post_id=? AND tag='标签3'", (pid,)
    ).fetchone()[0]
    resp = client.post(f"/api/admin/post-tag-reviews/{rid_dup}/approve", headers=admin)
    assert resp.status_code == 409, resp.text
    assert "已在消息标签里" in resp.json()["detail"]
    # 回滚后因标签已在帖上，队列不再列出这条
    assert [r["id"] for r in db.list_tag_reviews("pending")] == [rid]


# ---- 管理端 API：单条消息手动加/删标签 ----

def test_add_and_remove_post_tag_roundtrip():
    client = make_client()
    admin = auth_headers(client)
    pid = _seed_post(client, tags=["宏观"])

    resp = client.post(
        f"/api/admin/posts/{pid}/tags/add", headers=admin, json={"tag": "降息"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tags"] == ["宏观", "降息"]

    resp = client.post(
        f"/api/admin/posts/{pid}/tags/remove", headers=admin, json={"tag": "宏观"},
    )
    assert resp.status_code == 200
    assert resp.json()["tags"] == ["降息"]


def test_add_tag_duplicate_and_missing_post():
    client = make_client()
    admin = auth_headers(client)
    pid = _seed_post(client, tags=["宏观"])
    assert client.post(
        f"/api/admin/posts/{pid}/tags/add", headers=admin, json={"tag": "宏观"},
    ).status_code == 409
    assert client.post(
        "/api/admin/posts/999999/tags/add", headers=admin, json={"tag": "宏观"},
    ).status_code == 404
    assert client.post(
        f"/api/admin/posts/{pid}/tags/add", headers=admin, json={"tag": "  "},
    ).status_code == 400


def test_remove_missing_tag_returns_404():
    client = make_client()
    admin = auth_headers(client)
    pid = _seed_post(client)
    resp = client.post(
        f"/api/admin/posts/{pid}/tags/remove", headers=admin, json={"tag": "不存在"},
    )
    assert resp.status_code == 404


def test_tag_edit_requires_admin():
    client = make_client()
    admin = auth_headers(client)
    user = user_headers(client, "plainuser1")
    pid = _seed_post(client)
    for path in (f"/api/admin/posts/{pid}/tags/add", f"/api/admin/posts/{pid}/tags/remove"):
        assert client.post(path, headers=user, json={"tag": "x"}).status_code in (401, 403)
        assert client.post(path, json={"tag": "x"}).status_code in (401, 403)
    resp = client.post(
        "/api/admin/post-tag-reviews/batch", headers=user,
        json={"ids": [1], "action": "reject"},
    )
    assert resp.status_code in (401, 403)
    # 管理员同路径正常
    assert client.post(
        f"/api/admin/posts/{pid}/tags/remove", headers=admin, json={"tag": "x"},
    ).status_code == 404  # 无此标签，但已通过鉴权


# ---- db 层辅助 ----

def test_db_append_remove_post_tag_basics():
    client = make_client()
    db = client.app.state.db
    pid = _seed_post(client)
    assert db.has_post(pid) and not db.has_post(999999)
    assert db.get_post_tags(999999) == []
    assert db.append_post_tag(pid, "宏观")
    assert not db.append_post_tag(pid, "宏观")  # 去重
    assert db.append_post_tag(pid, " 降息 ") == True  # 收尾空白
    assert db.get_post_tags(pid) == ["宏观", "降息"]
    assert db.remove_post_tag(pid, "宏观")
    assert not db.remove_post_tag(pid, "宏观")  # 不存在
    assert not db.remove_post_tag(999999, "宏观")  # 帖子不存在
    assert db.get_post_tags(pid) == ["降息"]


def test_pending_queue_hides_tag_already_on_post():
    """登记后标签又被手动加上：通过与否它都已在帖，队列与详情都不再列它。"""
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    pid = _seed_post(client)
    _seed_review(client, pid, "宏观")
    assert [r["tag"] for r in db.list_tag_reviews("pending")] == ["宏观"]

    assert client.post(
        f"/api/admin/posts/{pid}/tags/add", headers=admin, json={"tag": "宏观"},
    ).status_code == 200
    assert db.list_tag_reviews("pending") == []
    detail = client.get(f"/api/admin/posts/{pid}/tag-detail", headers=admin).json()
    assert detail["pending_reviews"] == []
    assert detail["tags"] == ["宏观"]


# ---- 「查看」弹窗：LLM 直写标签留痕 + 详情接口 ----

def test_record_llm_applied_tag_upgrades_pending():
    client = make_client()
    db = client.app.state.db
    pid = _seed_post(client)
    _seed_review(client, pid, "AI算力", kind="topic")  # 上次跑批判 low 进审核
    db.merge_post_tags_llm(pid, ["AI算力"])  # 这次判 high 直写
    db.record_llm_applied_tag(pid, "AI算力", "topic")
    rows = db._conn.execute(
        "SELECT tag, kind, confidence, status FROM post_tag_reviews WHERE post_id=?", (pid,)
    ).fetchall()
    # pending 行被升级为 applied（LLM 已实际写入，无需再审），且不另起新行
    assert [(r["tag"], r["kind"], r["confidence"], r["status"]) for r in rows] == [
        ("AI算力", "topic", "high", "applied")
    ]
    # 人工已拒绝的结论不被重跑覆盖
    _seed_review(client, pid, "宏观", kind="topic")
    rid = db.list_tag_reviews("pending")[0]["id"]
    db.set_tag_review_status(rid, "rejected")
    db.record_llm_applied_tag(pid, "宏观", "topic")
    status = db._conn.execute(
        "SELECT status FROM post_tag_reviews WHERE post_id=? AND tag='宏观'", (pid,)
    ).fetchone()["status"]
    assert status == "rejected"


def test_tag_detail_endpoint_sections():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    pid = _seed_post(client, tags=["大盘"])  # 规则标签
    # LLM high 直写
    db.merge_post_tags_llm(pid, ["AI算力"])
    db.record_llm_applied_tag(pid, "AI算力", "topic")
    # low 待审
    _seed_review(client, pid, "宁王", kind="stock")

    resp = client.get(f"/api/admin/posts/{pid}/tag-detail", headers=admin)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["kol_name"] == "标签测试"
    assert data["tags"] == ["大盘", "AI算力"]
    assert data["llm_tags"] == [{"tag": "AI算力", "kind": "topic", "status": "applied"}]
    assert [r["tag"] for r in data["pending_reviews"]] == ["宁王"]
    assert data["pending_reviews"][0]["kind"] == "stock"

    # 审核通过后：标签进帖，LLM 打标记录里状态变 approved
    rid = data["pending_reviews"][0]["id"]
    assert client.post(f"/api/admin/post-tag-reviews/{rid}/approve", headers=admin).status_code == 200
    data = client.get(f"/api/admin/posts/{pid}/tag-detail", headers=admin).json()
    assert data["pending_reviews"] == []
    assert {x["tag"]: x["status"] for x in data["llm_tags"]} == {
        "AI算力": "applied", "宁王": "approved",
    }
    assert "宁王" in data["tags"]

    # 手动删除 LLM 直写标签后，llm_tags 同步消失（只列仍在帖上的）
    assert client.post(
        f"/api/admin/posts/{pid}/tags/remove", headers=admin, json={"tag": "AI算力"},
    ).status_code == 200
    data = client.get(f"/api/admin/posts/{pid}/tag-detail", headers=admin).json()
    assert [x["tag"] for x in data["llm_tags"]] == ["宁王"]
    assert data["tags"] == ["大盘", "宁王"]


def test_tag_detail_requires_admin_and_404():
    client = make_client()
    admin = auth_headers(client)
    user = user_headers(client, "plainuser2")
    pid = _seed_post(client)
    assert client.get(f"/api/admin/posts/{pid}/tag-detail", headers=user).status_code in (401, 403)
    assert client.get("/api/admin/posts/999999/tag-detail", headers=admin).status_code == 404
