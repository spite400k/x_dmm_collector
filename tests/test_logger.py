import logging
from logging.handlers import TimedRotatingFileHandler
from unittest.mock import patch

from utils.logger import RotatingLogFile, setup_logger


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
