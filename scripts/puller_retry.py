"""Retry helper for ARM lab puller_loop 115 uploads (no network).

``scripts/puller_loop.py``（连同 ``lab_common.py`` / ``manifest.py``）是
Oracle-SJ-ARM ``/opt/vpush-ima-lab/scripts/`` 的权威副本；宿主机 systemd
调用，**不是**生产 compose。``puller_loop.upload_one`` 在
``upload_ok(result)`` 为假时 raise，再走本模块：``MultipartUploadAbort``
/ 空 ``filesha1`` 退避重试 2–3 次，然后 ``on_fail`` 移入 ``failed/``。

不读 IMA / 115 Cookie，不发起上传。
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_ATTEMPTS = 3
DEFAULT_DELAYS = (1.0, 2.0)
RETRYABLE_MARKERS = (
    "MultipartUploadAbort",
    "empty filesha1",
    "filesha1 is empty",
    "filesha1为空",
)
_EMPTY_FILESHA1_RE = re.compile(
    r"filesha1\s*[:=]\s*(?:['\"]['\"]|null|none)?\s*(?:$|[,\s}])",
    re.IGNORECASE,
)


def is_retryable_upload_error(exc: BaseException | str) -> bool:
    """True for MultipartUploadAbort / empty-filesha1 style 115 flakes."""
    text = str(exc)
    if "MultipartUploadAbort" in text:
        return True
    lowered = text.lower()
    if "filesha1" not in lowered:
        return False
    if any(marker.lower() in lowered for marker in RETRYABLE_MARKERS if "filesha1" in marker.lower()):
        return True
    return _EMPTY_FILESHA1_RE.search(text) is not None


def call_with_retry(
    fn: Callable[[], T],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    delays: tuple[float, ...] = DEFAULT_DELAYS,
    sleeper: Callable[[float], None] = time.sleep,
    is_retryable: Callable[[BaseException], bool] = is_retryable_upload_error,
) -> T:
    """Call ``fn`` up to ``attempts`` times on retryable errors.

    Non-retryable errors raise immediately. After the last attempt the last
    exception is re-raised so the caller can move the file to ``failed/``.
    """
    tries = max(1, int(attempts))
    last: BaseException | None = None
    for index in range(tries):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if (not is_retryable(exc)) or index >= tries - 1:
                raise
            wait = delays[min(index, len(delays) - 1)] if delays else 0.0
            if wait > 0:
                sleeper(wait)
    assert last is not None
    raise last
