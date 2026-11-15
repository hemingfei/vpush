"""单实例互斥：数据目录下的锁文件 + O_EXCL 独占创建（Windows 原生可用）。

2026-11-15 事故根因之一：守护脚本靠「能枚举到 mx_agent.py 进程」判存活，
spawn 后 5s 复查太早（WMI 查询偶发慢/漏），每分钟误判「不在」再拉一个——
8 组实例并存共抢 9223。进程枚举是软前提，锁文件是硬前提：
- agent 启动即抢锁，抢不到说明已有实例，立刻退出（不抢 CDP 端口）；
- guard 判定改读锁：锁在 = 有实例（不管枚举得到与否）；锁不在 = 该拉起。

崩溃后锁残留由 acquire 返回「持锁进程已死」信息，调用方可安全接管
（Windows 无 flock/fcntl，独占创建 O_EXCL + 删文件即释放）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LockState:
    """抢锁结果：held=True 抢到（释放用 handle）；taken_by_alive=锁被活进程持有。"""
    held: bool = False
    taken_by_alive: bool = False
    holder_pid: int | None = None
    handle: int | None = None
    lock_path: object | None = None


def _pid_alive(pid: int | None) -> bool:
    """进程存活探测（无第三方依赖；跨平台——agent 仅在 Windows 运行，
    但 CI 的 test-python 车道是 Linux，windll 仅存在于 Windows）。"""
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False  # 打不开：进程不存在（或权限不足——本场景同用户，可判死）
        try:
            code = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return code.value == STILL_ACTIVE
            return True  # 查不到退出码按活着算（保守侧：宁不拉起勿双开）
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    # 非 Windows（CI/测试）：os.kill 探活，权限错=活着、无此进程=死
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True  # 未知异常按活着算（保守侧：宁不拉起勿双开）


def acquire_lock(lock_path) -> LockState:
    """抢单实例锁；抢到后写 pid 并保持句柄（删文件即释放）。

    锁文件被占（O_EXCL 失败）时读持有者 pid 判生死：
    - 死进程残留锁 → 接管（删除重建）；
    - 活进程持有 → taken_by_alive=True，调用方退出。
    任何 IO 异常都按「持有中」处理——双开抢 9223 比漏拉一次 tick 有害得多
    （漏拉由 guard 每分钟重试兜底）。
    """
    from pathlib import Path

    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(str(lock_path),
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        pid = _read_holder_pid(lock_path)
        if _pid_alive(pid):
            return LockState(held=False, taken_by_alive=True, holder_pid=pid)
        # 死进程残留：接管
        try:
            lock_path.unlink()
        except OSError:
            return LockState(held=False, taken_by_alive=True)  # 删不掉按被持有
        try:
            handle = os.open(str(lock_path),
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return LockState(held=False, taken_by_alive=True)
    except OSError:
        return LockState(held=False, taken_by_alive=True)
    try:
        os.write(handle, str(os.getpid()).encode())
    except OSError:
        pass  # pid 写失败不致命：句柄独占本身就是锁
    return LockState(held=True, handle=handle, lock_path=str(lock_path))


def lock_is_taken(lock_path) -> bool:
    """guard 用：锁是否被活进程持有（无锁文件/持有者已死 → False=该拉起）。"""
    from pathlib import Path

    lock_path = Path(lock_path)
    if not lock_path.exists():
        return False
    return _pid_alive(_read_holder_pid(lock_path))


def _read_holder_pid(lock_path) -> int | None:
    try:
        text = lock_path.read_text(encoding="utf-8").strip()
        return int(text)
    except (OSError, ValueError):
        return None


def release_lock(state: LockState) -> None:
    """释放锁（进程退出前调用；崩溃残留由 acquire 的接管路径自愈）。"""
    from pathlib import Path

    if not state.held:
        return
    if state.handle is not None:
        try:
            os.close(state.handle)
        except OSError:
            pass
    try:
        Path(state.lock_path).unlink()  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        pass
