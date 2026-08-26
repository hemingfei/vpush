import base64
import json
import logging
import time

import pytest
from fastapi.testclient import TestClient

from app.ima_documents import (
    IMA_LEGACY_GROUP_ID,
    IMA_LEGACY_GROUP_NAME,
    IMA_PURE_GROUPS_KEY,
    IMA_PURE_LAST_RESULT_KEY,
    IMA_PURE_REFRESH_TOKEN_KEY,
    ImaDocumentConfig,
    ImaDocumentService,
    ImaDocumentStore,
    ImaGroupConfig,
    ImaPureClient,
    merge_groups,
    normalize_discovered_groups,
    _safe_error,
    decrypt_body,
    encrypt_body,
)
from app.main import create_app


class FakeDB:
    def __init__(self, values=None):
        self.values = values or {}

    def get_setting(self, key):
        return self.values.get(key)

    def set_setting(self, key, value):
        self.values[key] = value


def test_default_config_targets_august_folder():
    cfg = ImaDocumentConfig.from_db(FakeDB())
    assert cfg.uid == "001aa361168019ef"
    assert cfg.knowledge_base_id == "7464369361259867"
    assert cfg.root_folder_id == "folder_7489327974078249"
    assert cfg.interval_seconds == 3600


def test_public_config_never_returns_refresh_token():
    cfg = ImaDocumentConfig(refresh_token="secret-token")
    public = cfg.public()
    assert public["refresh_token"]["set"] is True
    assert "secret-token" not in str(public)


def test_config_migrates_legacy_single_group():
    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb-old",
            "ima_pure_root_folder_id": "folder-old",
        }
    )
    cfg = ImaDocumentConfig.from_db(db)
    assert len(cfg.groups) == 1
    assert cfg.groups[0].name == "IMA 文档"
    assert cfg.groups[0].knowledge_base_id == "kb-old"
    assert cfg.groups[0].root_folder_id == "folder-old"
    assert cfg.groups[0].source == "manual"


def test_persisted_legacy_group_tracks_updated_scalar_paths():
    db = FakeDB(
        {
            IMA_PURE_GROUPS_KEY: json.dumps(
                [
                    {
                        "id": IMA_LEGACY_GROUP_ID,
                        "name": "IMA 文档",
                        "knowledge_base_id": "old-kb",
                        "root_folder_id": "old-root",
                        "enabled": True,
                        "source": "manual",
                    },
                    {
                        "id": "manual-other",
                        "name": "其他群组",
                        "knowledge_base_id": "other-kb",
                        "root_folder_id": "other-root",
                        "enabled": True,
                        "source": "manual",
                    },
                ],
                ensure_ascii=False,
            ),
            "ima_pure_knowledge_base_id": "new-kb",
            "ima_pure_root_folder_id": "new-root",
        }
    )
    cfg = ImaDocumentConfig.from_db(db)
    assert [(group.id, group.knowledge_base_id, group.root_folder_id) for group in cfg.groups] == [
        (IMA_LEGACY_GROUP_ID, "new-kb", "new-root"),
        ("manual-other", "other-kb", "other-root"),
    ]
    client = ImaPureClient(cfg)
    assert client.effective_knowledge_base_id == "new-kb"
    assert client.effective_root_folder_id == "new-root"


def test_config_reads_group_registry_without_exposing_token():
    db = FakeDB(
        {
            "ima_pure_refresh_token": "refresh-secret",
            IMA_PURE_GROUPS_KEY: json.dumps(
                [
                    {
                        "id": "banking",
                        "name": "投行研报",
                        "knowledge_base_id": "kb-1",
                        "root_folder_id": "folder-1",
                        "enabled": True,
                        "source": "discovered",
                    }
                ],
                ensure_ascii=False,
            ),
        }
    )
    public = ImaDocumentConfig.from_db(db).public()
    assert public["groups"] == [
        {
            "id": "banking",
            "name": "投行研报",
            "knowledge_base_id": "kb-1",
            "root_folder_id": "folder-1",
            "enabled": True,
            "source": "discovered",
        }
    ]
    assert "refresh-secret" not in json.dumps(public)


def test_config_ignores_malformed_group_registry_and_uses_legacy_group():
    db = FakeDB(
        {
            IMA_PURE_GROUPS_KEY: "not-json",
            "ima_pure_knowledge_base_id": "kb-old",
            "ima_pure_root_folder_id": "folder-old",
        }
    )
    cfg = ImaDocumentConfig.from_db(db)
    assert IMA_PURE_GROUPS_KEY == "ima_pure_groups"
    assert [group.knowledge_base_id for group in cfg.groups] == ["kb-old"]


def test_config_ignores_invalid_json_group_entries_and_falls_back():
    db = FakeDB(
        {
            IMA_PURE_GROUPS_KEY: json.dumps(
                [
                    None,
                    "not-a-group",
                    {"id": 123, "name": "数字 ID", "knowledge_base_id": "kb", "root_folder_id": "root"},
                    {"id": "numeric-kb", "name": "数字 KB", "knowledge_base_id": 123, "root_folder_id": "root"},
                    {"id": "numeric-root", "name": "数字目录", "knowledge_base_id": "kb", "root_folder_id": 123},
                    {"id": "string-enabled", "name": "字符串开关", "knowledge_base_id": "kb", "root_folder_id": "root", "enabled": "false"},
                    {"id": "numeric-name", "name": 123, "knowledge_base_id": "kb", "root_folder_id": "root"},
                    {"id": "missing-name", "knowledge_base_id": "kb", "root_folder_id": "root"},
                    {"id": "missing-kb", "name": "缺少 KB", "root_folder_id": "root"},
                    {"id": "missing-root", "name": "缺少目录", "knowledge_base_id": "kb"},
                ]
            ),
            "ima_pure_knowledge_base_id": "legacy-kb",
            "ima_pure_root_folder_id": "legacy-root",
        }
    )
    cfg = ImaDocumentConfig.from_db(db)
    assert cfg.groups == (
        ImaGroupConfig(
            id=IMA_LEGACY_GROUP_ID,
            name="IMA 文档",
            knowledge_base_id="legacy-kb",
            root_folder_id="legacy-root",
        ),
    )


@pytest.mark.parametrize("malformed_source", [123, []])
def test_config_ignores_non_string_source_in_mixed_registry(malformed_source):
    db = FakeDB(
        {
            IMA_PURE_GROUPS_KEY: json.dumps(
                [
                    {
                        "id": "valid",
                        "name": "有效群组",
                        "knowledge_base_id": "kb-valid",
                        "root_folder_id": "root-valid",
                    },
                    {
                        "id": "malformed-source",
                        "name": "错误来源",
                        "knowledge_base_id": "kb-invalid",
                        "root_folder_id": "root-invalid",
                        "source": malformed_source,
                    },
                ]
            )
        }
    )
    cfg = ImaDocumentConfig.from_db(db)
    assert [(group.id, group.source) for group in cfg.groups] == [("valid", "manual")]


def test_config_falls_back_when_registry_has_only_non_string_source():
    db = FakeDB(
        {
            IMA_PURE_GROUPS_KEY: json.dumps(
                [
                    {
                        "id": "malformed-source",
                        "name": "错误来源",
                        "knowledge_base_id": "kb-invalid",
                        "root_folder_id": "root-invalid",
                        "source": {"value": "manual"},
                    }
                ]
            ),
            "ima_pure_knowledge_base_id": "legacy-kb",
            "ima_pure_root_folder_id": "legacy-root",
        }
    )
    cfg = ImaDocumentConfig.from_db(db)
    assert cfg.groups == (
        ImaGroupConfig(
            id=IMA_LEGACY_GROUP_ID,
            name="IMA 文档",
            knowledge_base_id="legacy-kb",
            root_folder_id="legacy-root",
        ),
    )


def test_configured_uses_enabled_groups_even_when_legacy_scalars_are_missing():
    cfg = ImaDocumentConfig(
        uid="uid",
        refresh_token="refresh",
        knowledge_base_id="",
        root_folder_id="",
        groups=(
            ImaGroupConfig(
                id="group-1",
                name="团队资料",
                knowledge_base_id="kb-1",
                root_folder_id="root-1",
            ),
        ),
    )
    assert cfg.configured is True


def test_disabled_or_incomplete_groups_do_not_configure_account():
    cfg = ImaDocumentConfig(
        uid="uid",
        refresh_token="refresh",
        knowledge_base_id="",
        root_folder_id="",
        groups=(
            ImaGroupConfig(
                id="disabled",
                name="禁用",
                knowledge_base_id="kb",
                root_folder_id="root",
                enabled=False,
            ),
            ImaGroupConfig(
                id="incomplete",
                name="不完整",
                knowledge_base_id="kb",
                root_folder_id="",
            ),
        ),
    )
    assert cfg.configured is False


def test_client_uses_first_enabled_group_when_legacy_scalars_are_empty(monkeypatch):
    from app import ima_documents

    group = ImaGroupConfig(
        id="group-1",
        name="团队资料",
        knowledge_base_id="group-kb",
        root_folder_id="group-root",
    )
    config = ImaDocumentConfig(
        uid="uid",
        refresh_token="refresh",
        knowledge_base_id="",
        root_folder_id="",
        groups=(group,),
    )
    client = ImaPureClient(config)
    assert client.effective_knowledge_base_id == "group-kb"
    assert client.effective_root_folder_id == "group-root"

    requests = []
    client._token = lambda: "access"

    def open_json(request):
        requests.append(request)
        return {"code": 0, "knowledge_list": [], "is_end": True}, {}

    client._open_json = open_json
    client.list_items("child-folder")
    assert json.loads(requests[0].data)["knowledge_base_id"] == "group-kb"

    seen_folders = []

    def list_items(folder_id):
        seen_folders.append(folder_id)
        return []

    client.list_items = list_items
    client.manifest()
    assert seen_folders == ["group-root"]

    encrypted_plaintexts = []
    monkeypatch.setattr(
        ima_documents,
        "encrypt_body",
        lambda plain: (encrypted_plaintexts.append(plain) or (b"key", "encrypted", "wrapped")),
    )
    monkeypatch.setattr(
        ima_documents,
        "decrypt_body",
        lambda raw, key: b'{"code": 0, "jump_url": "https://example.invalid/media"}',
    )

    class Response:
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b"response"

    monkeypatch.setattr(ima_documents.urllib.request, "urlopen", lambda request, timeout: Response())
    client.get_media("media-1")
    assert json.loads(encrypted_plaintexts[0].decode())["source_knowledge_base_id"] == "group-kb"


def test_discover_groups_normalizes_knowledge_base_payload():
    payload = {
        "data": {
            "knowledge_base_list": [
                {"knowledge_base_id": "kb-1", "name": "投行研报", "root_folder_id": "folder-1"},
                {"id": "kb-2", "kb_name": "宏观策略", "folder_id": "folder-2"},
                {"id": "missing-root"},
                "invalid",
            ]
        }
    }
    groups = normalize_discovered_groups(payload)
    assert [(g.id, g.name, g.knowledge_base_id, g.root_folder_id) for g in groups] == [
        ("kb-1", "投行研报", "kb-1", "folder-1"),
        ("kb-2", "宏观策略", "kb-2", "folder-2"),
    ]
    assert all(group.source == "discovered" for group in groups)


def test_legacy_manifest_normalization_preserves_group_metadata(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    legacy = ImaGroupConfig(IMA_LEGACY_GROUP_ID, "IMA 文档", "kb", "root")
    other = ImaGroupConfig("other", "其他群组", "kb-other", "root-other")
    store.save_manifest([
        {"media_id": "legacy-old", "name": "old.pdf", "day": "0825"},
        {"media_id": "other-file", "name": "other.pdf", "day": "0825", "group_id": other.id},
    ])
    initial_records = store.load_manifest()
    assert initial_records[0]["group_id"] == IMA_LEGACY_GROUP_ID
    assert initial_records[0]["group_name"] == IMA_LEGACY_GROUP_NAME
    state = {}
    for record in initial_records:
        pdf, txt = store.pdf_path(record), store.txt_path(record)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.7")
        txt.write_text("text", encoding="utf-8")
        state[record["media_id"]] = {
            "pdf": str(pdf.relative_to(store.root)),
            "txt": str(txt.relative_to(store.root)),
        }
    store.save_state(state)
    direct_items = store.documents()
    old_item = next(item for item in direct_items if item["media_id"] == "legacy-old")
    assert old_item["group_id"] == legacy.id
    assert old_item["group_name"] == legacy.name
    old_detail = store.document("legacy-old")
    assert old_detail["group_id"] == legacy.id
    assert old_detail["group_name"] == legacy.name

    store.save_group_manifest(legacy.id, [{"media_id": "legacy-new", "name": "new.pdf", "day": "0826"}])
    records = store.load_manifest()
    assert {record["media_id"] for record in records} == {"legacy-new", "other-file"}
    state = {}
    for record in records:
        pdf, txt = store.pdf_path(record), store.txt_path(record)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.7")
        txt.write_text("text", encoding="utf-8")
        state[record["media_id"]] = {
            "pdf": str(pdf.relative_to(store.root)),
            "txt": str(txt.relative_to(store.root)),
        }
    store.save_state(state)
    items = store.documents(groups=(legacy, other))
    assert {item["media_id"] for item in items} == {"legacy-new", "other-file"}
    legacy_item = next(item for item in items if item["media_id"] == "legacy-new")
    assert legacy_item["group_id"] == legacy.id
    assert legacy_item["group_name"] == legacy.name
    detail = store.document("legacy-new")
    assert detail["group_id"] == legacy.id
    assert detail["group_name"] == legacy.name


def test_discovery_rejects_non_string_ids_and_roots():
    groups = normalize_discovered_groups(
        {
            "knowledge_list": [
                {"id": 123, "root_folder_id": "root-bad"},
                {"id": "kb-bad", "root_folder_id": 456},
                {"id": "kb-good", "root_folder_id": "root-good", "name": "有效"},
            ]
        }
    )
    assert [(group.id, group.root_folder_id) for group in groups] == [("kb-good", "root-good")]


def test_discovery_root_fallback_skips_malformed_folder_info(monkeypatch):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    client._token = lambda: "access"
    client._open_json = lambda request: (
        {"code": 0, "data": {"knowledge_base_list": [{"id": "kb-good", "name": "有效"}], "is_end": True}},
        {},
    )
    client.list_items = lambda folder_id: [
        {"media_type": 99, "folder_info": None},
        {"media_type": 99, "folder_info": "invalid"},
        {"media_type": 99, "folder_info": {"folder_id": "root-good"}},
    ]
    groups = client.discover_groups()
    assert [(group.id, group.root_folder_id) for group in groups] == [("kb-good", "root-good")]


def test_merge_groups_updates_discovered_without_deleting_manual():
    existing = (
        ImaGroupConfig("manual-1", "手动群", "kb-manual", "folder-manual", source="manual"),
        ImaGroupConfig("kb-1", "旧名称", "kb-1", "folder-old", source="discovered"),
    )
    discovered = (
        ImaGroupConfig("kb-1", "新名称", "kb-1", "folder-new", source="discovered"),
    )
    merged = merge_groups(existing, discovered)
    assert [(g.id, g.name, g.root_folder_id) for g in merged] == [
        ("manual-1", "手动群", "folder-manual"),
        ("kb-1", "新名称", "folder-new"),
    ]


def test_manifest_records_include_group_context():
    group = ImaGroupConfig("banking", "投行研报", "kb-1", "folder-1")
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client.list_items = lambda folder_id: [
        {"media_type": 99, "folder_info": {"name": "0825", "folder_id": "day-1"}}
    ] if folder_id == "folder-1" else [
        {"media_id": "pdf_1", "name": "report.pdf", "file_size": 4}
    ]
    records = client.manifest()
    assert records[0]["group_id"] == "banking"
    assert records[0]["group_name"] == "投行研报"


def test_group_manifest_replaces_only_target_and_legacy_records(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    store.save_manifest([
        {"media_id": "legacy", "name": "legacy.pdf"},
        {"media_id": "first", "group_id": "first", "group_name": "一组"},
        {"media_id": "second", "group_id": "second", "group_name": "二组"},
    ])
    store.save_group_manifest(IMA_LEGACY_GROUP_ID, [{"media_id": "new", "group_id": IMA_LEGACY_GROUP_ID}])

    assert {item["media_id"] for item in store.load_manifest()} == {"new", "first", "second"}
    store.save_group_manifest("first", [{"media_id": "first-new", "group_id": "first"}])
    assert {item["media_id"] for item in store.load_manifest()} == {"new", "first-new", "second"}


def test_discover_groups_paginates_and_resolves_missing_root(monkeypatch):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    requests = []
    pages = iter([
        {"code": 0, "data": {"knowledge_base_list": [{"id": "kb-1", "name": "一组"}], "next_cursor": "next", "is_end": False}},
        {"code": 0, "data": {"knowledge_list": [{"id": "kb-2", "name": "二组", "folder_id": "root-2"}], "is_end": True}},
    ])
    client._token = lambda: "access"
    client._open_json = lambda request: (requests.append(json.loads(request.data)) or (next(pages), {}))
    client.list_items = lambda folder_id: [{"media_type": 99, "folder_info": {"folder_id": "root-1"}}]
    groups = client.discover_groups()
    assert [group.root_folder_id for group in groups] == ["root-1", "root-2"]
    assert requests == [{"cursor": ""}, {"cursor": "next"}]


def test_discovery_error_is_preserved_when_group_also_fails(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "legacy-kb",
            "ima_pure_root_folder_id": "legacy-root",
            IMA_PURE_GROUPS_KEY: json.dumps(
                [
                    {
                        "id": "first",
                        "name": "一组",
                        "knowledge_base_id": "kb-1",
                        "root_folder_id": "root-1",
                        "enabled": True,
                        "source": "manual",
                    },
                    {
                        "id": "second",
                        "name": "二组",
                        "knowledge_base_id": "kb-2",
                        "root_folder_id": "root-2",
                        "enabled": True,
                        "source": "manual",
                    },
                ],
                ensure_ascii=False,
            ),
        }
    )
    calls = []

    class FakeClient:
        def __init__(self, config, group=None):
            self.group = group

        def discover_groups(self):
            raise RuntimeError("discovery https://secret.invalid/token=secret")

        def manifest(self):
            calls.append(self.group.id)
            if self.group.id == "first":
                raise RuntimeError("group failed https://group.invalid/sign=secret")
            return []

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    result = ImaDocumentService(db, tmp_path / "ima").sync_once()
    assert calls == ["first", "second"]
    assert result["failed_groups"] == ["first"]
    assert result["discovery_error"]
    assert result["last_error"] == result["discovery_error"]
    assert "secret.invalid" not in result["discovery_error"]
    assert "group.invalid" not in result["group_errors"]["first"]


def test_failed_group_does_not_block_later_group(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB({
        "ima_pure_uid": "uid", "ima_pure_refresh_token": "refresh",
        "ima_pure_knowledge_base_id": "kb", "ima_pure_root_folder_id": "root",
    })
    groups = (
        ImaGroupConfig("first", "一组", "kb-1", "root-1"),
        ImaGroupConfig("second", "二组", "kb-2", "root-2"),
    )
    db.values[IMA_PURE_GROUPS_KEY] = json.dumps([group.public() for group in groups], ensure_ascii=False)
    calls = []

    class FakeClient:
        def __init__(self, config, group=None):
            self.group = group
        def manifest(self):
            calls.append(self.group.id)
            if self.group.id == "first":
                raise RuntimeError("boom https://secret.invalid/token")
            return []

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    result = service.sync_once()
    assert result["status"] == "finished"
    assert calls == ["first", "second"]
    assert result["failed_groups"] == ["first"]
    assert result["succeeded_groups"] == 1
    assert "secret.invalid" not in result["last_error"]


def test_list_items_rejects_repeated_cursor(monkeypatch):
    client = ImaPureClient(
        ImaDocumentConfig(refresh_token="refresh", root_folder_id="root")
    )
    requests = []
    client._token = lambda: "access"

    def open_json(request):
        requests.append(json.loads(request.data))
        if len(requests) > 2:
            raise RuntimeError("test guard")
        return {"code": 0, "knowledge_list": [], "is_end": False, "next_cursor": "repeat"}, {}

    client._open_json = open_json
    with pytest.raises(RuntimeError, match="cursor"):
        client.list_items("root")
    assert len(requests) == 2


def test_discover_groups_rejects_repeated_cursor(monkeypatch):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    requests = []
    client._token = lambda: "access"

    def open_json(request):
        requests.append(json.loads(request.data))
        if len(requests) > 2:
            raise RuntimeError("test guard")
        return {"code": 0, "data": {"knowledge_base_list": [], "is_end": False, "next_cursor": "repeat"}}, {}

    client._open_json = open_json
    with pytest.raises(RuntimeError, match="cursor"):
        client.discover_groups()
    assert len(requests) == 2


def test_archive_paths_are_relative_and_confined(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "file_abc", "name": "../report.pdf", "day": "0825"}
    path = store.pdf_path(record)
    assert path.parent == (tmp_path / "ima" / "0825").resolve()
    assert path.is_relative_to((tmp_path / "ima").resolve())
    assert ".." not in path.name


def test_archive_paths_are_unique_for_same_day_same_name(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    first = {"media_id": "file_first", "name": "report.pdf", "day": "0825"}
    second = {"media_id": "file_second", "name": "report.pdf", "day": "0825"}
    assert store.pdf_path(first) != store.pdf_path(second)


def test_documents_ignore_invalid_manifest_media_ids(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    valid = {"media_id": "file_valid", "name": "valid.pdf", "day": "0825"}
    invalid = {"media_id": "bad' onclick='alert(1)", "name": "bad.pdf", "day": "0825"}
    state = {}
    for record in (valid, invalid):
        if record is valid:
            pdf = store.pdf_path(record)
        else:
            pdf = store.root / "0825" / "bad.pdf"
        txt = pdf.with_suffix(".txt")
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.7")
        txt.write_text("text", encoding="utf-8")
        state[record["media_id"]] = {
            "pdf": str(pdf.relative_to(store.root)),
            "txt": str(txt.relative_to(store.root)),
        }
    store.save_manifest([valid, invalid])
    store.save_state(state)
    assert [item["media_id"] for item in store.documents()] == ["file_valid"]


def test_completed_media_is_skipped_but_missing_txt_is_pending(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "file_abc", "name": "report.pdf", "day": "0825", "size": 4}
    pdf, txt = store.pdf_path(record), store.txt_path(record)
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7")
    store.save_state({"file_abc": {"pdf": str(pdf.relative_to(store.root)), "txt": str(txt.relative_to(store.root))}})
    assert store.is_complete(record) is False
    txt.write_text("text", encoding="utf-8")
    assert store.is_complete(record) is True


def test_encrypt_body_uses_aes_128_gcm_and_rsa_oaep():
    plaintext = b'{"media_id":"file_abc"}'
    key, body, wrapped = encrypt_body(plaintext)
    assert len(key) == 16
    assert len(base64.b64decode(body)) > 12 + 16
    assert len(base64.b64decode(wrapped)) == 256
    assert decrypt_body(body, key) == plaintext


def test_convert_pdf_writes_txt_archive(tmp_path):
    from pypdf import PdfWriter

    from app.ima_documents import convert_pdf

    pdf = tmp_path / "report.pdf"
    txt = tmp_path / "report.txt"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with pdf.open("wb") as output:
        writer.write(output)
    assert convert_pdf(pdf, txt) == 0
    assert txt.read_text(encoding="utf-8") == ""


@pytest.mark.parametrize("value", ["", "../outside", "/tmp/outside"])
def test_invalid_media_ids_are_not_accepted(tmp_path, value):
    store = ImaDocumentStore(tmp_path / "ima")
    with pytest.raises(ValueError):
        store.validate_media_id(value)


def test_error_summary_redacts_urls_and_credentials():
    text = _safe_error(RuntimeError("failed https://res-skb.ima.qq.com/a.pdf?sign=secret"))
    assert "res-skb.ima.qq.com" not in text
    assert "sign=secret" not in text
    assert "secret" not in _safe_error(RuntimeError("Authorization: Bearer secret"))
    assert "secret" not in _safe_error(RuntimeError("access_token=secret"))
    assert "secret" not in _safe_error(RuntimeError("token secret"))


def test_archive_root_rejects_symlink(tmp_path):
    real_root = tmp_path / "real-ima"
    real_root.mkdir()
    link_root = tmp_path / "ima"
    link_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ValueError, match="root.*symlink"):
        ImaDocumentStore(link_root)


def test_archive_path_rejects_symlinked_day_directory(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    outside = tmp_path / "outside"
    outside.mkdir()
    day = store.root / "0825"
    day.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        store.pdf_path({"media_id": "file_abc", "name": "report.pdf", "day": "0825"})


def test_worker_logs_only_redacted_error(tmp_path, monkeypatch, caplog):
    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    service = ImaDocumentService(db, tmp_path / "ima")

    def fail():
        raise RuntimeError("boom https://secret.invalid/file?sign=signature&token=secret")

    monkeypatch.setattr(service, "sync_once", fail)
    with caplog.at_level(logging.ERROR, logger="app.ima_documents"):
        service._worker()
    output = caplog.text
    assert "secret.invalid" not in output
    assert "signature" not in output
    assert "secret" not in output
    assert json.loads(db.get_setting(IMA_PURE_LAST_RESULT_KEY))["last_error"] == "sync failed"


def test_scheduled_trigger_after_stop_does_not_start_worker(tmp_path):
    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    service = ImaDocumentService(db, tmp_path / "ima")
    service._stop.set()
    result = service.trigger(scheduled=True)
    assert result["status"] == "stopped"
    assert service._worker_thread is None


def test_scheduler_checks_stop_after_wait_before_trigger(tmp_path, monkeypatch):
    service = ImaDocumentService(FakeDB(), tmp_path / "ima")
    calls = []

    class StoppedEvent:
        def __init__(self):
            self.waits = 0

        def wait(self, timeout):
            self.waits += 1
            if self.waits > 1:
                raise AssertionError("scheduler did not stop")
            return False

        def is_set(self):
            return True

    service._stop = StoppedEvent()
    monkeypatch.setattr(service, "trigger", lambda scheduled=False: calls.append(scheduled))
    service._schedule_loop()
    assert calls == []


def test_stop_waits_for_worker_without_timeout(tmp_path):
    service = ImaDocumentService(FakeDB(), tmp_path / "ima")
    calls = []

    class Worker:
        def is_alive(self):
            return True

        def join(self, timeout=None):
            calls.append(timeout)

    service._worker_thread = Worker()
    service.stop()
    assert calls == [None]


def test_manual_trigger_respects_lock_and_interval(tmp_path):
    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
            "ima_pure_last_started_at": str(time.time()),
        }
    )
    service = ImaDocumentService(db, tmp_path / "ima")
    assert service.trigger()["status"] == "too_soon"
    service._running = True
    db.values["ima_pure_last_started_at"] = "0"
    assert service.trigger()["status"] == "already_running"


def _headers(client, username, code, *, admin=False):
    client.app.state.db.add_register_code(code)
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "pass123456", "code": code},
    )
    assert response.status_code == 200, response.text
    if admin:
        client.app.state.db.update_user(response.json()["user"]["id"], is_admin=True)
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_document_api_auth_file_access_and_admin_config(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    user_headers = _headers(client, "ima_reader", "IMA001")
    admin_headers = _headers(client, "ima_admin", "IMA002", admin=True)
    service = client.app.state.ima_documents
    store = service.store
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

    assert client.get("/api/ima-documents").status_code == 401
    listed = client.get("/api/ima-documents", headers=user_headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["media_id"] == "file_abc"
    text_response = client.get("/api/ima-documents/file_abc/text", headers=user_headers)
    assert text_response.text == "text"
    assert text_response.headers["content-type"].startswith("text/plain")
    pdf_response = client.get("/api/ima-documents/file_abc/pdf", headers=user_headers)
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    download_response = client.get("/api/ima-documents/file_abc/pdf?download=1", headers=user_headers)
    assert "attachment" in download_response.headers["content-disposition"]
    assert client.get("/api/ima-documents/missing/text", headers=user_headers).status_code == 404
    assert client.get("/api/ima-documents/../outside/text", headers=user_headers).status_code in (404, 400)

    assert client.get("/api/admin/ima-collector", headers=user_headers).status_code == 403
    saved = client.put(
        "/api/admin/ima-collector",
        headers=admin_headers,
        json={"refresh_token": "secret-token"},
    )
    assert saved.status_code == 200
    status = client.get("/api/admin/ima-collector", headers=admin_headers).json()
    assert status["config"]["refresh_token"]["set"] is True
    assert "secret-token" not in saved.text
    assert "secret-token" not in str(status)




def test_group_aware_document_api_returns_summary_and_filters_items(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    headers = _headers(client, "group_reader", "GROUP001")
    db = client.app.state.db
    db.set_setting(
        IMA_PURE_GROUPS_KEY,
        json.dumps(
            [
                {
                    "id": "banking",
                    "name": "投行研报",
                    "knowledge_base_id": "kb-banking",
                    "root_folder_id": "root-banking",
                    "enabled": True,
                    "source": "manual",
                },
                {
                    "id": "empty",
                    "name": "空群组",
                    "knowledge_base_id": "kb-empty",
                    "root_folder_id": "root-empty",
                    "enabled": True,
                    "source": "manual",
                },
            ],
            ensure_ascii=False,
        ),
    )
    store = client.app.state.ima_documents.store
    records = [
        {"media_id": "banking-doc", "name": "银行报告.pdf", "day": "2026-08-25", "group_id": "banking", "group_name": "投行研报"},
        {"media_id": "disabled-doc", "name": "停用报告.pdf", "day": "2026-08-25", "group_id": "disabled", "group_name": "停用资料"},
    ]
    state = {}
    for record in records:
        pdf = store.pdf_path(record)
        txt = store.txt_path(record)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.7")
        txt.write_text("text", encoding="utf-8")
        state[record["media_id"]] = {
            "pdf": str(pdf.relative_to(store.root)),
            "txt": str(txt.relative_to(store.root)),
        }
    store.save_manifest(records)
    store.save_state(state)

    response = client.get("/api/ima-documents?group=banking", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"] == [
        {"id": "banking", "name": "投行研报", "count": 1},
        {"id": "empty", "name": "空群组", "count": 0},
    ]
    assert [item["group_id"] for item in payload["items"]] == ["banking"]
    assert payload["items"][0]["group_name"] == "投行研报"
    detail = client.get("/api/ima-documents/banking-doc", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["group_id"] == "banking"
    assert detail.json()["group_name"] == "投行研报"
    assert "pdf" not in detail.json()
    assert "txt" not in detail.json()
    assert client.get("/api/ima-documents?group=unknown", headers=headers).status_code == 400
    assert client.get("/api/ima-documents?group=disabled", headers=headers).status_code == 400
    assert client.get("/api/ima-documents").status_code == 401

    all_groups = client.get("/api/ima-documents", headers=headers)
    assert all_groups.status_code == 200
    assert {item["group_id"] for item in all_groups.json()["items"]} == {"banking"}
    assert client.get("/api/ima-documents?q=银行", headers=headers).json()["items"][0]["media_id"] == "banking-doc"
    assert client.get("/api/ima-documents?day=not-found", headers=headers).json()["items"] == []


def test_admin_groups_put_validates_persists_and_keeps_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    headers = _headers(client, "group_admin", "GROUP002", admin=True)
    db = client.app.state.db
    db.set_setting(IMA_PURE_REFRESH_TOKEN_KEY, "refresh-secret")
    db.set_setting(
        IMA_PURE_GROUPS_KEY,
        json.dumps(
            [{
                "id": "banking",
                "name": "旧名称",
                "knowledge_base_id": "old-kb",
                "root_folder_id": "old-root",
                "enabled": True,
                "source": "discovered",
            }],
            ensure_ascii=False,
        ),
    )

    response = client.put(
        "/api/admin/ima-collector",
        headers=headers,
        json={
            "groups": [
                {
                    "id": "banking",
                    "name": "投行研报",
                    "knowledge_base_id": "new-kb",
                    "root_folder_id": "new-root",
                    "enabled": False,
                },
                {
                    "name": "手工资料",
                    "knowledge_base_id": "manual-kb",
                    "root_folder_id": "manual-root",
                },
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert "refresh-secret" not in response.text
    saved = json.loads(db.get_setting(IMA_PURE_GROUPS_KEY))
    assert saved[0]["source"] == "discovered"
    assert saved[0]["name"] == "投行研报"
    assert saved[0]["enabled"] is False
    assert saved[1]["id"].startswith("manual-")
    assert db.get_setting(IMA_PURE_REFRESH_TOKEN_KEY) == "refresh-secret"
    audit = db.list_admin_logs(10)[0]["detail"]
    assert "banking" in audit and "groups_count=2" in audit
    assert "refresh-secret" not in audit
    assert "new-root" not in audit

    scalar = client.put(
        "/api/admin/ima-collector",
        headers=headers,
        json={"knowledge_base_id": "legacy-kb", "root_folder_id": "legacy-root"},
    )
    assert scalar.status_code == 200
    assert json.loads(db.get_setting(IMA_PURE_GROUPS_KEY)) == saved


@pytest.mark.parametrize(
    "payload",
    [
        {"groups": [{"name": "", "knowledge_base_id": "kb", "root_folder_id": "root"}]},
        {"groups": [{"name": "x" * 101, "knowledge_base_id": "kb", "root_folder_id": "root"}]},
        {"groups": [{"name": "有效", "knowledge_base_id": "bad.kb", "root_folder_id": "root"}]},
        {"groups": [{"name": "有效", "knowledge_base_id": "kb", "root_folder_id": "bad/root"}]},
        {"groups": [{"id": "bad/id", "name": "有效", "knowledge_base_id": "kb", "root_folder_id": "root"}]},
        {"groups": [
            {"id": "same", "name": "一", "knowledge_base_id": "kb1", "root_folder_id": "root1"},
            {"id": "same", "name": "二", "knowledge_base_id": "kb2", "root_folder_id": "root2"},
        ]},
    ],
)
def test_admin_groups_put_rejects_invalid_values(tmp_path, monkeypatch, payload):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    headers = _headers(client, "invalid_group_admin", "GROUP003", admin=True)
    response = client.put("/api/admin/ima-collector", headers=headers, json=payload)
    assert response.status_code == 400, response.text


def test_manifest_excludes_non_pdf_media():
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    responses = iter(
        [
            [{"media_type": 99, "folder_info": {"name": "0812", "folder_id": "day"}}],
            [
                {"media_id": "pdf_report", "name": "pdf_report", "file_size": 8},
                {"media_id": "txt_report", "name": "txt_report", "file_size": 4},
                {"media_id": "file_report", "name": "Report.pdf", "file_size": 8},
            ],
        ]
    )
    client.list_items = lambda folder_id: next(responses)
    assert [item["media_id"] for item in client.manifest()] == ["file_report", "pdf_report"]


def test_manifest_skips_malformed_folders_and_items():
    client = ImaPureClient(
        ImaDocumentConfig(refresh_token="refresh", root_folder_id="root")
    )
    responses = {
        "root": [
            None,
            {"media_type": 99, "folder_info": None},
            {"media_type": 99, "folder_info": "invalid"},
            {"media_type": 99, "folder_info": {"folder_id": 123, "name": "bad"}},
            {"media_type": 99, "folder_info": {"folder_id": "day", "name": "0825"}},
        ],
        "day": [
            None,
            {"media_id": 123, "name": "wrong.pdf"},
            {"media_id": "bad-name", "name": {"invalid": True}},
            {"media_id": "valid-file", "name": "valid.pdf", "file_size": 8},
        ],
    }
    client.list_items = lambda folder_id: responses[folder_id]
    records = client.manifest()
    assert [record["media_id"] for record in records] == ["valid-file"]


def test_service_sync_is_incremental(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    calls = []

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def manifest(self):
            return [{"media_id": "file_abc", "name": "Report.pdf", "day": "0825", "size": 8}]

        def get_media(self, media_id):
            calls.append(media_id)
            return {"jump_url_info": {"url": "https://download.invalid/report.pdf"}}

        def download(self, media, destination, expected_size=0):
            destination.write_bytes(b"%PDF-1.7")
            return {"size": 8, "md5": "md5"}

        @staticmethod
        def _pdf_info(path):
            return 8, "md5"

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    monkeypatch.setattr(ima_documents, "convert_pdf", lambda pdf, txt: (txt.write_text("text", encoding="utf-8") or 4))
    service = ImaDocumentService(db, tmp_path / "ima")
    assert service.sync_once()["downloaded"] == 1
    assert service.sync_once()["downloaded"] == 0
    assert calls == ["file_abc"]


def test_admin_ima_put_uses_one_atomic_settings_write(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    headers = _headers(client, "atomic_admin", "ATOMIC001", admin=True)
    db = client.app.state.db
    original_set_setting = db.set_setting
    calls = []

    def atomic_write(values):
        calls.append(dict(values))
        for key, value in values.items():
            original_set_setting(key, value)

    monkeypatch.setattr(db, "set_settings_atomic", atomic_write, raising=False)
    monkeypatch.setattr(
        db,
        "set_setting",
        lambda key, value: pytest.fail("IMA PUT must use set_settings_atomic"),
    )
    response = client.put(
        "/api/admin/ima-collector",
        headers=headers,
        json={
            "uid": "atomic-uid",
            "knowledge_base_id": "atomic-kb",
            "root_folder_id": "atomic-root",
            "groups": [
                {
                    "id": "atomic-group",
                    "name": "原子群组",
                    "knowledge_base_id": "group-kb",
                    "root_folder_id": "group-root",
                }
            ],
        },
    )
    assert response.status_code == 200
    assert len(calls) == 1
    assert set(calls[0]) == {
        "ima_pure_uid",
        "ima_pure_knowledge_base_id",
        "ima_pure_root_folder_id",
        IMA_PURE_GROUPS_KEY,
    }
