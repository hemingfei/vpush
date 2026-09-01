import json

import pytest
from fastapi.testclient import TestClient

from app.db import DB
from app.ima_documents import (
    ImaDocumentService,
    ImaGroupConfig,
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
    # 根级隐藏目录（如 .cicc 控制目录）不当成异常库
    (archive / "local" / ".cicc").mkdir(parents=True)
    _make_library(archive, pdfs=["0830/纪要.pdf"])

    result = service.scan_local_libraries()

    assert result["status"] == "finished"
    assert [item["slug"] for item in result["libraries"]] == ["demo"]
    assert result["libraries"][0]["pdf_count"] == 1
    assert service.store.load_manifest()[0]["group_id"] == "local-demo"


def test_scan_broken_marker_reports_error_and_keeps_old_index(tmp_path):
    """先成功扫描→标记损坏→重扫：该组保留旧索引行且管理页能看到 error（B1）。"""
    service, archive = _service(tmp_path)
    _make_library(archive, slug="broken", pdfs=["a.pdf"])
    service.scan_local_libraries()
    assert [item["name"] for item in service.store.load_manifest()] == ["a"]

    (archive / "local" / "broken" / MARKER).write_text("{not json", encoding="utf-8")
    result = service.scan_local_libraries()

    assert result["status"] == "finished"
    assert result["libraries"][0]["slug"] == "broken"
    assert "JSON" in result["libraries"][0]["error"]
    # prune keep 集合保住该组，索引/manifest 不再被静默清空
    assert [item["name"] for item in service.store.load_manifest()] == ["a"]
    assert service.db.ima_document_index_count() == 1
    state = service.store.load_state()
    assert len(service.store.local_group_state_keys(state, "local-broken")) == 1


def test_scan_unreadable_directory_keeps_old_index(tmp_path):
    """库目录不可读：os.walk onerror 记录后带 error 返回，旧组数据保留（与 B1 同语义）。"""
    service, archive = _service(tmp_path)
    lib = _make_library(archive, pdfs=["ok.pdf"])
    service.scan_local_libraries()
    assert service.db.ima_document_index_count() == 1

    locked = lib / "locked"
    locked.mkdir()
    (locked / "hidden.pdf").write_bytes(b"%PDF-1.7")
    locked.chmod(0o300)  # 无读权限：readdir 失败（root 下无效，跳过断言）
    try:
        result = service.scan_local_libraries()
    finally:
        locked.chmod(0o755)
    if not result["libraries"][0]["error"]:
        pytest.skip("运行环境忽略目录读权限（root）")

    assert "不可读" in result["libraries"][0]["error"]
    assert [item["name"] for item in service.store.load_manifest()] == ["ok"]
    assert service.db.ima_document_index_count() == 1


def test_scan_rescan_keeps_abstract_zh(tmp_path):
    """重扫后 state 合并结果原地写回内存，索引行 abstract_zh 不再被清空（B3）。"""
    service, archive = _service(tmp_path)
    _make_library(archive, pdfs=["a.pdf"])
    service.scan_local_libraries()

    state = service.store.load_state()
    key = next(iter(state))
    state[key]["abstract_zh"] = "中文摘要"
    state[key]["abstract_src_hash"] = "hash-1"
    service.store.save_state(state)

    service.scan_local_libraries()

    assert service.store.load_state()[key]["abstract_zh"] == "中文摘要"
    media_id = service.store.load_manifest()[0]["media_id"]
    indexed = service.db.ima_document_from_index(media_id, ["local-demo"], "local-demo")
    assert indexed["abstract_zh"] == "中文摘要"
    assert indexed["abstract_src_hash"] == "hash-1"


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


def test_sidecar_tags_capped_to_spec_limits(tmp_path):
    """sidecar tags 裁剪：≤5 个、单条 ≤40 字符；库级 tags 仍在其后合并去重。"""
    service, archive = _service(tmp_path)
    _make_library(
        archive,
        slug="capped",
        tags=["库级"],
        pdfs=["a_1.pdf", "b_2.pdf"],
        sidecar=[
            {"id": "1", "tags": [f"标签{i}" for i in range(8)]},
            {"id": "2", "tags": ["x" * 50, "正常"]},
        ],
    )

    service.scan_local_libraries()

    state = service.store.load_state()
    by_name = {item["name"]: item for item in state.values()}
    assert by_name["a_1"]["tags"] == ["标签0", "标签1", "标签2", "标签3", "标签4", "库级"]
    assert by_name["b_2"]["tags"] == ["x" * 40, "正常", "库级"]


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
    assert service._index_usable() is True
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


def test_update_local_library_meta_writes_marker_and_status(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(archive, name="旧名", tags=["旧标签"])
    service.scan_local_libraries()

    status = service.update_local_library_meta(
        "demo", name=" 新名 ", tags=["研报", " 中金 ", "研报", ""]
    )

    marker = json.loads((archive / "local" / "demo" / MARKER).read_text(encoding="utf-8"))
    assert marker["name"] == "新名"
    # tags 去重、去空白，空项剔除
    assert marker["tags"] == ["研报", "中金"]
    item = status["libraries"][0]
    assert item["name"] == "新名" and item["tags"] == ["研报", "中金"]
    # settings 缓存同步（下次 local_scan_status 直接可读）
    cached = service.local_scan_status()["libraries"][0]
    assert cached["name"] == "新名" and cached["tags"] == ["研报", "中金"]

    with pytest.raises(ValueError):
        service.update_local_library_meta("missing", name="任意")
    with pytest.raises(ValueError):
        service.update_local_library_meta("demo", name="  ")
    with pytest.raises(ValueError):
        service.update_local_library_meta("demo", name="x" * 81)


def test_create_local_library_makes_dir_marker_and_scans(tmp_path):
    service, archive = _service(tmp_path)

    result = service.create_local_library("papers", "论文库", tags=["研报"])

    assert result["status"] == "finished"
    assert result["libraries"][0]["slug"] == "papers"
    assert result["libraries"][0]["pdf_count"] == 0
    assert result["libraries"][0]["enabled"] is False
    marker = json.loads((archive / "local" / "papers" / MARKER).read_text(encoding="utf-8"))
    assert marker == {"name": "论文库", "enabled": False, "tags": ["研报"]}

    with pytest.raises(FileExistsError):
        service.create_local_library("papers", "重复")
    with pytest.raises(ValueError):
        service.create_local_library("Bad_Slug", "非法 slug")
    with pytest.raises(ValueError):
        service.create_local_library("ok-slug", "")
    # tags 带出扫描 summary
    listed = service.local_scan_status()["libraries"][0]
    assert listed["tags"] == ["研报"]


def test_local_library_admin_meta_create_acl_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "app.sqlite"))
    admin_headers = _headers(client, "meta_admin", "METADM1", admin=True)
    user_headers = _headers(client, "meta_user", "METUSR1")

    # 网页建库：建目录 + 写标记 + 扫描出现在列表
    created = client.post(
        "/api/admin/ima-local-libraries",
        headers=admin_headers,
        json={"slug": "papers", "name": "论文库", "tags": ["研报"]},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["libraries"][0]["slug"] == "papers"

    # 列表带 tags 与 acl_usernames
    listed = client.get("/api/admin/ima-local-libraries", headers=admin_headers)
    item = listed.json()["libraries"][0]
    assert item["tags"] == ["研报"]
    assert item["acl_usernames"] == []

    # 授权 + 改名/改标签
    granted = client.put(
        "/api/admin/ima-collector/groups/local-papers/acl",
        headers=admin_headers,
        json={"usernames": ["meta_user"]},
    )
    assert granted.status_code == 200, granted.text
    updated = client.put(
        "/api/admin/ima-local-libraries/papers",
        headers=admin_headers,
        json={"name": "论文库二", "tags": ["研报", "论文"]},
    )
    assert updated.status_code == 200, updated.text
    item = updated.json()["libraries"][0]
    assert item["name"] == "论文库二" and item["tags"] == ["研报", "论文"]

    listed = client.get("/api/admin/ima-local-libraries", headers=admin_headers)
    item = listed.json()["libraries"][0]
    assert item["acl_usernames"] == ["meta_user"]
    # 扫描/改名响应也要带授权，避免保存后立刻扫描把卡片冲成「仅管理员」
    assert updated.json()["libraries"][0]["acl_usernames"] == ["meta_user"]
    scanned = client.post("/api/admin/ima-local-libraries/scan", headers=admin_headers)
    assert scanned.status_code == 200, scanned.text
    assert scanned.json()["libraries"][0]["acl_usernames"] == ["meta_user"]

    # 错误路径：重复建库 409；非法 slug/name 400；空更新 400；库不存在 404
    assert (
        client.post(
            "/api/admin/ima-local-libraries",
            headers=admin_headers,
            json={"slug": "papers", "name": "重复"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/admin/ima-local-libraries",
            headers=admin_headers,
            json={"slug": "Bad_Slug", "name": "x"},
        ).status_code
        == 400
    )
    assert (
        client.put(
            "/api/admin/ima-local-libraries/papers",
            headers=admin_headers,
            json={},
        ).status_code
        == 400
    )
    missing = client.put(
        "/api/admin/ima-local-libraries/nope",
        headers=admin_headers,
        json={"name": "任意"},
    )
    assert missing.status_code == 404
    # name 非法是 400（参数错误），与库不存在的 404 区分
    invalid_name = client.put(
        "/api/admin/ima-local-libraries/papers",
        headers=admin_headers,
        json={"name": "x" * 81},
    )
    assert invalid_name.status_code == 400

    # 非管理员不可用新端点
    assert (
        client.post(
            "/api/admin/ima-local-libraries",
            headers=user_headers,
            json={"slug": "x", "name": "x"},
        ).status_code
        == 403
    )


# ---- 跨年排序键 sort_date（fix/kb-sort-date）----


def _make_mixed_stream(service, archive):
    """一个 IMA 组（day=0830）+ 一个本地库（2026-08-30 与 2025-12-31 各一篇）。"""
    ima_record = {
        "group_id": "semi",
        "group_name": "SemiAnalysis",
        "media_id": "file_ima",
        "name": "B_ima",
        "day": "0830",
    }
    service.store.save_group_manifest("semi", [ima_record])
    service.store.save_state({service.store.state_key(ima_record): {"pdf": "semi/ima.pdf"}})
    _make_library(
        archive,
        slug="cicc",
        name="中金点睛",
        pdfs=["宏观/0830/A_local_101.pdf", "宏观/1231/C_dec_102.pdf"],
        sidecar=[
            {"id": "101", "publish": "2026-08-30", "day": "0830"},
            {"id": "102", "publish": "2025-12-31", "day": "1231"},
        ],
    )
    service.scan_local_libraries()
    service.rebuild_read_index()
    return (
        ImaGroupConfig("semi", "SemiAnalysis", "kb", "root"),
        ImaGroupConfig("local-cicc", "中金点睛", "", ""),
    )


def test_latest_stream_orders_by_pub_date_across_years(tmp_path):
    """2025-12 尾巴不再压住 2026-08 新研报：按 sort_date（YYYY-MM-DD）排序。"""
    service, archive = _service(tmp_path)
    groups = _make_mixed_stream(service, archive)

    page = service.list_documents(groups)

    # 两篇 2026-08-30 同键，按 name DESC；2025-12-31 沉底（关键断言）
    assert [item["name"] for item in page["items"]] == ["B_ima", "A_local_101", "C_dec_102"]
    # day 展示仍是 MMDD 桶，接口响应结构不变
    assert [item["day"] for item in page["items"]] == ["0830", "0830", "1231"]
    manifest = {item["name"]: item for item in service.store.load_manifest()}
    assert manifest["A_local_101"]["pub_date"] == "2026-08-30"
    assert manifest["C_dec_102"]["pub_date"] == "2025-12-31"
    state = service.store.load_state()
    assert state[service.store.state_key(manifest["A_local_101"])]["pub_date"] == "2026-08-30"


def test_days_facets_keep_mmdd_buckets(tmp_path):
    """跨组浏览不算日期面；单组仍是 MMDD 桶。"""
    service, archive = _service(tmp_path)
    groups = _make_mixed_stream(service, archive)

    page = service.list_documents(groups)
    assert page["days"] == []

    single = service.list_documents((groups[1],))
    assert single["days"] == ["1231", "0830"]


def test_unknown_day_document_sinks_to_bottom(tmp_path):
    service, archive = _service(tmp_path)
    _make_library(
        archive,
        slug="cicc",
        name="中金点睛",
        pdfs=["0830/有日期_201.pdf", "无日期_202.pdf"],
        sidecar=[{"id": "201", "publish": "2026-08-30", "day": "0830"}],
    )
    service.scan_local_libraries()
    service.rebuild_read_index()

    page = service.list_documents((ImaGroupConfig("local-cicc", "中金点睛", "", ""),))

    assert [item["name"] for item in page["items"]] == ["有日期_201", "无日期_202"]
    # days 桶维持既有语义：MMDD 在前，unknown 桶沉底
    assert page["days"] == ["0830", "unknown"]


def test_json_fallback_matches_index_order(tmp_path, monkeypatch):
    """JSON 回退与 SQLite 读模型用同一排序键，顺序一致（性能规格 §10.1）。"""
    service, archive = _service(tmp_path)
    groups = _make_mixed_stream(service, archive)
    indexed = service.list_documents(groups)

    monkeypatch.setattr(service, "_index_usable", lambda: False)
    fallback = service.list_documents(groups)

    assert [item["name"] for item in fallback["items"]] == [
        item["name"] for item in indexed["items"]
    ]
    assert indexed["days"] == []
    assert fallback["days"] == ["1231", "0830"]


def test_sidecar_invalid_publish_left_empty_and_sinks(tmp_path):
    """sidecar publish 非法 → pub_date 留空 → 排序沉底，扫描不抛错。"""
    service, archive = _service(tmp_path)
    _make_library(
        archive,
        slug="cicc",
        name="中金点睛",
        pdfs=["宏观/0830/正常_301.pdf", "宏观/0831/坏日期_302.pdf"],
        sidecar=[
            {"id": "301", "publish": "2026-08-30", "day": "0830"},
            {"id": "302", "publish": "2025/12/31", "day": "0831"},
        ],
    )
    result = service.scan_local_libraries()  # 不抛错
    assert result["status"] == "finished"

    manifest = {item["name"]: item for item in service.store.load_manifest()}
    assert manifest["正常_301"]["pub_date"] == "2026-08-30"
    assert manifest["坏日期_302"]["pub_date"] == ""

    service.rebuild_read_index()
    page = service.list_documents((ImaGroupConfig("local-cicc", "中金点睛", "", ""),))
    # 坏日期文档虽有更新的 0831 目录，仍按 pub_date 语义沉底
    assert [item["name"] for item in page["items"]] == ["正常_301", "坏日期_302"]
