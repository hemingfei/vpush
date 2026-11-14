"""CDPExecutor 可单测部分的纯逻辑测试（票 #17 交付物 ①）。

不真连浏览器（真实链路 48h 挂机验收覆盖，spec 裁定）——只测：
- connect-over-CDP URL 组装；
- 干净启动参数：专用 profile、独立调试端口、**不带 --enable-automation**、
  不带 --headless、不带 Playwright/自动化痕迹（ADR-0001 否决纯 CDP agent
  的理由正是「自动化痕迹常驻」——这是产品红线，值得锁测试）；
- profile seed 免登的 localStorage 键集（scripts/mx_room_switch_capture.py:88
  抓包实测键名，mx-behavior-logic.md §3）；
- 点击选择器：点房间名 strong、回落头像区（真点击先例）。
"""
from __future__ import annotations

from pathlib import Path

from agent.executor import (
    CDPExecutor,
    cdp_endpoint_url,
    chrome_launch_args,
    seed_storage_script,
)

# ---- URL 组装 ----

def test_cdp_endpoint_url():
    assert cdp_endpoint_url(9333) == "http://127.0.0.1:9333"
    assert cdp_endpoint_url(0) == "http://127.0.0.1:0"


# ---- 干净启动参数 ----

def test_launch_args_clean_profile_no_automation_flags():
    args = chrome_launch_args(
        exe="C:/chrome.exe",
        user_data_dir=Path("p/a"),
        cdp_port=9333,
        origin="https://mx.example.com",
    )
    joined = " ".join(args)
    # 红线：不得携带任何自动化痕迹（ADR-0001 否决纯 CDP agent 的理由）
    assert "--enable-automation" not in joined
    assert "--headless" not in joined
    assert "--remote-allow-origins" not in joined
    assert "--disable-blink-features=AutomationControlled" not in joined
    # 必须：独立 profile + CDP 端口 + 干净首启 + MX 首页（profile 用
    # as_posix 断言，Windows 下 Path 会把 / 渲染成 \——分隔符不是行为）
    assert any(a.startswith("--user-data-dir=") and
               Path(a.split("=", 1)[1]).as_posix() == "p/a" for a in args)
    assert "--remote-debugging-port=9333" in joined
    assert "--no-first-run" in joined
    assert "--no-default-browser-check" in joined
    assert args[0] == "C:/chrome.exe"
    assert args[-1] == "https://mx.example.com"


def test_launch_args_exclude_home_profile(tmp_path):
    """profile 必须是 agent 数据目录内的专用目录——绝不能指向系统默认
    user-data-dir（Chrome 136+ 默认目录远程调试失效 + 污染真人日常 profile
    双重红线）。"""
    dedicated = tmp_path / "profiles" / "acc1"
    args = chrome_launch_args(
        exe="chrome", user_data_dir=dedicated, cdp_port=1, origin="https://mx.example.com"
    )
    assert f"--user-data-dir={dedicated}" in args


# ---- profile seed 免登 ----

def test_seed_storage_script_keys_match_capture_precedent():
    """localStorage 五键与 scripts/mx_room_switch_capture.py:88 实测集一致：
    mx_web_token(JSON.stringify)/mx_web_hosturl('/business-api/5')/
    mx_web_raw_hosturl('/5')/mx_web_login_account({user})/mx_web_dark_mode。
    """
    script = seed_storage_script()
    for key in ("mx_web_token", "mx_web_hosturl", "mx_web_raw_hosturl",
                "mx_web_login_account", "mx_web_dark_mode"):
        assert f"'{key}'" in script or f'"{key}"' in script
    assert "JSON.stringify(token)" in script
    assert "'/business-api/5'" in script or '"/business-api/5"' in script


def test_seed_storage_script_is_callable_js():
    """脚本可被 page.evaluate 调用：形如函数表达式，参数 (token, user)。"""
    script = seed_storage_script()
    assert "=>" in script or script.startswith(("(", "function"))
    assert "token" in script and "user" in script


# ---- 房间点击选择器（真点击先例搬运） ----

def test_room_selector_prefers_strong_fallback_position():
    """点房间名 strong；无 strong 回落左上头像区 (40, 20)——
    scripts/mx_room_switch_capture.py open_room 的选择器先例。"""
    assert CDPExecutor.ROOM_STRONG_SELECTOR == "strong"
    assert CDPExecutor.FALLBACK_CLICK_OFFSET == {"x": 40, "y": 20}
