def update_dmm_item(content_id: str, new_data: dict):
    """Supabase内の既存レコードを更新"""
    from supabase import create_client
    import os

    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )

    supabase.table("trn_dmm_items").update({
        "title": new_data.get("title"),
        "item_url": new_data.get("URL"),
        "review_count": new_data.get("review", {}).get("count"),
        "review_average": new_data.get("review", {}).get("average"),
        "updated_at": "now()"
    }).eq("content_id", content_id).execute()
