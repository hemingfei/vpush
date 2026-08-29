import base64
import hashlib
import json
import logging
import threading
import time

import pytest
from fastapi.testclient import TestClient

import app.ima_documents as ima_documents
from app.ima_storage import ImaStorageStatus
from app.ima_documents import (
    IMA_LEGACY_GROUP_ID,
    IMA_LEGACY_GROUP_NAME,
    IMA_MAX_FOLDER_DEPTH,
    IMA_PURE_GROUPS_KEY,
    IMA_PURE_KB_ID_KEY,
    IMA_PURE_DISCOVERY_KEY,
    IMA_PURE_LAST_RESULT_KEY,
    IMA_PURE_REFRESH_TOKEN_KEY,
    IMA_PURE_ROOT_FOLDER_KEY,
    IMA_PURE_UID_KEY,
    ImaDocumentConfig,
    ImaDocumentService,
    ImaDocumentStore,
    ImaGroupConfig,
    ImaPureClient,
    is_ima_folder_item,
    merge_groups,
    normalize_discovered_groups,
    normalize_ima_folder_item,
    _safe_error,
    decrypt_body,
    encrypt_body,
    safe_filename,
)
from app.main import create_app


class FakeDB:
    def __init__(self, values=None):
        self.values = values or {}

    def get_setting(self, key):
        return self.values.get(key)

    def set_setting(self, key, value):
        self.values[key] = value

    def set_settings_atomic(self, values):
        self.values.update(values)




def test_status_counts_only_complete_manifest_entries(tmp_path):
    service = ImaDocumentService(FakeDB(), tmp_path / "ima")
    complete = {"media_id": "complete", "name": "complete.pdf", "day": "0825"}
    incomplete = {"media_id": "incomplete", "name": "incomplete.pdf", "day": "0825"}
    service.store.save_manifest([complete, incomplete])

    pdf = service.store.pdf_path(complete)
    txt = service.store.txt_path(complete)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-1.7")
    txt.write_text("complete", encoding="utf-8")
    service.store.save_state({
        service.store.state_key(complete): {
            "pdf": str(pdf.relative_to(service.store.root)),
            "txt": str(txt.relative_to(service.store.root)),
        },
        service.store.state_key(incomplete): {"pdf": "0825/incomplete.pdf"},
    })

    assert service.status()["documents"] == 1


def test_remote_status_counts_state_without_statting_archive(tmp_path, monkeypatch):
    index_root = tmp_path / "index"
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    (archive_root / ".vpush-ima-root").touch()
    status_path = tmp_path / "status.json"
    _write_available_status(status_path)
    status = ImaStorageStatus(status_path, remote=True)
    service = ImaDocumentService(
        FakeDB(),
        index_root,
        archive_root=archive_root,
        storage_status=status,
    )
    records = []
    state = {}
    for index in range(20):
        record = {
            "media_id": f"file_{index}",
            "name": f"{index}.pdf",
            "day": "0829",
            "group_id": "banking",
        }
        records.append(record)
        state[service.store.state_key(record)] = {"pdf": f"banking/{index}.pdf"}
    service.store.save_manifest(records)
    service.store.save_state(state)

    def boom(*_args, **_kwargs):
        raise AssertionError("remote status must not probe archive files")

    monkeypatch.setattr(service.store, "_state_path", boom)
    monkeypatch.setattr(service.store, "archive_readable", boom)

    assert service.status()["documents"] == 20


def test_discovery_commit_reloads_config_after_admin_update(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB({
        IMA_PURE_UID_KEY: "uid",
        IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
        IMA_PURE_GROUPS_KEY: json.dumps([{
            "id": "group-a", "name": "资料", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "folder_ids": ["old"], "enabled": True,
            "source": "manual",
        }]),
    })
    remote_done = threading.Event()
    resume = threading.Event()

    class FakeClient:
        def __init__(self, config, group=None):
            pass

        def discover_groups(self):
            remote_done.set()
            assert resume.wait(5)
            return (ImaGroupConfig("group-a", "远端资料", "kb-a", "root-a"),)

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    worker = threading.Thread(target=service.discover)
    worker.start()
    assert remote_done.wait(5)
    with service.config_lock:
        db.set_setting(IMA_PURE_GROUPS_KEY, json.dumps([{
            "id": "group-a", "name": "资料", "knowledge_base_id": "kb-a",
            "root_folder_id": "root-a", "folder_ids": ["new"], "enabled": True,
            "source": "manual",
        }]))
    resume.set()
    worker.join(5)
    assert not worker.is_alive()
    saved = json.loads(db.get_setting(IMA_PURE_GROUPS_KEY))
    assert saved[0]["folder_ids"] == ["new"]


def test_sync_skips_stale_manifest_after_unmount(tmp_path, monkeypatch):
    from app import ima_documents

    group = ImaGroupConfig("group-a", "资料", "kb-a", "root-a", True, "manual", ("root-a",))
    db = FakeDB({
        IMA_PURE_UID_KEY: "uid",
        IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
        IMA_PURE_GROUPS_KEY: json.dumps([group.public()]),
    })
    manifest_started = threading.Event()
    resume = threading.Event()

    class FakeClient:
        def __init__(self, config, group=None):
            self.group = group

        def discover_groups(self):
            return ()

        def manifest(self):
            manifest_started.set()
            assert resume.wait(5)
            return [{"media_id": "stale", "name": "stale.pdf", "day": "0825"}]

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    result_holder = {}

    def run_sync():
        result_holder["result"] = service.sync_once()

    worker = threading.Thread(target=run_sync)
    worker.start()
    assert manifest_started.wait(5)
    with service.config_lock:
        db.set_setting(IMA_PURE_GROUPS_KEY, json.dumps([{**group.public(), "folder_ids": [], "enabled": False}]))
        service.store.save_group_manifest(group.id, [])
    resume.set()
    worker.join(5)
    assert not worker.is_alive()
    result = result_holder["result"]
    assert result["skipped_groups"] == [group.id]
    assert result["succeeded_groups"] == 0
    assert service.store.load_manifest() == []
    assert list((tmp_path / "ima").glob("*.tmp")) == []


def test_concurrent_group_manifest_writes_retain_both_groups(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    start = threading.Barrier(3)
    original_save = store._save
    errors = []

    def slowed_save(path, value):
        if path == store.manifest_path:
            time.sleep(0.01)
        original_save(path, value)

    store._save = slowed_save

    def save(group_id):
        try:
            start.wait(5)
            store.save_group_manifest(group_id, [{"media_id": group_id, "name": group_id}])
        except Exception as exc:  # pragma: no cover - regression captures old race
            errors.append(exc)

    threads = [threading.Thread(target=save, args=(group_id,)) for group_id in ("first", "second")]
    for thread in threads:
        thread.start()
    start.wait(5)
    for thread in threads:
        thread.join(5)
    assert not errors
    assert {item["group_id"] for item in store.load_manifest()} == {"first", "second"}


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


def test_empty_group_registry_disables_legacy_fallback():
    db = FakeDB(
        {
            IMA_PURE_GROUPS_KEY: "[]",
            IMA_PURE_UID_KEY: "uid",
            IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
            IMA_PURE_KB_ID_KEY: "legacy-kb",
            IMA_PURE_ROOT_FOLDER_KEY: "legacy-root",
        }
    )
    cfg = ImaDocumentConfig.from_db(db)
    assert cfg.groups == ()
    assert cfg.configured is False

    missing = ImaDocumentConfig.from_db(
        FakeDB(
            {
                IMA_PURE_UID_KEY: "uid",
                IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
                IMA_PURE_KB_ID_KEY: "legacy-kb",
                IMA_PURE_ROOT_FOLDER_KEY: "legacy-root",
            }
        )
    )
    assert [group.id for group in missing.groups] == [IMA_LEGACY_GROUP_ID]


def test_valid_old_group_rows_preserve_missing_and_null_folder_ids():
    db = FakeDB(
        {
            IMA_PURE_GROUPS_KEY: json.dumps(
                [
                    {
                        "id": "missing-folders",
                        "name": "缺省目录列表",
                        "knowledge_base_id": "kb-1",
                        "root_folder_id": "root-1",
                    },
                    {
                        "id": "null-folders",
                        "name": "空目录列表",
                        "knowledge_base_id": "kb-2",
                        "root_folder_id": "root-2",
                        "folder_ids": None,
                    },
                ],
                ensure_ascii=False,
            )
        }
    )
    groups = ImaDocumentConfig.from_db(db).groups
    assert [group.mount_folder_ids for group in groups] == [("root-1",), ("root-2",)]


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
            "folder_ids": ["folder-1"],
            "mounted_folder_count": 1,
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
    assert cfg.groups == ()


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
    assert cfg.groups == ()


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
    assert cfg.groups == ()


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
    assert cfg.groups == ()


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
                {"id": "uid-personal", "name": "个人知识库", "type": 1, "root_folder_id": "root-personal"},
            ]
        }
    }
    groups = normalize_discovered_groups(payload)
    assert [(g.id, g.name, g.knowledge_base_id, g.root_folder_id) for g in groups] == [
        ("kb-1", "投行研报", "kb-1", "folder-1"),
        ("kb-2", "宏观策略", "kb-2", "folder-2"),
        ("missing-root", "missing-root", "missing-root", "missing-root"),
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
        state[store.state_key(record)] = {
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
        state[store.state_key(record)] = {
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
    with pytest.raises(RuntimeError, match="invalid"):
        normalize_discovered_groups(
            {
                "knowledge_list": [
                    {"id": 123, "root_folder_id": "root-bad"},
                    {"id": "kb-bad", "root_folder_id": 456},
                    {"id": "kb-good", "root_folder_id": "root-good", "name": "有效"},
                ]
            }
        )


def test_discover_groups_accepts_valid_empty_list(monkeypatch):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    client._token = lambda: "access"
    client._open_json = lambda request: (
        {"code": 0, "knowledge_base_list": [], "is_end": True},
        {},
    )
    assert client.discover_groups() == ()


@pytest.mark.parametrize("value", [0, "0"])
def test_discover_groups_accepts_successful_retcode(monkeypatch, value):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    client._token = lambda: "access"
    client._open_json = lambda request: (
        {"retcode": value, "knowledge_base_list": [], "is_end": True},
        {},
    )
    assert client.discover_groups() == ()


@pytest.mark.parametrize("field", ["code", "retcode"])
@pytest.mark.parametrize("value", [False, True])
def test_discover_groups_rejects_boolean_status(monkeypatch, field, value):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    client._token = lambda: "access"
    client._open_json = lambda request: (
        {field: value, "knowledge_base_list": [], "is_end": True},
        {},
    )
    with pytest.raises(RuntimeError, match="IMA group discovery"):
        client.discover_groups()


@pytest.mark.parametrize("response", [
    {"knowledge_base_list": [], "is_end": True},
    {"code": None, "knowledge_base_list": [], "is_end": True},
])
def test_discover_groups_requires_successful_code(monkeypatch, response):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    client._token = lambda: "access"
    client._open_json = lambda request: (response, {})
    with pytest.raises(RuntimeError, match="IMA group discovery"):
        client.discover_groups()


@pytest.mark.parametrize(
    "payload",
    [
        {"code": 0, "data": {"results": [{"knowledge_base_list": {"id": "kb"}}]}},
        {"code": 0, "results": ["bad-section"]},
        {"code": 0, "knowledge_base_list": [None]},
        {"code": 0, "knowledge_base_list": {"id": "kb"}},
        {
            "code": 0,
            "knowledge_base_list": [
                {"id": "not valid", "name": "坏群组", "root_folder_id": "root"}
            ],
        },
    ],
)
def test_discover_groups_rejects_malformed_or_all_invalid_rows(monkeypatch, payload):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    client._token = lambda: "access"
    client._open_json = lambda request: (payload, {})
    with pytest.raises(RuntimeError, match="invalid"):
        client.discover_groups()


def test_discover_groups_uses_search_knowledge_base(monkeypatch):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    requests = []
    client._token = lambda: "access"

    def open_json(request):
        requests.append((request.full_url, json.loads(request.data)))
        return {
            "code": 0,
            "searched_knowledge_bases": [
                {"id": "uid-personal", "name": "我的知识库", "type": 1},
                {"id": "kb-1", "name": "八大顶级投行研报VIP", "type": 3},
            ],
            "is_end": True,
            "next_cursor": "ignore-when-ended",
        }, {}

    client._open_json = open_json
    groups = client.discover_groups()
    assert requests[0][0].endswith("/knowledge_tab_reader/search_knowledge_base")
    assert requests[0][1] == {"query": "", "limit": 50, "cursor": ""}
    assert [(group.id, group.name, group.root_folder_id) for group in groups] == [
        ("kb-1", "八大顶级投行研报VIP", "kb-1"),
    ]


def test_discover_groups_reads_home_page_sections(monkeypatch):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    client._token = lambda: "access"
    client._open_json = lambda request: (
        {
            "code": 0,
            "results": [
                {
                    "type": 1,
                    "knowledge_base_list": [
                        {"id": "uid-personal", "type": 1, "basic_info": {"name": "个人知识库"}},
                    ],
                },
                {
                    "type": 3,
                    "knowledge_base_list": [
                        {"id": "kb-join", "type": 3, "basic_info": {"name": "加入的知识库"}},
                    ],
                },
            ],
            "is_end": True,
        },
        {},
    )
    groups = client.discover_groups()
    assert [(group.id, group.name, group.root_folder_id) for group in groups] == [
        ("kb-join", "加入的知识库", "kb-join"),
    ]


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


def test_merge_groups_matches_existing_manual_by_knowledge_base_id():
    existing = (
        ImaGroupConfig("legacy", "外行研报", "kb-1", "folder-aug", source="manual"),
    )
    discovered = (
        ImaGroupConfig("kb-1", "八大顶级投行研报VIP", "kb-1", "kb-1", source="discovered"),
        ImaGroupConfig("kb-2", "新建知识库", "kb-2", "kb-2", source="discovered"),
    )
    merged = merge_groups(existing, discovered)
    assert [(g.id, g.name, g.knowledge_base_id, g.root_folder_id, g.source) for g in merged] == [
        ("legacy", "外行研报", "kb-1", "folder-aug", "manual"),
        ("kb-2", "新建知识库", "kb-2", "kb-2", "discovered"),
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


def test_discover_groups_paginates_and_defaults_root_to_knowledge_base_id(monkeypatch):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    requests = []
    pages = iter([
        {"code": 0, "data": {"knowledge_base_list": [{"id": "kb-1", "name": "一组"}], "next_cursor": "next", "is_end": False}},
        {"code": 0, "data": {"knowledge_list": [{"id": "kb-2", "name": "二组", "folder_id": "root-2"}], "is_end": True}},
    ])
    client._token = lambda: "access"
    client._open_json = lambda request: (requests.append(json.loads(request.data)) or (next(pages), {}))
    groups = client.discover_groups()
    assert [group.root_folder_id for group in groups] == ["kb-1", "root-2"]
    assert requests == [
        {"query": "", "limit": 50, "cursor": ""},
        {"query": "", "limit": 50, "cursor": "next"},
    ]


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


def test_service_malformed_discovery_preserves_group_registry(tmp_path, monkeypatch):
    from app import ima_documents

    old_raw = '[{"id":"old","name":"旧群组","knowledge_base_id":"kb-old","root_folder_id":"root-old"}]'
    db = FakeDB(
        {
            IMA_PURE_UID_KEY: "uid",
            IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
            IMA_PURE_KB_ID_KEY: "legacy-kb",
            IMA_PURE_ROOT_FOLDER_KEY: "legacy-root",
            IMA_PURE_GROUPS_KEY: old_raw,
        }
    )

    class FakeClient:
        def __init__(self, config, group=None):
            self.group = group

        def discover_groups(self):
            return normalize_discovered_groups(
                {"code": 0, "results": [{"knowledge_base_list": {"id": "bad"}}]}
            )

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    result = ImaDocumentService(db, tmp_path / "ima").discover()
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert db.values[IMA_PURE_GROUPS_KEY] == old_raw


@pytest.mark.parametrize("field", ["code", "retcode"])
@pytest.mark.parametrize("value", [False, True])
def test_service_boolean_discovery_status_preserves_group_registry(
    tmp_path, monkeypatch, field, value
):
    from app import ima_documents

    old_raw = '[{"id":"old","name":"旧群组","knowledge_base_id":"kb-old","root_folder_id":"root-old"}]'
    db = FakeDB(
        {
            IMA_PURE_UID_KEY: "uid",
            IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
            IMA_PURE_KB_ID_KEY: "legacy-kb",
            IMA_PURE_ROOT_FOLDER_KEY: "legacy-root",
            IMA_PURE_GROUPS_KEY: old_raw,
        }
    )
    real_client = ima_documents.ImaPureClient

    class FakeClient(real_client):
        def _token(self):
            return "access"

        def _open_json(self, request):
            return (
                {field: value, "knowledge_base_list": [], "is_end": True},
                {},
            )

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    result = ImaDocumentService(db, tmp_path / "ima").discover()
    assert result["ok"] is False
    assert result["status"] == "failed"
    assert db.values[IMA_PURE_GROUPS_KEY] == old_raw


def test_sync_with_empty_registry_processes_no_groups(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB(
        {
            IMA_PURE_UID_KEY: "uid",
            IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
            IMA_PURE_KB_ID_KEY: "legacy-kb",
            IMA_PURE_ROOT_FOLDER_KEY: "legacy-root",
            IMA_PURE_GROUPS_KEY: "[]",
        }
    )
    clients = []

    class FakeClient:
        def __init__(self, config, group=None):
            clients.append(group)

        def discover_groups(self):
            return ()

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    result = service.sync_once()
    assert service.config().groups == ()
    assert result["status"] == "finished"
    assert result["groups"] == 0
    assert result["succeeded_groups"] == 0
    assert clients == [None]
    assert db.values[IMA_PURE_GROUPS_KEY] == "[]"


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


@pytest.mark.parametrize(
    "page_two",
    [
        {"retcode": 401},
        {"code": 0},
        {"code": 0, "knowledge_list": None},
        {"code": 0, "knowledge_list": {"media_id": "not-a-list"}},
        {"code": 0, "knowledge_list": [None]},
    ],
)
def test_list_items_rejects_malformed_later_page_status_or_payload(monkeypatch, page_two):
    client = ImaPureClient(
        ImaDocumentConfig(refresh_token="refresh", root_folder_id="root")
    )
    pages = iter([
        {"code": 0, "knowledge_list": [{"media_id": "first"}], "next_cursor": "next"},
        page_two,
    ])
    client._token = lambda: "access"
    client._open_json = lambda request: (next(pages), {})

    with pytest.raises(RuntimeError, match="IMA list"):
        client.list_items("root")


def test_list_items_retries_transient_code_30005(monkeypatch):
    client = ImaPureClient(
        ImaDocumentConfig(refresh_token="refresh", root_folder_id="root")
    )
    responses = iter([
        {"code": 30005},
        {"code": 0, "knowledge_list": []},
    ])
    sleeps = []
    client._token = lambda: "access"
    client._open_json = lambda request: (next(responses), {})
    monkeypatch.setattr("app.ima_documents.time.sleep", sleeps.append)

    assert client.list_items("root") == []
    assert sleeps == [1.5]


def test_knowledge_tab_reader_status_prefers_code_on_success(monkeypatch):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh", root_folder_id="root"))
    client._token = lambda: "access"
    client._open_json = lambda request: (
        {"code": "0", "retcode": 401, "knowledge_list": []},
        {},
    )
    assert client.list_items("root") == []

    client._open_json = lambda request: (
        {"code": "0", "retcode": 401, "knowledge_base_list": [], "is_end": True},
        {},
    )
    assert client.discover_groups() == ()


def test_knowledge_tab_reader_status_prefers_code_on_failure(monkeypatch):
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh", root_folder_id="root"))
    client._token = lambda: "access"
    client._open_json = lambda request: (
        {"code": 401, "retcode": "0", "knowledge_list": []},
        {},
    )
    with pytest.raises(RuntimeError, match="IMA list failed"):
        client.list_items("root")

    client._open_json = lambda request: (
        {"code": 401, "retcode": "0", "knowledge_base_list": [], "is_end": True},
        {},
    )
    with pytest.raises(RuntimeError, match="IMA group discovery failed"):
        client.discover_groups()


@pytest.mark.parametrize(
    "first_status, second_status",
    [("code", "retcode"), ("retcode", "code")],
)
def test_list_items_accepts_string_success_status_on_each_page(
    monkeypatch, first_status, second_status
):
    client = ImaPureClient(
        ImaDocumentConfig(refresh_token="refresh", root_folder_id="root")
    )
    pages = iter([
        {
            first_status: "0",
            "knowledge_list": [{"media_id": "first"}],
            "next_cursor": "next",
        },
        {second_status: "0", "knowledge_list": [{"media_id": "second"}]},
    ])
    client._token = lambda: "access"
    client._open_json = lambda request: (next(pages), {})

    assert [item["media_id"] for item in client.list_items("root")] == [
        "first", "second"
    ]


def test_list_items_accepts_empty_terminal_page(monkeypatch):
    client = ImaPureClient(
        ImaDocumentConfig(refresh_token="refresh", root_folder_id="root")
    )
    client._token = lambda: "access"
    client._open_json = lambda request: (
        {"code": 0, "knowledge_list": []},
        {},
    )

    assert client.list_items("root") == []


def test_list_items_folders_only_stops_after_file_page():
    client = ImaPureClient(
        ImaDocumentConfig(refresh_token="refresh", root_folder_id="root")
    )
    client._token = lambda: "access"
    pages = iter([
        {
            "code": 0,
            "knowledge_list": [
                {"media_type": 99, "folder_info": {"folder_id": "folder-a", "name": "A"}},
                {"media_id": "pdf_one"},
            ],
            "next_cursor": "p2",
        },
        {
            "code": 0,
            "knowledge_list": [{"media_id": "pdf_two"}],
            "next_cursor": "p3",
        },
        {
            "code": 0,
            "knowledge_list": [
                {"media_type": 99, "folder_info": {"folder_id": "folder-b", "name": "B"}},
            ],
        },
    ])
    seen = []

    def open_json(request):
        seen.append(json.loads(request.data))
        return next(pages), {}

    client._open_json = open_json
    items = client.list_items("root", folders_only=True)
    assert [item["folder_info"]["folder_id"] for item in items] == ["folder-a"]
    assert len(seen) == 2


def test_list_items_folders_only_respects_max_pages():
    client = ImaPureClient(
        ImaDocumentConfig(refresh_token="refresh", root_folder_id="root")
    )
    client._token = lambda: "access"
    pages = 0

    def open_json(request):
        nonlocal pages
        pages += 1
        return {
            "code": 0,
            "knowledge_list": [
                {"media_type": 99, "folder_info": {"folder_id": f"folder-{pages}", "name": str(pages)}},
            ],
            "next_cursor": f"p{pages}",
        }, {}

    client._open_json = open_json
    items = client.list_items("root", folders_only=True, max_pages=2)
    assert len(items) == 2
    assert pages == 2


def test_service_keeps_manifest_when_later_folder_page_is_malformed(tmp_path, monkeypatch):
    from app import ima_documents

    group = ImaGroupConfig(
        "group-a", "资料", "kb-a", "root-a", folder_ids=("root-a",), enabled=True
    )
    old_manifest = [{
        "media_id": "old-file",
        "name": "old.pdf",
        "day": "0825",
        "group_id": group.id,
    }]
    db = FakeDB({
        IMA_PURE_UID_KEY: "uid",
        IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
        IMA_PURE_KB_ID_KEY: "kb-a",
        IMA_PURE_ROOT_FOLDER_KEY: "root-a",
        IMA_PURE_GROUPS_KEY: json.dumps([group.public()], ensure_ascii=False),
    })

    class FakeClient(ima_documents.ImaPureClient):
        def discover_groups(self):
            return ()

        def _token(self):
            return "access"

        def _open_json(self, request):
            if json.loads(request.data).get("cursor"):
                return {"retcode": 401}, {}
            return {
                "code": 0,
                "knowledge_list": [{"media_id": "new-file"}],
                "next_cursor": "next",
            }, {}

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    service.store.save_manifest(old_manifest)
    old_pdf = service.store.pdf_path(old_manifest[0])
    old_txt = service.store.txt_path(old_manifest[0])
    old_pdf.parent.mkdir(parents=True)
    old_pdf.write_bytes(b"%PDF-1.7")
    old_txt.write_text("old", encoding="utf-8")
    service.store.save_state({
        service.store.state_key(old_manifest[0]): {
            "pdf": str(old_pdf.relative_to(service.store.root)),
            "txt": str(old_txt.relative_to(service.store.root)),
        }
    })

    result = service.sync_once()

    assert result["failed_groups"] == [group.id]
    assert service.store.load_manifest() == old_manifest


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
    assert client.list_items("root") == []
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


def test_safe_filename_fits_linux_name_max():
    title = "花旗-中国汽车制造：" + ("订单疲软预计资金流向切换" * 12) + ".pdf"
    name = safe_filename(title, "fallback")
    assert name.endswith(".pdf")
    assert len(name.encode("utf-8")) <= 255


def test_restore_recovers_state_when_title_file_already_moved(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    media_id = "pdf_e3acd95dd822029938ddb48d5e628c06"
    record = {"media_id": media_id, "name": "高盛-美图新AI产品.pdf", "day": "0801"}
    moved = store.pdf_path(record)
    moved.parent.mkdir(parents=True)
    moved.write_bytes(b"%PDF-1.7")
    moved.with_suffix(".txt").write_text("text", encoding="utf-8")
    store.save_manifest([record])
    store.save_state(
        {
            media_id: {
                "name": media_id,
                "day": "0801",
                "pdf": f"0801/{media_id}.pdf",
                "txt": f"0801/{media_id}.txt",
            }
        }
    )
    assert store.restore_original_filenames()["renamed"] == 0
    state = store.load_state()
    assert state[media_id]["pdf"] == "0801/高盛-美图新AI产品.pdf"
    assert state[media_id]["name"] == "高盛-美图新AI产品.pdf"
    assert moved.is_file()


def test_archive_uses_original_filename_when_unique(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "file_abc", "name": "中金-宏观周报.pdf", "day": "0825"}
    path = store.pdf_path(record)
    assert path.name == "中金-宏观周报.pdf"
    assert path.parent.name == "0825"
    assert "__" not in path.name


def test_archive_paths_are_unique_for_same_day_same_name(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    first = {"media_id": "file_first", "name": "report.pdf", "day": "0825"}
    second = {"media_id": "file_second", "name": "report.pdf", "day": "0825"}
    first_path = store.pdf_path(first)
    occupied = {str(first_path.relative_to(store.root))}
    second_path = store.pdf_path(second, occupied=occupied)
    assert first_path.name == "report.pdf"
    assert second_path != first_path
    assert second_path.parent == first_path.parent
    assert second_path.name.endswith(".pdf")


def test_restore_legacy_hashed_filenames_to_original_names(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "file_abc", "name": "中金-宏观周报.pdf", "day": "0825"}
    unique = hashlib.sha256(b"file_abc").hexdigest()[:16]
    hashed = store.root / "0825" / f"中金-宏观周报__{unique}.pdf"
    hashed.parent.mkdir(parents=True)
    hashed.write_bytes(b"%PDF-1.7")
    hashed.with_suffix(".txt").write_text("text", encoding="utf-8")
    store.save_manifest([record])
    store.save_state(
        {
            "file_abc": {
                "name": record["name"],
                "day": "0825",
                "pdf": f"0825/中金-宏观周报__{unique}.pdf",
                "txt": f"0825/中金-宏观周报__{unique}.txt",
            }
        }
    )

    result = store.restore_original_filenames()
    assert result["renamed"] == 1
    restored = store.pdf_path(record)
    assert restored.name == "中金-宏观周报.pdf"
    assert restored.is_file()
    assert restored.with_suffix(".txt").is_file()
    assert not hashed.exists()
    state = store.load_state()
    assert state["file_abc"]["pdf"] == "0825/中金-宏观周报.pdf"
    assert state["file_abc"]["txt"] == "0825/中金-宏观周报.txt"


def test_restore_keeps_remote_names_that_already_contain_double_underscore(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "file_abc", "name": "研报__终稿.pdf", "day": "0825"}
    path = store.pdf_path(record)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF-1.7")
    path.with_suffix(".txt").write_text("text", encoding="utf-8")
    store.save_manifest([record])
    store.save_state(
        {
            "file_abc": {
                "name": record["name"],
                "pdf": str(path.relative_to(store.root)),
                "txt": str(path.with_suffix(".txt").relative_to(store.root)),
            }
        }
    )
    assert store.restore_original_filenames()["renamed"] == 0
    assert path.name == "研报__终稿.pdf"
    assert path.is_file()


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


def test_completed_media_is_skipped_when_pdf_exists(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "file_abc", "name": "report.pdf", "day": "0825", "size": 4}
    pdf = store.pdf_path(record)
    pdf.parent.mkdir(parents=True)
    store.save_state({"file_abc": {"pdf": str(pdf.relative_to(store.root)), "txt": ""}})
    assert store.is_complete(record) is False
    pdf.write_bytes(b"%PDF-1.7")
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


@pytest.mark.parametrize(
    "message",
    [
        'upstream {"refresh_token":"json-refresh-secret"}',
        "refresh_token=equals-refresh-secret",
        "access_token: colon-access-secret",
        "authorization: Basic basic-auth-secret",
        "signature=signature-secret",
        '"sig":"json-sig-secret"',
        "sign=sign-secret",
        '"q-sign":"q-sign-secret"',
        "x-ima-cookie=x-ima-cookie-secret",
        "Cookie: SID=cookie-secret; Path=/",
        "Set-Cookie: IMA-TOKEN=set-cookie-secret; Path=/",
        'upstream {"Cookie":"SID=cookie-json-secret"}',
        'upstream {"Set-Cookie":"IMA-TOKEN=set-cookie-json-secret"}',
        "Bearer bearer-secret",
        "Basic basic-secret",
        "failed https://res-skb.ima.qq.com/a.pdf?sign=url-secret",
    ],
)
def test_safe_error_redacts_credential_shapes(message):
    text = _safe_error(RuntimeError(message))
    assert not any(secret in text for secret in message.split() if "secret" in secret)
    assert "<redacted>" in text or "<url>" in text


def test_safe_error_leaves_prefixed_header_names_unchanged():
    for message in (
        "my-cookie: public",
        "my-cookie=public",
        "my-set-cookie: public",
        "my-set-cookie=public",
        "my-authorization: Bearer public",
        "my-authorization=Bearer public",
    ):
        assert _safe_error(RuntimeError(message)) == message


def test_safe_error_leaves_prefixed_ordinary_keys_unchanged():
    for message in ("my-token=public", "my-signature=public", "my-x-ima-cookie=public"):
        assert _safe_error(RuntimeError(message)) == message


def test_error_summary_redacts_urls_and_credentials():
    text = _safe_error(RuntimeError("failed https://res-skb.ima.qq.com/a.pdf?sign=secret"))
    assert "res-skb.ima.qq.com" not in text
    assert "sign=secret" not in text
    assert "secret" not in _safe_error(RuntimeError("Authorization: Bearer secret"))
    assert "secret" not in _safe_error(RuntimeError("access_token=secret"))
    assert _safe_error(RuntimeError("token expired")) == "token expired"


def test_safe_error_redacts_standalone_basic_credential():
    text = _safe_error(RuntimeError("Basic dXNlcjpwYXNz"))
    assert "dXNlcjpwYXNz" not in text
    assert "<redacted>" in text
    text = _safe_error(RuntimeError("Authorization=Bearer authorization-secret"))
    assert "authorization-secret" not in text
    assert "<redacted>" in text


def test_safe_error_handles_empty_exception_messages():
    for error in (RuntimeError(""), RuntimeError("\nIMA request failed")):
        text = _safe_error(error)
        assert text == ""
        assert "\n" not in text
        assert len(text) <= 240


@pytest.mark.parametrize(
    ("slash_count", "secret"),
    [(1, "private-secret"), (3, "odd-private-secret")],
)
def test_safe_error_consumes_escaped_json_value(slash_count, secret):
    value = '{"access_token":"abc' + chr(92) * slash_count + f'" {secret}"}}'
    text = _safe_error(RuntimeError(value))
    assert secret not in text
    assert "<redacted>" in text


def test_safe_error_keeps_redaction_marker_whole_at_limit():
    text = _safe_error(RuntimeError("x" * 220 + " access_token=secret"))
    assert len(text) <= 240
    assert "secret" not in text
    assert "<redacted>" in text


def test_safe_error_keeps_url_marker_whole_at_limit():
    text = _safe_error(RuntimeError("x" * 235 + " https://secret.invalid/path"))
    assert len(text) <= 240
    assert "secret.invalid" not in text
    assert "<url>" in text


def _write_available_status(path, **overrides):
    payload = {
        "checked_at": int(time.time()),
        "available": True,
        "writable": True,
        "used_percent": 10,
        "inode_percent": 1,
        "monthly_tx_bytes": 10,
        "capacity_blocked": False,
        "reason": "",
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_archive_root_rejects_symlink(tmp_path):
    real_root = tmp_path / "real-ima"
    real_root.mkdir()
    link_root = tmp_path / "ima"
    link_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ValueError, match="root.*symlink"):
        ImaDocumentStore(link_root)


def test_separate_root_keeps_indexes_local_and_files_remote(tmp_path):
    index_root = tmp_path / "index"
    archive_root = tmp_path / "archive"
    marker = archive_root / ".vpush-ima-root"
    archive_root.mkdir()
    marker.touch()
    status_path = tmp_path / "status.json"
    _write_available_status(status_path)

    status = ImaStorageStatus(status_path, remote=True)
    store = ImaDocumentStore(index_root, archive_root=archive_root, storage_status=status)

    assert store.manifest_path == index_root.resolve() / "manifest.json"
    assert store.state_path == index_root.resolve() / "state.json"
    assert store.root == index_root.resolve()
    assert store.archive_root == archive_root.resolve()
    assert not (archive_root / "manifest.json").exists()
    assert not (archive_root / "state.json").exists()

    record = {
        "media_id": "file_abc",
        "name": "Report.pdf",
        "day": "0827",
        "group_id": "7476629605476515",
    }
    pdf = store.pdf_path(record)
    txt = store.txt_path(record)
    assert pdf.is_relative_to(archive_root.resolve())
    assert txt.is_relative_to(archive_root.resolve())
    assert not pdf.is_relative_to(index_root.resolve())

    relative_pdf = str(pdf.relative_to(store.archive_root))
    relative_txt = str(txt.relative_to(store.archive_root))
    assert not relative_pdf.startswith("/")
    assert relative_pdf.endswith("0827/Report.pdf") or relative_pdf.endswith("unknown/Report.pdf") or "/0827/Report.pdf" in relative_pdf
    store.save_manifest([record])
    store.save_state(
        {
            store.state_key(record): {
                "pdf": relative_pdf,
                "txt": relative_txt,
                "name": "Report.pdf",
                "day": "0827",
            }
        }
    )
    state = store.load_state()
    saved = state[store.state_key(record)]
    assert saved["pdf"] == relative_pdf
    assert saved["txt"] == relative_txt
    assert not saved["pdf"].startswith("/")
    assert store._state_path(saved["pdf"]) == pdf

    detail = store.document("file_abc", group_id="7476629605476515", groups=(
        ImaGroupConfig("7476629605476515", "远端", "kb", "root"),
    ))
    assert detail["has_pdf"] is True
    assert detail["has_txt"] is True
    assert detail["pdf"] is None
    assert detail["txt"] is None
    assert store.authorized_archive_file(saved["pdf"]) == pdf


def test_separate_root_symlink_archive_raises(tmp_path):
    index_root = tmp_path / "index"
    real_archive = tmp_path / "real-archive"
    real_archive.mkdir()
    (real_archive / ".vpush-ima-root").touch()
    archive_root = tmp_path / "archive"
    archive_root.symlink_to(real_archive, target_is_directory=True)
    status_path = tmp_path / "status.json"
    _write_available_status(status_path)
    status = ImaStorageStatus(status_path, remote=True)
    with pytest.raises(ValueError, match="root.*symlink"):
        ImaDocumentStore(index_root, archive_root=archive_root, storage_status=status)


def test_separate_root_missing_marker_blocks_without_mkdir(tmp_path):
    index_root = tmp_path / "index"
    archive_root = tmp_path / "archive"
    status_path = tmp_path / "status.json"
    _write_available_status(status_path)
    status = ImaStorageStatus(status_path, remote=True)
    store = ImaDocumentStore(index_root, archive_root=archive_root, storage_status=status)

    assert store.archive_readable() is False
    assert store.archive_writable() is False
    assert not archive_root.exists()
    assert index_root.exists()
    store.save_manifest([{"media_id": "file_abc", "name": "Report.pdf", "day": "0827"}])
    assert (index_root / "manifest.json").is_file()
    assert not archive_root.exists()


def test_local_single_root_construction_unchanged(tmp_path):
    root = tmp_path / "ima"
    store = ImaDocumentStore(root)
    assert store.root == root.resolve()
    assert store.archive_root == store.root
    assert store.archive_readable() is True
    assert store.archive_writable() is True
    record = {"media_id": "file_abc", "name": "Report.pdf", "day": "0827"}
    pdf = store.pdf_path(record)
    assert pdf.parent == (root / "0827").resolve()
    assert store.manifest_path.parent == store.root


def test_separate_root_partial_write_failure_and_recovery(tmp_path, monkeypatch):
    from app import ima_documents

    index_root = tmp_path / "index"
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    (archive_root / ".vpush-ima-root").touch()
    status_path = tmp_path / "status.json"
    _write_available_status(status_path)
    status = ImaStorageStatus(status_path, remote=True)

    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    service = ImaDocumentService(
        db,
        index_root,
        archive_root=archive_root,
        storage_status=status,
    )
    relative_holder = {}

    class FakeClient:
        def __init__(self, config, group=None):
            self.config = config

        def discover_groups(self):
            return ()

        def manifest(self):
            return [{"media_id": "file_abc", "name": "Report.pdf", "day": "0827", "size": 8}]

        def get_media(self, media_id):
            return {"jump_url_info": {"url": "https://download.invalid/report.pdf"}}

        def download(self, media, destination, expected_size=0):
            import os
            import tempfile
            from pathlib import Path

            destination.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                prefix=destination.name + ".", suffix=".part", dir=destination.parent
            )
            os.close(fd)
            temp = Path(temp_name)
            relative_holder["pdf"] = str(destination.relative_to(archive_root.resolve()))
            try:
                temp.write_bytes(b"%PDF-1.")
                raise OSError("disk full")
            except Exception:
                temp.unlink(missing_ok=True)
                raise

        @staticmethod
        def _pdf_info(path):
            return 8, "md5"

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    monkeypatch.setattr(
        ima_documents,
        "convert_pdf",
        lambda pdf, txt: (txt.write_text("text", encoding="utf-8") or 4),
    )

    first = service.sync_once()
    assert first["downloaded"] == 0
    assert first["failed"] >= 1
    pdf = archive_root / "0827" / "Report.pdf"
    assert not pdf.exists()
    assert list(archive_root.rglob("*.part")) == []
    assert service.store.is_complete({"media_id": "file_abc", "name": "Report.pdf", "day": "0827"}) is False

    class GoodClient(FakeClient):
        def download(self, media, destination, expected_size=0):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"%PDF-1.7")
            relative_holder["pdf"] = str(destination.relative_to(archive_root.resolve()))
            return {"size": 8, "md5": "md5"}

    monkeypatch.setattr(ima_documents, "ImaPureClient", GoodClient)
    second = service.sync_once()
    assert second["downloaded"] == 1
    assert pdf.is_file()
    state = service.store.load_state()
    assert state["file_abc"]["pdf"] == "0827/Report.pdf"
    assert state["file_abc"]["pdf"] == relative_holder["pdf"]
    assert not state["file_abc"]["pdf"].startswith("/")


def test_sync_blocked_when_archive_not_writable(tmp_path):
    index_root = tmp_path / "index"
    archive_root = tmp_path / "archive"
    archive_root.mkdir()
    (archive_root / ".vpush-ima-root").touch()
    status_path = tmp_path / "status.json"
    _write_available_status(status_path, available=False, writable=False)
    status = ImaStorageStatus(status_path, remote=True)
    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    service = ImaDocumentService(
        db,
        index_root,
        archive_root=archive_root,
        storage_status=status,
    )
    assert service.trigger()["status"] == "storage_unavailable"
    assert service.sync_once()["status"] == "storage_unavailable"


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
    assert listed.json()["items"] == []
    assert client.get("/api/ima-documents/file_abc", headers=user_headers).status_code == 404
    assert client.get("/api/ima-documents/file_abc/text", headers=user_headers).status_code == 404
    assert client.get("/api/ima-documents/file_abc/pdf", headers=user_headers).status_code == 404

    listed = client.get("/api/ima-documents", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["items"][0]["media_id"] == "file_abc"
    text_response = client.get("/api/ima-documents/file_abc/text", headers=admin_headers)
    assert text_response.text == "text"
    assert text_response.headers["content-type"].startswith("text/plain")
    pdf_response = client.get("/api/ima-documents/file_abc/pdf", headers=admin_headers)
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    download_response = client.get("/api/ima-documents/file_abc/pdf?download=1", headers=admin_headers)
    disposition = download_response.headers["content-disposition"]
    assert "attachment" in disposition
    assert "Report.pdf" in disposition
    assert client.get("/api/ima-documents/missing/text", headers=admin_headers).status_code == 404
    assert client.get("/api/ima-documents/../outside/text", headers=admin_headers).status_code in (404, 400)

    group_id = client.get("/api/admin/ima-collector", headers=admin_headers).json()["config"]["groups"][0]["id"]
    granted = client.put(
        f"/api/admin/ima-collector/groups/{group_id}/acl",
        headers=admin_headers,
        json={"usernames": ["ima_reader"]},
    )
    assert granted.status_code == 200, granted.text
    subscribed = client.post(
        f"/api/ima-documents/groups/{group_id}/subscribe",
        headers=user_headers,
    )
    assert subscribed.status_code == 200, subscribed.text
    assert client.get("/api/ima-documents/file_abc", headers=user_headers).status_code == 200

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
    headers = _headers(client, "group_reader", "GROUP001", admin=True)
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
        state[store.state_key(record)] = {
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
    assert client.get("/api/ima-documents/disabled-doc", headers=headers).status_code == 404
    assert client.get("/api/ima-documents?group=unknown", headers=headers).status_code == 404
    assert client.get("/api/ima-documents?group=disabled", headers=headers).status_code == 404
    assert client.get("/api/ima-documents").status_code == 401

    all_groups = client.get("/api/ima-documents", headers=headers)
    assert all_groups.status_code == 200
    assert {item["group_id"] for item in all_groups.json()["items"]} == {"banking"}
    assert client.get("/api/ima-documents?q=银行", headers=headers).json()["items"][0]["media_id"] == "banking-doc"
    assert client.get("/api/ima-documents?day=not-found", headers=headers).json()["items"] == []


def test_document_api_rejects_ambiguous_media_id_without_group(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    headers = _headers(client, "ima_ambiguous_reader", "IMAAMB01", admin=True)
    db = client.app.state.db
    db.set_setting(IMA_PURE_GROUPS_KEY, json.dumps([
        {"id": "group-a", "name": "一组资料", "knowledge_base_id": "kb-a", "root_folder_id": "root-a", "enabled": True},
        {"id": "group-b", "name": "二组资料", "knowledge_base_id": "kb-b", "root_folder_id": "root-b", "enabled": True},
        {"id": "disabled", "name": "停用资料", "knowledge_base_id": "kb-d", "root_folder_id": "root-d", "enabled": False},
    ], ensure_ascii=False))
    store = client.app.state.ima_documents.store
    records = [
        {"media_id": "shared-doc", "name": "一组.pdf", "day": "0825", "group_id": "group-a"},
        {"media_id": "shared-doc", "name": "二组.pdf", "day": "0825", "group_id": "group-b"},
        {"media_id": "disabled-doc", "name": "停用.pdf", "day": "0825", "group_id": "disabled"},
    ]
    state = {}
    for record in records:
        pdf, txt = store.pdf_path(record), store.txt_path(record)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.7")
        txt.write_text(record["group_id"], encoding="utf-8")
        state[store.state_key(record)] = {"group_id": record["group_id"], "pdf": str(pdf.relative_to(store.root)), "txt": str(txt.relative_to(store.root))}
    store.save_manifest(records)
    store.save_state(state)

    assert client.get("/api/ima-documents/shared-doc", headers=headers).status_code == 404
    assert client.get("/api/ima-documents/shared-doc?group=group-a", headers=headers).json()["group_id"] == "group-a"
    assert client.get("/api/ima-documents/shared-doc?group=group-b", headers=headers).json()["group_id"] == "group-b"
    assert client.get("/api/ima-documents/disabled-doc", headers=headers).status_code == 200
    assert client.get("/api/ima-documents/disabled-doc?group=disabled", headers=headers).status_code == 200


def test_document_store_namespaces_same_media_id_by_group(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    first = {"media_id": "shared", "name": "first.pdf", "day": "0825", "group_id": "group-a", "group_name": "一组"}
    second = {"media_id": "shared", "name": "second.pdf", "day": "0825", "group_id": "group-b", "group_name": "二组"}
    state = {}
    for record in (first, second):
        pdf, txt = store.pdf_path(record), store.txt_path(record)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.7")
        txt.write_text(record["group_id"], encoding="utf-8")
        state[store.state_key(record)] = {
            "group_id": record["group_id"],
            "pdf": str(pdf.relative_to(store.root)),
            "txt": str(txt.relative_to(store.root)),
            "size": 8,
            "chars": 7,
        }
    store.save_manifest([first, second])
    store.save_state(state)

    assert store.pdf_path(first) != store.pdf_path(second)
    assert store.is_complete(first, state) and store.is_complete(second, state)
    assert [item["group_id"] for item in store.documents(groups=(
        ImaGroupConfig("group-a", "一组", "kb-a", "root-a"),
        ImaGroupConfig("group-b", "二组", "kb-b", "root-b"),
    ))] == ["group-b", "group-a"]
    assert store.document("shared", group_id="group-a")["txt"].read_text(encoding="utf-8") == "group-a"
    assert store.document("shared", group_id="group-b")["txt"].read_text(encoding="utf-8") == "group-b"


def test_legacy_state_and_archive_paths_remain_compatible(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    record = {"media_id": "legacy-shared", "name": "legacy.pdf", "day": "0825", "group_id": IMA_LEGACY_GROUP_ID}
    pdf = store.pdf_path(record)
    txt = pdf.with_suffix(".txt")
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7")
    txt.write_text("legacy", encoding="utf-8")
    store.save_manifest([record])
    store.save_state({"legacy-shared": {"pdf": str(pdf.relative_to(store.root)), "txt": str(txt.relative_to(store.root))}})

    assert store.is_complete(record)
    assert store.document("legacy-shared")["txt"].read_text(encoding="utf-8") == "legacy"


def test_document_api_restricts_details_text_and_pdf_to_enabled_group(tmp_path, monkeypatch):
    monkeypatch.setenv("DAV_UI_ONLY", "1")
    client = TestClient(create_app(db_path=tmp_path / "db.sqlite"))
    headers = _headers(client, "ima_acl_reader", "IMAACL01", admin=True)
    db = client.app.state.db
    db.set_setting(IMA_PURE_GROUPS_KEY, json.dumps([
        {"id": "enabled", "name": "启用资料", "knowledge_base_id": "kb-e", "root_folder_id": "root-e", "enabled": True},
        {"id": "disabled", "name": "停用资料", "knowledge_base_id": "kb-d", "root_folder_id": "root-d", "enabled": False},
    ], ensure_ascii=False))
    store = client.app.state.ima_documents.store
    records = [
        {"media_id": "enabled-doc", "name": "enabled.pdf", "day": "0825", "group_id": "enabled"},
        {"media_id": "disabled-doc", "name": "disabled.pdf", "day": "0825", "group_id": "disabled"},
    ]
    state = {}
    for record in records:
        pdf, txt = store.pdf_path(record), store.txt_path(record)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.7")
        txt.write_text(record["group_id"], encoding="utf-8")
        state[store.state_key(record)] = {"group_id": record["group_id"], "pdf": str(pdf.relative_to(store.root)), "txt": str(txt.relative_to(store.root))}
    store.save_manifest(records)
    store.save_state(state)

    for suffix in ("", "/text", "/pdf"):
        assert client.get(f"/api/ima-documents/disabled-doc{suffix}?group=disabled", headers=headers).status_code == 200
        assert client.get(f"/api/ima-documents/enabled-doc{suffix}?group=enabled", headers=headers).status_code == 200
    assert client.get("/api/ima-documents/enabled-doc?group=disabled", headers=headers).status_code == 404
    assert client.get("/api/ima-documents/enabled-doc?group=unknown", headers=headers).status_code == 404


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


def test_folder_info_classifies_mixed_metadata_as_folder():
    item = {
        "folder_info": {"folder_id": "child", "name": "子目录"},
        "media_id": "metadata_1",
        "media_type": 1,
    }
    assert is_ima_folder_item(item)
    assert normalize_ima_folder_item(item, "root") == {
        "id": "child",
        "name": "子目录",
        "parent_id": "root",
        "has_children": None,
    }


def test_normalize_ima_folder_item_matches_folder_classification():
    assert normalize_ima_folder_item(
        {"folder_id": "metadata-folder", "media_id": "pdf_file", "name": "file.pdf"},
        "root",
    ) is None
    normalized = normalize_ima_folder_item(
        {
            "folder_info": {"folder_id": "child", "name": "子目录"},
            "media_id": "metadata_1",
        },
        "root",
    )
    assert normalized is not None
    assert normalized["id"] == "child"


def test_manifest_recurses_mixed_folder_metadata():
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh", root_folder_id="root"))
    responses = {
        "root": [
            {
                "folder_info": {"folder_id": "child", "name": "子目录"},
                "media_id": "metadata_1",
                "media_type": 1,
            }
        ],
        "child": [{"media_id": "pdf_child", "name": "child.pdf", "file_size": 8}],
    }
    calls = []
    client.list_items = lambda folder_id: calls.append(folder_id) or responses[folder_id]

    records = client.manifest()
    assert calls == ["root", "child"]
    assert [record["media_id"] for record in records] == ["pdf_child"]


def test_manifest_keeps_media_file_with_bare_folder_id():
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh", root_folder_id="root"))
    client.list_items = lambda folder_id: [
        {"media_id": "pdf_file", "folder_id": "metadata-folder", "name": "file.pdf", "file_size": 8}
    ]

    assert [record["media_id"] for record in client.manifest()] == ["pdf_file"]


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


def test_manifest_accepts_string_file_size():
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    responses = iter(
        [
            [{"media_type": 99, "folder_info": {"name": "0825", "folder_id": "day"}}],
            [
                {
                    "media_id": "pdf_abc123",
                    "title": "伯恩斯坦-优质潜艇三明治.pdf",
                    "file_size": "16491584",
                }
            ],
        ]
    )
    client.list_items = lambda folder_id: next(responses)
    records = client.manifest()
    assert records[0]["media_id"] == "pdf_abc123"
    assert records[0]["size"] == 16491584


def test_sync_keeps_existing_manifest_when_listing_empty(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    service = ImaDocumentService(db, tmp_path / "ima")
    service.store.save_manifest(
        [{"media_id": "pdf_old", "name": "old.pdf", "day": "0801", "group_id": IMA_LEGACY_GROUP_ID}]
    )

    class FakeClient:
        def __init__(self, config, group=None):
            self.group = group

        def discover_groups(self):
            return ()

        def manifest(self):
            return []

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    result = service.sync_once()
    assert result["total"] == 1
    assert [record["media_id"] for record in service.store.load_manifest()] == ["pdf_old"]


def test_rebuild_manifest_from_state_when_index_empty(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    media_id = "pdf_e3acd95dd822029938ddb48d5e628c06"
    record = {"media_id": media_id, "name": "高盛-美图新AI产品.pdf", "day": "0801"}
    pdf = store.pdf_path(record)
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7")
    store.save_state(
        {
            media_id: {
                "name": "高盛-美图新AI产品.pdf",
                "day": "0801",
                "pdf": str(pdf.relative_to(store.root)),
                "txt": str(pdf.with_suffix(".txt").relative_to(store.root)),
                "size": 8,
            }
        }
    )
    store.save_manifest([])
    assert store.load_manifest() == []
    assert store.rebuild_manifest_from_state() == 1
    restored = store.load_manifest()
    assert restored[0]["media_id"] == media_id
    assert restored[0]["name"] == "高盛-美图新AI产品.pdf"
    assert restored[0]["day"] == "0801"


def test_manifest_uses_chinese_title_as_filename():
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    responses = iter(
        [
            [{"media_type": 99, "folder_info": {"name": "0825", "folder_id": "day"}}],
            [
                {
                    "media_id": "pdf_abc123",
                    "title": "伯恩斯坦-优质潜艇三明治.pdf",
                    "file_size": 8,
                }
            ],
        ]
    )
    client.list_items = lambda folder_id: next(responses)
    records = client.manifest()
    assert records[0]["media_id"] == "pdf_abc123"
    assert records[0]["name"] == "伯恩斯坦-优质潜艇三明治.pdf"


def test_restore_renames_media_id_archive_to_chinese_title(tmp_path):
    store = ImaDocumentStore(tmp_path / "ima")
    media_id = "pdf_e3acd95dd822029938ddb48d5e628c06"
    unique = hashlib.sha256(media_id.encode("utf-8")).hexdigest()[:16]
    hashed = store.root / "0801" / f"{media_id}__{unique}.pdf"
    hashed.parent.mkdir(parents=True)
    hashed.write_bytes(b"%PDF-1.7")
    hashed.with_suffix(".txt").write_text("text", encoding="utf-8")
    record = {"media_id": media_id, "name": "高盛-美图新AI产品.pdf", "day": "0801"}
    store.save_manifest([record])
    store.save_state(
        {
            media_id: {
                "name": media_id,
                "day": "0801",
                "pdf": f"0801/{media_id}__{unique}.pdf",
                "txt": f"0801/{media_id}__{unique}.txt",
            }
        }
    )
    assert store.restore_original_filenames()["renamed"] == 1
    assert (store.root / "0801" / "高盛-美图新AI产品.pdf").is_file()
    assert not hashed.exists()
    state = store.load_state()
    assert state[media_id]["pdf"] == "0801/高盛-美图新AI产品.pdf"
    assert state[media_id]["name"] == "高盛-美图新AI产品.pdf"


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
    pdf = next((tmp_path / "ima").joinpath("0825").glob("*.pdf"))
    assert pdf.name == "Report.pdf"
    assert service.sync_once()["downloaded"] == 0
    assert calls == ["file_abc"]


def test_sync_retries_transient_pdf_failure_three_times(tmp_path, monkeypatch, caplog):
    from app import ima_documents

    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    calls = {"get_media": 0, "download": 0}
    sleeps = []

    class FakeClient:
        def __init__(self, config, group=None):
            self.config = config

        def manifest(self, listing_cache=None):
            return [{"media_id": "file_retry", "name": "retry.pdf", "day": "0829", "size": 8}]

        def get_media(self, media_id):
            calls["get_media"] += 1
            return {"jump_url_info": {"url": "https://res-skb.ima.qq.com/retry.pdf"}}

        def download(self, media, destination, expected_size=0):
            calls["download"] += 1
            if calls["download"] == 1:
                raise ConnectionResetError("connection reset while reading PDF")
            if calls["download"] == 2:
                raise RuntimeError("IMA PDF size mismatch got=7 expected=8")
            return {"size": 8, "md5": "d" * 32, "path": str(destination)}

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    monkeypatch.setattr(ima_documents.time, "sleep", sleeps.append)
    caplog.set_level("WARNING")
    result = ImaDocumentService(db, tmp_path / "ima").sync_once()

    assert calls == {"get_media": 3, "download": 3}
    assert sleeps == [2, 8]
    assert result["downloaded"] == 1
    assert "media=file_retry" in caplog.text
    assert "attempt=1/3" in caplog.text


def test_sync_does_not_retry_permanent_pdf_failure(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    calls = {"get_media": 0, "download": 0}

    class FakeClient:
        def __init__(self, config, group=None):
            self.config = config

        def manifest(self, listing_cache=None):
            return [{"media_id": "file_html", "name": "bad.pdf", "day": "0829", "size": 8}]

        def get_media(self, media_id):
            calls["get_media"] += 1
            return {"jump_url_info": {"url": "https://res-skb.ima.qq.com/bad.pdf"}}

        def download(self, media, destination, expected_size=0):
            calls["download"] += 1
            raise RuntimeError("IMA download is not a PDF")

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    result = ImaDocumentService(db, tmp_path / "ima").sync_once()

    assert calls == {"get_media": 1, "download": 1}
    assert result["downloaded"] == 0
    assert result["failed"] == 1


def test_sync_retries_get_media_after_pdf_http_403(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    calls = {"get_media": 0, "download": 0}

    class FakeClient:
        def __init__(self, config, group=None):
            self.config = config

        def manifest(self, listing_cache=None):
            return [{"media_id": "file_new", "name": "n.pdf", "day": "0829", "size": 8}]

        def get_media(self, media_id):
            calls["get_media"] += 1
            return {"jump_url_info": {"url": "https://res-skb.ima.qq.com/n.pdf", "headers": {}}}

        def download(self, media, destination, expected_size=0):
            calls["download"] += 1
            if calls["download"] == 1:
                raise RuntimeError("IMA PDF HTTP 403")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"%PDF-1.7")
            return {"size": 8, "md5": "d" * 32, "path": str(destination)}

        def _pdf_info(self, path):
            return 8, "d" * 32

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    result = service.sync_once()
    assert calls["get_media"] == 2
    assert calls["download"] == 2
    assert result["downloaded"] == 1


def test_download_worker_count_is_four():
    from app import ima_documents

    assert ima_documents.IMA_DOWNLOAD_WORKERS == 4


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


def test_sync_restores_legacy_hashed_files_without_redownload(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    unique = hashlib.sha256(b"file_abc").hexdigest()[:16]
    root = tmp_path / "ima"
    hashed = root / "0825" / f"Report__{unique}.pdf"
    hashed.parent.mkdir(parents=True)
    hashed.write_bytes(b"%PDF-1.7")
    hashed.with_suffix(".txt").write_text("text", encoding="utf-8")
    store = ImaDocumentStore(root)
    store.save_manifest([{"media_id": "file_abc", "name": "Report.pdf", "day": "0825", "size": 8}])
    store.save_state(
        {
            "file_abc": {
                "name": "Report.pdf",
                "day": "0825",
                "pdf": f"0825/Report__{unique}.pdf",
                "txt": f"0825/Report__{unique}.txt",
                "size": 8,
                "chars": 4,
            }
        }
    )

    class FakeClient:
        def __init__(self, config):
            self.config = config

        def manifest(self):
            return [{"media_id": "file_abc", "name": "Report.pdf", "day": "0825", "size": 8}]

        def get_media(self, media_id):
            raise AssertionError("completed legacy file must not redownload")

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, root)
    result = service.sync_once()
    assert result["downloaded"] == 0
    assert (root / "0825" / "Report.pdf").is_file()
    assert not hashed.exists()
    assert store.load_state()["file_abc"]["pdf"] == "0825/Report.pdf"


def test_service_discover_success_persists_new_unmounted_groups_and_failure_keeps_config(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB({
        IMA_PURE_UID_KEY: "uid",
        IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
        IMA_PURE_KB_ID_KEY: "kb-old",
        IMA_PURE_ROOT_FOLDER_KEY: "root-old",
        IMA_PURE_GROUPS_KEY: json.dumps([{
            "id": "old", "name": "旧库", "knowledge_base_id": "kb-old",
            "root_folder_id": "root-old", "folder_ids": ["keep"],
            "enabled": True, "source": "discovered",
        }]),
    })

    class FakeClient:
        def __init__(self, config, group=None):
            self.config = config

        def discover_groups(self):
            return (ImaGroupConfig("new", "新库", "kb-new", "root-new"),)

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    result = service.discover()
    assert result["status"] == "finished"
    saved = json.loads(db.get_setting(IMA_PURE_GROUPS_KEY))
    assert [row["id"] for row in saved] == ["new"]
    assert saved[0]["folder_ids"] == []
    assert saved[0]["enabled"] is False

    class BrokenClient(FakeClient):
        def discover_groups(self):
            raise RuntimeError('upstream {"refresh_token":"discovery-json-secret"}')

    monkeypatch.setattr(ima_documents, "ImaPureClient", BrokenClient)
    before = db.get_setting(IMA_PURE_GROUPS_KEY)
    failed = service.discover()
    assert failed["status"] == "failed"
    assert db.get_setting(IMA_PURE_GROUPS_KEY) == before
    discovery = json.loads(db.get_setting(IMA_PURE_DISCOVERY_KEY))
    assert discovery["error"] == failed["discovery"]["error"]
    assert "discovery-json-secret" not in discovery["error"]
    assert "<redacted>" in discovery["error"]


def test_service_skips_unmounted_group_without_sync_client(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB({
        IMA_PURE_UID_KEY: "uid", IMA_PURE_REFRESH_TOKEN_KEY: "refresh",
        IMA_PURE_KB_ID_KEY: "kb", IMA_PURE_ROOT_FOLDER_KEY: "root",
        IMA_PURE_GROUPS_KEY: json.dumps([{
            "id": "empty", "name": "空库", "knowledge_base_id": "kb",
            "root_folder_id": "root", "folder_ids": [], "enabled": False,
        }]),
    })
    calls = {"manifest": 0}

    class FakeClient:
        def __init__(self, config, group=None):
            self.group = group

        def discover_groups(self):
            return ()

        def manifest(self):
            calls["manifest"] += 1
            raise AssertionError("unmounted group must not scan")

    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    service = ImaDocumentService(db, tmp_path / "ima")
    service.store.save_manifest([{"media_id": "old", "group_id": "empty", "name": "old.pdf"}])
    result = service.sync_once()
    assert result["groups"] == 0
    assert result["skipped_groups"] == ["empty"]
    assert calls["manifest"] == 0
    assert service.store.load_manifest()[0]["media_id"] == "old"


def test_manifest_recurses_selected_folders_and_keeps_folder_metadata():
    group = ImaGroupConfig(
        "research", "研究", "kb", "root", True, "discovered", ("mount-a", "child-a")
    )
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    responses = {
        "mount-a": [
            {"media_id": "pdf_direct", "name": "直接.pdf", "file_size": 8},
            {"media_type": 99, "folder_info": {"folder_id": "child-a", "name": "0826"}},
        ],
        "child-a": [
            {"media_type": 99, "folder_info": {"folder_id": "child-b", "name": "研报"}},
        ],
        "child-b": [
            {"media_id": "pdf_nested", "name": "嵌套.pdf", "file_size": "9"},
        ],
    }
    calls = []

    def list_items(folder_id):
        calls.append(folder_id)
        return responses[folder_id]

    client.list_items = list_items

    records = client.manifest()
    assert {r["media_id"] for r in records} == {"pdf_direct", "pdf_nested"}
    direct = next(r for r in records if r["media_id"] == "pdf_direct")
    nested = next(r for r in records if r["media_id"] == "pdf_nested")
    assert direct["source_folder_id"] == "mount-a"
    assert nested["source_folder_id"] == "child-b"
    assert nested["source_root_folder_id"] == "mount-a"
    assert nested["folder_path"] == ["0826", "研报"]
    assert nested["day"] == "0826"
    assert calls.count("child-a") == 1
    assert calls.count("mount-a") == 1


def test_manifest_skips_cached_child_when_parent_counts_match():
    group = ImaGroupConfig("research", "研究", "kb", "root", True, "discovered", ("mount",))
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    responses = {
        "mount": [
            {"media_id": "pdf_root", "name": "a.pdf", "file_size": 8},
            {
                "media_type": 99,
                "folder_info": {"folder_id": "child", "name": "0826"},
                "file_number": 1,
                "folder_number": 0,
            },
        ],
        "child": [
            {"media_id": "pdf_child", "name": "b.pdf", "file_size": 8},
        ],
    }
    calls = []

    def list_items(folder_id):
        calls.append(folder_id)
        return list(responses[folder_id])

    client.list_items = list_items
    cache = {}
    first = client.manifest(listing_cache=cache)
    assert {item["media_id"] for item in first} == {"pdf_root", "pdf_child"}
    assert calls.count("mount") == 1
    assert calls.count("child") == 1
    calls.clear()
    second = client.manifest(listing_cache=cache)
    assert {item["media_id"] for item in second} == {"pdf_root", "pdf_child"}
    assert calls == ["mount"]
    responses["mount"][1]["file_number"] = 2
    responses["child"] = [
        {"media_id": "pdf_child", "name": "b.pdf", "file_size": 8},
        {"media_id": "pdf_new", "name": "c.pdf", "file_size": 8},
    ]
    calls.clear()
    third = client.manifest(listing_cache=cache)
    assert {item["media_id"] for item in third} == {"pdf_root", "pdf_child", "pdf_new"}
    assert "child" in calls


def test_manifest_deduplicates_overlapping_roots_and_stops_folder_cycles():
    group = ImaGroupConfig(
        "research", "研究", "kb", "root", True, "discovered", ("root-a", "root-b")
    )
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    responses = {
        "root-a": [
            {"media_type": 99, "folder_info": {"folder_id": "root-b", "name": "A"}},
            {"media_id": "pdf_same", "name": "同一份.pdf", "file_size": 8},
        ],
        "root-b": [
            {"media_type": 99, "folder_info": {"folder_id": "root-a", "name": "B"}},
            {"media_id": "pdf_same", "name": "同一份.pdf", "file_size": 8},
        ],
    }
    calls = []
    client.list_items = lambda folder_id: calls.append(folder_id) or responses[folder_id]
    records = client.manifest()
    assert [r["media_id"] for r in records] == ["pdf_same"]
    assert calls.count("root-a") == 1
    assert calls.count("root-b") == 1


def test_manifest_uses_unknown_day_for_non_date_folder_path():
    group = ImaGroupConfig("research", "研究", "kb", "root", True, "discovered", ("mount",))
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client.list_items = lambda folder_id: [{"media_id": "pdf_x", "name": "x.pdf", "file_size": 8}]
    record = client.manifest()[0]
    assert record["day"] == "unknown"
    assert record["folder_path"] == []


def test_manifest_uses_create_time_for_non_date_folder_path():
    group = ImaGroupConfig("research", "研究", "kb", "root", True, "discovered", ("mount",))
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client.list_items = lambda folder_id: [{
        "media_id": "pdf_x",
        "name": "x.pdf",
        "file_size": 8,
        "create_time": 1787155200000,
    }]
    record = client.manifest()[0]
    assert record["day"] == "0820"
    assert record["folder_path"] == []


def test_manifest_does_not_use_update_time_as_create_day():
    group = ImaGroupConfig("research", "研究", "kb", "root", True, "discovered", ("mount",))
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client.list_items = lambda folder_id: [{
        "media_id": "pdf_x",
        "name": "x.pdf",
        "file_size": 8,
        "update_time": 1787155200000,
    }]
    assert client.manifest()[0]["day"] == "unknown"


@pytest.mark.parametrize("create_time", [True, [], {}, "bad", float("inf")])
def test_manifest_keeps_pdf_with_invalid_create_time(create_time):
    group = ImaGroupConfig("research", "研究", "kb", "root", True, "discovered", ("mount",))
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client.list_items = lambda folder_id: [{
        "media_id": "pdf_x",
        "name": "x.pdf",
        "file_size": 8,
        "create_time": create_time,
    }]
    records = client.manifest()
    assert len(records) == 1
    assert records[0]["day"] == "unknown"


def test_group_folder_ids_distinguish_legacy_fallback_from_explicit_empty():
    legacy_db = FakeDB({
        IMA_PURE_GROUPS_KEY: json.dumps([{
            "id": "old", "name": "旧库", "knowledge_base_id": "kb",
            "root_folder_id": "root", "enabled": True,
        }])
    })
    legacy = ImaDocumentConfig.from_db(legacy_db).groups[0]
    assert legacy.folder_ids is None
    assert legacy.mount_folder_ids == ("root",)
    assert legacy.public()["folder_ids"] == ["root"]

    empty_db = FakeDB({
        IMA_PURE_GROUPS_KEY: json.dumps([{
            "id": "new", "name": "新库", "knowledge_base_id": "kb",
            "root_folder_id": "root", "folder_ids": [], "enabled": False,
        }])
    })
    empty = ImaDocumentConfig.from_db(empty_db).groups[0]
    assert empty.folder_ids == ()
    assert empty.mount_folder_ids == ()
    assert empty.public()["folder_ids"] == []
    assert empty.public()["mounted_folder_count"] == 0


def test_merge_groups_preserves_mounts_and_new_discovered_group_is_unmounted():
    existing = (
        ImaGroupConfig(
            "old", "旧名称", "kb-old", "root-old", True, "discovered",
            ("folder-kept",),
        ),
    )
    discovered = (
        ImaGroupConfig("old", "新名称", "kb-old", "root-new"),
        ImaGroupConfig("new", "新库", "kb-new", "root-new"),
    )
    merged = merge_groups(existing, discovered, discovery_complete=True)
    assert [(g.id, g.name, g.root_folder_id, g.mount_folder_ids) for g in merged] == [
        ("old", "新名称", "root-new", ("folder-kept",)),
        ("new", "新库", "root-new", ()),
    ]
    assert merged[1].enabled is False


def test_merge_groups_failed_discovery_keeps_stale_discovered_groups():
    existing = (ImaGroupConfig("gone", "旧库", "kb-gone", "root", True, "discovered", ("f",)),)
    assert merge_groups(existing, (), discovery_complete=False) == existing


def test_manifest_uses_ima_current_path_for_selected_root_day():
    group = ImaGroupConfig("research", "研究", "kb", "root", True, "discovered", ("mount",))
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client._token = lambda: "access"
    client._open_json = lambda request: ({
        "code": 0,
        "data": {
            "knowledge_list": [{
                "media_id": "pdf_x",
                "name": "x.pdf",
                "file_size": 8,
                "create_time": 1787155200000,
            }],
            "current_path": [{"folder_id": "mount", "name": "0806"}],
            "is_end": True,
        },
    }, {})
    record = client.manifest()[0]
    assert record["folder_path"] == ["0806"]
    assert record["day"] == "0806"


def test_discover_groups_rejects_success_payload_without_known_shape():
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    client._token = lambda: "access"
    client._open_json = lambda request: ({"code": 0, "data": {}}, {})
    with pytest.raises(RuntimeError, match="invalid response"):
        client.discover_groups()


def test_discovery_rejects_invalid_string_ids():
    with pytest.raises(RuntimeError, match="invalid"):
        normalize_discovered_groups({
            "knowledge_list": [{
                "id": "kb/bad", "name": "坏库", "root_folder_id": "root/bad",
            }]
        })


def test_manifest_rejects_folder_tree_depth_limit(monkeypatch):
    group = ImaGroupConfig("deep", "深目录", "kb", "root", True, "discovered", ("folder_0",))
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    responses = {
        f"folder_{index}": [{
            "media_type": 99,
            "folder_info": {"folder_id": f"folder_{index + 1}", "name": f"目录{index}"},
        }]
        for index in range(IMA_MAX_FOLDER_DEPTH + 2)
    }
    client.list_items = lambda folder_id: responses.get(folder_id, [])
    with pytest.raises(RuntimeError, match="maximum depth"):
        client.manifest()


def test_manifest_rejects_folder_tree_node_limit(monkeypatch):
    from app import ima_documents

    monkeypatch.setattr(ima_documents, "IMA_MAX_FOLDER_NODES", 2)
    group = ImaGroupConfig("wide", "宽目录", "kb", "root", True, "discovered", ("root",))
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"), group=group)
    client.list_items = lambda folder_id: (
        [{"media_type": 99, "folder_info": {"folder_id": "child-a", "name": "甲"}},
         {"media_type": 99, "folder_info": {"folder_id": "child-b", "name": "乙"}}]
        if folder_id == "root" else []
    )
    with pytest.raises(RuntimeError, match="maximum size"):
        client.manifest()


def test_download_posts_to_puller_when_url_configured(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    seen = {}

    class FakeResponse:
        def read(self):
            return json.dumps({"size": 8, "md5": "d" * 32}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=120):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        seen["body"] = json.loads(req.data.decode())
        return FakeResponse()

    monkeypatch.setenv("IMA_PULL_URL", "http://10.80.0.2:8743/pull")
    monkeypatch.setenv("IMA_PULL_TOKEN", "tok")
    monkeypatch.setenv("IMA_ARCHIVE_ROOT", str(archive))
    monkeypatch.setattr(ima_documents.urllib.request, "urlopen", fake_urlopen)
    client = ImaPureClient(ImaDocumentConfig(refresh_token="refresh"))
    dest = archive / "g" / "a.pdf"
    result = client.download(
        {
            "jump_url_info": {
                "url": "https://res-skb.ima.qq.com/file.pdf?sign=1",
                "headers": {"X-IMA-Sign": "sig"},
            }
        },
        dest,
        expected_size=8,
    )
    assert seen["url"] == "http://10.80.0.2:8743/pull"
    assert seen["auth"] == "Bearer tok"
    assert seen["body"]["dest"] == "g/a.pdf"
    assert seen["body"]["headers"]["X-IMA-Sign"] == "sig"
    assert result["size"] == 8
    assert result["md5"] == "d" * 32


def test_download_uses_cdn_when_pull_url_unset(tmp_path, monkeypatch):
    seen = {}

    class FakeResponse:
        def __init__(self):
            self._data = b"%PDF-1.7xxxx"

        def read(self, n):
            chunk = self._data[:n]
            self._data = self._data[n:]
            return chunk

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=120):
        seen["url"] = req.full_url
        return FakeResponse()

    monkeypatch.setenv("IMA_PULL_URL", "")
    monkeypatch.setattr(ima_documents.urllib.request, "urlopen", fake_urlopen)
    dest = tmp_path / "g" / "a.pdf"
    ImaPureClient(ImaDocumentConfig(refresh_token="refresh")).download(
        {
            "jump_url_info": {
                "url": "https://res-skb.ima.qq.com/file.pdf?sign=1",
                "headers": {"X-IMA-Sign": "sig"},
            }
        },
        dest,
    )
    assert seen["url"] == "https://res-skb.ima.qq.com/file.pdf?sign=1"
    assert "/pull" not in seen["url"]
    assert dest.read_bytes().startswith(b"%PDF-1.7")


def test_sync_redownloads_when_pull_url_set_even_if_file_exists(tmp_path, monkeypatch):
    from app import ima_documents

    db = FakeDB(
        {
            "ima_pure_uid": "uid",
            "ima_pure_refresh_token": "refresh",
            "ima_pure_knowledge_base_id": "kb",
            "ima_pure_root_folder_id": "root",
        }
    )
    calls = {"get_media": 0, "download": 0}
    record = {"media_id": "file_new", "name": "n.pdf", "day": "0829", "size": 8}

    class FakeClient:
        def __init__(self, config, group=None):
            self.config = config

        def manifest(self, listing_cache=None):
            return [dict(record)]

        def get_media(self, media_id):
            calls["get_media"] += 1
            return {"jump_url_info": {"url": "https://res-skb.ima.qq.com/n.pdf", "headers": {}}}

        def download(self, media, destination, expected_size=0):
            calls["download"] += 1
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"%PDF-1.7xxxx")
            return {"size": 12, "md5": "d" * 32, "path": str(destination)}

        def _pdf_info(self, path):
            return 8, "d" * 32

    archive = tmp_path / "ima"
    monkeypatch.setenv("IMA_PULL_URL", "http://10.80.0.2:8743/pull")
    monkeypatch.setenv("IMA_PULL_TOKEN", "tok")
    monkeypatch.setenv("IMA_ARCHIVE_ROOT", str(archive))
    monkeypatch.setattr(ima_documents, "ImaPureClient", FakeClient)
    monkeypatch.setattr(
        ima_documents,
        "convert_pdf",
        lambda pdf, txt: (txt.write_text("text", encoding="utf-8") or 4),
    )
    service = ImaDocumentService(db, archive)
    planted = service.store.pdf_path(record)
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_bytes(b"%PDF-1.7old!")
    assert planted.is_file()
    result = service.sync_once()
    assert calls["get_media"] >= 1
    assert calls["download"] >= 1
    assert result["downloaded"] == 1
