from dmm.dmm_api import fetch_items
from db.trn_dmm_items_repository import insert_dmm_item

def main():
    site = "FANZA"
    service = "doujin"
    floor = "digital_doujin"
    items = fetch_items(site=site, service=service, floor=floor, offset=5, hits=10)

    for item in items:
        insert_dmm_item(item)


if __name__ == "__main__":
    main()
