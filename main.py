from dmm.dmm_api import fetch_items
from db.trn_dmm_items_repository import insert_dmm_item
import os
import logging

from utils.get_tachiyomi import capture_all_tachiyomi_pages

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
        # {"site": "FANZA", "service": "doujin", "floor": "digital_doujin"}, # 同人誌
        # {"site": "FANZA", "service": "digital", "floor": "videoc"}, # 動画 素人
        {"site": "DMM.R18", "service": "ebook", "floor": "comic"}, # コミック
        # {"site": "DMM.R18", "service": "digital", "floor": "videoa"}, # ビデオ
        # {"site": "DMM.R18", "service": "digital", "floor": "anime"}, # アニメ
    ]

    for target in targets:
        site = target["site"]
        service = target["service"]
        floor = target.get("floor")  # KeyError 回避
        logging.info("[FETCH] site=%s service=%s floor=%s", site, service, floor)

        try:
            items = fetch_items(site=site, service=service, floor=floor, offset=1, hits=100, min_sample_count=10)
            top_items = items[:10]  # 上位10件のみ処理

            for item in top_items:
                tachiyomi_url = item.get("tachiyomi").get("URL")
                if tachiyomi_url:
                    tachiyomi_image_paths = capture_all_tachiyomi_pages(tachiyomi_url)
                # image_paths = fetch_sample_images_from_tachiyomi(sample_urls)
                insert_dmm_item(item, tachiyomi_image_paths, site=site, service=service, floor=floor)
                for image_path in tachiyomi_image_paths:
                    cleanup_file(image_path)
        except Exception as e:
            logging.error("[ERROR] Failed to fetch or insert items for floor=%s: %s", floor, str(e))

if __name__ == "__main__":
    main()
