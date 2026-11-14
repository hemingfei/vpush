"""行为器生命周期结构化日志（票 #17 交付物 ⑥，user story 19 行为器侧）。

形态：JSONL 文件，一行一事件，字段 t（epoch 秒）/kind/account/detail 固定。
「可查询」由 query_events 提供（按 kind 过滤、按时间顺序返回）——排障时
（如「接力切换为什么发生」）直接查文件，不需要额外基础设施。

凭据红线：record 无密码/token 参数位——登录成败只记「成败与原因」，
绝不记凭据（scripts/mx_login.py 的防泄漏口径：凭据不进任何输出/日志）。
坏行读侧跳过：单行损坏不阻塞查询整段（日志是排障资产）。
"""
from __future__ import annotations

import json
import time
from pathlib import Path


class LifecycleLog:
    """JSONL 追加写入器（行为器全生命周期事件的唯一落点）。"""

    def __init__(self, path: str | Path, *, clock=time.time):
        self.path = Path(path)
        self._clock = clock

    def record(self, kind: str, *, account: str | None, detail: str) -> None:
        """记一条事件。事件词汇表：agent_start/browser_open/browser_close/
        login_ok/login_fail/room_switch/relay_switch/new_day_reset。"""
        event = {"t": self._clock(), "kind": kind, "account": account,
                 "detail": detail}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def query_events(path: str | Path, *, kind: str | None = None) -> list[dict]:
    """读回事件（按 kind 过滤、时间顺序）；坏行跳过。"""
    events: list[dict] = []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return events
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or "kind" not in event:
            continue
        if kind is None or event.get("kind") == kind:
            events.append(event)
    return events
