from pathlib import Path

from scripts.check_inline_handlers import check, collect_module_names, parse_bindings


def _tree(tmp_path: Path, app: str, views: str | None = None, core: str | None = None) -> Path:
    static = tmp_path / "static"
    (static / "views").mkdir(parents=True)
    (static / "core").mkdir(parents=True)
    (static / "app.js").write_text(app)
    if views:
        (static / "views" / "sample.js").write_text(views)
    if core:
        (static / "core" / "html.js").write_text(core)
    return static / "app.js"


def test_ok_local_and_imported_handler(tmp_path: Path):
    app = _tree(
        tmp_path,
        'import { wired } from "./views/sample.js";\n'
        "function localFn() {}\n"
        "const INLINE_HANDLERS = { wired, localFn, };\n",
        "export function wired() {}\n",
    )
    names = parse_bindings(app.read_text())
    assert "localFn" in names and "wired" in names
    assert "wired" in collect_module_names(app.parent)
    assert check(app) == 0


def test_missing_handler_fails(tmp_path: Path, capsys):
    app = _tree(
        tmp_path,
        "function localFn() {}\n"
        "const INLINE_HANDLERS = { localFn, ghost, };\n",
    )
    assert check(app) == 1
    assert "missing: ghost" in capsys.readouterr().out


def test_duplicate_handler_fails(tmp_path: Path, capsys):
    app = _tree(
        tmp_path,
        "function dup() {}\n"
        "const { dup } = factory();\n"
        "const INLINE_HANDLERS = { dup, };\n",
    )
    assert check(app) == 1
    assert "duplicate: dup×2" in capsys.readouterr().out
