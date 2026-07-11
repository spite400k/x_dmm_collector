import logging
import os
import sys
from io import StringIO
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
        delay=True,
    )


def _try_create_rotating_file_handler(
    log_file: str | Path,
) -> TimedRotatingFileHandler | None:
    path = _resolve_log_path(log_file)
    try:
        handler = create_rotating_file_handler(log_file)
        handler.acquire()
        try:
            if handler.stream is None:
                handler.stream = handler._open()
        finally:
            handler.release()
        return handler
    except (PermissionError, OSError) as exc:
        print(
            f"警告: ログファイルを開けません ({path}): {exc} — コンソール出力のみにフォールバックします",
            file=sys.stderr,
        )
        return None


def setup_logger(log_file: str) -> None:
    os.makedirs(LOG_DIR, exist_ok=True)

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    file_handler = _try_create_rotating_file_handler(log_file)
    if file_handler is not None:
        handlers.insert(0, file_handler)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=handlers,
        force=True,
    )


class RotatingLogFile:
    """TimedRotatingFileHandler と同等の設定で生テキストを追記するファイルライクオブジェクト。"""

    def __init__(self, log_file: str | Path):
        self.handler = _try_create_rotating_file_handler(log_file)
        self._fallback = StringIO() if self.handler is None else None

    def _maybe_rollover(self) -> None:
        if self.handler is None:
            return
        record = logging.LogRecord("rotating_log_file", logging.INFO, "", 0, "", (), None)
        if self.handler.shouldRollover(record):
            self.handler.doRollover()

    def write(self, s: str) -> int:
        if not s:
            return 0
        if self.handler is None:
            assert self._fallback is not None
            return self._fallback.write(s)
        self._maybe_rollover()
        return self.handler.stream.write(s)

    def flush(self) -> None:
        if self.handler is None:
            if self._fallback is not None:
                sys.stderr.write(self._fallback.getvalue())
                self._fallback = StringIO()
            return
        self.handler.stream.flush()

    def fileno(self) -> int:
        if self.handler is None:
            return sys.stderr.fileno()
        return self.handler.stream.fileno()

    def close(self) -> None:
        if self.handler is not None:
            self.handler.close()

    def __enter__(self) -> "RotatingLogFile":
        return self

    def __exit__(self, *args) -> None:
        self.close()
