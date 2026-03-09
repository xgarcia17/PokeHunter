from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import requests


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET_NAME = "pokemon-images"

DATASET_ROOT = Path("identification/dataset_comp/raw_images")
SET_REPORT_CSV = Path("dataset_set_resolution_report.csv")

TCGDEX_BASE = "https://api.tcgdex.net/v2/en"
TIMEOUT_SECONDS = 45
BATCH_SIZE = 500


def validate_env() -> None:
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def load_resolved_folder_set_map() -> dict[str, str]:
    if not SET_REPORT_CSV.exists():
        raise FileNotFoundError(f"Missing required file: {SET_REPORT_CSV}")

    mapping: dict[str, str] = {}
    with SET_REPORT_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("status") != "resolved":
                continue
            folder = (row.get("folder") or "").strip()
            set_id = (row.get("resolved_set_id") or "").strip()
            if folder and set_id:
                mapping[folder] = set_id
    return mapping


def list_bucket_webp_paths(folder_set_map: dict[str, str]) -> set[str]:
    paths: set[str] = set()
    headers = supabase_headers()

    for folder in sorted(folder_set_map):
        prefix = f"raw_images/{folder}"
        offset = 0
        while True:
            payload = {
                "prefix": prefix,
                "limit": 200,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            }
            url = f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET_NAME}"
            r = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)
            r.raise_for_status()
            items = r.json()
            if not items:
                break

            for item in items:
                if item.get("id") and str(item.get("name", "")).lower().endswith(".webp"):
                    paths.add(f"{prefix}/{item['name']}")

            if len(items) < payload["limit"]:
                break
            offset += payload["limit"]

    return paths


def fetch_set_details(set_id: str) -> dict | None:
    r = requests.get(f"{TCGDEX_BASE}/sets/{set_id}", timeout=TIMEOUT_SECONDS)
    if r.status_code != 200:
        print(f"FAILED set lookup: {set_id} | {r.status_code}")
        return None
    return r.json()


def build_card_lookup(set_payload: dict) -> dict[str, tuple[str, str]]:
    lookup: dict[str, tuple[str, str]] = {}
    for c in set_payload.get("cards", []):
        local_id = str(c.get("localId", "")).strip()
        name = str(c.get("name", "")).strip()
        if not local_id:
            continue
        canon = normalize_card_number(local_id)
        if canon and name:
            lookup[canon] = (local_id, name)
    return lookup


def normalize_card_number(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+", text):
        return str(int(text))
    return text.lower()


def extract_card_number_from_filename(filename: str) -> str | None:
    stem = Path(filename).stem

    patterns = [
        r"^[^_]+_en_(\d+)",  # sv3-5_en_001_std
        r"en_[a-z]{2}-[a-z0-9.]+-(\d+)-",  # en_US-SWSH2-047-name
        r"-(\d+)$",  # ...-35
    ]

    for pattern in patterns:
        m = re.search(pattern, stem, flags=re.IGNORECASE)
        if m:
            return str(int(m.group(1)))

    tail = re.search(r"[_-](\d+)(?:[_-].*)?$", stem)
    if tail:
        return str(int(tail.group(1)))

    return None


def title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[_-](en|std).*$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[_-]\d+$", "", stem)
    stem = re.sub(r"[_-]+", " ", stem).strip()
    if not stem:
        return "Unknown Card"
    return " ".join(word.capitalize() for word in stem.split())


def chunked(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def upsert_rows(table: str, rows: list[dict], on_conflict: str) -> None:
    if not rows:
        return

    headers = supabase_headers()
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}"

    for batch in chunked(rows, BATCH_SIZE):
        r = requests.post(url, headers=headers, json=batch, timeout=TIMEOUT_SECONDS)
        if not (200 <= r.status_code < 300):
            raise RuntimeError(f"Upsert failed for {table}: {r.status_code} {r.text}")


def main() -> None:
    validate_env()
    if not DATASET_ROOT.exists():
        raise FileNotFoundError(f"Missing dataset root: {DATASET_ROOT}")

    folder_set_map = load_resolved_folder_set_map()
    print(f"Resolved folders: {len(folder_set_map)}")

    print("Listing bucket .webp paths...")
    bucket_paths = list_bucket_webp_paths(folder_set_map)
    print(f"Bucket .webp files discovered: {len(bucket_paths)}")

    sets_rows: list[dict] = []
    cards_map: dict[str, dict] = {}
    card_images_map: dict[str, dict] = {}

    for folder in sorted(folder_set_map):
        set_id = folder_set_map[folder]
        set_payload = fetch_set_details(set_id)
        if not set_payload:
            continue

        set_name = str(set_payload.get("name", "")).strip()
        release_date = set_payload.get("releaseDate")
        if set_name:
            sets_rows.append(
                {
                    "id": set_id,
                    "name": set_name,
                    "release_date": release_date if isinstance(release_date, str) else None,
                }
            )

        card_lookup = build_card_lookup(set_payload)
        folder_path = DATASET_ROOT / folder
        for image_path in sorted(folder_path.glob("*.webp")):
            storage_path = f"raw_images/{folder}/{image_path.name}"
            if storage_path not in bucket_paths:
                continue

            extracted = extract_card_number_from_filename(image_path.name)
            if not extracted:
                continue

            card_number = extracted
            card_name = title_from_filename(image_path.name)
            normalized = normalize_card_number(extracted)
            if normalized in card_lookup:
                card_number, card_name = card_lookup[normalized]

            card_id = f"{set_id}-{card_number}"
            cards_map[card_id] = {
                "id": card_id,
                "set_id": set_id,
                "card_number": card_number,
                "name": card_name,
            }
            card_images_map[storage_path] = {
                "card_id": card_id,
                "storage_bucket": BUCKET_NAME,
                "storage_path": storage_path,
            }

    sets_rows = sorted({row["id"]: row for row in sets_rows}.values(), key=lambda x: x["id"])
    cards_rows = sorted(cards_map.values(), key=lambda x: x["id"])
    card_images_rows = sorted(card_images_map.values(), key=lambda x: x["storage_path"])

    print(f"Upserting sets: {len(sets_rows)}")
    upsert_rows("sets", sets_rows, "id")
    print(f"Upserting cards: {len(cards_rows)}")
    upsert_rows("cards", cards_rows, "id")
    print(f"Upserting card_images: {len(card_images_rows)}")
    upsert_rows("card_images", card_images_rows, "storage_path")

    print("\nDone")
    print(f"sets upserted: {len(sets_rows)}")
    print(f"cards upserted: {len(cards_rows)}")
    print(f"card_images upserted: {len(card_images_rows)}")


if __name__ == "__main__":
    main()
