#!/usr/bin/env python3
"""INLINE_HANDLERS 每个键必须能解析到唯一定义；漏挂或重名非零退出。"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP = ROOT / "app" / "static" / "app.js"
IDENT = r"[A-Za-z_][A-Za-z0-9_]*"


def _from_braces(src: str, prefix: str) -> list[str]:
    names: list[str] = []
    for block in re.findall(rf"{prefix}\s*\{{([^}}]+)\}}", src, re.M):
        for part in block.split(","):
            bits = part.replace("\n", " ").split()
            if not bits or bits[0] == "...":
                continue
            names.append(bits[-1] if "as" in bits else bits[0].strip())
    return [n for n in names if re.fullmatch(IDENT, n)]


def parse_bindings(src: str) -> list[str]:
    names = re.findall(rf"^(?:export\s+)?(?:async\s+)?function\s+({IDENT})", src, re.M)
    names += re.findall(rf"^(?:export\s+)?const\s+({IDENT})\s*=", src, re.M)
    names += _from_braces(src, r"^(?:export\s+|import\s+)")
    names += _from_braces(src, r"^const")
    return names


def inline_keys(src: str) -> list[str]:
    m = re.search(r"const INLINE_HANDLERS\s*=\s*\{([^}]+)\}", src)
    if not m:
        raise SystemExit("INLINE_HANDLERS not found")
    return re.findall(rf"({IDENT})\s*,", m.group(1))


def collect_module_names(static: Path) -> list[str]:
    names: list[str] = []
    for folder in (static / "core", static / "views"):
        if not folder.exists():
            continue
        for path in folder.rglob("*.js"):
            names.extend(parse_bindings(path.read_text()))
    return names


def check(app_js: Path) -> int:
    src = app_js.read_text()
    keys = inline_keys(src)
    counts = Counter(parse_bindings(src))
    collect_module_names(app_js.parent)  # parse core/views import+export
    missing = [k for k in keys if counts[k] == 0]
    dup = [k for k in keys if counts[k] > 1]
    if missing or dup:
        if missing:
            print("missing:", ", ".join(missing))
        if dup:
            print("duplicate:", ", ".join(f"{k}×{counts[k]}" for k in dup))
        return 1
    print(f"ok: {len(keys)} handlers")
    return 0


if __name__ == "__main__":
    sys.exit(check(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_APP))
