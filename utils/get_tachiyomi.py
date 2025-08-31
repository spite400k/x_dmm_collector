import os
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time

def fetch_sample_images_from_tachiyomi(tachiyomi_url: str):
    """
    Tachiyomiの試し読みページをSeleniumで開き、画面キャプチャを保存
    """
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TEMP_DIR = os.path.join(BASE_DIR, "temp")
    os.makedirs(TEMP_DIR, exist_ok=True)
    # os.makedirs(save_dir, exist_ok=True)

    # Chromeオプション
    options = Options()
    options.add_argument("--headless")  # ヘッドレスモード
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1200,2000")  # 画面サイズ調整

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        logging.info(f"ページを開く: {tachiyomi_url}")
        driver.get(tachiyomi_url)
        driver.add_cookie({"name": "age_check_done", "value": "1"})
        driver.add_cookie({"name": "over18", "value": "yes"})
        driver.get(tachiyomi_url)  # 再度アクセスすれば直接読める
        time.sleep(3)  # ページが完全に読み込まれるまで待機

        # ページ内の画像要素を取得
        pages = driver.find_elements(By.CSS_SELECTOR, "img")  # 必要に応じてセレクタを変更
        image_paths = []

        for idx, page in enumerate(pages, start=1):
            screenshot_path = os.path.join(TEMP_DIR, f"page_{idx}.png")
            # 画像要素だけをスクリーンショット
            page.screenshot(screenshot_path)
            image_paths.append(screenshot_path)

        logging.info(f"保存したページ数: {len(image_paths)}")
        return image_paths

    finally:
        driver.quit()


# def download_tachiyomi_images(image_urls, save_dir=SAVE_DIR):
#     """
#     画像をダウンロードして保存
#     """
#     for i, url in enumerate(image_urls, 1):
#         filename = f"page_{i:03}.jpg"
#         path = os.path.join(save_dir, filename)
#         logging.info(f"ダウンロード: {url} → {path}")
#         try:
#             r = requests.get(url, stream=True)
#             r.raise_for_status()
#             with open(path, "wb") as f:
#                 for chunk in r.iter_content(1024):
#                     f.write(chunk)
#         except Exception as e:
#             logging.error(f"失敗: {e}")

if __name__ == "__main__":
    # ← サンプル用、実際には商品ページから自動で拾ってくる想定
    tachiyomi_url = "https://book.dmm.co.jp/tachiyomi/?cid=FRNfXRNVFW1RAQxTBAJWVhEJRUIAAVQLVk5EDl0VClQMBllNB1o*UFcKWhRHVwVfCBxZW1kEVQ__&lin=1&sd=0"
    
    # sample_urls = fetch_sample_images_from_tachiyomi(tachiyomi_url)
    # download_images(sample_urls)
    logging.info("試し読み画像ダウンロード完了！")
