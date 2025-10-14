import os
import subprocess
import logging
import platform
from dotenv import load_dotenv
import requests
import traceback

# ---------------------------------------------------------------------
# ログ設定（ファイル + コンソール、DEBUGレベルまで出力）
# ---------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/mega_storage.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# ---------------------------------------------------------------------
# OSごとの MEGAcmd 実行ファイルパス
# ---------------------------------------------------------------------
def get_mega_cmd_path(command: str) -> str:
    system = platform.system()
    if system == "Windows":
        # Windows は .bat ファイルをフルパス指定
        base = r"C:\Users\kazuk\AppData\Local\MEGAcmd"  # ← 実際のパスに置き換え
        path = os.path.join(base, f"{command}.bat")
        logging.debug("Using Windows MEGA command path: %s", path)
        return path
    else:
        # Linux / macOS
        logging.debug("Using Linux/macOS MEGA command path: %s", command)
        return command

# ---------------------------------------------------------------------
# サブプロセス実行ラッパー（標準出力・標準エラーをログに）
# ---------------------------------------------------------------------
def run_subprocess(cmd_list, check=True):
    try:
        logging.debug("Running command: %s", " ".join(cmd_list))
        result = subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            check=check,
            shell=False
        )
        logging.debug("stdout: %s", result.stdout.strip())
        if result.stderr.strip():
            logging.warning("stderr: %s", result.stderr.strip())
        return result
    except subprocess.CalledProcessError as e:
        logging.error("Subprocess failed: %s", " ".join(cmd_list))
        logging.error("Return code: %s", e.returncode)
        logging.error("stdout: %s", e.stdout)
        logging.error("stderr: %s", e.stderr)
        raise
    except Exception as e:
        logging.error("Subprocess exception: %s", e)
        logging.debug(traceback.format_exc())
        raise

# ---------------------------------------------------------------------
# MEGAログイン
# ---------------------------------------------------------------------
def mega_login():
    load_dotenv()
    email = os.getenv("MEGA_EMAIL")
    password = os.getenv("MEGA_PASSWORD")
    if not email or not password:
        raise ValueError("MEGA_EMAIL / MEGA_PASSWORD が環境変数に設定されていません")
    logging.info("MEGAログイン開始")
    run_subprocess([get_mega_cmd_path("mega-login"), email, password])
    logging.info("MEGAログイン成功 ✅")

# ---------------------------------------------------------------------
# MEGAログアウト
# ---------------------------------------------------------------------
def mega_logout():
    logging.info("MEGAログアウト開始")
    run_subprocess([get_mega_cmd_path("mega-logout")])
    logging.info("MEGAログアウト完了 ✅")

# ---------------------------------------------------------------------
# ローカル画像アップロード（-c で階層自動作成）
# ---------------------------------------------------------------------
def upload_local_image_to_mega(filepath: str, content_id: str, index: int, floor: str) -> str:
    try:
        if not os.path.exists(filepath):
            logging.warning("ファイルが存在しません: %s", filepath)
            return ""

        remote_dir = f"/{floor}/{content_id}"
        filename = f"{content_id}_{index:02d}{os.path.splitext(filepath)[1]}"

        # アップロード（-c で階層自動作成）
        logging.info("[UPLOAD] %s -> %s", filepath, f"{remote_dir}/{filename}")
        run_subprocess([
            get_mega_cmd_path("mega-put"),
            "-c",  # <- 親フォルダ自動作成
            filepath,
            f"{remote_dir}/{filename}"
        ])
        logging.info("[UPLOAD OK] %s", f"{remote_dir}/{filename}")
        return f"{remote_dir}/{filename}"

    except Exception as e:
        logging.error("MEGAアップロード失敗: %s", e)
        logging.debug(traceback.format_exc())
        return ""


# ---------------------------------------------------------------------
# 複数ファイルアップロードサンプル
# ---------------------------------------------------------------------
def upload_files_local_image(file_list, content_id, floor):

    uploaded_paths = []
    try:
        mega_login()  # 先にログイン

        if isinstance(file_list, list):
            for i, file in enumerate(file_list, start=1):
                storage_path = upload_local_image_to_mega(file, content_id, i, floor)
                uploaded_paths.append(storage_path)
        elif isinstance(file_list, str):
            # 単一ファイルの場合
            storage_path = upload_local_image_to_mega(file_list, content_id, 1, floor)
            uploaded_paths.append(storage_path)
        else:
            logging.warning("file_list が list または str ではありません: %s", type(file_list))
            
        return uploaded_paths
    finally:
        mega_logout()  # 最後にログアウト
        
# ---------------------------------------------------------------------
# URL画像アップロード（-c で階層自動作成）
# ---------------------------------------------------------------------
def upload_image_to_mega(url: str, content_id: str, index: int, floor: str) -> str:
    temp_file = f"temp_{content_id}_{index:02d}.jpg"
    try:
        mega_login()
        logging.info("[DOWNLOAD] URL: %s", url)
        response = requests.get(url)
        response.raise_for_status()

        with open(temp_file, "wb") as f:
            f.write(response.content)
        logging.info("[DOWNLOAD OK] %s", temp_file)

        result = upload_local_image_to_mega(temp_file, content_id, index, floor)
        return result

    except Exception as e:
        logging.error("URL画像アップロード失敗: %s", e)
        logging.debug(traceback.format_exc())
        return ""
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
            logging.debug("[TEMP FILE REMOVED] %s", temp_file)
        try:
            mega_logout()
        except Exception as e:
            logging.warning("ログアウト時にエラー: %s", e)
            logging.debug(traceback.format_exc())

# ---------------------------------------------------------------------
# 複数ファイルアップロードサンプル
# ---------------------------------------------------------------------
def upload_files_buffer(file_list, content_id, floor):
    try:
        mega_login()  # 先にログイン

        uploaded_paths = []
        for i, file in enumerate(file_list, start=1):
            storage_path = upload_image_to_mega(file, content_id, i, floor)
            uploaded_paths.append(storage_path)

        return uploaded_paths
    finally:
        mega_logout()  # 最後にログアウト