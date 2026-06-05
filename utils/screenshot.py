import os
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs

def save_debug_files(driver, product_url, prefix="review"):

    # フォルダ作成
    os.makedirs("debug/html", exist_ok=True)
    os.makedirs("debug/screenshots", exist_ok=True)

    # content_id抽出
    parsed = urlparse(product_url)
    query = parse_qs(parsed.query)
    content_id = query.get("id", ["unknown"])[0]

    # タイムスタンプ
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    base_name = f"{prefix}_{content_id}_{timestamp}"

    # 📸 スクショ保存
    screenshot_path = f"debug/screenshots/{base_name}.png"
    # driver.save_screenshot(screenshot_path)

    # 📝 HTML保存
    html_path = f"debug/html/{base_name}.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(driver.page_source)

    print(f"✅ Debug保存完了:")
    print(f"   screenshot → {screenshot_path}")
    print(f"   html       → {html_path}")
