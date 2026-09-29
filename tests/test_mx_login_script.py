"""scripts/mx_login.py + app.fetchers.mx.login 的契约测试。

核心契约：
- 登录/验证码请求与官方前端逐字段一致（URL、body 字段名、头形态）；
- 密码与验证码答案绝不出现在任何输出/异常文本里；
- 写回 API 模式只发 token（及探针触发的 api_base/ws_url 切换），走与后台
  手粘相同的 PUT 端点。
"""

import base64
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.fetchers.mx.client import MXClient, MXTokenExpiredError  # noqa: E402
from app.fetchers.mx.login import (  # noqa: E402
    MXLoginError,
    classify_captcha,
    fetch_captcha,
    login,
)

_spec = importlib.util.spec_from_file_location("mx_login_script", REPO / "scripts" / "mx_login.py")
mx_login_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mx_login_script)


class _FakeCffiResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeCffiSession:
    """按序返回 payload 的假 curl_cffi Session，记录每次请求供断言。"""

    def __init__(self, payloads):
        self._payloads = payloads
        self.requests = []

    def request(self, method, url, headers=None, data=None, timeout=None):
        self.requests.append(
            {"method": method, "url": url, "headers": headers, "data": data}
        )
        return _FakeCffiResponse(self._payloads[len(self.requests) - 1])


def _client(payloads):
    session = _FakeCffiSession(payloads)
    return MXClient("https://mx.test/business-api/5", "", session=session), session


def _b64_png() -> str:
    raw = b"\x89PNG" + b"0" * 120
    return base64.b64encode(raw).decode()


# ---- 协议形态 ----

def test_fetch_captcha_matches_official_frontend():
    """GET master-api/api/code：query 只带 tt（登录前无 token 参数），
    头不带 Content-Type（官方 GET 无此头），常量头 ad/i/version 在。"""
    client, session = _client([{"code": 200, "captcha": f"data:image/png;base64,{_b64_png()}", "key": "k1"}])
    cap = fetch_captcha(client)

    assert cap["key"] == "k1"
    assert cap["captcha"].startswith("data:image/png;base64,")
    req = session.requests[0]
    assert req["method"] == "GET"
    assert re.fullmatch(r"https://mx\.test/master-api/api/code\?tt=\d+", req["url"])
    assert "token=" not in req["url"]
    headers = req["headers"]
    assert "Content-Type" not in headers
    assert headers["ad"] == "true" and headers["i"] == "qq" and headers["version"] == "web"
    assert headers["token"] == ""


def test_login_body_fields_match_official_frontend():
    """POST master-api/api/login 的 body 字段与官方 fetch 完全一致
    （2026-09-29 bundle 实测：user/password/code_key/code/device/ad/h5/tt）。"""
    client, session = _client([{"code": 200, "token": "tok", "hosturl": "https://alt.test", "info": {"id": 1}}])
    result = login(client, "acct", "secret-pw", "k1", "9x6")

    assert result["token"] == "tok" and result["hosturl"] == "https://alt.test"
    req = session.requests[0]
    assert req["method"] == "POST"
    assert req["url"] == "https://mx.test/master-api/api/login"
    body = json.loads(req["data"])
    assert body["user"] == "acct" and body["password"] == "secret-pw"
    assert body["code_key"] == "k1" and body["code"] == "9x6"
    assert body["device"] == "web-browser" and body["ad"] is True and body["h5"] is True
    assert isinstance(body["tt"], int)
    assert req["headers"]["Content-Type"] == "application/json"


def test_login_failure_message_never_leaks_password():
    client, _ = _client([{"code": 400, "msg": "验证码错误"}])
    with pytest.raises(MXLoginError) as exc_info:
        login(client, "acct", "super-secret-pw", "k1", "0000")
    assert "验证码错误" in str(exc_info.value)
    assert "super-secret-pw" not in str(exc_info.value)
    assert "0000" not in str(exc_info.value)


def test_classify_captcha_variants():
    data_uri = f"data:image/png;base64,{_b64_png()}"
    kind, payload = classify_captcha(data_uri)
    assert kind == "image" and payload.startswith(b"\x89PNG")

    kind, payload = classify_captcha(_b64_png())
    assert kind == "image" and payload.startswith(b"\x89PNG")

    kind, payload = classify_captcha("3+5=?")
    assert kind == "text" and payload == "3+5=?"


def test_classify_captcha_svg_and_extension():
    """平台实测（2026-09-29）下发 SVG 矢量验证码：裸 base64 也要认出，
    扩展名按魔数给（.svg 才能被系统默认程序打开）。"""
    from app.fetchers.mx.login import captcha_image_ext

    svg = b'<svg xmlns="http://www.w3.org/2000/svg">' + b"M8 8 L9 9" * 30
    kind, payload = classify_captcha(base64.b64encode(svg).decode())
    assert kind == "image" and payload.startswith(b"<svg")
    assert captcha_image_ext(payload) == ".svg"
    assert captcha_image_ext(b"\x89PNG" + b"0" * 16) == ".png"
    assert captcha_image_ext(b"\xff\xd8\xff" + b"0" * 16) == ".jpg"


# ---- 验证码重试循环 ----

def test_run_login_flow_retries_with_fresh_captcha():
    payloads = [
        {"code": 200, "captcha": "data:image/png;base64," + _b64_png(), "key": "k1"},
        {"code": 400, "msg": "验证码错误"},
        {"code": 200, "captcha": "data:image/png;base64," + _b64_png(), "key": "k2"},
        {"code": 200, "token": "tok2", "hosturl": "", "info": None},
    ]
    client, session = _client(payloads)
    printed = []
    answers = iter(["bad", "good"])

    result = mx_login_script.run_login_flow(
        client, "acct", "secret-pw", attempts=3,
        prompt=lambda _prompt: next(answers), present=printed.append,
        ocr_fn=None, on_captcha=lambda _png: "fake-path.png",
    )

    assert result["token"] == "tok2"
    # 第二次登录用的是第二张验证码的 key
    login_bodies = [json.loads(r["data"]) for r in session.requests if r["url"].endswith("/api/login")]
    assert [b["code_key"] for b in login_bodies] == ["k1", "k2"]
    assert any("失败：验证码错误" in line for line in printed)
    # 密码不进任何输出
    assert not any("secret-pw" in line for line in printed)


def test_run_login_flow_exhausts_attempts():
    payloads = [
        {"code": 200, "captcha": "data:image/png;base64," + _b64_png(), "key": "k1"},
        {"code": 400, "msg": "验证码错误"},
    ] * 3
    client, _ = _client(payloads)
    with pytest.raises(MXLoginError) as exc_info:
        mx_login_script.run_login_flow(
            client, "acct", "pw", attempts=3,
            prompt=lambda _p: "x", present=lambda *_a: None,
        )
    assert "连续 3 次未成功" in str(exc_info.value)


def test_run_login_flow_fatal_error_breaks_retry():
    """熔断：密码/账号类致命错误立即中止，不烧剩余重试次数
    （换码重试毫无意义，只会积累连续失败登录的风控信号）。"""
    payloads = [
        {"code": 200, "captcha": "data:image/png;base64," + _b64_png(), "key": "k1"},
        {"code": 400, "msg": "账号或密码错误"},
        # 若未熔断会继续消费这两个 payload——断言用
        {"code": 200, "captcha": "data:image/png;base64," + _b64_png(), "key": "k2"},
        {"code": 200, "token": "should-not-reach", "hosturl": "", "info": None},
    ]
    client, session = _client(payloads)
    with pytest.raises(MXLoginError) as exc_info:
        mx_login_script.run_login_flow(
            client, "acct", "pw", attempts=3,
            prompt=lambda _p: "x", present=lambda *_a: None,
        )
    assert "熔断" in str(exc_info.value)
    # 只发生了一轮（1 次拉码 + 1 次登录），重试机会未消耗
    assert len(session.requests) == 2


def test_run_login_flow_text_captcha_prompts_answer():
    payloads = [
        {"code": 200, "captcha": "3+5=?", "key": "k9"},
        {"code": 200, "token": "tok-text", "hosturl": "", "info": None},
    ]
    client, session = _client(payloads)
    result = mx_login_script.run_login_flow(
        client, "acct", "pw", attempts=1,
        prompt=lambda _p: "8", present=lambda *_a: None,
    )
    assert result["token"] == "tok-text"
    body = json.loads(session.requests[1]["data"])
    assert body["code"] == "8" and body["code_key"] == "k9"


# ---- 探针与域名切换 ----

def test_probe_token_accepts_and_rejects():
    ok, _ = _client([{"code": 200, "info": {"id": 1}}])
    assert mx_login_script.probe_token("https://mx.test/business-api/5", "t", ok._session) is True

    expired, _ = _client([{"code": 502, "msg": "token失效"}])
    assert mx_login_script.probe_token("https://mx.test/business-api/5", "t", expired._session) is False


def test_origin_and_ws_url_helpers():
    assert mx_login_script.api_base_of("https://mx.2026.foodtop1.com") == \
        "https://mx.2026.foodtop1.com/business-api/5"
    assert mx_login_script.ws_url_of("https://x.test/business-api/5") == \
        "wss://x.test/business-api/5"
    assert mx_login_script.resolve_origin(None, "https://a.test/business-api/5") == "https://a.test"
    assert mx_login_script.resolve_origin("https://b.test", "https://a.test/business-api/5") == "https://b.test"
    assert mx_login_script.mask("abcdefghijklmnop") == "abcd…mnop"


# ---- 写回 API ----

def _skip_url_gate(monkeypatch):
    """push_via_api 的公网校验走真实 DNS/保留段判断，传输层测试直接放行。"""
    import app.url_safety as url_safety_mod
    monkeypatch.setattr(url_safety_mod, "is_safe_http_url", lambda _url: True)


def test_push_via_api_puts_token_only(monkeypatch):
    import httpx

    _skip_url_gate(monkeypatch)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.path] = request
        if request.url.path == "/api/auth/login":
            assert json.loads(request.content) == {"username": "admin", "password": "vp-pw"}
            return httpx.Response(200, json={"token": "bearer-t", "user": {}})
        assert request.headers["Authorization"] == "Bearer bearer-t"
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    body = mx_login_script.push_via_api(
        "https://vpush.test", "admin", "vp-pw", "new-mx-token", transport=transport,
    )
    assert body == {"token": "new-mx-token"}
    put = seen["/api/admin/sources/mx"]
    assert put.method == "PUT"
    assert json.loads(put.content) == {"token": "new-mx-token"}


def test_push_via_api_includes_switched_base(monkeypatch):
    import httpx

    _skip_url_gate(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"token": "bearer-t"})
        return httpx.Response(200, json={"ok": True})

    body = mx_login_script.push_via_api(
        "https://vpush.test", "admin", "pw", "tok",
        api_base="https://alt.test/business-api/5",
        ws_url="wss://alt.test/business-api/5",
        transport=httpx.MockTransport(handler),
    )
    assert body["api_base"] == "https://alt.test/business-api/5"
    assert body["ws_url"] == "wss://alt.test/business-api/5"


def test_push_via_api_turnstile_hint(monkeypatch):
    import httpx

    _skip_url_gate(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "人机验证失败，请重试"})

    with pytest.raises(MXLoginError) as exc_info:
        mx_login_script.push_via_api(
            "https://vpush.test", "admin", "pw", "tok",
            transport=httpx.MockTransport(handler),
        )
    assert "Turnstile" in str(exc_info.value)


# ---- 无人值守：AI 视觉识码 ----

def test_vision_config_env_precedence(monkeypatch):
    monkeypatch.setenv("MX_VISION_API_BASE", " https://mx.example/v3 ")
    monkeypatch.setenv("MX_VISION_API_KEY", "k1")
    monkeypatch.setenv("MX_VISION_MODEL", "m1")
    monkeypatch.setenv("LLM_API_BASE", "https://llm.example/v1")
    assert mx_login_script._vision_config() == ("https://mx.example/v3", "k1", "m1")

    monkeypatch.delenv("MX_VISION_API_BASE")
    monkeypatch.delenv("MX_VISION_API_KEY")
    monkeypatch.delenv("MX_VISION_MODEL")
    monkeypatch.setenv("LLM_API_KEY", "k2")
    monkeypatch.setenv("LLM_MODEL", "m2")
    assert mx_login_script._vision_config() == ("https://llm.example/v1", "k2", "m2")


def test_ai_read_captcha_parses_and_sanitizes(monkeypatch):
    import app.llm as llm_mod

    calls = {}

    def fake_vision(prompt, png, config, timeout=60):
        calls["config"] = config
        return calls.setdefault("answer", "验证码是 x9K2。")

    monkeypatch.setattr(llm_mod, "vision_read_text", fake_vision)
    monkeypatch.setenv("MX_VISION_API_BASE", "https://v.example/v3")
    monkeypatch.setenv("MX_VISION_API_KEY", "k")
    monkeypatch.setenv("MX_VISION_MODEL", "m")

    assert mx_login_script.ai_read_captcha(b"\x89PNGxx") == "x9K2"
    # 走 app.llm 的 user_supplied 安全体（公网端点校验 + IP 固定在 _chat 内）
    assert calls["config"].user_supplied is True


def test_ai_read_captcha_unconfigured_never_calls(monkeypatch):
    import app.llm as llm_mod

    def boom(*a, **k):
        raise AssertionError("未配置视觉端点不应发起调用")

    monkeypatch.setattr(llm_mod, "vision_read_text", boom)
    monkeypatch.delenv("MX_VISION_API_BASE", raising=False)
    monkeypatch.delenv("MX_VISION_API_KEY", raising=False)
    monkeypatch.delenv("MX_VISION_MODEL", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert mx_login_script.ai_read_captcha(b"\x89PNGxx") is None


def test_ai_ocr_rasterizes_svg_first(monkeypatch):
    seen = {}

    def fake_raster(svg):
        seen["svg"] = svg
        return b"\x89PNG-rendered"

    monkeypatch.setattr(mx_login_script, "rasterize_svg", fake_raster)
    monkeypatch.setattr(mx_login_script, "ai_read_captcha", lambda png: "from-png")
    assert mx_login_script.ai_ocr(b"<svg>paths</svg>") == "from-png"
    assert seen["svg"] == b"<svg>paths</svg>"
    # 位图直接透传
    monkeypatch.setattr(mx_login_script, "ai_read_captcha", lambda png: "ok")
    assert mx_login_script.ai_ocr(b"\x89PNGraw") == "ok"


def test_rasterize_svg_fallback_chain(monkeypatch):
    """resvg-py 可用时直接出 PNG；全部渲染器缺失时返回 None。"""
    from app.fetchers.mx.login import rasterize_svg

    png = rasterize_svg(b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                        b'<rect width="10" height="10" fill="red"/></svg>')
    assert png is not None and png[:4] == b"\x89PNG"

    monkeypatch.setitem(sys.modules, "resvg_py", None)
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    assert rasterize_svg(b"<svg/>") is None


def test_run_login_flow_no_prompt_never_waits_input():
    """无人值守模式：OCR 识别不出只换码重试，绝不等终端输入（Jenkins 无 stdin）。"""
    payloads = [
        {"code": 200, "captcha": "data:image/png;base64," + _b64_png(), "key": f"k{i}"}
        for i in range(3)
    ]
    client, _ = _client(payloads)

    def _boom(_prompt):
        raise AssertionError("无人值守模式不允许等待输入")

    with pytest.raises(MXLoginError) as exc_info:
        mx_login_script.run_login_flow(
            client, "acct", "pw", attempts=3,
            prompt=_boom, present=lambda *_a: None,
            ocr_fn=lambda _png: None, no_prompt=True,
        )
    assert "未成功" in str(exc_info.value)


def test_main_ai_ocr_requires_vision_config(monkeypatch, capsys):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("MX_ACCOUNT", "acct")
    monkeypatch.setenv("MX_PASSWORD", "pw")
    for key in ("MX_VISION_API_BASE", "MX_VISION_API_KEY", "MX_VISION_MODEL",
                "LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    fake = _fake_client_for_main([])
    monkeypatch.setattr(mx_login_script, "MXClient", lambda *a, **k: fake)

    rc = mx_login_script.main(["--ai-ocr"])
    assert rc == 2
    assert "MX_VISION" in capsys.readouterr().out


# ---- 失败告警（安全体：仅公网 webhook） ----

def test_notify_failure_bark_and_private_rejected(monkeypatch):
    import app.url_safety as url_safety_mod

    sent = []

    def fake_safe(client, method, url, **kw):
        sent.append((method, url, kw.get("content")))
        return None

    monkeypatch.setattr(url_safety_mod, "safe_request_limited", fake_safe)

    monkeypatch.setenv("BARK_SERVER", "http://8.8.8.8")
    monkeypatch.setenv("BARK_KEY", "k1")
    mx_login_script.notify_failure("登录连续失败")
    assert len(sent) == 1 and sent[0][0] == "GET"
    assert "/k1/" in sent[0][1] and "8.8.8.8" in sent[0][1]

    # 内网 Bark 地址必须被拒（不发起请求）
    sent.clear()
    monkeypatch.setenv("BARK_SERVER", "http://192.168.1.5")
    mx_login_script.notify_failure("x")
    assert sent == []


def test_notify_failure_feishu_webhook(monkeypatch):
    import app.url_safety as url_safety_mod

    sent = []

    def fake_safe(client, method, url, **kw):
        sent.append((method, url, kw.get("content")))
        return None

    monkeypatch.setattr(url_safety_mod, "safe_request_limited", fake_safe)
    monkeypatch.delenv("BARK_SERVER", raising=False)
    monkeypatch.delenv("BARK_KEY", raising=False)
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "http://1.2.3.4/hook/abc")

    mx_login_script.notify_failure("写回失败")
    assert len(sent) == 1 and sent[0][0] == "POST"
    body = json.loads(sent[0][2])
    assert body["msg_type"] == "text" and "写回失败" in body["content"]["text"]


def test_push_via_api_rejects_non_public_url():
    with pytest.raises(MXLoginError) as exc_info:
        mx_login_script.push_via_api("http://192.168.1.9:8000", "u", "p", "tok")
    assert "公网" in str(exc_info.value)


# ---- CLI 入口 ----

def test_main_missing_credentials_exits(monkeypatch, capsys):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("MX_ACCOUNT", "")
    monkeypatch.setenv("MX_PASSWORD", "")
    rc = mx_login_script.main(["--write", "print"])
    assert rc == 2
    assert "MX_ACCOUNT" in capsys.readouterr().out


def test_main_auto_mode_prints_token_without_push(monkeypatch, capsys):
    """auto 模式在无 VPUSH_URL 时退化为 print：只打印 token，不发管理请求。"""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("MX_ACCOUNT", "acct")
    monkeypatch.setenv("MX_PASSWORD", "pw")
    monkeypatch.delenv("VPUSH_URL", raising=False)
    monkeypatch.delenv("MX_LOGIN_ORIGIN", raising=False)
    monkeypatch.setattr(mx_login_script, "run_login_flow",
                        lambda *a, **k: {"token": "tok-print-123456", "hosturl": "", "info": None})
    monkeypatch.setattr(mx_login_script, "probe_token", lambda *a, **k: True)
    monkeypatch.setattr(mx_login_script, "copy_to_clipboard", lambda _t: False)
    fake_client = type("C", (), {"close": staticmethod(lambda: None), "_session": None})()
    monkeypatch.setattr(mx_login_script, "MXClient", lambda *a, **k: fake_client)

    rc = mx_login_script.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "tok-print-123456" in out


def _fake_client_for_main(payloads):
    session = _FakeCffiSession(payloads)
    return type("C", (), {
        "close": staticmethod(lambda: None),
        "_session": session,
        "_master_base": staticmethod(lambda: "https://mx.test/master-api"),
        "_headers": staticmethod(lambda: {"ad": "true", "i": "qq", "version": "web",
                                          "token": "", "Content-Type": "application/json"}),
    })()


def test_main_show_captcha_no_credentials_needed(monkeypatch, capsys):
    """两段式第一步：无需账密即可出图与 captcha-key。"""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("MX_ACCOUNT", "")
    monkeypatch.setenv("MX_PASSWORD", "")
    fake = _fake_client_for_main([
        {"code": 200, "captcha": f"data:image/png;base64,{_b64_png()}", "key": "kk-1"},
    ])
    monkeypatch.setattr(mx_login_script, "MXClient", lambda *a, **k: fake)
    monkeypatch.setattr(mx_login_script, "_present_captcha", lambda _png: "saved.png")

    rc = mx_login_script.main(["--show-captcha"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "captcha-key: kk-1" in out
    assert "saved.png" in out


def test_main_two_phase_login_with_key_and_code(monkeypatch, capsys):
    """两段式第二步：--captcha-key/--code 直接登录，不重新拉验证码。"""
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("MX_ACCOUNT", "acct")
    monkeypatch.setenv("MX_PASSWORD", "pw")
    monkeypatch.delenv("VPUSH_URL", raising=False)
    fake = _fake_client_for_main([
        {"code": 200, "token": "tok-2phase", "hosturl": "", "info": None},
    ])
    monkeypatch.setattr(mx_login_script, "MXClient", lambda *a, **k: fake)
    monkeypatch.setattr(mx_login_script, "probe_token", lambda *a, **k: True)
    monkeypatch.setattr(mx_login_script, "copy_to_clipboard", lambda _t: False)

    rc = mx_login_script.main(["--captcha-key", "kk-1", "--code", "9x6", "--write", "print"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "tok-2phase" in out
    body = json.loads(fake._session.requests[0]["data"])
    assert body["code_key"] == "kk-1" and body["code"] == "9x6"
