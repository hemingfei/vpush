"""Per-user knowledge-library quotas. Admins are exempt at the call site."""
from __future__ import annotations

from datetime import datetime

from .fetchers.base import CN_TZ

IMA_LIST_BURST = 60
IMA_LIST_BURST_SEC = 600
IMA_PDF_BURST = 30
IMA_PDF_BURST_SEC = 600
IMA_PDF_DAY = 120

BUCKET_LIST_BURST = "ima_list_burst"
BUCKET_PDF_BURST = "ima_pdf_burst"
BUCKET_PDF_DAY = "ima_pdf_day"


def window_start(now: float, seconds: int) -> int:
    step = max(int(seconds), 1)
    return int(now) // step * step


def shanghai_day_start(now: float) -> int:
    local = datetime.fromtimestamp(now, CN_TZ)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp())
