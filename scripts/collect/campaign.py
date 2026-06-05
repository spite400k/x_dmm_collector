import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import logging
import os
import sys

from dmm.dmm_campaign_api import fetch_campaigns
from db.trn_campaigns_repository import upsert_campaign
from utils.logger import setup_logger

os.makedirs("logs", exist_ok=True)
setup_logger("main_campaign.log")


def main():
    has_error = False

    try:
        campaigns = fetch_campaigns()
        logging.info("取得件数: %d", len(campaigns))

        for campaign in campaigns:
            if not upsert_campaign(campaign):
                has_error = True
    except Exception as exc:
        logging.error("登録処理に失敗: %s", exc)
        has_error = True

    if has_error:
        logging.error("処理中にエラーが発生しました")
        sys.exit(1)

    logging.info("全ての処理が正常に完了しました")
    sys.exit(0)


if __name__ == "__main__":
    main()
