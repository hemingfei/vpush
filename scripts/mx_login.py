#!/usr/bin/env python3
"""MX 平台半自动换 TOKEN：拉验证码 → 人工/OCR 输码 → 登录 → 写回 vpush。

用法（仓库根目录）：
    python scripts/mx_login.py                 # 默认 --write auto，交互输验证码
    python scripts/mx_login.py --ocr           # ddddocr 自动识别验证码（需 pip install ddddocr）
    python scripts/mx_login.py --write print   # 只打印/复制 token，手动粘后台
    # 两段式（外部识码 / 无交互终端）：
    python scripts/mx_login.py --show-captcha                    # 出验证码图 + captcha-key
    python scripts/mx_login.py --captcha-key <key> --code <答案>  # 用该答案直接登录

凭据只从环境变量 / 根目录 .env 读取，源码、日志、文档不落任何凭据：
    MX_ACCOUNT / MX_PASSWORD          MX 平台账号密码（必填）
    MX_LOGIN_ORIGIN                   登录域名覆盖（默认取当前配置 api_base 的域名，
                                      平台换域名重定向时用它指定，如 https://mx.2026.foodtop1.com）
    VPUSH_URL / VPUSH_ADMIN_USER / VPUSH_ADMIN_PASSWORD
                                      --write api 模式写回 vpush 生产实例所需
                                      （POST /api/auth/login + PUT /api/admin/sources/mx，
                                      与后台手粘同一条热应用链路）。VPUSH_URL 未配置时
                                      auto 模式退化为 print。

防风控口径：请求走 app.fetchers.mx 的同一 impersonate 人格与 XHR 头形态；
保持 2 天一次的人工低频轮换，不做无人值守自动定时登录（连续失败登录
本身就是风控信号）。详见 docs/mx-token-更换脚本.md。
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote
import base64

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.fetchers.mx.client import MXClient  # noqa: E402
from app.fetchers.mx.login import (  # noqa: E402
    MXLoginError,
    classify_captcha,
    fetch_captcha,
    login,
    rasterize_svg,
)

DEFAULT_API_BASE = "https://mx.2026.naaifu.cn/business-api/5"

# 登录失败 msg 里的「致命」特征：换验证码重试毫无意义，只会积累连续失败
# 登录的风控信号——命中即熔断本轮，剩余次数不烧，等人工处置
_FATAL_LOGIN_MSG_MARKERS = ("密码", "账号", "锁定", "冻结", "封禁", "禁止", "不存在")


def mask(token: str) -> str:
    return f"{token[:4]}…{token[-4:]}" if len(token) > 12 else "***"


def resolve_origin(origin_arg: str | None, config_api_base: str) -> str:
    """登录域名：--origin > MX_LOGIN_ORIGIN > 当前配置 api_base 的域名。"""
    origin = origin_arg or os.environ.get("MX_LOGIN_ORIGIN") or ""
    if origin:
        return origin.rstrip("/")
    parsed = config_api_base.split("/business-api")[0]
    return parsed.rstrip("/")


def api_base_of(origin: str) -> str:
    return f"{origin.rstrip('/')}/business-api/5"


def ws_url_of(api_base: str) -> str:
    scheme = "wss" if api_base.startswith("https://") else "ws"
    return f"{scheme}://{api_base.split('://', 1)[1]}".rstrip("/")


def probe_token(api_base: str, token: str, session) -> bool:
    """新 token 在指定 api_base 上是否可用（官方冷启动的 user/info 只读探针）。"""
    client = MXClient(api_base, token, session=session)
    try:
        info = client.user_info()
    except Exception:  # noqa: BLE001 - 探针失败一律视为不可用，不阻断主流程
        return False
    if isinstance(info, dict) and info.get("code") not in (None, 200):
        return False
    return True


def ocr_image(image_bytes: bytes) -> str | None:
    """可选 ddddocr 识别；未安装/识别失败返回 None（回落人工输入）。"""
    try:
        import ddddocr
    except ImportError:
        return None
    try:
        try:
            engine = ddddocr.DdddOcr(show_ad=False)
        except TypeError:  # 旧版本无 show_ad 参数
            engine = ddddocr.DdddOcr()
        return engine.classification(image_bytes)
    except Exception:  # noqa: BLE001 - OCR 只是尽力，失败不阻断
        return None


# ---- AI 视觉识码（无人值守） ----

def _vision_config() -> tuple[str, str, str]:
    """视觉模型配置：MX_VISION_* 优先，回落 LLM_*（模型必须具备视觉能力）。"""
    env = os.environ
    return (
        (env.get("MX_VISION_API_BASE") or env.get("LLM_API_BASE") or "").strip().rstrip("/"),
        env.get("MX_VISION_API_KEY") or env.get("LLM_API_KEY") or "",
        env.get("MX_VISION_MODEL") or env.get("LLM_MODEL") or "",
    )


def vision_configured() -> bool:
    return all(_vision_config())


def ai_read_captcha(png_bytes: bytes) -> str | None:
    """视觉模型读验证码：复用 app.llm.vision_read_text——user_supplied 安全体
    （公网端点校验 + IP 固定 + 响应体受限），失败/答案不合形状返回 None。"""
    from types import SimpleNamespace

    from app.llm import vision_read_text

    base, key, model = _vision_config()
    if not (base and key and model):
        return None
    config = SimpleNamespace(api_key=key, api_base=base, model=model,
                             user_supplied=True, api_format="chat")
    text = vision_read_text(
        "这是一张验证码图片。只输出图中的验证码字符，不要任何解释、标点或其他内容。",
        png_bytes, config,
    )
    if not text:
        return None
    match = re.search(r"[A-Za-z0-9]{3,8}", text)
    return match.group(0) if match else None


def ai_ocr(image_bytes: bytes) -> str | None:
    """无人值守识码入口：SVG 先栅格化再交视觉模型。"""
    if image_bytes.lstrip()[:4] == b"<svg":
        png = rasterize_svg(image_bytes)
        if png is None:
            return None
        image_bytes = png
    return ai_read_captcha(image_bytes)


def notify_vpush(title: str, text: str) -> None:
    """把换 token 结果回调到 vpush 的 KOL webhook（签名协议与飞书同款：
    sign = base64(hmac_sha256(key="{ts}\\n{secret}))，timestamp+sign 放 body）。

    端点与密钥来自 MX_NOTIFY_WEBHOOK_URL / MX_NOTIFY_WEBHOOK_SECRET（Jenkins
    凭据注入）；URL 走 app.url_safety 安全体（仅公网、IP 固定、不跟随重定向）。
    未配置或失败一律静默——构建结果另有 Jenkins 标红兜底。
    """
    url = (os.environ.get("MX_NOTIFY_WEBHOOK_URL") or "").strip()
    secret = (os.environ.get("MX_NOTIFY_WEBHOOK_SECRET") or "").strip()
    if not url:
        return
    try:
        import httpx

        from app.url_safety import is_safe_http_url, safe_request_limited

        if not is_safe_http_url(url):
            return
        ts = int(time.time())
        sign = base64.b64encode(
            hmac.new(f"{ts}\n{secret}".encode(), digestmod=hashlib.sha256).digest()
        ).decode()
        body = json.dumps({"title": title, "text": text, "timestamp": ts, "sign": sign},
                           ensure_ascii=False).encode()
        with httpx.Client() as client:
            safe_request_limited(client, "POST", url, max_bytes=65536,
                                 headers={"Content-Type": "application/json"},
                                 content=body, timeout=15.0, follow_redirects=False)
    except Exception:  # noqa: BLE001 - 回调尽力而为
        pass


def notify_failure(summary: str) -> None:
    """换 token 失败时尽力通知：优先 vpush KOL webhook（MX_NOTIFY_*），
    未配置时回落 Bark / 飞书 webhook（配置自环境变量/.env）。

    webhook 地址走 app.url_safety 安全体：仅公网 http(s)、拒绝内网/环回、
    IP 固定、不跟随重定向；任何失败静默——退出码非 0 已能让 Jenkins 标红。
    """
    if (os.environ.get("MX_NOTIFY_WEBHOOK_URL") or "").strip():
        notify_vpush("MX 换 token 失败",
                     f"{summary}——请人工执行 python scripts/mx_login.py 兜底")
        return
    try:
        import httpx

        from app.url_safety import is_safe_http_url, safe_request_limited

        bark_server = (os.environ.get("BARK_SERVER") or "").rstrip("/")
        bark_key = os.environ.get("BARK_KEY") or ""
        feishu = (os.environ.get("FEISHU_WEBHOOK_URL") or "").strip()
        if bark_server and bark_key:
            url = f"{bark_server}/{bark_key}/{quote('MX换token失败')}/{quote(summary)}"
            method, headers, content = "GET", None, None
        elif feishu:
            url = feishu
            method = "POST"
            headers = {"Content-Type": "application/json"}
            content = json.dumps({
                "msg_type": "text",
                "content": {"text": f"【MX 换 token 失败】{summary}"
                                     "——请人工执行 python scripts/mx_login.py"},
            }).encode()
        else:
            return
        if not is_safe_http_url(url):
            return
        with httpx.Client() as client:
            safe_request_limited(client, method, url, max_bytes=65536,
                                 headers=headers, content=content,
                                 timeout=10.0, follow_redirects=False)
    except Exception:  # noqa: BLE001 - 告警尽力而为
        pass


def run_login_flow(client, account: str, password: str, *, attempts: int = 3,
                   prompt=input, present=print, ocr_fn=None, on_captcha=None,
                   no_prompt: bool = False) -> dict:
    """验证码重试循环。on_captcha(image_bytes) 负责展示图片并返回描述（如保存路径）。

    任一次登录失败都换一张验证码重来（与官方网页行为一致），密码不进任何输出。
    no_prompt=True 为无人值守模式（Jenkins/定时任务）：OCR 识别不出时直接换一张
    重试，绝不等待终端输入。
    """
    last_err = ""
    for _ in range(max(1, attempts)):
        cap = fetch_captcha(client)
        kind, payload = classify_captcha(cap["captcha"])
        if kind == "image":
            display = on_captcha(payload) if on_captcha else "（未展示）"
            present(f"验证码图片：{display}")
            guess = ocr_fn(payload) if ocr_fn else None
            if guess:
                present(f"OCR 识别：{guess}")
                code = guess.strip()
            elif no_prompt:
                present("未能识别验证码，换一张重试")
                code = ""
            else:
                code = prompt("请输入验证码（直接回车换一张）> ").strip()
        elif no_prompt:
            present(f"收到文本验证码（无人值守模式无法作答）：{payload}")
            code = ""
        else:
            present(f"验证码题面：{payload}")
            code = prompt("请输入答案（直接回车换一张）> ").strip()
        if not code:
            continue
        try:
            return login(client, account, password, cap["key"], code)
        except MXLoginError as exc:
            last_err = str(exc)
            if any(marker in last_err for marker in _FATAL_LOGIN_MSG_MARKERS):
                raise MXLoginError(
                    f"{last_err}（致命错误，熔断本轮重试——请人工检查账号状态后重跑）"
                ) from None
            present(f"失败：{last_err}，换一张验证码重试")
    raise MXLoginError(f"连续 {attempts} 次未成功：{last_err or '未识别出验证码'}")


# ---- token 写回 ----

def _push_detail(exc_response) -> str:
    try:
        detail = exc_response.json().get("detail") or exc_response.text[:200]
    except Exception:  # noqa: BLE001
        detail = exc_response.text[:200]
    return str(detail)


def push_via_api(base_url: str, admin_user: str, admin_password: str,
                 new_token: str, api_base: str | None = None,
                 ws_url: str | None = None, transport=None,
                 hot_apply: bool = True) -> dict:
    """登录 vpush 管理 API 并 PUT 新 token。默认与后台手粘完全同一条热应用链路；
    hot_apply=False 时 body 带 hot_apply=false 只保存不热应用——由调用方重启
    容器冷启动生效（Jenkins 无人值守回填口径）。
    VPUSH_URL 须为公网 http(s) 地址（安全体拒绝内网/环回）；transport 供测试注入。"""
    from app.url_safety import is_safe_http_url

    if not is_safe_http_url(base_url.rstrip("/")):
        raise MXLoginError(f"VPUSH_URL 不是安全的公网地址：{base_url}")
    import httpx

    client_kwargs = {"base_url": base_url.rstrip("/"), "timeout": 30.0}
    if transport is not None:
        client_kwargs["transport"] = transport
    with httpx.Client(**client_kwargs) as http:
        resp = http.post("/api/auth/login",
                         json={"username": admin_user, "password": admin_password})
        if resp.status_code == 403 and "人机验证" in resp.text:
            raise MXLoginError(
                "vpush 已开启 Turnstile 人机验证，API 登录不可用；"
                "请改用 --write print 取 token 后到后台手粘"
            )
        if resp.status_code != 200:
            raise MXLoginError(f"vpush 管理登录失败：{_push_detail(resp)}")
        headers = {"Authorization": f"Bearer {resp.json()['token']}"}

        body = {"token": new_token}
        if api_base and ws_url:
            body["api_base"] = api_base
            body["ws_url"] = ws_url
        if not hot_apply:
            body["hot_apply"] = False
        resp = http.put("/api/admin/sources/mx", headers=headers, json=body)
        if resp.status_code != 200:
            raise MXLoginError(f"写入 MX 配置失败：{_push_detail(resp)}")
    return body


def write_local_config(new_token: str, api_base: str | None = None,
                       ws_url: str | None = None) -> str:
    """直写本机 config.yaml + DB（同机部署且不方便走 API 时用）。

    注意：不经服务进程，运行中的服务不会热应用——需重启，或到后台点「登录」。
    """
    from app.config import load_config, save_config
    from app.db import Database

    config = load_config()
    config.sources.mx.token = new_token
    if api_base and ws_url:
        config.sources.mx.api_base = api_base
        config.sources.mx.ws_url = ws_url
    save_config(config)
    Database(config.db_path).set_setting("mx_token_updated_at", str(int(time.time())))
    return os.environ.get("CONFIG_PATH") or "config.yaml"


def copy_to_clipboard(text: str) -> bool:
    """Windows clip 最佳努力复制（token 通常为 ASCII）。"""
    if os.name != "nt":
        return False
    try:
        import subprocess
        subprocess.run(["clip"], input=text.encode("ascii", "ignore"), check=True,
                       capture_output=True)
        return True
    except Exception:  # noqa: BLE001 - 复制失败不影响主流程
        return False


def _present_captcha(image_bytes: bytes) -> str:
    import tempfile
    from app.fetchers.mx.login import captcha_image_ext
    path = Path(tempfile.gettempdir()) / f"mx_captcha{captcha_image_ext(image_bytes)}"
    path.write_bytes(image_bytes)
    try:
        os.startfile(path)  # noqa: S606 - Windows 默认看图器
        hint = "（已用看图器打开）"
    except (AttributeError, OSError):
        hint = "（请手动打开）"
    return f"{path} {hint}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MX 平台半自动换 TOKEN")
    parser.add_argument("--write", choices=["auto", "api", "config", "print"], default="auto",
                        help="写回方式：auto=有 VPUSH_URL 走 api 否则 print")
    parser.add_argument("--origin", default=None, help="登录域名覆盖（平台换域名时用）")
    parser.add_argument("--ocr", action="store_true",
                        help="ddddocr 自动识别验证码（平台 SVG 码暂无效，需栅格化）")
    parser.add_argument("--ai-ocr", action="store_true",
                        help="无人值守：视觉模型自动识别验证码"
                             "（需 MX_VISION_* 或 LLM_* 指向具备视觉能力的模型）")
    parser.add_argument("--attempts", type=int, default=3, help="验证码重试次数（默认 3）")
    parser.add_argument("--no-hot-apply", action="store_true",
                        help="写回只保存不热应用（Jenkins 无人值守用：写回后由流水线"
                             "重启 vpush 容器冷启动生效，避免写回链路立刻登录）")
    parser.add_argument("--show-captcha", action="store_true",
                        help="只拉一张验证码并出图/题面与 captcha-key（配合两段式），无需账密")
    parser.add_argument("--captcha-key", default=None,
                        help="两段式：--show-captcha 输出的 captcha-key（跳过拉码直接登录）")
    parser.add_argument("--code", default=None, help="两段式：该验证码的答案")
    args = parser.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass

    from app.config import load_config

    config = load_config()
    current_api_base = (getattr(config.sources.mx, "api_base", "") or DEFAULT_API_BASE).rstrip("/")
    origin = resolve_origin(args.origin, current_api_base)
    print(f"登录域名：{origin}（当前配置 api_base：{current_api_base}）")

    client = MXClient(api_base_of(origin), "")

    if args.show_captcha:
        cap = fetch_captcha(client)
        kind, payload = classify_captcha(cap["captcha"])
        if kind == "image":
            print(f"验证码图片：{_present_captcha(payload)}")
        else:
            print(f"验证码题面：{payload}")
        print(f"captcha-key: {cap['key']}")
        print("下一步：python scripts/mx_login.py --captcha-key <key> --code <答案>")
        client.close()
        return 0

    account = os.environ.get("MX_ACCOUNT", "").strip()
    password = os.environ.get("MX_PASSWORD", "")
    if not account or not password:
        print("缺少 MX_ACCOUNT / MX_PASSWORD（写入根目录 .env，参考 .env.example）")
        notify_failure("缺少 MX_ACCOUNT / MX_PASSWORD 凭据（Jenkins 凭据或 .env 未配置）")
        client.close()
        return 2

    if args.ai_ocr and not vision_configured():
        print("✗ --ai-ocr 需要 MX_VISION_API_BASE/KEY/MODEL（或 LLM_* 三键齐全，"
              "模型须具备视觉能力）")
        client.close()
        return 2

    if args.captcha_key and args.code:
        # 两段式：验证码答案对应 --show-captcha 拉到的那张图，失败不自动重试
        # （该 key 已作废，需换一张）。
        try:
            result = login(client, account, password, args.captcha_key, args.code)
        except MXLoginError as exc:
            print(f"✗ {exc}（请重跑 --show-captcha 换一张验证码）")
            client.close()
            return 1
    else:
        try:
            result = run_login_flow(
                client, account, password,
                attempts=args.attempts,
                present=print,
                ocr_fn=(ai_ocr if args.ai_ocr else (ocr_image if args.ocr else None)),
                on_captcha=(None if args.ai_ocr else _present_captcha),
                no_prompt=args.ai_ocr,
            )
        except MXLoginError as exc:
            print(f"✗ {exc}")
            notify_failure(str(exc))
            client.close()
            return 1

    new_token = result["token"]
    print(f"✓ 登录成功，新 TOKEN：{mask(new_token)}（hosturl：{result['hosturl'] or '未下发'}）")

    # 探针：新 token 在当前 api_base 不行时，按 hosturl/登录域名切换（官方登录后
    # 也会按 hosturl 切业务域）。切换信息会随写回一并下发。探针复用登录会话，
    # 全部结束后再统一关闭。
    switch_base = None
    if not probe_token(current_api_base, new_token, client._session):
        candidates = []
        if result["hosturl"]:
            candidates.append(result["hosturl"].rstrip("/"))
        candidates.append(origin)
        for cand in candidates:
            cand_base = cand if "/business-api" in cand else api_base_of(cand)
            if probe_token(cand_base, new_token, client._session):
                switch_base = cand_base
                break
        if switch_base:
            print(f"！当前 api_base 不可用，切换为 {switch_base}")
        else:
            print("⚠ 探针全部失败：token 仍会写回，但可能需要检查 api_base 域名")
    client.close()

    mode = args.write
    if mode == "auto":
        mode = "api" if os.environ.get("VPUSH_URL") else "print"
    try:
        if mode == "api":
            body = push_via_api(
                os.environ["VPUSH_URL"],
                os.environ["VPUSH_ADMIN_USER"],
                os.environ["VPUSH_ADMIN_PASSWORD"],
                new_token,
                api_base=switch_base,
                ws_url=(ws_url_of(switch_base) if switch_base else None),
                hot_apply=not args.no_hot_apply,
            )
            print(f"✓ 已通过管理 API 写回（键：{sorted(body)}），"
                  + ("服务已热应用" if not args.no_hot_apply
                     else "未热应用，待容器重启生效"))
            notify_vpush(
                "MX TOKEN 已更换",
                f"新 TOKEN {mask(new_token)} 已写回生产"
                + ("并热应用" if not args.no_hot_apply
                   else "（未热应用，容器重启后冷启动生效）")
                + (f"，api_base 切换为 {switch_base}" if switch_base else "")
                + f"（hosturl：{result['hosturl'] or '未下发'}）",
            )
        elif mode == "config":
            path = write_local_config(new_token, switch_base,
                                      ws_url_of(switch_base) if switch_base else None)
            print(f"✓ 已直写 {path}；运行中的服务不热应用——重启或在后台点「登录」")
            notify_vpush(
                "MX TOKEN 已更换",
                f"新 TOKEN {mask(new_token)} 已直写 {path}"
                + (f"，api_base 切换为 {switch_base}" if switch_base else "")
                + "；需重启或后台点「登录」热应用",
            )
        else:
            print(f"\nTOKEN（已复制到剪贴板可直接粘贴）：\n{new_token}\n")
            copy_to_clipboard(new_token)
    except KeyError as exc:
        print(f"缺少环境变量 {exc}（--write api 需要 VPUSH_URL / VPUSH_ADMIN_USER / VPUSH_ADMIN_PASSWORD）")
        return 2
    except MXLoginError as exc:
        print(f"✗ {exc}")
        notify_failure(f"写回失败：{exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
