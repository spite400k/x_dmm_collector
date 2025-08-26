import os
import re
import requests
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SAVE_DIR = "dmm_samples"
os.makedirs(SAVE_DIR, exist_ok=True)


def fetch_sample_images_from_tachiyomi(cid: str):
    """
    試し読みビューアの内部APIから画像URLリストを取得
    """
    session = requests.Session()
    session.cookies.set("age_check_done", "1", domain=".dmm.co.jp")
    session.cookies.set("ckcy", "1", domain=".dmm.co.jp")

    # ビューアの内部API (※ cid が作品ID)
    api_url = f"https://book.dmm.co.jp/api/publus/viewer/?cid={cid}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": f"https://book.dmm.co.jp/detail/{cid}/"
    }

    logging.info("API取得: %s", api_url)
    r = session.get(api_url, headers=headers)
    # r.raise_for_status()

    data = r.json()

    # ページ配列を探索
    image_urls = []
    for page in data.get("result", {}).get("pages", []):
        url = page.get("src")
        if url and url.endswith(".jpg"):
            image_urls.append(url)

    logging.info("取得したページ画像数: %d", len(image_urls))
    return image_urls


def download_tachiyomi_images(image_urls):
    for i, url in enumerate(image_urls, 1):
        filename = f"page_{i:03}.jpg"
        path = os.path.join(SAVE_DIR, filename)
        logging.info("DL: %s → %s", url, path)

        try:
            r = requests.get(url, stream=True)
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
        except Exception as e:
            logging.error("失敗: %s", e)


if __name__ == "__main__":
    cid = "b202aoota01012"  # 作品ID
    urls = fetch_image_urls_from_tachiyomi(cid)
    download_images(urls)
