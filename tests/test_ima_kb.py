import json
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.db import DB
from app.ima_documents import (
    IMA_PURE_GROUPS_KEY,
    ImaDocumentConfig,
    ImaDocumentService,
    ImaDocumentStore,
    ImaGroupConfig,
    ImaPureClient,
    ima_kb_valid_tags,
    purge_ima_document_tags,
)
from app.ima_kb import attach_catalog_stats, attach_catalog_summary, catalog, readable_group_ids
from app.main import create_app
from app.stock_universe import bundled_plain_names
from app.tagging import tag_text
from tests.test_ima_documents import _headers, _write_available_status


def test_admin_ima_put_shares_service_config_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-lock.sqlite"))
    headers = _headers(client, "mount_lock_admin", "MOUNTLOCK", admin=True)
    service = client.app.state.ima_documents
    service.config_lock.acquire()
    response_holder = {}
    started = threading.Event()
    finished = threading.Event()

    def update():
        started.set()
        try:
            response_holder["response"] = client.put(
                "/api/admin/ima-collector",
                headers=headers,
                json={
                    "groups": [{
                        "id": "group-a",
                        "name": "资料",
                        "knowledge_base_id": "kb-a",
                        "root_folder_id": "root-a",
                        "folder_ids": ["new"],
                        "enabled": True,
                    }],
                },
            )
        finally:
            finished.set()

    worker = threading.Thread(target=update)
    worker.start()
    try:
        assert started.wait(5)
        assert not finished.wait(0.1)
    finally:
        service.config_lock.release()
    worker.join(5)
    assert not worker.is_alive()
    assert response_holder["response"].status_code == 200
    saved = json.loads(client.app.state.db.get_setting(IMA_PURE_GROUPS_KEY))
    assert saved[0]["folder_ids"] == ["new"]


def test_admin_ima_scalar_put_shares_service_config_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-scalar-lock.sqlite"))
    headers = _headers(client, "scalar_lock_admin", "SCALARLOCK", admin=True)
    service = client.app.state.ima_documents
    service.config_lock.acquire()
    response_holder = {}
    started = threading.Event()
    finished = threading.Event()

    def update():
        started.set()
        try:
            response_holder["response"] = client.put(
                "/api/admin/ima-collector",
                headers=headers,
                json={"uid": "new-uid"},
            )
        finally:
            finished.set()

    worker = threading.Thread(target=update)
    worker.start()
    try:
        assert started.wait(5)
        assert not finished.wait(0.1)
    finally:
        service.config_lock.release()
    worker.join(5)
    assert not worker.is_alive()
    assert response_holder["response"].status_code == 200
    assert client.app.state.db.get_setting("ima_pure_uid") == "new-uid"


def test_tag_text_uses_vocab_and_stock_names():
    tags = tag_text(
        "宁德时代产业链点评",
        "新能源车需求回暖，宁德时代排产上修。",
        tag_rules=[{"tag": "新能源", "keywords": ["新能源车", "排产"]}],
        stock_names=["宁德时代", "贵州茅台"],
        aliases=[{"alias": "宁王", "stock": "宁德时代"}],
    )
    assert "新能源" in tags
    assert "宁德时代" in tags
    assert tags.count("宁德时代") == 1


def test_tag_text_empty_when_no_hit():
    assert tag_text("无标题", "无关正文", tag_rules=[], stock_names=[], aliases=[]) == []


def test_ima_kb_acl_and_subscribe_roundtrip(tmp_path):
    db = DB(tmp_path / "kb.sqlite")
    admin_id = db.add_user("kb_admin", "hash", is_admin=True)
    user_id = db.add_user("kb_user", "hash", is_admin=False)
    db.set_ima_kb_acl("banking", [user_id])
    assert db.ima_kb_acl_usernames("banking") == ["kb_user"]
    assert db.ima_kb_can_subscribe(user_id, "banking") is True
    assert db.ima_kb_can_subscribe(admin_id, "banking") is False
    assert db.ima_kb_can_read(user_id, "banking") is True
    db.set_ima_kb_acl("banking", [])
    assert db.ima_kb_can_read(user_id, "banking") is False
    assert db.ima_kb_is_subscribed(user_id, "banking") is False
    db.set_ima_kb_acl("banking", [user_id])
    db.set_ima_kb_acl_for_user(user_id, ["macro"])
    assert db.ima_kb_group_ids_for_user(user_id) == ["macro"]
    assert db.ima_kb_subscribed_group_ids_for_user(user_id) == ["macro"]
    assert db.ima_kb_can_subscribe(user_id, "banking") is False


def test_delete_user_clears_ima_kb_rows(tmp_path):
    db = DB(tmp_path / "kb-del.sqlite")
    user_id = db.add_user("gone", "hash", is_admin=False)
    db.set_ima_kb_acl("kb1", [user_id])
    db.ima_kb_subscribe(user_id, "kb1")
    db.delete_user(user_id)
    assert db.ima_kb_acl_usernames("kb1") == []
    assert db.ima_kb_is_subscribed(user_id, "kb1") is False


def _groups():
    return (
        ImaGroupConfig("banking", "投行研报", "kb1", "root1"),
        ImaGroupConfig("macro", "宏观", "kb2", "root2"),
    )


def test_catalog_hides_ungranted_groups_from_users(tmp_path):
    db = DB(tmp_path / "cat.sqlite")
    user_id = db.add_user("reader", "hash", is_admin=False)
    admin_id = db.add_user("owner", "hash", is_admin=True)
    db.set_ima_kb_acl("banking", [user_id])
    user = {"id": user_id, "is_admin": 0}
    admin = {"id": admin_id, "is_admin": 1}
    listed = catalog(db, user, _groups())
    assert [g["id"] for g in listed["subscribed"]] == ["banking"]
    assert listed["available"] == []
    assert {g["id"] for g in catalog(db, admin, _groups())["subscribed"] + catalog(db, admin, _groups())["available"]} >= {"banking", "macro"}
    assert readable_group_ids(db, user, _groups()) == {"banking"}
    assert readable_group_ids(db, admin, _groups()) == {"banking", "macro"}


def test_catalog_endpoint_reads_config_once(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "catalog-snapshot.sqlite"))
    headers = _headers(client, "catalog_snapshot_admin", "CATALOGSNAP", admin=True)
    service = client.app.state.ima_documents
    original_config = service.config
    calls = 0

    def config():
        nonlocal calls
        calls += 1
        return original_config()

    monkeypatch.setattr(service, "config", config)
    response = client.get("/api/ima-documents/catalog", headers=headers)
    assert response.status_code == 200, response.text
    assert calls == 1


def test_catalog_endpoint_does_not_dispatch_to_dynamic_detail(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "catalog-route.sqlite"))
    headers = _headers(client, "catalog_route_admin", "CATALOGROUTE", admin=True)
    store = client.app.state.ima_documents.store

    def unexpected_detail_lookup(*args, **kwargs):
        raise AssertionError("catalog request dispatched to dynamic detail")

    monkeypatch.setattr(store, "document", unexpected_detail_lookup)
    response = client.get("/api/ima-documents/catalog", headers=headers)

    assert response.status_code == 200, response.text
    assert set(response.json()) >= {"subscribed", "available"}


def test_attach_catalog_stats_uses_latest_mmdd_title():
    listed = {
        "subscribed": [{"id": "banking", "name": "投行研报", "enabled": True}],
        "available": [{"id": "macro", "name": "宏观", "enabled": True}],
    }
    attach_catalog_stats(
        listed,
        [
            {"group_id": "banking", "day": "unknown", "name": "坏日期", "media_id": "bad"},
            {"group_id": "banking", "day": "0810", "name": "旧稿", "media_id": "old"},
            {"group_id": "banking", "day": "0826", "name": "新稿.pdf", "media_id": "new"},
            {"group_id": "macro", "day": "0101", "name": "宏观一", "media_id": "m1"},
        ],
    )
    assert listed["subscribed"][0]["document_count"] == 3
    assert listed["subscribed"][0]["latest_day"] == "0826"
    assert listed["subscribed"][0]["latest_title"] == "新稿.pdf"
    assert listed["subscribed"][0]["latest_media_id"] == "new"
    assert listed["available"][0]["document_count"] == 1


def test_attach_catalog_summary_copies_precomputed_stats():
    listed = {
        "subscribed": [{"id": "banking", "name": "投行研报", "enabled": True}],
        "available": [{"id": "macro", "name": "宏观", "enabled": True}],
    }
    attach_catalog_summary(
        listed,
        {
            "banking": {
                "document_count": 3,
                "latest_day": "0826",
                "latest_title": "新稿.pdf",
                "latest_media_id": "new",
            },
            "macro": {
                "document_count": 1,
                "latest_day": "0101",
                "latest_title": "宏观一",
                "latest_media_id": "m1",
            },
        },
    )
    assert listed["subscribed"][0]["document_count"] == 3
    assert listed["subscribed"][0]["latest_day"] == "0826"
    assert listed["subscribed"][0]["latest_title"] == "新稿.pdf"
    assert listed["subscribed"][0]["latest_media_id"] == "new"
    assert listed["available"][0]["document_count"] == 1
    assert listed["available"][0]["latest_media_id"] == "m1"


def test_user_cannot_see_kb_until_granted_and_subscribed(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "acl.sqlite"))
    user_headers = _headers(client, "reader", "KBUSER1")
    admin_headers = _headers(client, "kb_owner", "KBADM1", admin=True)
    store = client.app.state.ima_documents.store
    record = {"media_id": "file_abc", "name": "Report.pdf", "day": "0825", "size": 8}
    pdf = store.pdf_path(record)
    txt = store.txt_path(record)
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7")
    txt.write_text("text", encoding="utf-8")
    store.save_manifest([record])
    store.save_state(
        {
            "file_abc": {
                "pdf": str(pdf.relative_to(store.root)),
                "txt": str(txt.relative_to(store.root)),
                "size": 8,
                "chars": 4,
            }
        }
    )
    listed = client.get("/api/ima-documents", headers=user_headers)
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert client.get("/api/ima-documents/file_abc", headers=user_headers).status_code == 404
    catalog_payload = client.get("/api/ima-documents/catalog", headers=user_headers).json()
    assert catalog_payload["subscribed"] == []
    assert catalog_payload["available"] == []

    group_id = client.get("/api/admin/ima-collector", headers=admin_headers).json()["config"]["groups"][0]["id"]
    granted = client.put(
        f"/api/admin/ima-collector/groups/{group_id}/acl",
        headers=admin_headers,
        json={"usernames": ["reader"]},
    )
    assert granted.status_code == 200, granted.text
    catalog_payload = client.get("/api/ima-documents/catalog", headers=user_headers).json()
    assert [g["id"] for g in catalog_payload["subscribed"]]
    assert catalog_payload["available"] == []
    assert "acl_usernames" not in catalog_payload["subscribed"][0]
    admin_catalog = client.get("/api/ima-documents/catalog", headers=admin_headers).json()
    admin_group = next(g for g in admin_catalog["subscribed"] if g["id"] == group_id)
    assert "reader" in admin_group["acl_usernames"]
    assert client.get("/api/ima-documents/file_abc", headers=user_headers).status_code == 200

    outsider = _headers(client, "outsider", "KBOUT1")
    assert client.post(
        f"/api/ima-documents/groups/{group_id}/subscribe", headers=outsider
    ).status_code == 404
    unknown_user = client.put(
        f"/api/admin/ima-collector/groups/{group_id}/acl",
        headers=admin_headers,
        json={"usernames": ["missing_user"]},
    )
    assert unknown_user.status_code == 400
    unknown_group = client.put(
        "/api/admin/ima-collector/groups/not-a-real-group/acl",
        headers=admin_headers,
        json={"usernames": ["reader"]},
    )
    assert unknown_group.status_code == 404
    status = client.get("/api/admin/ima-collector", headers=admin_headers).json()
    assert "acl_usernames" in status["config"]["groups"][0]
    assert "reader" in status["config"]["groups"][0]["acl_usernames"]

    revoked = client.put(
        f"/api/admin/ima-collector/groups/{group_id}/acl",
        headers=admin_headers,
        json={"usernames": []},
    )
    assert revoked.status_code == 200, revoked.text
    assert client.get("/api/ima-documents/file_abc", headers=user_headers).status_code == 404


def test_ima_file_quota_blocks_burst_but_exempts_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    import app.user_quota as quotas

    monkeypatch.setattr(quotas, "IMA_PDF_BURST", 2)
    monkeypatch.setattr(quotas, "IMA_LIST_BURST", 2)
    client = TestClient(create_app(db_path=tmp_path / "quota.sqlite"))
    user_headers = _headers(client, "reader", "KBQUOTA")
    admin_headers = _headers(client, "kb_owner_q", "KBADMQ", admin=True)
    store = client.app.state.ima_documents.store
    record = {"media_id": "file_abc", "name": "Report.pdf", "day": "0825", "size": 8}
    pdf = store.pdf_path(record)
    txt = store.txt_path(record)
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7 extra")
    txt.write_text("text", encoding="utf-8")
    store.save_manifest([record])
    store.save_state(
        {
            "file_abc": {
                "pdf": str(pdf.relative_to(store.root)),
                "txt": str(txt.relative_to(store.root)),
                "size": 8,
                "chars": 4,
            }
        }
    )
    group_id = client.get("/api/admin/ima-collector", headers=admin_headers).json()["config"]["groups"][0]["id"]
    assert client.put(
        f"/api/admin/ima-collector/groups/{group_id}/acl",
        headers=admin_headers,
        json={"usernames": ["reader"]},
    ).status_code == 200
    pdf_path = f"/api/ima-documents/file_abc/pdf?group={group_id}"
    txt_path = f"/api/ima-documents/file_abc/text?group={group_id}"
    assert client.get(pdf_path, headers=user_headers).status_code == 200
    assert client.get(txt_path, headers=user_headers).status_code == 200
    blocked = client.get(pdf_path, headers=user_headers)
    assert blocked.status_code == 429
    assert "频繁" in blocked.json()["detail"]
    assert blocked.headers.get("retry-after")
    assert client.get(pdf_path, headers=user_headers).status_code == 429
    logs = client.get("/api/admin/logs", headers=admin_headers).json()
    quota_logs = [row for row in logs if row.get("action") == "ima_quota"]
    assert len(quota_logs) == 1
    assert quota_logs[0]["target"] == "reader"
    assert client.get(pdf_path, headers=admin_headers).status_code == 200
    assert client.get("/api/ima-documents", headers=user_headers).status_code == 200
    assert client.get("/api/ima-documents", headers=user_headers).status_code == 200
    listed = client.get("/api/ima-documents", headers=user_headers)
    assert listed.status_code == 429
    assert "频繁" in listed.json()["detail"]


def test_admin_sets_user_ima_kb_groups(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "user-kb.sqlite"))
    user_headers = _headers(client, "reader", "KBUSER2")
    admin_headers = _headers(client, "kb_owner2", "KBADM2", admin=True)
    group_id = client.get("/api/admin/ima-collector", headers=admin_headers).json()["config"]["groups"][0]["id"]
    users = {u["username"]: u for u in client.get("/api/users", headers=admin_headers).json()}
    reader = users["reader"]
    owner = users["kb_owner2"]
    assert reader["ima_kb_groups"] == []
    granted = client.put(
        f"/api/admin/users/{reader['id']}/ima-kb",
        headers=admin_headers,
        json={"group_ids": [group_id]},
    )
    assert granted.status_code == 200, granted.text
    assert granted.json()["ima_kb_groups"] == [group_id]
    reader = next(u for u in client.get("/api/users", headers=admin_headers).json() if u["username"] == "reader")
    assert group_id in reader["ima_kb_groups"]
    catalog = client.get("/api/ima-documents/catalog", headers=user_headers).json()
    assert any(g["id"] == group_id for g in catalog["subscribed"])
    assert catalog["available"] == []
    reader = next(u for u in client.get("/api/users", headers=admin_headers).json() if u["username"] == "reader")
    assert group_id in reader["ima_kb_subscribed"]
    updated = client.put(
        f"/api/users/{reader['id']}",
        headers=admin_headers,
        json={"username": "reader"},
    )
    assert updated.status_code == 200
    assert group_id in updated.json()["ima_kb_groups"]
    assert group_id in updated.json()["ima_kb_subscribed"]
    revoked = client.put(
        f"/api/admin/users/{reader['id']}/ima-kb",
        headers=admin_headers,
        json={"group_ids": []},
    )
    assert revoked.status_code == 200
    assert revoked.json()["ima_kb_groups"] == []
    assert revoked.json()["ima_kb_subscribed"] == []
    assert client.get("/api/ima-documents/catalog", headers=user_headers).json()["available"] == []
    assert client.put(
        f"/api/admin/users/{owner['id']}/ima-kb",
        headers=admin_headers,
        json={"group_ids": [group_id]},
    ).status_code == 400
    assert client.put(
        "/api/admin/users/999999/ima-kb",
        headers=admin_headers,
        json={"group_ids": [group_id]},
    ).status_code == 404
    assert client.put(
        f"/api/admin/users/{reader['id']}/ima-kb",
        headers=admin_headers,
        json={"group_ids": ["not-a-real-group"]},
    ).status_code == 404


def test_admin_stats_includes_ima_kb_acl_usernames(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "stats-acl.sqlite"))
    _headers(client, "reader", "KBSTAT1")
    admin_headers = _headers(client, "kb_stats_admin", "KBSTAT2", admin=True)
    group_id = client.get("/api/admin/ima-collector", headers=admin_headers).json()["config"]["groups"][0]["id"]
    granted = client.put(
        f"/api/admin/ima-collector/groups/{group_id}/acl",
        headers=admin_headers,
        json={"usernames": ["reader"]},
    )
    assert granted.status_code == 200, granted.text
    stats = client.get("/api/stats", headers=admin_headers)
    assert stats.status_code == 200, stats.text
    payload = stats.json()["ima_collector"]["config"]["groups"][0]
    assert "acl_usernames" in payload
    assert "reader" in payload["acl_usernames"]
    assert "refresh_token" not in payload


def test_documents_include_metadata_and_tag_filter(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {
        "media_id": "file_meta",
        "name": "宁德时代纪要.pdf",
        "day": "0826",
        "abstract": "排产上修",
        "cover_url": "https://example.com/c.jpg",
        "group_id": "banking",
    }
    pdf = store.pdf_path(record)
    txt = store.txt_path(record)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.7")
    txt.write_text("正文", encoding="utf-8")
    store.save_manifest([record])
    store.save_state({
        store.state_key(record): {
            "pdf": str(pdf.relative_to(store.root)),
            "txt": str(txt.relative_to(store.root)),
            "tags": ["新能源", "宁德时代"],
            "has_pdf": True,
            "has_txt": True,
        }
    })
    banking = ImaGroupConfig("banking", "投行", "kb", "root")
    items = store.documents(groups=(banking,))
    assert items[0]["abstract"] == "排产上修"
    assert items[0]["cover_url"] == "https://example.com/c.jpg"
    assert items[0]["tags"] == ["新能源", "宁德时代"]
    assert items[0]["has_pdf"] is True
    assert store.documents(tag="新能源", groups=(banking,))[0]["media_id"] == "file_meta"
    assert store.documents(tag="宏观", groups=(banking,)) == []
    assert store.documents(query="排产", groups=(banking,))[0]["media_id"] == "file_meta"
    detail = store.document("file_meta", group_id="banking", groups=(banking,))
    assert detail["abstract"] == "排产上修"
    assert detail["cover_url"] == "https://example.com/c.jpg"
    assert detail["tags"] == ["新能源", "宁德时代"]
    assert detail["has_pdf"] is True
    assert detail["has_txt"] is True


def test_documents_can_list_metadata_without_files(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima2")
    record = {"media_id": "file_bare", "name": "只有摘要.pdf", "day": "0826", "abstract": "摘要", "group_id": "banking"}
    store.save_manifest([record])
    store.save_state({store.state_key(record): {"tags": []}})
    banking = ImaGroupConfig("banking", "投行", "kb", "root")
    items = store.documents(groups=(banking,))
    assert items[0]["media_id"] == "file_bare"
    assert items[0]["has_pdf"] is False
    assert items[0]["has_txt"] is False
    detail = store.document("file_bare", group_id="banking", groups=(banking,))
    assert detail["pdf"] is None
    assert detail["txt"] is None
    assert detail["abstract"] == "摘要"
    assert detail["has_pdf"] is False
    assert detail["has_txt"] is False
    other = ImaGroupConfig("macro", "宏观", "kb2", "root2")
    assert store.documents(groups=(other,)) == []
    assert store.document("file_bare", group_id="banking", groups=(other,)) is None


def test_manifest_records_include_abstract_and_http_cover():
    group = ImaGroupConfig("banking", "投行研报", "kb-1", "folder-1")
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client.list_items = lambda folder_id: [
        {"media_type": 99, "folder_info": {"name": "0825", "folder_id": "day-1"}}
    ] if folder_id == "folder-1" else [
        {
            "media_id": "pdf_1",
            "name": "report.pdf",
            "file_size": 4,
            "abstract": "排产上修",
            "cover_urls": ["/local/c.jpg", "https://example.com/c.jpg"],
        }
    ]
    records = client.manifest()
    assert records[0]["abstract"] == "排产上修"
    assert records[0]["cover_url"] == "https://example.com/c.jpg"


def test_retag_all_writes_tags_from_title_and_txt(tmp_path):
    db = DB(tmp_path / "tag.sqlite")
    db.set_tag_vocabulary([{"tag": "新能源", "keywords": ["排产"]}])
    db.set_stock_names(["宁德时代"])
    service = ImaDocumentService(db, tmp_path / "ima")
    record = {"media_id": "file_tag", "name": "宁德时代纪要.pdf", "day": "0826", "abstract": "排产上修"}
    pdf = service.store.pdf_path(record)
    txt = service.store.txt_path(record)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.7")
    txt.write_text("排产上修，宁德时代", encoding="utf-8")
    service.store.save_manifest([record])
    service.store.save_state({
        service.store.state_key(record): {
            "pdf": str(pdf.relative_to(service.store.root)),
            "txt": str(txt.relative_to(service.store.root)),
        }
    })
    result = service.retag_all()
    assert result["tagged"] >= 1
    state = service.store.load_state()
    tags = state[service.store.state_key(record)]["tags"]
    assert "新能源" in tags
    assert "宁德时代" in tags


def test_retag_all_skips_empty_tags_on_second_run(tmp_path):
    db = DB(tmp_path / "tag-empty.sqlite")
    db.set_tag_vocabulary([{"tag": "新能源", "keywords": ["排产"]}])
    db.set_stock_names(["宁德时代"])
    service = ImaDocumentService(db, tmp_path / "ima")
    record = {"media_id": "file_empty", "name": "宁德时代纪要.pdf", "day": "0826", "abstract": "排产上修"}
    pdf = service.store.pdf_path(record)
    txt = service.store.txt_path(record)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.7")
    txt.write_text("排产上修，宁德时代", encoding="utf-8")
    service.store.save_manifest([record])
    key = service.store.state_key(record)
    service.store.save_state({
        key: {
            "pdf": str(pdf.relative_to(service.store.root)),
            "txt": str(txt.relative_to(service.store.root)),
            "tags": [],
        }
    })
    result = service.retag_all()
    assert result["processed"] == 0
    assert result["tagged"] == 0
    assert service.store.load_state()[key]["tags"] == []


def test_purge_ima_document_tags_keeps_valid_only(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "file_purge", "name": "纪要.pdf", "day": "0826", "group_id": "banking"}
    store.save_manifest([record])
    store.save_state({
        store.state_key(record): {"tags": ["过期标签", "新能源"]},
    })
    changed = purge_ima_document_tags(store, {"新能源"})
    assert changed == 1
    assert store.load_state()[store.state_key(record)]["tags"] == ["新能源"]
    assert purge_ima_document_tags(store, {"新能源"}) == 0


def test_purge_ima_document_tags_keeps_concurrent_state_write(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima-purge-race")
    existing_key = "existing"
    store.save_state({existing_key: {"tags": ["keep", "obsolete"]}})
    read = threading.Event()
    resume = threading.Event()
    original_load_state = store.load_state

    def paused_load_state():
        read.set()
        assert resume.wait(5)
        return original_load_state()

    store.load_state = paused_load_state
    purge_result = {}
    writer_done = threading.Event()

    def purge():
        purge_result["changed"] = purge_ima_document_tags(store, {"keep"})

    def sync_write():
        store.save_state({
            existing_key: {"tags": ["keep", "obsolete"]},
            "sync-entry": {"tags": ["keep"]},
        })
        writer_done.set()

    purge_thread = threading.Thread(target=purge)
    purge_thread.start()
    assert read.wait(5)
    writer_thread = threading.Thread(target=sync_write)
    writer_thread.start()
    assert not writer_done.wait(0.1)
    resume.set()
    purge_thread.join(5)
    writer_thread.join(5)
    assert not purge_thread.is_alive()
    assert not writer_thread.is_alive()
    assert purge_result["changed"] == 1
    state = store.load_state()
    assert state[existing_key]["tags"] == ["keep", "obsolete"]
    assert state["sync-entry"]["tags"] == ["keep"]


def test_ima_kb_valid_tags_keeps_bundled_universe_name(tmp_path):
    db = DB(tmp_path / "kb-universe.sqlite")
    db.set_tag_vocabulary([{"tag": "新能源", "keywords": ["排产"]}])
    db.set_stock_names(["茅台"])
    curated = set(db.get_stock_names())
    universe_name = next(
        (n for n in bundled_plain_names() if len(n) >= 3 and n not in curated),
        None,
    )
    valid = ima_kb_valid_tags(db)
    if universe_name is None:
        # bundled universe empty: fall back to curated/vocab only
        keep = "茅台"
        assert keep in valid
    else:
        assert universe_name not in curated
        assert universe_name in valid
        keep = universe_name

    store = ImaDocumentStore(tmp_path / "ima-universe")
    record = {"media_id": "file_universe", "name": "纪要.pdf", "day": "0826"}
    store.save_manifest([record])
    store.save_state({store.state_key(record): {"tags": [keep, "过期标签"]}})
    changed = purge_ima_document_tags(store, valid)
    assert changed == 1
    assert store.load_state()[store.state_key(record)]["tags"] == [keep]


def test_document_detail_exposes_metadata_and_list_filters_by_tag(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "kb-meta.sqlite"))
    admin_headers = _headers(client, "kb_meta_admin", "KBMETA1", admin=True)
    store = client.app.state.ima_documents.store
    tagged = {
        "media_id": "file_tagged",
        "name": "宁德时代纪要.pdf",
        "day": "0826",
        "abstract": "排产上修",
        "cover_url": "https://example.com/c.jpg",
    }
    other = {
        "media_id": "file_other",
        "name": "宏观点评.pdf",
        "day": "0810",
        "abstract": "利率",
        "cover_url": "https://example.com/m.jpg",
    }
    state = {}
    for record, tags in ((tagged, ["新能源", "宁德时代"]), (other, ["宏观"])):
        pdf = store.pdf_path(record)
        txt = store.txt_path(record)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.7")
        txt.write_text("正文", encoding="utf-8")
        state[store.state_key(record)] = {
            "pdf": str(pdf.relative_to(store.root)),
            "txt": str(txt.relative_to(store.root)),
            "tags": tags,
            "has_pdf": True,
            "has_txt": True,
        }
    store.save_manifest([tagged, other])
    store.save_state(state)

    detail = client.get("/api/ima-documents/file_tagged", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["abstract"] == "排产上修"
    assert payload["tags"] == ["新能源", "宁德时代"]
    assert payload["has_pdf"] is True

    listed = client.get("/api/ima-documents?tag=新能源", headers=admin_headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["media_id"] for item in items] == ["file_tagged"]
    assert items[0]["tags"] == ["新能源", "宁德时代"]
    assert "新能源" in listed.json()["tags"]
    assert "宏观" in listed.json()["tags"]
    assert listed.json()["tag_counts"]["新能源"] == 1
    assert listed.json()["tag_counts"]["宏观"] == 1
    by_day = client.get("/api/ima-documents?day=0826", headers=admin_headers)
    assert by_day.status_code == 200
    assert [item["media_id"] for item in by_day.json()["items"]] == ["file_tagged"]
    assert set(by_day.json()["days"]) == {"0826", "0810"}


def test_catalog_entries_and_facets_do_not_need_files(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima-cheap")
    banking = ImaGroupConfig("banking", "投行", "kb", "root")
    older = {
        "media_id": "file_old",
        "name": "旧稿.pdf",
        "day": "0810",
        "abstract": "旧摘要很长" * 20,
        "cover_url": "https://example.com/old.jpg",
        "group_id": "banking",
    }
    newer = {
        "media_id": "file_new",
        "name": "新稿.pdf",
        "day": "0826",
        "abstract": "新摘要",
        "cover_url": "https://example.com/new.jpg",
        "group_id": "banking",
    }
    store.save_manifest([older, newer])
    store.save_state({
        store.state_key(older): {"tags": ["宏观"], "pdf": "missing/old.pdf", "size": 12},
        store.state_key(newer): {"tags": ["新能源"], "txt": "missing/new.txt"},
    })
    entries = store.catalog_entries(groups=(banking,))
    assert {(item["media_id"], item["day"], item["name"]) for item in entries} == {
        ("file_old", "0810", "旧稿.pdf"),
        ("file_new", "0826", "新稿.pdf"),
    }
    facets = store.document_facets(group_id="banking", groups=(banking,))
    assert facets["days"] == ["0826", "0810"]
    assert set(facets["tags"]) == {"宏观", "新能源"}
    assert facets["tag_counts"] == {"宏观": 1, "新能源": 1}
    assert facets["document_count"] == 2
    assert store.document_facets("不存在", group_id="banking", groups=(banking,)) == facets
    listed = store.documents(groups=(banking,), include_body=False)
    assert listed[0]["media_id"] == "file_new"
    assert listed[0]["has_pdf"] is False
    assert listed[0]["has_txt"] is True
    assert listed[0]["size"] == 0
    assert "abstract" not in listed[0]
    assert "cover_url" not in listed[0]
    missing_pdf = store.documents(day="0810", groups=(banking,), include_body=False)
    assert missing_pdf[0]["has_pdf"] is True
    assert missing_pdf[0]["size"] == 12
    summary = store.group_summary((banking,))
    assert summary == [{"id": "banking", "name": "投行", "count": 2}]


def test_documents_page_slices_search_hits(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima-page")
    banking = ImaGroupConfig("banking", "投行", "kb", "root")
    records = [
        {"media_id": f"file_{idx}", "name": f"研报{idx}.pdf", "day": "0826", "abstract": "锂电", "group_id": "banking"}
        for idx in range(3)
    ]
    store.save_manifest(records)
    store.save_state({store.state_key(record): {"tags": ["新能源"]} for record in records})
    page = store.documents(query="研报", groups=(banking,), include_body=False, limit=2, offset=0)
    assert [item["media_id"] for item in page] == ["file_2", "file_1"]
    assert store.documents(query="研报", groups=(banking,), include_body=False, limit=2, offset=2)[0]["media_id"] == "file_0"
    assert [item["media_id"] for item in store.documents(query="锂电", groups=(banking,), include_body=False)] == ["file_2", "file_1", "file_0"]


def test_list_ima_documents_defaults_to_latest_stream_and_pages_search(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "kb-day.sqlite"))
    admin_headers = _headers(client, "kb_day_admin", "KBDAY01", admin=True)
    store = client.app.state.ima_documents.store
    records = [
        {"media_id": "file_old", "name": "旧稿.pdf", "day": "0810", "abstract": "旧摘要"},
        {"media_id": "file_new", "name": "新稿.pdf", "day": "0826", "abstract": "新摘要"},
        {"media_id": "file_hit", "name": "锂电跟踪.pdf", "day": "0810", "abstract": "新摘要也在旧日"},
        {"media_id": "file_unknown", "name": "杂项.pdf", "day": "unknown", "abstract": "无日期"},
    ]
    store.save_manifest(records)
    store.save_state({store.state_key(record): {"tags": ["新能源"]} for record in records})

    latest = client.get("/api/ima-documents", headers=admin_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["day"] == ""
    assert {item["media_id"] for item in body["items"]} == {"file_old", "file_new", "file_hit", "file_unknown"}
    assert body["items"][0]["media_id"] == "file_new"
    assert "abstract" not in body["items"][0]
    assert "cover_url" not in body["items"][0]
    assert body["has_more"] is False
    paged = client.get("/api/ima-documents?limit=2&offset=0", headers=admin_headers).json()
    assert paged["has_more"] is True
    assert len(paged["items"]) == 2
    assert body["days"] == ["unknown", "0826", "0810"]
    assert "unknown" in body["days"]

    missing = client.get("/api/ima-documents?day=0101", headers=admin_headers)
    assert missing.json()["items"] == []
    assert missing.json()["day"] == "0101"
    assert missing.json()["days"] == ["unknown", "0826", "0810"]

    search = client.get("/api/ima-documents?q=摘要&limit=1&offset=0", headers=admin_headers)
    assert search.status_code == 200
    search_body = search.json()
    assert search_body["day"] == ""
    assert search_body["has_more"] is True
    assert len(search_body["items"]) == 1
    page2 = client.get("/api/ima-documents?q=摘要&limit=1&offset=1", headers=admin_headers).json()
    assert page2["has_more"] is True
    ids = {search_body["items"][0]["media_id"], page2["items"][0]["media_id"]}
    assert "file_new" in ids
    assert search_body["items"][0]["media_id"] != page2["items"][0]["media_id"]
    page3 = client.get("/api/ima-documents?q=摘要&limit=1&offset=2", headers=admin_headers).json()
    assert page3["has_more"] is False


def test_documents_searches_tags_and_group_name_and_ranks_title_hits_first(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima-report-search")
    semi = ImaGroupConfig("semi", "SemiAnalysis", "kb-semi", "root")
    records = [
        {
            "media_id": "body-hit",
            "name": "数据中心周报.pdf",
            "day": "0829",
            "abstract": "AI 算力需求继续增长",
            "group_id": "semi",
        },
        {
            "media_id": "title-hit",
            "name": "全球 AI 资本开支展望.pdf",
            "day": "0828",
            "abstract": "云厂商资本开支",
            "group_id": "semi",
        },
        {
            "media_id": "tag-hit",
            "name": "电力基础设施框架.pdf",
            "day": "0827",
            "abstract": "公用事业",
            "group_id": "semi",
        },
    ]
    store.save_manifest(records)
    store.save_state({
        store.state_key(records[0]): {},
        store.state_key(records[1]): {},
        store.state_key(records[2]): {"tags": ["AI"]},
    })

    matches = store.documents(query="ai", groups=(semi,), include_body=False)

    assert [item["media_id"] for item in matches] == [
        "title-hit",
        "tag-hit",
        "body-hit",
    ]
    assert all("_match_rank" not in item for item in matches)
    assert store.documents(query="semianalysis", groups=(semi,), include_body=False)


def test_document_detail_and_translate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "kb-tr.sqlite"))
    admin_headers = _headers(client, "kb_tr_admin", "KBTR001", admin=True)
    store = client.app.state.ima_documents.store
    zh = {"media_id": "file_zh", "name": "中文.pdf", "day": "0826", "abstract": "宁德时代排产上修，产业链需求回暖。"}
    en = {"media_id": "file_en", "name": "English.pdf", "day": "0826", "abstract": "CATL solid-state timeline"}
    store.save_manifest([zh, en])
    store.save_state({store.state_key(zh): {}, store.state_key(en): {}})

    zh_detail = client.get("/api/ima-documents/file_zh", headers=admin_headers).json()
    assert zh_detail["needs_translation"] is False
    assert zh_detail["abstract_zh"] == ""

    en_detail = client.get("/api/ima-documents/file_en", headers=admin_headers).json()
    assert en_detail["needs_translation"] is True
    assert en_detail["abstract"] == "CATL solid-state timeline"

    monkeypatch.setattr(
        "app.scheduler.translate_text",
        lambda text, **kwargs: "宁德时代固态时间表",
    )
    translated = client.post("/api/ima-documents/file_en/translate", headers=admin_headers)
    assert translated.status_code == 200
    assert translated.json()["abstract_zh"] == "宁德时代固态时间表"
    again = client.get("/api/ima-documents/file_en", headers=admin_headers).json()
    assert again["needs_translation"] is False
    assert again["abstract_zh"] == "宁德时代固态时间表"
    state = store.load_state()[store.state_key(en)]
    assert state["abstract_zh"] == "宁德时代固态时间表"
    assert state["abstract_src_hash"]


def test_save_state_preserves_disk_abstract_zh(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima-tr-lock")
    record = {"media_id": "file_en", "name": "English.pdf", "day": "0826"}
    key = store.state_key(record)
    store.save_state(
        {
            key: {
                "pdf": "0826/a.pdf",
                "abstract_zh": "宁德时代固态时间表",
                "abstract_src_hash": "abc",
            }
        }
    )
    store.save_state({key: {"pdf": "0826/a.pdf", "txt": "0826/a.txt", "tags": ["新能源"]}})
    saved = store.load_state()[key]
    assert saved["pdf"] == "0826/a.pdf"
    assert saved["txt"] == "0826/a.txt"
    assert saved["tags"] == ["新能源"]
    assert saved["abstract_zh"] == "宁德时代固态时间表"
    assert saved["abstract_src_hash"] == "abc"


def test_write_abstract_zh_merges_without_wiping_fields(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima-tr-merge")
    record = {
        "media_id": "file_en",
        "name": "English.pdf",
        "day": "0826",
        "abstract": "CATL solid-state timeline",
    }
    key = store.state_key(record)
    store.save_manifest([record])
    store.save_state({key: {"pdf": "0826/a.pdf", "tags": ["新能源"]}})
    store.write_abstract_zh("file_en", text_zh="宁德时代固态时间表")
    saved = store.load_state()[key]
    assert saved["pdf"] == "0826/a.pdf"
    assert saved["tags"] == ["新能源"]
    assert saved["abstract_zh"] == "宁德时代固态时间表"
    assert saved["abstract_src_hash"]


def test_translate_acl_failures_and_stale_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "kb-tr-acl.sqlite"))
    admin_headers = _headers(client, "kb_tr_acl_admin", "KBTRACL", admin=True)
    guest_headers = _headers(client, "kb_tr_guest", "KBTRGST")
    store = client.app.state.ima_documents.store
    zh = {"media_id": "file_zh", "name": "中文.pdf", "day": "0826", "abstract": "宁德时代排产上修，产业链需求回暖。"}
    en = {"media_id": "file_en", "name": "English.pdf", "day": "0826", "abstract": "CATL solid-state timeline"}
    store.save_manifest([zh, en])
    store.save_state({store.state_key(zh): {}, store.state_key(en): {}})

    def boom(*args, **kwargs):
        raise AssertionError("translate_text should not be called")

    monkeypatch.setattr("app.scheduler.translate_text", boom)
    denied = client.post("/api/ima-documents/file_en/translate", headers=guest_headers)
    assert denied.status_code == 404

    chinese = client.post("/api/ima-documents/file_zh/translate", headers=admin_headers)
    assert chinese.status_code == 200
    assert chinese.json()["abstract_zh"] == "宁德时代排产上修，产业链需求回暖。"

    def fail_translate(*args, **kwargs):
        raise RuntimeError("x down")

    monkeypatch.setattr("app.scheduler.translate_text", fail_translate)
    failed = client.post("/api/ima-documents/file_en/translate", headers=admin_headers)
    assert failed.status_code == 200
    assert failed.json()["abstract_zh"] == "CATL solid-state timeline"
    en_state = store.load_state()[store.state_key(en)]
    assert not en_state.get("abstract_zh")

    store.save_state(
        {
            store.state_key(en): {
                "abstract_zh": "旧译文",
                "abstract_src_hash": "deadbeef",
            }
        }
    )
    stale = client.get("/api/ima-documents/file_en", headers=admin_headers).json()
    assert stale["needs_translation"] is True
    assert stale["abstract_zh"] == ""


def test_admin_ima_discover_and_folder_listing(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-api.sqlite"))
    headers = _headers(client, "mount_admin", "MOUNT01", admin=True)
    db = client.app.state.db
    db.set_setting("ima_pure_uid", "uid")
    db.set_setting("ima_pure_refresh_token", "refresh")
    db.set_setting(
        IMA_PURE_GROUPS_KEY,
        json.dumps([{
            "id": "old", "name": "旧库", "knowledge_base_id": "kb-old",
            "root_folder_id": "root-old", "folder_ids": [], "enabled": False,
            "source": "manual",
        }], ensure_ascii=False),
    )

    class FakeClient:
        fail_listing = False

        def __init__(self, config, group=None):
            self.group = group

        def discover_groups(self):
            return (ImaGroupConfig("kb-new", "新知识库", "kb-new", "root-new"),)

        def list_items(self, folder_id, **_kwargs):
            assert self.group.knowledge_base_id == "kb-new"
            if self.fail_listing:
                raise RuntimeError('Cookie: SID=folder-cookie-secret; Path=/; {"access_token":"folder-json-secret"}')
            return [{
                "media_type": 99,
                "folder_info": {"folder_id": "folder-a", "name": "周报"},
                "folder_number": 2,
            }]

    monkeypatch.setattr("app.ima_documents.ImaPureClient", FakeClient)
    import app.api as api_module
    monkeypatch.setattr(api_module, "ImaPureClient", FakeClient, raising=False)

    discovered = client.post("/api/admin/ima-collector/discover", headers=headers)
    assert discovered.status_code == 200, discovered.text
    group = next(
        item for item in discovered.json()["config"]["groups"] if item["id"] == "kb-new"
    )
    assert group["folder_ids"] == []
    assert group["enabled"] is False

    listed = client.get(
        "/api/admin/ima-collector/groups/kb-new/folders",
        headers=headers,
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == [{
        "id": "folder-a", "name": "周报", "parent_id": "root-new",
        "has_children": True, "folder_count": 2,
    }]
    FakeClient.fail_listing = True
    failed = client.get(
        "/api/admin/ima-collector/groups/kb-new/folders",
        headers=headers,
    )
    assert failed.status_code == 502
    assert "folder-cookie-secret" not in failed.text
    assert "folder-json-secret" not in failed.text
    assert "<redacted>" in failed.text
    assert client.get(
        "/api/admin/ima-collector/groups/kb-new/folders?parent_id=bad/id",
        headers=headers,
    ).status_code == 400
    assert client.get(
        "/api/admin/ima-collector/groups/kb-new/folders",
    ).status_code == 401


def test_admin_ima_put_folder_ids_validates_and_keeps_old_client_compat(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-put.sqlite"))
    headers = _headers(client, "mount_put_admin", "MOUNTPUT", admin=True)
    body = {
        "groups": [{
            "id": "group-a", "name": "资料", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "folder_ids": ["f1", "f1", "f2"],
            "enabled": True,
        }]
    }
    response = client.put("/api/admin/ima-collector", headers=headers, json=body)
    assert response.status_code == 200, response.text
    saved = json.loads(client.app.state.db.get_setting(IMA_PURE_GROUPS_KEY))
    assert saved[0]["folder_ids"] == ["f1", "f2"]
    assert saved[0]["enabled"] is True

    old = client.put("/api/admin/ima-collector", headers=headers, json={
        "groups": [{
            "id": "group-a", "name": "资料", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "enabled": True,
        }]
    })
    assert old.status_code == 200, old.text
    assert json.loads(client.app.state.db.get_setting(IMA_PURE_GROUPS_KEY))[0]["folder_ids"] == ["f1", "f2"]


@pytest.mark.parametrize("folder_ids", [
    ["bad/id"], [""], [123], ["f"] * 257,
])
def test_admin_ima_put_rejects_invalid_folder_ids(tmp_path, monkeypatch, folder_ids):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-invalid.sqlite"))
    headers = _headers(client, "mount_invalid_admin", "MOUNTINV", admin=True)
    response = client.put("/api/admin/ima-collector", headers=headers, json={
        "groups": [{
            "id": "group-a", "name": "资料", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "folder_ids": folder_ids,
        }]
    })
    assert response.status_code == 400, response.text


def test_admin_ima_put_clears_manifest_for_omitted_groups(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-omitted.sqlite"))
    headers = _headers(client, "omitted_group_admin", "OMITTED1", admin=True)
    db = client.app.state.db
    service = client.app.state.ima_documents
    db.set_setting(IMA_PURE_GROUPS_KEY, json.dumps([
        {
            "id": "group-a", "name": "资料 A", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "folder_ids": ["folder-a"], "enabled": True,
            "source": "manual",
        },
        {
            "id": "group-b", "name": "资料 B", "knowledge_base_id": "kb-b",
            "root_folder_id": "root-b", "folder_ids": ["folder-b"], "enabled": True,
            "source": "manual",
        },
    ], ensure_ascii=False))
    service.store.save_manifest([
        {"media_id": "file-a", "name": "a.pdf", "group_id": "group-a"},
        {"media_id": "file-b", "name": "b.pdf", "group_id": "group-b"},
    ])

    response = client.put(
        "/api/admin/ima-collector",
        headers=headers,
        json={"groups": [{
            "id": "group-b", "name": "资料 B", "knowledge_base_id": "kb-b",
            "root_folder_id": "root-b", "folder_ids": ["folder-b"], "enabled": True,
        }]},
    )
    assert response.status_code == 200, response.text
    saved = json.loads(db.get_setting(IMA_PURE_GROUPS_KEY))
    assert [group["id"] for group in saved] == ["group-b"]
    assert [record["media_id"] for record in service.store.load_manifest()] == ["file-b"]


def test_admin_ima_put_clears_stale_manifest_for_omitted_disabled_group(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-omitted-disabled.sqlite"))
    headers = _headers(client, "omitted_disabled_admin", "OMITTEDDIS", admin=True)
    db = client.app.state.db
    service = client.app.state.ima_documents
    db.set_setting(IMA_PURE_GROUPS_KEY, json.dumps([
        {
            "id": "group-a", "name": "资料 A", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "folder_ids": [], "enabled": False,
            "source": "manual",
        },
        {
            "id": "group-b", "name": "资料 B", "knowledge_base_id": "kb-b",
            "root_folder_id": "root-b", "folder_ids": ["folder-b"], "enabled": True,
            "source": "manual",
        },
    ], ensure_ascii=False))
    service.store.save_manifest([
        {"media_id": "stale-a", "name": "a.pdf", "group_id": "group-a"},
    ])

    response = client.put(
        "/api/admin/ima-collector",
        headers=headers,
        json={"groups": [{
            "id": "group-b", "name": "资料 B", "knowledge_base_id": "kb-b",
            "root_folder_id": "root-b", "folder_ids": ["folder-b"], "enabled": True,
        }]},
    )
    assert response.status_code == 200, response.text
    saved = json.loads(db.get_setting(IMA_PURE_GROUPS_KEY))
    assert [group["id"] for group in saved] == ["group-b"]
    assert service.store.load_manifest() == []


def test_admin_ima_discover_failure_keeps_previous_groups(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-discover-fail.sqlite"))
    headers = _headers(client, "mount_fail_admin", "MOUNTFAIL", admin=True)
    db = client.app.state.db
    db.set_setting("ima_pure_uid", "uid")
    db.set_setting("ima_pure_refresh_token", "refresh")
    original = [{
        "id": "old", "name": "旧库", "knowledge_base_id": "kb-old",
        "root_folder_id": "root-old", "folder_ids": ["keep"],
        "enabled": True, "source": "discovered",
    }]
    db.set_setting(IMA_PURE_GROUPS_KEY, json.dumps(original, ensure_ascii=False))

    class BrokenClient:
        def __init__(self, config, group=None):
            pass

        def discover_groups(self):
            raise RuntimeError("https://ima.invalid/?token=secret")

    monkeypatch.setattr("app.ima_documents.ImaPureClient", BrokenClient)
    response = client.post("/api/admin/ima-collector/discover", headers=headers)
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["discovery"]["status"] == "failed"
    assert "secret" not in response.text
    assert json.loads(db.get_setting(IMA_PURE_GROUPS_KEY)) == original


def test_full_text_index_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    monkeypatch.delenv("IMA_SEARCH_GROUP_IDS", raising=False)
    path = tmp_path / "ima-search.db"

    client = TestClient(create_app(db_path=tmp_path / "disabled-search.sqlite"))

    assert client.app.state.ima_search_index.group_ids == ()
    assert client.app.state.ima_search_index.path == path
    assert client.app.state.ima_documents.status()["full_text_index"] == {
        "enabled": False,
        "ready": False,
        "documents": 0,
        "last_sync_at": "",
        "error": "",
    }
    assert not path.exists()


def test_full_text_index_env_parses_deduplicated_groups_and_path(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    monkeypatch.setenv("IMA_SEARCH_GROUP_IDS", " group-b,group-a, group-b,, ")

    client = TestClient(create_app(db_path=tmp_path / "configured-search.sqlite"))
    index = client.app.state.ima_search_index

    assert index.group_ids == ("group-b", "group-a")
    assert index.path == tmp_path / "ima-search.db"
    assert index.archive_root == (tmp_path / "ima").resolve()
    assert not index.path.exists()


def test_full_text_index_db_rows_filter_and_order_groups(tmp_path):
    db = DB(tmp_path / "rows.sqlite")
    db.replace_ima_document_index(
        [
            {"group_id": "group-b", "media_id": "two", "name": "B"},
            {"group_id": "group-a", "media_id": "two", "name": "A2"},
            {"group_id": "group-a", "media_id": "one", "name": "A1"},
        ],
        "fingerprint",
        0,
    )

    assert db.ima_document_index_rows([]) == []
    rows = db.ima_document_index_rows(["group-b", "group-a", "group-a"])
    assert [(row["group_id"], row["media_id"]) for row in rows] == [
        ("group-a", "one"),
        ("group-a", "two"),
        ("group-b", "two"),
    ]
    assert rows[0]["txt_path"] == ""


def test_full_text_index_maintenance_runs_after_final_metadata_rebuild(tmp_path, monkeypatch):
    db = DB(tmp_path / "maintenance.sqlite")
    service = ImaDocumentService(db, tmp_path / "ima")
    calls = []

    monkeypatch.setattr(service, "_rebuild_index_if_needed", lambda: calls.append("rebuild"))
    monkeypatch.setattr(service.store, "archive_writable", lambda: False)
    monkeypatch.setattr(service.store, "archive_readable", lambda: False)
    monkeypatch.setattr(service, "_sync_full_text_index", lambda: calls.append("full-text"))

    service._archive_maintenance()

    assert calls == ["rebuild", "rebuild", "full-text"]


def test_full_text_index_sync_once_invokes_background_sync_once(tmp_path, monkeypatch):
    db = DB(tmp_path / "cycle.sqlite")
    service = ImaDocumentService(db, tmp_path / "ima")
    group = ImaGroupConfig("group-a", "资料", "kb-a", "root-a", folder_ids=("folder-a",))
    config = ImaDocumentConfig(uid="uid", refresh_token="refresh", groups=(group,))
    calls = []

    monkeypatch.setattr(service, "config", lambda: config)
    monkeypatch.setattr(service, "_storage_block_status", lambda: None)
    monkeypatch.setattr(
        service,
        "discover",
        lambda: {"ok": True, "discovery": {"status": "ok", "error": ""}},
    )
    monkeypatch.setattr(
        service,
        "_sync_group",
        lambda *_args, **_kwargs: {
            "group_id": "group-a",
            "group_name": "资料",
            "total": 0,
            "pending": 0,
            "downloaded": 0,
            "failed": 0,
            "last_error": "",
        },
    )
    monkeypatch.setattr(service, "_sync_full_text_index", lambda: calls.append("sync"))

    assert service.sync_once()["status"] == "finished"
    assert calls == ["sync"]


def test_full_text_index_failure_does_not_escape_maintenance_or_healthz(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    monkeypatch.setenv("IMA_SEARCH_GROUP_IDS", "group-a")
    monkeypatch.delenv("IMA_ARCHIVE_ROOT", raising=False)
    monkeypatch.delenv("IMA_STORAGE_STATUS_PATH", raising=False)
    client = TestClient(create_app(db_path=tmp_path / "failure.sqlite"))
    service = client.app.state.ima_documents
    scheduler_started = threading.Event()
    log_seen = threading.Event()
    log_messages = []

    def fail(_rows):
        raise RuntimeError("simulated full-text failure")

    def record_exception(message, *args, **kwargs):
        log_messages.append(message)
        log_seen.set()

    def schedule_loop():
        scheduler_started.set()
        service._stop.wait(2)

    monkeypatch.setattr(client.app.state.ima_search_index, "sync", fail)
    monkeypatch.setattr("app.ima_documents.logger.exception", record_exception)
    monkeypatch.setattr(service, "_rebuild_index_if_needed", lambda: None)
    monkeypatch.setattr(service.store, "archive_writable", lambda: False)
    monkeypatch.setattr(service.store, "archive_readable", lambda: False)
    monkeypatch.setattr(service, "_schedule_loop", schedule_loop)

    service.start()
    scheduler = service._scheduler_thread
    try:
        assert scheduler_started.wait(1)
        assert log_seen.wait(1)
        assert scheduler is not None and scheduler.is_alive()
        assert client.get("/healthz").status_code == 200
        assert service.status()["full_text_index"]["enabled"] is True
        assert log_messages == ["IMA full-text index sync failed"]
    finally:
        service.stop()

    assert scheduler is not None and not scheduler.is_alive()


def _remote_storage_client(tmp_path, monkeypatch, *, available=True, writable=True, **status_overrides):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    archive_root = tmp_path / "archive"
    archive_root.mkdir(exist_ok=True)
    (archive_root / ".vpush-ima-root").touch()
    status_path = tmp_path / "status.json"
    _write_available_status(
        status_path,
        available=available,
        writable=writable,
        **status_overrides,
    )
    monkeypatch.setenv("IMA_ARCHIVE_ROOT", str(archive_root))
    monkeypatch.setenv("IMA_STORAGE_STATUS_PATH", str(status_path))
    client = TestClient(create_app(db_path=tmp_path / "ima-storage.sqlite"))
    return client, archive_root, status_path


def _seed_remote_document(client, archive_root, *, pdf_bytes=b"%PDF-1.7", txt="hello"):
    store = client.app.state.ima_documents.store
    admin_headers = _headers(client, "storage_admin", "STORADM1", admin=True)
    group_id = client.get("/api/admin/ima-collector", headers=admin_headers).json()["config"]["groups"][0]["id"]
    record = {
        "media_id": "file_storage",
        "name": "Report.pdf",
        "day": "0827",
        "group_id": group_id,
        "size": len(pdf_bytes),
    }
    pdf = store.pdf_path(record)
    txt_path = store.txt_path(record)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(pdf_bytes)
    txt_path.write_text(txt, encoding="utf-8")
    relative_pdf = str(pdf.relative_to(store.archive_root))
    relative_txt = str(txt_path.relative_to(store.archive_root))
    store.save_manifest([record])
    store.save_state(
        {
            store.state_key(record): {
                "pdf": relative_pdf,
                "txt": relative_txt,
                "size": len(pdf_bytes),
                "chars": len(txt),
                "name": "Report.pdf",
                "day": "0827",
                "group_id": group_id,
            }
        }
    )
    return admin_headers, group_id, relative_pdf, relative_txt


def test_admin_ima_collector_includes_storage(tmp_path, monkeypatch):
    client, _, _ = _remote_storage_client(tmp_path, monkeypatch)
    headers = _headers(client, "collector_storage", "COLSTOR1", admin=True)
    payload = client.get("/api/admin/ima-collector", headers=headers).json()
    assert "storage" in payload
    assert payload["storage"]["status"] == "available"
    assert payload["storage"]["available"] is True
    assert "capacity_blocked" not in payload["storage"]


def test_admin_ima_collector_put_includes_storage(tmp_path, monkeypatch):
    client, _, _ = _remote_storage_client(tmp_path, monkeypatch)
    headers = _headers(client, "collector_put_storage", "COLPUTST", admin=True)
    payload = client.put("/api/admin/ima-collector", headers=headers, json={}).json()
    assert "storage" in payload
    assert payload["storage"]["status"] == "available"
    assert payload["storage"]["available"] is True


def test_list_catalog_detail_ok_during_storage_outage(tmp_path, monkeypatch):
    client, archive_root, status_path = _remote_storage_client(
        tmp_path, monkeypatch, available=False, writable=False
    )
    admin_headers, group_id, _, _ = _seed_remote_document(client, archive_root)
    store = client.app.state.ima_documents.store

    def boom(*_args, **_kwargs):
        raise AssertionError("document detail must not resolve or stat archive paths")

    monkeypatch.setattr(store, "_state_path", boom)
    monkeypatch.setattr(store, "authorized_archive_file", boom)

    listed = client.get("/api/ima-documents", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["items"]
    catalog_payload = client.get("/api/ima-documents/catalog", headers=admin_headers)
    assert catalog_payload.status_code == 200
    detail = client.get("/api/ima-documents/file_storage", headers=admin_headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["has_pdf"] is True
    assert body["has_txt"] is True
    assert status_path.is_file()
    assert group_id


def test_pdf_txt_return_503_when_storage_unavailable(tmp_path, monkeypatch):
    client, archive_root, _ = _remote_storage_client(
        tmp_path, monkeypatch, available=False, writable=False
    )
    admin_headers, _, _, _ = _seed_remote_document(client, archive_root)
    pdf = client.get("/api/ima-documents/file_storage/pdf", headers=admin_headers)
    txt = client.get("/api/ima-documents/file_storage/text", headers=admin_headers)
    assert pdf.status_code == 503
    assert pdf.json()["detail"] == "知识库存储暂不可用"
    assert txt.status_code == 503
    assert txt.json()["detail"] == "知识库存储暂不可用"


def test_pdf_range_request_returns_partial_content(tmp_path, monkeypatch):
    client, archive_root, _ = _remote_storage_client(tmp_path, monkeypatch)
    admin_headers, _, _, _ = _seed_remote_document(
        client, archive_root, pdf_bytes=b"A" * 4096
    )
    resp = client.get(
        "/api/ima-documents/file_storage/pdf",
        headers={**admin_headers, "Range": "bytes=0-1023"},
    )
    assert resp.status_code == 206
    assert resp.headers["content-range"] == "bytes 0-1023/4096"
    assert len(resp.content) == 1024


@pytest.mark.parametrize(
    ("status_overrides", "expected_detail"),
    [
        ({"available": False, "writable": False}, "知识库存储暂不可用"),
        (
            {"checked_at": int(time.time()) - 10_000, "available": True, "writable": True},
            "知识库存储状态已过期",
        ),
        ({"available": True, "writable": False, "capacity_blocked": False}, "知识库存储当前只读"),
        (
            {"available": True, "writable": True, "capacity_blocked": True},
            "知识库存储空间已达限制",
        ),
    ],
)
def test_manual_sync_maps_blocked_storage_to_503(
    tmp_path, monkeypatch, status_overrides, expected_detail
):
    client, archive_root, status_path = _remote_storage_client(tmp_path, monkeypatch)
    _write_available_status(status_path, **status_overrides)
    headers = _headers(client, "sync_block_admin", "SYNCBLOCK", admin=True)
    db = client.app.state.db
    db.set_setting("ima_pure_uid", "uid")
    db.set_setting("ima_pure_refresh_token", "refresh")
    assert archive_root.is_dir()
    resp = client.post("/api/admin/ima-collector/sync", headers=headers)
    assert resp.status_code == 503
    assert resp.json()["detail"] == expected_detail


def test_ima_collector_sync_unknown_group_404(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-sync-unknown.sqlite"))
    headers = _headers(client, "sync_unknown_admin", "SYNCUNKN", admin=True)
    db = client.app.state.db
    db.set_setting("ima_pure_uid", "uid")
    db.set_setting("ima_pure_refresh_token", "refresh")
    response = client.post(
        "/api/admin/ima-collector/sync",
        headers=headers,
        json={"group_id": "missing"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "知识库不存在"


def test_ima_collector_sync_unmounted_group_409(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-sync-unmounted.sqlite"))
    headers = _headers(client, "sync_unmounted_admin", "SYNCUNMT", admin=True)
    db = client.app.state.db
    db.set_setting("ima_pure_uid", "uid")
    db.set_setting("ima_pure_refresh_token", "refresh")
    db.set_setting(
        IMA_PURE_GROUPS_KEY,
        json.dumps([{
            "id": "unmounted",
            "name": "未挂载",
            "knowledge_base_id": "kb-unmounted",
            "root_folder_id": "root-unmounted",
            "folder_ids": [],
            "enabled": True,
            "source": "manual",
        }], ensure_ascii=False),
    )
    response = client.post(
        "/api/admin/ima-collector/sync",
        headers=headers,
        json={"group_id": "unmounted"},
    )
    assert response.status_code == 409


def _configure_two_groups(client, headers):
    response = client.put(
        "/api/admin/ima-collector",
        headers=headers,
        json={
            "groups": [
                {
                    "id": "group-a",
                    "name": "SemiAnalysis",
                    "knowledge_base_id": "kb-a",
                    "root_folder_id": "root-a",
                    "folder_ids": ["folder-a"],
                    "enabled": True,
                },
                {
                    "id": "group-b",
                    "name": "宏观",
                    "knowledge_base_id": "kb-b",
                    "root_folder_id": "root-b",
                    "folder_ids": ["folder-b"],
                    "enabled": True,
                },
            ]
        },
    )
    assert response.status_code == 200, response.text
    return ("group-a", "group-b")


def _seed_indexed_record(store, record, *, tags=None, txt="hello"):
    pdf = store.pdf_path(record)
    txt_path = store.txt_path(record)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.7")
    txt_path.write_text(txt, encoding="utf-8")
    return {
        store.state_key(record): {
            "pdf": str(pdf.relative_to(store.archive_root)),
            "txt": str(txt_path.relative_to(store.archive_root)),
            "size": 8,
            "chars": len(txt),
            "name": record["name"],
            "day": record.get("day") or "unknown",
            "group_id": record["group_id"],
            "tags": tags or [],
        }
    }


def _block_json_readers(store, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("indexed API must not read JSON")

    monkeypatch.setattr(store, "load_manifest", boom)
    monkeypatch.setattr(store, "load_state", boom)


def _seed_full_text_search(client, records_and_tags):
    service = client.app.state.ima_documents
    store = service.store
    records = []
    state = {}
    for record, tags, text in records_and_tags:
        records.append(record)
        state.update(_seed_indexed_record(store, record, tags=tags, txt=text))
    store.save_manifest(records)
    store.save_state(state)
    assert service.rebuild_read_index(service.config().groups)["status"] == "ready"
    service._sync_full_text_index()
    assert service.search_index.status()["ready"] is True
    return service


def _full_text_search_client(tmp_path, monkeypatch, name):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    monkeypatch.setenv("IMA_SEARCH_GROUP_IDS", "group-a,group-b")
    client = TestClient(create_app(db_path=tmp_path / f"{name}.sqlite"))
    admin_headers = _headers(client, f"{name}_admin", "FTSADMIN1", admin=True)
    reader_headers = _headers(client, f"{name}_reader", "FTSREAD01")
    group_a, group_b = _configure_two_groups(client, admin_headers)
    reader = client.app.state.db.get_user_by_username(f"{name}_reader")
    client.app.state.db.set_ima_kb_acl(group_a, [reader["id"]])
    return client, admin_headers, reader_headers, group_a, group_b


def test_full_text_search_api_preserves_metadata_order_dedupes_and_enforces_acl(
    tmp_path, monkeypatch
):
    client, admin_headers, reader_headers, group_a, group_b = _full_text_search_client(
        tmp_path, monkeypatch, "hybrid_order"
    )
    phrase = "quantum interconnect"
    records = [
        ({"media_id": "title-hit", "name": "Quantum interconnect outlook.pdf", "day": "0904", "group_id": group_a, "abstract": "title"}, [], phrase + " in body"),
        ({"media_id": "tag-hit", "name": "Tag report.pdf", "day": "0903", "group_id": group_a, "abstract": "tag"}, [phrase], "unrelated body"),
        ({"media_id": "abstract-hit", "name": "Abstract report.pdf", "day": "0902", "group_id": group_a, "abstract": phrase + " adoption"}, [], "unrelated body"),
        ({"media_id": "body-hit", "name": "Body report.pdf", "day": "0901", "group_id": group_a, "abstract": "unrelated"}, [], "deep " + phrase + " demand"),
        ({"media_id": "private-hit", "name": "Private report.pdf", "day": "0905", "group_id": group_b, "abstract": "unrelated"}, [], "private " + phrase),
    ]
    _seed_full_text_search(client, records)

    response = client.get(
        "/api/ima-documents?q=quantum%20interconnect", headers=reader_headers
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["media_id"] for item in items] == [
        "title-hit", "tag-hit", "abstract-hit", "body-hit"
    ]
    assert [item["media_id"] for item in items].count("title-hit") == 1
    assert "private-hit" not in {item["media_id"] for item in items}
    assert "quantum interconnect" in items[-1]["search_snippet"].casefold()
    assert "abstract" not in items[-1]
    assert "body" not in items[-1]

    selected = client.get(
        f"/api/ima-documents?q=quantum%20interconnect&group={group_a}",
        headers=admin_headers,
    ).json()["items"]
    assert "private-hit" not in {item["media_id"] for item in selected}


def test_hybrid_full_text_search_applies_exact_tag_to_body_only_hits(
    tmp_path, monkeypatch
):
    client, admin_headers, _reader_headers, group_a, _group_b = _full_text_search_client(
        tmp_path, monkeypatch, "hybrid_tag"
    )
    records = [
        ({"media_id": "selected", "name": "Selected.pdf", "day": "0902", "group_id": group_a, "abstract": "none"}, ["selected-tag"], "liquidity runway improves"),
        ({"media_id": "other", "name": "Other.pdf", "day": "0901", "group_id": group_a, "abstract": "none"}, ["other-tag"], "liquidity runway declines"),
    ]
    _seed_full_text_search(client, records)

    items = client.get(
        "/api/ima-documents?q=liquidity%20runway&tag=selected-tag",
        headers=admin_headers,
    ).json()["items"]

    assert [item["media_id"] for item in items] == ["selected"]


def test_hybrid_full_text_search_pages_metadata_then_body_without_duplicates(
    tmp_path, monkeypatch
):
    client, admin_headers, _reader_headers, group_a, _group_b = _full_text_search_client(
        tmp_path, monkeypatch, "hybrid_pages"
    )
    phrase = "wafer bottleneck"
    records = [
        ({"media_id": "metadata", "name": "Wafer bottleneck.pdf", "day": "0902", "group_id": group_a, "abstract": "none"}, [], phrase + " duplicate body"),
        ({"media_id": "body", "name": "Supply report.pdf", "day": "0901", "group_id": group_a, "abstract": "none"}, [], "persistent " + phrase),
    ]
    _seed_full_text_search(client, records)

    pages = [
        client.get(
            f"/api/ima-documents?q=wafer%20bottleneck&limit=1&offset={offset}",
            headers=admin_headers,
        ).json()
        for offset in range(3)
    ]

    assert [page["items"][0]["media_id"] for page in pages[:2]] == ["metadata", "body"]
    assert pages[0]["has_more"] is True
    assert pages[1]["has_more"] is False
    assert pages[2]["items"] == []
    assert pages[2]["has_more"] is False


def test_hybrid_full_text_search_pages_beyond_rank_200(
    tmp_path, monkeypatch
):
    client, admin_headers, _reader_headers, group_a, _group_b = _full_text_search_client(
        tmp_path, monkeypatch, "hybrid_deep_pages"
    )
    records = [
        (
            {
                "media_id": f"body-{index_value:03d}",
                "name": f"Document {index_value:03d}.pdf",
                "day": "0901",
                "group_id": group_a,
                "abstract": "unrelated",
            },
            [],
            "ranked body needle",
        )
        for index_value in range(205)
    ]
    _seed_full_text_search(client, records)

    deep_page = client.get(
        "/api/ima-documents?q=ranked%20body%20needle&limit=3&offset=201",
        headers=admin_headers,
    ).json()
    final_page = client.get(
        "/api/ima-documents?q=ranked%20body%20needle&limit=3&offset=204",
        headers=admin_headers,
    ).json()

    assert [item["media_id"] for item in deep_page["items"]] == [
        "body-201", "body-202", "body-203"
    ]
    assert deep_page["has_more"] is True
    assert [item["media_id"] for item in final_page["items"]] == ["body-204"]
    assert final_page["has_more"] is False
    assert final_page["document_count"] == 205


def test_hybrid_metadata_page_does_not_materialize_all_matches(
    tmp_path, monkeypatch
):
    client, admin_headers, _reader_headers, group_a, _group_b = _full_text_search_client(
        tmp_path, monkeypatch, "hybrid_bounded_metadata"
    )
    records = [
        (
            {
                "media_id": f"metadata-{index_value}",
                "name": f"Capacity planning {index_value}.pdf",
                "day": f"090{index_value}",
                "group_id": group_a,
                "abstract": "unrelated",
            },
            [],
            "capacity planning body",
        )
        for index_value in range(1, 6)
    ]
    service = _seed_full_text_search(client, records)
    calls = {"count": 0, "page": 0, "search": 0}
    original_count = service.db.ima_document_match_count
    original_page = service.db.ima_document_page
    original_search = service.search_index.search

    def counted_count(*args, **kwargs):
        calls["count"] += 1
        return original_count(*args, **kwargs)

    def counted_page(*args, **kwargs):
        calls["page"] += 1
        return original_page(*args, **kwargs)

    def counted_search(*args, **kwargs):
        calls["search"] += 1
        return original_search(*args, **kwargs)

    monkeypatch.setattr(service.db, "ima_document_match_count", counted_count)
    monkeypatch.setattr(service.db, "ima_document_page", counted_page)
    monkeypatch.setattr(service.search_index, "search", counted_search)

    response = client.get(
        "/api/ima-documents?q=capacity%20planning&limit=2",
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == 2
    assert response.json()["has_more"] is True
    assert calls == {"count": 1, "page": 1, "search": 0}


def test_hybrid_full_text_search_short_missing_and_broken_indexes_keep_metadata(
    tmp_path, monkeypatch
):
    client, admin_headers, _reader_headers, group_a, _group_b = _full_text_search_client(
        tmp_path, monkeypatch, "hybrid_fallback"
    )
    records = [
        ({"media_id": "short", "name": "估值跟踪.pdf", "day": "0902", "group_id": group_a, "abstract": "估值"}, [], "unrelated"),
        ({"media_id": "fallback", "name": "Fallback phrase.pdf", "day": "0901", "group_id": group_a, "abstract": "none"}, [], "unrelated"),
    ]
    service = _seed_full_text_search(client, records)

    short = client.get("/api/ima-documents?q=%E4%BC%B0%E5%80%BC", headers=admin_headers)
    assert [item["media_id"] for item in short.json()["items"]] == ["short"]

    service.search_index.path = tmp_path / "absent-search.db"
    missing = client.get("/api/ima-documents?q=fallback%20phrase", headers=admin_headers)
    assert [item["media_id"] for item in missing.json()["items"]] == ["fallback"]

    def broken_search(*_args, **_kwargs):
        raise sqlite3.OperationalError("broken optional index")

    monkeypatch.setattr(service.search_index, "search", broken_search)
    broken = client.get("/api/ima-documents?q=fallback%20phrase", headers=admin_headers)
    assert broken.status_code == 200, broken.text
    assert [item["media_id"] for item in broken.json()["items"]] == ["fallback"]


@pytest.mark.parametrize(
    ("metadata_total", "page_limit", "expected_fts_calls", "expected_count"),
    [
        (0, 50, [(51, 2000)], 2051),
        (0, 200, [(200, 2000), (1, 2200)], 2201),
        (0, 500, [(200, 2000), (200, 2200), (101, 2400)], 2501),
        (1, 1, [(200, offset) for offset in range(0, 2200, 200)], 2200),
    ],
)
def test_hybrid_max_offset_uses_bounded_fts_batches(
    tmp_path,
    monkeypatch,
    metadata_total,
    page_limit,
    expected_fts_calls,
    expected_count,
):
    client, admin_headers, _reader_headers, group_a, _group_b = _full_text_search_client(
        tmp_path, monkeypatch, f"hybrid_max_offset_{metadata_total}"
    )
    service = client.app.state.ima_documents
    calls = {"search": [], "lookup": 0}

    monkeypatch.setattr(service, "_index_usable", lambda: True)
    monkeypatch.setattr(service.search_index, "status", lambda: {"error": ""})
    monkeypatch.setattr(
        service.db,
        "ima_document_match_count",
        lambda *_args, **_kwargs: metadata_total,
    )

    def search(_query, _group_ids, limit, *, offset=0):
        calls["search"].append((limit, offset))
        assert limit <= 200
        return [
            {
                "group_id": group_a,
                "media_id": f"hit-{rank}",
                "search_snippet": "body needle",
            }
            for rank in range(offset, offset + limit)
        ]

    def lookup(keys, *_args, **_kwargs):
        calls["lookup"] += 1
        return [
            {
                "group_id": group_id,
                "media_id": media_id,
                "name": f"{media_id}.pdf",
                "day": "0901",
                "_metadata_match": metadata_total == 1 and media_id == "hit-0",
            }
            for group_id, media_id in keys
        ]

    monkeypatch.setattr(service.search_index, "search", search)
    monkeypatch.setattr(service.db, "ima_documents_by_keys", lookup)

    response = client.get(
        f"/api/ima-documents?q=body%20needle&limit={page_limit}&offset=2000",
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert [item["media_id"] for item in response.json()["items"]] == [
        f"hit-{rank}" for rank in range(2000, 2000 + page_limit)
    ]
    assert response.json()["has_more"] is True
    assert response.json()["document_count"] == expected_count
    assert calls == {"search": expected_fts_calls, "lookup": len(expected_fts_calls)}


def test_hybrid_tag_filter_stops_after_eleven_rejected_fts_batches(
    tmp_path, monkeypatch
):
    client, admin_headers, _reader_headers, group_a, _group_b = _full_text_search_client(
        tmp_path, monkeypatch, "hybrid_tag_batch_cap"
    )
    service = client.app.state.ima_documents
    calls = {"search": 0, "lookup": 0}

    monkeypatch.setattr(service, "_index_usable", lambda: True)
    monkeypatch.setattr(
        service.db,
        "ima_document_match_count",
        lambda *_args, **_kwargs: 0,
    )

    def search(_query, _group_ids, limit, *, offset=0):
        calls["search"] += 1
        if calls["search"] > 11:
            raise AssertionError("hybrid FTS scan exceeded eleven batches")
        assert limit == 200
        return [
            {
                "group_id": group_a,
                "media_id": f"rejected-{rank}",
                "search_snippet": "body needle",
            }
            for rank in range(offset, offset + limit)
        ]

    def reject_all(_keys, *_args, **_kwargs):
        calls["lookup"] += 1
        return []

    monkeypatch.setattr(service.search_index, "search", search)
    monkeypatch.setattr(service.db, "ima_documents_by_keys", reject_all)

    response = client.get(
        "/api/ima-documents?q=body%20needle&tag=restricted&limit=1",
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []
    assert response.json()["has_more"] is False
    assert response.json()["document_count"] == 0
    assert calls == {"search": 11, "lookup": 11}


@pytest.mark.parametrize(
    (
        "scenario",
        "page_offset",
        "eligible_batch",
        "eligible_count",
        "expected_ids",
        "expected_has_more",
        "expected_count",
    ),
    [
        ("full_page", 0, 11, 2, ["candidate-2000", "candidate-2001"], True, 3),
        ("sparse_deep", 2000, 1, 1, [], False, 1),
    ],
)
def test_hybrid_capped_pages_report_lower_bounds_honestly(
    tmp_path,
    monkeypatch,
    scenario,
    page_offset,
    eligible_batch,
    eligible_count,
    expected_ids,
    expected_has_more,
    expected_count,
):
    client, admin_headers, _reader_headers, group_a, _group_b = _full_text_search_client(
        tmp_path, monkeypatch, f"cap_{scenario}"
    )
    service = client.app.state.ima_documents
    calls = {"search": 0, "lookup": 0}

    monkeypatch.setattr(service, "_index_usable", lambda: True)
    monkeypatch.setattr(
        service.db,
        "ima_document_match_count",
        lambda *_args, **_kwargs: 0,
    )

    def search(_query, _group_ids, limit, *, offset=0):
        calls["search"] += 1
        return [
            {
                "group_id": group_a,
                "media_id": f"candidate-{rank}",
                "search_snippet": "body needle",
            }
            for rank in range(offset, offset + limit)
        ]

    def lookup(keys, *_args, **_kwargs):
        calls["lookup"] += 1
        if calls["lookup"] != eligible_batch:
            return []
        return [
            {
                "group_id": group_id,
                "media_id": media_id,
                "name": f"{media_id}.pdf",
                "day": "0901",
                "_metadata_match": False,
            }
            for group_id, media_id in keys[:eligible_count]
        ]

    monkeypatch.setattr(service.search_index, "search", search)
    monkeypatch.setattr(service.db, "ima_documents_by_keys", lookup)

    response = client.get(
        f"/api/ima-documents?q=body%20needle&tag=restricted&limit=2&offset={page_offset}",
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["media_id"] for item in body["items"]] == expected_ids
    assert body["has_more"] is expected_has_more
    assert body["document_count"] == expected_count
    assert calls == {"search": 11, "lookup": 11}


def test_hybrid_stale_search_error_disables_direct_deep_seek(tmp_path, monkeypatch):
    client, admin_headers, _reader_headers, group_a, _group_b = _full_text_search_client(
        tmp_path, monkeypatch, "hybrid_stale_seek"
    )
    service = client.app.state.ima_documents
    offsets = []
    lookup_calls = 0

    monkeypatch.setattr(service, "_index_usable", lambda: True)
    monkeypatch.setattr(service.search_index, "status", lambda: {"error": "sync failed"})
    monkeypatch.setattr(
        service.db,
        "ima_document_match_count",
        lambda *_args, **_kwargs: 0,
    )

    def search(_query, _group_ids, limit, *, offset=0):
        offsets.append(offset)
        assert limit == 200
        return [
            {
                "group_id": group_a,
                "media_id": f"hit-{rank}",
                "search_snippet": "body needle",
            }
            for rank in range(offset, offset + limit)
        ]

    def lookup(keys, *_args, **_kwargs):
        nonlocal lookup_calls
        lookup_calls += 1
        return [
            {
                "group_id": group_id,
                "media_id": media_id,
                "name": f"{media_id}.pdf",
                "day": "0901",
                "_metadata_match": False,
            }
            for group_id, media_id in keys
        ]

    monkeypatch.setattr(service.search_index, "search", search)
    monkeypatch.setattr(service.db, "ima_documents_by_keys", lookup)

    response = client.get(
        "/api/ima-documents?q=body%20needle&limit=1&offset=2000",
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert [item["media_id"] for item in response.json()["items"]] == ["hit-2000"]
    assert response.json()["has_more"] is True
    assert offsets == list(range(0, 2200, 200))
    assert lookup_calls == 11


def test_ima_documents_offset_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "ima-offset.sqlite"))
    headers = _headers(client, "ima_offset_admin", "IMAOFFSET1", admin=True)

    assert client.get(
        "/api/ima-documents?offset=-1", headers=headers
    ).status_code == 422
    assert client.get(
        "/api/ima-documents?offset=2001", headers=headers
    ).status_code == 422
    accepted = client.get(
        "/api/ima-documents?offset=2000", headers=headers
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["offset"] == 2000


def test_indexed_api_serves_without_reading_json(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "indexed-api.sqlite"))
    admin_headers = _headers(client, "idx_admin", "IDXADM01", admin=True)
    reader_headers = _headers(client, "idx_reader", "IDXREAD1")
    outsider_headers = _headers(client, "idx_out", "IDXOUT01")
    group_a, group_b = _configure_two_groups(client, admin_headers)
    service = client.app.state.ima_documents
    store = service.store
    records = [
        {
            "media_id": "file_ai",
            "name": "AI 展望.pdf",
            "day": "0829",
            "group_id": group_a,
            "abstract": "算力需求",
        },
        {
            "media_id": "file_maotai",
            "name": "调研纪要.pdf",
            "day": "0828",
            "group_id": group_a,
            "abstract": "贵州茅台渠道",
        },
        {
            "media_id": "file_stock",
            "name": "300750 排产.pdf",
            "day": "0827",
            "group_id": group_a,
            "abstract": "宁德时代",
        },
        {
            "media_id": "file_pct",
            "name": "100%_增长.pdf",
            "day": "0826",
            "group_id": group_a,
            "abstract": "含%与_",
        },
        {
            "media_id": "file_unknown",
            "name": "杂项.pdf",
            "day": "unknown",
            "group_id": group_a,
            "abstract": "无日期",
        },
        {
            "media_id": "file_page1",
            "name": "分页甲.pdf",
            "day": "0825",
            "group_id": group_a,
            "abstract": "分页摘要",
        },
        {
            "media_id": "file_page2",
            "name": "分页乙.pdf",
            "day": "0824",
            "group_id": group_a,
            "abstract": "分页摘要",
        },
        {
            "media_id": "file_page3",
            "name": "分页丙.pdf",
            "day": "0823",
            "group_id": group_a,
            "abstract": "分页摘要",
        },
        {
            "media_id": "file_shared",
            "name": "共享A.pdf",
            "day": "0822",
            "group_id": group_a,
            "abstract": "共享文档A",
        },
        {
            "media_id": "file_shared",
            "name": "共享B.pdf",
            "day": "0821",
            "group_id": group_b,
            "abstract": "共享文档B",
        },
        {
            "media_id": "file_macro",
            "name": "宏观周报.pdf",
            "day": "0820",
            "group_id": group_b,
            "abstract": "利率",
        },
    ]
    state = {}
    tags = {
        "file_ai": ["AI"],
        "file_maotai": ["消费"],
        "file_stock": ["新能源"],
        "file_pct": ["宏观"],
        "file_macro": ["宏观"],
        "file_shared": ["共享"],
    }
    for record in records:
        state.update(_seed_indexed_record(store, record, tags=tags.get(record["media_id"], [])))
    store.save_manifest(records)
    store.save_state(state)
    rebuilt = service.rebuild_read_index(service.config().groups)
    assert rebuilt["status"] == "ready"
    assert rebuilt["documents"] == len(records)
    _block_json_readers(store, monkeypatch)

    listed = client.get("/api/ima-documents", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert {item["media_id"] for item in body["items"]} >= {
        "file_ai",
        "file_maotai",
        "file_stock",
        "file_pct",
        "file_unknown",
        "file_macro",
    }
    assert body["items"][0]["media_id"] == "file_ai"
    assert "abstract" not in body["items"][0]
    assert "cover_url" not in body["items"][0]
    assert "pdf_path" not in body["items"][0]
    assert "txt_path" not in body["items"][0]
    assert body["days"] == []
    grouped = client.get(f"/api/ima-documents?group={group_a}", headers=admin_headers)
    assert grouped.status_code == 200, grouped.text
    assert "unknown" in grouped.json()["days"]

    catalog_payload = client.get("/api/ima-documents/catalog", headers=admin_headers)
    assert catalog_payload.status_code == 200, catalog_payload.text
    catalog_body = catalog_payload.json()
    by_id = {group["id"]: group for group in catalog_body["subscribed"]}
    assert by_id[group_a]["document_count"] == 9
    assert by_id[group_a]["latest_media_id"] == "file_ai"
    assert by_id[group_b]["document_count"] == 2
    assert by_id[group_b]["latest_media_id"] == "file_shared"

    detail = client.get("/api/ima-documents/file_ai", headers=admin_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["name"] == "AI 展望.pdf"
    assert detail.json()["abstract"] == "算力需求"
    assert detail.json()["tags"] == ["AI"]

    assert client.get("/api/ima-documents/file_shared", headers=admin_headers).status_code == 404
    shared_a = client.get(
        f"/api/ima-documents/file_shared?group={group_a}", headers=admin_headers
    )
    assert shared_a.status_code == 200
    assert shared_a.json()["name"] == "共享A.pdf"
    shared_b = client.get(
        f"/api/ima-documents/file_shared?group={group_b}", headers=admin_headers
    )
    assert shared_b.status_code == 200
    assert shared_b.json()["name"] == "共享B.pdf"

    tagged = client.get("/api/ima-documents?tag=新能源", headers=admin_headers)
    assert [item["media_id"] for item in tagged.json()["items"]] == ["file_stock"]
    by_day = client.get("/api/ima-documents?day=0829", headers=admin_headers)
    assert [item["media_id"] for item in by_day.json()["items"]] == ["file_ai"]
    unknown = client.get("/api/ima-documents?day=unknown", headers=admin_headers)
    assert [item["media_id"] for item in unknown.json()["items"]] == ["file_unknown"]

    search_ai = client.get("/api/ima-documents?q=AI", headers=admin_headers)
    assert "file_ai" in {item["media_id"] for item in search_ai.json()["items"]}
    search_zh = client.get("/api/ima-documents?q=茅台", headers=admin_headers)
    assert [item["media_id"] for item in search_zh.json()["items"]] == ["file_maotai"]
    search_code = client.get("/api/ima-documents?q=300750", headers=admin_headers)
    assert [item["media_id"] for item in search_code.json()["items"]] == ["file_stock"]
    search_pct = client.get("/api/ima-documents?q=%25", headers=admin_headers)
    assert "file_pct" in {item["media_id"] for item in search_pct.json()["items"]}
    search_us = client.get("/api/ima-documents?q=_", headers=admin_headers)
    assert "file_pct" in {item["media_id"] for item in search_us.json()["items"]}

    page1 = client.get("/api/ima-documents?q=分页摘要&limit=1&offset=0", headers=admin_headers)
    page2 = client.get("/api/ima-documents?q=分页摘要&limit=1&offset=1", headers=admin_headers)
    page3 = client.get("/api/ima-documents?q=分页摘要&limit=1&offset=2", headers=admin_headers)
    assert page1.json()["has_more"] is True
    assert page2.json()["has_more"] is True
    assert page3.json()["has_more"] is False
    page_ids = [
        page1.json()["items"][0]["media_id"],
        page2.json()["items"][0]["media_id"],
        page3.json()["items"][0]["media_id"],
    ]
    assert page_ids == ["file_page1", "file_page2", "file_page3"]

    granted = client.put(
        f"/api/admin/ima-collector/groups/{group_a}/acl",
        headers=admin_headers,
        json={"usernames": ["idx_reader"]},
    )
    assert granted.status_code == 200, granted.text
    reader_list = client.get("/api/ima-documents", headers=reader_headers)
    assert reader_list.status_code == 200
    assert {item["media_id"] for item in reader_list.json()["items"]} == {
        "file_ai",
        "file_maotai",
        "file_stock",
        "file_pct",
        "file_unknown",
        "file_page1",
        "file_page2",
        "file_page3",
        "file_shared",
    }
    assert client.get("/api/ima-documents/file_macro", headers=reader_headers).status_code == 404
    assert client.get("/api/ima-documents/file_ai", headers=reader_headers).status_code == 200
    assert client.post(
        f"/api/ima-documents/groups/{group_a}/subscribe", headers=outsider_headers
    ).status_code == 404
    assert client.get("/api/ima-documents", headers=outsider_headers).json()["items"] == []
    assert client.get("/api/ima-documents/file_ai", headers=outsider_headers).status_code == 404

    status = client.get("/api/admin/ima-collector", headers=admin_headers)
    assert status.status_code == 200, status.text
    index = status.json()["index"]
    blob = json.dumps(index, ensure_ascii=False)
    assert index["status"] == "ready"
    assert "file_ai" not in blob
    assert "算力需求" not in blob
    assert "pdf" not in blob.lower()
    assert "abstract" not in blob
    assert "token" not in blob.lower()
    assert "http" not in blob.lower()


def test_indexed_pdf_and_txt_use_index_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "indexed-pdf.sqlite"))
    admin_headers = _headers(client, "idx_pdf_admin", "IDXPDF01", admin=True)
    group_a, _group_b = _configure_two_groups(client, admin_headers)
    service = client.app.state.ima_documents
    store = service.store
    record = {
        "media_id": "file_pdf",
        "name": "Archive.pdf",
        "day": "0829",
        "group_id": group_a,
        "abstract": "正文摘要",
    }
    store.save_manifest([record])
    store.save_state(_seed_indexed_record(store, record, txt="indexed text"))
    assert service.rebuild_read_index(service.config().groups)["status"] == "ready"
    _block_json_readers(store, monkeypatch)

    pdf = client.get("/api/ima-documents/file_pdf/pdf", headers=admin_headers)
    txt = client.get("/api/ima-documents/file_pdf/text", headers=admin_headers)
    assert pdf.status_code == 200, pdf.text
    assert pdf.content.startswith(b"%PDF")
    assert txt.status_code == 200, txt.text
    assert txt.text == "indexed text"


def test_indexed_api_no_json_read_stays_stable_across_repeated_queries(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "indexed-repeat.sqlite"))
    admin_headers = _headers(client, "idx_repeat_admin", "IDXREP01", admin=True)
    group_a, _group_b = _configure_two_groups(client, admin_headers)
    service = client.app.state.ima_documents
    store = service.store
    records = [
        {
            "media_id": "file_repeat_ai",
            "name": "AI 展望.pdf",
            "day": "0829",
            "group_id": group_a,
            "abstract": "算力需求",
        },
        {
            "media_id": "file_repeat_energy",
            "name": "新能源跟踪.pdf",
            "day": "0828",
            "group_id": group_a,
            "abstract": "排产",
        },
    ]
    state = {}
    for record, tags in ((records[0], ["AI"]), (records[1], ["新能源"])):
        state.update(_seed_indexed_record(store, record, tags=tags))
    store.save_manifest(records)
    store.save_state(state)
    assert service.rebuild_read_index(service.config().groups)["status"] == "ready"
    _block_json_readers(store, monkeypatch)
    routes = (
        "/api/ima-documents/catalog",
        "/api/ima-documents?limit=50&offset=0",
        "/api/ima-documents?q=新能源&limit=50&offset=0",
        "/api/ima-documents?q=AI&limit=50&offset=0",
        f"/api/ima-documents?group={group_a}&limit=50&offset=0",
    )
    for _ in range(20):
        for route in routes:
            response = client.get(route, headers=admin_headers)
            assert response.status_code == 200, response.text

