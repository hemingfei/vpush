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
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, replace
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


@dataclass(frozen=True)
class SyncOptions:
    device: str = DEFAULT_ANDROID_SERIAL
    host: str = ""
    user: str = "root"
    ssh_key: str = ""
    remote_db: str = DEFAULT_REMOTE_DB
    expected_uid: str = ""


_SYNC_FIELDS = {
    "IMA_ANDROID_SERIAL": "device",
    "IMA_SYNC_HOST": "host",
    "IMA_SYNC_USER": "user",
    "IMA_SYNC_SSH_KEY": "ssh_key",
    "IMA_SYNC_REMOTE_DB": "remote_db",
    "IMA_EXPECTED_UID": "expected_uid",
}


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


def load_sync_config(path: str | Path) -> SyncOptions:
    target = Path(path)
    try:
        mode = target.stat().st_mode & 0o777
    except OSError as exc:
        raise ImaPhoneSyncError("同步配置无法读取") from exc
    if mode & 0o077:
        raise ImaPhoneSyncError("同步配置权限必须为 0600")
    values = {
        "device": DEFAULT_ANDROID_SERIAL,
        "host": "",
        "user": "root",
        "ssh_key": "",
        "remote_db": DEFAULT_REMOTE_DB,
        "expected_uid": "",
    }
    for number, raw_line in enumerate(target.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ImaPhoneSyncError(f"同步配置第 {number} 行无效")
        key, value = (part.strip() for part in line.split("=", 1))
        field = _SYNC_FIELDS.get(key)
        if field is None:
            raise ImaPhoneSyncError(f"同步配置项无效: {key}")
        values[field] = value
    return SyncOptions(**values)


def save_sync_config(path: str | Path, options: SyncOptions) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    content = "".join(
        f"{key}={getattr(options, field)}\n" for key, field in _SYNC_FIELDS.items()
    )
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(content)
        os.replace(temporary, target)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        Path(temporary).unlink(missing_ok=True)
        raise


def resolve_sync_options(
    config_path: str | Path,
    cli_values: dict[str, str] | None = None,
) -> SyncOptions:
    path = Path(config_path)
    options = load_sync_config(path) if path.exists() else SyncOptions(
        device=os.environ.get("IMA_ANDROID_SERIAL", DEFAULT_ANDROID_SERIAL),
        host=os.environ.get("IMA_SYNC_HOST", ""),
        user=os.environ.get("IMA_SYNC_USER", "root"),
        ssh_key=os.environ.get("IMA_SYNC_SSH_KEY", ""),
        remote_db=os.environ.get("IMA_SYNC_REMOTE_DB", DEFAULT_REMOTE_DB),
        expected_uid=os.environ.get("IMA_EXPECTED_UID", ""),
    )
    updates = {
        key: value
        for key, value in (cli_values or {}).items()
        if value not in (None, "")
    }
    invalid = set(updates) - set(SyncOptions.__dataclass_fields__)
    if invalid:
        raise ImaPhoneSyncError(f"同步配置项无效: {min(invalid)}")
    return replace(options, **updates)


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


def _prompt_sync_options(path: str | Path) -> SyncOptions:
    defaults = SyncOptions(
        device=os.environ.get("IMA_ANDROID_SERIAL", DEFAULT_ANDROID_SERIAL),
        host=os.environ.get("IMA_SYNC_HOST", ""),
        user=os.environ.get("IMA_SYNC_USER", "root"),
        ssh_key=os.environ.get("IMA_SYNC_SSH_KEY", ""),
        remote_db=os.environ.get("IMA_SYNC_REMOTE_DB", DEFAULT_REMOTE_DB),
        expected_uid=os.environ.get("IMA_EXPECTED_UID", ""),
    )

    def ask(label: str, default: str, *, required: bool = False) -> str:
        suffix = f" [{default}]" if default else ""
        try:
            value = input(f"{label}{suffix}: ").strip()
        except EOFError as exc:
            raise ImaPhoneSyncError("无法读取交互配置") from exc
        value = value or default
        if required and not value:
            raise ImaPhoneSyncError(f"{label}不能为空")
        return value

    options = SyncOptions(
        device=ask("Android 设备序列号", defaults.device, required=True),
        host=ask("VPS 地址", defaults.host, required=True),
        user=ask("SSH 用户", defaults.user, required=True),
        ssh_key=ask("SSH 私钥路径", defaults.ssh_key),
        remote_db=ask("远端数据库路径", defaults.remote_db, required=True),
        expected_uid=ask("期望的 IMA UID", defaults.expected_uid, required=True),
    )
    _validate_sync_options(options)
    save_sync_config(path, options)
    return options


def _validate_sync_options(options: SyncOptions) -> None:
    build_adb_command(options.device)
    build_ssh_command(
        host=options.host,
        user=options.user,
        ssh_key=options.ssh_key or None,
        remote_db=options.remote_db,
    )
    if options.expected_uid:
        _validate_uid(options.expected_uid)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步 rooted Android 上的 IMA Refresh Token 到 VPS")
    parser.add_argument("--device", default=None, help="ADB 设备序列号")
    parser.add_argument("--host", default=None, help="VPS 地址")
    parser.add_argument("--user", default=None, help="SSH 用户")
    parser.add_argument("--ssh-key", default=None, help="SSH 私钥路径")
    parser.add_argument("--remote-db", default=None, help="远端数据库路径")
    parser.add_argument("--expected-uid", default=None, help="期望的 IMA UID")
    parser.add_argument("--one-click", action="store_true")
    parser.add_argument(
        "--config-file",
        type=Path,
        default=ROOT / "data" / "ima_phone_sync.env",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.one_click:
            options = (
                _prompt_sync_options(args.config_file)
                if not args.config_file.exists()
                else load_sync_config(args.config_file)
            )
        else:
            options = resolve_sync_options(
                args.config_file,
                {
                    "device": args.device,
                    "host": args.host,
                    "user": args.user,
                    "ssh_key": args.ssh_key,
                    "remote_db": args.remote_db,
                    "expected_uid": args.expected_uid,
                },
            )
        _validate_sync_options(options)
        credentials = sync_once(
            device=options.device,
            host=options.host,
            user=options.user,
            ssh_key=options.ssh_key or None,
            remote_db=options.remote_db,
            expected_uid=options.expected_uid,
        )
    except ImaPhoneSyncError as exc:
        print(f"IMA 凭据同步失败: {exc}", file=sys.stderr)
        return 1
    print(f"IMA 凭据同步成功: UID={credentials.uid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
