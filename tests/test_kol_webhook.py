"""系统 KOL Webhook 回归测试：管理端配置 + 入站发帖（飞书自定义机器人风格）。

覆盖：token 生成与轮换、仅系统 KOL 限制、飞书 text/post 与简化格式解析、
msg_id 幂等、签名校验（飞书同款 HMAC）、限流、webhook 字段不随通用接口外泄、
调度器 ingest_external_post 的入库+推送链路（屏蔽词/静默源不推送）。
"""
import base64
import dataclasses
import hashlib
import hmac
import json
import tempfile
import time
from pathlib import Path

from app.db import DB
from app.fetchers.base import Post
from app.scheduler import Scheduler

from test_api import auth_headers, make_client


def _make_system_kol(client, name="Webhook KOL") -> int:
    db = client.app.state.db
    return db.add_kol("system", name, f"sys_{name}")


def _enable_webhook(client, admin, kol_id, **extra):
    return client.put(
        f"/api/admin/kols/{kol_id}/webhook",
        headers=admin,
        json={"enabled": True, **extra},
    )


def _feishu_sign(secret: str, ts: int) -> str:
    string_to_sign = f"{ts}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


# ---- 管理端配置 ----


def test_enable_generates_token_once_and_get_roundtrips():
    client = make_client()
    admin = auth_headers(client)
    kid = _make_system_kol(client)

    resp = client.get(f"/api/admin/kols/{kid}/webhook", headers=admin)
    assert resp.status_code == 200
    info = resp.json()
    assert info["enabled"] is False and info["token"] == "" and info["path"] == ""

    resp = _enable_webhook(client, admin, kid)
    assert resp.status_code == 200, resp.text
    info = resp.json()
    assert info["enabled"] is True and info["token"] and info["path"] == f"/api/kol-webhook/{info['token']}"
    token = info["token"]

    # 再次 PUT 不换 token；GET 与 PUT 视图一致
    resp = _enable_webhook(client, admin, kid)
    assert resp.json()["token"] == token
    assert client.get(f"/api/admin/kols/{kid}/webhook", headers=admin).json()["token"] == token


def test_regenerate_replaces_token():
    client = make_client()
    admin = auth_headers(client)
    kid = _make_system_kol(client)
    old = _enable_webhook(client, admin, kid).json()["token"]

    resp = client.post(f"/api/admin/kols/{kid}/webhook/regenerate", headers=admin)
    assert resp.status_code == 200
    new = resp.json()["token"]
    assert new and new != old


def test_webhook_config_requires_system_kol_and_admin():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    xid = db.add_kol("xueqiu", "普通大V", "u1")

    assert client.get(f"/api/admin/kols/{xid}/webhook", headers=admin).status_code == 400
    assert client.put(
        f"/api/admin/kols/{xid}/webhook", headers=admin, json={"enabled": True}
    ).status_code == 400
    assert client.get("/api/admin/kols/9999/webhook", headers=admin).status_code == 404
    # 非管理员无权读写
    assert client.get(f"/api/admin/kols/{xid + 1}/webhook").status_code == 401
    assert client.get("/api/admin/kols", headers=admin).status_code == 200


def test_secret_set_and_cleared():
    client = make_client()
    admin = auth_headers(client)
    kid = _make_system_kol(client)
    _enable_webhook(client, admin, kid)

    resp = client.put(
        f"/api/admin/kols/{kid}/webhook", headers=admin, json={"secret": "s3cret"}
    )
    assert resp.status_code == 200
    info = resp.json()
    assert info["secret_set"] is True
    assert "s3cret" not in str(info)  # 密钥明文不回传

    resp = client.put(
        f"/api/admin/kols/{kid}/webhook", headers=admin, json={"secret": ""}
    )
    assert resp.json()["secret_set"] is False


# ---- 入站发帖 ----


def _post_incoming(client, token, payload, expect=200):
    resp = client.post(f"/api/kol-webhook/{token}", json=payload)
    assert resp.status_code == expect, resp.text
    return resp


def test_incoming_simplified_and_feishu_text():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kid = _make_system_kol(client, "KOL 甲")
    token = _enable_webhook(client, admin, kid).json()["token"]

    # 简化格式
    data = _post_incoming(client, token, {"text": "你好", "title": "标题"}).json()
    assert data["code"] == 0 and data["post_id"]
    post = db.get_post(data["post_id"])
    assert post["content"] == "你好" and post["title"] == "标题"
    assert post["kol_id"] == kid and post["platform"] == "system" and post["post_type"] == ""

    # 飞书 text 格式
    data = _post_incoming(
        client, token, {"msg_type": "text", "content": {"text": "飞书消息"}}
    ).json()
    assert db.get_post(data["post_id"])["content"] == "飞书消息"

    # 空内容 / 非法 JSON
    _post_incoming(client, token, {"msg_type": "text", "content": {"text": "  "}}, expect=400)
    resp = client.post(
        f"/api/kol-webhook/{token}",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    _post_incoming(client, token, [1, 2], expect=400)


def test_incoming_feishu_post_rich_text():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kid = _make_system_kol(client, "KOL 富文本")
    token = _enable_webhook(client, admin, kid).json()["token"]

    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": "日报",
                    "content": [
                        [{"tag": "text", "text": "第一行 "}, {"tag": "a", "href": "https://e.com", "text": "链接"}],
                        [{"tag": "text", "text": "第二行"}],
                    ],
                }
            }
        },
    }
    data = _post_incoming(client, token, payload).json()
    post = db.get_post(data["post_id"])
    assert post["title"] == "日报"
    assert "第一行 " in post["content"] and "https://e.com" in post["content"]
    assert "第二行" in post["content"]


def test_incoming_msg_id_idempotent():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kid = _make_system_kol(client, "KOL 幂等")
    token = _enable_webhook(client, admin, kid).json()["token"]

    first = _post_incoming(client, token, {"text": "hi", "msg_id": "abc-1"}).json()
    assert first["code"] == 0 and first["post_id"]
    second = _post_incoming(client, token, {"text": "hi", "msg_id": "abc-1"}).json()
    assert second["code"] == 0 and second.get("duplicate") is True
    rows = db._rows("SELECT id FROM posts WHERE kol_id = ?", (kid,))
    assert len(rows) == 1


def test_incoming_sign_verification():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kid = _make_system_kol(client, "KOL 签名")
    token = _enable_webhook(client, admin, kid, secret="top-secret").json()["token"]

    # 未带签名 / 签名错误 / 时间戳过期 → 拒绝
    _post_incoming(client, token, {"text": "hi"}, expect=403)
    _post_incoming(
        client, token, {"text": "hi", "timestamp": str(int(time.time())), "sign": "bad"}, expect=403
    )
    stale = int(time.time()) - 7200
    _post_incoming(
        client,
        token,
        {"text": "hi", "timestamp": str(stale), "sign": _feishu_sign("top-secret", stale)},
        expect=403,
    )

    # 飞书同款签名正确 → 放行
    ts = int(time.time())
    data = _post_incoming(
        client,
        token,
        {"text": "签名消息", "timestamp": str(ts), "sign": _feishu_sign("top-secret", ts)},
    ).json()
    assert data["code"] == 0
    assert db.get_post(data["post_id"])["content"] == "签名消息"


def test_incoming_rejects_bad_token_and_disabled():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kid = _make_system_kol(client, "KOL 停用")
    token = _enable_webhook(client, admin, kid).json()["token"]

    _post_incoming(client, "no-such-token", {"text": "hi"}, expect=404)
    _post_incoming(client, "bad token!", {"text": "hi"}, expect=404)

    # 停用 webhook 后拒绝；停用大V同样拒绝
    client.put(f"/api/admin/kols/{kid}/webhook", headers=admin, json={"enabled": False})
    _post_incoming(client, token, {"text": "hi"}, expect=404)
    _enable_webhook(client, admin, kid)
    db.update_kol(kid, enabled=False)
    _post_incoming(client, token, {"text": "hi"}, expect=404)


def test_incoming_rate_limit():
    client = make_client()
    admin = auth_headers(client)
    kid = _make_system_kol(client, "KOL 限流")
    token = _enable_webhook(client, admin, kid).json()["token"]

    codes = [
        client.post(f"/api/kol-webhook/{token}", json={"text": "hi"}).status_code
        for _ in range(101)
    ]
    assert all(c == 200 for c in codes[:100])
    assert codes[100] == 429


def test_webhook_fields_not_exposed_via_common_endpoints():
    client = make_client()
    admin = auth_headers(client)
    db = client.app.state.db
    kid = _make_system_kol(client, "KOL 泄露")
    _enable_webhook(client, admin, kid, secret="s3cret")

    detail = client.get(f"/api/kols/{kid}", headers=admin).json()
    assert "webhook_token" not in detail and "webhook_secret" not in detail
    listing = client.get("/api/admin/kols", headers=admin).json()
    assert all("webhook_token" not in k for k in listing["items"])
    catalog_rows = client.get("/api/catalog", headers=admin).json()
    assert all("webhook_token" not in k for k in catalog_rows)


# ---- 调度器入库+推送链路 ----


def test_scheduler_ingest_external_post():
    from app import scheduler as scheduler_mod

    tmp = tempfile.mkdtemp()
    db = DB(Path(tmp) / "t.db")
    kid = db.add_kol("system", "AI 报告", "ai_analysis_output")
    sched = Scheduler(db, {}, [], None, None)

    calls = []
    orig = scheduler_mod.notify_subscribers
    scheduler_mod.notify_subscribers = lambda *a, **k: calls.append(a[1])
    try:
        post = Post(
            platform="system",
            kol_id=kid,
            kol_name="AI 报告",
            external_id="webhook_t1_1",
            title="",
            content="你好",
            url="",
            published_at="2026-09-01 10:00:00",
        )
        post_id = sched.ingest_external_post(post)
        assert post_id is not None
        assert calls == [post_id]

        # 重复帖：入库返回 None，不推送
        assert sched.ingest_external_post(post) is None
        assert len(calls) == 1

        # 屏蔽词命中：入库留档但不推送（block_keywords 落库为 JSON 文本）
        db.update_kol(kid, block_keywords=json.dumps(["敏感词"], ensure_ascii=False))
        blocked = sched.ingest_external_post(
            dataclasses.replace(post, external_id="webhook_t1_2", content="包含敏感词的内容")
        )
        assert blocked is not None
        assert len(calls) == 1

        # 静默源：入库不打推送
        db.update_kol(kid, block_keywords="[]", silent=True)
        silent_id = sched.ingest_external_post(
            dataclasses.replace(post, external_id="webhook_t1_3", content="普通内容")
        )
        assert silent_id is not None
        assert len(calls) == 1
    finally:
        scheduler_mod.notify_subscribers = orig


# ---- 前端静态回归（与 test_frontend_interactions.py 同风格）----


def test_admin_ui_webhook_button_and_modal_wiring():
    """系统 KOL 行有 Webhook 按钮，弹窗走专用管理端点。"""
    import re

    app_js = Path(__file__).parent.parent / "app" / "static" / "app.js"
    src = app_js.read_text(encoding="utf-8")
    # 行内按钮：仅 system 平台渲染
    assert re.search(r'k\.platform === "system"[^\n]*adminKolWebhook\(', src)
    # 弹窗与开关走专用端点
    assert "/api/admin/kols/${id}/webhook" in src
    assert "/api/admin/kols/${id}/webhook/regenerate" in src
    # 入站示例 URL 用 /api/kol-webhook/ 前缀
    assert "_kolWebhookUrl" in src
