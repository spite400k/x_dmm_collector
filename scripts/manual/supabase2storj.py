import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# --- 追加インポート ---
import os
import time
import io
import logging
import boto3
import botocore
from botocore.config import Config
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


# --- デバッグ（ヘッダ確認用） ---
ENABLE_BOTO_DEBUG = False
if ENABLE_BOTO_DEBUG:
    # botocore の HTTP レベルのやり取りを出す（ヘッダ確認に便利）
    logging.basicConfig(level=logging.DEBUG)
    boto3.set_stream_logger('botocore', level='DEBUG')

# --- boto3/botocore バージョン確認（任意出力） ---
try:
    import boto3 as _b3, botocore as _bc
    print("boto3", _b3.__version__, "botocore", _bc.__version__)
except Exception:
    pass

# --- client 初期化（必ず signature v4 を指定する） ---
_s3_config = Config(signature_version="s3v4", s3={'addressing_style': 'virtual'})
s3 = boto3.client(
    "s3",
    endpoint_url=STORJ_ENDPOINT,                 # 例: https://gateway.storjshare.io
    aws_access_key_id=STORJ_ACCESS_KEY,
    aws_secret_access_key=STORJ_SECRET_KEY,
    region_name="us-east-1",                     # Storj では固定で問題ないことが多い
    config=_s3_config
)

# --- download_supabase を bytes 確実返却に強化 ---

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


def download_supabase(path: str) -> bytes:
    """
    Supabase の download が streaming / bytes のどちらを返しても
    常に bytes を返すようにする。
    """
    try:
        res = supabase.storage.from_(SUPABASE_BUCKET).download(path)

        # supabase-py のレスポンスが streaming-like (has read) の場合
        if hasattr(res, "read"):
            data = res.read()
        else:
            data = res

        # memoryview / bytearray などの可能性を潰す
        if isinstance(data, memoryview):
            data = data.tobytes()
        elif isinstance(data, bytearray):
            data = bytes(data)
        elif not isinstance(data, (bytes, bytearray)):
            # 最後の手段で bytes() に詰める
            data = bytes(data)

        # 最低限のチェック
        if not isinstance(data, (bytes, bytearray)):
            raise RuntimeError("download_supabase: data is not bytes-like")

        return bytes(data)

    except Exception as e:
        # 呼び出し元で扱いやすいよう例外を投げる
        raise RuntimeError(f"Supabase download failed ({path}): {e}")

# --- upload_storj を安定版に置換 ---
def upload_storj(key: str, data: bytes, mime: str, retry=3):
    """
    put_object を使い、必ず ContentLength を明示して送る実装。
    Storj（S3互換）では署名 v4 + Content-Length が重要。
    """
    # sanity
    if not isinstance(data, (bytes, bytearray)):
        raise RuntimeError("upload_storj: data must be bytes")

    content_length = len(data)
    # 追加の ExtraArgs / Metadata があればここで作る
    extra_args = {
        "ContentType": mime,
        # "Metadata": {"source": "supabase-migrate"}  # 必要なら付ける
    }

    for attempt in range(1, retry + 1):
        try:
            # ※ここで Body=bytes を渡し、ContentLength を明示する
            resp = s3.put_object(
                Bucket=STORJ_BUCKET,
                Key=key,
                Body=data,
                ContentLength=content_length,
                **extra_args
            )
            # HTTP ステータスのチェック（念のため）
            # boto3 の put_object は通常例外を投げるが念のためログ確認
            return True

        except ClientError as e:
            # 失敗の理由を詳細に表示
            print(f"[ERROR] Upload failed ({attempt}/{retry}): {key}")
            print("  boto3 ClientError:", e)
            # 401/403 系なら認証関連の可能性が高い
            # MissingContentLength の場合は HTTP 層でヘッダが付いていないことを示す
            # リトライ前に短い待ち
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR] Upload failed ({attempt}/{retry}): {key}")
            print("  Reason:", e)
            time.sleep(1)

    return False

# --- ヘルプ: 設定・環境チェック関数（実行前に一度呼ぶことを推奨） ---
def sanity_checks():
    errors = []
    if not SUPABASE_URL:
        errors.append("SUPABASE_URL is empty")
    if not SUPABASE_SERVICE_KEY:
        errors.append("SUPABASE_SERVICE_KEY is empty")
    if not STORJ_ENDPOINT:
        errors.append("STORJ_S3_ENDPOINT is empty")
    if not STORJ_ACCESS_KEY or not STORJ_SECRET_KEY:
        errors.append("STORJ access key/secret missing")
    if not STORJ_BUCKET:
        errors.append("STORJ_BUCKET is empty")

    # boto3 / botocore のバージョン確認推奨
    try:
        import boto3 as _b3, botocore as _bc
        v_b3 = tuple(map(int, _b3.__version__.split(".")[:2]))
        v_bc = tuple(map(int, _bc.__version__.split(".")[:2]))
        # 例: 古すぎる場合は注意喚起（任意）
        if v_b3 < (1, 26) or v_bc < (1, 29):
            print("Warning: boto3/botocore version may be old. Consider `pip install -U boto3 botocore`.")
    except Exception:
        pass

    if errors:
        raise RuntimeError("Sanity check failed: " + "; ".join(errors))

# --- 実行前のワンライン（必要なら migrate の冒頭で呼ぶ） ---
# sanity_checks()

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

    sanity_checks()
    
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
