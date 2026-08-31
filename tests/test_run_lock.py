"""utils.run_lock のテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from utils.run_lock import (
    RunLock,
    RunLockError,
    clear_stale_lock,
    lock_is_held,
    pid_alive,
    read_lock_holder,
    wait_until_locks_free,
)


class TestPidAlive:
    def test_non_positive(self):
        assert pid_alive(0) is False
        assert pid_alive(-1) is False

    def test_current_process(self):
        import os

        assert pid_alive(os.getpid()) is True

    def test_dead_pid(self):
        # 通常存在しない大きな PID
        assert pid_alive(999_999_999) is False


class TestReadLockHolder:
    def test_missing(self, tmp_path: Path):
        assert read_lock_holder(tmp_path / "no.lock") == "(unreadable)"

    def test_empty(self, tmp_path: Path):
        p = tmp_path / "empty.lock"
        p.write_text("", encoding="utf-8")
        assert read_lock_holder(p) == "(empty)"

    def test_content(self, tmp_path: Path):
        p = tmp_path / "h.lock"
        p.write_text("1234 2026-01-01\n", encoding="utf-8")
        assert "1234" in read_lock_holder(p)


class TestClearStaleLock:
    def test_missing(self, tmp_path: Path):
        assert clear_stale_lock(tmp_path / "x.lock") is False

    def test_invalid_holder(self, tmp_path: Path):
        p = tmp_path / "bad.lock"
        p.write_text("not-a-pid", encoding="utf-8")
        assert clear_stale_lock(p) is False
        assert p.exists()

    def test_live_holder(self, tmp_path: Path):
        import os

        p = tmp_path / "live.lock"
        p.write_text(f"{os.getpid()} now\n", encoding="utf-8")
        assert clear_stale_lock(p) is False
        assert p.exists()

    def test_dead_holder(self, tmp_path: Path):
        p = tmp_path / "dead.lock"
        p.write_text("999999999 stale\n", encoding="utf-8")
        assert clear_stale_lock(p) is True
        assert not p.exists()


class TestRunLock:
    def test_acquire_release(self, tmp_path: Path):
        lock_path = tmp_path / "run.lock"
        lock = RunLock(lock_path)
        lock.acquire()
        assert lock_path.exists()
        import os

        assert str(os.getpid()) in lock_path.read_text(encoding="utf-8")
        lock.release()
        assert not lock_path.exists()

    def test_context_manager(self, tmp_path: Path):
        lock_path = tmp_path / "ctx.lock"
        with RunLock(lock_path):
            assert lock_path.exists()
        assert not lock_path.exists()

    def test_double_acquire_raises(self, tmp_path: Path):
        lock_path = tmp_path / "dup.lock"
        first = RunLock(lock_path)
        first.acquire()
        second = RunLock(lock_path)
        with pytest.raises(RunLockError, match="実行中"):
            second.acquire()
        first.release()

    def test_stale_then_acquire(self, tmp_path: Path):
        lock_path = tmp_path / "stale.lock"
        lock_path.write_text("999999999 old\n", encoding="utf-8")
        lock = RunLock(lock_path)
        lock.acquire()
        assert lock_path.exists()
        lock.release()

    def test_release_idempotent(self, tmp_path: Path):
        lock = RunLock(tmp_path / "idem.lock")
        lock.release()
        lock.acquire()
        lock.release()
        lock.release()

    def test_acquire_creates_parent(self, tmp_path: Path):
        lock_path = tmp_path / "nested" / "a" / "run.lock"
        with RunLock(lock_path):
            assert lock_path.exists()


class TestLockIsHeld:
    def test_missing(self, tmp_path: Path):
        assert lock_is_held(tmp_path / "no.lock") is False

    def test_live(self, tmp_path: Path):
        import os

        p = tmp_path / "live.lock"
        p.write_text(f"{os.getpid()} now\n", encoding="utf-8")
        assert lock_is_held(p) is True
        assert p.exists()

    def test_stale_cleared(self, tmp_path: Path):
        p = tmp_path / "dead.lock"
        p.write_text("999999999 stale\n", encoding="utf-8")
        assert lock_is_held(p) is False
        assert not p.exists()


class TestWaitUntilLocksFree:
    def test_empty_paths(self, tmp_path: Path):
        assert wait_until_locks_free([], timeout=1, poll_interval=0.01) is False

    def test_already_free(self, tmp_path: Path):
        p = tmp_path / "free.lock"
        assert wait_until_locks_free([p], timeout=1, poll_interval=0.01) is False

    def test_waits_until_released(self, tmp_path: Path):
        import os

        p = tmp_path / "held.lock"
        p.write_text(f"{os.getpid()} now\n", encoding="utf-8")
        calls: list[float] = []

        def on_wait(_held, elapsed):
            calls.append(elapsed)
            p.unlink()

        waited = wait_until_locks_free(
            [p], timeout=2, poll_interval=0.01, on_wait=on_wait
        )
        assert waited is True
        assert calls

    def test_wait_without_callback(self, tmp_path: Path, monkeypatch):
        import os

        p = tmp_path / "held.lock"
        p.write_text(f"{os.getpid()} now\n", encoding="utf-8")

        def fake_sleep(_sec):
            p.unlink()

        monkeypatch.setattr("utils.run_lock.time.sleep", fake_sleep)
        assert wait_until_locks_free([p], timeout=2, poll_interval=0.01) is True

    def test_timeout(self, tmp_path: Path):
        import os

        p = tmp_path / "stuck.lock"
        p.write_text(f"{os.getpid()} now\n", encoding="utf-8")
        with pytest.raises(RunLockError, match="タイムアウト"):
            wait_until_locks_free([p], timeout=0.0, poll_interval=0.01)

    def test_timeout_after_poll(self, tmp_path: Path, monkeypatch):
        import os

        p = tmp_path / "stuck.lock"
        p.write_text(f"{os.getpid()} now\n", encoding="utf-8")
        sleeps: list[float] = []

        def fake_sleep(sec):
            sleeps.append(sec)

        monkeypatch.setattr("utils.run_lock.time.sleep", fake_sleep)
        monotonic_vals = iter([0.0, 0.0, 0.05, 0.05])
        monkeypatch.setattr(
            "utils.run_lock.time.monotonic", lambda: next(monotonic_vals, 1.0)
        )
        with pytest.raises(RunLockError, match="stuck.lock"):
            wait_until_locks_free([p], timeout=0.05, poll_interval=1.0)
        assert sleeps == [0.05]
