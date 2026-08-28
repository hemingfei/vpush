import json
import threading

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
from app.ima_kb import attach_catalog_stats, catalog, readable_group_ids
from app.main import create_app
from app.stock_universe import bundled_plain_names
from app.tagging import tag_text
from tests.test_ima_documents import _headers


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
    assert db.ima_kb_can_read(user_id, "banking") is False
    db.ima_kb_subscribe(user_id, "banking")
    assert db.ima_kb_can_read(user_id, "banking") is True
    db.set_ima_kb_acl("banking", [])
    assert db.ima_kb_can_read(user_id, "banking") is False
    assert db.ima_kb_is_subscribed(user_id, "banking") is False
    db.set_ima_kb_acl("banking", [user_id])
    db.ima_kb_subscribe(user_id, "banking")
    db.set_ima_kb_acl_for_user(user_id, ["macro"])
    assert db.ima_kb_group_ids_for_user(user_id) == ["macro"]
    assert db.ima_kb_subscribed_group_ids_for_user(user_id) == []
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
    assert [g["id"] for g in listed["available"]] == ["banking"]
    assert listed["subscribed"] == []
    db.ima_kb_subscribe(user_id, "banking")
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
    assert [g["id"] for g in catalog_payload["available"]]
    assert "acl_usernames" not in catalog_payload["available"][0]
    admin_catalog = client.get("/api/ima-documents/catalog", headers=admin_headers).json()
    admin_group = next(g for g in admin_catalog["subscribed"] if g["id"] == group_id)
    assert "reader" in admin_group["acl_usernames"]
    assert client.get("/api/ima-documents/file_abc", headers=user_headers).status_code == 404
    assert client.post(
        f"/api/ima-documents/groups/{group_id}/subscribe", headers=user_headers
    ).status_code == 200
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
    assert any(g["id"] == group_id for g in catalog["available"])
    assert client.post(
        f"/api/ima-documents/groups/{group_id}/subscribe", headers=user_headers
    ).status_code == 200
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


def test_list_ima_documents_defaults_to_latest_day_and_pages_search(tmp_path, monkeypatch):
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
    assert body["day"] == "0826"
    assert [item["media_id"] for item in body["items"]] == ["file_new"]
    assert "abstract" not in body["items"][0]
    assert "cover_url" not in body["items"][0]
    assert body["has_more"] is False
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

        def list_items(self, folder_id):
            assert self.group.knowledge_base_id == "kb-new"
            if self.fail_listing:
                raise RuntimeError("IMA list failed")
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
