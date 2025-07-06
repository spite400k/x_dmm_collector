from db.supabase_client import supabase

def insert_dmm_item(item: dict, site:str ,service: str, floor: str):
    image_urls = item.get("sampleImageURL", {}).get("large", [])
    data = {
        "title": item.get("title"),
        "image_urls": image_urls,
        "affiliate_url": item.get("affiliateURL"),
        "site":site,
        "service": service,
        "floor": floor,
        "item_id": item.get("cid")
    }
    exists = supabase.table("trn_dmm_items").select("id").eq("item_id", item.get("cid")).execute()
    if exists.data:
        print(f"[SKIP] Duplicate item: {item.get('title')}")
        return
    supabase.table("trn_dmm_items").insert(data).execute()
    print(f"[OK] Inserted item: {item.get('title')}")
