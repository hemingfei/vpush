import base64
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.ima_documents import (
    IMA_PURE_GROUPS_KEY,
    ImaDocumentConfig,
    ImaDocumentService,
    ImaDocumentStore,
    ImaGroupConfig,
    ImaPureClient,
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
            id="legacy:legacy-kb:legacy-root",
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
            id="legacy:legacy-kb:legacy-root",
            name="IMA 文档",
            knowledge_base_id="legacy-kb",
            root_folder_id="legacy-root",
        ),
    )


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
