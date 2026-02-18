import csv
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.justtcg.com/v1"
REQUEST_TIMEOUT = 20
DEFAULT_BATCH_SIZE = 20
API_KEY = os.environ.get("JUST_TCG_API_KEY")

def read_collection(path):
    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def chunked(values, size):
    return [values[i : i + size] for i in range(0, len(values), size)]


def fetch_cards_batch(
    session,
    headers,
    payload_items,
    batch_size=DEFAULT_BATCH_SIZE,
):
    cards = []
    for batch in chunked(payload_items, batch_size):
        resp = session.post(
            f"{API_BASE}/cards",
            headers=headers,
            json=batch,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        cards.extend(resp.json().get("data", []))
    return cards


def fetch_card_by_set_number(
    session,
    headers,
    game,
    set_id,
    number,
    condition=None,
):
    params = {"game": game, "set": set_id, "number": number}
    if condition:
        params["condition"] = condition
    resp = session.get(
        f"{API_BASE}/cards",
        headers=headers,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return data[0] if data else None


def build_cache(csv_path, output_path):
    headers = {"x-api-key": API_KEY}
    session = requests.Session()

    rows = read_collection(csv_path)
    payload_items = []
    for row in rows:
        tcg_id = row.get("tcgplayer_id")
        condition = row.get("condition")
        item = {"tcgplayerId": tcg_id, "condition": condition}
        payload_items.append(item)

    cards_by_tcgplayer_id = {}
    cards_by_set_number = {}
    cards_by_tcgplayer_id_condition = {}
    missing = []

    if payload_items:
        cards = fetch_cards_batch(session, headers, payload_items)
        for card in cards:
            tcg_id = card.get("tcgplayerId")
            if tcg_id:
                cards_by_tcgplayer_id[str(tcg_id)] = card
            set_id = card.get("set")
            number = card.get("number")
            if set_id and number:
                cards_by_set_number[f"{set_id}:{number}"] = card

    for row in rows:
        tcg_id = row.get("tcgplayer_id")
        condition = row.get("condition")
        if tcg_id and condition and tcg_id in cards_by_tcgplayer_id:
            cards_by_tcgplayer_id_condition[f"{tcg_id}:{condition}"] = cards_by_tcgplayer_id[tcg_id]

    payload = {
        "collection": rows,
        "cards_by_tcgplayer_id": cards_by_tcgplayer_id,
        "cards_by_tcgplayer_id_condition": cards_by_tcgplayer_id_condition,
        "cards_by_set_number": cards_by_set_number,
        "missing": missing,
    }

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    print(f"Wrote cache: {output_path}")
    print(f"Fetched cards: {len(cards_by_tcgplayer_id)}")
    if missing:
        print(f"Missing rows: {len(missing)} (see 'missing' in cache)")


def main():
    csv_path = Path(__file__).with_name("example_collection.csv")
    output_path = Path(__file__).with_name("example_collection_cache.json")
    build_cache(str(csv_path), str(output_path))


if __name__ == "__main__":
    main()
