"""run.py の多重起動防止用ロック。"""

from __future__ import annotations

import atexit
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

DEFAULT_HEARTBEAT_INTERVAL = 30.0
DEFAULT_STALE_AFTER = 600.0  # 生存 PID でも heartbeat がこの秒数古いと stale
HEARTBEAT_INTERVAL_ENV = "X_DMM_LOCK_HEARTBEAT_INTERVAL"
STALE_AFTER_ENV = "X_DMM_LOCK_STALE_AFTER"


class RunLockError(RuntimeError):
    """別プロセスが既にロックを保持している。"""


def heartbeat_settings() -> tuple[float, float]:
    """(heartbeat_interval, stale_after) 秒。"""
    interval = float(
        os.environ.get(HEARTBEAT_INTERVAL_ENV, str(DEFAULT_HEARTBEAT_INTERVAL))
    )
    stale_after = float(os.environ.get(STALE_AFTER_ENV, str(DEFAULT_STALE_AFTER)))
    if interval <= 0:
        interval = DEFAULT_HEARTBEAT_INTERVAL
    if stale_after <= 0:
        stale_after = DEFAULT_STALE_AFTER
    return interval, stale_after


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


def parse_lock_record(text: str) -> tuple[int | None, float | None]:
    """ロック1行から (pid, heartbeat_epoch) を返す。hb 無しの旧形式は heartbeat=None。"""
    raw = (text or "").strip()
    if not raw:
        return None, None
    line = raw.splitlines()[0].strip()
    parts = line.split()
    try:
        pid = int(parts[0])
    except (ValueError, IndexError):
        return None, None
    heartbeat: float | None = None
    for part in parts[1:]:
        if part.startswith("hb="):
            try:
                heartbeat = float(part[3:])
            except ValueError:
                heartbeat = None
            break
    return pid, heartbeat


def clear_stale_lock(
    path: Path,
    *,
    now: float | None = None,
    stale_after: float | None = None,
) -> bool:
    """ホルダ PID が死んでいる、または heartbeat が古い場合にロックを削除する。"""
    if not path.exists():
        return False
    holder = read_lock_holder(path)
    pid, heartbeat = parse_lock_record(holder)
    if pid is None:
        return False

    should_clear = False
    if not pid_alive(pid):
        should_clear = True
    else:
        if stale_after is None:
            _, stale_after = heartbeat_settings()
        clock = time.time() if now is None else now
        if heartbeat is not None:
            if clock - heartbeat > stale_after:
                should_clear = True
        else:
            # 旧形式（hb 無し）: ファイル mtime が古ければ固着とみなす
            try:
                mtime = path.stat().st_mtime
            except OSError:
                return False
            if clock - mtime > stale_after:
                should_clear = True

    if not should_clear:
        return False
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def lock_is_held(path: Path) -> bool:
    """生存プロセスがロックを保持していれば True（stale は回収して False）。"""
    if not path.exists():
        return False
    if clear_stale_lock(path):
        return False
    return path.exists()


def wait_until_locks_free(
    paths: list[Path],
    *,
    timeout: float,
    poll_interval: float,
    on_wait: Callable[[list[Path], float], None] | None = None,
) -> bool:
    """指定ロックが全て空くまで待つ。1 回以上待ったら True。タイムアウト時は RunLockError。"""
    if not paths:
        return False
    start = time.monotonic()
    waited = False
    while True:
        held = [p for p in paths if lock_is_held(p)]
        if not held:
            return waited
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            holders = ", ".join(f"{p.name}={read_lock_holder(p)}" for p in held)
            raise RunLockError(
                f"相手ジョブの終了待ちがタイムアウトしました ({timeout:.0f}s): {holders}"
            )
        waited = True
        if on_wait is not None:
            on_wait(held, elapsed)
        remaining = timeout - elapsed
        time.sleep(min(poll_interval, max(0.0, remaining)))


class RunLock:
    """O_EXCL による排他ロック（クラッシュ後は stale PID / 古い heartbeat で回収）。"""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None
        self._held = False
        self._started = ""
        self._stop_heartbeat = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def _format_holder(self) -> str:
        return f"{os.getpid()} {self._started} hb={time.time():.0f}\n"

    def _write_holder(self) -> None:
        if self._fh is None:
            return
        content = self._format_holder()
        self._fh.seek(0)
        self._fh.write(content)
        self._fh.truncate()
        self._fh.flush()

    def _heartbeat_loop(self, interval: float) -> None:
        while not self._stop_heartbeat.wait(interval):
            if not self._held:
                break
            try:
                self._write_holder()
            except OSError:
                break

    def _start_heartbeat(self) -> None:
        interval, _ = heartbeat_settings()
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(interval,),
            name=f"run-lock-hb:{self.path.name}",
            daemon=True,
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat_thread(self) -> None:
        self._stop_heartbeat.set()
        thread = self._heartbeat_thread
        self._heartbeat_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

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
        self._started = time.strftime("%Y-%m-%d %H:%M:%S")
        self._write_holder()
        self._held = True
        self._start_heartbeat()
        atexit.register(self.release)

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        self._stop_heartbeat_thread()
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
