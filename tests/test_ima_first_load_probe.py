"""Acceptance tests for the IMA first-load performance probe."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.db import DB

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
SCRIPT = ROOT / "scripts" / "ima_first_load_probe.py"


def _row(group_id: str, number: int) -> dict:
    media_id = f"{group_id}-{number:04d}"
    name = f"{group_id} document {number:04d}.pdf"
    return {
        "group_id": group_id,
        "media_id": media_id,
        "day": f"09{number % 30 + 1:02d}",
        "valid_day": 1,
        "name": name,
        "group_name": group_id,
        "name_folded": name.casefold(),
        "metadata_folded": group_id,
        "abstract": "fixture abstract",
        "abstract_folded": "fixture abstract",
        "abstract_zh": "",
        "abstract_src_hash": "",
        "cover_url": "",
        "tags": [],
        "size": 0,
        "chars": 16,
        "has_pdf": 1,
        "has_txt": 0,
        "pdf_path": "",
        "txt_path": "",
        "downloaded_at": "2026-09-01T00:00:00+00:00",
    }


def _fixture_db(tmp_path: Path) -> Path:
    path = tmp_path / "ima-first-load.sqlite"
    db = DB(path)
    try:
        rows = [
            _row(group, number)
            for group in ("alpha", "beta", "gamma")
            for number in range(2000)
        ]
        db.replace_ima_document_index(rows, "acceptance", 1)
    finally:
        db.close()
    return path


def _run(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [str(PYTHON), str(SCRIPT), "--db", str(path), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


def test_first_load_probe_reports_real_fixture_metrics_and_plans(tmp_path):
    db_path = _fixture_db(tmp_path)
    source_before = db_path.read_bytes()
    result = _run(
        db_path,
        "--runs",
        "2",
        "--list-budget-ms",
        "100000",
        "--facets-budget-ms",
        "100000",
        "--hard-request-ceiling-ms",
        "100000",
    )

    assert result.returncode == 0, result.stderr + result.stdout
    report = result.stdout
    assert "db path:" in report
    assert "document count: 6000" in report
    assert "group count: 3" in report
    assert "requested group count: 3" in report
    assert "list runs (ms):" in report
    assert "facets runs (ms):" in report
    assert "list median (ms):" in report
    assert "facets median (ms):" in report
    assert "thresholds:" in report
    assert "EXPLAIN multi-group:" in report
    assert "idx_ima_doc_latest" in report
    assert "no TEMP B-TREE FOR ORDER BY" in report
    assert "warmup safety:" in report
    assert "empty index: 0" in report
    assert "populated/stale-like index: 1" in report
    assert db_path.read_bytes() == source_before

    selected = _run(
        db_path,
        "--groups",
        "alpha",
        "beta",
        "--runs",
        "1",
        "--list-budget-ms",
        "100000",
        "--facets-budget-ms",
        "100000",
        "--hard-request-ceiling-ms",
        "100000",
    )
    assert selected.returncode == 0, selected.stderr + selected.stdout
    assert "requested group count: 2" in selected.stdout
    assert db_path.read_bytes() == source_before


def test_first_load_probe_rejects_invalid_runs_and_failing_budget(tmp_path):
    db_path = _fixture_db(tmp_path)

    bad_runs = _run(db_path, "--runs", "0")
    assert bad_runs.returncode != 0
    assert "runs" in bad_runs.stderr.lower()

    impossible_budget = _run(
        db_path,
        "--runs",
        "1",
        "--list-budget-ms",
        "0",
        "--facets-budget-ms",
        "100000",
        "--hard-request-ceiling-ms",
        "100000",
    )
    assert impossible_budget.returncode != 0
    assert "list" in (impossible_budget.stdout + impossible_budget.stderr).lower()
