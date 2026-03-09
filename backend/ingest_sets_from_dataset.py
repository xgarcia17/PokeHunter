from __future__ import annotations

import os
from pathlib import Path

import requests


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
POKEMON_TCG_API_KEY = os.getenv("POKEMON_TCG_API_KEY", "")

POKEMON_API_BASE = "https://api.pokemontcg.io/v2/sets"
SUPABASE_UPSERT_URL = f"{SUPABASE_URL}/rest/v1/sets?on_conflict=id"

# Tries dataset_comp first, then identification/dataset_comp for this repo layout.
DATASET_CANDIDATES = [Path("dataset_comp"), Path("identification/dataset_comp")]
TIMEOUT_SECONDS = 30


def validate_env() -> None:
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if not POKEMON_TCG_API_KEY:
        missing.append("POKEMON_TCG_API_KEY")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def resolve_dataset_root() -> Path:
    for candidate in DATASET_CANDIDATES:
        if candidate.exists() and candidate.is_dir():
            return candidate
    paths = ", ".join(str(p) for p in DATASET_CANDIDATES)
    raise FileNotFoundError(f"Could not find dataset directory. Tried: {paths}")


def extract_set_id(filename: str) -> str | None:
    if "_" not in filename:
        return None
    set_id = filename.split("_", 1)[0].strip()
    return set_id or None


def discover_set_ids(dataset_root: Path) -> set[str]:
    set_ids: set[str] = set()
    for path in dataset_root.rglob("*.webp"):
        if not path.is_file():
            continue
        set_id = extract_set_id(path.name)
        if set_id:
            set_ids.add(set_id)
    return set_ids


def fetch_set_from_pokemon_api(set_id: str) -> dict | None:
    url = f"{POKEMON_API_BASE}/{set_id}"
    headers = {"X-Api-Key": POKEMON_TCG_API_KEY}
    response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)

    if response.status_code != 200:
        print(f"FAILED API: {set_id} | {response.status_code} | {response.text}")
        return None

    payload = response.json()
    data = payload.get("data")
    if not isinstance(data, dict):
        print(f"FAILED API: {set_id} | missing data field")
        return None

    name = data.get("name")
    release_date = data.get("releaseDate")
    if not name:
        print(f"FAILED API: {set_id} | missing name")
        return None

    return {
        "id": data.get("id", set_id),
        "name": name,
        "release_date": release_date,
    }


def upsert_set_to_supabase(set_row: dict) -> bool:
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }
    response = requests.post(SUPABASE_UPSERT_URL, headers=headers, json=[set_row], timeout=TIMEOUT_SECONDS)
    if 200 <= response.status_code < 300:
        return True

    print(f"FAILED UPSERT: {set_row.get('id')} | {response.status_code} | {response.text}")
    return False


def main() -> None:
    validate_env()
    dataset_root = resolve_dataset_root()
    set_ids = sorted(discover_set_ids(dataset_root))

    print(f"Dataset root: {dataset_root}")
    print(f"Sets discovered from dataset: {len(set_ids)}")

    success: list[str] = []
    failed: list[str] = []

    for set_id in set_ids:
        try:
            set_row = fetch_set_from_pokemon_api(set_id)
            if not set_row:
                failed.append(set_id)
                continue

            if upsert_set_to_supabase(set_row):
                success.append(set_id)
                print(f"UPSERTED: {set_id}")
            else:
                failed.append(set_id)
        except Exception as exc:
            failed.append(set_id)
            print(f"FAILED: {set_id} | exception: {exc}")

    print("\nSummary")
    print(f"sets discovered from dataset: {len(set_ids)}")
    print(f"sets successfully inserted: {len(success)}")
    print(f"sets that failed: {len(failed)}")
    if failed:
        print("failed set_ids:")
        for set_id in failed:
            print(set_id)


if __name__ == "__main__":
    main()
