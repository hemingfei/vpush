"""MX 每日运行窗口：把 MX 在线时间压缩到每天一段随机时段，降低被风控画像的暴露面。

窗口每天生成一次：早 7:00-8:00 之间随机一个时刻开启，晚 16:00-17:00 之间随机
一个时刻关闭，生成后当天固定（服务重启后重新生成，属可接受的随机性损失）。
"""
from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))

WINDOW_START_EARLIEST = time(7, 0)
WINDOW_STOP_EARLIEST = time(16, 0)
# 开/关各自在 [earliest, earliest+1h) 内随机
WINDOW_RANDOM_SPAN_SECONDS = 3600


def generate_mx_daily_window(day: date) -> tuple[datetime, datetime]:
    """生成 day 当天的运行窗口 (start, stop)：开在 7-8 点、关在 16-17 点的随机时刻。"""
    start = datetime.combine(
        day, WINDOW_START_EARLIEST, tzinfo=CN_TZ
    ) + timedelta(seconds=random.randint(0, WINDOW_RANDOM_SPAN_SECONDS - 1))
    stop = datetime.combine(
        day, WINDOW_STOP_EARLIEST, tzinfo=CN_TZ
    ) + timedelta(seconds=random.randint(0, WINDOW_RANDOM_SPAN_SECONDS - 1))
    return start, stop


def in_window(now: datetime, start: datetime, stop: datetime) -> bool:
    """now 是否落在 [start, stop) 窗口内。"""
    return start <= now < stop
