def insert_genres_to_master(genres_raw: list):
    for g in genres_raw:
        genre_id = g["id"]
        name = g["name"]
        exists = supabase.table("mst_genre").select("id").eq("id", genre_id).execute()
        if not exists.data:
            supabase.table("mst_genre").insert({"id": genre_id, "name": name}).execute()
            logging.info("[GENRE INSERT] %s (%d)", name, genre_id)
