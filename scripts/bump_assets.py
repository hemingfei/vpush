#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path("app/static")
DIGEST_LEN = 12


def asset_paths(root: Path = ROOT) -> list[Path]:
    static = root / STATIC
    paths = [static / "style.css", static / "app.js"]
    paths += sorted((static / "core").glob("**/*.js")) if (static / "core").exists() else []
    paths += sorted((static / "views").glob("**/*.js")) if (static / "views").exists() else []
    missing = [path for path in paths[:2] if not path.is_file()]
    if missing:
        raise ValueError("missing required assets: " + ", ".join(map(str, missing)))
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def asset_digest(root: Path = ROOT) -> str:
    digest = hashlib.sha256()
    for path in asset_paths(root):
        relative = path.relative_to(root).as_posix().encode()
        digest.update(relative + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()[:DIGEST_LEN]


def replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one reference, found {count}")
    return updated


def module_urls(root: Path = ROOT) -> list[str]:
    static = root / STATIC
    return [
        "/" + path.relative_to(static).as_posix()
        for path in asset_paths(root)
        if path.suffix == ".js" and path.name != "app.js"
    ]


def rendered_targets(root: Path = ROOT) -> dict[Path, str]:
    static = root / STATIC
    digest = asset_digest(root)
    index = (static / "index.html").read_text("utf-8")
    sw = (static / "sw.js").read_text("utf-8")
    index = replace_once(index, r'href="/style\.css\?v=[^"]+"',
                         f'href="/style.css?v={digest}"', "style.css reference")
    index = replace_once(index, r'src="/app\.js\?v=[^"]+"',
                         f'src="/app.js?v={digest}"', "app.js reference")
    sw = replace_once(sw, r'const CACHE = "dav-shell-[^"]+";',
                      f'const CACHE = "dav-shell-{digest}";', "service-worker cache")
    lines = "\n".join(f'  "{url}",' for url in module_urls(root))
    block = f"  // asset-modules:start\n{lines}\n  // asset-modules:end"
    sw = replace_once(sw, r"  // asset-modules:start[\s\S]*?  // asset-modules:end",
                      block, "service-worker module block")
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
    parser = argparse.ArgumentParser(description="Synchronize content-derived frontend asset versions")
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
