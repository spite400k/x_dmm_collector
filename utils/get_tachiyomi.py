import os
import time
import logging
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException

# ---------------------
# ログ設定
# ---------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def capture_all_tachiyomi_pages(tachiyomi_url: str):
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    TEMP_DIR = os.path.join(BASE_DIR, "temp")
    os.makedirs(TEMP_DIR, exist_ok=True)

    options = Options()
    # options.add_argument("--headless")  # 必要に応じて
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=600,2000")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        logging.info("DMMトップページを開く")
        driver.get("https://www.dmm.co.jp/top/")

        # 年齢認証ボタン
        try:
            button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.LINK_TEXT, "はい"))
            )
            button.click()
            logging.info("年齢認証成功")
            time.sleep(2)
        except:
            logging.info("年齢認証不要 or 既認証済み")

        logging.info("試し読みページを開く")
        driver.get(tachiyomi_url)
        time.sleep(5)

        images = []
        page_idx = 1

        # viewer要素にフォーカス
        viewer = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "viewer"))
        )
        viewer.click()
        actions = ActionChains(driver)

        while True:
            try:
                # canvas取得
                canvas = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#viewport0 canvas"))
                )
                screenshot_path = os.path.join(TEMP_DIR, f"page_{page_idx:03}.png")
                canvas.screenshot(screenshot_path)
                images.append(screenshot_path)
                logging.info(f"保存: {screenshot_path}")

                # キーボードで次ページへ
                actions.send_keys(Keys.ARROW_LEFT).perform()
                page_idx += 1
                time.sleep(1)  # ページ描画待ち

            except NoSuchElementException:
                logging.warning("canvas取得失敗 → 終了")
                break

            # 適宜、最後のページ判定（例：canvasが変わらなければ終了）を追加可能

        logging.info(f"合計 {len(images)} ページを保存しました")
        return images

    finally:
        driver.quit()


if __name__ == "__main__":
    test_url = "https://book.dmm.co.jp/tachiyomi/?cid=FRNfXRNVFW1RAQxaBwFUVgMLU1gAClAPVU5EDl0VClQMBllNB1o*UFcKWhRHVwVfCBxZW1kEVQ__&lin=1&sd=0"
    capture_all_tachiyomi_pages(test_url)
