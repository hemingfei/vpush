import sqlite3
import threading
from pathlib import Path

from app.ima_search import ImaSearchIndex


def _row(
    group_id: str,
    media_id: str,
    txt_path: str,
    *,
    name: str = "Research note",
    downloaded_at: str = "2026-09-01T00:00:00+00:00",
    chars: int = 100,
) -> dict:
    return {
        "group_id": group_id,
        "media_id": media_id,
        "name": name,
        "group_name": "SemiAnalysis",
        "metadata_folded": "semiconductor ai",
        "abstract": "Public abstract",
        "tags_json": '["AI", "chips"]',
        "txt_path": txt_path,
        "downloaded_at": downloaded_at,
        "chars": chars,
    }


def test_disabled_index_does_not_create_database(tmp_path):
    path = tmp_path / "ima-search.db"
    index = ImaSearchIndex(path, tmp_path / "archive", ())

    assert index.enabled is False
    assert index.sync([]) == {
        "indexed": 0,
        "updated": 0,
        "skipped": 0,
        "removed": 0,
        "missing": 0,
    }
    assert index.search("cash flow", ["semi"], 10) == []
    assert index.status() == {
        "enabled": False,
        "ready": False,
        "documents": 0,
        "last_sync_at": "",
        "error": "",
    }
    assert not path.exists()


def test_sync_filters_groups_and_skips_missing_or_escaping_paths(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "valid.txt").write_text("Free cash flow inflected higher.", encoding="utf-8")
    (tmp_path / "escape.txt").write_text("must not be indexed", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))

    result = index.sync([
        _row("semi", "valid", "valid.txt"),
        _row("semi", "missing", "missing.txt"),
        _row("semi", "escape", "../escape.txt"),
        _row("other", "other", "valid.txt"),
    ])

    assert result == {
        "indexed": 1,
        "updated": 1,
        "skipped": 1,
        "removed": 0,
        "missing": 2,
    }
    assert [item["media_id"] for item in index.search("cash flow", ["semi"], 10)] == ["valid"]
    assert index.search("must not", ["semi"], 10) == []


def test_identical_sync_does_not_reread_and_changed_source_updates(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    body = archive / "report.txt"
    body.write_text("Capital expenditure is increasing.", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))
    row = _row("semi", "report", "report.txt")

    assert index.sync([row])["updated"] == 1
    body.unlink()
    unchanged = index.sync([row])
    assert unchanged["updated"] == 0
    assert unchanged["skipped"] == 1
    assert unchanged["missing"] == 0
    assert index.search("capital expenditure", ["semi"], 10)[0]["media_id"] == "report"

    body.write_text("Supply chain constraints have eased.", encoding="utf-8")
    changed = {**row, "downloaded_at": "2026-09-02T00:00:00+00:00", "chars": 120}
    assert index.sync([changed])["updated"] == 1
    assert index.search("capital expenditure", ["semi"], 10) == []
    assert index.search("supply chain", ["semi"], 10)[0]["media_id"] == "report"


def test_sync_and_search_overlap_serves_a_committed_version(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    body = archive / "report.txt"
    body.write_text("Previous committed margin outlook.", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))
    row = _row("semi", "report", "report.txt")
    assert index.sync([row])["updated"] == 1

    body.write_text("Updated committed supply outlook.", encoding="utf-8")
    changed = {**row, "downloaded_at": "2026-09-02T00:00:00+00:00"}
    read_started = threading.Event()
    allow_read = threading.Event()
    original_read_text = Path.read_text

    def controlled_read_text(path, *args, **kwargs):
        if path == body:
            read_started.set()
            assert allow_read.wait(2), "sync body read was not released"
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", controlled_read_text)
    outcome = {}

    def run_sync():
        outcome["result"] = index.sync([changed])

    worker = threading.Thread(target=run_sync)
    worker.start()
    assert read_started.wait(2), "sync did not reach the controlled body read"
    overlapping = index.search("previous committed", ["semi"], 10)
    allow_read.set()
    worker.join(2)

    assert not worker.is_alive()
    assert [item["media_id"] for item in overlapping] == ["report"]
    assert outcome["result"]["updated"] == 1
    assert index.search("previous committed", ["semi"], 10) == []
    assert index.search("updated committed", ["semi"], 10)[0]["media_id"] == "report"


def test_sync_removes_configured_documents_absent_from_next_input(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "one.txt").write_text("gross margin expansion", encoding="utf-8")
    (archive / "two.txt").write_text("gross margin contraction", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))

    first = index.sync([
        _row("semi", "one", "one.txt"),
        _row("semi", "two", "two.txt"),
    ])
    assert first["indexed"] == 2

    second = index.sync([_row("semi", "one", "one.txt")])
    assert second["indexed"] == 1
    assert second["removed"] == 1
    assert [item["media_id"] for item in index.search("gross margin", ["semi"], 10)] == ["one"]


def test_database_uses_wal_busy_timeout_and_trigram_fts(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "report.txt").write_text("artificial intelligence", encoding="utf-8")
    path = tmp_path / "ima-search.db"
    index = ImaSearchIndex(path, archive, ("semi",))
    index.sync([_row("semi", "report", "report.txt")])

    with index._connect(readonly=True) as connection:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'documents_fts'"
        ).fetchone()[0]
    assert "tokenize='trigram'" in schema


def test_search_enforces_acl_short_query_rules_and_plain_snippets(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "semi.txt").write_text(
        "<script>alert('x')</script><p>Free cash flow improved materially.</p>",
        encoding="utf-8",
    )
    (archive / "private.txt").write_text("Free cash flow remained weak.", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi", "private"))
    index.sync([
        _row("semi", "semi-report", "semi.txt"),
        _row("private", "private-report", "private.txt"),
    ])

    assert index.search("", ["semi"], 10) == []
    assert index.search("估值", ["semi"], 10) == []
    assert index.search("cash flow", [], 10) == []
    assert index.search("cash flow", ["other"], 10) == []
    results = index.search("cash flow", ["semi"], 10)

    assert len(results) == 1
    assert set(results[0]) == {"group_id", "media_id", "score", "search_snippet"}
    assert results[0]["group_id"] == "semi"
    assert results[0]["media_id"] == "semi-report"
    assert isinstance(results[0]["score"], float)
    assert "cash flow" in results[0]["search_snippet"].casefold()
    assert "<script>" not in results[0]["search_snippet"]
    assert "<p>" not in results[0]["search_snippet"]
    assert len(results[0]["search_snippet"]) <= 240


def test_sync_failure_keeps_last_good_index_and_reports_error(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "report.txt").write_text("supply chain normalization", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))
    row = _row("semi", "report", "report.txt")
    assert index.sync([row])["indexed"] == 1
    good_status = index.status()
    assert good_status["ready"] is True
    assert good_status["documents"] == 1
    assert good_status["last_sync_at"]
    assert good_status["error"] == ""

    def broken_connect(*args, **kwargs):
        raise sqlite3.OperationalError("simulated sync failure")

    with monkeypatch.context() as patch:
        patch.setattr("app.ima_search.sqlite3.connect", broken_connect)
        result = index.sync([row])

    assert result == {
        "indexed": 1,
        "updated": 0,
        "skipped": 0,
        "removed": 0,
        "missing": 0,
    }
    failed_status = index.status()
    assert failed_status["enabled"] is True
    assert failed_status["ready"] is True
    assert failed_status["documents"] == 1
    assert failed_status["last_sync_at"] == good_status["last_sync_at"]
    assert "simulated sync failure" in failed_status["error"]
    assert index.search("supply chain", ["semi"], 10)[0]["media_id"] == "report"


def test_search_database_failure_returns_empty_and_preserves_last_good_index(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "report.txt").write_text("free cash flow recovery", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))
    row = _row("semi", "report", "report.txt")
    assert index.sync([row])["indexed"] == 1
    good_status = index.status()
    original_connect = index._connect

    def fail_readonly_connect(*, readonly=False):
        if readonly:
            raise sqlite3.OperationalError("simulated search failure")
        return original_connect(readonly=readonly)

    with monkeypatch.context() as patch:
        patch.setattr(index, "_connect", fail_readonly_connect)
        assert index.search("cash flow", ["semi"], 10) == []
        failed_status = index.status()

    assert failed_status["ready"] is True
    assert failed_status["documents"] == 1
    assert failed_status["last_sync_at"] == good_status["last_sync_at"]
    assert "simulated search failure" in failed_status["error"]
    assert index.search("cash flow", ["semi"], 10)[0]["media_id"] == "report"
