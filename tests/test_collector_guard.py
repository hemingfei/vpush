"""采集宿主守护（#22 宿主守护面）纯逻辑测试。

锁定语义（ticket 交付物口径）：
- 锁/探测分类全部注入桩离线跑——绝不真起浏览器（真浏览器链路不进
  CI，spec 裁定，48h 挂机验收覆盖）；
- 启动参数 = 手动恢复配方（--load-extension + 持久 profile + CDP 端口 +
  MX 首页），且零自动化痕迹（--enable-automation/--headless 红线，
  ADR-0001 与 agent.executor.chrome_launch_args 同口径）；
- 异种浏览器（端口被非采集器 Chrome 占）绝不动手——2026-11-15 事故的
  教训是「误判动手」而非「漏拉一次」。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.mx_collector_guard import (  # noqa: E402
    CollectorConfig,
    _is_collector_target,
    load_collector_config,
    probe_health,
)

# ---- 配置：环境变量旋钮 ----


def _clear_env(monkeypatch):
    for key in (
        "MX_COLLECTOR_CHROME_EXE",
        "MX_COLLECTOR_PROFILE_DIR",
        "MX_COLLECTOR_EXTENSION_DIR",
        "MX_COLLECTOR_ORIGIN",
        "MX_COLLECTOR_CDP_PORT",
        "MX_LOGIN_ORIGIN",
    ):
        monkeypatch.delenv(key, raising=False)


def test_config_defaults_match_manual_recipe(monkeypatch, tmp_path):
    """默认配置即 2026-11-15 实证的手动恢复配方（.scratch 持久 profile + 9223）。"""
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)  # cwd 无关：路径锚 REPO，不锚 cwd
    cfg = load_collector_config()
    assert cfg.cdp_port == 9223
    assert cfg.profile_dir.name == "mx-collector-profile"
    assert cfg.extension_dir.name == "extension"
    assert cfg.origin == "https://mx.2026.foodtop1.com"
    assert cfg.chrome_exe  # 探测得到或 PATH 兜底，非空


def test_config_env_overrides(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("MX_COLLECTOR_CHROME_EXE", "C:/pw/chrome.exe")
    monkeypatch.setenv("MX_COLLECTOR_PROFILE_DIR", "D:/prof")
    monkeypatch.setenv("MX_COLLECTOR_EXTENSION_DIR", "D:/ext")
    monkeypatch.setenv("MX_COLLECTOR_ORIGIN", "https://mx.example.com/")
    monkeypatch.setenv("MX_COLLECTOR_CDP_PORT", "9333")
    cfg = load_collector_config()
    assert cfg.chrome_exe == "C:/pw/chrome.exe"
    assert cfg.profile_dir == Path("D:/prof")
    assert cfg.extension_dir == Path("D:/ext")
    assert cfg.origin == "https://mx.example.com"  # 尾斜杠剥掉
    assert cfg.cdp_port == 9333


def test_config_origin_falls_back_to_mx_login_origin(monkeypatch):
    """MX_COLLECTOR_ORIGIN 缺席时复用 MX_LOGIN_ORIGIN（与 agent 配置同源）。"""
    _clear_env(monkeypatch)
    monkeypatch.setenv("MX_LOGIN_ORIGIN", "https://login.example.com/")
    cfg = load_collector_config()
    assert cfg.origin == "https://login.example.com"


def test_config_bad_port_defaults(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("MX_COLLECTOR_CDP_PORT", "not-a-port")
    assert load_collector_config().cdp_port == 9223


# ---- 启动参数：手动恢复配方 + 零自动化痕迹 ----


def _cfg(**over):
    base = {
        "chrome_exe": "C:/pw/chrome.exe",
        "profile_dir": Path("D:/prof"),
        "extension_dir": Path("D:/ext"),
        "origin": "https://mx.example.com",
        "cdp_port": 9223,
    }
    base.update(over)
    return CollectorConfig(**base)


def test_launch_args_match_manual_recipe():
    args = _cfg().launch_args()
    assert f"--load-extension={Path('D:/ext')}" in args
    assert f"--user-data-dir={Path('D:/prof')}" in args
    assert "--remote-debugging-port=9223" in args
    assert "https://mx.example.com" in args  # MX 首页：spawn 即打开
    assert args[0] == "C:/pw/chrome.exe"  # exe 打头（Popen argv 形态）


def test_launch_args_no_automation_fingerprint():
    """红线：绝不带 --enable-automation/--headless（ADR-0001 自动化痕迹）。"""
    joined = " ".join(_cfg().launch_args())
    assert "--enable-automation" not in joined
    assert "--headless" not in joined


def test_launch_args_config_wired():
    """旋钮进参数：改端口/profile/exe 全部反映到 argv。"""
    args = _cfg(
        cdp_port=9555, profile_dir=Path("P2"), chrome_exe="X:/chrome.exe"
    ).launch_args()
    joined = " ".join(args)
    assert "--remote-debugging-port=9555" in joined
    assert "--user-data-dir=P2" in joined
    assert args[0] == "X:/chrome.exe"


# ---- 健康分类（注入 fake fetcher） ----


def _targets_json(targets) -> str:
    return json.dumps(targets)


class _FakeFetch:
    """可编排的 CDP fetch 桩：按 URL 返回 /json/list 内容或抛错。"""

    def __init__(self, *, targets=None, fail=False):
        self.targets = targets or []
        self.fail = fail
        self.calls: list[str] = []

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        if self.fail:
            raise OSError("connection refused")
        return _targets_json(self.targets)


MX_PAGE = {"type": "page", "url": "https://mx.example.com/live"}
SW = {
    "type": "service_worker",
    "url": "chrome-extension://ibagiomlfclfpelekbaohmjbeickkchh/sw.js",
}


def test_probe_healthy_with_sw_and_mx_page():
    cfg = _cfg()
    fetch = _FakeFetch(targets=[MX_PAGE, SW])
    assert probe_health(config=cfg, fetch=fetch)["kind"] == "healthy"
    assert fetch.calls and "/json/list" in fetch.calls[0]


def test_probe_port_closed():
    """端口不通（fetch 报错）→ 该拉起。"""
    cfg = _cfg()
    assert (
        probe_health(config=cfg, fetch=_FakeFetch(fail=True))["kind"] == "port_closed"
    )


def test_probe_foreign_browser_not_collector():
    """端口通但没有 unpacked sw.js 目标 = 异种 Chrome（pytest 残留/日常
    浏览器）——分类为 foreign，动手与否由调用方裁定（本守护绝不动）。"""
    cfg = _cfg()
    fetch = _FakeFetch(
        targets=[
            {"type": "page", "url": "https://example.com/"},
            # Store 组件 SW 的 URL 不以 /sw.js 结尾（带组件名），不会误判
            {
                "type": "service_worker",
                "url": "chrome-extension://ghbmnnjooepelmjcndidkpnffknjibdk/"
                "Google-Network-Speech.js",
            },
        ]
    )
    assert probe_health(config=cfg, fetch=fetch)["kind"] == "foreign"


def test_probe_foreign_when_only_builtin_components():
    """Chrome 内置组件扩展（语音识别等）不判我们的——extension id 逐个
    排除不可行，判据是「unpacked sw.js」而非黑名单。"""
    cfg = _cfg()
    fetch = _FakeFetch(
        targets=[
            {
                "type": "service_worker",
                "url": "chrome-extension://abc/Google-voice-search-sw.js",
            },
        ]
    )
    assert probe_health(config=cfg, fetch=fetch)["kind"] == "foreign"


def test_probe_mx_tab_missing_still_reports_host_alive():
    """宿主健康但 MX 页没了：kind=mx_tab_missing（只告警不代开，#22 裁定）。"""
    cfg = _cfg()
    fetch = _FakeFetch(
        targets=[
            SW,
            {"type": "page", "url": "chrome://newtab/"},
        ]
    )
    assert probe_health(config=cfg, fetch=fetch)["kind"] == "mx_tab_missing"


def test_probe_sw_url_matcher_does_not_hardcode_id():
    """扩展 ID 逐机漂移（unpacked）：判据只认 chrome-extension://…/sw.js。"""
    assert _is_collector_target({"url": "chrome-extension://ANYTHING/sw.js"})
    assert not _is_collector_target({"url": "https://mx.example.com/live"})
    assert not _is_collector_target({"url": "chrome-extension://ANY/other.js"})


def test_probe_bad_json_is_port_closed():
    """/json/list 返回坏 JSON → 按端口不通处理（保守拉起路径）。"""

    class _BadJson:
        def __call__(self, url, timeout=None):
            return "{not json"

    assert probe_health(config=_cfg(), fetch=_BadJson())["kind"] == "port_closed"


# ---- tick 语义：agent 锁与端口真空的解耦（2026-11-15 演练实锤）----


def test_tick_spawns_when_agent_lock_held_but_port_closed(monkeypatch, tmp_path):
    """agent 锁被持 ≠ agent 有浏览器：端口空必须拉起（agent 下一 tick adopt）。

    回归锁定：原实现「锁在即让位」导致采集宿主被杀后 9223 空转无人接管。
    """
    from scripts import mx_collector_guard as g

    calls = []
    monkeypatch.setattr(g, "agent_owns_port", lambda: True)
    monkeypatch.setattr(
        g, "probe_health", lambda config, fetch: {"kind": "port_closed"}
    )
    monkeypatch.setattr(g, "spawn_collector", lambda cfg: calls.append(cfg))
    monkeypatch.setattr(g, "_log", lambda msg: None)
    result = g.tick(_cfg(), fetch=_FakeFetch(fail=True))
    assert result["spawned"] is True
    assert len(calls) == 1


def test_tick_stands_down_only_for_foreign_browser(monkeypatch):
    """锁在 + 端口在但非本扩展宿主（agent branded 领地）→ 让位不碰。"""
    from scripts import mx_collector_guard as g

    calls = []
    monkeypatch.setattr(g, "agent_owns_port", lambda: True)
    monkeypatch.setattr(g, "probe_health", lambda config, fetch: {"kind": "foreign"})
    monkeypatch.setattr(g, "spawn_collector", lambda cfg: calls.append(cfg))
    monkeypatch.setattr(g, "_log", lambda msg: None)
    result = g.tick(_cfg(), fetch=_FakeFetch())
    assert result["kind"] == "foreign"
    assert result["spawned"] is False
    assert calls == []
