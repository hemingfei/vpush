from pathlib import Path

from scripts.check_platform_badges import check


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def _copy_surface(tmp_path: Path) -> Path:
    static = tmp_path / "static"
    (static / "core").mkdir(parents=True)
    for relative in ("app.js", "style.css", "core/platforms.js"):
        target = static / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((STATIC / relative).read_text())
    return static


def test_current_platform_badges_pass_contract():
    assert check(STATIC) == []


def test_ci_runs_platform_badge_contract():
    workflow = (ROOT / ".github" / "workflows" / "docker-publish.yml").read_text()
    assert "python scripts/check_platform_badges.py" in workflow


def test_rejects_duplicate_platform_configuration(tmp_path):
    static = _copy_surface(tmp_path)
    with (static / "app.js").open("a") as f:
        f.write('\nconst PLATFORM_LABELS = { truth: "Truth" };\n')
    assert any("平台配置只能定义在 core/platforms.js" in error for error in check(static))


def test_rejects_platform_configuration_in_another_module(tmp_path):
    static = _copy_surface(tmp_path)
    (static / "core" / "rogue.js").write_text('const PLATFORM_ICONS = { truth: "T" };\n')
    assert any("平台配置只能定义在 core/platforms.js" in error for error in check(static))


def test_rejects_unapproved_image_badge(tmp_path):
    static = _copy_surface(tmp_path)
    platforms = static / "core/platforms.js"
    platforms.write_text(platforms.read_text().replace(
        "const TRUTH_ICON = `<svg",
        'const TRUTH_ICON = `<img class="pt-icon" src="/truth.svg"><svg',
    ))
    assert any("仅雪球允许使用图片角标" in error for error in check(static))


def test_rejects_platform_specific_selected_style(tmp_path):
    static = _copy_surface(tmp_path)
    with (static / "style.css").open("a") as f:
        f.write('\n.tl-pill[data-platform="truth"].selected { color: red; }\n')
    assert any("禁止平台专属选中态" in error for error in check(static))
