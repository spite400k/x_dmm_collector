import os
import subprocess
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def upload_local_image_to_mega(filepath: str, content_id: str, index: int, floor: str) -> str:
    try:
        if not os.path.exists(filepath):
            logging.warning("ファイルが存在しません: %s", filepath)
            return ""

        remote_dir = f"/Root/{floor}/{content_id}"
        filename = f"{content_id}_{index:02d}{os.path.splitext(filepath)[1]}"

        # フォルダ作成
        subprocess.run(["mega-mkdir", remote_dir], check=False)

        # アップロード
        subprocess.run(["mega-put", filepath, f"{remote_dir}/{filename}"], check=True)

        logging.info("[UPLOAD OK] %s", f"{remote_dir}/{filename}")
        return f"{remote_dir}/{filename}"

    except Exception as e:
        logging.error("MEGAアップロード失敗: %s", e)
        return ""

def upload_image_to_mega(url: str, content_id: str, index: int, floor: str) -> str:
    try:
        response = requests.get(url)
        response.raise_for_status()

        temp_file = f"temp_{content_id}_{index:02d}.jpg"
        with open(temp_file, "wb") as f:
            f.write(response.content)

        result = upload_local_image_to_mega(temp_file, content_id, index, floor)
        os.remove(temp_file)
        return result

    except Exception as e:
        logging.error("URLアップロード失敗: %s", e)
        return ""
