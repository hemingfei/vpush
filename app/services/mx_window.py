"""MX 每日运行窗口：把 MX 在线时间压缩到每天三段随机时段，降低被风控画像的暴露面。

窗口每天生成一次（2026-09-02 起为三段）：
- 早市：7:00-8:00 之间随机开，11:40-12:00 之间随机关；
- 午后：12:30-12:50 之间随机开，16:00-16:30 之间随机关；
- 晚间：19:00-19:30 之间随机开，23:30-23:55 之间随机关。
生成后当天固定（服务重启后重新生成，属可接受的随机性损失）。
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))

# 每日窗口规格：(开窗最早时刻, 开窗随机跨度秒, 关窗最早时刻, 关窗随机跨度秒)
DAILY_WINDOW_SPECS = (
    (time(7, 0), 3600, time(11, 40), 20 * 60),      # 早市
    (time(12, 30), 20 * 60, time(16, 0), 30 * 60),  # 午后
    (time(19, 0), 30 * 60, time(23, 30), 25 * 60),  # 晚间
)


def generate_mx_daily_windows(day: date) -> list[tuple[datetime, datetime]]:
    """生成 day 当天的运行窗口列表：各段在自身随机跨度内取开/关时刻。"""
    windows = []
    for open_earliest, open_span, stop_earliest, stop_span in DAILY_WINDOW_SPECS:
        start = datetime.combine(
            day, open_earliest, tzinfo=CN_TZ
        ) + timedelta(seconds=random.randint(0, open_span - 1))
        stop = datetime.combine(
            day, stop_earliest, tzinfo=CN_TZ
        ) + timedelta(seconds=random.randint(0, stop_span - 1))
        windows.append((start, stop))
    return windows


def in_window(now: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    """now 是否落在任一 [start, stop) 窗口内。"""
    return any(start <= now < stop for start, stop in windows)


def arm_windows(
    windows: list[tuple[datetime, datetime]], now: datetime
) -> list[bool]:
    """标记哪些窗口「武装」（到点自动开启）。

    重启安全：开窗时刻早于 now（服务重启前就已错过）的窗口不武装——重启后
    不自动续连，只能管理员「登录」手动拉起，或等下一个尚未到点的窗口到点
    自动触发。
    """
    return [start >= now for start, _ in windows]


def pick_daily_fallback_slot(
    windows: list[tuple[datetime, datetime]],
) -> datetime | None:
    """在窗口内随机挑一个时刻，作为当日唯一一次兜底拉取的预约时刻。

    离关窗至少留 1 分钟，避免时刻落在关窗边缘导致必然放弃。
    """
    if not windows:
        return None
    start, stop = random.choice(windows)
    span = max(0.0, (stop - start).total_seconds() - 60)
    return start + timedelta(seconds=random.uniform(0, span))
