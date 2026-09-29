"""MX 平台账号登录换 TOKEN 的核心流程（scripts/mx_login.py 使用）。

官方前端行为（2026-09-29 前端 bundle 实测，docs/mx-token-更换脚本.md）：
- GET  {origin}/master-api/api/code?tt=<ms>：图形验证码。响应 data 为密文，
  解密后 {code, captcha, key}；captcha 官方直接塞进 <img src>，为
  data:image base64（兼容纯 base64 与文本题面）。
- POST {origin}/master-api/api/login：body 明文
  {user, password, code_key, code, device:"web-browser", ad:true, h5:true, tt}，
  响应 data 解密后 {code, token, info, hosturl}；code===200 且有 token 即成功，
  hosturl 为平台动态下发的业务接口域（官方登录后会切换）。

防风控口径与 client.py 一致：复用同一 impersonate 人格与 XHR 头形态；
登录前请求 token 头为空串（与官方 fetch 一致）。密码只经内存传递，
任何异常/日志不得带出密码。
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import time
from typing import Any

from .client import MXClient
from .client import MXTokenExpiredError  # noqa: F401 - re-export 供调用方统一捕获
from .crypto import decrypt_api_data

# 官方登录请求体常量（前端写死，2026-09-29 bundle 实测）
LOGIN_DEVICE = "web-browser"

_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


class MXLoginError(RuntimeError):
    """登录流程失败（验证码错/账密错/WAF 拦截等）。message 只含平台返回的
    msg 或流程描述，绝不拼接请求体（防密码泄漏）。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.msg = message


def _decode_envelope(payload: Any) -> Any:
    """官方响应信封解码：data 为密文字符串时解密替换整包（与 client._request 同口径）。"""
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, str) and data:
            decrypted = decrypt_api_data(data)
            if decrypted is not None:
                return decrypted
    return payload


def _request_json(client: MXClient, method: str, url: str, body: dict | None = None) -> Any:
    """走 client 的同款会话/头发请求；GET 不带 Content-Type（对齐官方 fetch）。"""
    headers = dict(client._headers())
    if method == "GET":
        headers.pop("Content-Type", None)
    data = json.dumps(body) if body is not None else None
    response = client._session.request(
        method, url, headers=headers, data=data, timeout=30.0
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - WAF 拦截页等非 JSON 响应
        raise MXLoginError("登录接口响应非 JSON（疑似被 WAF 拦截）") from exc
    return _decode_envelope(payload)


def fetch_captcha(client: MXClient) -> dict:
    """拉取图形验证码：GET /master-api/api/code?tt=<ms>（官方登录前请求，
    token 头为空、query 只带 tt 不带 token——与官方 fetch 一致）。

    Returns:
        {"captcha": str, "key": str}
    """
    url = f"{client._master_base()}/api/code?tt={int(time.time() * 1000)}"
    result = _request_json(client, "GET", url)
    # 官方前端不校验 code、只取 captcha/key；这里仅拒绝明确的非 200 与缺 key
    if not isinstance(result, dict) or result.get("code") not in (None, 200) or not result.get("key"):
        msg = result.get("msg") if isinstance(result, dict) else None
        raise MXLoginError(f"获取验证码失败：{msg or '响应异常'}")
    return {"captcha": str(result.get("captcha") or ""), "key": str(result["key"])}


def classify_captcha(captcha: str) -> tuple[str, Any]:
    """区分图片验证码与文本题面。

    官方前端把 captcha 直接塞 <img src>；data:image 前缀或可解出图片魔数的
    base64 视为图片（返回 ("image", bytes)），否则按文本题面返回 ("text", str)。
    平台实测（2026-09-29）下发的是 SVG 矢量验证码（路径绘制，防 OCR），
    浏览器可直接显示，栅格化需另用渲染器。
    """
    if captcha.startswith("data:image"):
        payload = captcha.split(",", 1)[1] if "," in captcha else ""
        try:
            return "image", base64.b64decode(payload)
        except (binascii.Error, ValueError):
            raise MXLoginError("验证码 data:image 载荷不是合法 base64") from None
    if len(captcha) > 64 and _BASE64_RE.match(captcha):
        try:
            raw = base64.b64decode(captcha + "=" * (-len(captcha) % 4))
        except (binascii.Error, ValueError):
            raw = b""
        if raw[:4] in (b"\x89PNG", b"GIF8") or raw.startswith(b"\xff\xd8\xff"):
            return "image", raw
        if raw.lstrip()[:4] == b"<svg":
            return "image", raw
    return "text", captcha


def captcha_image_ext(image_bytes: bytes) -> str:
    """按魔数给验证码图片定扩展名（SVG 存成 .svg 才能被系统默认程序打开）。"""
    head = image_bytes.lstrip()[:4]
    if head == b"\x89PNG":
        return ".png"
    if head.startswith(b"\xff\xd8"):
        return ".jpg"
    if head == b"GIF8":
        return ".gif"
    if head == b"<svg":
        return ".svg"
    return ".png"


def rasterize_svg(svg: bytes | str) -> bytes | None:
    """SVG 验证码栅格化为 PNG（AI 识图/ddddocr 都需要位图）。

    首选 resvg-py（纯 wheel、无系统依赖，容器友好）；缺装时回落 Playwright
    Chromium 截图（开发机/CI 已有）。两者都不可用返回 None。
    """
    text = svg.decode("utf-8", "ignore") if isinstance(svg, bytes) else svg
    try:
        import resvg_py
        png = resvg_py.svg_to_bytes(text)
        if png and png[:4] == b"\x89PNG":
            return png
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - 栅格化失败走回落链
        pass
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 300, "height": 80},
                                        device_scale_factor=3)
                page.set_content(f'<body style="margin:0">{text}</body>')
                return page.screenshot(type="png", full_page=True)
            finally:
                browser.close()
    except Exception:  # noqa: BLE001 - 回落也失败只能放弃
        return None
    return None


def login(client: MXClient, account: str, password: str, captcha_key: str, code: str) -> dict:
    """账号登录换 TOKEN：POST /master-api/api/login，body 字段名与官方前端一致。

    Returns:
        {"token": str, "hosturl": str, "info": Any}
    Raises:
        MXLoginError: 平台返回非 200/无 token（验证码错、账密错等）
    """
    body = {
        "user": account,
        "password": password,
        "code_key": captcha_key,
        "code": code,
        "device": LOGIN_DEVICE,
        "ad": True,
        "h5": True,
        "tt": int(time.time() * 1000),
    }
    url = f"{client._master_base()}/api/login"
    result = _request_json(client, "POST", url, body)
    token = result.get("token") if isinstance(result, dict) else None
    if not isinstance(result, dict) or result.get("code") != 200 or not token:
        msg = result.get("msg") or result.get("message") if isinstance(result, dict) else None
        raise MXLoginError(f"登录失败：{msg or '响应异常'}")
    return {
        "token": str(token),
        "hosturl": str(result.get("hosturl") or ""),
        "info": result.get("info"),
    }
