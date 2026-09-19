"""ARM lab ops panel settings. Paths and bind defaults; never commit secrets."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8055
DEFAULT_CACHE_ROOT = "/data/vpush-ima-cache"
DEFAULT_IMA_SECRETS = "/secrets/ima-pure.json"
DEFAULT_COOKIES = "/secrets/115-cookies.txt"
DEFAULT_PASSWORD_FILE = "/secrets/arm-ops-password.txt"
DEFAULT_TIMER_UNIT = "vpush-ima-lab-sync.timer"
SESSION_COOKIE = "arm_ops"
SESSION_TTL_SECONDS = 12 * 3600
QR_START_LIMIT = 5
QR_START_WINDOW_SECONDS = 60
QR_SESSION_TTL_SECONDS = 5 * 60
WALK_FILE_CAP = 12_000
WALK_SECONDS_CAP = 1.5
LOG_TAIL_LINES = 20
LOG_FILE_CAP = 6
TAILSCALE_BIND_TOKENS = frozenset({"tailscale", "tailscale0", "tailnet"})
_IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
BIND_ALL_WARNING = (
    "WARNING: ARM_OPS_BIND/ARM_OPS_HOST is 0.0.0.0 / :: — the process listens on "
    "every NIC, including the public internet. Do not publish 0.0.0.0:8055 on the "
    "public NIC. Preferred: ARM_OPS_BIND=tailscale (or the IPv4 from "
    "`tailscale ip -4`) on host network. Fallback: 127.0.0.1:8055 + "
    "ssh -L 8055:127.0.0.1:8055. Or `tailscale serve` in front of loopback."
)
TAILSCALE_MISSING_WARNING = (
    "WARNING: ARM_OPS_BIND requested Tailscale but no IPv4 was found "
    "(`tailscale ip -4` / tailscale0). Falling back to 127.0.0.1:8055. "
    "Use an SSH tunnel or set ARM_OPS_BIND to the address from `tailscale ip -4`."
)

# p115client AVAILABLE_APPS plus the short aliases used in lab scripts.
P115_DEVICE_TYPES = (
    "harmony",
    "web",
    "ios",
    "115ios",
    "android",
    "115android",
    "ipad",
    "115ipad",
    "tv",
    "apple_tv",
    "qandroid",
    "qios",
    "qipad",
    "os_windows",
    "os_mac",
    "os_linux",
    "windows",
    "mac",
    "linux",
    "wechatmini",
    "alipaymini",
)


def env_str(name: str, default: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def cache_root() -> Path:
    return Path(env_str("CACHE_ROOT", DEFAULT_CACHE_ROOT))


def ima_secrets_path() -> Path:
    return Path(env_str("IMA_PURE_SECRETS_FILE", DEFAULT_IMA_SECRETS))


def cookies_path() -> Path:
    return Path(env_str("P115_COOKIES_FILE", DEFAULT_COOKIES))


def password_file() -> Path:
    return Path(env_str("ARM_OPS_PASSWORD_FILE", DEFAULT_PASSWORD_FILE))


def openlist_public_url() -> str:
    return env_str("OPENLIST_PUBLIC_URL", "")


def puller_health_url() -> str:
    return env_str("PULLER_HEALTH_URL", "")


def puller_health_file() -> Path | None:
    raw = env_str("PULLER_HEALTH_FILE", "")
    if raw:
        return Path(raw)
    candidate = cache_root() / "logs" / "health.json"
    return candidate


def docker_sock() -> Path:
    return Path(env_str("DOCKER_SOCK", "/var/run/docker.sock"))


def puller_container_name() -> str:
    return env_str("PULLER_CONTAINER_NAME", "")


def timer_unit() -> str:
    return env_str("ARM_OPS_TIMER_UNIT", DEFAULT_TIMER_UNIT)


def _first_ipv4_line(text: str) -> str | None:
    for line in text.splitlines():
        token = line.strip().split()[0] if line.strip() else ""
        if _IPV4_RE.fullmatch(token):
            return token
    match = re.search(r"\binet\s+(\d{1,3}(?:\.\d{1,3}){3})\b", text)
    return match.group(1) if match else None


def tailscale_ipv4(
    runner=subprocess.run,
) -> str | None:
    """Resolve Tailscale IPv4. uvicorn binds an IP, not iface tailscale0."""
    try:
        proc = runner(
            ["tailscale", "ip", "-4"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    if proc is not None and proc.returncode == 0:
        found = _first_ipv4_line(proc.stdout or "")
        if found:
            return found
    try:
        proc = runner(
            ["ip", "-4", "-o", "addr", "show", "dev", "tailscale0"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return _first_ipv4_line(proc.stdout or "")


def bind_spec() -> str:
    """Raw ARM_OPS_BIND, else ARM_OPS_HOST, else loopback."""
    return env_str("ARM_OPS_BIND") or env_str("ARM_OPS_HOST") or DEFAULT_HOST


def bind_host(runner=subprocess.run) -> str:
    spec = bind_spec()
    if spec.lower() in TAILSCALE_BIND_TOKENS:
        ip = tailscale_ipv4(runner=runner)
        return ip or DEFAULT_HOST
    return spec


def bind_port() -> int:
    return env_int("ARM_OPS_PORT", DEFAULT_PORT)


def default_device_type() -> str:
    raw = env_str("P115_DEVICE_TYPE", "harmony").lower()
    return raw if raw in P115_DEVICE_TYPES else "harmony"


def binds_all_interfaces(host: str | None = None) -> bool:
    value = (host if host is not None else bind_host()).strip().lower()
    return value in {"0.0.0.0", "::", "[::]"}
