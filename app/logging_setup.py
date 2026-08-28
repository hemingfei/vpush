"""统一日志配置：级别可控、内存环形缓冲（网页查看）、可选文件轮转。"""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
import threading
from collections import deque
from pathlib import Path

LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s [%(threadName)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
RING_SIZE = 2000

MAX_REDACTED_LEN = 2000

# 错误文本里的常见凭据形态：异常字符串会原样进 push_logs/error_logs，
# 而 httpx 异常的 __str__ 含完整请求 URL（自建 bot token / webhook key / Bark key）
_REDACT_PATTERNS = [
    (re.compile(r"(bot\d+:)[A-Za-z0-9_-]{20,}"), r"\1<redacted>"),
    (
        re.compile(
            r"\b((?:key|token|secret|password|access_token|ticket)=)[^&\s'\"<>]+",
            re.IGNORECASE,
        ),
        r"\1<redacted>",
    ),
    (
        re.compile(
            r"(?<![A-Za-z0-9_-])((?:auth_token|ct0|ima-openapi-apikey|api_key)=)[^&;\s'\"<>]+",
            re.IGNORECASE,
        ),
        r"\1<redacted>",
    ),
    (re.compile(r"(api\.day\.app/)[A-Za-z0-9]{8,}", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE), r"\1<redacted>"),
    # 微博登录 META 响应：su 是 base64 用户名，其余为 SSO 会话 cookie 名
    (re.compile(r"(\bsu=)[^&\s'\"<>]+", re.IGNORECASE), r"\1<redacted>"),
    (re.compile(r"(\b(?:SUB|SUE|SUP|SCF|SSOLoginState)=)[^;\s'\"<>]+"), r"\1<redacted>"),
]


def redact_secrets(text) -> str:
    """抹掉文本中的常见明文凭据并截断；用于任何入库/持久化的错误描述。"""
    if not text:
        return ""
    result = str(text)
    for pattern, repl in _REDACT_PATTERNS:
        result = pattern.sub(repl, result)
    return result[:MAX_REDACTED_LEN]

class RedactingFormatter(logging.Formatter):
    """格式化完整日志行后脱敏，避免日志 sink 保存明文凭据。"""

    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


_ring: deque[str] = deque(maxlen=RING_SIZE)
_ring_lock = threading.Lock()
_configured_lock = threading.Lock()


class RingBufferHandler(logging.Handler):
    """把格式化后的日志行保留在内存环形缓冲，供管理后台查看。"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            with _ring_lock:
                _ring.append(line)
        except Exception:  # noqa: BLE001, S110 - 日志记录失败不影响业务
            pass


# WARNING+ 持久化 sink（由 create_app 注入 DB 写入函数；未注入时丢弃）
_error_sink = None


def register_error_sink(sink) -> None:
    """注册错误日志持久化回调（logging 模块不直接依赖 DB）。"""
    global _error_sink
    _error_sink = sink


_LARK_BENIGN_ERRORS = (
    "processor not found, type: im.message.message_read_v1",
    "sent 1000 (OK); then received 1000 (OK) bye",
)


class LarkBenignErrorFilter(logging.Filter):
    """丢掉 lark-oapi 的已知无害 ERROR，真故障（连不上、event loop）仍留下。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.ERROR:
            return True
        msg = record.getMessage()
        return not any(needle in msg for needle in _LARK_BENIGN_ERRORS)


class ErrorDbHandler(logging.Handler):
    """把 WARNING+ 日志写入 DB，跨重启可查（管理后台错误记录面板）。"""

    def emit(self, record: logging.LogRecord) -> None:
        sink = _error_sink
        if sink is None:
            return
        try:
            sink(record)
        except Exception:  # noqa: BLE001, S110 - 错误日志落库失败不影响业务
            pass


def recent_logs(limit: int = 200, level: str | None = None, q: str | None = None) -> list[str]:
    """返回内存环形缓冲里的最近日志行（新→旧），可按级别（含更高级别）与关键词过滤。

    DEBUG 为精确匹配（只显示 DEBUG 行）；其余级别为「及以上」（ERROR+ 含 ERROR/CRITICAL）。
    """
    with _ring_lock:
        lines = list(_ring)
    if level:
        want = level.upper()
        exact = want == "DEBUG"  # DEBUG 行最稀缺且不会混入上级日志，选它时只显示 DEBUG
        min_rank = getattr(logging, want, 0)
        if not isinstance(min_rank, int):
            min_rank = 0
        lines = [
            line for line in lines
            if (r := _line_rank(line)) is not None
            and (r == logging.DEBUG if exact else r >= min_rank)
        ]
    if q:
        needle = q.lower()
        lines = [line for line in lines if needle in line.lower()]
    return list(reversed(lines[-limit:]))


def _line_rank(line: str) -> int | None:
    # 日志格式：2026-08-05 22:14:58.091 LEVEL app.name [thread] message
    try:
        level = getattr(logging, line.split()[2].upper(), None)
    except (IndexError, AttributeError):
        return None
    return level if isinstance(level, int) else None


def setup_logging(level: str | None = None, log_file: str | None = None) -> None:
    """配置根日志器（幂等）：stdout + 可选滚动文件 + 环形缓冲。"""
    level = level or os.environ.get("LOG_LEVEL", "INFO")
    log_file = log_file if log_file is not None else os.environ.get("LOG_FILE", "")
    with _configured_lock:
        root = logging.getLogger()
        root.setLevel(level.upper())
        # 幂等：避免 create_app 多次调用时重复挂 handler
        if not any(isinstance(h, RingBufferHandler) for h in root.handlers):
            formatter = RedactingFormatter(LOG_FORMAT, datefmt=DATE_FORMAT)
            console = logging.StreamHandler()
            console.setFormatter(formatter)
            root.addHandler(console)
            ring = RingBufferHandler(level=logging.DEBUG)
            ring.setFormatter(formatter)
            root.addHandler(ring)
            # WARNING+ 持久化到 DB（跨重启可查）；sink 由 create_app 注入，未注入时静默
            error_db = ErrorDbHandler(level=logging.WARNING)
            error_db.setFormatter(formatter)
            root.addHandler(error_db)
            if log_file:
                Path(log_file).parent.mkdir(parents=True, exist_ok=True)
                file_handler = logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=5 * 1024 * 1024,
                    backupCount=3,
                    encoding="utf-8",
                )
                file_handler.setFormatter(formatter)
                root.addHandler(file_handler)
    # httpx 访问日志可能包含 Telegram bot token；始终禁止请求 URL 进入应用日志。
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # lark-oapi 把已读回执未注册、WebSocket 正常关闭（1000）打成 ERROR。
    lark = logging.getLogger("Lark")
    if not any(isinstance(f, LarkBenignErrorFilter) for f in lark.filters):
        lark.addFilter(LarkBenignErrorFilter())
