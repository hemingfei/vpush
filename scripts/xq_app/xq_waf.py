#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雪球 WAF 挑战解算器（复用 vpush waf-bot 的 solver.js）

原理：雪球对 /statuses/* 等路径下发阿里云 WAF 挑战页（renderData + 外链 JS），
      解算脚本会在 jsdom 中执行该挑战，产出带 md5__1038 签名的 URL；
      请求该签名 URL 即放行（返回业务 JSON 而非挑战 HTML）。

实测特性（2026-09-22）：
  · 签名与 URL 绑定        —— 换个路径必须重新解算
  · 签名可重复使用        —— 同一签名反复请求均放行
  · 签名不绑 session/cookie —— 新会话携签名同样放行
  · 过了 WAF 仍是业务鉴权 —— 未登录返回 error_code 400016

用法：
    from xq_waf import XueqiuWaf
    xq = XueqiuWaf(cookies={"xq_a_token": "...", "u": "..."})
    r = xq.fetch("https://xueqiu.com/statuses/hot/listV2.json?since_id=-1&max_id=-1&size=20")
    print(r.status_code, r.text[:200])
"""
from __future__ import annotations

import json
import subprocess
import urllib.parse
from pathlib import Path

try:
    from curl_cffi import requests
except ImportError:  # 退化为标准库
    import requests  # type: ignore

WAF_BOT = Path.home() / "Documents/微信小程序大 v 订阅/dav-subscription/waf-bot"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

NAV_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}
XHR_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "X-Requested-With": "XMLHttpRequest",
}


class WafChallengeError(RuntimeError):
    """解算失败。"""


def is_challenge(text: str) -> bool:
    return "renderData" in text and ("aliyun_waf" in text or "_waf_" in text)


def solve_challenge(html: str, url: str, timeout: int = 25) -> str:
    """在 jsdom 里执行挑战脚本，返回带 md5__1038 的签名 URL。"""
    proc = subprocess.run(
        ["node", "--permission",
         "--allow-fs-read=./solver.js",
         "--allow-fs-read=./node_modules",
         "./solver.js"],
        cwd=str(WAF_BOT),
        input=json.dumps({"html": html, "url": url, "user_agent": UA}),
        text=True, capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise WafChallengeError(f"solver exit={proc.returncode}: {proc.stderr.strip()[:200]}")
    try:
        signed = json.loads(proc.stdout)["signed_url"]
    except (ValueError, KeyError) as exc:
        raise WafChallengeError(f"solver output unparseable: {proc.stdout[:200]}") from exc
    if not signed.startswith("http"):
        raise WafChallengeError(f"bad signed url: {signed[:120]}")
    return signed


class XueqiuWaf:
    """带 WAF 自动解算的雪球会话。"""

    def __init__(self, cookies: dict | None = None, impersonate: str = "chrome", verbose: bool = False):
        self.session = requests.Session(impersonate=impersonate)
        if cookies:
            self.session.cookies.update(cookies)
        self.verbose = verbose
        self._cache: dict[str, str] = {}   # 原始URL -> 签名URL

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[xq_waf] {msg}", flush=True)

    def solve(self, url: str) -> str:
        r = self.session.get(url, headers=XHR_HEADERS, timeout=25)
        if not is_challenge(r.text):
            return url
        signed = solve_challenge(r.text, url)
        self._cache[self._key(url)] = signed
        self._log(f"solved {url[:60]} → md5__1038={urllib.parse.parse_qs(urllib.parse.urlparse(signed).query).get('md5__1038',[''])[0][:24]}…")
        return signed

    @staticmethod
    def _key(url: str) -> str:
        p = urllib.parse.urlparse(url)
        return f"{p.netloc}{p.path}"

    def fetch(self, url: str, headers: dict | None = None, retries: int = 2):
        """请求 url；若遇挑战则自动解算并重试。返回最终 response。"""
        hdrs = dict(XHR_HEADERS)
        if headers:
            hdrs.update(headers)
        resp = self.session.get(url, headers=hdrs, timeout=25)
        for _ in range(retries):
            if not is_challenge(resp.text):
                return resp
            signed = self._cache.get(self._key(url)) or self.solve(url)
            resp = self.session.get(signed, headers=hdrs, timeout=25)
        return resp

    @staticmethod
    def classify(resp) -> str:
        t = resp.text
        if is_challenge(t):
            return "WAF挑战"
        if "安全策略拦截" in t:
            return "安全策略拦截"
        if '"error_code":400016' in t or '"error_code":"400016"' in t:
            return "需登录(400016)"
        if "用户未登录" in t:
            return "需登录"
        if t.lstrip().startswith(("{", "[")):
            return "数据"
        return "其他"


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else \
        "https://xueqiu.com/statuses/hot/listV2.json?since_id=-1&max_id=-1&size=20"
    xq = XueqiuWaf(verbose=True)
    r = xq.fetch(target)
    print(f"{xq.classify(r)} http={r.status_code} len={len(r.text)}")
    print(r.text[:300])
