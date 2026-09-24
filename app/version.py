"""版本号与 GitHub 更新检查（带缓存，避免频繁请求 GitHub API）。"""
from __future__ import annotations

import json
import threading
import time

APP_VERSION = "1.12.265"
VERSION_CHECK_TTL = 6 * 3600  # 6 小时
GITHUB_REPO = "icekale/vpush"

# 后台刷新单飞：TTL 过期后只允许一个线程去连 GitHub。此前是在请求线程里
# 同步 httpx.get（timeout=10），阿里云到 api.github.com 经常连不通，缓存过期
# 瞬间的并发 version 请求全部挂住，占满浏览器连接槽把整个页面拖卡
_refresh_lock = threading.Lock()
_refreshing = False


def _version_key(version: str) -> list[int]:
    try:
        return [int(x) for x in (version or "").split(".") if x.isdigit()]
    except (ValueError, TypeError):
        return []


def is_newer(version: str, base: str) -> bool:
    return _version_key(version) > _version_key(base)


def _refresh_in_background(db) -> None:
    global _refreshing
    with _refresh_lock:
        if _refreshing:
            return
        _refreshing = True

    def run() -> None:
        global _refreshing
        try:
            latest = _fetch_latest_version()
            db.set_setting(
                "version_check_cache",
                json.dumps({"latest": latest, "checked_at": time.time()}),
            )
        finally:
            with _refresh_lock:
                _refreshing = False

    threading.Thread(target=run, daemon=True, name="version-check").start()


def _fetch_latest_version() -> str:
    import httpx

    try:
        resp = httpx.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/tags",
            timeout=10,
            headers={"User-Agent": "vpush", "Accept": "application/vnd.github+json"},
        )
        if resp.status_code == 200:
            versions = []
            for tag in resp.json() or []:
                name = (tag.get("name") or "").strip().lstrip("v")
                if name and name[0].isdigit():
                    versions.append(name)
            if versions:
                return max(versions, key=_version_key)
    except Exception:  # noqa: BLE001, S110 - 更新检查失败不影响使用
        pass
    return ""


def latest_github_version(db) -> tuple[str, bool]:
    """查询 GitHub 最新 v* 标签；请求路径永不访问外网。

    缓存命中直接返回；过期/缺失时踢一次后台单飞刷新并立即返回旧值（可能为
    空）——GitHub 检查失败或未完成只影响「有新版本」角标，不值得挂住请求。
    """
    cached = db.get_setting("version_check_cache")
    now = time.time()
    if cached:
        try:
            data = json.loads(cached)
            latest = data.get("latest") or ""
            if now - float(data.get("checked_at") or 0) < VERSION_CHECK_TTL:
                return latest, bool(latest)
            _refresh_in_background(db)
            return latest, bool(latest)
        except (TypeError, ValueError):
            pass
    _refresh_in_background(db)
    return "", False
