"""mitmproxy addon: 只记录 ima 文件通道，不把 token/正文写进日志。"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from mitmproxy import http

OUT = Path(__file__).resolve().parents[1] / "data" / "ima_win_capture.jsonl"
INTEREST = (
    "/cgi-bin/file_manager/get_media",
    "/cgi-bin/media_logic/parse_media",
    "/cgi-bin/s/",
    "/cgi-bin/knowledge_tab_reader",
    "/openapi/wiki/",
)


def _interesting(url: str) -> bool:
    host = urlparse(url).netloc
    if "ima.qq.com" not in host and "myqcloud.com" not in host:
        return False
    if "myqcloud.com" in host:
        return True
    return any(p in urlparse(url).path for p in INTEREST)


def _cookie_keys(header: str) -> list[str]:
    keys = []
    for part in header.split(";"):
        part = part.strip()
        if "=" in part:
            keys.append(part.split("=", 1)[0])
    return keys


def response(flow: http.HTTPFlow) -> None:
    url = flow.request.pretty_url
    if not _interesting(url):
        return
    path = urlparse(url).path
    req_ctk = flow.request.headers.get("x-ima-ctk") or flow.request.headers.get("x-ima-cm")
    resp_ctk = flow.response.headers.get("x-ima-ctk") if flow.response else None
    trpc = flow.response.headers.get("Trpc-Func-Ret") if flow.response else None
    action = toast = code = None
    body_len = 0
    ctype = ""
    if flow.response:
        body_len = len(flow.response.content or b"")
        ctype = (flow.response.headers.get("content-type") or "").split(";")[0]
        if "json" in ctype:
            try:
                data = json.loads(flow.response.get_text())
            except Exception:
                data = None
            if isinstance(data, dict):
                code = data.get("code", data.get("retcode"))
                action = data.get("action")
                toast = data.get("toast_text")
    row = {
        "method": flow.request.method,
        "path": path,
        "host": urlparse(url).netloc,
        "http": flow.response.status_code if flow.response else None,
        "code": code,
        "action": action,
        "toast": toast,
        "ctype": ctype,
        "body_len": body_len,
        "ua_has_windows": "Windows" in (flow.request.headers.get("user-agent") or ""),
        "client_cookie_keys": _cookie_keys(flow.request.headers.get("x-ima-cookie") or ""),
        "has_ctk_req": bool(req_ctk),
        "has_ctk_resp": bool(resp_ctk),
        "trpc": trpc,
        "from_browser_ima": flow.request.headers.get("from_browser_ima"),
        "extension_version": flow.request.headers.get("extension_version"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        f"IMA {row['method']} {row['path']} http={row['http']} "
        f"code={row['code']} action={row['action']} toast={row['toast']!r} "
        f"len={row['body_len']} ctk={row['has_ctk_req']}/{row['has_ctk_resp']} trpc={row['trpc']}"
    )
