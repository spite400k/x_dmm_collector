import io
from unittest.mock import MagicMock, patch

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
