import json
from pathlib import Path

from app.db import DB
from app.ima_documents import IMA_PURE_GROUPS_KEY, ImaDocumentService
from app.ima_title_zh import refresh_bank_titles_zh


def test_refresh_bank_titles_zh_writes_override_and_index(tmp_path):
    db = DB(str(tmp_path / "zh.sqlite"))
    archive = tmp_path / "archive"
    group_dir = archive / "bank1__xx"
    group_dir.mkdir(parents=True)
    db.set_setting(
        IMA_PURE_GROUPS_KEY,
        json.dumps(
            [
                {
                    "id": "bank1",
                    "name": "全球顶级投行研报库",
                    "knowledge_base_id": "kb",
                    "root_folder_id": "root",
                    "folder_ids": ["root"],
                    "enabled": True,
                }
            ]
        ),
    )
    service = ImaDocumentService(db, tmp_path / "ima", archive_root=archive)
    rec = {
        "group_id": "bank1",
        "media_id": "m1",
        "name": "Goldman Sachs-Foo-260801.pdf",
        "day": "0801",
    }
    service.store.save_manifest([rec])
    service.store.save_state({service.store.state_key(rec): {"pdf": "bank1/a.pdf"}})
    assert service.rebuild_read_index()["status"] == "ready"
    n = refresh_bank_titles_zh(
        service,
        llm_config=object(),
        chat=lambda titles: ["高盛-测试公司-260801.pdf" for _ in titles],
    )
    assert n == 1
    row = db._rows("SELECT name FROM ima_document_index WHERE media_id = ?", ("m1",))[0]
    assert row["name"].startswith("高盛")
    overrides = json.loads((group_dir / "titles.json").read_text(encoding="utf-8"))
    assert "Goldman Sachs-Foo-260801" in overrides


def test_refresh_bank_titles_zh_skips_without_llm(tmp_path):
    db = DB(str(tmp_path / "zh2.sqlite"))
    service = ImaDocumentService(db, tmp_path / "ima", archive_root=tmp_path / "archive")
    assert refresh_bank_titles_zh(service, llm_config=object(), chat=lambda titles: titles) == 0
