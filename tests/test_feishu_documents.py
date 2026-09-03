import json
import threading
import time

import httpx
import pytest
from cryptography.fernet import Fernet

from app.config import FeishuDocumentsConfig
from app.db import DB
from app.feishu_documents import (
    MAX_MEDIA_BYTES,
    FeishuDocumentClient,
    FeishuDocumentError,
    FeishuDocumentSyncService,
    normalize_timeline,
    parse_feishu_document_url,
)
from app.ima_documents import ImaDocumentService


def test_parse_feishu_document_url_normalizes_and_rejects_untrusted_hosts():
    parsed = parse_feishu_document_url(
        "https://hcn3wbq9qksp.feishu.cn/docx/NXbndzo1wowuQFxtH3ec5U3snOd?from=from_copylink"
    )
    assert parsed["canonical_url"] == "https://hcn3wbq9qksp.feishu.cn/docx/NXbndzo1wowuQFxtH3ec5U3snOd"
    assert parsed["source_type"] == "docx"
    assert parsed["group_id"].startswith("feishu-")

    for url in (
        "http://hcn3wbq9qksp.feishu.cn/docx/NXbndzo1wowuQFxtH3ec5U3snOd",
        "https://feishu.cn.evil.test/docx/NXbndzo1wowuQFxtH3ec5U3snOd",
        "https://hcn3wbq9qksp.feishu.cn/share/NXbndzo1wowuQFxtH3ec5U3snOd",
    ):
        try:
            parse_feishu_document_url(url)
        except ValueError:
            pass
        else:
            raise AssertionError(url)


def _paragraph(block_id, text):
    return {
        "block_id": block_id,
        "block_type": 2,
        "text": {"elements": [{"text_run": {"content": text}}]},
    }


def test_timeline_keeps_same_minute_entries_and_reply_relationship():
    timeline = normalize_timeline([
        _paragraph("t1", "2026-09-01 21:18"),
        _paragraph("m1", "天才考研仔：完了 低开那么多"),
        _paragraph("t2", "2026-09-01 21:18"),
        _paragraph("m2", "失业期神 回复 L：对"),
    ])

    assert [item["id"] for item in timeline["entries"]] == ["t1", "t2"]
    assert timeline["entries"][0]["blocks"][0]["speaker"] == "天才考研仔"
    reply = timeline["entries"][1]["blocks"][0]
    assert reply["speaker"] == "失业期神"
    assert reply["reply_to"] == "L"
    assert reply["text"] == "对"


def test_text_before_first_timestamp_is_notice():
    timeline = normalize_timeline([
        _paragraph("notice", "拼团有风险，如遇不可抗力导致断更，恕不退款"),
        _paragraph("t1", "2026-08-31 14:25"),
        _paragraph("body", "这个低开高走"),
    ])
    assert timeline["notices"][0]["text"].startswith("拼团有风险")
    assert timeline["entries"][0]["blocks"][0]["text"] == "这个低开高走"


def test_timeline_normalizes_table_cells_without_rendering_children_twice():
    table = {
        "block_id": "table",
        "block_type": 31,
        "table": {
            "cells": ["cell-1", "cell-2", "cell-3", "cell-4"],
            "property": {"row_size": 2, "column_size": 2},
        },
    }
    blocks = [
        _paragraph("time", "2026-09-01 21:18"),
        table,
        {"block_id": "cell-1", "children": ["p-1"]},
        {"block_id": "cell-2", "children": ["p-2"]},
        {"block_id": "cell-3", "children": ["p-3"]},
        {"block_id": "cell-4", "children": ["p-4"]},
        _paragraph("p-1", "指标"),
        _paragraph("p-2", "数值"),
        _paragraph("p-3", "收入"),
        _paragraph("p-4", "100"),
    ]

    timeline = normalize_timeline(blocks)

    assert timeline["entries"][0]["blocks"] == [{
        "type": "table",
        "block_id": "table",
        "rows": [
            [{"text": "指标"}, {"text": "数值"}],
            [{"text": "收入"}, {"text": "100"}],
        ],
        "columns": 2,
    }]


from app.api import _feishu_timeline_cursor, _feishu_timeline_page


def _timeline_entry(entry_id, day, time="12:00"):
    return {
        "id": entry_id,
        "timestamp": f"{day}T{time}:00+08:00",
        "day": day,
        "time": time,
        "blocks": [{"type": "text", "text": entry_id}],
    }


def test_feishu_timeline_page_returns_latest_seven_days_and_cursor():
    entries = [
        _timeline_entry("d10", "2026-09-10"),
        _timeline_entry("d09", "2026-09-09"),
        _timeline_entry("d08", "2026-09-08"),
        _timeline_entry("d07", "2026-09-07"),
        _timeline_entry("d06", "2026-09-06"),
        _timeline_entry("d05", "2026-09-05"),
        _timeline_entry("d04", "2026-09-04"),
        _timeline_entry("d03", "2026-09-03"),
    ]

    page, has_more, cursor = _feishu_timeline_page(entries, "latest", 7, "")

    assert [item["id"] for item in page] == ["d10", "d09", "d08", "d07", "d06", "d05", "d04"]
    assert has_more is True
    assert cursor == _feishu_timeline_cursor(page[-1])


def test_feishu_timeline_page_uses_strict_timestamp_and_id_cursor():
    entries = [
        _timeline_entry("same-b", "2026-09-04", "12:00"),
        _timeline_entry("same-a", "2026-09-04", "12:00"),
        _timeline_entry("older", "2026-09-03"),
    ]
    before = _feishu_timeline_cursor(entries[0])

    page, _has_more, _cursor = _feishu_timeline_page(entries, "latest", 7, before)

    assert [item["id"] for item in page] == ["same-a", "older"]


def test_feishu_timeline_page_without_window_preserves_full_order():
    entries = [_timeline_entry("a", "2026-09-01"), _timeline_entry("b", "2026-09-02")]

    page, has_more, cursor = _feishu_timeline_page(entries, "latest", None, "")

    assert [item["id"] for item in page] == ["b", "a"]
    assert has_more is False
    assert cursor == ""


def _service(tmp_path, client):
    key = Fernet.generate_key().decode()
    db = DB(tmp_path / "db.sqlite", credential_key=key)
    config = FeishuDocumentsConfig(
        app_id="app",
        app_secret="secret",
        redirect_uri="https://example.com/api/admin/feishu-documents/oauth/callback",
    )
    ima = ImaDocumentService(db, tmp_path / "index", archive_root=tmp_path / "archive")
    service = FeishuDocumentSyncService(
        db,
        config,
        tmp_path / "archive",
        ima_documents=ima,
        client=client,
    )
    return db, ima, service


class FakeFeishuClient:
    def __init__(self, revision="1", blocks=None):
        self.revision = revision
        self.block_items = blocks or [
            _paragraph("time", "2026-09-01 21:18"),
            _paragraph("body", "张三：正文"),
        ]
        self.block_calls = 0
        self.active = 0
        self.max_active = 0
        self.gate = None

    def authorization_url(self, state, code_challenge=""):
        return f"https://accounts.feishu.cn/auth?state={state}&code_challenge={code_challenge}"

    def exchange_code(self, code, code_verifier=""):
        return {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "refresh_token_expires_in": 7200,
        }

    def refresh(self, refresh_token):
        return self.exchange_code("refresh")

    def resolve_document(self, source, access_token):
        return "document"

    def document_meta(self, document_id, access_token):
        return {"document_id": document_id, "title": "测试时间线", "revision_id": self.revision}

    def blocks(self, document_id, revision_id, access_token):
        self.block_calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.gate is not None:
                self.gate.wait(timeout=2)
            return list(self.block_items)
        finally:
            self.active -= 1

    def download_media(self, token, access_token):
        return b"image", "image/png", ""

    def close(self):
        pass


def _authorize(db):
    db.save_feishu_oauth_credential({
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_in": 3600,
        "refresh_token_expires_in": 7200,
    })


def _add_source(db):
    parsed = parse_feishu_document_url(
        "https://a.feishu.cn/docx/NXbndzo1wowuQFxtH3ec5U3snOd"
    )
    return db.upsert_feishu_document_source(parsed)


def test_sync_publishes_archive_and_unchanged_restore_reuses_last_good(tmp_path):
    fake = FakeFeishuClient()
    db, ima, service = _service(tmp_path, fake)
    _authorize(db)
    source = _add_source(db)

    assert service.sync_source(source["id"])["status"] == "updated"
    published = db.get_feishu_document_source(source["id"])
    assert published["revision_id"] == "1"
    assert ima.external_document_current(
        published["group_id"], published["media_id"], published["txt_path"]
    )

    ima.remove_external_document(published["group_id"], published["media_id"])
    assert not ima.external_document_current(
        published["group_id"], published["media_id"], published["txt_path"]
    )
    assert service.sync_source(source["id"])["status"] == "unchanged"
    assert fake.block_calls == 1
    assert ima.external_document_current(
        published["group_id"], published["media_id"], published["txt_path"]
    )


def test_publish_failure_preserves_source_revision_and_last_good(tmp_path, monkeypatch):
    fake = FakeFeishuClient(revision="1")
    db, ima, service = _service(tmp_path, fake)
    _authorize(db)
    source = _add_source(db)
    service.sync_source(source["id"])
    before = db.get_feishu_document_source(source["id"])
    fake.revision = "2"
    monkeypatch.setattr(ima, "external_document_current", lambda *_args: False)

    with pytest.raises(FeishuDocumentError, match="读模型发布失败"):
        service.sync_source(source["id"])

    after = db.get_feishu_document_source(source["id"])
    assert after["revision_id"] == before["revision_id"] == "1"
    assert after["timeline_path"] == before["timeline_path"]
    assert after["sync_status"] == "failed"


def test_sync_rejects_new_revision_when_archive_is_read_only(tmp_path, monkeypatch):
    fake = FakeFeishuClient()
    db, ima, service = _service(tmp_path, fake)
    _authorize(db)
    source = _add_source(db)
    monkeypatch.setattr(ima.store, "archive_writable", lambda: False)

    with pytest.raises(FeishuDocumentError, match="不可写"):
        service.sync_source(source["id"])

    current = db.get_feishu_document_source(source["id"])
    assert current["revision_id"] == ""
    assert current["timeline_path"] == ""


def test_manual_source_syncs_are_serialized(tmp_path):
    fake = FakeFeishuClient()
    fake.gate = threading.Event()
    db, _ima, service = _service(tmp_path, fake)
    _authorize(db)
    first = _add_source(db)
    second = db.upsert_feishu_document_source(parse_feishu_document_url(
        "https://a.feishu.cn/docx/Abcdefghijklmnop"
    ))
    errors = []

    def run(source_id):
        try:
            service.sync_source(source_id, True)
        except Exception as exc:  # pragma: no cover - assertion reports details
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(item["id"],)) for item in (first, second)]
    for thread in threads:
        thread.start()
    time.sleep(0.05)
    fake.gate.set()
    for thread in threads:
        thread.join(timeout=3)

    assert not errors
    assert fake.max_active == 1


def test_oauth_start_uses_s256_pkce_and_encrypted_verifier(tmp_path):
    captured = {}
    fake = FakeFeishuClient()
    db, _ima, service = _service(tmp_path, fake)
    admin_id = db.add_user("pkce-admin", "hash", is_admin=True)

    url = service.oauth_start(admin_id)
    state = url.split("state=", 1)[1].split("&", 1)[0]
    raw = db._rows("SELECT * FROM feishu_document_oauth_sessions")[0]
    ciphertext = raw["code_verifier_ciphertext"]
    assert ciphertext.startswith("enc1:")
    assert "code_challenge=" in url

    fake.exchange_code = lambda code, verifier="": captured.update(code=code, verifier=verifier) or {
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_in": 3600,
        "refresh_token_expires_in": 7200,
    }
    assert service.oauth_callback(state, "code") == admin_id
    assert captured["code"] == "code"
    assert 43 <= len(captured["verifier"]) <= 128
    assert captured["verifier"] not in ciphertext


def test_authorization_url_uses_official_parameters():
    client = FeishuDocumentClient(
        "cli_id", "secret", "https://example.com/callback", "offline_access"
    )
    url = httpx.URL(client.authorization_url("state", "challenge"))
    assert url.params["client_id"] == "cli_id"
    assert url.params["response_type"] == "code"
    assert url.params["code_challenge"] == "challenge"
    assert url.params["code_challenge_method"] == "S256"


def test_oauth_callback_rejects_demoted_admin_before_token_exchange(tmp_path):
    fake = FakeFeishuClient()
    db, _ima, service = _service(tmp_path, fake)
    admin_id = db.add_user("admin", "hash", is_admin=True)
    url = service.oauth_start(admin_id)
    state = url.split("state=", 1)[1].split("&", 1)[0]
    db.update_user(admin_id, is_admin=False)
    called = []
    fake.exchange_code = lambda code, verifier="": called.append((code, verifier)) or {}

    with pytest.raises(FeishuDocumentError, match="不是管理员"):
        service.oauth_callback(state, "code")

    assert called == []
    assert db.get_feishu_oauth_credential() is None


def test_client_retries_rate_limit_and_pages_blocks(monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(429, json={"code": 99991400}, headers={"retry-after": "0"})
        page = request.url.params.get("page_token")
        return httpx.Response(200, json={
            "code": 0,
            "data": {"items": [{"block_id": page or "first"}], "has_more": not page, "page_token": "next"},
        })

    monkeypatch.setattr(time, "sleep", lambda _delay: None)
    client = FeishuDocumentClient("app", "secret", "https://example.com/cb", "scope", httpx.Client(transport=httpx.MockTransport(handler)))

    assert [item["block_id"] for item in client.blocks("doc", "7", "token")] == ["first", "next"]
    assert len(calls) == 3


def test_client_rejects_oversized_media_from_content_length():
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200,
        content=b"x",
        headers={"content-length": str(MAX_MEDIA_BYTES + 1), "content-type": "image/png"},
    ))
    client = FeishuDocumentClient("app", "secret", "https://example.com/cb", "scope", httpx.Client(transport=transport))

    with pytest.raises(FeishuDocumentError, match="50 MB"):
        client.download_media("asset-token", "token")


def test_oauth_session_is_one_time_and_credentials_are_encrypted(tmp_path):
    db = DB(tmp_path / "db.sqlite", credential_key=Fernet.generate_key().decode())
    db.create_feishu_oauth_session("hash", 1, int(time.time()) + 60)
    assert db.consume_feishu_oauth_session("hash", int(time.time()))["user_id"] == 1
    assert db.consume_feishu_oauth_session("hash", int(time.time())) is None

    db.save_feishu_oauth_credential({
        "access_token": "access-secret",
        "refresh_token": "refresh-secret",
        "expires_in": 3600,
        "refresh_token_expires_in": 7200,
        "scope": "docx:document:readonly",
    })
    raw = db._rows("SELECT * FROM feishu_document_oauth")[0]
    assert raw["access_token_ciphertext"].startswith("enc1:")
    assert "access-secret" not in json.dumps(raw)
    credential = db.get_feishu_oauth_credential(decrypt=True)
    assert credential["access_token"] == "access-secret"
    assert credential["refresh_token"] == "refresh-secret"


def test_readding_soft_deleted_source_restores_identity_and_archive_fields(tmp_path):
    db = DB(tmp_path / "db.sqlite")
    parsed = parse_feishu_document_url("https://a.feishu.cn/wiki/Dyc5wDTVUiwiKvkbBO1cGvHWnHh")
    first = db.upsert_feishu_document_source(parsed)
    db.update_feishu_document_source(
        first["id"],
        title="K神-2026",
        timeline_path="feishu-documents/hash/versions/v/timeline.json",
        content_hash="old-version",
    )
    db.soft_delete_feishu_document_source(first["id"])

    restored = db.upsert_feishu_document_source(parsed)
    assert restored["id"] == first["id"]
    assert restored["group_id"] == first["group_id"]
    assert restored["deleted_at"] is None
    assert restored["timeline_path"].endswith("timeline.json")
    assert restored["content_hash"] == "old-version"


def test_service_reports_not_configured_without_document_app(tmp_path):
    db = DB(tmp_path / "db.sqlite")
    service = FeishuDocumentSyncService(db, FeishuDocumentsConfig(), tmp_path)
    assert service.configured is False
    service.stop()


def _feishu_api(tmp_path, monkeypatch, fake=None):
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.test_ima_documents import _headers

    monkeypatch.setenv("DAV_UI_ONLY", "1")
    monkeypatch.setenv("FEISHU_CREDENTIAL_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("FEISHU_DOCS_APP_ID", "cli_id")
    monkeypatch.setenv("FEISHU_DOCS_APP_SECRET", "secret")
    monkeypatch.setenv(
        "FEISHU_DOCS_REDIRECT_URI",
        "https://example.com/api/admin/feishu-documents/oauth/callback",
    )
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    service = client.app.state.feishu_documents
    service.client.close()
    service.client = fake or FakeFeishuClient()
    admin = _headers(client, "fs_admin", "FSADM1", admin=True)
    user = _headers(client, "fs_user", "FSUSR1")
    return client, service, admin, user


def test_feishu_document_preview_returns_metadata_without_creating_source(tmp_path, monkeypatch):
    client, service, admin, _user = _feishu_api(tmp_path, monkeypatch)
    client.app.state.db.save_feishu_oauth_credential({
        "access_token": "access", "refresh_token": "refresh",
        "expires_in": 3600, "refresh_token_expires_in": 7200,
    })

    response = client.post(
        "/api/admin/feishu-documents/preview",
        headers=admin,
        json={"url": "https://a.feishu.cn/docx/NXbndzo1wowuQFxtH3ec5U3snOd?from=copy"},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "source_type": "docx",
        "title": "测试时间线",
        "revision_id": "1",
        "ready": True,
    }
    assert client.app.state.db.list_feishu_document_sources() == []
    assert not list(tmp_path.glob("**/timeline.json"))
    assert service.client.block_calls == 0
    service.stop()


def test_feishu_document_preview_requires_admin_and_authorization(tmp_path, monkeypatch):
    client, service, admin, user = _feishu_api(tmp_path, monkeypatch)
    url = "https://a.feishu.cn/wiki/Dyc5wDTVUiwiKvkbBO1cGvHWnHh"

    assert client.post(
        "/api/admin/feishu-documents/preview", headers=user, json={"url": url}
    ).status_code == 403
    missing = client.post(
        "/api/admin/feishu-documents/preview", headers=admin, json={"url": url}
    )
    assert missing.status_code == 400
    assert "授权" in missing.json()["detail"]
    service.stop()


def test_api_rejects_untrusted_feishu_url(tmp_path, monkeypatch):
    client, _service, admin, _user = _feishu_api(tmp_path, monkeypatch)
    resp = client.post(
        "/api/admin/feishu-documents",
        headers=admin,
        json={"url": "https://feishu.cn.evil.test/docx/NXbndzo1wowuQFxtH3ec5U3snOd"},
    )
    assert resp.status_code == 400


def test_feishu_timeline_is_open_to_all_users(tmp_path, monkeypatch):
    client, _service, admin, user = _feishu_api(tmp_path, monkeypatch)
    client.app.state.db.save_feishu_oauth_credential({
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_in": 3600,
        "refresh_token_expires_in": 7200,
    })
    added = client.post(
        "/api/admin/feishu-documents",
        headers=admin,
        json={"url": "https://a.feishu.cn/docx/NXbndzo1wowuQFxtH3ec5U3snOd"},
    )
    assert added.status_code == 200, added.text
    source = added.json()
    group_id = source["group_id"]
    media_id = source["media_id"]
    assert source["sync_status"] in {"succeeded", "pending", "running"}

    listed = client.get("/api/admin/feishu-documents", headers=admin).json()
    assert listed["authorized"] is True
    published = next(item for item in listed["sources"] if item["id"] == source["id"])
    assert published["revision_id"] == "1"
    assert published["entry_count"] >= 1

    admin_doc = client.get(
        f"/api/ima-documents/{media_id}?group={group_id}", headers=admin
    ).json()
    assert admin_doc["type"] == "feishu_timeline"
    assert admin_doc["source_url"] == "https://a.feishu.cn/docx/NXbndzo1wowuQFxtH3ec5U3snOd"

    catalog = client.get("/api/ima-documents/catalog", headers=user).json()
    assert any(item["id"] == group_id for item in catalog["subscribed"])
    user_doc = client.get(
        f"/api/ima-documents/{media_id}?group={group_id}", headers=user
    ).json()
    assert user_doc["type"] == "feishu_timeline"
    timeline = client.get("/api/ima-documents/timeline/all", headers=user).json()
    assert timeline["entries"]
    assert timeline["entries"][0]["source"]["group_id"] == group_id
    assert "canonical_url" in timeline["sources"][0]
    windowed = client.get(
        f"/api/ima-documents/timeline/all?window_days=7&group={group_id}",
        headers=user,
    )
    assert windowed.status_code == 200, windowed.text
    assert windowed.json()["has_more"] is False
    assert windowed.json()["next_cursor"] == ""
    invalid = client.get(
        "/api/ima-documents/timeline/all?window_days=7&before=bad-cursor",
        headers=user,
    )
    assert invalid.status_code == 400


def test_feishu_docs_config_endpoint_persists_and_hot_reloads(tmp_path, monkeypatch):
    client, service, admin, _user = _feishu_api(tmp_path, monkeypatch)

    initial = client.get("/api/admin/feishu-documents", headers=admin).json()
    assert initial["config"]["app_id"] == "cli_id"  # 来自环境变量
    assert initial["config"]["config_source"] == "env"
    assert initial["config"]["app_secret_set"] is True
    assert initial["config"]["redirect_path_ok"] is True

    saved = client.put(
        "/api/admin/feishu-documents/config",
        headers=admin,
        json={
            "app_id": "cli_page",
            "app_secret": "page-secret-value",
            "redirect_uri": "https://page.example.com/api/admin/feishu-documents/oauth/callback",
            "scopes": "wiki:node:read offline_access",
            "interval_seconds": 120,
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["reauth_required"] is False

    stored = client.get("/api/admin/feishu-documents", headers=admin).json()
    cfg = stored["config"]
    assert cfg["app_id"] == "cli_page"
    assert cfg["config_source"] == "db"
    assert cfg["app_secret_set"] is True
    assert cfg["interval_seconds"] == 120
    assert stored["interval_seconds"] == 120
    assert "page-secret-value" not in saved.text and "page-secret-value" not in stored.__str__()

    db = client.app.state.db
    raw_setting = db.get_setting("feishu_docs_app_secret")
    assert raw_setting.startswith("enc1:")
    assert service.config.app_id == "cli_page"
    assert service.configured is True

    admin_id = db.get_user_by_username("fs_admin")["id"]
    url = service.oauth_start(admin_id)
    assert "state=" in url  # 应用配置齐备后可直接发起授权
    assert service.client.app_id == "cli_page"  # reload_config 已热更新客户端

    assert client.put(
        "/api/admin/feishu-documents/config", headers=admin, json={"interval_seconds": 10}
    ).status_code == 400
    assert client.put(
        "/api/admin/feishu-documents/config", headers=admin,
        json={"redirect_uri": "http://page.example.com/cb"},
    ).status_code == 400
    assert client.put(
        "/api/admin/feishu-documents/config", headers=admin, json={}
    ).status_code == 400
    # 非管理员不可改
    assert client.put(
        "/api/admin/feishu-documents/config", headers=_user, json={"interval_seconds": 60}
    ).status_code == 403
    service.stop()


def test_feishu_source_display_mode_patch_and_detail(tmp_path, monkeypatch):
    client, service, admin, _user = _feishu_api(tmp_path, monkeypatch)
    client.app.state.db.save_feishu_oauth_credential({
        "access_token": "access", "refresh_token": "refresh",
        "expires_in": 3600, "refresh_token_expires_in": 7200,
    })
    added = client.post(
        "/api/admin/feishu-documents", headers=admin,
        json={"url": "https://a.feishu.cn/docx/NXbndzo1wowuQFxtH3ec5U3snOd"},
    ).json()
    source = client.app.state.db.get_feishu_document_source(added["id"])
    service.sync_source(source["id"], True)

    detail = client.get(
        f"/api/ima-documents/{source['media_id']}?group={source['group_id']}", headers=admin
    ).json()
    assert detail["feishu_display"] == "timeline"

    patched = client.patch(
        f"/api/admin/feishu-documents/{source['id']}", headers=admin,
        json={"display_mode": "document"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["display_mode"] == "document"

    detail = client.get(
        f"/api/ima-documents/{source['media_id']}?group={source['group_id']}", headers=admin
    ).json()
    assert detail["feishu_display"] == "document"

    assert client.patch(
        f"/api/admin/feishu-documents/{source['id']}", headers=admin, json={}
    ).status_code == 400
    assert client.patch(
        f"/api/admin/feishu-documents/{source['id']}", headers=admin,
        json={"display_mode": "poster"},
    ).status_code == 400
    service.stop()
