import requests
import logging
from db.supabase_client import supabase

def upload_image_to_storage(url: str, content_id: str, index: int, bucket: str = "dmm-images2") -> str:
    try:
        response = requests.get(url)
        response.raise_for_status()

        filename = f"{content_id}_{index:02d}.jpg"
        storage_path = f"{content_id}/{filename}"  # フォルダごと格納
        logging.info("[UPLOAD] %s", storage_path)

        # すでに存在する場合は上書きせずスキップ（必要に応じて変更）
        files = supabase.storage.from_(bucket).list(f"{content_id}/")
        if any(file["name"] == filename for file in files):
            logging.info("[SKIP] 既に存在: %s", filename)
            return storage_path

        supabase.storage.from_(bucket).upload(
            path=storage_path,
            file=response.content,
            file_options={"content-type": "image/jpeg"}
        )

        return storage_path

    except Exception as e:
        logging.warning("[ERROR] 画像アップロード失敗: %s (%s)", url, e)
        return ""
