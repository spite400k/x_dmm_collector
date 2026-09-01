import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import sys

from db.supabase_client import supabase2
# from db.storageMega import mega_login, mega_logout
from dmm.dmm_api import fetch_items
from db.trn_dmm_items_repository import insert_dmm_item_supabase2 as insert_dmm_item
import os
import logging
from utils.get_sample_movie import get_sample_movie
from utils.get_tachiyomi import TachiyomiCaptureSession
from utils.logger import setup_logger
from scripts.collect._filter import (
    filter_unregistered_items,
    register_collected_item,
    run_items_isolated,
    supabase_exists_checker,
)

# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)

# ZIP ローテート付きログ設定
setup_logger("main_bltl.log")
#---------------------
#定数・設定
#---------------------
hits_per_request = 30

# ---------------------
# ファイル削除
# ---------------------
def cleanup_file(filepath: str):
    try:
        os.remove(filepath)
        logging.info(f"🧹 削除完了: {filepath}")
    except FileNotFoundError:
        pass


# ---------------------
# メイン処理
# ---------------------
def main():
    # 対象の service/floor の組み合わせ一覧
    targets = [
        {"site": "FANZA", "service": "doujin", "floor": "digital_doujin_bl"}, # らぶカル（BL）
        {"site": "FANZA", "service": "doujin", "floor": "digital_doujin_tl"}, # らぶカル（TL）
        {"site": "FANZA", "service": "ebook", "floor": "tl"}, # TL
        {"site": "FANZA", "service": "ebook", "floor": "bl"}, # BL
    ]

    has_error = False

    with TachiyomiCaptureSession() as tachiyomi:
        for target in targets:
            site = target["site"]
            service = target["service"]
            floor = target.get("floor")
            logging.info("[FETCH] site=%s service=%s floor=%s", site, service, floor)

            try:
                top_items = fetch_items(
                    site=site,
                    service=service,
                    floor=floor,
                    offset=1,
                    hits=hits_per_request,
                    min_sample_count=10,
                    supabase_client=supabase2,
                )
                logging.info("データ取得完了")

                items = filter_unregistered_items(
                    top_items,
                    exists_by_content_id=supabase_exists_checker(supabase2.table("trn_dmm_items")),
                )
                logging.info("未登録 %d 件 / 取得 %d 件", len(items), len(top_items))
            except Exception as e:
                logging.error("登録処理に失敗: %s", str(e))
                has_error = True
                continue

            def process_one(item: dict) -> None:
                register_collected_item(
                    item,
                    site=site,
                    service=service,
                    floor=floor,
                    insert_fn=insert_dmm_item,
                    tachiyomi_session=tachiyomi,
                    cleanup_file=cleanup_file,
                )

            if run_items_isolated(items, process_one):
                has_error = True

    if has_error:
        logging.error("処理中にエラーが発生しました")
        # mega_logout()  # 最後にログアウト
        sys.exit(1)  # 非ゼロで終了（CIで失敗扱い）
    else:
        logging.info("全ての処理が正常に完了しました")
        # mega_logout()  # 最後にログアウト
        sys.exit(0)


if __name__ == "__main__":
    main()
