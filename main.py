from dmm.dmm_api import fetch_items
from db.trn_dmm_items_repository import insert_dmm_item
import os
import logging

# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/fetch_items.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def main():
    site = "FANZA"

    # 対象の service/floor の組み合わせ一覧
    targets = [
        {"service": "doujin", "floor": "digital_doujin"},
        {"service": "ebook", "floor": "comic"},
        {"service": "ebook", "floor": "photo"},
        {"service": "videoa", "floor": "videoa"},
        # 必要に応じて追加...
    ]

    for target in targets:
        service = target["service"]
        floor = target["floor"]
        logging.info("[FETCH] site=%s service=%s floor=%s", site, service, floor)

        try:
            items = fetch_items(site=site, service=service, floor=floor, offset=1, hits=10)
            for item in items:
                insert_dmm_item(item)
        except Exception as e:
            logging.error("[ERROR] Failed to fetch or insert items for floor=%s: %s", floor, str(e))

if __name__ == "__main__":
    main()
