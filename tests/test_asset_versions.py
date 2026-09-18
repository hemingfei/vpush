from __future__ import annotations

from pathlib import Path

import pytest

from scripts import bump_assets


def make_tree(tmp_path: Path) -> Path:
    static = tmp_path / "app" / "static"
    (static / "core").mkdir(parents=True)
    (static / "vendor").mkdir()
    (static / "views").mkdir()
    (static / "style.css").write_text("body { color: black; }\n")
    (static / "vendor" / "design-tokens.css").write_text(":root { --color: black; }\n")
    (static / "app.js").write_text("import './core/html.js';\n")
    (static / "core" / "html.js").write_text("export const x = 1;\n")
    (static / "views" / "news.js").write_text("export const y = 2;\n")
    (static / "index.html").write_text(
        '  <!-- asset-importmap:start -->\n'
        '  <script type="importmap">{"imports":{}}</script>\n'
        '  <!-- asset-importmap:end -->\n'
        '<link rel="stylesheet" href="/vendor/design-tokens.css?v=old">\n'
        '<link rel="stylesheet" href="/style.css?v=old">\n'
        '<script type="module" src="/app.js?v=old"></script>\n'
    )
    (static / "sw.js").write_text(
        'const CACHE = "dav-shell-old";\n'
        'const SHELL = [\n'
        '  "/",\n'
        '  "/app.js",\n'
        '  // asset-modules:start\n'
        '  // asset-modules:end\n'
        '  "/style.css",\n'
        '  "/vendor/design-tokens.css",\n'
        '];\n'
    )
    return tmp_path


def test_sync_then_check(tmp_path: Path):
    root = make_tree(tmp_path)
    digest = bump_assets.sync_assets(root)
    assert len(digest) == 12
    assert bump_assets.check_consistency(root)
    html = (root / "app" / "static" / "index.html").read_text()
    style = bump_assets.hashed_url(root / "app" / "static" / "style.css", root)
    app_js = bump_assets.hashed_url(root / "app" / "static" / "app.js", root)
    html_js = bump_assets.hashed_url(root / "app" / "static" / "core" / "html.js", root)
    assert f'href="{style}"' in html
    assert f'src="{app_js}"' in html
    assert f'"/core/html.js":"{html_js}"' in html
    sw = (root / "app" / "static" / "sw.js").read_text()
    assert f'"{app_js}"' in sw
    assert f'"{html_js}"' in sw


def test_sync_is_deterministic(tmp_path: Path):
    root = make_tree(tmp_path)
    first = bump_assets.sync_assets(root)
    static = root / "app" / "static"
    before = {path: path.read_bytes() for path in (static / "index.html", static / "sw.js")}
    second = bump_assets.sync_assets(root)
    assert second == first
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize(
    "relative",
    [
        "app/static/style.css",
        "app/static/vendor/design-tokens.css",
        "app/static/app.js",
        "app/static/core/html.js",
        "app/static/views/news.js",
    ],
)
def test_changed_asset_fails_check(tmp_path: Path, relative: str):
    root = make_tree(tmp_path)
    bump_assets.sync_assets(root)
    path = root / relative
    path.write_bytes(path.read_bytes() + b"\n")
    assert not bump_assets.check_consistency(root)


@pytest.mark.parametrize(
    ("target_name", "old", "new", "message"),
    [
        ("index.html", '  <!-- asset-importmap:start -->\n', "", "import map"),
        ("index.html", '<link rel="stylesheet" href="/vendor/design-tokens.css?v=old">\n',
         "", "design-tokens.css reference"),
        ("index.html", '<link rel="stylesheet" href="/style.css?v=old">\n', "", "style.css reference"),
        ("index.html", '<script type="module" src="/app.js?v=old"></script>\n',
         '<script type="module" src="/app.js?v=old"></script>\n' * 2, "app.js reference"),
        ("sw.js", 'const CACHE = "dav-shell-old";\n', "", "service-worker cache"),
        ("sw.js", 'const CACHE = "dav-shell-old";\n',
         'const CACHE = "dav-shell-old";\n' * 2, "service-worker cache"),
        ("sw.js", '  "/app.js",\n', "", "service-worker app.js"),
    ],
)
def test_invalid_reference_does_not_write(
    tmp_path: Path, target_name: str, old: str, new: str, message: str
):
    root = make_tree(tmp_path)
    static = root / "app" / "static"
    target = static / target_name
    target.write_text(target.read_text().replace(old, new))
    before = {path: path.read_bytes() for path in (static / "index.html", static / "sw.js")}
    with pytest.raises(ValueError, match=message):
        bump_assets.sync_assets(root)
    assert {path: path.read_bytes() for path in before} == before


def test_replace_failure_rolls_back_both_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = make_tree(tmp_path)
    static = root / "app" / "static"
    targets = (static / "index.html", static / "sw.js")
    before = {path: path.read_bytes() for path in targets}
    real_replace = bump_assets.os.replace
    calls = 0

    def fail_second_replace(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second replace failure")
        real_replace(source, target)

    monkeypatch.setattr(bump_assets.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="simulated second replace failure"):
        bump_assets.sync_assets(root)
    assert {path: path.read_bytes() for path in targets} == before


def test_sync_populates_complete_module_shell(tmp_path: Path):
    root = make_tree(tmp_path)
    bump_assets.sync_assets(root)
    sw = (root / "app" / "static" / "sw.js").read_text()
    assert f'"{bump_assets.hashed_url(root / "app" / "static" / "core" / "html.js", root)}"' in sw
    assert f'"{bump_assets.hashed_url(root / "app" / "static" / "views" / "news.js", root)}"' in sw
