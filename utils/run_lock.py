"""run.py の多重起動防止用ロック。"""

from __future__ import annotations

import atexit
import os
import sys
import time
from pathlib import Path


class RunLockError(RuntimeError):
    """別プロセスが既にロックを保持している。"""


def pid_alive(pid: int) -> bool:
    """指定 PID が生存しているか。"""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            )
            if ok == 0:
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock_holder(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip() or "(empty)"
    except OSError:
        return "(unreadable)"


def clear_stale_lock(path: Path) -> bool:
    """ホルダ PID が死んでいればロックファイルを削除する。削除したら True。"""
    if not path.exists():
        return False
    holder = read_lock_holder(path)
    try:
        pid = int(holder.split()[0])
    except (ValueError, IndexError):
        return False
    if pid_alive(pid):
        return False
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


class RunLock:
    """O_EXCL による排他ロック（クラッシュ後は stale PID 判定で回収）。"""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None
        self._held = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        clear_stale_lock(self.path)

        flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
        try:
            fd = os.open(self.path, flags)
        except FileExistsError as exc:
            holder = read_lock_holder(self.path)
            raise RunLockError(
                f"別の run.py が実行中です (lock={self.path}, holder={holder})"
            ) from exc

        self._fh = os.fdopen(fd, "w+", encoding="utf-8")
        self._fh.write(f"{os.getpid()} {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self._fh.flush()
        self._held = True
        atexit.register(self.release)

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            if self._fh is not None:
                self._fh.close()
                self._fh = None
        finally:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, *args) -> bool:
        self.release()
        return False
