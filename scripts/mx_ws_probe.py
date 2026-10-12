#!/usr/bin/env python3
"""MX WS 被踢诊断工具：同一 token 下对比多种 WS 客户端人格，定位踢连根因。

背景（2026-10-12）：平台换域名 mx.2026.foodtop1.com 后，vpush 生产 WS 频繁被踢
且重连失败。真实浏览器抓包 ground truth（Playwright + addInitScript 钩子）：
- 端点   wss://<host>/business-api/4/socket.io/?EIO=4&transport=websocket
- ns     /msg；认证帧 40/msg,{"tt":ms,"token":...,"version":"web"}（紧凑 JSON）
- 心跳   engine.io v4：服务端每 25s 发 "2"，客户端立即回 "3"
- 域名无 cookie；浏览器连接长时间存活（被踢非账号封禁/平台全局踢）

本工具按序运行三种变体（同一 token、同一网络环境）做 A/B：
- prod       生产同款：python-socketio + aiohttp（app.fetchers.mx.ws.MxWsClient 原类）
- curlffi    curl_cffi impersonate chrome146 的 WS 握手（Chrome TLS 指纹）+ 手写
             最小 Engine.IO/Socket.IO 客户端
- aiohttp    同一手写最小客户端但走 aiohttp（与 curlffi 只差 TLS 指纹/头形态，
             用于隔离「TLS 指纹」与「协议行为」两个变量）

判读：
- prod 被踢 / curlffi 存活        → WS 握手指纹检测（TLS/头），修 ws.py 换 transport
- prod 与 curlffi 都被踢、浏览器活 → 行为层检测（心跳时序/请求足迹）或单会话策略
- 全部存活                        → 间歇性平台问题，用 --watch 长跑观察

用法（仓库根目录）：
    python scripts/mx_ws_probe.py                     # 登录(验证码走视觉模型)+三变体各 120s
    python scripts/mx_ws_probe.py --token <t>         # 跳过登录
    python scripts/mx_ws_probe.py --duration 45 --repeat 3
    python scripts/mx_ws_probe.py --watch curlffi     # 单变体长跑监控（Ctrl+C 结束）
    python scripts/mx_ws_probe.py --login-only        # 只登录取 token

凭据读根目录 .env：MX_ACCOUNT / MX_PASSWORD；视觉识码用 MX_VISION_*/LLM_*
（Ark 多模态，与 Jenkins mx-token 任务同源）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

DEFAULT_ORIGIN = "https://mx.2026.foodtop1.com"
EIO_QUERY = "EIO=4&transport=websocket"

JSONL_PATH = REPO / ".scratch" / "mx_ws_probe.jsonl"


def log_event(variant: str, ev: str, **detail) -> None:
    """统一事件输出：控制台一行 + JSONL 落盘（供事后分析时序）。"""
    record = {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "mono": round(time.monotonic(), 3),
        "variant": variant,
        "ev": ev,
        **detail,
    }
    parts = [f"[{variant}] {ev}"]
    for key, value in detail.items():
        text = str(value)
        if len(text) > 160:
            text = text[:160] + "…"
        parts.append(f"{key}={text}")
    print(" ".join(parts), flush=True)
    try:
        JSONL_PATH.parent.mkdir(exist_ok=True)
        with JSONL_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


# ---- 浏览器人格握手头（与 app.fetchers.mx.ws._browser_handshake_headers 同口径）----

def chrome_ws_headers(ws_url: str) -> dict[str, str]:
    from app.fetchers.mx.ws import (
        ACCEPT_LANGUAGE,
        BROWSER_UA,
        SEC_CH_UA,
        SEC_CH_UA_MOBILE,
        SEC_CH_UA_PLATFORM,
    )

    host = urlparse(ws_url).netloc
    return {
        "User-Agent": BROWSER_UA,
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": ACCEPT_LANGUAGE,
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": SEC_CH_UA_MOBILE,
        "sec-ch-ua-platform": SEC_CH_UA_PLATFORM,
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "websocket",
        "sec-fetch-dest": "empty",
        "Origin": f"https://{host}",
    }


def compact_auth(token: str, namespace: str) -> str:
    """Socket.IO CONNECT 载荷：紧凑 JSON（与官方前端 JSON.stringify 一致）。"""
    payload = json.dumps(
        {"tt": int(time.time() * 1000), "token": token, "version": "web"},
        separators=(",", ":"),
    )
    return f"40{namespace}," + payload


# ---- 登录（复用 app.fetchers.mx.login 全链路 + Ark 视觉识码）----

def do_login(origin: str, attempts: int = 4) -> dict:
    from app.fetchers.mx.client import MXClient
    from app.fetchers.mx.login import MXLoginError, classify_captcha, fetch_captcha, login

    from mx_login import ai_ocr  # scripts/mx_login.py：SVG 栅格化 + 视觉模型

    api_base = f"{origin.rstrip('/')}/business-api/4"
    client = MXClient(api_base, "")
    last_err = ""
    try:
        for _ in range(max(1, attempts)):
            cap = fetch_captcha(client)
            kind, payload = classify_captcha(cap["captcha"])
            code = ""
            if kind == "image":
                guess = ai_ocr(payload)
                if guess:
                    code = guess.strip()
                    log_event("login", "captcha_ocr", code=code)
            else:
                log_event("login", "captcha_text", payload=str(payload)[:80])
            if not code:
                log_event("login", "captcha_unreadable_retry")
                continue
            try:
                result = login(client, os.environ.get("MX_ACCOUNT", ""), os.environ.get("MX_PASSWORD", ""), cap["key"], code)
                log_event("login", "login_ok", hosturl=result.get("hosturl") or "")
                return result
            except MXLoginError as exc:
                last_err = str(exc)
                log_event("login", "login_failed", msg=last_err)
        raise MXLoginError(f"连续 {attempts} 次未成功：{last_err or '验证码未识别'}")
    finally:
        client.close()


def discover_business_base(token: str, origin: str, hosturl: str) -> str:
    """登录后确定 business-api 基址：hosturl（新版是路径如 /4）优先，逐个探针。"""
    from app.fetchers.mx.client import MXClient

    origin = origin.rstrip("/")
    candidates: list[str] = []
    if hosturl:
        if hosturl.startswith("http"):
            candidates.append(hosturl.rstrip("/"))
        elif hosturl.startswith("/business-api"):
            candidates.append(origin + hosturl)
        elif hosturl.startswith("/"):
            candidates.append(f"{origin}/business-api{'' if hosturl == '/' else hosturl}")
    candidates.append(f"{origin}/business-api/4")
    candidates.append(f"{origin}/business-api/5")  # 旧版兼容
    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        probe = MXClient(cand, token)
        try:
            probe.user_info()
            log_event("discovery", "business_base_ok", base=cand)
            return cand
        except Exception as exc:  # noqa: BLE001 - 探针失败换下一个
            log_event("discovery", "business_base_fail", base=cand, err=str(exc)[:120])
        finally:
            probe.close()
    raise RuntimeError(f"所有 business-api 候选均不可用：{seen}")


# ---- 变体一：生产同款（python-socketio + aiohttp，原类直跑）----

async def probe_prod(ws_base: str, ws_path: str, namespace: str, token: str,
                     duration: float | None) -> dict:
    from app.fetchers.mx.ws import MxWsClient

    cfg = SimpleNamespace(ws_url=ws_base, ws_path=ws_path, ws_namespace=namespace, token=token)
    stats = {"frames_in": 0}
    client = MxWsClient(cfg, on_message_callback=lambda m: stats.__setitem__("frames_in", stats["frames_in"] + 1))
    t0 = time.monotonic()
    result: dict = {"connected": False, "ns_ok": False, "uptime": None, "end": "", "err": ""}
    try:
        await asyncio.wait_for(client.connect(), timeout=30)
        result["connected"] = True
        result["ns_ok"] = True  # python-socketio connect() 返回即 ns 握手成功
        log_event("prod", "ws_open", latency_ms=round((time.monotonic() - t0) * 1000))
        await asyncio.wait_for(client._sio.wait(), timeout=duration)
        result["end"] = "disconnected"
    except asyncio.TimeoutError:
        if duration is not None and time.monotonic() - t0 >= duration:
            result["end"] = "duration_reached"
            await client.stop("probe duration 结束")
        else:
            result["end"] = "connect_timeout"
            result["err"] = "connect 阶段超时"
    except Exception as exc:  # noqa: BLE001 - 连接失败/被踢都要记录原始报错
        result["err"] = f"{exc.__class__.__name__}: {exc}"
        result["end"] = "exception"
    result["uptime"] = round(time.monotonic() - t0, 1)
    result["frames_in"] = stats["frames_in"]
    log_event("prod", "ws_end", **result)
    return result


# ---- 手写最小 Engine.IO v4 / Socket.IO v5 客户端（两种 transport 共用协议语义）----

class EioStats:
    def __init__(self):
        self.open_packet: dict = {}
        self.connected_at: float | None = None
        self.ns_connected = False
        self.connect_error = ""
        self.frames_in = 0
        self.frames_out = 0
        self.events = 0
        self.pings = 0
        self.pong_delays_ms: list[float] = []
        self.close_info = "duration_reached"
        self.err = ""

    def summary(self, t_start: float) -> dict:
        ended = getattr(self, "ended_at", None) or time.monotonic()
        return {
            "connected": self.connected_at is not None,
            "ns_ok": self.ns_connected,
            "uptime": round(ended - t_start, 1),
            "end": self.close_info,
            "err": self.err,
            "frames_in": self.frames_in,
            "frames_out": self.frames_out,
            "events": self.events,
            "pings": self.pings,
            "pong_delay_ms_max": round(max(self.pong_delays_ms), 1) if self.pong_delays_ms else None,
        }


def handle_eio_frame(text: str, stats: EioStats, send_text, namespace: str, token: str, variant: str) -> None:
    """单帧协议处理：返回要发什么由 send_text 回调完成（同步语义）。"""
    now = time.monotonic()
    stats.frames_in += 1
    if text.startswith("0{"):
        import json as _json
        stats.open_packet = _json.loads(text[1:])
        stats.connected_at = time.monotonic()
        log_event(variant, "eio_open", sid=stats.open_packet.get("sid"),
                  pingInterval=stats.open_packet.get("pingInterval"),
                  pingTimeout=stats.open_packet.get("pingTimeout"))
        payload = compact_auth(token, namespace)
        send_text(payload)
        stats.frames_out += 1
        log_event(variant, "sio_connect_sent", payload=payload[:120])
    elif text == "2":
        stats.pings += 1
        ping_at = time.monotonic()
        send_text("3")
        stats.frames_out += 1
        stats.pong_delays_ms.append((time.monotonic() - ping_at) * 1000)
    elif text.startswith("40"):
        stats.ns_connected = True
        log_event(variant, "sio_connected", ack=text[:80])
    elif text.startswith("44"):
        stats.connect_error = text[:200]
        stats.close_info = "connect_error"
        log_event(variant, "sio_connect_error", detail=text[:200])
    elif text.startswith("41"):
        stats.close_info = "sio_server_disconnect"
        log_event(variant, "sio_server_disconnect", detail=text[:120])
    elif text.startswith("4"):
        stats.events += 1
        if stats.events <= 3 or stats.events % 50 == 0:
            log_event(variant, "event", seq=stats.events, head=text[:100])
    elif text == "1":
        stats.close_info = "server_close_packet"
        log_event(variant, "eio_server_close")
    else:
        log_event(variant, "unknown_frame", head=text[:80])


# ---- 变体二：curl_cffi impersonate（Chrome TLS 指纹）----

def probe_curlffi(ws_url: str, namespace: str, token: str,
                  duration: float | None) -> dict:
    import threading

    from curl_cffi import CurlWsFlag
    from curl_cffi.requests import Session

    from app.fetchers.mx.ws import IMPERSONATE_TARGET

    stats = EioStats()
    t_start = time.monotonic()
    session = Session(impersonate=IMPERSONATE_TARGET)
    ws = None

    def run() -> None:
        nonlocal ws
        try:
            ws = session.ws_connect(ws_url, headers=chrome_ws_headers(ws_url), default_headers=False)
            log_event("curlffi", "ws_open", latency_ms=round((time.monotonic() - t_start) * 1000))
            while True:
                data, flags = ws.recv()
                if flags & CurlWsFlag.CLOSE:
                    stats.close_info = "ws_close_frame"
                    log_event("curlffi", "ws_close_frame", code=ws.close_code, reason=ws.close_reason)
                    break
                text = data.decode("utf-8", "replace")
                handle_eio_frame(text, stats, lambda s: ws.send(s, CurlWsFlag.TEXT), namespace, token, "curlffi")
                if stats.close_info in ("connect_error", "server_close_packet", "sio_server_disconnect"):
                    break
        except Exception as exc:  # noqa: BLE001 - 断连/握手失败原样记录
            if getattr(stats, "probe_done", False):
                return  # 主线程到期硬掐引发的报错，不是平台行为
            stats.err = f"{exc.__class__.__name__}: {exc}"
            if not stats.close_info or stats.close_info == "duration_reached":
                stats.close_info = "exception"
            log_event("curlffi", "ws_error", err=stats.err[:300])

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    if duration is None:
        while worker.is_alive():
            time.sleep(1)
    else:
        worker.join(duration + 5)
        stats.probe_done = True
        stats.ended_at = time.monotonic()
    try:
        if ws is not None:
            ws.terminate()
    except Exception:  # noqa: BLE001 - 尽力清理
        pass
    session.close()
    result = stats.summary(t_start)
    log_event("curlffi", "ws_end", **result)
    # curl 的 C 层句柄会让 daemon recv 线程吊住进程：诊断工具直接强制退出，
    # 避免僵尸进程继续占着平台 WS 会话污染后续观察（2026-10-12 实踩）
    os._exit(0)
    return result


# ---- 变体三：aiohttp 原生（Python TLS 指纹，协议行为与 curlffi 变体一致）----

async def probe_aiohttp(ws_url: str, namespace: str, token: str,
                        duration: float | None) -> dict:
    import aiohttp

    stats = EioStats()
    t_start = time.monotonic()
    try:
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.ws_connect(
                    ws_url, headers=chrome_ws_headers(ws_url), autoping=True
                ) as ws:
                    log_event("aiohttp", "ws_open", latency_ms=round((time.monotonic() - t_start) * 1000))
                    async def send_text(text: str) -> None:
                        await ws.send_str(text)

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            handle_eio_frame(msg.data, stats, lambda t: asyncio.ensure_future(send_text(t)),
                                             namespace, token, "aiohttp")
                            if stats.close_info in ("connect_error", "server_close_packet", "sio_server_disconnect"):
                                break
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            stats.close_info = "ws_closed"
                            break
                    else:
                        stats.close_info = stats.close_info or "stream_end"
                    if ws.closed:
                        stats.close_info = f"ws_close code={ws.close_code} reason={ws.close_reason!r}"
            except aiohttp.WSServerHandshakeError as exc:
                stats.err = f"handshake {exc.status} {exc.message}"
                stats.close_info = "handshake_rejected"
    except asyncio.TimeoutError:
        if duration is not None and time.monotonic() - t_start >= duration:
            stats.close_info = "duration_reached"
        else:
            stats.close_info = "timeout"
            stats.err = "connect timeout"
    except Exception as exc:  # noqa: BLE001
        stats.err = f"{exc.__class__.__name__}: {exc}"
        stats.close_info = stats.close_info if stats.close_info != "duration_reached" else "exception"
        log_event("aiohttp", "ws_error", err=stats.err[:300])
    result = stats.summary(t_start)
    log_event("aiohttp", "ws_end", **result)
    return result


VARIANTS = ("prod", "curlffi", "aiohttp")


def split_ws_endpoint(ws_url_full: str) -> tuple[str, str]:
    """'wss://h/p/socket.io/?q' -> ('wss://h/p', '/socket.io')；无 /socket.io 段时整段视为 base。"""
    base = ws_url_full.partition("?")[0].rstrip("/")
    if base.endswith("/socket.io"):
        return base[: -len("/socket.io")], "/socket.io"
    return base, "/socket.io"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MX WS 被踢诊断：多客户端人格 A/B")
    parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="平台域名（默认新域名）")
    parser.add_argument("--token", default=None, help="已有 token（跳过登录）")
    parser.add_argument("--hosturl", default=None, help="business-api 路径覆盖（默认自动发现）")
    parser.add_argument("--namespace", default="/msg")
    parser.add_argument("--ws-url", default=None,
                        help="完整 WS 端点覆盖（如 wss://host/msg/socket.io/），跳过自动发现")
    parser.add_argument("--duration", type=float, default=120.0, help="每变体观察秒数（默认 120）")
    parser.add_argument("--repeat", type=int, default=1, help="每变体重复连接次数（默认 1）")
    parser.add_argument("--variants", default="prod,curlffi,aiohttp", help="逗号分隔：prod,curlffi,aiohttp")
    parser.add_argument("--watch", choices=VARIANTS, default=None, help="单变体无限长跑（忽略 --duration/--repeat）")
    parser.add_argument("--login-only", action="store_true", help="只登录并打印 token")
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
    except ImportError:
        pass

    origin = args.origin.rstrip("/")
    token = args.token or os.environ.get("MX_WS_TOKEN", "")
    hosturl = args.hosturl or ""

    if not token:
        log_event("main", "login_start", origin=origin)
        result = do_login(origin)
        token = result["token"]
        hosturl = hosturl or result.get("hosturl", "")
        print(f"TOKEN：{token}")
    if args.login_only:
        return 0

    if args.ws_url:
        ws_full = args.ws_url if "?" in args.ws_url else args.ws_url.rstrip("/") + f"/?{EIO_QUERY}"
        ws_base, ws_path = split_ws_endpoint(ws_full)
        print(f"\nWS 端点（--ws-url 覆盖）：{ws_full}\n")
    else:
        business_base = discover_business_base(token, origin, hosturl)
        parsed = urlparse(business_base)
        ws_base = f"wss://{parsed.netloc}{parsed.path.rstrip('/')}"
        ws_path = "/socket.io"
        ws_full = f"{ws_base}/socket.io/?{EIO_QUERY}"
        print(f"\nWS 端点：{ws_full}\n业务基址：{business_base}\n")

    plan: list[tuple[str, int, float | None]] = []
    if args.watch:
        plan.append((args.watch, 1, None))
    else:
        for name in [v.strip() for v in args.variants.split(",") if v.strip()]:
            if name not in VARIANTS:
                print(f"未知变体：{name}（可选 {VARIANTS}）")
                return 2
            plan.append((name, max(1, args.repeat), args.duration))

    all_results: dict[str, list[dict]] = {}
    for name, repeat, duration in plan:
        for round_no in range(1, repeat + 1):
            log_event("main", "variant_start", name=name, round=round_no, duration=duration)
            if name == "prod":
                res = asyncio.run(probe_prod(ws_base, ws_path, args.namespace, token, duration))
            elif name == "curlffi":
                res = probe_curlffi(ws_full, args.namespace, token, duration)
            else:
                res = asyncio.run(probe_aiohttp(ws_full, args.namespace, token, duration))
            all_results.setdefault(name, []).append(res)
            time.sleep(3)

    print("\n==== 汇总 ====")
    print(f"{'变体':<10} {'连接':<4} {'ns':<4} {'存活(s)':<9} {'结束原因':<26} {'收/发帧':<10} {'ping':<5} {'错误'}")
    for name, results in all_results.items():
        for res in results:
            print(f"{name:<10} {str(res['connected']):<4} {str(res['ns_ok']):<4} "
                  f"{str(res['uptime']):<9} {str(res['end']):<26} "
                  f"{res.get('frames_in', '?')}/{res.get('frames_out', '?'):<5} "
                  f"{res.get('pings', '-'):<5} {res.get('err', '')[:80]}")
    print(f"\n明细已落盘：{JSONL_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
