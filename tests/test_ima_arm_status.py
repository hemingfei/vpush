from app.ima_documents import arm_status_libraries


def test_arm_status_uses_stored_group_results():
    rows = arm_status_libraries(
        [],
        {"legacy": {"last_finished_at": 100}},
        {"group_results": [{
            "id": "legacy",
            "name": "投行",
            "downloaded": 5,
            "failed": 1,
            "error": "list failed code=30021",
        }]},
    )
    assert rows == [{
        "id": "legacy",
        "name": "投行",
        "downloaded": 5,
        "failed": 1,
        "finished_at": 100,
        "error": "list failed code=30021",
    }]


def test_arm_status_falls_back_to_download_window():
    seen = {}

    def count(group_id, started, finished):
        seen["args"] = (group_id, started, finished)
        return 12

    rows = arm_status_libraries(
        [
            {"id": "legacy", "name": "投行", "enabled": True},
            {"id": "local-cicc-research", "name": "中金", "enabled": True},
            {"id": "off", "name": "停用", "enabled": False},
        ],
        {"legacy": {"last_started_at": 10, "last_finished_at": 20}},
        {"group_errors": {"legacy": "busy"}, "failed_groups": []},
        download_count=count,
    )
    assert seen["args"] == ("legacy", 10, 20)
    assert len(rows) == 1
    assert rows[0]["downloaded"] == 12
    assert rows[0]["failed"] == 0
    assert rows[0]["error"] == "busy"


def test_cicc_row_uses_last_ingest_stamp():
    from app.ima_documents import cicc_status_row

    row = cicc_status_row("2026-09-22T10:11:50.395376+00:00", 24, name="中金公司研报")
    assert row["id"] == "local-cicc-research"
    assert row["name"] == "中金公司研报"
    assert row["downloaded"] == 24
    assert row["finished_at"] > 0
