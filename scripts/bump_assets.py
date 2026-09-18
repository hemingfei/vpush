#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.static_assets import (  # noqa: E402
    asset_digest,
    check_consistency,
    hashed_url,
    main,
    module_urls,
    os,
    static_dir,
    sync_assets,
)

__all__ = [
    "ROOT",
    "asset_digest",
    "check_consistency",
    "hashed_url",
    "main",
    "module_urls",
    "os",
    "static_dir",
    "sync_assets",
]


if __name__ == "__main__":
    main()
