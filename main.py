import sys
# from db.storageMega import mega_login, mega_logout
from dmm.dmm_api import fetch_items
from db.trn_dmm_items_repository import insert_dmm_item
import os
import logging
from utils.get_sample_movie import get_sample_movie
from utils.get_tachiyomi import capture_all_tachiyomi_pages
from utils.zip_logger import ZipRotatingLogger

# ログ用ディレクトリを作成（存在しなければ）
os.makedirs("logs", exist_ok=True)

# ZIP ローテート付きログ設定
ZipRotatingLogger.setup(
    log_path="logs/fetch_items.log",
    backupCount=7,   # 必要に応じて変更
)
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
        {"site": "DMM.R18", "service": "ebook", "floor": "comic"}, # コミック
        {"site": "FANZA", "service": "doujin", "floor": "digital_doujin"}, # 同人誌
        {"site": "FANZA", "service": "digital", "floor": "videoc"}, # 動画 素人
        {"site": "DMM.R18", "service": "digital", "floor": "videoa"}, # ビデオ
        {"site": "DMM.R18", "service": "digital", "floor": "anime"}, # アニメ
        {"site": "FANZA", "service": "ebook", "floor": "novel"}, # 美少女ノベル・官能小説
        {"site": "FANZA", "service": "ebook", "floor": "photo"}, # アダルト写真集・雑誌
        {"site": "FANZA", "service": "pcgame", "floor": "digital_pcgame"}, # アダルトPCゲーム
    ]

    has_error = False

    # mega_login()  # 先にログイン

    for target in targets:
        site = target["site"]
        service = target["service"]
        floor = target.get("floor")
        logging.info("[FETCH] site=%s service=%s floor=%s", site, service, floor)

        try:
            top_items = fetch_items(site=site, service=service, floor=floor, offset=1, hits=hits_per_request, min_sample_count=10)
            logging.info("データ取得完了")

            
            
            for item in top_items:
                # 立ち読みデータの取得
                # 立ち読みURLが存在する場合のみ処理
                tachiyomi_url = item.get("tachiyomi", {}).get("URL")  # ← .get を安全化
                # logging.info("立ち読みデータ取得開始")
                tachiyomi_image_paths = []
                if tachiyomi_url:
                    logging.info("立ち読みデータ取得 URL=%s", tachiyomi_url)
                    tachiyomi_image_paths = capture_all_tachiyomi_pages(tachiyomi_url=tachiyomi_url)
                # logging.info("立ち読みデータ取得完了")

                sample_movie_url = item.get("sampleMovieURL_highest")
                # sample_movie_path = ""
                # if sample_movie_url:
                #     logging.info("サンプル動画URL: %s", sample_movie_url)
                #     sample_movie_path = get_sample_movie(sample_movie_url)

                insert_dmm_item(item, tachiyomi_image_paths, sample_movie_url,site=site, service=service, floor=floor)
                logging.info("データ登録完了")

                for image_path in tachiyomi_image_paths:
                    cleanup_file(image_path)

                # cleanup_file(sample_movie_path)
                logging.info("不要ファイル削除完了")

        except Exception as e:
            # logging.error(" Failed to fetch or insert items for floor=%s: %s", floor, str(e))
            logging.error("登録処理に失敗: %s", str(e))
            has_error = True
        # finally :
            

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
