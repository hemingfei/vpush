"""行为器当日计划持久化：本地文件版（票 #17 交付物 ②）。

云端先例：scheduler 把 MXDailyPlan 存 settings 键 mx_daily_plan
（app/scheduler.py:129，读写于 _mx_windows_today，scheduler.py:2725-2744：
当天键命中 loads_plan、否则 build_daily_plan + set_setting）。

本地 agent 无云端 DB——计划存 agent 数据目录下按日命名的 JSON 文件，
序列化格式复用 mx_window.dumps_plan/loads_plan（「键格式复用」是搬运红线，
mx-behavior-logic.md §1）：

- 同一天重启后读到同一份计划：「真人日程当天固定」，多次重启窗口形状
  不漂移（mx_window.py 模块 docstring 的原文语义）；
- 跨天/坏文件 → 调用方 builder 重新生成并覆盖：坏数据只损失「重启后计划
  复用」，绝不让一条坏文件阻塞当日窗口管理（loads_plan 容错边界原文）。

计划生成本身（三段窗口/兜底槽/晚间强关的随机分布）不在此重写——
直接复用 app.services.mx_window.build_daily_plan，数值语义单一来源。
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from app.services.mx_window import CN_TZ, MXDailyPlan, dumps_plan, loads_plan


class DailyPlanStore:
    """按日命名的计划文件存取：load_or_build 是唯一入口。"""

    def __init__(self, dir_path: str | Path):
        self.dir_path = Path(dir_path)

    def _path_for(self, day: date) -> Path:
        return self.dir_path / f"mx_daily_plan_{day.isoformat()}.json"

    def load_or_build(
        self,
        day: date,
        builder: Callable[[date], MXDailyPlan],
    ) -> MXDailyPlan:
        """读当日计划；缺失/日期不匹配/坏数据时 builder 重建并覆盖写。"""
        path = self._path_for(day)
        try:
            plan = loads_plan(path.read_text(encoding="utf-8"), day)
        except OSError:
            plan = None
        if plan is None:
            plan = builder(day)
            self.dir_path.mkdir(parents=True, exist_ok=True)
            # 序列化走 mx_window.dumps_plan：与云端 settings 存储串同构
            path.write_text(dumps_plan(plan), encoding="utf-8")
        return plan


def get_today_plan(
    *,
    store_dir: str | Path,
    now: datetime,
    builder: Callable[[date], MXDailyPlan],
) -> MXDailyPlan:
    """取「今天」（CN_TZ 口径）的计划——窗口日历属于 MX 平台侧的上海时间。

    与 mx_window.CN_TZ 同口径固定 UTC+8，不落运行机器本地时区：运营机
    时区设置不该改变平台可观察的在线日程。
    """
    store = DailyPlanStore(store_dir)
    day = (now.astimezone(CN_TZ) if now.tzinfo else now.replace(tzinfo=CN_TZ)).date()
    return store.load_or_build(day, builder)
