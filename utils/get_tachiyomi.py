import time
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ---------------------
# ログ設定
# ---------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

tachiyomi_url = "https://book.dmm.co.jp/tachiyomi/?cid=FRNfXRNVFW1RAQxaAQZUVg4KQlcACFQIUE5EDl0VClQMBllNB1o*UFcKWhRHVwVfCBxZW1kEVQ__&lin=1&sd=0"

# ---------------------
# Chrome起動
# ---------------------
options = Options()
options.add_argument("--disable-blink-features=AutomationControlled")
# options.add_argument("--headless")
driver = webdriver.Chrome(options=options)

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

    print(driver.page_source[:100000])  # ページHTMLの先頭2,000文字だけ出す

    # iframe を探す
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    if iframes:
        driver.switch_to.frame(iframes[0])
        logging.info("iframe に切り替え完了")
        # print(driver.page_source[:10000])  # ページHTMLの先頭2,000文字だけ出す
    else:
        logging.info("iframe は存在しなかった → そのまま進む")

    # canvas が描画されるまで待機
    canvas = None
    for _ in range(10):  # 最大10回チェック
        try:
            canvas = driver.find_element(By.TAG_NAME, "canvas")
            if canvas.size["width"] > 0:
                break
        except:
            pass
        time.sleep(1)

    if canvas and canvas.size["width"] > 0:
        logging.info(f"canvas 見つかった: size={canvas.size}")
        driver.save_screenshot("tachiyomi_page.png")
        logging.info("スクショ保存しました")
    else:
        logging.error("canvas が見つからない or 描画されていない")
except Exception as e:
    logging.error(f"処理中にエラー: {e}")

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
