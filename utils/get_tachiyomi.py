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
options.add_argument("--disable-blink-features=AutomationControlled")  # bot判定回避
driver = webdriver.Chrome(options=options)

try:
    # 1. DMMトップを開く
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
    except Exception as e:
        logging.warning("年齢認証ボタンが見つからなかった（すでに認証済みかも）")

    # 3. 試し読みページを開く
    logging.info("試し読みページを開く")
    driver.get(tachiyomi_url)

    # 4. iframe / canvas 待機
    iframe = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.TAG_NAME, "iframe"))
    )
    driver.switch_to.frame(iframe)
    logging.info("iframe に切り替え完了")

    # 5. canvas を取得
    canvas = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.TAG_NAME, "canvas"))
    )
    logging.info(f"canvas 見つかった: size={canvas.size}")

    # スクショ保存
    driver.save_screenshot("tachiyomi_page.png")
    logging.info("スクショ保存しました")

    time.sleep(3)

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
