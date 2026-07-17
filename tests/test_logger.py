import logging
from logging.handlers import TimedRotatingFileHandler
from unittest.mock import patch

from utils.logger import (
    LOG_ENCODING,
    RotatingLogFile,
    create_rotating_file_handler,
    create_utf8_stream_handler,
    ensure_utf8_stdio,
    setup_logger,
)


def test_setup_logger_falls_back_when_file_locked(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "locked.log"
    log_file.write_text("existing", encoding="utf-8")

    monkeypatch.setattr("utils.logger.LOG_DIR", str(log_dir))
    monkeypatch.setattr(
        "utils.logger._resolve_log_path",
        lambda _: str(log_file),
    )

    with patch(
        "logging.handlers.TimedRotatingFileHandler._open",
        side_effect=PermissionError(13, "Permission denied"),
    ):
        setup_logger("locked.log")

    root = logging.getLogger()
    assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    assert not any(isinstance(h, TimedRotatingFileHandler) for h in root.handlers)


def test_rotating_log_file_falls_back_when_file_locked(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "locked.log"

    monkeypatch.setattr("utils.logger.LOG_DIR", str(log_dir))
    monkeypatch.setattr(
        "utils.logger._resolve_log_path",
        lambda _: str(log_file),
    )

    with patch(
        "logging.handlers.TimedRotatingFileHandler._open",
        side_effect=PermissionError(13, "Permission denied"),
    ):
        with RotatingLogFile("locked.log") as log_file_obj:
            nbytes = log_file_obj.write("hello\n")

    assert nbytes == 6


def test_rotating_log_file_reopens_stream_after_rollover(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "app.log"

    monkeypatch.setattr("utils.logger.LOG_DIR", str(log_dir))
    monkeypatch.setattr("utils.logger._resolve_log_path", lambda _: str(log_file))

    with RotatingLogFile("app.log") as log_file_obj:
        # delay=True の doRollover 相当で stream が None になった状態を再現。
        log_file_obj.handler.stream.close()
        log_file_obj.handler.stream = None

        assert log_file_obj.fileno() >= 0
        nbytes = log_file_obj.write("after-rollover\n")
        log_file_obj.flush()

    assert nbytes == len("after-rollover\n")
    assert "after-rollover" in log_file.read_text(encoding="utf-8")


def test_file_handler_uses_utf8_encoding(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "utf8.log"

    monkeypatch.setattr("utils.logger.LOG_DIR", str(log_dir))
    monkeypatch.setattr("utils.logger._resolve_log_path", lambda _: str(log_file))

    handler = create_rotating_file_handler(log_file)
    assert handler.encoding == LOG_ENCODING
    handler.close()


def test_setup_logger_writes_japanese_as_utf8(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "jp.log"

    monkeypatch.setattr("utils.logger.LOG_DIR", str(log_dir))
    monkeypatch.setattr("utils.logger._resolve_log_path", lambda _: str(log_file))

    setup_logger("jp.log")
    logging.getLogger("utf8_test").info("登録処理に失敗")

    for handler in logging.getLogger().handlers:
        handler.flush()

    raw = log_file.read_bytes()
    assert "登録処理に失敗".encode("utf-8") in raw


def test_create_utf8_stream_handler_and_ensure_stdio():
    ensure_utf8_stdio()
    handler = create_utf8_stream_handler()
    assert isinstance(handler, logging.StreamHandler)
    handler.close()


def test_ensure_utf8_stdio_skips_when_reconfigure_unavailable(monkeypatch):
    class _NoReconfigure:
        pass

    monkeypatch.setattr("utils.logger.sys.stdout", _NoReconfigure())
    monkeypatch.setattr("utils.logger.sys.stderr", _NoReconfigure())
    ensure_utf8_stdio()  # 例外なくスキップされること


def test_ensure_utf8_stdio_ignores_reconfigure_errors(monkeypatch):
    class _BadStream:
        def reconfigure(self, **_kwargs):
            raise ValueError("cannot reconfigure")

    monkeypatch.setattr("utils.logger.sys.stdout", _BadStream())
    monkeypatch.setattr("utils.logger.sys.stderr", _BadStream())
    ensure_utf8_stdio()
