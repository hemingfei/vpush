from fastapi.testclient import TestClient

from app.db import DB
from app.ima_documents import ImaGroupConfig
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
