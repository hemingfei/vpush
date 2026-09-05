#!/usr/bin/env python3
"""INLINE_HANDLERS 每个键必须能解析到唯一定义；漏挂或重名非零退出。

同时反向校验：模板 HTML 里 on* 内联事件处理器调用到的标识符必须都挂在
INLINE_HANDLERS 上（模块作用域函数对内联 onclick 不可见，漏挂即点击报
「X is not defined」）。
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_APP = ROOT / "app" / "static" / "app.js"
IDENT = r"[A-Za-z_$][A-Za-z0-9_$]*"

# 内联处理器里合法出现的非应用标识符：关键字与 JS 内建全局。
# 应用函数一个都不该出现在这里——内联 onclick 只能调 window 上的东西
INLINE_GLOBALS = frozenset({
    "if", "else", "return", "new", "typeof", "function", "void",
    "event", "this", "arguments", "window", "document", "navigator", "location", "history",
    "alert", "confirm", "prompt", "open", "close", "focus", "blur", "print", "stop",
    "encodeURIComponent", "decodeURIComponent", "parseInt", "parseFloat", "isNaN",
    "String", "Number", "Boolean", "Array", "Object", "JSON", "Math", "Date", "RegExp",
    "Set", "Map", "Promise", "Error", "TypeError", "Symbol", "BigInt",
    "console", "fetch", "URL", "URLSearchParams", "Blob", "File", "FileReader", "FormData",
    "AbortController", "CustomEvent", "Event", "KeyboardEvent", "MouseEvent",
    "crypto", "btoa", "atob", "structuredClone", "queueMicrotask",
    "setTimeout", "clearTimeout", "setInterval", "clearInterval", "requestAnimationFrame",
    "getComputedStyle", "matchMedia", "alert",
})


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


INLINE_ATTR_RE = re.compile(r"""\bon[a-z]+\s*=\s*(?:"([^"]*)"|'([^']*)')""")
CALL_RE = re.compile(rf"(?<![\w$.])({IDENT})\s*\(")


def inline_html_calls(static: Path) -> dict[str, set[str]]:
    """扫描模板 HTML 里 on* 内联属性调用到的标识符 → 引用它的文件集合。

    ${...} 模板插值是拼接时（构建期）执行的代码，不是点击时执行的，先剔除；
    方法调用 obj.fn() 的 fn 不是全局引用（正则负向断言已排除带点前缀的名字）。
    """
    files = [static / "app.js", static / "index.html"]
    files += sorted((static / "core").rglob("*.js"))
    files += sorted((static / "views").rglob("*.js"))
    found: dict[str, set[str]] = {}
    for path in files:
        if not path.is_file():
            continue
        for attr in INLINE_ATTR_RE.findall(path.read_text(encoding="utf-8")):
            value = attr[0] or attr[1]
            value = re.sub(r"\$\{[^}]*\}", "", value)
            for name in CALL_RE.findall(value):
                if name not in INLINE_GLOBALS:
                    found.setdefault(name, set()).add(path.name)
    return found


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
    keys_set = set(keys)
    called = inline_html_calls(app_js.parent)
    unexposed = {name: files for name, files in called.items() if name not in keys_set}
    if missing or dup or missing_exports or missing_factory_returns or unexposed:
        if missing:
            print("missing:", ", ".join(missing))
        if dup:
            print("duplicate:", ", ".join(f"{k}×{counts[k]}" for k in dup))
        if missing_exports:
            print("missing export:", ", ".join(missing_exports))
        if missing_factory_returns:
            print("missing factory return:", ", ".join(missing_factory_returns))
        if unexposed:
            print("unexposed (called in inline on* handlers but not in INLINE_HANDLERS):")
            for name, files in sorted(unexposed.items()):
                print(f"  {name}  <- {', '.join(sorted(files))}")
        return 1
    print(f"ok: {len(keys)} handlers, {len(called)} inline-referenced names all exposed")
    return 0


if __name__ == "__main__":
    sys.exit(check(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_APP))
