import logging
import os
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

LOG_DIR = "logs"
BACKUP_COUNT = 7
ROTATE_WHEN = "midnight"
ROTATE_INTERVAL = 1


def _resolve_log_path(log_file: str | Path) -> str:
    path = Path(log_file)
    if not path.is_absolute() and path.parent == Path("."):
        path = Path(LOG_DIR) / path.name
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def create_rotating_file_handler(log_file: str | Path) -> TimedRotatingFileHandler:
    return TimedRotatingFileHandler(
        filename=_resolve_log_path(log_file),
        when=ROTATE_WHEN,
        interval=ROTATE_INTERVAL,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )


def setup_logger(log_file: str) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

    rotating_file_handler = create_rotating_file_handler(log_file)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            rotating_file_handler,
            logging.StreamHandler(),
        ],
        force=True,
    )


class RotatingLogFile:
    """TimedRotatingFileHandler と同等の設定で生テキストを追記するファイルライクオブジェクト。"""

    def __init__(self, log_file: str | Path):
        self.handler = create_rotating_file_handler(log_file)

    def _maybe_rollover(self) -> None:
        record = logging.LogRecord("rotating_log_file", logging.INFO, "", 0, "", (), None)
        if self.handler.shouldRollover(record):
            self.handler.doRollover()

    def write(self, s: str) -> int:
        if not s:
            return 0
        self._maybe_rollover()
        return self.handler.stream.write(s)

    def flush(self) -> None:
        self.handler.stream.flush()

    def fileno(self) -> int:
        return self.handler.stream.fileno()

    def close(self) -> None:
        self.handler.close()

    def __enter__(self) -> "RotatingLogFile":
        return self

    def __exit__(self, *args) -> None:
        self.close()
