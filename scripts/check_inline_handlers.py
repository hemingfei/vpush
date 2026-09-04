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


def imported_exports(src: str) -> dict[str, tuple[str, str]]:
    imports: dict[str, tuple[str, str]] = {}
    for block, module in re.findall(r'import\s*\{([^}]+)\}\s*from\s*["\']([^"\']+)["\']', src, re.M):
        for part in block.split(","):
            bits = part.split()
            if not bits:
                continue
            imported, local = bits[0], bits[-1]
            imports[local] = (module, imported)
    return imports


def module_exports(src: str) -> set[str]:
    names = set(re.findall(rf"^export\s+(?:async\s+)?function\s+({IDENT})", src, re.M))
    names.update(re.findall(rf"^export\s+const\s+({IDENT})\s*=", src, re.M))
    for block in re.findall(r"^export\s*\{([^}]+)\}", src, re.M):
        for part in block.split(","):
            bits = part.split()
            if bits:
                names.add(bits[-1])
    return names


def factory_bindings(src: str) -> dict[str, tuple[str, str]]:
    bindings: dict[str, tuple[str, str]] = {}
    pattern = rf"const\s*\{{([^}}]+)\}}\s*=\s*({IDENT})\s*\("
    for block, factory in re.findall(pattern, src, re.M):
        for part in block.split(","):
            bits = part.strip().split(":", 1)
            prop = bits[0].strip()
            local = bits[-1].strip()
            if re.fullmatch(IDENT, prop) and re.fullmatch(IDENT, local):
                bindings[local] = (factory, prop)
    return bindings


def factory_return_names(src: str) -> set[str]:
    blocks = re.findall(r"^\s*return\s*\{([^}]*)\}", src, re.M)
    if not blocks:
        return set()
    return {
        part.split(":", 1)[0].strip()
        for part in blocks[-1].split(",")
        if re.fullmatch(IDENT, part.split(":", 1)[0].strip())
    }


def check(app_js: Path) -> int:
    src = app_js.read_text()
    keys = inline_keys(src)
    counts = Counter(parse_bindings(src))
    imports = imported_exports(src)
    missing_exports = []
    for key in keys:
        if key not in imports:
            continue
        module, imported = imports[key]
        path = (app_js.parent / module).resolve()
        if not path.is_file() or imported not in module_exports(path.read_text()):
            missing_exports.append(key)
    missing_factory_returns = []
    for key, (factory, prop) in factory_bindings(src).items():
        if key not in keys or factory not in imports:
            continue
        module, _ = imports[factory]
        path = (app_js.parent / module).resolve()
        if not path.is_file() or prop not in factory_return_names(path.read_text()):
            missing_factory_returns.append(key)
    missing = [k for k in keys if counts[k] == 0]
    dup = [k for k in keys if counts[k] > 1]
    if missing or dup or missing_exports or missing_factory_returns:
        if missing:
            print("missing:", ", ".join(missing))
        if dup:
            print("duplicate:", ", ".join(f"{k}×{counts[k]}" for k in dup))
        if missing_exports:
            print("missing export:", ", ".join(missing_exports))
        if missing_factory_returns:
            print("missing factory return:", ", ".join(missing_factory_returns))
        return 1
    print(f"ok: {len(keys)} handlers")
    return 0


if __name__ == "__main__":
    sys.exit(check(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_APP))
