import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from db.supabase_client import supabase
from dmm.dmm_api import fetch_items_merged_sorts
from db.trn_dmm_items_repository import insert_dmm_item
import os
import logging
from utils.logger import setup_logger
from scripts.collect._filter import (
    filter_released_items,
    filter_unregistered_items,
    register_collected_item,
    run_items_isolated,
    supabase_exists_checker,
)

os.makedirs("logs", exist_ok=True)
setup_logger("main.log")

hits_per_request = 100
COLLECT_SORTS = ("rank", "date", "review")


def main():
    targets = [
        {"site": "FANZA", "service": "doujin", "floor": "digital_doujin"},
        {"site": "FANZA", "service": "digital", "floor": "videoc"},
        {"site": "FANZA", "service": "digital", "floor": "videoa"},
        {"site": "FANZA", "service": "ebook", "floor": "comic"},
        {"site": "FANZA", "service": "ebook", "floor": "photo"},
    ]

    has_error = False

    for target in targets:
        site = target["site"]
        service = target["service"]
        floor = target.get("floor")
        logging.info("[FETCH] site=%s service=%s floor=%s", site, service, floor)

        try:
            top_items = fetch_items_merged_sorts(
                site=site,
                service=service,
                floor=floor,
                offset=1,
                hits=hits_per_request,
                sorts=COLLECT_SORTS,
                min_sample_count=10,
            )
            logging.info("データ取得完了")

            top_items = filter_released_items(top_items)
            items = filter_unregistered_items(
                top_items,
                exists_by_content_id=supabase_exists_checker(supabase.table("trn_dmm_items")),
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
            )

        if run_items_isolated(items, process_one):
            has_error = True

    if has_error:
        logging.error("処理中にエラーが発生しました")
        sys.exit(1)
    else:
        logging.info("全ての処理が正常に完了しました")
        sys.exit(0)


if __name__ == "__main__":
    main()
