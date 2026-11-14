"""接力（Relay）账号注册表：本地 JSON 自管，云端无账号表（spec #14）。

注册表形态是新物（mx-behavior-logic.md §5：云端只有单账号 config + .env
凭据，token 时效记录 settings 键 mx_token_updated_at 的先例）；本地 agent
以一个 JSON 文件承接同等语义：

- 每账号一个独立 Chrome profile 目录（ADR-0001：Chrome 136+ 远程调试端口
  在默认 user-data-dir 失效，独立 profile 是硬前提；同时两账号 profile 隔离
  才能实现「不并行在线」的接力切换）；
- 每账号一份 token + 更新时刻（epoch 秒），掉线检测与重登的输入；
- 每账号最后打开的房间（云端 settings 键 mx_last_room 的本地等价——接力下
  各账号「恢复上次房间」互不串号）。

安全红线：密码绝不进注册表——账号密码只经环境变量传递（scripts/mx_login.py
文件头明文约定：凭据只从环境变量/.env 读取，源码、日志、文档不落任何凭据）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Account:
    """接力账号条目：user 是账号名；role 依清单顺序（第一个主、其后备用）。"""

    user: str
    role: str  # "primary" | "backup"

    def password_env_key(self) -> str:
        """该账号密码的环境变量键：MX_AGENT_PASSWORD_<账号名大写>。

        账号名里的非字母数字一律转下划线——环境变量键不允许出现点/横线/空格。
        """
        sanitized = re.sub(r"[^A-Za-z0-9]", "_", self.user).upper()
        return f"MX_AGENT_PASSWORD_{sanitized}"


def parse_accounts(raw: str) -> list[Account]:
    """逗号分隔账号清单 → 账号列表；顺序即接力优先级（首个 primary）。

    与 mx_login 的 MX_ACCOUNT 单账号约定兼容：只有一个账号时无接力，
    行为器单账号照常跑（接力是可选增强，不是前置条件）。
    """
    names = [name.strip() for name in (raw or "").split(",") if name.strip()]
    roles = ["primary"] + ["backup"] * (len(names) - 1) if names else []
    return [Account(user=name, role=role) for name, role in zip(names, roles)]


class AccountRegistry:
    """账号运行态注册表：profile 目录 + token/更新时刻 + 最后房间，JSON 持久化。

    坏 JSON 从空表重建：注册表是可重建的运行态缓存，损坏不该阻止 agent
    启动（与 mx_window.loads_plan 的容错哲学一致——坏数据只损失恢复能力）。
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data: dict[str, dict] = {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data = {str(k): v for k, v in raw.items()
                              if isinstance(v, dict)}
        except (OSError, ValueError):
            pass

    # ---- 持久化 ----

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    def _entry(self, user: str) -> dict:
        entry = self._data.setdefault(user, {})
        if "profile_dir" not in entry:
            # profile 目录名 = 账号名净化：同账号目录稳定（重复调用不漂移）
            safe = re.sub(r"[^A-Za-z0-9_-]", "_", user) or "account"
            entry["profile_dir"] = str(self.path.parent / "profiles" / safe)
        return entry

    # ---- 读写面 ----

    def profile_dir(self, user: str) -> Path:
        """账号专属 Chrome profile 目录（懒创建）。"""
        path = Path(self._entry(user)["profile_dir"])
        path.mkdir(parents=True, exist_ok=True)
        return path

    def set_token(self, user: str, token: str, *, updated_at: float) -> None:
        entry = self._entry(user)
        entry["token"] = token
        entry["token_updated_at"] = float(updated_at)
        self._save()

    def token(self, user: str) -> str | None:
        entry = self._data.get(user)
        return entry.get("token") if entry else None

    def token_updated_at(self, user: str) -> float | None:
        entry = self._data.get(user)
        return entry.get("token_updated_at") if entry else None

    def set_last_room(self, user: str, room: str) -> None:
        self._entry(user)["last_room"] = room
        self._save()

    def last_room(self, user: str) -> str | None:
        entry = self._data.get(user)
        return entry.get("last_room") if entry else None
