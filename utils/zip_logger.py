# utils/zip_logger.py
import logging
from logging.handlers import TimedRotatingFileHandler
import zipfile
import os


class ZipRotator:
    """Rotator: ローテートされたログを ZIP 圧縮する"""

    def __call__(self, source, dest):
        zip_name = dest + ".zip"

        # ZIP 圧縮
        with zipfile.ZipFile(zip_name, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(source, arcname=os.path.basename(source))

        # 元ログ削除
        os.remove(source)


class ZipRotatingLogger:
    """
    日次ローテート + ZIP圧縮 + backupCount維持 の便利ログクラス
    """

    @staticmethod
    def setup(
        log_path: str = "logs/fetch_items.log",
        level=logging.INFO,
        backupCount: int = 7,
    ):
        # ディレクトリを自動作成
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        logger = logging.getLogger()
        logger.setLevel(level)

        handler = TimedRotatingFileHandler(
            filename=log_path,
            when="midnight",
            interval=1,
            backupCount=backupCount,
            encoding="utf-8",
            utc=False,
        )

        # ローテート後のファイル名 suffix
        handler.suffix = "%Y-%m-%d"

        # ZIP圧縮ローテータに差し替え
        handler.rotator = ZipRotator()

        # ログフォーマット設定
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        )
        handler.setFormatter(formatter)

        # 重複追加を防ぐ
        if not logger.handlers:
            logger.addHandler(handler)

            # コンソール出力も付ける
            console = logging.StreamHandler()
            console.setFormatter(formatter)
            logger.addHandler(console)

        return logger
