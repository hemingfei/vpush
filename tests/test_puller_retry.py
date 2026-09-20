"""ARM lab 115 upload retry helper: Multipart / empty filesha1, no network."""
from __future__ import annotations

import pytest

from scripts import puller_retry as retry


@pytest.mark.parametrize("text,expected", [
    ("115 MultipartUploadAbort: part timeout", True),
    ("upload failed: empty filesha1", True),
    ("filesha1 is empty", True),
    ("filesha1为空", True),
    ("filesha1=", True),
    ("filesha1: ", True),
    ("permission denied", False),
    ("quota exceeded", False),
    ("", False),
])
def test_is_retryable_upload_error(text, expected):
    assert retry.is_retryable_upload_error(text) is expected
    assert retry.is_retryable_upload_error(RuntimeError(text)) is expected


def test_retries_then_succeeds():
    sleeps: list[float] = []
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 3:
            raise RuntimeError("MultipartUploadAbort")
        return "ok"

    assert retry.call_with_retry(flaky, sleeper=sleeps.append) == "ok"
    assert state["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_empty_filesha1_retries_then_raises():
    sleeps: list[float] = []
    state = {"n": 0}

    def always_fail():
        state["n"] += 1
        raise RuntimeError("init upload: filesha1=")

    with pytest.raises(RuntimeError, match="filesha1"):
        retry.call_with_retry(always_fail, attempts=3, sleeper=sleeps.append)
    assert state["n"] == 3
    assert sleeps == [1.0, 2.0]


def test_non_retryable_raises_immediately():
    sleeps: list[float] = []
    state = {"n": 0}

    def boom():
        state["n"] += 1
        raise RuntimeError("401 unauthorized")

    with pytest.raises(RuntimeError, match="401"):
        retry.call_with_retry(boom, sleeper=sleeps.append)
    assert state["n"] == 1
    assert sleeps == []
