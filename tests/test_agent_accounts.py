"""行为器（Agent）账号注册表与配置解析的纯逻辑测试（票 #17 交付物 ⑤⑦）。

注册表语义（mx-behavior-logic.md §5）：云端没有账号表，接力账号注册表是
本地 agent 自管的新物——JSON 文件即可；每账号一个 Chrome profile；
token 更新时刻类比 settings 键 mx_token_updated_at 的云端先例。

配置语义：账号注册表与密钥循 .env/config 既有模式——账号名/角色来自
MX_AGENT_ACCOUNTS，密码按账号名走独立环境变量键，绝不落库不入日志
（scripts/mx_login.py:12-13 明文约定）。
"""
from __future__ import annotations

import json

from agent.accounts import Account, AccountRegistry, parse_accounts
from agent.config import AgentConfig, load_agent_config

# ---- 账号清单解析 ----

def test_parse_accounts_first_is_primary_second_is_backup():
    """逗号分隔账号：第一个是主账号、第二个是备用；顺序即接力优先级。"""
    accounts = parse_accounts("hemingfei,backup007")
    assert [a.user for a in accounts] == ["hemingfei", "backup007"]
    assert [a.role for a in accounts] == ["primary", "backup"]


def test_parse_accounts_strips_blank_and_order_preserved():
    accounts = parse_accounts(" a , ,b ,  ")
    assert [a.user for a in accounts] == ["a", "b"]
    assert accounts[0].role == "primary"
    assert accounts[1].role == "backup"


def test_parse_accounts_empty_returns_empty_list():
    assert parse_accounts("") == []
    assert parse_accounts(" , ,") == []


def test_account_password_env_key_uses_upper_sanitized_name():
    """密码环境变量键：MX_AGENT_PASSWORD_<账号名大写>，非字母数字转下划线。"""
    acc = Account(user="back-up 007", role="backup")
    assert acc.password_env_key() == "MX_AGENT_PASSWORD_BACK_UP_007"


# ---- 注册表持久化 ----

def test_registry_profile_dir_is_per_account_and_created(tmp_path):
    """每账号一个独立 Chrome profile 目录（ADR-0001：独立 profile 是硬前提）。"""
    reg = AccountRegistry(tmp_path / "accounts.json")
    d1 = reg.profile_dir("hemingfei")
    d2 = reg.profile_dir("backup007")
    assert d1 != d2
    assert d1.exists() and d2.exists()
    assert d1.parent == d2.parent
    # 同名账号目录稳定（重复调用不漂移）
    assert reg.profile_dir("hemingfei") == d1


def test_registry_token_roundtrip_and_updated_at(tmp_path):
    """token 存取 + 更新时刻记录；重启（新实例）后仍在。"""
    reg = AccountRegistry(tmp_path / "accounts.json")
    reg.set_token("hemingfei", "tok-abc", updated_at=1234.5)
    assert reg.token("hemingfei") == "tok-abc"
    assert reg.token_updated_at("hemingfei") == 1234.5

    reg2 = AccountRegistry(tmp_path / "accounts.json")
    assert reg2.token("hemingfei") == "tok-abc"
    assert reg2.token_updated_at("hemingfei") == 1234.5


def test_registry_unknown_account_token_is_none(tmp_path):
    reg = AccountRegistry(tmp_path / "accounts.json")
    assert reg.token("nobody") is None
    assert reg.token_updated_at("nobody") is None


def test_registry_last_room_per_account(tmp_path):
    """最后打开的房间按账号记录（云端 settings 键 mx_last_room 的本地等价，
    接力下不同账号各自的「恢复上次房间」互不串号）。"""
    reg = AccountRegistry(tmp_path / "accounts.json")
    reg.set_last_room("hemingfei", "格兰投研888")
    reg.set_last_room("backup007", "妖股刺客")
    assert reg.last_room("hemingfei") == "格兰投研888"
    assert reg.last_room("backup007") == "妖股刺客"
    # 持久化
    assert AccountRegistry(tmp_path / "accounts.json").last_room("backup007") == "妖股刺客"


def test_registry_corrupt_file_starts_empty(tmp_path):
    """坏 JSON 不炸：注册表是运行态缓存，损坏即从空表重建（损失可重建数据）。"""
    path = tmp_path / "accounts.json"
    path.write_text("{not json", encoding="utf-8")
    reg = AccountRegistry(path)
    assert reg.token("hemingfei") is None


def test_registry_file_never_contains_password(tmp_path):
    """密码绝不进注册表文件：注册表只存 profile 路径/token/房间等运行态。"""
    reg = AccountRegistry(tmp_path / "accounts.json")
    reg.set_token("hemingfei", "tok", updated_at=1.0)
    raw = (tmp_path / "accounts.json").read_text(encoding="utf-8")
    assert "password" not in raw.lower()
    data = json.loads(raw)
    assert set(data["hemingfei"]) <= {"profile_dir", "token", "token_updated_at", "last_room"}


# ---- 配置加载（.env 既有模式） ----

def _set_env(monkeypatch, **kv):
    for k, v in kv.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


def test_load_config_reads_accounts_origin_rooms_port(monkeypatch, tmp_path):
    _set_env(
        monkeypatch,
        MX_AGENT_ACCOUNTS="hemingfei,backup007",
        MX_AGENT_PASSWORD_HEMINGFEI="pw1",
        MX_AGENT_PASSWORD_BACKUP007="pw2",
        MX_LOGIN_ORIGIN="https://mx.example.com",
        MX_AGENT_CDP_PORT="9333",
        MX_AGENT_ROOMS='["房A","房B"]',
        MX_AGENT_DATA_DIR=str(tmp_path / "agentdata"),
    )
    cfg = load_agent_config()
    assert isinstance(cfg, AgentConfig)
    assert [a.user for a in cfg.accounts] == ["hemingfei", "backup007"]
    assert cfg.password_of(cfg.accounts[0]) == "pw1"
    assert cfg.password_of(cfg.accounts[1]) == "pw2"
    assert cfg.origin == "https://mx.example.com"
    assert cfg.cdp_port == 9333
    assert cfg.rooms == ["房A", "房B"]
    assert cfg.data_dir == tmp_path / "agentdata"


def test_load_config_defaults(monkeypatch, tmp_path):
    """默认值：域名沿用 mx_login 先例默认；端口/数据目录/房间清单可开箱即跑。"""
    _set_env(
        monkeypatch,
        MX_AGENT_ACCOUNTS=None,
        MX_LOGIN_ORIGIN=None,
        MX_AGENT_CDP_PORT=None,
        MX_AGENT_ROOMS=None,
        MX_AGENT_DATA_DIR=None,
    )
    cfg = load_agent_config()
    assert cfg.accounts == []
    assert cfg.origin == "https://mx.2026.foodtop1.com"
    assert cfg.cdp_port == 9223
    assert cfg.rooms and isinstance(cfg.rooms, list)
    assert cfg.data_dir.name == "agent"


def test_load_config_missing_password_is_empty_not_error(monkeypatch, tmp_path):
    """缺账号密码不炸：返回空串，登录链路到用时才报「缺凭据」。"""
    _set_env(
        monkeypatch,
        MX_AGENT_ACCOUNTS="hemingfei",
        MX_AGENT_PASSWORD_HEMINGFEI=None,
        MX_AGENT_DATA_DIR=str(tmp_path),
    )
    cfg = load_agent_config()
    assert cfg.password_of(cfg.accounts[0]) == ""


def test_config_requires_no_config_yaml(monkeypatch, tmp_path):
    """行为器不依赖云端 config.yaml：纯环境变量 + 本地数据目录（ADR-0001
    本地组件自管，agent 不感知云端配置体系）。"""
    monkeypatch.chdir(tmp_path)
    _set_env(
        monkeypatch,
        MX_AGENT_ACCOUNTS="u1",
        MX_AGENT_PASSWORD_U1="p",
        MX_AGENT_DATA_DIR=str(tmp_path / "d"),
    )
    assert load_agent_config().accounts[0].user == "u1"
