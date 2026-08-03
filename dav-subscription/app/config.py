"""配置加载：YAML 文件 + 环境变量覆盖。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

import yaml


@dataclass
class FeishuConfig:
    webhook_url: str = ""


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class NotifiersConfig:
    feishu: FeishuConfig = field(default_factory=FeishuConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


@dataclass
class XueqiuConfig:
    cookie: str = ""


@dataclass
class WeiboConfig:
    cookie: str = ""
    token: str = ""


@dataclass
class SourcesConfig:
    xueqiu: XueqiuConfig = field(default_factory=XueqiuConfig)
    weibo: WeiboConfig = field(default_factory=WeiboConfig)


@dataclass
class PollingConfig:
    interval_seconds: int = 180
    jitter_seconds: int = 30
    notify_on_start: bool = True


@dataclass
class WebConfig:
    password: str = ""


@dataclass
class Config:
    notifiers: NotifiersConfig = field(default_factory=NotifiersConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    web: WebConfig = field(default_factory=WebConfig)
    db_path: str = "/data/dav.db"


# 环境变量 -> Config 属性路径（用于覆盖）
_ENV_MAP = {
    "FEISHU_WEBHOOK_URL": ("notifiers", "feishu", "webhook_url"),
    "TELEGRAM_BOT_TOKEN": ("notifiers", "telegram", "bot_token"),
    "TELEGRAM_CHAT_ID": ("notifiers", "telegram", "chat_id"),
    "XUEQIU_COOKIE": ("sources", "xueqiu", "cookie"),
    "WEIBO_COOKIE": ("sources", "weibo", "cookie"),
    "WEIBO_TOKEN": ("sources", "weibo", "token"),
    "POLLING_INTERVAL_SECONDS": ("polling", "interval_seconds"),
    "POLLING_JITTER_SECONDS": ("polling", "jitter_seconds"),
    "NOTIFY_ON_START": ("polling", "notify_on_start"),
    "WEB_PASSWORD": ("web", "password"),
    "DB_PATH": ("db_path",),
}


def _fill(dc, data: dict) -> None:
    """用嵌套 dict 就地填充 dataclass，忽略未知字段。"""
    for f in fields(dc):
        if f.name not in data:
            continue
        value = data[f.name]
        child = getattr(dc, f.name)
        if is_dataclass(child) and isinstance(value, dict):
            _fill(child, value)
        else:
            setattr(dc, f.name, value)


def _set_path(obj, path, value) -> None:
    for key in path[:-1]:
        obj = getattr(obj, key)
    setattr(obj, path[-1], value)


def load_config(path: str | Path | None = None) -> Config:
    """加载 config.yaml（如存在），再用环境变量覆盖。"""
    path = Path(path or os.environ.get("CONFIG_PATH", "config.yaml"))
    config = Config()
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        _fill(config, raw)
    for env_name, attr_path in _ENV_MAP.items():
        value = os.environ.get(env_name)
        if value is None:
            continue
        if env_name in ("POLLING_INTERVAL_SECONDS", "POLLING_JITTER_SECONDS"):
            value = int(value)
        elif env_name == "NOTIFY_ON_START":
            value = value.strip().lower() in ("1", "true", "yes")
        _set_path(config, attr_path, value)
    return config
