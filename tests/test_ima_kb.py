from fastapi.testclient import TestClient

from app.db import DB
from app.ima_documents import (
    ImaDocumentConfig,
    ImaDocumentService,
    ImaDocumentStore,
    ImaGroupConfig,
    ImaPureClient,
    ima_kb_valid_tags,
    purge_ima_document_tags,
)
from app.stock_universe import bundled_plain_names
from app.ima_kb import catalog, readable_group_ids
from app.main import create_app
from app.tagging import tag_text
from tests.test_ima_documents import _headers


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
        "day": "0826",
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
