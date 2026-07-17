import os
import logging
import requests
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

from utils.logger import LOG_ENCODING, create_utf8_stream_handler

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/storage.log", encoding=LOG_ENCODING),
        create_utf8_stream_handler(),
    ],
)

# S3 設定（環境変数から取得）
S3_BUCKET = os.environ.get("S3_BUCKET")
S3_BUCKET_3 = os.environ.get("S3_BUCKET_3")
S3_REGION = os.environ.get("S3_REGION", "ap-northeast-1")
S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY")
S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY")

s3_client = boto3.client(
    "s3",
    region_name=S3_REGION,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
)


def _upload_local_image_to_s3(
    filepath: str, content_id: str, index: int, floor: str, bucket: str
) -> str:
    if not bucket:
        logging.error("S3 バケット名が未設定です")
        return ""
    if not os.path.exists(filepath):
        logging.warning("ファイルが存在しません: %s", filepath)
        return ""

    filename = f"{content_id}_{index:02d}{os.path.splitext(filepath)[1]}"
    key = f"{floor}/{content_id}/{filename}"
    logging.info("[UPLOAD] %s", key)

    # 既存チェック
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        logging.info("[SKIP] 既に存在: %s", key)
    except ClientError as e:
        if e.response["Error"]["Code"] != "404":
            logging.error("S3 head_object エラー: %s", e)
            return ""
        # アップロード
        with open(filepath, "rb") as f:
            s3_client.upload_fileobj(
                f, bucket, key, ExtraArgs={"ContentType": "image/jpeg"}
            )
        logging.info("[UPLOADED] %s", key)

    # 署名付きURLを生成（1時間有効）
    try:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=3600,
        )
        return url
    except ClientError as e:
        logging.error("署名付きURL生成失敗: %s", e)
        return ""


def _upload_image_to_s3(
    url: str, content_id: str, index: int, floor: str, bucket: str
) -> str:
    if not bucket:
        logging.error("S3 バケット名が未設定です")
        return ""
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
        s3_client.head_object(Bucket=bucket, Key=key)
        logging.info("[SKIP] 既に存在: %s", key)
    except ClientError as e:
        if e.response["Error"]["Code"] != "404":
            logging.error("S3 head_object エラー: %s", e)
            return ""
        # アップロード
        s3_client.put_object(
            Bucket=bucket, Key=key, Body=response.content, ContentType="image/jpeg"
        )
        logging.info("[UPLOADED] %s", key)

    # 署名付きURLを生成（1時間有効）
    try:
        signed = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=3600,
        )
        return signed
    except ClientError as e:
        logging.error("署名付きURL生成失敗: %s", e)
        return ""


# ---------------------------------------------------------------------
# ローカル画像ファイルを S3 にアップロード（既定バケット S3_BUCKET）
# ---------------------------------------------------------------------
def upload_local_image_to_s3(filepath: str, content_id: str, index: int, floor: str) -> str:
    return _upload_local_image_to_s3(filepath, content_id, index, floor, S3_BUCKET)


# ---------------------------------------------------------------------
# ローカル画像ファイルを S3 にアップロード（S3_BUCKET_3）
# ---------------------------------------------------------------------
def upload_local_image_to_s3_bucket3(
    filepath: str, content_id: str, index: int, floor: str
) -> str:
    return _upload_local_image_to_s3(filepath, content_id, index, floor, S3_BUCKET_3)


# ---------------------------------------------------------------------
# URLから画像を S3 にアップロード（既定バケット S3_BUCKET）
# ---------------------------------------------------------------------
def upload_image_to_s3(url: str, content_id: str, index: int, floor: str) -> str:
    return _upload_image_to_s3(url, content_id, index, floor, S3_BUCKET)


# ---------------------------------------------------------------------
# URLから画像を S3 にアップロード（S3_BUCKET_3）
# ---------------------------------------------------------------------
def upload_image_to_s3_bucket3(url: str, content_id: str, index: int, floor: str) -> str:
    return _upload_image_to_s3(url, content_id, index, floor, S3_BUCKET_3)


# ---------------------------------------------------------------------
# 女優プロフィール画像を S3 にアップロード（公開URLを返す）
# ---------------------------------------------------------------------
S3_ACTRESS_PREFIX = os.environ.get("S3_ACTRESS_PREFIX", "actress")
S3_PUBLIC_BASE_URL = os.environ.get("S3_PUBLIC_BASE_URL", "")


def build_s3_public_url(key: str, bucket: str) -> str:
    base = S3_PUBLIC_BASE_URL.rstrip("/")
    if base:
        return f"{base}/{key}"
    return f"https://{bucket}.s3.{S3_REGION}.amazonaws.com/{key}"


def upload_actress_image_to_s3(
    actress_id: int | str,
    source_url: str,
    *,
    bucket: str | None = None,
) -> str:
    target_bucket = bucket or S3_BUCKET
    if not target_bucket:
        logging.error("S3 バケット名が未設定です")
        return ""
    if not source_url:
        return ""

    key = f"{S3_ACTRESS_PREFIX}/{actress_id}.jpg"
    logging.info("[UPLOAD] actress image %s", key)

    try:
        s3_client.head_object(Bucket=target_bucket, Key=key)
        logging.info("[SKIP] 既に存在: %s", key)
        return build_s3_public_url(key, target_bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] != "404":
            logging.error("S3 head_object エラー: %s", e)
            return ""

    try:
        response = requests.get(
            source_url,
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        if len(response.content) < 1024:
            logging.warning(
                "[SKIP] 画像サイズが小さすぎます actress_id=%s size=%d",
                actress_id,
                len(response.content),
            )
            return ""
    except Exception as e:
        logging.error("女優画像取得失敗 actress_id=%s: %s", actress_id, e)
        return ""

    try:
        s3_client.put_object(
            Bucket=target_bucket,
            Key=key,
            Body=response.content,
            ContentType="image/jpeg",
            CacheControl="public, max-age=31536000, immutable",
        )
        logging.info("[UPLOADED] %s (%d bytes)", key, len(response.content))
    except ClientError as e:
        logging.error("女優画像アップロード失敗 actress_id=%s: %s", actress_id, e)
        return ""

    return build_s3_public_url(key, target_bucket)


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
