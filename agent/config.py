"""行为器配置：纯环境变量 + 本地数据目录（循 .env 既有模式，票 #17 交付物 ⑦）。

用户偏好：密钥类写 .env——账号清单与各账号密码全部走环境变量键，
行为器不依赖云端 config.yaml（agent 不感知云端配置体系，ADR-0001 分层）。

键（均带 MX_AGENT_ 前缀，MX_LOGIN_ORIGIN 复用 mx_login 既有键语义）：
- MX_AGENT_ACCOUNTS           逗号分隔账号清单，顺序即接力优先级（首个主账号）
- MX_AGENT_PASSWORD_<账号大写>  各账号密码（独立键，绝不落库不入日志）
- MX_LOGIN_ORIGIN             登录域名（复用 scripts/mx_login.py 的既有键）
- MX_AGENT_CDP_PORT            专用 Chrome 远程调试端口（默认 9223，避开常见 9222）
- MX_AGENT_ROOMS               房间清单 JSON（切房目标池；默认沿用实机抓包先例）
- MX_AGENT_DATA_DIR            数据目录（注册表/当日计划/日志）
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .accounts import Account, AccountRegistry, parse_accounts

# 默认域名与 scripts/mx_login.py DEFAULT_API_BASE 同源（2026-10-12 平台迁域）
DEFAULT_ORIGIN = "https://mx.2026.foodtop1.com"
# 默认房间池沿用 scripts/mx_room_switch_capture.py 的实机抓包先例房间
DEFAULT_ROOMS = ["格兰投研888", "妖股刺客", "姆爷的守护", "老樊"]
DEFAULT_CDP_PORT = 9223


@dataclass
class AgentConfig:
    """行为器运行配置（纯环境变量派生，无 YAML/DB）。"""

    accounts: list[Account] = field(default_factory=list)
    origin: str = DEFAULT_ORIGIN
    cdp_port: int = DEFAULT_CDP_PORT
    rooms: list[str] = field(default_factory=lambda: list(DEFAULT_ROOMS))
    data_dir: Path = Path("data") / "agent"

    def password_of(self, account: Account) -> str:
        """账号密码：只从环境变量读，缺失返回空串（登录链路用时再报缺凭据）。"""
        return os.environ.get(account.password_env_key(), "")

    def registry_path(self) -> Path:
        return self.data_dir / "accounts.json"

    def registry(self) -> AccountRegistry:
        return AccountRegistry(self.registry_path())


def _parse_rooms(raw: str | None) -> list[str]:
    rooms: list[str] | None = None
    if raw and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                rooms = [str(r).strip() for r in parsed if str(r).strip()]
        except ValueError:
            rooms = None
    return rooms if rooms else list(DEFAULT_ROOMS)


def load_agent_config() -> AgentConfig:
    """从环境变量组装配置（.env 由调用方先 load_dotenv，与 mx_login 同序）。"""
    accounts = parse_accounts(os.environ.get("MX_AGENT_ACCOUNTS", ""))
    port_raw = os.environ.get("MX_AGENT_CDP_PORT", "").strip()
    try:
        port = int(port_raw) if port_raw else DEFAULT_CDP_PORT
    except ValueError:
        port = DEFAULT_CDP_PORT
    data_raw = os.environ.get("MX_AGENT_DATA_DIR", "").strip()
    return AgentConfig(
        accounts=accounts,
        origin=(os.environ.get("MX_LOGIN_ORIGIN", "").strip().rstrip("/")
                or DEFAULT_ORIGIN),
        cdp_port=port,
        rooms=_parse_rooms(os.environ.get("MX_AGENT_ROOMS")),
        data_dir=Path(data_raw) if data_raw else Path("data") / "agent",
    )
