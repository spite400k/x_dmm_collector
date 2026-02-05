import os
import logging
import requests
import boto3
from botocore.exceptions import ClientError

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/storage.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# S3 設定（環境変数から取得）
S3_BUCKET = os.environ.get("S3_BUCKET_3")
S3_REGION = os.environ.get("S3_REGION", "ap-northeast-1")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY")

s3_client = boto3.client(
    "s3",
    region_name=S3_REGION,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
)

# ---------------------------------------------------------------------
# ローカル画像ファイルを S3 にアップロード
# ---------------------------------------------------------------------
def upload_local_image_to_s3(filepath: str, content_id: str, index: int, floor: str) -> str:
    if not os.path.exists(filepath):
        logging.warning("ファイルが存在しません: %s", filepath)
        return ""

    filename = f"{content_id}_{index:02d}{os.path.splitext(filepath)[1]}"
    key = f"{floor}/{content_id}/{filename}"
    logging.info("[UPLOAD] %s", key)

    # 既存チェック
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        logging.info("[SKIP] 既に存在: %s", key)
    except ClientError as e:
        if e.response['Error']['Code'] != '404':
            logging.error("S3 head_object エラー: %s", e)
            return ""
        # アップロード
        with open(filepath, "rb") as f:
            s3_client.upload_fileobj(f, S3_BUCKET, key, ExtraArgs={"ContentType": "image/jpeg"})
        logging.info("[UPLOADED] %s", key)

    # 署名付きURLを生成（1時間有効）
    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=3600
        )
        return url
    except ClientError as e:
        logging.error("署名付きURL生成失敗: %s", e)
        return ""

# ---------------------------------------------------------------------
# URLから画像を S3 にアップロード
# ---------------------------------------------------------------------
def upload_image_to_s3(url: str, content_id: str, index: int, floor: str) -> str:
    try:
        response = requests.get(url)
        response.raise_for_status()
    except Exception as e:
        logging.error("画像取得失敗: %s", e)
        return ""

    filename = f"{content_id}_{index:02d}.jpg"
    key = f"{floor}/{content_id}/{filename}"
    logging.info("[UPLOAD] %s", key)

    # 既存チェック
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
        logging.info("[SKIP] 既に存在: %s", key)
    except ClientError as e:
        if e.response['Error']['Code'] != '404':
            logging.error("S3 head_object エラー: %s", e)
            return ""
        # アップロード
        s3_client.put_object(Bucket=S3_BUCKET, Key=key, Body=response.content, ContentType="image/jpeg")
        logging.info("[UPLOADED] %s", key)

    # 署名付きURLを生成（1時間有効）
    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=3600
        )
        return url
    except ClientError as e:
        logging.error("署名付きURL生成失敗: %s", e)
        return ""

# ---------------------------------------------------------------------
# テスト用メソッド
# ---------------------------------------------------------------------
def test_s3_upload():
    test_content_id = "TEST123"
    floor = "comic"

    # 1. ローカルファイルアップロードテスト
    sample_local_file = "/Users/koonishi/python/x_dmm_collector/utils/temp/page_001.png"
    if os.path.exists(sample_local_file):
        result_url = upload_local_image_to_s3(sample_local_file, test_content_id, 1, floor)
        logging.info("[TEST] ローカルファイルURL: %s", result_url)
    else:
        logging.warning("[TEST] ローカルファイルが存在しないためスキップ")

    # 2. URLアップロードテスト
    sample_url = "https://picsum.photos/300/400"
    result_url = upload_image_to_s3(sample_url, test_content_id, 2, floor)
    logging.info("[TEST] URLアップロード結果: %s", result_url)

# ---------------------------------------------------------------------
# 実行
# ---------------------------------------------------------------------
if __name__ == "__main__":
    test_s3_upload()
