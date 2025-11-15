import os
import time
import boto3
from botocore.exceptions import ClientError
from supabase import create_client, Client

# ==========================
# 環境変数
# ==========================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "dmm-images2")

STORJ_ENDPOINT = os.getenv("STORJ_S3_ENDPOINT")
STORJ_ACCESS_KEY = os.getenv("STORJ_ACCESS_KEY")
STORJ_SECRET_KEY = os.getenv("STORJ_SECRET_KEY")
STORJ_BUCKET = os.getenv("STORJ_BUCKET")

# ==========================
# クライアント作成
# ==========================
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

s3 = boto3.client(
    "s3",
    endpoint_url=STORJ_ENDPOINT,
    aws_access_key_id=STORJ_ACCESS_KEY,
    aws_secret_access_key=STORJ_SECRET_KEY,
    region_name="us-east-1",
)


# ==========================
# MIME タイプ推定
# ==========================
def detect_mime(path: str) -> str:
    ext = path.lower().split(".")[-1]
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")


# ==========================
# Storj に既に存在するかチェック
# ==========================
def storj_exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=STORJ_BUCKET, Key=key)
        return True
    except ClientError:
        return False


# ==========================
# Supabase からファイル取得
# ==========================
def download_supabase(path: str) -> bytes:
    return supabase.storage.from_(SUPABASE_BUCKET).download(path)


# ==========================
# Storj へアップロード（リトライ対応）
# ==========================
def upload_storj(key: str, data: bytes, mime: str, retry=3):
    for attempt in range(1, retry + 1):
        try:
            s3.put_object(
                Bucket=STORJ_BUCKET,
                Key=key,
                Body=data,
                ContentType=mime,
                ContentLength=len(data)   # ← 追加
            )
            return True
        except Exception as e:
            print(f"[ERROR] Upload failed ({attempt}/{retry}): {key}")
            print("  Reason:", e)
            time.sleep(1)

    return False



# ==========================
# 再帰で Supabase の階層を走査
# ==========================
def list_recursive(prefix=""):
    items = []
    queue = [prefix]

    while queue:
        current = queue.pop(0)

        # Supabase Storage のリスト取得
        objs = supabase.storage.from_(SUPABASE_BUCKET).list(current)

        for obj in objs:
            name = obj["name"]
            # パスを連結
            full_path = f"{current}/{name}" if current else name

            # -------------------------
            # フォルダ判定（重要）
            # -------------------------
            # Supabase の仕様：
            # フォルダ → metadata が None、name の末尾が '/'
            # ファイル → metadata に size などが入る
            # -------------------------
            is_folder = (obj.get("metadata") is None)

            if is_folder:
                # comic/
                # comic/12345/
                queue.append(full_path)
            else:
                # comic/12345/filename.png
                items.append(full_path)

    return items



# ==========================
# 移行メイン処理
# ==========================
def migrate():
    print("📁 Supabase Storage → Storj Migration")
    print(f"Bucket: {SUPABASE_BUCKET}")
    print("=" * 50)

    # 全ファイル一覧を取得（再帰）
    all_files = list_recursive("")
    total = len(all_files)

    print(f"Total files found: {total}")
    print("=" * 50)

    migrated = 0
    skipped = 0
    failed = 0

    for i, path in enumerate(all_files, start=1):
        print(f"[{i}/{total}] {path}")

        # ✨ 差分移行：Storj にすでに存在するならスキップ
        if storj_exists(path):
            print("  → Skipped (already exists)")
            skipped += 1
            continue

        # Supabase からダウンロード
        try:
            file_bytes = download_supabase(path)
        except Exception as e:
            print("  ✖ Failed to download:", e)
            failed += 1
            continue

        # MIME 推定
        mime = detect_mime(path)

        # Storj へアップロード
        ok = upload_storj(path, file_bytes, mime)
        if ok:
            print("  ✔ Uploaded")
            migrated += 1
        else:
            print("  ✖ Upload failed")
            failed += 1

    print("\n===== Migration Summary =====")
    print(f"✔ Migrated: {migrated}")
    print(f"↩ Skipped: {skipped}")
    print(f"✖ Failed : {failed}")
    print("=============================")


if __name__ == "__main__":
    migrate()
