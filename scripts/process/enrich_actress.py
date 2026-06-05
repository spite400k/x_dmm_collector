import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import logging
import os
import sys

from dmm.dmm_actress_api import _create_session, enrich_actress, is_unenrichable_name
from db.mst_actress_repository import (
    enrich_and_update_actress,
    fetch_actresses_to_enrich,
    touch_actress_updated_at,
)
from db.supabase_client import supabase
from utils.logger import setup_logger

os.makedirs("logs", exist_ok=True)
setup_logger("main_actress.log")

DEFAULT_BATCH_SIZE = 1000


def main():
    has_error = False
    updated_count = 0
    skipped_count = 0
    touched_count = 0
    batch_size = int(os.getenv("ACTRESS_ENRICH_BATCH_SIZE", DEFAULT_BATCH_SIZE))

    try:
        actresses = fetch_actresses_to_enrich(limit=batch_size, supabase_client=supabase)
        logging.info("更新対象件数: %d", len(actresses))

        if not actresses:
            logging.info("更新対象の女優がありません")
            sys.exit(0)

        session = _create_session()
        try:
            for actress in actresses:
                actress_id = actress["actress_id"]
                name = actress.get("name", "")
                logging.info("[START] actress_id=%s name=%s", actress_id, name)

                if is_unenrichable_name(name):
                    logging.warning("[SKIP] プレースホルダー女優 actress_id=%s name=%s", actress_id, name)
                    if touch_actress_updated_at(actress_id, supabase_client=supabase):
                        touched_count += 1
                    else:
                        has_error = True
                    skipped_count += 1
                    continue

                try:
                    enriched = enrich_actress(actress_id, name=name, session=session)
                except Exception as exc:
                    logging.error("[ERROR] 情報取得失敗 actress_id=%s: %s", actress_id, exc)
                    has_error = True
                    continue

                if not enriched:
                    logging.warning("[SKIP] 取得データなし actress_id=%s", actress_id)
                    if touch_actress_updated_at(actress_id, supabase_client=supabase):
                        touched_count += 1
                    else:
                        has_error = True
                    skipped_count += 1
                    continue

                if enrich_and_update_actress(actress_id, enriched):
                    updated_count += 1
                else:
                    has_error = True
        finally:
            session.close()
    except Exception as exc:
        logging.error("女優情報更新処理に失敗: %s", exc)
        has_error = True

    logging.info(
        "処理結果: 更新=%d スキップ=%d updated_atのみ=%d",
        updated_count,
        skipped_count,
        touched_count,
    )

    if has_error:
        logging.error("処理中にエラーが発生しました")
        sys.exit(1)

    logging.info("全ての処理が正常に完了しました")
    sys.exit(0)


if __name__ == "__main__":
    main()
