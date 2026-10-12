"""MX 每日运行窗口：把 MX 在线时间压缩到每天三段随机时段，降低被风控画像的暴露面。

窗口每天生成一次（2026-09-02 起为三段）：
- 早市：7:00-8:00 之间随机开，11:40-12:00 之间随机关；
- 午后：12:30-12:50 之间随机开，16:00-16:30 之间随机关；
- 晚间：19:00-19:30 之间随机开，23:30-23:55 之间随机关。

当日计划（窗口 + 兜底槽 + 晚间强关时刻）以 MXDailyPlan 打包，由调度器持久化
到 settings（单键当日覆盖）：同一天无论重启多少次，对平台可见的日程完全一致
——「真人日程当天固定」；旧口径「重启后重新随机」会让多次重启的窗口形状
漂移，与当日日程固定的人像矛盾。

重启自动登录（2026-09-16 起）：工作日 08:00-22:00 内重启服务时补登一次，
让工作时段的重启不丢消息——正处的窗口重新武装，窗口间隙则立即补登；其余
时间维持「错过的窗口不续连」。
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

CN_TZ = timezone(timedelta(hours=8))

# 每日窗口规格：(开窗最早时刻, 开窗随机跨度秒, 关窗最早时刻, 关窗随机跨度秒)
DAILY_WINDOW_SPECS = (
    (time(7, 0), 3600, time(11, 40), 20 * 60),      # 早市
    (time(12, 30), 20 * 60, time(16, 0), 30 * 60),  # 午后
    (time(19, 0), 30 * 60, time(23, 30), 25 * 60),  # 晚间
)

# 重启自动登录时段（工作日 08:00-22:00）：服务重启落在该时段内时补登一次，
# 保证工作时段的重启不丢 MX 消息；夜间/周末重启维持「错过不续连」旧口径
RESTART_LOGIN_START = time(8, 0)
RESTART_LOGIN_END = time(22, 0)


def restart_login_allowed(now: datetime) -> bool:
    """重启时刻是否允许「重启自动登录」：工作日（周一至周五）08:00 ≤ now < 22:00。

    法定节假日调休不做识别，按自然周一至周五口径。
    """
    return now.weekday() < 5 and RESTART_LOGIN_START <= now.time() < RESTART_LOGIN_END


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
    windows: list[tuple[datetime, datetime]],
    now: datetime,
    restart_login: bool = False,
) -> list[bool]:
    """标记哪些窗口「武装」（到点自动开启）。

    重启安全：开窗时刻早于 now（服务重启前就已错过）的窗口不武装——重启后
    不自动续连，只能管理员「登录」手动拉起，或等下一个尚未到点的窗口到点
    自动触发。

    restart_login（工作日 08:00-22:00 重启自动登录，见 restart_login_allowed）
    为 True 时放宽一条：now 正落在其中的窗口重新武装——窗口循环在下个 tick
    自动补登，会话持续到该窗口的关窗时刻。
    """
    armed = [start >= now for start, _ in windows]
    if restart_login:
        for i, (start, stop) in enumerate(windows):
            if start <= now < stop:
                armed[i] = True
                break
    return armed


def pick_daily_fallback_slot(
    windows: list[tuple[datetime, datetime]],
    armed: list[bool] | None = None,
) -> datetime | None:
    """在窗口内随机挑一个时刻，作为当日一次兜底拉取的预约时刻。

    armed 提供时只从当天仍武装的窗口里挑：已错过开窗点的窗口不会自动拉起
    会话，选中它们只会得到「时刻一到就放弃」的迟到执行；全部未武装返回
    None（当天放弃兜底拉取）。不传 armed 保持旧行为（全窗口随机，向后兼容）。

    离关窗至少留 1 分钟，避免时刻落在关窗边缘导致必然放弃。
    """
    if not windows:
        return None
    candidates = windows
    if armed is not None:
        candidates = [w for w, ok in zip(windows, armed) if ok]
        if not candidates:
            return None
    start, stop = random.choice(candidates)
    span = max(0.0, (stop - start).total_seconds() - 60)
    return start + timedelta(seconds=random.uniform(0, span))


def _slot_in_window(window: tuple[datetime, datetime]) -> datetime:
    """单个窗口内随机挑一个兜底时刻（离关窗至少留 1 分钟）。"""
    start, stop = window
    span = max(0.0, (stop - start).total_seconds() - 60)
    return start + timedelta(seconds=random.uniform(0, span))


def pick_daily_fallback_slots(
    windows: list[tuple[datetime, datetime]],
    armed: list[bool] | None = None,
) -> list[datetime]:
    """在窗口内随机挑 1~3 个兜底拉取时刻（2026-10-12 起每天 1~3 次）。

    「每天恰好 1 次、恰好 1 个房间」长期看本身就是可被统计的节拍；放宽成
    每天随机 1~3 次，且每个窗口最多贡献一个槽——槽天然全天铺开、绝不会
    背靠背连发，既更像真人随手点开房间，顺带多兜几层窗口间隙的漏消息。
    armed 语义与 pick_daily_fallback_slot 一致；全部未武装返回空列表。
    """
    candidates = list(windows)
    if armed is not None:
        candidates = [w for w, ok in zip(windows, armed) if ok]
    if not candidates:
        return []
    count = min(random.randint(1, 3), len(candidates))
    chosen = random.sample(candidates, count)
    return sorted(_slot_in_window(w) for w in chosen)


@dataclass(frozen=True)
class MXDailyPlan:
    """当日完整运行计划：窗口、兜底拉取槽、晚间强关时刻。

    三者同日绑定、整体序列化持久化——重启后复用同一份计划，当日对外可见
    的日程（开/关窗、兜底拉取、强关）不再随重启漂移。
    """

    day: date
    windows: tuple[tuple[datetime, datetime], ...]
    fallback_slots: tuple[datetime, ...]
    force_close_at: datetime


# 晚间强关随机跨度：23:30-23:55（与晚间关窗同区间，先到者关窗）
NIGHTLY_FORCE_CLOSE_SPAN_SECONDS = 25 * 60


def build_daily_plan(day: date) -> MXDailyPlan:
    """生成 day 的完整运行计划（窗口 + 兜底槽 + 晚间强关时刻）。"""
    windows = generate_mx_daily_windows(day)
    slots = pick_daily_fallback_slots(windows)
    force_close = datetime.combine(day, time(23, 30), tzinfo=CN_TZ) + timedelta(
        seconds=random.randint(0, NIGHTLY_FORCE_CLOSE_SPAN_SECONDS - 1)
    )
    return MXDailyPlan(
        day=day,
        windows=tuple(windows),
        fallback_slots=tuple(slots),
        force_close_at=force_close,
    )


def dumps_plan(plan: MXDailyPlan) -> str:
    """计划 → settings 存储串（ISO 时刻，ensure_ascii=False）。"""
    return json.dumps(
        {
            "day": plan.day.isoformat(),
            "windows": [[s.isoformat(), e.isoformat()] for s, e in plan.windows],
            "fallback_slots": [t.isoformat() for t in plan.fallback_slots],
            "force_close_at": plan.force_close_at.isoformat(),
        },
        ensure_ascii=False,
    )


def loads_plan(raw: str | None, day: date) -> MXDailyPlan | None:
    """settings 存储串 → 当日计划；日期不匹配或任何字段异常都返回 None。

    容错边界：坏数据只损失「重启后计划复用」，调用方随即重新生成并覆盖，
    绝不让一条坏 settings 阻塞当日窗口管理。
    """
    try:
        data = json.loads(raw or "")
        if not isinstance(data, dict) or data.get("day") != day.isoformat():
            return None
        windows = [
            (datetime.fromisoformat(s), datetime.fromisoformat(e))
            for s, e in data["windows"]
        ]
        slots = [datetime.fromisoformat(t) for t in data["fallback_slots"]]
        force_close = datetime.fromisoformat(data["force_close_at"])
        if not windows or not slots:
            return None
        if force_close.date() != day:
            return None
        return MXDailyPlan(
            day=day,
            windows=tuple(windows),
            fallback_slots=tuple(slots),
            force_close_at=force_close,
        )
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
