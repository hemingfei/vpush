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


def test_missing_import_export_fails(tmp_path: Path, capsys):
    app = _tree(
        tmp_path,
        'import { ghost } from "./views/sample.js";\n'
        "const INLINE_HANDLERS = { ghost, };\n",
        "export function wired() {}\n",
    )
    assert check(app) == 1
    assert "missing export: ghost" in capsys.readouterr().out


def test_missing_factory_return_fails(tmp_path: Path, capsys):
    app = _tree(
        tmp_path,
        'import { createView } from "./views/sample.js";\n'
        "const { ghost } = createView({});\n"
        "const INLINE_HANDLERS = { ghost, };\n",
        "export function createView() {\n"
        "  function ghost() {}\n"
        "  return {};\n"
        "}\n",
    )
    assert check(app) == 1
    assert "missing factory return: ghost" in capsys.readouterr().out


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


def test_inline_called_but_unexposed_fails(tmp_path: Path, capsys):
    """模板 on* 内联事件里调用的名字必须挂在 INLINE_HANDLERS 上，否则点击报 undefined。"""
    app = _tree(
        tmp_path,
        "function exposed() {}\n"
        "function hidden() {}\n"
        "const INLINE_HANDLERS = { exposed, };\n"
        'const html = `<a onclick="event.preventDefault();hidden(1)">x</a>`;\n',
    )
    assert check(app) == 1
    out = capsys.readouterr().out
    assert "unexposed" in out
    assert "hidden" in out


def test_inline_called_and_exposed_passes(tmp_path: Path):
    app = _tree(
        tmp_path,
        "function shown() {}\n"
        "const INLINE_HANDLERS = { shown, };\n"
        'const html = `<a onclick="event.preventDefault();shown(1)">x</a>`;\n',
    )
    assert check(app) == 0


def test_inline_template_interpolation_ignored(tmp_path: Path):
    """${...} 是拼接期执行的代码（模块作用域可见），不算点击期引用。"""
    app = _tree(
        tmp_path,
        "function shown() {}\n"
        "function helper(v) { return v; }\n"
        "const INLINE_HANDLERS = { shown, };\n"
        'const html = `<a onclick="shown(\'${helper(1)}\')">x</a>`;\n',
    )
    assert check(app) == 0
