#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.static_assets import (  # noqa: E402
    DIGEST_LEN,
    IMMUTABLE_CACHE_CONTROL,
    REVALIDATE_CACHE_CONTROL,
    ROOT as PACKAGE_ROOT,
    STATIC_REL,
    asset_digest,
    asset_paths,
    atomic_write,
    cached_file_digest,
    check_consistency,
    file_digest,
    hashed_url,
    import_map_block,
    import_map_imports,
    logical_url,
    main,
    module_urls,
    rendered_targets,
    replace_once,
    resolve_fingerprinted_path,
    should_revalidate,
    static_dir,
    sync_assets,
)

__all__ = [
    "DIGEST_LEN",
    "IMMUTABLE_CACHE_CONTROL",
    "PACKAGE_ROOT",
    "REVALIDATE_CACHE_CONTROL",
    "ROOT",
    "STATIC_REL",
    "asset_digest",
    "asset_paths",
    "atomic_write",
    "cached_file_digest",
    "check_consistency",
    "file_digest",
    "hashed_url",
    "import_map_block",
    "import_map_imports",
    "logical_url",
    "main",
    "module_urls",
    "rendered_targets",
    "replace_once",
    "resolve_fingerprinted_path",
    "should_revalidate",
    "static_dir",
    "sync_assets",
]


if __name__ == "__main__":
    main()
