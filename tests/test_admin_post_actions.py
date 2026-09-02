"""管理端帖子操作回归测试：隐藏（库内保留、用户不可见、可恢复）与彻底删除。

覆盖：hide/unhide/delete 三个管理端动作、用户侧时间线/单帖详情/KOL 帖子列表的
可见性、hidden 帖在管理端列表的状态筛选、推送失败重试不再外推、审计留痕与越权拒绝。
"""
from types import SimpleNamespace

from app.fetchers.base import Post
from app.scheduler import Scheduler
from test_api import auth_headers, make_client, user_headers


def _seed_posts(client, n=2):
    state = client.app.state
    kid = state.db.add_kol("xueqiu", "帖管测试", "admpost-1")
    ids = []
    for i in range(1, n + 1):
        pid = state.db.insert_post(
            "xueqiu", kid, f"ext-{i}", f"标题{i}", f"内容{i}",
            f"https://xueqiu.com/u/admpost/{i}", f"2026-08-2{i} 10:00:00",
        )
        ids.append(pid)
    return kid, ids


def test_hide_keeps_row_but_hides_from_user_feed_and_detail():
    client = make_client()
    admin = auth_headers(client)
    user = user_headers(client, "plainuser1")
    db = client.app.state.db
    uid = client.get("/api/me", headers=user).json()["id"]
    kid, ids = _seed_posts(client)
    db.add_subscription(uid, kid)
    pid = ids[0]

    # 隐藏前：用户时间线与单帖详情可见
    feed_before = client.get("/api/my/feed", headers=user).json()
    assert {p["id"] for p in feed_before} == set(ids)
    assert client.get(f"/api/posts/{pid}", headers=user).status_code == 200

    resp = client.post(f"/api/posts/{pid}/hide", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "hidden": True}

    # 内容仍在库（可恢复），但用户侧时间线/单帖详情不再可见
    assert db.get_post(pid) is not None
    feed_after = client.get("/api/my/feed", headers=user).json()
    assert [p["id"] for p in feed_after] == [ids[1]]
    assert client.get(f"/api/posts/{pid}", headers=user).status_code == 404
    # 另一帖不受影响；KOL 帖子列表（用户侧）同样排除隐藏帖
    assert client.get(f"/api/posts/{ids[1]}", headers=user).status_code == 200
    kol_posts = client.get(f"/api/kols/{kid}/posts", headers=user).json()
    assert pid not in [p["id"] for p in kol_posts]


def test_unhide_restores_visibility():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    _, ids = _seed_posts(client)
    pid = ids[0]
    assert client.post(f"/api/posts/{pid}/hide", headers=admin).status_code == 200
    # db 层默认排除隐藏帖，只返回未隐藏的另一帖
    assert [p["id"] for p in db.list_posts(limit=50)] == [ids[1]]

    resp = client.post(f"/api/posts/{pid}/unhide", headers=admin)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "hidden": False}
    assert {p["id"] for p in db.list_posts(limit=50)} == set(ids)


def test_admin_list_status_filters_include_hidden_and_hidden_only():
    client = make_client()
    admin = auth_headers(client)
    _, ids = _seed_posts(client)
    client.post(f"/api/posts/{ids[0]}/hide", headers=admin)

    # 默认（include_hidden=1）：全部返回，隐藏帖带 hidden 标记
    rows = client.get("/api/posts?include_hidden=1", headers=admin).json()
    assert {p["id"]: p["hidden"] for p in rows} == {ids[0]: 1, ids[1]: 0}
    # 只看已隐藏 / 只看未隐藏
    rows = client.get("/api/posts?hidden_only=1", headers=admin).json()
    assert [p["id"] for p in rows] == [ids[0]]
    rows = client.get("/api/posts", headers=admin).json()
    assert [p["id"] for p in rows] == [ids[1]]


def test_delete_removes_post_and_push_logs():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    _, ids = _seed_posts(client)
    pid = ids[0]
    db.add_push_log(pid, "telegram", "failed", "boom")

    resp = client.post(f"/api/posts/{pid}/delete", headers=admin)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "deleted": True}
    assert db.get_post(pid) is None
    assert db.list_push_logs(limit=50) == []
    assert client.get(f"/api/posts/{pid}", headers=admin).status_code == 404


def test_hide_delete_requires_admin_and_missing_post_404():
    client = make_client()
    user = user_headers(client, "plainuser2")
    _, ids = _seed_posts(client)
    pid = ids[0]

    for path in (f"/posts/{pid}/hide", f"/posts/{pid}/unhide", f"/posts/{pid}/delete"):
        assert client.post(f"/api{path}", headers=user).status_code in (401, 403)
        assert client.post(f"/api{path}").status_code in (401, 403)

    admin = auth_headers(client)
    for path in ("/posts/999999/hide", "/posts/999999/unhide", "/posts/999999/delete"):
        assert client.post(f"/api{path}", headers=admin).status_code == 404


def test_hide_unhide_delete_writes_audit_log():
    client = make_client()
    admin = auth_headers(client)
    _, ids = _seed_posts(client)
    pid = ids[0]
    client.post(f"/api/posts/{pid}/hide", headers=admin)
    client.post(f"/api/posts/{pid}/unhide", headers=admin)
    client.post(f"/api/posts/{pid}/delete", headers=admin)

    actions = {
        (row["action"], row["target"])
        for row in client.app.state.db.list_admin_logs(limit=100)
    }
    assert {("post_hide", str(pid)), ("post_unhide", str(pid)), ("post_delete", str(pid))} <= actions


def test_retry_push_skips_hidden_post():
    """入库后推送失败 + 管理员隐藏：重启恢复循环不再把该帖入重试队列。"""
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    _, ids = _seed_posts(client)
    for pid in ids:
        db.add_push_log(pid, "telegram", "failed", "boom")
    client.post(f"/api/posts/{ids[0]}/hide", headers=admin)

    scheduler = Scheduler(
        db, {}, [], SimpleNamespace(),
        notifiers_config=SimpleNamespace(),
        xueqiu_config=SimpleNamespace(cookie=""),
        weibo_config=SimpleNamespace(cookie="", username="", password=""),
    )
    scheduler._recover_failed_pushes()
    queued = {item["post"].external_id for item in scheduler.retry_queue._items.values()}
    assert queued == {"ext-2"}  # 隐藏帖不入队，正常帖照常恢复
