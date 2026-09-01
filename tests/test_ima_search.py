import sqlite3
import threading
from pathlib import Path

import app.ima_search as ima_search
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


def _writer_connection(index: ImaSearchIndex, factory) -> sqlite3.Connection:
    connection = sqlite3.connect(index.path, timeout=5, factory=factory)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


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


def test_sync_streams_each_changed_body_into_the_transaction(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    first = archive / "first.txt"
    second = archive / "second.txt"
    first.write_text("first searchable body", encoding="utf-8")
    second.write_text("second searchable body", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))
    written: list[str] = []

    class TrackingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            result = super().execute(sql, parameters)
            if sql.startswith("INSERT INTO documents "):
                written.append(parameters[1])
            return result

    monkeypatch.setattr(
        index,
        "_connect",
        lambda *, readonly=False: _writer_connection(index, TrackingConnection),
    )
    original_open = Path.open

    def tracked_open(path, *args, **kwargs):
        if path == second:
            assert written == ["first"]
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", tracked_open)

    result = index.sync([
        _row("semi", "first", "first.txt"),
        _row("semi", "second", "second.txt"),
    ])

    assert result["updated"] == 2
    assert written == ["first", "second"]


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
    dml_done = threading.Event()
    allow_commit = threading.Event()
    original_connect = index._connect

    class PausingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            result = super().execute(sql, parameters)
            if sql.startswith("INSERT INTO documents "):
                dml_done.set()
                assert allow_commit.wait(2), "sync transaction was not released"
            return result

    def controlled_connect(*, readonly=False):
        if readonly:
            return original_connect(readonly=True)
        return _writer_connection(index, PausingConnection)

    monkeypatch.setattr(index, "_connect", controlled_connect)
    outcome = {}

    def run_sync():
        outcome["result"] = index.sync([changed])

    worker = threading.Thread(target=run_sync)
    worker.start()
    assert dml_done.wait(2), "sync did not execute transactional DML"
    overlapping = index.search("previous committed", ["semi"], 10)
    allow_commit.set()
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


def test_sync_bounds_body_bytes_and_indexes_only_the_prefix(tmp_path, monkeypatch):
    assert ima_search.MAX_BODY_BYTES == 8 * 1024 * 1024
    monkeypatch.setattr(ima_search, "MAX_BODY_BYTES", 64)
    archive = tmp_path / "archive"
    archive.mkdir()
    prefix = b"searchable prefix " + b"x" * (64 - len(b"searchable prefix "))
    (archive / "large.txt").write_bytes(prefix + b" beyond-limit-marker")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))

    assert index.sync([_row("semi", "large", "large.txt")])["updated"] == 1
    assert index.search("searchable prefix", ["semi"], 10)[0]["media_id"] == "large"
    assert index.search("beyond-limit-marker", ["semi"], 10) == []
    with index._connect(readonly=True) as connection:
        stored = connection.execute(
            "SELECT body FROM documents WHERE media_id = 'large'"
        ).fetchone()[0]
    assert "beyond-limit-marker" not in stored
    assert len(stored.encode()) <= 64


def test_oversized_query_is_truncated_before_fts(tmp_path):
    assert ima_search.MAX_QUERY_CHARS == 256
    archive = tmp_path / "archive"
    archive.mkdir()
    prefix = "cashflow" + "x" * (ima_search.MAX_QUERY_CHARS - len("cashflow"))
    (archive / "report.txt").write_text(prefix, encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))
    index.sync([_row("semi", "report", "report.txt")])

    results = index.search(prefix + "y" * 1000, ["semi"], 10)

    assert results[0]["media_id"] == "report"


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


def test_full_text_search_matches_body_column_only(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "title.txt").write_text("unrelated body", encoding="utf-8")
    (archive / "body.txt").write_text("quantum interconnect demand", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))

    index.sync([
        _row("semi", "title-only", "title.txt", name="Quantum interconnect outlook"),
        _row("semi", "body-only", "body.txt", name="Unrelated report"),
    ])

    assert [item["media_id"] for item in index.search(
        "quantum interconnect", ["semi"], 10
    )] == ["body-only"]


def test_full_text_search_supports_bounded_offset_pages(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    rows = []
    for index_value in range(3):
        filename = f"body-{index_value}.txt"
        (archive / filename).write_text("ranked body phrase", encoding="utf-8")
        rows.append(_row("semi", f"body-{index_value}", filename))
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))
    index.sync(rows)

    assert [item["media_id"] for item in index.search(
        "ranked body", ["semi"], 1, offset=1
    )] == ["body-1"]


def test_full_text_search_unready_index_returns_empty(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "report.txt").write_text("quantum interconnect demand", encoding="utf-8")
    path = tmp_path / "ima-search.db"
    index = ImaSearchIndex(path, archive, ("semi",))
    index.sync([_row("semi", "report", "report.txt")])
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE search_meta SET ready = 0 WHERE id = 1")
        connection.commit()

    unready = ImaSearchIndex(path, archive, ("semi",))

    assert unready.status()["ready"] is False
    assert unready.search("quantum interconnect", ["semi"], 10) == []


def test_sync_failure_keeps_last_good_index_and_reports_error(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    archive.mkdir()
    body = archive / "report.txt"
    body.write_text("supply chain normalization", encoding="utf-8")
    index = ImaSearchIndex(tmp_path / "ima-search.db", archive, ("semi",))
    row = _row("semi", "report", "report.txt")
    assert index.sync([row])["indexed"] == 1
    good_status = index.status()
    assert good_status["ready"] is True
    assert good_status["documents"] == 1
    assert good_status["last_sync_at"]
    assert good_status["error"] == ""

    body.write_text("updated demand outlook", encoding="utf-8")
    changed = {**row, "downloaded_at": "2026-09-02T00:00:00+00:00"}
    original_connect = index._connect

    class FailingAfterDmlConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            result = super().execute(sql, parameters)
            if sql.startswith("INSERT INTO documents "):
                raise sqlite3.OperationalError("simulated failure after DML")
            return result

    def controlled_connect(*, readonly=False):
        if readonly:
            return original_connect(readonly=True)
        return _writer_connection(index, FailingAfterDmlConnection)

    with monkeypatch.context() as patch:
        patch.setattr(index, "_connect", controlled_connect)
        result = index.sync([changed])

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
    assert "simulated failure after DML" in failed_status["error"]
    assert index.search("supply chain", ["semi"], 10)[0]["media_id"] == "report"
    assert index.search("updated demand", ["semi"], 10) == []


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
