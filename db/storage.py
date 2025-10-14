import requests
import logging
from db.supabase_client import supabase
import os
import logging
from db.supabase_client import supabase

# ログ設定（ファイル + コンソール出力）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/storage.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# ---------------------------------------------------------------------
# ローカル画像ファイルをSupabase Storageにアップロード
# ---------------------------------------------------------------------
def upload_local_image_to_storage(filepath: str, content_id: str, index: int, floor:str, bucket: str = "dmm-images2") -> str:
    """
    ローカルの画像ファイルを Supabase Storage にアップロードする
    """
    try:
        if not os.path.exists(filepath):
            logging.warning("ファイルが存在しません: %s", filepath)
            return ""

        filename = f"{content_id}_{index:02d}{os.path.splitext(filepath)[1]}"
        storage_path = f"{floor}/{content_id}/{filename}"  # フォルダごと格納
        logging.info("[UPLOAD] %s", storage_path)

        # すでに存在する場合はスキップ
        files = supabase.storage.from_(bucket).list(f"{floor}/{content_id}/")
        if any(file["name"] == filename for file in files):
            logging.info("[SKIP] 既に存在: %s", filename)
            return storage_path

        # ローカルファイルを読み込んでアップロード
        with open(filepath, "rb") as f:
            supabase.storage.from_(bucket).upload(
                path=storage_path,
                file=f,
                file_options={"content-type": "image/jpeg"}
            )

        return storage_path

    except Exception as e:
        logging.error("ローカル画像アップロード失敗: %s (%s)", filepath, e)
        return ""
    
# ---------------------------------------------------------------------
# 画像URLをSupabase Storageにアップロード
# ---------------------------------------------------------------------
def upload_image_to_storage(url: str, content_id: str, index: int, bucket: str = "dmm-images2") -> str:
    try:
        # 画像を取得
        response = requests.get(url)
        response.raise_for_status()

        filename = f"{content_id}_{index:02d}.jpg"
        storage_path = f"{content_id}/{filename}"  # フォルダごと格納
        logging.info("[UPLOAD] %s", storage_path)

        # 既存チェック
        files = supabase.storage.from_(bucket).list(f"{content_id}/")
        if any(file["name"] == filename for file in files):
            logging.info("[SKIP] 既に存在: %s", filename)
        else:
            # アップロード
            supabase.storage.from_(bucket).upload(
                path=storage_path,
                file=response.content,
                file_options={"content-type": "image/jpeg"}
            )

        # 公開URLを取得
        public_url = supabase.storage.from_(bucket).get_public_url(storage_path).get("publicUrl")
        return public_url

    except Exception as e:
        logging.error("画像アップロード失敗: %s", e)
        return ""


# ---------------------------------------------------------------------
# テスト用メソッド
# ---------------------------------------------------------------------
def test_storage_upload():
    """
    アップロード系の動作確認用
    """
    test_content_id = "TEST123"

    # 1. ローカルファイルのアップロードテスト
    sample_local_file = "/Users/koonishi/python/x_dmm_collector/utils/temp/page_001.png"  # capture_all_tachiyomi_pages の出力ファイルを想定
    if os.path.exists(sample_local_file):
        result_path = upload_local_image_to_storage(sample_local_file, test_content_id, 1)
        logging.info("[TEST] ローカルファイルアップロード結果: %s", result_path)
    else:
        logging.warning("[TEST] ローカルファイルが存在しないためスキップ: %s", sample_local_file)

    # 2. URLからのアップロードテスト
    sample_url = "https://picsum.photos/300/400"  # ダミー画像API
    result_path = upload_image_to_storage(sample_url, test_content_id, 2)
    logging.info("[TEST] URLアップロード結果: %s", result_path)


# ---------------------------------------------------------------------
# 実行
# ---------------------------------------------------------------------
if __name__ == "__main__":
    test_storage_upload()
