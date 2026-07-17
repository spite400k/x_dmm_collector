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
LOG_ENCODING = "utf-8"


def ensure_utf8_stdio() -> None:
    """stdout / stderr のエンコーディングを UTF-8 に揃える（Windows cp932 対策）。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding=LOG_ENCODING, errors="replace")
        except (OSError, ValueError, AttributeError):
            pass


def create_utf8_stream_handler(
    stream=None,
) -> logging.StreamHandler:
    """コンソール出力用 StreamHandler（UTF-8）。"""
    ensure_utf8_stdio()
    return logging.StreamHandler(stream=stream)


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
        encoding=LOG_ENCODING,
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

    handlers: list[logging.Handler] = [create_utf8_stream_handler()]
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

    def _ensure_stream(self):
        # delay=True や doRollover 後は stream が None になるため再オープンする。
        if self.handler.stream is None:
            self.handler.stream = self.handler._open()
        return self.handler.stream

    def write(self, s: str) -> int:
        if not s:
            return 0
        if self.handler is None:
            assert self._fallback is not None
            return self._fallback.write(s)
        self._maybe_rollover()
        return self._ensure_stream().write(s)

    def flush(self) -> None:
        if self.handler is None:
            if self._fallback is not None:
                sys.stderr.write(self._fallback.getvalue())
                self._fallback = StringIO()
            return
        self._ensure_stream().flush()

    def fileno(self) -> int:
        if self.handler is None:
            return sys.stderr.fileno()
        return self._ensure_stream().fileno()

    def close(self) -> None:
        if self.handler is not None:
            self.handler.close()

    def __enter__(self) -> "RotatingLogFile":
        return self

    def __exit__(self, *args) -> None:
        self.close()
