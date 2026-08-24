"""验收：审计清单里的正确性修复。"""
import json
import tempfile
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import DB
from app.fetchers.base import Post
from app.main import create_app
from app.scheduler import PlatformState, flush_digest, poll_once

from tests.test_api import auth_headers, user_headers
from tests.test_scheduler import add_kol_subscribed, make_db, make_post


class BoomFetcher:
    def fetch(self, kol):
        raise RuntimeError("timeout boom")


class OkFetcher:
    def fetch(self, kol):
        return []


class SelectiveError:
    def __init__(self, fail_ids):
        self.fail_ids = set(fail_ids)
        self.calls = []

    def fetch(self, kol):
        self.calls.append(kol["id"])
        if kol["id"] in self.fail_ids:
            raise RuntimeError("one kol timeout")
        return []


def test_one_kol_timeout_does_not_skip_sibling():
    db = make_db()
    a = add_kol_subscribed(db, "xueqiu", "A", "1")
    b = add_kol_subscribed(db, "xueqiu", "B", "2")
    fetcher = SelectiveError({a})
    states = {}
    poll_once(db, {"xueqiu": fetcher}, [], states, interval_seconds=0)
    assert set(fetcher.calls) == {a, b}
    assert states["xueqiu"].skip_until == 0
    assert a in states["xueqiu"].kol_skip_until
    fetcher.calls.clear()
    poll_once(db, {"xueqiu": fetcher}, [], states, interval_seconds=0)
    assert fetcher.calls == [b]


def test_success_clears_platform_skip_until():
    db = make_db()
    kid = add_kol_subscribed(db, "xueqiu", "A", "1")
    states = {"xueqiu": PlatformState()}
    expired = time.monotonic() - 1
    states["xueqiu"].skip_until = expired
    states["xueqiu"].kol_skip_until[kid] = expired
    poll_once(db, {"xueqiu": OkFetcher()}, [], states, interval_seconds=0)
    assert states["xueqiu"].skip_until == 0
    assert kid not in states["xueqiu"].kol_skip_until


def test_flush_digest_keeps_buffer_when_notify_raises(monkeypatch):
    db = make_db()
    kid = add_kol_subscribed(db, "xueqiu", "A", "1")
    digest = {kid: [make_post(kid)]}

    def boom(*_a, **_k):
        raise RuntimeError("digest down")

    monkeypatch.setattr("app.scheduler.notify_digest_subscribers", boom)
    flush_digest(db, digest, [], None)
    assert kid in digest and digest[kid]


def test_delete_user_removes_keywords_and_feishu_bot():
    db = make_db()
    uid = db.add_user("gone", "h")
    kid = db.add_kol("xueqiu", "A", "del-user")
    db.add_subscription(uid, kid)
    db.set_user_keywords(uid, ["茅台"])
    db._execute(
        "INSERT INTO feishu_personal_bots "
        "(user_id, app_id, app_secret_ciphertext, status) VALUES (?, ?, ?, ?)",
        (uid, "cli_x", "cipher", "active"),
    )
    db.delete_user(uid)
    assert db.get_user(uid) is None
    assert db.get_user_keywords(uid) == []
    assert db.get_feishu_personal_bot(uid) is None


def test_delete_kol_removes_cube_snapshots():
    db = make_db()
    kid = db.add_kol("combination", "组合", "ZH1")
    db.set_cube_snapshot(kid, "quote", {"net_value": 1.0})
    assert db.get_cube_snapshot(kid, "quote")
    db.delete_kol(kid)
    assert db.get_cube_snapshot(kid, "quote") is None


def test_set_kol_acl_is_one_transaction(tmp_path):
    db = DB(str(tmp_path / "acl.db"))
    kid = db.add_kol("xueqiu", "私", "acl1")
    u1 = db.add_user("a1", "h")
    u2 = db.add_user("a2", "h")
    db.set_kol_acl(kid, [u1, u2])
    assert set(db.acl_user_ids(kid)) == {u1, u2}
    db.set_kol_acl(kid, [u1])
    assert db.acl_user_ids(kid) == [u1]


def test_last_post_time_uses_kol_column():
    db = make_db()
    kid = db.add_kol("xueqiu", "A", "lp1")
    db.insert_post("xueqiu", kid, "e1", "t", "c", "u", "2026-08-01 10:00")
    times = db.last_post_time_by_kol()
    assert times.get(kid)


def test_existing_post_keys_batch():
    db = make_db()
    kid = db.add_kol("xueqiu", "A", "ex1")
    db.insert_post("xueqiu", kid, "e1", "t", "c", "u", "")
    found = db.existing_post_keys([("xueqiu", "e1"), ("xueqiu", "missing")])
    assert found == {("xueqiu", "e1")}


def test_catalog_hides_disabled_kol():
    tmp = Path(tempfile.mkdtemp())
    client = TestClient(create_app(config=None, db_path=tmp / "t.db"))
    h = auth_headers(client)
    kid = client.app.state.db.add_kol("xueqiu", "停用的", "off1")
    client.app.state.db.update_kol(kid, enabled=False)
    names = [k["name"] for k in client.get("/api/catalog", headers=h).json()]
    assert "停用的" not in names


def test_subscribe_disabled_kol_404():
    tmp = Path(tempfile.mkdtemp())
    client = TestClient(create_app(config=None, db_path=tmp / "t.db"))
    admin = auth_headers(client)
    kid = client.app.state.db.add_kol("xueqiu", "停用的", "off2")
    client.app.state.db.update_kol(kid, enabled=False)
    user = user_headers(client, "suboff")
    resp = client.post("/api/subscriptions", headers=user, json={"kol_id": kid, "type": "post"})
    assert resp.status_code == 404


def test_resubscribe_updates_type():
    tmp = Path(tempfile.mkdtemp())
    client = TestClient(create_app(config=None, db_path=tmp / "t.db"))
    admin = auth_headers(client)
    kid = client.app.state.db.add_kol("xueqiu", "A", "re1")
    user = user_headers(client, "resub01")
    client.post("/api/subscriptions", headers=user, json={"kol_id": kid, "type": "post"})
    resp = client.post("/api/subscriptions", headers=user, json={"kol_id": kid, "type": "both"})
    assert resp.status_code == 200
    uid = next(u["id"] for u in client.app.state.db.list_users() if u["username"] == "resub01")
    assert client.app.state.db.get_subscription(uid, kid)["type"] == "both"


def test_zsxq_file_requires_subscription():
    tmp = Path(tempfile.mkdtemp())
    client = TestClient(create_app(config=None, db_path=tmp / "t.db"))
    admin = auth_headers(client)
    kid = client.app.state.db.add_kol("zsxq", "星球", "288")
    client.app.state.db.insert_posts_batch(
        [
            Post(
                platform="zsxq",
                kol_id=kid,
                kol_name="星球",
                external_id="t1",
                title="pdf",
                content="c",
                url="https://wx.zsxq.com/group/288/t1",
                published_at="2026-08-20 10:00",
                detail={"files": [{"file_id": "181528458481522", "name": "a.pdf", "url": ""}]},
            )
        ]
    )
    files = tmp / "zsxq_files"
    files.mkdir(exist_ok=True)
    (files / "181528458481522.pdf").write_bytes(b"%PDF-1.7 data")
    outsider = user_headers(client, "outsider")
    resp = client.get("/api/media/zsxq-file/181528458481522", headers=outsider)
    assert resp.status_code == 404
    resp_admin = client.get("/api/media/zsxq-file/181528458481522", headers=admin)
    assert resp_admin.status_code == 200


def test_feed_strips_zsxq_raw_detail():
    db = make_db()
    uid = db.add_user("reader", "h")
    kid = db.add_kol("zsxq", "星球", "g1")
    db.add_subscription(uid, kid)
    db.insert_posts_batch(
        [
            Post(
                platform="zsxq",
                kol_id=kid,
                kol_name="星球",
                external_id="t1",
                title="t",
                content="c",
                url="u",
                published_at="",
                detail={"files": [{"file_id": "1", "name": "a.pdf"}], "raw": {"huge": True}},
            )
        ]
    )
    rows = db.list_feed_posts([kid], user_id=uid, include_secondary=True)
    assert rows
    detail = rows[0]["detail"]
    if isinstance(detail, str):
        detail = json.loads(detail)
    assert "raw" not in (detail or {})
    assert detail.get("files")


def test_get_post_detail_defined_once():
    import inspect

    from app import db as dbmod

    source = inspect.getsource(dbmod.DB)
    assert source.count("def get_post_detail(") == 1


def test_combination_skips_rebalancing_with_no_changes():
    from app.config import XueqiuConfig
    from app.fetchers.combination import CombinationFetcher

    payload = {
        "list": [
            {
                "id": 1,
                "status": "success",
                "updated_at": 1785822205799,
                "rebalancing_histories": [
                    {
                        "stock_name": "中国平安",
                        "stock_symbol": "SH601318",
                        "prev_weight": 30.0,
                        "target_weight": 30.0,
                    }
                ],
            }
        ]
    }

    def handler(request):
        if "rebalancing/history" in str(request.url):
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json={})

    fetcher = CombinationFetcher(
        XueqiuConfig(cookie="xq_a_token=abc"),
        db=DB(":memory:"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    posts = fetcher.fetch({"id": 1, "name": "组合", "external_id": "ZH1"})
    assert posts == []


def test_combination_401_does_not_hit_homepage():
    from app.config import XueqiuConfig
    from app.fetchers.combination import CombinationFetcher

    hits = {"home": 0}

    def handler(request):
        if request.url.path == "/":
            hits["home"] += 1
            return httpx.Response(200, text="homepage")
        return httpx.Response(401)

    fetcher = CombinationFetcher(
        XueqiuConfig(cookie="xq_a_token=old"),
        db=DB(":memory:"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        fetcher.fetch({"id": 1, "name": "组合", "external_id": "ZH1"})
    except RuntimeError as exc:
        assert "cookie 已失效" in str(exc)
    else:
        raise AssertionError("401 时应抛出 cookie 失效错误")
    assert hits["home"] == 0


def test_ima_post_exists_error_still_tries_full_text():
    os = __import__("os")
    from app.fetchers.ima import ImaFetcher

    os.environ["IMA_FETCH_DELAY"] = "0"
    os.environ["IMA_PROBE_DELAY"] = "0"
    os.environ["IMA_OPENAPI_CLIENTID"] = "cid"
    os.environ["IMA_OPENAPI_APIKEY"] = "key"
    try:
        calls = []

        def handler(request):
            calls.append(str(request.url))
            if "get_knowledge_list" in str(request.url):
                return httpx.Response(
                    200,
                    json={
                        "retcode": 0,
                        "data": {
                            "knowledge_list": [
                                {
                                    "media_id": "txt_abc",
                                    "title": "文档",
                                    "abstract": "摘要",
                                    "create_time": 1787152223403,
                                    "media_type": 13,
                                }
                            ],
                            "is_end": True,
                            "next_cursor": "",
                        },
                    },
                )
            if "get_media_info" in str(request.url):
                return httpx.Response(
                    200,
                    json={"retcode": 0, "data": {"url_info": {"url": "https://cdn.example/raw.txt"}}},
                )
            if "cdn.example" in str(request.url):
                return httpx.Response(200, content="全文".encode("utf-8"))
            return httpx.Response(404)

        class BoomDB:
            def post_exists(self, *_a, **_k):
                raise RuntimeError("db locked")

            def get_setting(self, *_a, **_k):
                return ""

        fetcher = ImaFetcher(
            db=BoomDB(),
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        posts = fetcher.fetch({"id": 1, "name": "库", "external_id": "kb1"})
        assert posts[0].content == "全文"
        assert any("get_media_info" in u for u in calls)
    finally:
        os.environ.pop("IMA_OPENAPI_CLIENTID", None)
        os.environ.pop("IMA_OPENAPI_APIKEY", None)
        os.environ.pop("IMA_FETCH_DELAY", None)
        os.environ.pop("IMA_PROBE_DELAY", None)
