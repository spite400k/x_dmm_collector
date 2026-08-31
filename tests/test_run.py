import io
import sys
from unittest.mock import MagicMock, patch

import pytest

import run as run_mod


def test_should_echo_child_output_flag():
    env = {k: v for k, v in __import__("os").environ.items() if k != "GITHUB_ACTIONS"}
    with patch.dict("os.environ", env, clear=True):
        assert run_mod.should_echo_child_output(echo_output=True) is True
        assert run_mod.should_echo_child_output(echo_output=False) is False


def test_should_echo_child_output_on_github_actions():
    with patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}, clear=False):
        assert run_mod.should_echo_child_output(echo_output=False) is True


def test_stream_script_output_echoes_when_requested(capsys):
    proc = MagicMock()
    proc.stdout = io.StringIO("line1\nline2\n")
    log_file = MagicMock()

    out = run_mod.stream_script_output(proc, log_file, echo=True)

    assert out == "line1\nline2\n"
    assert log_file.write.call_count == 2
    captured = capsys.readouterr()
    assert "line1\n" in captured.out
    assert "line2\n" in captured.out


def test_stream_script_output_silent_without_echo(capsys):
    proc = MagicMock()
    proc.stdout = io.StringIO("secret\n")
    log_file = MagicMock()

    out = run_mod.stream_script_output(proc, log_file, echo=False)

    assert out == "secret\n"
    log_file.write.assert_called_once_with("secret\n")
    assert capsys.readouterr().out == ""


def test_log_child_output_on_failure_empty():
    with patch.object(run_mod.logger, "error") as err:
        run_mod.log_child_output_on_failure("scripts/x.py", "  \n")
        err.assert_called_once()
        assert "出力なし" in err.call_args[0][0]


def test_log_child_output_on_failure_with_body():
    with patch.object(run_mod.logger, "error") as err:
        run_mod.log_child_output_on_failure("scripts/x.py", "Traceback\nboom\n")
        err.assert_called_once()
        args = err.call_args[0]
        assert "子プロセス出力" in args[0]
        assert args[1] == "scripts/x.py"
        assert "Traceback" in args[2]
        assert "boom" in args[2]


def test_run_script_dumps_output_on_failure(tmp_path):
    entry = {"path": "scripts/process/create_actress_review.py", "log": str(tmp_path / "t.log")}
    fake_stdout = io.StringIO("SupabaseException: supabase_url is required\n")
    proc = MagicMock()
    proc.stdout = fake_stdout
    proc.wait.return_value = 1

    with patch.object(run_mod.subprocess, "Popen", return_value=proc):
        with patch.object(run_mod, "should_echo_child_output", return_value=False):
            with patch.object(run_mod.logger, "info"):
                with patch.object(run_mod.logger, "error") as err:
                    code = run_mod.run_script(entry, "python", True, 1, 1)
                    assert code == 1
                    dumped = " ".join(str(c) for c in err.call_args_list)
                    assert "supabase_url is required" in dumped


def test_run_script_success(tmp_path):
    entry = {"path": "scripts/process/create_weekly_rankings.py", "log": str(tmp_path / "ok.log")}
    proc = MagicMock()
    proc.stdout = io.StringIO("done\n")
    proc.wait.return_value = 0

    with patch.object(run_mod.subprocess, "Popen", return_value=proc):
        with patch.object(run_mod, "should_echo_child_output", return_value=False):
            with patch.object(run_mod.logger, "info") as info:
                with patch.object(run_mod.logger, "error") as err:
                    code = run_mod.run_script(entry, "python", False, 1, 1)
                    assert code == 0
                    err.assert_not_called()
                    assert any("完了" in str(c) for c in info.call_args_list)


def test_run_lock_path_default():
    assert run_mod.RUN_LOCK_PATH.name == "run.lock"
    assert run_mod.RUN_LOCK_PATH.parent.name == "logs"


def test_resolve_lock_paths_pipeline_phases():
    paths = run_mod.resolve_lock_paths("process_main", None)
    assert len(paths) == 1
    assert paths[0].name == "run_process_main.lock"

    paths = run_mod.resolve_lock_paths("process_actress", None)
    assert paths[0].name == "run_process_actress.lock"

    paths = run_mod.resolve_lock_paths("process_mesugaki", None)
    assert paths[0].name == "run_process_mesugaki.lock"


def test_resolve_lock_paths_process_acquires_all_pipelines():
    paths = run_mod.resolve_lock_paths("process", None)
    names = {p.name for p in paths}
    assert names == {
        "run_process_main.lock",
        "run_process_actress.lock",
        "run_process_mesugaki.lock",
    }


def test_resolve_lock_paths_all_includes_run_and_pipelines():
    paths = run_mod.resolve_lock_paths("all", None)
    names = {p.name for p in paths}
    assert "run.lock" in names
    assert "run_process_main.lock" in names
    assert len(paths) == 4


def test_resolve_lock_paths_script_maps_to_pipeline():
    paths = run_mod.resolve_lock_paths(None, "scripts/process/create_actress_review.py")
    assert paths[0].name == "run_process_actress.lock"

    paths = run_mod.resolve_lock_paths(None, "scripts/collect/default.py")
    assert paths[0].name == "run.lock"


def test_script_cli_args():
    assert run_mod.script_cli_args({}) == []
    assert run_mod.script_cli_args({"args": None}) == []
    assert run_mod.script_cli_args({"args": "--mode weekly"}) == ["--mode weekly"]
    assert run_mod.script_cli_args({"args": ["--mode", "weekly"]}) == ["--mode", "weekly"]


def test_run_script_passes_args(tmp_path):
    entry = {
        "path": "scripts/process/update_items.py",
        "log": str(tmp_path / "w.log"),
        "args": ["--mode", "weekly"],
    }
    proc = MagicMock()
    proc.stdout = io.StringIO("ok\n")
    proc.wait.return_value = 0

    with patch.object(run_mod.subprocess, "Popen", return_value=proc) as popen:
        with patch.object(run_mod, "should_echo_child_output", return_value=False):
            with patch.object(run_mod.logger, "info"):
                code = run_mod.run_script(entry, "python", False, 1, 1)
    assert code == 0
    cmd = popen.call_args[0][0]
    assert cmd[-2:] == ["--mode", "weekly"]


def test_resolve_scripts_weekly_phase():
    tasks = run_mod.load_tasks()
    entries = run_mod.resolve_scripts(tasks, "process_main_weekly", None)
    assert len(entries) == 1
    assert entries[0]["phase"] == "process_main_weekly"
    assert entries[0]["args"] == ["--mode", "weekly"]
    assert entries[0]["path"].endswith("update_items.py")

    mesu = run_mod.resolve_scripts(tasks, "process_mesugaki_weekly", None)
    assert mesu[0]["path"].endswith("update_mesugaki.py")
    assert mesu[0]["args"] == ["--mode", "weekly"]


def test_resolve_scripts_prefers_daily_over_weekly():
    tasks = run_mod.load_tasks()
    entries = run_mod.resolve_scripts(
        tasks, None, "scripts/process/update_items.py"
    )
    assert entries[0]["phase"] == "process_main"
    assert not entries[0].get("args")


def test_resolve_lock_paths_weekly_shares_daily_lock():
    paths = run_mod.resolve_lock_paths("process_main_weekly", None)
    assert paths[0].name == "run_process_main.lock"
    paths = run_mod.resolve_lock_paths("process_mesugaki_weekly", None)
    assert paths[0].name == "run_process_mesugaki.lock"
    tasks = run_mod.load_tasks()
    entries = run_mod.resolve_scripts(tasks, "process_main", None)
    assert len(entries) == 3
    assert all(e["phase"] == "process_main" for e in entries)
    assert entries[0]["path"].endswith("update_items.py")
    assert entries[-1]["path"].endswith("create_weekly_rankings.py")


def test_resolve_scripts_pipeline_phase():
    tasks = run_mod.load_tasks()
    entries = run_mod.resolve_scripts(tasks, "process_main", None)
    assert len(entries) == 3
    assert all(e["phase"] == "process_main" for e in entries)
    assert entries[0]["path"].endswith("update_items.py")
    assert entries[-1]["path"].endswith("create_weekly_rankings.py")


def test_resolve_scripts_prefers_pipeline_over_process():
    tasks = run_mod.load_tasks()
    entries = run_mod.resolve_scripts(
        tasks, None, "scripts/process/update_mesugaki.py"
    )
    assert len(entries) == 1
    assert entries[0]["phase"] == "process_mesugaki"


def test_lock_set_acquire_release(tmp_path):
    p1 = tmp_path / "a.lock"
    p2 = tmp_path / "b.lock"
    lock_set = run_mod.LockSet([p1, p2])
    lock_set.acquire()
    assert p1.exists()
    assert p2.exists()
    lock_set.release()
    assert not p1.exists()
    assert not p2.exists()


def test_lock_set_rollback_on_conflict(tmp_path):
    from utils.run_lock import RunLock, RunLockError

    p1 = tmp_path / "a.lock"
    p2 = tmp_path / "b.lock"
    holder = RunLock(p2)
    holder.acquire()
    try:
        lock_set = run_mod.LockSet([p1, p2])
        with pytest.raises(RunLockError):
            lock_set.acquire()
        assert not p1.exists()
    finally:
        holder.release()


def test_resolve_peer_wait_paths_process_waits_for_collect():
    paths = run_mod.resolve_peer_wait_paths("process_main", None)
    assert [p.name for p in paths] == ["run.lock"]
    paths = run_mod.resolve_peer_wait_paths("process", None)
    assert [p.name for p in paths] == ["run.lock"]
    paths = run_mod.resolve_peer_wait_paths("process_main_weekly", None)
    assert [p.name for p in paths] == ["run.lock"]


def test_resolve_peer_wait_paths_collect_waits_for_process():
    names = {p.name for p in run_mod.resolve_peer_wait_paths("collect", None)}
    assert names == {
        "run_process_main.lock",
        "run_process_actress.lock",
        "run_process_mesugaki.lock",
    }
    names = {p.name for p in run_mod.resolve_peer_wait_paths("manual", None)}
    assert "run_process_main.lock" in names


def test_resolve_peer_wait_paths_script_and_all():
    paths = run_mod.resolve_peer_wait_paths(None, "scripts/process/create_ai_review.py")
    assert [p.name for p in paths] == ["run.lock"]
    paths = run_mod.resolve_peer_wait_paths(None, "scripts/collect/default.py")
    assert {p.name for p in paths} == {
        "run_process_main.lock",
        "run_process_actress.lock",
        "run_process_mesugaki.lock",
    }
    assert run_mod.resolve_peer_wait_paths("all", None) == []


def test_peer_wait_settings_env(monkeypatch):
    monkeypatch.setenv(run_mod.PEER_WAIT_TIMEOUT_ENV, "12.5")
    monkeypatch.setenv(run_mod.PEER_WAIT_POLL_ENV, "0.5")
    assert run_mod.peer_wait_settings() == (12.5, 0.5)


def test_wait_for_peer_locks_all_is_noop():
    assert run_mod.wait_for_peer_locks("all", None) is False


def test_wait_for_peer_locks_logs_throttled(monkeypatch):
    calls: list[tuple] = []

    def fake_wait(paths, *, timeout, poll_interval, on_wait):
        on_wait(paths, 0.0)
        on_wait(paths, 10.0)
        on_wait(paths, 600.0)
        calls.append((timeout, poll_interval, [p.name for p in paths]))
        return True

    monkeypatch.setattr(run_mod, "wait_until_locks_free", fake_wait)
    monkeypatch.setattr(run_mod, "peer_wait_settings", lambda: (99.0, 1.0))
    with patch.object(run_mod.logger, "info") as info:
        assert run_mod.wait_for_peer_locks("process_main", None) is True
        messages = [c.args[0] for c in info.call_args_list]
        assert len(messages) == 2
        assert all("待機中" in m for m in messages)
    assert calls[0][0] == 99.0


def test_apply_process_stagger_skips_when_not_waited():
    with patch.object(run_mod.time, "sleep") as sleep:
        run_mod.apply_process_stagger("process_actress", False)
        run_mod.apply_process_stagger(None, True)
        run_mod.apply_process_stagger("process_main", True)
        sleep.assert_not_called()


def test_apply_process_stagger_sleeps_for_actress():
    with patch.object(run_mod.time, "sleep") as sleep:
        with patch.object(run_mod.logger, "info"):
            run_mod.apply_process_stagger("process_actress", True)
            run_mod.apply_process_stagger("process_mesugaki", True)
        assert sleep.call_args_list[0].args[0] == 3600
        assert sleep.call_args_list[1].args[0] == 7200


def test_apply_process_stagger_disabled_by_env(monkeypatch):
    monkeypatch.setenv(run_mod.PROCESS_STAGGER_ENV, "0")
    with patch.object(run_mod.time, "sleep") as sleep:
        run_mod.apply_process_stagger("process_actress", True)
        sleep.assert_not_called()


def test_main_peer_wait_timeout_exits_2(monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["run.py", "--phase", "process_main", "--continue-on-error"]
    )
    monkeypatch.setattr(
        run_mod,
        "wait_for_peer_locks",
        MagicMock(side_effect=run_mod.RunLockError("timeout")),
    )
    monkeypatch.setattr(
        run_mod,
        "resolve_scripts",
        lambda *a, **k: [{"path": "scripts/process/update_items.py", "phase": "process_main"}],
    )
    with patch.object(run_mod, "setup_logger"):
        with patch.object(run_mod.logger, "error"):
            with pytest.raises(SystemExit) as exc:
                run_mod.main()
    assert exc.value.code == 2
