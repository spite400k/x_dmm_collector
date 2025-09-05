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
    # options.add_argument("--headless")  # 必要に応じてコメント解除
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1200,2000")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        logging.info("DMMトップページを開く")
        driver.get("https://www.dmm.co.jp/top/")

        # 年齢認証ボタンを押す
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

        print(driver.page_source[:100000])  # ページHTMLの先頭2,000文字だけ出す

        images = []
        page_idx = 1

        # まず #viewport0 内の canvas を探す（現行ページ用）
        try:
            canvas = driver.find_element(By.CSS_SELECTOR, "#viewport0 canvas")
            screenshot_path = os.path.join(TEMP_DIR, f"page_{page_idx}.png")
            canvas.screenshot(screenshot_path)
            images.append(screenshot_path)
            logging.info(f"保存: {screenshot_path}")
        except NoSuchElementException:
            logging.info("viewport0 canvas が見つからないので iframe を探索します")
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
                return images  # 空リストを返す

            driver.switch_to.frame(canvas_frame)
            canvas = driver.find_element(By.TAG_NAME, "canvas")
            screenshot_path = os.path.join(TEMP_DIR, f"page_{page_idx}.png")
            canvas.screenshot(screenshot_path)
            images.append(screenshot_path)
            logging.info(f"保存: {screenshot_path}")

        # 次ページがある場合、ループしてスクショを撮る
        while True:
            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, ".nextButton")  # 要調整
                if "disabled" in next_btn.get_attribute("class"):
                    logging.info("最後のページに到達")
                    break
                next_btn.click()
                page_idx += 1
                time.sleep(1)
                # canvas を再取得
                canvas = driver.find_element(By.CSS_SELECTOR, "#viewport0 canvas")
                screenshot_path = os.path.join(TEMP_DIR, f"page_{page_idx}.png")
                canvas.screenshot(screenshot_path)
                images.append(screenshot_path)
                logging.info(f"保存: {screenshot_path}")
            except NoSuchElementException:
                logging.info("次ページボタンが見つからないので終了")
                break
            except ElementClickInterceptedException:
                logging.warning("ボタンクリック妨害 → 再試行")
                time.sleep(1)
                continue

        logging.info(f"合計 {len(images)} ページを保存しました")
        return images

    finally:
        driver.quit()


if __name__ == "__main__":
    test_url = "https://book.dmm.co.jp/tachiyomi/?cid=XXXX&lin=1&sd=0"
    capture_all_tachiyomi_pages(test_url)
