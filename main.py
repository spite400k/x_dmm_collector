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
        {"service": "doujin", "floor": "digital_doujin"}, # 同人誌
        {"service": "digital", "floor": "videoc"}, # 動画 素人
        # {"service": "digital", "floor": "nikkatsu"}, # 写真
        # {"service": "digital", "floor": "videoa"}, # ビデオ
        # {"service": "digital", "floor": "anime"}, # アニメ
    ]

    for target in targets:
        service = target["service"]
        floor = target["floor"]
        logging.info("[FETCH] site=%s service=%s floor=%s", site, service, floor)

        try:
            items = fetch_items(site=site, service=service, floor=floor, offset=1, hits=100, min_sample_count=5)
            top_items = items[:10]

            for item in top_items:
                insert_dmm_item(item, site=site, service=service, floor=floor)
        except Exception as e:
            logging.error("[ERROR] Failed to fetch or insert items for floor=%s: %s", floor, str(e))

if __name__ == "__main__":
    main()
