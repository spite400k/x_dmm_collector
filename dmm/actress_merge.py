from typing import Optional

TEXT_FIELDS = ("profile", "career_text", "fanza_activity", "awards")


def merge_supplement_record(
    base_record: dict,
    supplement: Optional[dict],
    *,
    prefer_longer_text: bool = True,
) -> dict:
    if not supplement:
        return base_record

    for key, value in supplement.items():
        if key.startswith("_") or value in (None, ""):
            continue
        if not base_record.get(key):
            base_record[key] = value
        elif prefer_longer_text and key in TEXT_FIELDS:
            if len(str(value)) > len(str(base_record.get(key, ""))):
                base_record[key] = value

    return base_record
