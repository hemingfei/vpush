#!/usr/bin/env python3
"""Sync the IMA refresh token from a rooted Android phone to the VPS."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ima_documents import ImaDocumentConfig, ImaPureClient

IMA_PACKAGE = "com.tencent.ima"
IMA_PREFS_PATH = f"/data/data/{IMA_PACKAGE}/shared_prefs/public_setting.xml"
DEFAULT_ANDROID_SERIAL = "381a2bca"
DEFAULT_REMOTE_DB = "/opt/vpush/data/dav.db"
_UID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
_DEVICE_RE = re.compile(r"[A-Za-z0-9._:-]{1,64}")
_HOST_RE = re.compile(r"[A-Za-z0-9._:-]{1,255}")
_USER_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
_REMOTE_DB_RE = re.compile(r"/[A-Za-z0-9._/~+-]+")
_MAX_REFRESH_TOKEN_LENGTH = 4096


class ImaPhoneSyncError(RuntimeError):
    """A safe, user-facing phone synchronization error."""


@dataclass(frozen=True)
class ImaCredentials:
    uid: str
    refresh_token: str


def _safe_error(value: Any, secret: str = "") -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", "replace")
    else:
        text = str(value or "")
    text = next((line.strip() for line in reversed(text.splitlines()) if line.strip()), "")[:240]
    if secret:
        text = text.replace(secret, "<redacted>")
    text = re.sub(r"https?://\S+", "<url>", text)
    return re.sub(
        r"(?i)((?:bearer|token|refresh_token|authorization|signature|sig)\s*[=:]?\s*)[^\s,;]+",
        r"\1<redacted>",
        text,
    )


def _validate_uid(value: Any) -> str:
    uid = str(value or "")
    if not _UID_RE.fullmatch(uid):
        raise ImaPhoneSyncError("IMA UID 格式无效")
    return uid


def _validate_refresh_token(value: Any) -> str:
    token = str(value or "")
    if not token or len(token) > _MAX_REFRESH_TOKEN_LENGTH:
        raise ImaPhoneSyncError("IMA Refresh Token 无效")
    if any(ord(char) < 32 or ord(char) == 127 for char in token):
        raise ImaPhoneSyncError("IMA Refresh Token 无效")
    return token


def _credential_value(data: dict[str, Any], *names: str) -> Any:
    for name in names:
        if data.get(name):
            return data[name]
    nested = data.get("data")
    if isinstance(nested, dict):
        for name in names:
            if nested.get(name):
                return nested[name]
    return None


def parse_login_preferences(xml: bytes | str, expected_uid: str = "") -> ImaCredentials:
    """Extract and validate only IMA credentials from Android preferences XML."""
    try:
        root = ET.fromstring(xml)
    except (ET.ParseError, TypeError, ValueError) as exc:
        raise ImaPhoneSyncError("Android 登录配置 XML 无效") from exc

    raw_response = next(
        (
            node.text or ""
            for node in root.iter("string")
            if node.attrib.get("name") == "pref_login_response"
        ),
        "",
    ).strip()
    if not raw_response:
        raise ImaPhoneSyncError("未找到 pref_login_response")
    try:
        response = json.loads(raw_response)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ImaPhoneSyncError("pref_login_response 不是有效 JSON") from exc
    if not isinstance(response, dict):
        raise ImaPhoneSyncError("pref_login_response 格式无效")

    credentials = ImaCredentials(
        uid=_validate_uid(_credential_value(response, "userId", "user_id")),
        refresh_token=_validate_refresh_token(
            _credential_value(response, "refreshToken", "refresh_token")
        ),
    )
    if expected_uid:
        expected = _validate_uid(expected_uid)
        if credentials.uid != expected:
            raise ImaPhoneSyncError("IMA UID 不匹配")
    return credentials


def build_adb_command(
    device: str,
    *,
    adb_bin: str = "adb",
    package: str = IMA_PACKAGE,
) -> list[str]:
    if not _DEVICE_RE.fullmatch(device):
        raise ImaPhoneSyncError("Android 设备序列号无效")
    if not re.fullmatch(r"[A-Za-z0-9_.]{1,128}", package):
        raise ImaPhoneSyncError("Android 包名无效")
    prefs_path = f"/data/data/{package}/shared_prefs/public_setting.xml"
    return [
        adb_bin,
        "-s",
        device,
        "exec-out",
        "su",
        "-c",
        f"cat {shlex.quote(prefs_path)}",
    ]


def read_phone_preferences(
    device: str,
    *,
    runner: Callable[..., Any] = subprocess.run,
    timeout: int = 30,
) -> bytes:
    command = build_adb_command(device)
    result = runner(
        command,
        capture_output=True,
        check=False,
        input=None,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ImaPhoneSyncError(f"读取 Android 登录配置失败: {_safe_error(result.stderr)}")
    output = result.stdout or b""
    if not output:
        raise ImaPhoneSyncError("Android 登录配置为空")
    return output


def validate_ima_credentials(
    credentials: ImaCredentials,
    *,
    client_factory: Callable[[ImaDocumentConfig], Any] = ImaPureClient,
) -> ImaCredentials:
    """Prove the refresh token works without persisting the short-lived token."""
    try:
        client = client_factory(
            ImaDocumentConfig(uid=credentials.uid, refresh_token=credentials.refresh_token)
        )
        token = client.refresh()
    except Exception as exc:  # upstream errors must never reach the CLI
        raise ImaPhoneSyncError("IMA Refresh Token 校验失败") from exc
    if not token:
        raise ImaPhoneSyncError("IMA Refresh Token 校验失败")
    return credentials


_REMOTE_UPDATE_SCRIPT = r'''import json
import sqlite3
import sys

payload = json.load(sys.stdin)
uid = str(payload.get("uid") or "")
refresh_token = str(payload.get("refresh_token") or "")
expected_uid = str(payload.get("expected_uid") or "")
db_path = sys.argv[1]
if not uid or not refresh_token:
    raise RuntimeError("invalid credential payload")

conn = sqlite3.connect(db_path, timeout=15)
try:
    conn.execute("PRAGMA busy_timeout = 15000")
    row = conn.execute("SELECT value FROM settings WHERE key = 'ima_pure_uid'").fetchone()
    current_uid = str(row[0] or "") if row else ""
    if expected_uid and current_uid and current_uid != expected_uid:
        raise RuntimeError("existing UID mismatch")
    if current_uid and current_uid != uid:
        raise RuntimeError("UID mismatch")
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("ima_pure_uid", uid),
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("ima_pure_refresh_token", refresh_token),
        )
    print(json.dumps({"uid": uid, "updated": True}))
finally:
    conn.close()
'''


def build_ssh_command(
    *,
    host: str,
    user: str,
    ssh_key: str | Path | None,
    remote_db: str = DEFAULT_REMOTE_DB,
    ssh_bin: str = "ssh",
) -> list[str]:
    if not _HOST_RE.fullmatch(host):
        raise ImaPhoneSyncError("VPS 地址无效")
    if not _USER_RE.fullmatch(user):
        raise ImaPhoneSyncError("SSH 用户名无效")
    if not _REMOTE_DB_RE.fullmatch(remote_db):
        raise ImaPhoneSyncError("远端数据库路径无效")
    remote_command = f"python3 -c {shlex.quote(_REMOTE_UPDATE_SCRIPT)} {shlex.quote(remote_db)}"
    command = [
        ssh_bin,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
    ]
    if ssh_key:
        command.extend(["-i", str(ssh_key)])
    command.extend([f"{user}@{host}", remote_command])
    return command


def update_remote_settings(
    credentials: ImaCredentials,
    *,
    host: str,
    user: str,
    ssh_key: str | Path | None,
    remote_db: str = DEFAULT_REMOTE_DB,
    expected_uid: str = "",
    runner: Callable[..., Any] = subprocess.run,
    timeout: int = 30,
) -> None:
    if expected_uid and credentials.uid != _validate_uid(expected_uid):
        raise ImaPhoneSyncError("IMA UID 不匹配")
    command = build_ssh_command(
        host=host,
        user=user,
        ssh_key=ssh_key,
        remote_db=remote_db,
    )
    payload = json.dumps(
        {
            "uid": credentials.uid,
            "refresh_token": credentials.refresh_token,
            **({"expected_uid": expected_uid} if expected_uid else {}),
        },
        separators=(",", ":"),
    ).encode()
    result = runner(
        command,
        input=payload,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ImaPhoneSyncError(
            f"VPS 凭据更新失败: {_safe_error(result.stderr, credentials.refresh_token)}"
        )
    try:
        response = json.loads(result.stdout or b"{}")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ImaPhoneSyncError("VPS 凭据更新返回无效结果") from exc
    if response.get("updated") is not True:
        raise ImaPhoneSyncError("VPS 凭据更新未确认")


def sync_once(
    *,
    device: str,
    host: str,
    user: str,
    ssh_key: str | Path | None,
    remote_db: str = DEFAULT_REMOTE_DB,
    expected_uid: str = "",
    runner: Callable[..., Any] = subprocess.run,
    client_factory: Callable[[ImaDocumentConfig], Any] = ImaPureClient,
) -> ImaCredentials:
    credentials = parse_login_preferences(
        read_phone_preferences(device, runner=runner),
        expected_uid=expected_uid,
    )
    validate_ima_credentials(credentials, client_factory=client_factory)
    update_remote_settings(
        credentials,
        host=host,
        user=user,
        ssh_key=ssh_key,
        remote_db=remote_db,
        expected_uid=expected_uid,
        runner=runner,
    )
    return credentials


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步 rooted Android 上的 IMA Refresh Token 到 VPS")
    parser.add_argument(
        "--device",
        default=os.environ.get("IMA_ANDROID_SERIAL", DEFAULT_ANDROID_SERIAL),
        help="ADB 设备序列号（默认读取 IMA_ANDROID_SERIAL）",
    )
    parser.add_argument("--host", default=os.environ.get("IMA_SYNC_HOST", ""), required=False)
    parser.add_argument("--user", default=os.environ.get("IMA_SYNC_USER", "root"))
    parser.add_argument("--ssh-key", default=os.environ.get("IMA_SYNC_SSH_KEY", ""))
    parser.add_argument("--remote-db", default=os.environ.get("IMA_SYNC_REMOTE_DB", DEFAULT_REMOTE_DB))
    parser.add_argument("--expected-uid", default=os.environ.get("IMA_EXPECTED_UID", ""))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.host:
        print("缺少 --host 或 IMA_SYNC_HOST", file=sys.stderr)
        return 2
    try:
        credentials = sync_once(
            device=args.device,
            host=args.host,
            user=args.user,
            ssh_key=args.ssh_key or None,
            remote_db=args.remote_db,
            expected_uid=args.expected_uid,
        )
    except ImaPhoneSyncError as exc:
        print(f"IMA 凭据同步失败: {exc}", file=sys.stderr)
        return 1
    print(f"IMA 凭据同步成功: UID={credentials.uid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
