import json

import pytest
from fastapi.testclient import TestClient

from app.db import DB
from app.ima_documents import (
    ImaDocumentService,
    _prepare_discovery_item,
)
from app.main import create_app
from tests.test_ima_documents import _headers

MARKER = ".vpush-local-library.json"
SIDECAR = ".vpush-local-meta.jsonl"


def _service(tmp_path):
    db = DB(tmp_path / "db.sqlite")
    archive = tmp_path / "archive"
    archive.mkdir(exist_ok=True)
    (archive / ".vpush-ima-root").touch()
    service = ImaDocumentService(db, tmp_path / "index", archive_root=archive)
    return service, archive


def _make_library(
    archive,
    slug="demo",
    name="内部纪要",
    enabled=True,
    tags=None,
    pdfs=(),
    sidecar=(),
    marker_text=None,
):
    lib = archive / "local" / slug
    lib.mkdir(parents=True, exist_ok=True)
    if marker_text is not None:
        (lib / MARKER).write_text(marker_text, encoding="utf-8")
    else:
        (lib / MARKER).write_text(
            json.dumps({"name": name, "enabled": enabled, "tags": tags or []}, ensure_ascii=False),
            encoding="utf-8",
        )
    for rel in pdfs:
        path = lib / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.7 fake")
    if sidecar:
        lines = "\n".join(json.dumps(row, ensure_ascii=False) for row in sidecar)
        (lib / SIDECAR).write_text(lines + "\n", encoding="utf-8")
    return lib


def _index_group_ids(store):
    return {
        str(record.get("group_id") or "")
        for record in store.load_manifest()
    }


def test_scan_ignores_directory_without_marker(tmp_path):
    service, archive = _service(tmp_path)
    (archive / "local" / "no-marker").mkdir(parents=True)
    (archive / "local" / "no-marker" / "a.pdf").write_bytes(b"%PDF")
    _make_library(archive, pdfs=["0830/纪要.pdf"])

    result = service.scan_local_libraries()

    assert result["status"] == "finished"
    assert [item["slug"] for item in result["libraries"]] == ["demo"]
    assert result["libraries"][0]["pdf_count"] == 1
    assert service.store.load_manifest()[0]["group_id"] == "local-demo"


def test_scan_ignores_broken_marker_json(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, slug="broken", marker_text="{not json", pdfs=["a.pdf"])

    result = service.scan_local_libraries()

    assert result["status"] == "finished"
    assert result["libraries"] == []
    assert service.store.load_manifest() == []


def test_scan_injects_sidecar_abstract_tags_and_day(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(
        archive,
        slug="cicc",
        name="中金点睛",
        tags=["中金研报"],
        pdfs=["宏观/0829/策略点评_398682.pdf", "宏观/0829/无摘要_1.pdf"],
        sidecar=[
            {
                "id": "398682",
                "title": "策略点评",
                "summary": "这是官方摘要",
                "tags": ["中金研报", "宏观"],
                "day": "0829",
                "authors": ["某人"],
            }
        ],
    )

    result = service.scan_local_libraries()

    assert result["status"] == "finished"
    manifest = {item["name"]: item for item in service.store.load_manifest()}
    assert set(manifest) == {"策略点评_398682", "无摘要_1"}
    hit = manifest["策略点评_398682"]
    missing = manifest["无摘要_1"]
    assert hit["abstract"] == "这是官方摘要"
    assert missing["abstract"] == ""
    assert hit["day"] == "0829" and missing["day"] == "0829"
    assert hit["group_id"] == "local-cicc" and hit["group_name"] == "中金点睛"
    assert hit["media_id"].startswith("loc") and len(hit["media_id"]) == 23
    state = service.store.load_state()
    tags_hit = state[service.store.state_key(hit)]["tags"]
    tags_missing = state[service.store.state_key(missing)]["tags"]
    # sidecar tags 与库级 tags 合并去重；未命中行只挂库级 tags
    assert tags_hit == ["中金研报", "宏观"]
    assert tags_missing == ["中金研报"]
    assert state[service.store.state_key(hit)]["pdf"].startswith("local/cicc/")


def test_scan_day_prefers_deepest_mmdd_directory(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, pdfs=["0801/0830/深.pdf", "0801/浅.pdf", "根.pdf"])

    service.scan_local_libraries()

    days = {item["name"]: item["day"] for item in service.store.load_manifest()}
    assert days == {"深": "0830", "浅": "0801", "根": "unknown"}


def test_scan_replaces_rows_when_pdf_deleted(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, pdfs=["a.pdf", "b.pdf"])
    service.scan_local_libraries()
    assert len(service.store.load_manifest()) == 2

    (archive / "local" / "demo" / "a.pdf").unlink()
    result = service.scan_local_libraries()

    assert result["libraries"][0]["pdf_count"] == 1
    assert [item["name"] for item in service.store.load_manifest()] == ["b"]
    assert service.db.ima_document_index_count() == 1
    state = service.store.load_state()
    assert len(service.store.local_group_state_keys(state, "local-demo")) == 1


def test_scan_reports_invalid_slug(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, slug="Bad_Slug", pdfs=["a.pdf"])

    result = service.scan_local_libraries()

    assert "slug" in result["libraries"][0]["error"]
    assert service.store.load_manifest() == []


def test_scan_conflict_with_existing_group_reports_error(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, slug="clash", pdfs=["b.pdf"])

    # 正常配置读入时 local- 前缀组已被 _read_groups 拒收，这里直接验证扫描器的冲突契约
    result = service.store.scan_local_libraries(existing_group_ids={"local-clash"})

    assert "冲突" in result["libraries"][0]["error"]
    assert result["libraries"][0]["records"] == []


def test_scan_skips_symlink_escape(tmp_path):
    service, archive = _service(tmp_path)
    secret = tmp_path / "secret.pdf"
    secret.write_bytes(b"%PDF secret")
    lib = _make_library(archive, pdfs=["ok.pdf"])
    (lib / "leak.pdf").symlink_to(secret)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "nested.pdf").write_bytes(b"%PDF nested")
    (lib / "dirlink").symlink_to(outside, target_is_directory=True)

    service.scan_local_libraries()

    names = {item["name"] for item in service.store.load_manifest()}
    assert names == {"ok"}
    state = service.store.load_state()
    assert not any("secret" in str(item.get("pdf")) for item in state.values())


def test_scan_removes_disappeared_library(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, slug="gone", pdfs=["a.pdf"])
    _make_library(archive, slug="stay", pdfs=["b.pdf"])
    service.scan_local_libraries()
    assert _index_group_ids(service.store) == {"local-gone", "local-stay"}

    import shutil

    shutil.rmtree(archive / "local" / "gone")
    service.scan_local_libraries()

    assert _index_group_ids(service.store) == {"local-stay"}
    assert service.db.ima_document_index_count() == 1
    # ACL 行不受库消失影响（本用例没有 ACL 行，只要组行被清掉即可）


def test_set_enabled_writes_marker_and_updates_status(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, enabled=True)

    service.scan_local_libraries()
    status = service.set_local_library_enabled("demo", False)

    marker = json.loads((archive / "local" / "demo" / MARKER).read_text(encoding="utf-8"))
    assert marker["enabled"] is False
    assert status["libraries"][0]["enabled"] is False

    with pytest.raises(ValueError):
        service.set_local_library_enabled("missing", True)
    _make_library(archive, slug="bad", marker_text="{oops")
    with pytest.raises(ValueError):
        service.set_local_library_enabled("bad", True)


def test_restore_original_filenames_keeps_local_files(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, pdfs=["0830/纪要_1.pdf"])
    service.scan_local_libraries()
    pdf = archive / "local" / "demo" / "0830" / "纪要_1.pdf"
    assert pdf.is_file()

    service.store.restore_original_filenames()

    assert pdf.is_file()
    state = service.store.load_state()
    item = next(iter(state.values()))
    assert item["pdf"] == "local/demo/0830/纪要_1.pdf"


def test_discovery_skips_local_prefix_groups():
    assert (
        _prepare_discovery_item(
            {"id": "local-demo", "basic_info": {"name": "x"}}
        )
        is None
    )


def test_sync_once_runs_local_scan_without_ima_credentials(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, pdfs=["a.pdf"])

    result = service.sync_once()

    assert result["status"] == "not_configured"
    assert [item["name"] for item in service.store.load_manifest()] == ["a"]


def test_local_library_visibility_reading_and_disable(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "app.sqlite"))
    admin_headers = _headers(client, "local_admin", "LOCADM1", admin=True)
    user_headers = _headers(client, "local_user", "LOCUSR1")
    archive = tmp_path / "ima"  # 未设 IMA_ARCHIVE_ROOT 时 archive_root=index 根
    _make_library(
        archive,
        slug="cicc",
        name="中金点睛",
        enabled=True,
        tags=["中金研报"],
        pdfs=["0829/研报_398682.pdf"],
        sidecar=[{"id": "398682", "summary": "官方摘要词", "tags": ["宏观"]}],
    )
    service = client.app.state.ima_documents

    # 管理员列表 + 扫描
    listed = client.get("/api/admin/ima-local-libraries", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["libraries"] == []
    scanned = client.post("/api/admin/ima-local-libraries/scan", headers=admin_headers)
    assert scanned.status_code == 200, scanned.text
    body = scanned.json()
    assert body["status"] == "finished"
    assert body["libraries"][0]["slug"] == "cicc"
    assert body["libraries"][0]["pdf_count"] == 1
    assert body["libraries"][0]["enabled"] is True

    # 走一次全量重建，让 SQLite 读模型路径生效
    service._rebuild_index_if_needed()
    assert service.read_index_status()["status"] == "ready"

    # 未授权用户不可见
    assert client.get("/api/ima-documents", headers=user_headers).json()["items"] == []
    outsider_catalog = client.get("/api/ima-documents/catalog", headers=user_headers).json()
    assert outsider_catalog["subscribed"] == [] and outsider_catalog["available"] == []

    # 授权 + 订阅后可见、可读、摘要可搜
    granted = client.put(
        "/api/admin/ima-collector/groups/local-cicc/acl",
        headers=admin_headers,
        json={"usernames": ["local_user"]},
    )
    assert granted.status_code == 200, granted.text
    assert client.post(
        "/api/ima-documents/groups/local-cicc/subscribe", headers=user_headers
    ).status_code == 200
    listed = client.get("/api/ima-documents", headers=user_headers)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1 and items[0]["group_id"] == "local-cicc"
    media_id = items[0]["media_id"]
    found = client.get("/api/ima-documents", headers=user_headers, params={"q": "官方摘要词"})
    assert found.json()["document_count"] == 1
    detail = client.get(
        f"/api/ima-documents/{media_id}", headers=user_headers, params={"group": "local-cicc"}
    )
    assert detail.status_code == 200
    assert detail.json()["abstract"] == "官方摘要词"
    assert detail.json()["tags"] == ["宏观", "中金研报"]
    pdf = client.get(
        f"/api/ima-documents/{media_id}/pdf", headers=user_headers, params={"group": "local-cicc"}
    )
    assert pdf.status_code == 200

    # 管理员停用后普通用户立即不可见，ACL 保留
    toggled = client.put(
        "/api/admin/ima-local-libraries/cicc/enabled",
        headers=admin_headers,
        json={"enabled": False},
    )
    assert toggled.status_code == 200
    assert toggled.json()["libraries"][0]["enabled"] is False
    assert client.get("/api/ima-documents", headers=user_headers).json()["items"] == []
    assert (
        client.get(
            f"/api/ima-documents/{media_id}",
            headers=user_headers,
            params={"group": "local-cicc"},
        ).status_code
        == 404
    )
    reenabled = client.put(
        "/api/admin/ima-local-libraries/cicc/enabled",
        headers=admin_headers,
        json={"enabled": True},
    )
    assert reenabled.status_code == 200
    assert client.get("/api/ima-documents", headers=user_headers).json()["items"]

    # 非管理员访问管理端点被拒
    assert (
        client.get("/api/admin/ima-local-libraries", headers=user_headers).status_code == 403
    )
    assert (
        client.post("/api/admin/ima-local-libraries/scan", headers=user_headers).status_code
        == 403
    )


def test_collector_rejects_local_prefix_group_id(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "app.sqlite"))
    admin_headers = _headers(client, "collector_admin", "COLADM1", admin=True)
    response = client.put(
        "/api/admin/ima-collector",
        headers=admin_headers,
        json={
            "groups": [
                {
                    "id": "local-hijack",
                    "name": "伪装组",
                    "knowledge_base_id": "kb",
                    "root_folder_id": "root",
                    "enabled": True,
                }
            ]
        },
    )
    assert response.status_code == 400
    assert "local-" in response.json()["detail"]


def test_enabled_toggle_reports_write_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    db_path = tmp_path / "app.sqlite"
    client = TestClient(create_app(db_path=db_path))
    admin_headers = _headers(client, "toggle_admin", "TOGADM1", admin=True)
    archive = tmp_path / "ima"
    _make_library(archive, slug="ro", enabled=False, pdfs=["a.pdf"])
    assert (
        client.post("/api/admin/ima-local-libraries/scan", headers=admin_headers).status_code
        == 200
    )
    marker = archive / "local" / "ro" / MARKER
    lib_dir = archive / "local" / "ro"
    # 写入是“临时文件 + rename”，所以目录不可写才会失败（对应属主/权限配错的场景）
    lib_dir.chmod(0o500)
    try:
        response = client.put(
            "/api/admin/ima-local-libraries/ro/enabled",
            headers=admin_headers,
            json={"enabled": True},
        )
        assert response.status_code == 502
        assert "标记文件写入失败" in response.json()["detail"]
    finally:
        lib_dir.chmod(0o755)
    status = client.get(
        "/api/admin/ima-local-libraries", headers=admin_headers
    ).json()["libraries"][0]
    assert status["enabled"] is False
    assert json.loads(marker.read_text(encoding="utf-8"))["enabled"] is False
