import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException

# ---------------------
# ログ設定
# ---------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def capture_all_tachiyomi_pages(tachiyomi_url: str):
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TEMP_DIR = os.path.join(BASE_DIR, "temp")
    os.makedirs(TEMP_DIR, exist_ok=True)

    options = Options()
    # options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1200,2000")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        logging.info("DMMトップページを開く")
        driver.get("https://www.dmm.co.jp/top/")

        # 2. 年齢認証（「はい、18歳以上です」ボタンを押す）
        logging.info("年齢認証ボタンを探す")
        try:
            button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "はい"))
            )
            button.click()
            logging.info("年齢認証に成功")
            time.sleep(2)
        except:
            logging.info("年齢認証ボタンなし（すでに認証済み）")

        # 試し読みページへ
        logging.info("試し読みページを開く")
        driver.get(tachiyomi_url)
        time.sleep(5)

        # iframe をループして canvas があるものを探す
        canvas_frame = None
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        logging.info(f"iframe の数: {len(iframes)}")
        for idx, f in enumerate(iframes):
            driver.switch_to.frame(f)
            canvases = driver.find_elements(By.TAG_NAME, "canvas")
            if canvases:
                logging.info(f"canvas を発見した iframe index: {idx}")
                canvas_frame = f
                break
            driver.switch_to.default_content()

        if not canvas_frame:
            logging.error("試し読みの canvas がある iframe が見つからない")
            return []

        driver.switch_to.frame(canvas_frame)
        images = []
        page_idx = 1

        while True:
            # canvas を取得
            canvas = driver.find_element(By.TAG_NAME, "canvas")
            screenshot_path = os.path.join(TEMP_DIR, f"page_{page_idx}.png")
            canvas.screenshot(screenshot_path)
            images.append(screenshot_path)
            logging.info(f"保存: {screenshot_path}")

            # 次ページボタンを探してクリック
            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, ".nextButton")  # 要セレクタ調整
                if "disabled" in next_btn.get_attribute("class"):
                    logging.info("最後のページに到達")
                    break
                next_btn.click()
                page_idx += 1
                time.sleep(1)  # ページ描画待機
            except NoSuchElementException:
                logging.info("次ページボタンが見つからないので終了")
                break
            except ElementClickInterceptedException:
                logging.warning("ボタンクリックが妨害されました。少し待機して再試行")
                time.sleep(1)
                continue

        logging.info(f"合計 {len(images)} ページを保存しました")
        return images

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
    test_url = "https://book.dmm.co.jp/tachiyomi/?cid=XXXX&lin=1&sd=0"
    capture_all_tachiyomi_pages(test_url)
