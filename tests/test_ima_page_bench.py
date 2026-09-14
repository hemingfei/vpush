import importlib.util
import sys
from pathlib import Path


def load_benchmark_module():
    script = Path(__file__).parents[1] / "scripts" / "ima_page_bench.py"
    spec = importlib.util.spec_from_file_location("ima_page_bench_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_runs_use_fresh_connections(monkeypatch):
    module = load_benchmark_module()
    opened = []

    class FakeDB:
        def __init__(self):
            self.closed = False

        def _read_only_rows(self, _sql, _params=()):
            return []

        def ima_document_page(self, _groups, **_kwargs):
            return {"items": []}

        def close(self):
            self.closed = True

    def open_db(path, *, cold):
        db = FakeDB()
        opened.append((path, cold, db))
        return db

    monkeypatch.setattr(module, "open_benchmark_db", open_db)
    samples = module.run_benchmarks(
        "bench.sqlite", ["group"], cold=True, limit=50, offset=0, runs=2
    )

    assert len(samples) == 2
    assert [(path, cold) for path, cold, _db in opened] == [
        ("bench.sqlite", True),
        ("bench.sqlite", True),
        ("bench.sqlite", True),
        ("bench.sqlite", True),
    ]
    assert all(db.closed for _path, _cold, db in opened)


def test_main_prints_median_of_all_runs(monkeypatch, capsys):
    module = load_benchmark_module()
    monkeypatch.setattr(
        sys,
        "argv",
        ["ima_page_bench.py", "--groups", "group", "--runs", "3"],
    )
    monkeypatch.setattr(
        module,
        "run_benchmarks",
        lambda *_args, **_kwargs: [([], 1.0, 9.0), ([], 5.0, 5.0), ([], 9.0, 1.0)],
    )
    monkeypatch.setattr(module, "explain", lambda *_args: None)

    assert module.main() == 0
    output = capsys.readouterr().out
    assert "list p50=5.0 ms" in output
    assert "facets p50=5.0 ms" in output


def test_ima_page_bench_does_not_synthesize_api_json():
    source = (Path(__file__).parents[1] / "scripts" / "ima_page_bench.py").read_text()
    assert "json.dumps" not in source
    assert "api-shaped JSON" not in source
