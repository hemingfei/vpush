import json
from types import SimpleNamespace

from app.db import DB
from app.ima_documents import IMA_PURE_GROUPS_KEY, ImaDocumentService
from app.ima_title_zh import refresh_bank_titles_zh


def make_bank_service(tmp_path, rows):
    db = DB(str(tmp_path / "zh.sqlite"))
    archive = tmp_path / "archive"
    group_dir = archive / "bank1__xx"
    group_dir.mkdir(parents=True)
    db.set_setting(IMA_PURE_GROUPS_KEY, json.dumps([{
        "id": "bank1",
        "name": "全球顶级投行研报库",
        "knowledge_base_id": "kb",
        "root_folder_id": "root",
        "folder_ids": ["root"],
        "enabled": True,
    }]))
    service = ImaDocumentService(db, tmp_path / "ima", archive_root=archive)
    records = [
        {"group_id": "bank1", "media_id": media_id, "name": name, "day": "0801"}
        for media_id, name in rows
    ]
    service.store.save_manifest(records)
    service.store.save_state({})
    assert service.rebuild_read_index()["status"] == "ready"
    return service, group_dir


def test_refresh_bank_titles_zh_writes_override_and_index(tmp_path):
    service, group_dir = make_bank_service(
        tmp_path, [("m1", "Goldman Sachs-Foo-260801.pdf")]
    )
    n = refresh_bank_titles_zh(
        service,
        llm_config=object(),
        chat=lambda titles: ["高盛-测试公司-260801.pdf" for _ in titles],
    )
    assert n == 1
    row = service.db._rows("SELECT name FROM ima_document_index WHERE media_id = ?", ("m1",))[0]
    assert row["name"].startswith("高盛")
    overrides = json.loads((group_dir / "titles.json").read_text(encoding="utf-8"))
    assert "Goldman Sachs-Foo-260801" in overrides


def test_refresh_bank_titles_zh_skips_without_llm(tmp_path):
    db = DB(str(tmp_path / "zh2.sqlite"))
    service = ImaDocumentService(db, tmp_path / "ima", archive_root=tmp_path / "archive")
    assert refresh_bank_titles_zh(service, llm_config=object(), chat=lambda titles: titles) == 0


def test_refresh_translates_duplicate_stem_once_and_updates_all_rows(tmp_path):
    service, group_dir = make_bank_service(
        tmp_path,
        [
            ("m1", "Goldman-Foo-260801.pdf"),
            ("m2", "Goldman-Foo-260801.pdf"),
        ],
    )
    calls = []

    def chat(titles):
        calls.append(titles)
        return ["高盛-测试公司.pdf"]

    assert refresh_bank_titles_zh(service, llm_config=object(), chat=chat) == 2
    assert calls == [["Goldman-Foo-260801.pdf"]]
    names = [row["name"] for row in service.db._rows(
        "SELECT name FROM ima_document_index ORDER BY media_id"
    )]
    assert names == ["高盛-测试公司-260801.pdf", "高盛-测试公司-260801.pdf"]


def test_refresh_uses_injected_site_llm_config(tmp_path):
    service, _ = make_bank_service(tmp_path, [("m1", "Goldman-Foo-260801.pdf")])
    service.llm_config = SimpleNamespace(
        api_key="site-key",
        api_base="https://llm.example.com/v1",
        model="site-model",
    )
    seen = []
    assert refresh_bank_titles_zh(
        service,
        chat=lambda titles: seen.append(titles) or ["高盛-测试-260801.pdf"],
    ) == 1
    assert seen


def test_refresh_stops_after_first_failed_batch(tmp_path):
    rows = [(f"m{i}", f"Goldman-Foo-{i:06d}.pdf") for i in range(25)]
    service, _ = make_bank_service(tmp_path, rows)
    calls = []
    assert refresh_bank_titles_zh(
        service,
        llm_config=object(),
        chat=lambda titles: calls.append(titles) or None,
    ) == 0
    assert len(calls) == 1
