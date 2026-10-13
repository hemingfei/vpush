"""MX 平台「切换房间」实机抓包工具（本地 Chrome，Playwright 驱动）。

复现真人行为链：seed localStorage token 自动登录（官方「关窗重开自动登录」
路径）→ 等冷启动完成 → 逐个点击房间（有新消息/无新消息/回访）→ 记录每次
切换发出的全部 HTTP 请求（含 body）与 WebSocket 双向帧 → 输出逐房差异报告。

用途：核对官方客户端切房间的请求足迹（2026-09-02 抓包结论在新域 /5 上的
复测，以及「切房间是否 emit WS 事件」的 ground truth）。

用法（凭据一律走环境变量，绝不写入文件/仓库）：
    MX_PROBE_TOKEN=<token> python scripts/mx_room_switch_capture.py
    # 或验证码登录路径：MX_PROBE_USER=... MX_PROBE_PASS=... MX_PROBE_CODE=1234
    # 可选：MX_PROBE_BASE（默认 https://mx.2026.foodtop1.com）
    #       MX_PROBE_HEADLESS=1 无头；MX_PROBE_ROOMS='["房间A","房间B"]'
输出：.scratch/mx_room_switch_<ts>.md（人读）+ .json（原始帧/请求）
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

BASE = os.environ.get("MX_PROBE_BASE", "https://mx.2026.foodtop1.com").rstrip("/")
OUT_DIR = Path(".scratch")
SETTLE_SECONDS = 10.0   # 开窗后等冷启动安静
DWELL_SECONDS = 12.0    # 每个房间停留（含切换请求全量落地）
HOSTURL = "/business-api/5"
API_RE = re.compile(r"/api/|socket\.io")


def now_ms() -> float:
    return time.time()


def ts_of(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M:%S.%f")[:-3]


class Recorder:
    """请求 + WS 帧统一记录（附着在 Playwright 事件上，跨点击累积）。"""

    def __init__(self):
        self.reqs: list[dict] = []
        self.frames: list[dict] = []

    def attach(self, page):
        page.on("request", self._on_request)
        page.on("websocket", self._on_ws)

    def _on_request(self, request):
        try:
            self.reqs.append({
                "t": ts_of(now_ms()),
                "method": request.method,
                "url": request.url,
                "body": (request.post_data or "")[:400] or None,
                "kind": "ws-handshake" if request.resource_type == "websocket" else request.resource_type,
            })
        except Exception:
            pass

    def _on_ws(self, ws):
        path = urlparse(ws.url).path
        self.frames.append({"t": ts_of(now_ms()), "dir": "OPEN", "data": path})
        ws.on("framesent", lambda p: self._frame("SEND", p))
        ws.on("framereceived", lambda p: self._frame("RECV", p))
        ws.on("close", lambda _: self.frames.append({"t": ts_of(now_ms()), "dir": "CLOSE", "data": ""}))

    def _frame(self, direction: str, payload):
        data = payload if isinstance(payload, str) else bytes(payload).decode("utf-8", "replace")
        self.frames.append({"t": ts_of(now_ms()), "dir": direction, "data": data[:300]})

    def marker(self) -> tuple[int, int]:
        return len(self.reqs), len(self.frames)

    def delta(self, mark: tuple[int, int]) -> tuple[list[dict], list[dict]]:
        api = [r for r in self.reqs[mark[0]:] if API_RE.search(r["url"])]
        return api, self.frames[mark[1]:]


def seed_login_storage(page, token: str, user: str):
    """官方自动登录的最小 localStorage 集（抓包实测键名）。"""
    page.evaluate(
        """([token, user]) => {
        localStorage.setItem('mx_web_token', JSON.stringify(token));
        localStorage.setItem('mx_web_hosturl', JSON.stringify('/business-api/5'));
        localStorage.setItem('mx_web_raw_hosturl', JSON.stringify('/5'));
        localStorage.setItem('mx_web_login_account', JSON.stringify({ user }));
        localStorage.setItem('mx_web_dark_mode', 'false');
    }""",
        [token, user],
    )


def dismiss_modals(page):
    """关掉开窗弹窗（系统公告等），真人开窗第一件事就是点掉它。"""
    for _ in range(3):
        backdrop = page.locator(".modal-backdrop")
        if backdrop.count() == 0 or not backdrop.first.is_visible():
            return
        for sel in ("button:has-text('知道了')", "button:has-text('确定')",
                    "button:has-text('关闭')", "[class*='close']", ".close"):
            btn = backdrop.first.locator(sel)
            if btn.count():
                try:
                    btn.first.click(timeout=1500)
                    page.wait_for_timeout(600)
                    break
                except Exception:  # noqa: BLE001 - 换下一个候选
                    continue
        else:
            try:
                backdrop.first.click(position={"x": 12, "y": 12}, timeout=1500)
            except Exception:  # noqa: BLE001
                page.keyboard.press("Escape")
        page.wait_for_timeout(800)


def open_room(page, name: str) -> dict:
    """点击左侧房间列表里名为 name 的房间（点房间名 strong，避开列表中部的 AI 按钮）。

    返回 {before, after}：点击前后条目文本（用于观察未读徽标是否被清掉）。
    """
    # 官方 DOM 的列表项是 role=button 元素（非 <button> 标签），accessible name
    # 以房间名开头；点它内部的 <strong>（房间名文本）避免命中中部 AI 按钮
    item = page.get_by_role("button", name=re.compile(f"^{re.escape(name)}")).first
    if item.count() == 0:
        raise RuntimeError(f"房间列表里没找到：{name}")
    before = " ".join(item.inner_text().split())
    try:
        item.locator("strong").first.click(timeout=3000)
    except Exception:  # noqa: BLE001 - 无 strong 时点左侧头像区
        item.click(position={"x": 40, "y": 20})
    page.wait_for_timeout(int(DWELL_SECONDS * 1000))
    after = " ".join(item.inner_text().split())
    return {"before": before, "after": after}


def fmt_delta(api: list[dict], frames: list[dict]) -> list[str]:
    lines = []
    for r in api:
        short = r["url"].replace(BASE, "")
        lines.append(f"  HTTP {r['t']} {r['method']} {short}" + (f"  body={r['body']}" if r["body"] else ""))
    for f in frames:
        data = f["data"].replace("\n", " ")[:160]
        lines.append(f"  WS   {f['t']} {f['dir']} {data}")
    return lines or ["  （无）"]


def main() -> int:
    token = os.environ.get("MX_PROBE_TOKEN", "").strip()
    user = os.environ.get("MX_PROBE_USER", "hemingfei").strip()
    if not token:
        print("缺 MX_PROBE_TOKEN（或走验证码路径：MX_PROBE_USER/PASS/CODE，见文件头注释）", file=sys.stderr)
        return 2

    rooms: list[str] = json.loads(os.environ.get("MX_PROBE_ROOMS", "null")) or [
        "格兰投研888",   # 未读 99
        "妖股刺客",      # 未读 26
        "姆爷的守护",    # 无未读徽标
        "老樊",          # 无未读徽标
        "格兰投研888",   # 回访（本会话已打开过的房间）
    ]

    OUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rec = Recorder()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=os.environ.get("MX_PROBE_HEADLESS", "") == "1",
            args=["--window-size=1440,900"],
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 860},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = ctx.new_page()
        rec.attach(page)  # 导航前挂上，抓全冷启动 + WS 握手

        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        seed_login_storage(page, token, user)
        mark_boot = rec.marker()
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("text=直播间", timeout=30000)
        page.wait_for_timeout(int(SETTLE_SECONDS * 1000))
        dismiss_modals(page)
        page.wait_for_timeout(1000)
        boot_api, boot_ws = rec.delta(mark_boot)

        report: list[dict] = []
        for i, name in enumerate(rooms, 1):
            mark = rec.marker()
            try:
                dismiss_modals(page)
                badge = open_room(page, name)
            except Exception as exc:  # noqa: BLE001 - 单房失败不影响后续
                shot = OUT_DIR / f"mx_probe_fail_{i}.png"
                try:
                    page.screenshot(path=str(shot))
                except Exception:  # noqa: BLE001
                    shot = None
                report.append({"step": i, "room": name,
                               "error": str(exc), "screenshot": str(shot) if shot else None})
                continue
            api, frames = rec.delta(mark)
            report.append({
                "step": i, "room": name,
                "item_before": badge["before"], "item_after": badge["after"],
                "http": api, "ws": frames,
            })
            print(f"[{i}/{len(rooms)}] {name}: {len(api)} 个 API 请求, {len(frames)} 个 WS 帧")

        browser.close()

    # ---- 报告 ----
    rid_map = {}
    for r in rec.reqs:
        m = re.search(r"/api/room/view$", r["url"])
        if m and r["body"]:
            try:
                rid_map[json.loads(r["body"]).get("rid")] = r["t"]
            except Exception:
                pass

    md = [f"# MX 切房间实机抓包（{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}，{BASE}）", ""]
    md.append("## 冷启动（token 自动登录）")
    md += fmt_delta(*rec.delta(mark_boot))
    for step in report:
        md.append(f"\n## 第 {step.get('step')} 次：{step.get('room')}")
        if "error" in step:
            md.append(f"- ❌ 点击失败：{step['error']}")
            continue
        md.append(f"- 列表项点击前：`{step['item_before']}`")
        md.append(f"- 列表项点击后：`{step['item_after']}`")
        md.append("- 本次切换产生的 API/WS：")
        md += fmt_delta(step["http"], step["ws"])
    (OUT_DIR / f"mx_room_switch_{stamp}.md").write_text("\n".join(md), encoding="utf-8")
    (OUT_DIR / f"mx_room_switch_{stamp}.json").write_text(
        json.dumps({"base": BASE, "rooms": rooms, "report": report,
                    "boot_api": boot_api, "boot_ws": boot_ws,
                    "all_requests": rec.reqs, "all_frames": rec.frames},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"报告：{OUT_DIR / f'mx_room_switch_{stamp}.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
