import os
import subprocess
import logging
import platform
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
        base = r"C:\Users\kazuk\AppData\Local\MEGAcmd"
        path = os.path.join(base, f"{command}.exe")
        logging.debug("Using Windows MEGA command path: %s", path)
        return path
    else:
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
            check=check
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
# ローカル画像アップロード
# ---------------------------------------------------------------------
def upload_local_image_to_mega(filepath: str, content_id: str, index: int, floor: str) -> str:
    try:
        if not os.path.exists(filepath):
            logging.warning("ファイルが存在しません: %s", filepath)
            return ""

        remote_dir = f"/Root/{floor}/{content_id}"
        filename = f"{content_id}_{index:02d}{os.path.splitext(filepath)[1]}"

        # フォルダ作成
        logging.info("[MKDIR] %s", remote_dir)
        run_subprocess([get_mega_cmd_path("mega-mkdir"), remote_dir], check=False)

        # アップロード
        logging.info("[UPLOAD] %s -> %s", filepath, f"{remote_dir}/{filename}")
        run_subprocess([get_mega_cmd_path("mega-put"), filepath, f"{remote_dir}/{filename}"])
        logging.info("[UPLOAD OK] %s", f"{remote_dir}/{filename}")
        return f"{remote_dir}/{filename}"

    except Exception as e:
        logging.error("MEGAアップロード失敗: %s", e)
        logging.debug(traceback.format_exc())
        return ""

# ---------------------------------------------------------------------
# URL画像アップロード
# ---------------------------------------------------------------------
def upload_image_to_mega(url: str, content_id: str, index: int, floor: str) -> str:
    try:
        logging.info("[DOWNLOAD] URL: %s", url)
        response = requests.get(url)
        response.raise_for_status()

        temp_file = f"temp_{content_id}_{index:02d}.jpg"
        with open(temp_file, "wb") as f:
            f.write(response.content)
        logging.info("[DOWNLOAD OK] %s", temp_file)

        result = upload_local_image_to_mega(temp_file, content_id, index, floor)

        os.remove(temp_file)
        logging.debug("[TEMP FILE REMOVED] %s", temp_file)
        return result

    except Exception as e:
        logging.error("URL画像アップロード失敗: %s", e)
        logging.debug(traceback.format_exc())
        return ""
