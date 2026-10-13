"""MX TOKEN 自动更换触发器（Jenkins vpush-mx-token）。

2026-10-13 下午破案：平台在下午时段对被回收会话的 token 置「连上即断」
标记（40/msg ack 后同毫秒 41/msg, 空载荷），与源 IP/TLS 指纹/客户端实现
全无关，本地退避无法自愈（实测 67 分钟不消退），唯一解法是换新 token
（当日两次实锤：13:51、16:02 换 token 后首连即站住）。

本模块把「管理员手动跑 Jenkins」升级为受限自动触发：
- 触发点（scheduler 接线）：WS 风暴形态确认（连续 2 次连上即断）、
  WS 永久放弃自动重连（含 TOKEN 过期被拒）；
- 闸门：每日预算 + 最小冷却间隔（DB 持久化，重启不清零）——频繁的验证码
  登录本身就是账号风险事件，宁可少换不能刷穿；
- 凭据（仅环境变量，不入库不入配置文件）：
    MX_RENEW_JENKINS_USER / MX_RENEW_JENKINS_PASSWORD  必填，缺省=功能关闭
    MX_RENEW_JENKINS_URL       默认 https://jenkins.hegame.tech
    MX_RENEW_JENKINS_JOB       默认 vpush-mx-token
    MX_RENEW_DAILY_BUDGET      默认 2（次/日）
    MX_RENEW_COOLDOWN_MIN      默认 60（分钟）
    MX_RENEW_DISABLED          置 1 强制关闭
- Jenkins 侧任务自带 disableConcurrentBuilds，重复触发只是排队，无害。

触发成功后 Jenkins 任务会写回新 TOKEN 并重启容器冷启动生效，本进程随后
被替换，无需任何本地收尾。
"""
from __future__ import annotations

import asyncio
import base64
import http.cookiejar
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)

DEFAULT_JENKINS_URL = "https://jenkins.hegame.tech"
DEFAULT_JENKINS_JOB = "vpush-mx-token"
DEFAULT_DAILY_BUDGET = 2
DEFAULT_COOLDOWN_MIN = 60
_HTTP_TIMEOUT = 20.0

_SETTING_DAY = "mx_renew_day"
_SETTING_USED = "mx_renew_used"
_SETTING_LAST = "mx_renew_last"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(_env(name) or default))
    except ValueError:
        return default


class MxAutoRenewer:
    """受限的「换 TOKEN」自动触发器：闸门判断 + Jenkins 构建触发。"""

    def __init__(self, db=None):
        self._db = db
        self._lock = asyncio.Lock()

    # ---- 配置（全部读环境变量，运行时求值，便于不重启改配置的测试与运维）----

    @property
    def enabled(self) -> bool:
        if _env("MX_RENEW_DISABLED") in {"1", "true", "yes"}:
            return False
        return bool(_env("MX_RENEW_JENKINS_USER") and _env("MX_RENEW_JENKINS_PASSWORD"))

    @property
    def daily_budget(self) -> int:
        return _env_int("MX_RENEW_DAILY_BUDGET", DEFAULT_DAILY_BUDGET)

    @property
    def cooldown_min(self) -> int:
        return _env_int("MX_RENEW_COOLDOWN_MIN", DEFAULT_COOLDOWN_MIN)

    # ---- 预算/冷却（DB 持久化；db 缺席时仅内存外无状态，测试用假 db）----

    def _used_today(self) -> int:
        if self._db is None:
            return 0
        today = datetime.now().strftime("%Y-%m-%d")
        if (self._db.get_setting(_SETTING_DAY) or "") != today:
            return 0
        try:
            return int(self._db.get_setting(_SETTING_USED) or 0)
        except ValueError:
            return 0

    def _gate(self) -> tuple[bool, str]:
        used = self._used_today()
        if used >= self.daily_budget:
            return False, f"今日预算已用完（{used}/{self.daily_budget}）"
        last_raw = ""
        if self._db is not None:
            last_raw = self._db.get_setting(_SETTING_LAST) or ""
        try:
            last = float(last_raw)
        except ValueError:
            last = 0.0
        if last:
            elapsed = time.time() - last
            remain = self.cooldown_min * 60 - elapsed
            if remain > 0:
                return False, f"冷却中（还需约 {int(remain) // 60 + 1} 分钟）"
        return True, f"今日第 {used + 1}/{self.daily_budget} 次"

    def _record(self) -> None:
        if self._db is None:
            return
        self._db.set_setting(_SETTING_DAY, datetime.now().strftime("%Y-%m-%d"))
        self._db.set_setting(_SETTING_USED, str(self._used_today() + 1))
        self._db.set_setting(_SETTING_LAST, str(time.time()))

    # ---- Jenkins 触发（crumb 与 POST 必须同 cookie 会话；-H 用 "Name: Value"）----

    def _jenkins_post_build(self) -> dict:
        """阻塞版 Jenkins 触发（调用方 to_thread）。201=已入队。"""
        user = _env("MX_RENEW_JENKINS_USER")
        password = _env("MX_RENEW_JENKINS_PASSWORD")
        base = _env("MX_RENEW_JENKINS_URL", DEFAULT_JENKINS_URL).rstrip("/")
        job = _env("MX_RENEW_JENKINS_JOB", DEFAULT_JENKINS_JOB)
        auth = base64.b64encode(f"{user}:{password}".encode()).decode()

        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

        def call(path: str, data=None, method: str | None = None, extra: dict | None = None):
            headers = {"Authorization": f"Basic {auth}"}
            if extra:
                headers.update(extra)
            req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
            return opener.open(req, timeout=_HTTP_TIMEOUT)

        crumb = json.load(call("/crumbIssuer/api/json"))
        build_req = {
            crumb["crumbRequestField"]: crumb["crumb"],
        }
        try:
            resp = call(f"/job/{job}/build", data=b"", method="POST", extra=build_req)
            code = resp.status
        except urllib.error.HTTPError as exc:
            return {"ok": False, "detail": f"Jenkins POST HTTP {exc.code}（crumb/权限问题）"}
        return {"ok": code == 201, "detail": f"Jenkins 构建#{job} 触发 HTTP {code}"}

    async def trigger(self, reason: str) -> dict:
        """带闸门的触发入口：返回 {ok, detail}，绝不抛异常（失败只记日志）。"""
        if not self.enabled:
            return {
                "ok": False,
                "detail": "自动换 TOKEN 未启用（缺 MX_RENEW_JENKINS_USER/PASSWORD）",
            }
        async with self._lock:
            gate_ok, gate_detail = self._gate()
            if not gate_ok:
                logger.warning(
                    "MX 自动换 TOKEN 跳过（%s）：原因：%s", gate_detail, reason
                )
                return {"ok": False, "detail": f"未触发：{gate_detail}"}
            try:
                result = await asyncio.to_thread(self._jenkins_post_build)
            except Exception as exc:  # noqa: BLE001 - 网络问题不能炸掉调用链
                logger.error("MX 自动换 TOKEN 触发异常（原因：%s）：%s", reason, exc)
                return {"ok": False, "detail": f"触发异常：{exc}"}
            if result.get("ok"):
                self._record()
                logger.warning(
                    "MX 自动换 TOKEN 已触发（%s；原因：%s）——Jenkins 构建完成后"
                    "写回新 TOKEN 并重启容器",
                    gate_detail, reason,
                )
            else:
                logger.error("MX 自动换 TOKEN 触发失败：%s", result.get("detail"))
            return result
