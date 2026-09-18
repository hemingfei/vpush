"""Content-hashed static asset URLs so Cloudflare can long-cache JS/CSS.

Source files stay at stable names (`app.js`, `style.css`, `core/*.js`).
`index.html` / `sw.js` point at `/name.<sha256-12>.ext`. The static mount
maps those URLs back to the source file and sends immutable cache headers.
HTML, SPA fallback, `sw.js`, and web manifests stay on short revalidation.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

DIGEST_LEN = 12
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
REVALIDATE_CACHE_CONTROL = "no-cache"
HASHED_ASSET_RE = re.compile(
    rf"^(?P<stem>.+)\.(?P<digest>[0-9a-f]{{{DIGEST_LEN}}})\.(?P<ext>js|css)$"
)
# HTML / 未哈希 JS/CSS 每次校验，避免用户卡在旧前端。
# manifest 也必须重新校验：WebAPK 安装时 Chrome 会取它烤入状态栏色，
# 命中旧缓存会把浅色 theme_color 烤进安装包（卸载重装也救不回来）。
REVALIDATE_SUFFIXES = (".html", ".js", ".css", ".webmanifest", ".json")
IMPORTMAP_BLOCK_RE = re.compile(
    r"  <!-- asset-importmap:start -->[\s\S]*?  <!-- asset-importmap:end -->"
)
MODULE_BLOCK_RE = re.compile(r"  // asset-modules:start[\s\S]*?  // asset-modules:end")
TOKENS_HREF_RE = (
    r'href="/vendor/design-tokens(?:\.[0-9a-f]{' + str(DIGEST_LEN) + r'})?\.css(?:\?v=[^"]+)?"'
)
STYLE_HREF_RE = (
    r'href="/style(?:\.[0-9a-f]{' + str(DIGEST_LEN) + r'})?\.css(?:\?v=[^"]+)?"'
)
APP_SRC_RE = r'src="/app(?:\.[0-9a-f]{' + str(DIGEST_LEN) + r'})?\.js(?:\?v=[^"]+)?"'
SW_APP_RE = r'  "/app(?:\.[0-9a-f]{' + str(DIGEST_LEN) + r'})?\.js",'
SW_STYLE_RE = r'  "/style(?:\.[0-9a-f]{' + str(DIGEST_LEN) + r'})?\.css",'
SW_TOKENS_RE = (
    r'  "/vendor/design-tokens(?:\.[0-9a-f]{' + str(DIGEST_LEN) + r'})?\.css",'
)

ROOT = Path(__file__).resolve().parent.parent
STATIC_REL = Path("app/static")


def static_dir(root: Path = ROOT) -> Path:
    return root / STATIC_REL


def asset_paths(root: Path = ROOT) -> list[Path]:
    static = static_dir(root)
    paths = [
        static / "style.css",
        static / "app.js",
        static / "vendor" / "design-tokens.css",
    ]
    paths += sorted((static / "core").glob("**/*.js")) if (static / "core").exists() else []
    paths += sorted((static / "views").glob("**/*.js")) if (static / "views").exists() else []
    missing = [path for path in paths[:3] if not path.is_file()]
    if missing:
        raise ValueError("missing required assets: " + ", ".join(map(str, missing)))
    return sorted(set(paths), key=lambda path: path.relative_to(root).as_posix())


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:DIGEST_LEN]


@functools.lru_cache(maxsize=512)
def _digest_for(path: str, mtime_ns: int, size: int) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:DIGEST_LEN]


def cached_file_digest(path: Path) -> str:
    stat = path.stat()
    return _digest_for(str(path), stat.st_mtime_ns, stat.st_size)


def asset_digest(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in asset_paths(root):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(relative + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()[:DIGEST_LEN]


def hashed_url(path: Path, root: Path = ROOT) -> str:
    relative = path.relative_to(static_dir(root))
    name = f"{path.stem}.{file_digest(path)}{path.suffix}"
    if relative.parent == Path("."):
        return f"/{name}"
    return f"/{relative.parent.as_posix()}/{name}"


def logical_url(path: Path, root: Path = ROOT) -> str:
    return "/" + path.relative_to(static_dir(root)).as_posix()


def module_urls(root: Path = ROOT) -> list[str]:
    return [
        hashed_url(path, root)
        for path in asset_paths(root)
        if path.suffix == ".js" and path.name != "app.js"
    ]


def import_map_imports(root: Path = ROOT) -> dict[str, str]:
    return {
        logical_url(path, root): hashed_url(path, root)
        for path in asset_paths(root)
        if path.suffix == ".js" and path.name != "app.js"
    }


def import_map_block(root: Path = ROOT) -> str:
    payload = json.dumps({"imports": import_map_imports(root)}, separators=(",", ":"), sort_keys=True)
    return (
        "  <!-- asset-importmap:start -->\n"
        f'  <script type="importmap">{payload}</script>\n'
        "  <!-- asset-importmap:end -->"
    )


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one reference, found {count}")
    return updated


def resolve_fingerprinted_path(static: Path, request_path: str) -> str | None:
    """Map `/name.<hash>.ext` back to `name.ext` when the hash matches current bytes."""
    normalized = request_path.replace("\\", "/").lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        return None
    match = HASHED_ASSET_RE.match(normalized)
    if not match:
        return None
    logical = f"{match.group('stem')}.{match.group('ext')}"
    if ".." in logical.split("/"):
        return None
    try:
        static_resolved = static.resolve()
        full = (static / logical).resolve()
    except OSError:
        return None
    if not full.is_file() or not full.is_relative_to(static_resolved):
        return None
    if cached_file_digest(full) != match.group("digest"):
        return None
    return logical


def should_revalidate(path: str) -> bool:
    lowered = path.replace("\\", "/").lower().strip("/")
    if not lowered or lowered == "index.html":
        return True
    return lowered.endswith(REVALIDATE_SUFFIXES)


def rendered_targets(root: Path = ROOT) -> dict[Path, str]:
    static = static_dir(root)
    digest = asset_digest(root)
    index = (static / "index.html").read_text("utf-8")
    sw = (static / "sw.js").read_text("utf-8")
    index = replace_once(
        index,
        IMPORTMAP_BLOCK_RE.pattern,
        import_map_block(root),
        "import map",
    )
    index = replace_once(
        index,
        TOKENS_HREF_RE,
        f'href="{hashed_url(static / "vendor" / "design-tokens.css", root)}"',
        "design-tokens.css reference",
    )
    index = replace_once(
        index,
        STYLE_HREF_RE,
        f'href="{hashed_url(static / "style.css", root)}"',
        "style.css reference",
    )
    index = replace_once(
        index,
        APP_SRC_RE,
        f'src="{hashed_url(static / "app.js", root)}"',
        "app.js reference",
    )
    sw = replace_once(
        sw,
        r'const CACHE = "dav-shell-[^"]+";',
        f'const CACHE = "dav-shell-{digest}";',
        "service-worker cache",
    )
    sw = replace_once(
        sw,
        SW_APP_RE,
        f'  "{hashed_url(static / "app.js", root)}",',
        "service-worker app.js",
    )
    lines = "\n".join(f'  "{url}",' for url in module_urls(root))
    block = f"  // asset-modules:start\n{lines}\n  // asset-modules:end"
    sw = replace_once(sw, MODULE_BLOCK_RE.pattern, block, "service-worker module block")
    sw = replace_once(
        sw,
        SW_STYLE_RE,
        f'  "{hashed_url(static / "style.css", root)}",',
        "service-worker style.css",
    )
    sw = replace_once(
        sw,
        SW_TOKENS_RE,
        f'  "{hashed_url(static / "vendor" / "design-tokens.css", root)}",',
        "service-worker design-tokens.css",
    )
    return {static / "index.html": index, static / "sw.js": sw}


def check_consistency(root: Path = ROOT) -> bool:
    try:
        expected = rendered_targets(root)
    except ValueError as error:
        print(error, file=sys.stderr)
        return False
    stale = [path for path, text in expected.items() if path.read_text("utf-8") != text]
    if stale:
        print("stale asset digest: " + ", ".join(map(str, stale)), file=sys.stderr)
        return False
    print(f"asset digest ok: {asset_digest(root)}")
    return True


def atomic_write(path: Path, data: bytes) -> None:
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sync_assets(root: Path = ROOT) -> str:
    rendered = rendered_targets(root)
    originals = {target: target.read_bytes() for target in rendered}
    temporary: list[tuple[Path, Path]] = []
    replaced: list[Path] = []
    try:
        for target, text in rendered.items():
            fd, name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.append((Path(name), target))
        try:
            for source, target in temporary:
                os.replace(source, target)
                replaced.append(target)
        except OSError:
            for target in replaced:
                atomic_write(target, originals[target])
            raise
        return asset_digest(root)
    finally:
        for source, _ in temporary:
            source.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize content-hashed frontend asset URLs"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    if args.sync:
        print(f"asset digest synced: {sync_assets()}")
        return
    raise SystemExit(0 if check_consistency() else 1)


if __name__ == "__main__":
    main()
