#!/usr/bin/env python3
"""MX 行为器（Agent）常驻进程入口（票 #17 交付物 ⑧，ADR-0001 本地组件）。

本地运行（仓库根目录）：
    .venv/Scripts/python.exe scripts/mx_agent.py            # 前台常驻（Ctrl+C 停）
    python scripts/mx_agent.py --validate                   # 只做导入/配置/纯逻辑自检，不碰浏览器
    python scripts/mx_agent.py --dump-config                # 打印配置解析结果后退出

配置（.env，凭据绝不入源码/仓库；行为器不依赖 config.yaml）：
    MX_AGENT_ACCOUNTS=主账号,备用账号        逗号分隔，顺序即接力优先级（首个主账号）
    MX_AGENT_PASSWORD_<账号大写>=密码         每账号一个键（如 MX_AGENT_PASSWORD_HEMINGFEI）
    MX_LOGIN_ORIGIN=https://...              登录域名（复用 mx_login 既有键）
    MX_AGENT_CDP_PORT=9223                   专用 Chrome 调试端口
    MX_AGENT_ROOMS='["房A","房B"]'           切房目标池 JSON
    MX_AGENT_DATA_DIR=data/agent             数据目录（注册表/当日计划/生命周期日志）
    MX_AGENT_ALWAYS_ON=1                     全天在线：打开软件即登录监听，关进程才下线（旁路窗口）
    MX_AGENT_WINDOWS='[["07:00","11:30"]]'   自定义窗口 JSON（覆盖默认三段随机窗；确定性无漂移）
    MX_AGENT_CHROME_EXE=C:/path/chrome.exe  Chrome 可执行文件覆盖
    视觉识码：MX_VISION_* 或 LLM_*（与 scripts/mx_login.py --ai-ocr 同一套）

行为面（唯一行为决策者）：三段随机窗口开关专用 Chrome、每 5-10 分钟真点击
切房间、掉登录态 AI 视觉识码重登、账号失效接力切换。agent 不感知采集器
（互不感知，ADR-0001）；不做云端兜底（Q4）；不新增拟人动作（Q6）。

真实浏览器链路不进 CI：验收由 48h 挂机覆盖（spec 裁定）；
本地可复现验证脚本见 scripts/mx_agent_validate.py。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _load_env() -> None:
    """根目录 .env 注入环境变量（mx_login.py:445 先例；缺席则跳过）。"""
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except ImportError:
        pass


def _build_components():
    """组装 runner 的全部组件（--validate 与常驻模式共用）。"""
    from agent.config import load_agent_config
    from agent.lifecycle import LifecycleLog
    from agent.runner import AgentRunner

    config = load_agent_config()
    log = LifecycleLog(config.data_dir / "lifecycle.jsonl")
    runner = AgentRunner(config, log=log)
    return config, log, runner


def _validate() -> int:
    """本地自检：导入/配置/纯逻辑链路，不真连 MX 不碰浏览器（票验收口径）。"""
    config, _log, runner = _build_components()
    accounts = ", ".join(a.user for a in config.accounts) or "（未配置）"
    print("✓ 组件导入/配置解析 OK")
    print(f"  账号清单：{accounts}")
    print(f"  登录域名：{config.origin}")
    print(f"  CDP 端口：{config.cdp_port}；数据目录：{config.data_dir}")
    print(f"  房间池：{config.rooms}")
    missing = [a.user for a in config.accounts if not config.password_of(a)]
    if missing:
        print(f"⚠ 缺账号密码环境变量：{missing}（常驻运行前需补齐）")
    from scripts.mx_login import vision_configured
    print(f"  视觉识码：{'已配置' if vision_configured() else '未配置（掉登录态重登需要 MX_VISION_* 或 LLM_*）'}")
    # 纯逻辑冒烟：当日计划生成 + 接力状态机决策 + 切房目标选择
    from datetime import datetime

    from app.services.mx_window import CN_TZ, build_daily_plan

    plan = build_daily_plan(datetime.now(CN_TZ).date())
    print(f"  当日计划冒烟：{len(plan.windows)} 段窗口 "
          + " / ".join(f"{s:%H:%M}-{e:%H:%M}" for s, e in plan.windows))
    if runner.relay.accounts:
        print(f"  接力冒烟：主账号 {runner.relay.active.user}（活跃），备用待命")
    print(f"  生命周期日志：{config.data_dir / 'lifecycle.jsonl'}")
    print("✓ 自检通过（未启动浏览器；真实链路验证跑 scripts/mx_agent_validate.py）")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MX 行为器（Agent）常驻进程")
    parser.add_argument("--validate", action="store_true",
                        help="导入/配置/纯逻辑自检后退出，不启动浏览器")
    parser.add_argument("--dump-config", action="store_true",
                        help="打印配置解析结果后退出")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    _load_env()

    if args.dump_config:
        config, _log, runner = _build_components()
        for a in config.accounts:
            print(f"account={a.user} role={a.role} profile={config.registry().profile_dir(a.user)}")
        print(f"origin={config.origin} cdp_port={config.cdp_port} rooms={config.rooms}")
        mode = "always_on" if config.always_on else (
            f"custom={config.windows}" if config.windows else "default-plan")
        print(f"window_mode={mode}")
        print(f"data_dir={config.data_dir}")
        return 0

    if args.validate:
        return _validate()

    config, _log, runner = _build_components()
    try:
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        print("\n行为器停止（Ctrl+C）")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
