#!/usr/bin/env python3
"""Validate the single-source platform badge contract."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PLATFORMS = {"", "xueqiu", "combination", "weibo", "twitter", "zsxq", "truth", "mx", "system"}
ALIASES = {
    "PLATFORM_LABELS": '{ ...PLATFORM_LABELS_CONFIG, ima: "ima" }',
    "PLATFORM_SHORT_LABELS": '{ ...PLATFORM_SHORT_LABELS_CONFIG, ima: "ima" }',
    "PLATFORM_ICONS": "PLATFORM_ICONS_CONFIG",
    "PLATFORM_TABS": "PLATFORM_TABS_CONFIG",
}


def check(static: Path = ROOT / "app" / "static") -> list[str]:
    app = (static / "app.js").read_text()
    platforms = (static / "core" / "platforms.js").read_text()
    css = (static / "style.css").read_text()
    errors: list[str] = []

    javascript = {
        path.relative_to(static).as_posix(): path.read_text()
        for path in static.rglob("*.js")
    }
    for name, value in ALIASES.items():
        expected = f"const {name} = {value};"
        definitions = [
            relative
            for relative, source in javascript.items()
            for _ in re.finditer(rf"(?:export\s+)?const\s+{name}\s*=", source)
        ]
        if app.count(f"const {name} =") != 1 or expected not in app or sorted(definitions) != ["app.js", "core/platforms.js"]:
            errors.append(f"平台配置只能定义在 core/platforms.js：{name}")

    badge_block = re.search(r"export const PLATFORM_BADGES = \{(.*?)\n\};", platforms, re.S)
    keys = set(re.findall(r'^\s*(?:"([^"]*)"|([a-z]+)):\s*\{', badge_block.group(1) if badge_block else "", re.M))
    actual = {quoted or bare for quoted, bare in keys}
    if actual != EXPECTED_PLATFORMS:
        errors.append(f"平台清单不完整：{sorted(actual)}")

    if any('<img class="pt-icon"' in source for relative, source in javascript.items() if relative != "core/platforms.js"):
        errors.append("角标图形只能定义在 core/platforms.js")
    images = re.findall(r'<img class="pt-icon"[^>]*>', platforms)
    if images or "<image" in platforms or "data:image" in platforms:
        errors.append("平台角标必须使用内联矢量 SVG")
    if "filter:" in platforms:
        errors.append("平台配置不得自行定义滤镜")

    selectors = re.findall(r"([^{}]+)\{", re.sub(r"/\*.*?\*/", "", css, flags=re.S))
    selected_platform_rules = []
    for selector_group in selectors:
        for selector in selector_group.split(","):
            selector = selector.replace(":not(.selected)", "")
            if "[data-platform=" in selector and ".selected" in selector and "::after" not in selector:
                selected_platform_rules.append(selector)
    if selected_platform_rules:
        errors.append("禁止平台专属选中态")
    return errors


def main() -> int:
    errors = check()
    if errors:
        print("\n".join(f"error: {error}" for error in errors))
        return 1
    print("platform badges: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
