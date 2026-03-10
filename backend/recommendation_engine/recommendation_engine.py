from __future__ import annotations

import csv
import json
import logging
import os
import re
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from http_compat import get as http_get

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local dependency
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled via runtime fallback
    OpenAI = None  # type: ignore[assignment]

try:
    from tcgdexsdk import TCGdex
except ImportError:  # pragma: no cover - handled via runtime fallback
    TCGdex = None  # type: ignore[assignment]

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DEFAULT_BUDGET_USD = 1000.0
DEFAULT_LIMIT = 15
DEFAULT_SHORTLIST_SIZE = 24
DEFAULT_COLLECTION_CSV = Path(__file__).with_name("example_collection.csv")
SUPABASE_PAGE_SIZE = 500
RAW_SET_FETCH_LIMIT = 3
RAW_POKEMON_FETCH_LIMIT = 3
RAW_NAME_SEARCH_LIMIT = 30
RECOMMENDATION_CACHE_TTL_SECONDS = 10 * 60
_NAME_SUFFIX_RE = re.compile(
    r"\b(?:ex|gx|vmax|vstar|v union|v-union|v|lv\.?\s*x|break|prism star|star|radiant)\b",
    re.IGNORECASE,
)

_TCGDEX_CLIENT = TCGdex() if TCGdex else None
_TCGDEX_CACHE: dict[str, dict[str, Any] | None] = {}
_RECOMMENDATION_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
LOGGER = logging.getLogger(__name__)
RECOMMENDATION_GROUP_SPECS = (
    {
        "key": "pokemon_affinity",
        "title": "Pokemon Affinity",
        "focus": "Cards that match the Pokemon you collect most.",
        "limit": 5,
        "candidate_pool_size": 10,
    },
    {
        "key": "set_affinity",
        "title": "Set Affinity",
        "focus": "Cards that deepen the sets you already favor.",
        "limit": 5,
        "candidate_pool_size": 10,
    },
    {
        "key": "rarity_affinity",
        "title": "Rarity Affinity",
        "focus": "Cards that match the rarities you tend to keep.",
        "limit": 5,
        "candidate_pool_size": 20,
    },
)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _compact_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize_text(value))


def _clean_pokemon_name(value: str | None) -> str:
    text = (value or "").replace("-", " ").replace("δ", " ")
    text = _NAME_SUFFIX_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" .-")
    return text or (value or "Unknown")


def _normalize_card_number(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    base = raw.replace(" ", "").split("/")[0]
    stripped = base.lstrip("0")
    return stripped or base


def card_number_candidates(value: str | None) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return []

    candidates: list[str] = []

    def add(candidate: str | None) -> None:
        text = (candidate or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    compact = raw.replace(" ", "")
    slash_base = compact.split("/")[0]
    stripped = slash_base.lstrip("0")
    alnum = re.sub(r"[^A-Za-z0-9]", "", compact)

    add(raw)
    add(compact)
    add(slash_base)
    add(stripped or slash_base)
    add(alnum)
    return candidates


def price_status_for_budget(price_usd: float | None, budget_usd: float) -> str:
    if price_usd is None:
        return "unknown"
    return "under_budget" if price_usd <= budget_usd else "over_budget"


def _supabase_config(required: bool = True) -> tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if required and (not url or not key):
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    return url, key


def _storage_bucket() -> str:
    return (os.getenv("STORAGE_BUCKET") or "pokemon-images").strip() or "pokemon-images"


def _supabase_headers() -> dict[str, str]:
    _, key = _supabase_config(required=True)
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _to_public_image_url(storage_path: str | None) -> str | None:
    if not storage_path:
        return None
    url, _ = _supabase_config(required=True)
    cleaned = storage_path.lstrip("/")
    return f"{url}/storage/v1/object/public/{_storage_bucket()}/{cleaned}"


def _fetch_supabase_rows(
    table: str,
    select_cols: str,
    filters: dict[str, str] | None = None,
    *,
    page_size: int = SUPABASE_PAGE_SIZE,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    url, _ = _supabase_config(required=True)
    endpoint = f"{url}/rest/v1/{table}"
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        params = {"select": select_cols}
        if filters:
            params.update(filters)

        headers = {
            **_supabase_headers(),
            "Range-Unit": "items",
            "Range": f"{offset}-{offset + page_size - 1}",
        }
        response = http_get(endpoint, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected Supabase response for table {table}")

        rows.extend(batch)
        if max_rows is not None and len(rows) >= max_rows:
            return rows[:max_rows]
        if len(batch) < page_size:
            break
        offset += page_size

    return rows


def _build_or_filter(column: str, values: list[str]) -> str:
    return ",".join(f"{column}.eq.{value}" for value in values if value)


def _fetch_rows_by_values(table: str, select_cols: str, column: str, values: list[str]) -> list[dict[str, Any]]:
    unique_values = list(dict.fromkeys(value for value in values if value))
    rows: list[dict[str, Any]] = []
    chunk_size = 50
    for index in range(0, len(unique_values), chunk_size):
        chunk = unique_values[index : index + chunk_size]
        rows.extend(
            _fetch_supabase_rows(
                table,
                select_cols,
                {"or": f"({_build_or_filter(column, chunk)})"},
                page_size=min(len(chunk) or 1, SUPABASE_PAGE_SIZE),
            )
        )
    return rows


def _fetch_cards_for_sets(set_ids: list[str]) -> list[dict[str, Any]]:
    unique_set_ids = [set_id for set_id in dict.fromkeys(set_ids) if set_id]
    if not unique_set_ids:
        return []
    return _fetch_supabase_rows(
        "cards",
        "id,name,set_id,card_number,price_usd,price_last_updated",
        {"or": f"({_build_or_filter('set_id', unique_set_ids)})"},
    )


def _search_cards_by_name(name_fragment: str, max_rows: int = 80) -> list[dict[str, Any]]:
    fragment = (name_fragment or "").strip()
    if not fragment:
        return []
    return _fetch_supabase_rows(
        "cards",
        "id,name,set_id,card_number,price_usd,price_last_updated",
        {"name": f"ilike.*{fragment}*"},
        page_size=min(max_rows, 100),
        max_rows=max_rows,
    )


def _fetch_set_name_lookup(set_ids: list[str]) -> dict[str, str]:
    rows = _fetch_rows_by_values("sets", "id,name", "id", set_ids)
    return {str(row.get("id")): str(row.get("name")) for row in rows if row.get("id")}


def _fetch_image_lookup(card_ids: list[str]) -> dict[str, str]:
    rows = _fetch_rows_by_values("card_images", "card_id,storage_path", "card_id", card_ids)
    lookup: dict[str, str] = {}
    for row in rows:
        card_id = str(row.get("card_id") or "").strip()
        storage_path = str(row.get("storage_path") or "").strip()
        if card_id and storage_path and card_id not in lookup:
            lookup[card_id] = storage_path
    return lookup


def _collection_signature(
    collection: list[dict[str, Any]],
    source: str,
    csv_path: str | os.PathLike[str] | None = None,
) -> str:
    if source == "csv":
        resolved_path = Path(csv_path) if csv_path else DEFAULT_COLLECTION_CSV
        try:
            stat = resolved_path.stat()
            return json.dumps(
                {
                    "source": "csv",
                    "path": str(resolved_path.resolve()),
                    "mtime_ns": stat.st_mtime_ns,
                },
                sort_keys=True,
            )
        except OSError:
            pass

    entries = sorted(
        (
            str(card.get("card_id") or ""),
            max(1, _as_int(card.get("quantity"), 1)),
            str(card.get("set_id") or ""),
            str(card.get("card_number") or ""),
        )
        for card in collection
    )
    return json.dumps({"source": source, "entries": entries}, sort_keys=True)


def _recommendation_cache_key(
    *,
    source: str,
    user_id: str | None,
    csv_path: str | os.PathLike[str] | None,
    budget_usd: float,
    limit: int,
    collection_signature: str,
) -> str:
    return json.dumps(
        {
            "source": source,
            "user_id": (user_id or "").strip(),
            "csv_path": str(csv_path or ""),
            "budget_usd": float(budget_usd),
            "limit": int(limit),
            "collection_signature": collection_signature,
        },
        sort_keys=True,
    )


def _get_cached_recommendation(cache_key: str) -> dict[str, Any] | None:
    cached = _RECOMMENDATION_CACHE.get(cache_key)
    if not cached:
        return None
    created_at, payload = cached
    if time.time() - created_at > RECOMMENDATION_CACHE_TTL_SECONDS:
        _RECOMMENDATION_CACHE.pop(cache_key, None)
        return None
    return deepcopy(payload)


def _store_recommendation_cache(cache_key: str, payload: dict[str, Any]) -> None:
    _RECOMMENDATION_CACHE[cache_key] = (time.time(), deepcopy(payload))


def load_collection_from_csv(path: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    csv_path = Path(path) if path else DEFAULT_COLLECTION_CSV
    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    collection: list[dict[str, Any]] = []
    for row in rows:
        set_id = str(row.get("set") or "").strip()
        card_number = str(row.get("number") or "").strip()
        if not set_id or not card_number:
            continue
        collection.append(
            {
                "card_id": None,
                "set_id": set_id,
                "card_number": card_number,
                "name": str(row.get("name") or "").strip() or f"{set_id}-{card_number}",
                "quantity": max(1, _as_int(row.get("quantity"), 1)),
                "price_usd": _as_float(row.get("price_usd")),
                "price_last_updated": row.get("price_last_updated"),
                "condition": row.get("condition"),
                "source": "csv",
            }
        )
    return collection


def load_collection_from_supabase(user_id: str) -> list[dict[str, Any]]:
    cleaned_user_id = (user_id or "").strip()
    if not cleaned_user_id:
        raise ValueError("user_id is required for Supabase recommendations")

    collection_rows = _fetch_supabase_rows(
        "collections",
        "card_id,quantity,price_usd,price_last_updated",
        {"user_id": f"eq.{cleaned_user_id}"},
    )
    if not collection_rows:
        return []

    card_ids = [str(row.get("card_id") or "").strip() for row in collection_rows if row.get("card_id")]
    cards = _fetch_rows_by_values(
        "cards",
        "id,name,set_id,card_number,price_usd,price_last_updated",
        "id",
        card_ids,
    )
    cards_by_id = {str(card.get("id")): card for card in cards if card.get("id")}
    set_lookup = _fetch_set_name_lookup([str(card.get("set_id") or "") for card in cards])

    collection: list[dict[str, Any]] = []
    for row in collection_rows:
        card_id = str(row.get("card_id") or "").strip()
        if not card_id:
            continue
        card = cards_by_id.get(card_id)
        if not card:
            continue
        set_id = str(card.get("set_id") or "").strip()
        collection.append(
            {
                "card_id": card_id,
                "set_id": set_id,
                "card_number": str(card.get("card_number") or "").strip(),
                "name": str(card.get("name") or "").strip() or card_id,
                "quantity": max(1, _as_int(row.get("quantity"), 1)),
                "price_usd": _as_float(row.get("price_usd"))
                if row.get("price_usd") is not None
                else _as_float(card.get("price_usd")),
                "price_last_updated": row.get("price_last_updated") or card.get("price_last_updated"),
                "set_name": set_lookup.get(set_id),
                "source": "supabase",
            }
        )
    return collection


def _extract_tcgdex_image(card: Any) -> str | None:
    image = getattr(card, "image", None)
    if image is None:
        return None
    if isinstance(image, str):
        return image
    for attr in ("high", "url", "small"):
        value = getattr(image, attr, None)
        if value:
            return str(value)
    return None


def _lookup_tcgdex_card(set_id: str, card_number: str) -> dict[str, Any] | None:
    if _TCGDEX_CLIENT is None:
        return None

    for candidate_number in card_number_candidates(card_number):
        lookup = f"{set_id}-{candidate_number}"
        if lookup in _TCGDEX_CACHE:
            cached = _TCGDEX_CACHE[lookup]
            if cached is not None:
                return dict(cached)
            continue

        try:
            card = _TCGDEX_CLIENT.card.getSync(lookup)
        except Exception:
            card = None

        if not card:
            _TCGDEX_CACHE[lookup] = None
            continue

        set_info = getattr(card, "set", None)
        parsed = {
            "tcgdex_id": getattr(card, "id", None),
            "name": getattr(card, "name", None),
            "set_id": getattr(set_info, "id", None) or set_id,
            "set_name": getattr(set_info, "name", None),
            "card_number": str(getattr(card, "localId", candidate_number) or candidate_number),
            "rarity": getattr(card, "rarity", None),
            "category": getattr(card, "category", None),
            "dex_id": getattr(card, "dexId", []) or [],
            "types": getattr(card, "types", []) or [],
            "image_url": _extract_tcgdex_image(card),
        }
        _TCGDEX_CACHE[lookup] = parsed
        return dict(parsed)

    return None


def _decorate_supabase_cards(cards: list[dict[str, Any]], include_images: bool = True) -> list[dict[str, Any]]:
    set_lookup = _fetch_set_name_lookup([str(card.get("set_id") or "") for card in cards])
    image_lookup = _fetch_image_lookup([str(card.get("card_id") or "") for card in cards]) if include_images else {}

    decorated: list[dict[str, Any]] = []
    for card in cards:
        next_card = dict(card)
        set_id = str(next_card.get("set_id") or "").strip()
        card_id = str(next_card.get("card_id") or "").strip()
        next_card["set_name"] = next_card.get("set_name") or set_lookup.get(set_id)
        if include_images:
            storage_path = image_lookup.get(card_id)
            next_card["image_url"] = next_card.get("image_url") or _to_public_image_url(storage_path)
        decorated.append(next_card)
    return decorated


def enrich_cards_with_tcgdex(cards: list[dict[str, Any]], include_images: bool = True) -> list[dict[str, Any]]:
    cards_to_enrich = cards
    needs_supabase_assets = any(card.get("card_id") for card in cards) and any(
        not card.get("set_name") or (include_images and "image_url" not in card) for card in cards
    )
    if needs_supabase_assets:
        cards_to_enrich = _decorate_supabase_cards(cards, include_images=include_images)

    enriched: list[dict[str, Any]] = []
    for card in cards_to_enrich:
        metadata = _lookup_tcgdex_card(str(card.get("set_id") or ""), str(card.get("card_number") or "")) or {}
        next_card = dict(card)
        next_card["name"] = metadata.get("name") or next_card.get("name")
        next_card["set_id"] = metadata.get("set_id") or next_card.get("set_id")
        next_card["set_name"] = metadata.get("set_name") or next_card.get("set_name") or next_card.get("set_id")
        next_card["card_number"] = metadata.get("card_number") or next_card.get("card_number")
        next_card["rarity"] = metadata.get("rarity") or next_card.get("rarity")
        next_card["category"] = metadata.get("category") or next_card.get("category")
        next_card["dex_id"] = metadata.get("dex_id") or []
        next_card["types"] = metadata.get("types") or []
        next_card["image_url"] = next_card.get("image_url") or metadata.get("image_url")
        enriched.append(next_card)
    return enriched


def _pokemon_affinity(card: dict[str, Any]) -> dict[str, str] | None:
    if _normalize_text(str(card.get("category") or "")) != "pokemon":
        return None
    display_name = _clean_pokemon_name(str(card.get("name") or ""))
    key = _compact_text(display_name)
    if not key:
        return None
    return {"key": key, "name": display_name}


def infer_user_profile(cards: list[dict[str, Any]], budget_usd: float = DEFAULT_BUDGET_USD) -> dict[str, Any]:
    pokemon_counter: Counter[str] = Counter()
    pokemon_names: dict[str, str] = {}
    set_counter: Counter[str] = Counter()
    set_names: dict[str, str] = {}
    rarity_counter: Counter[str] = Counter()
    collection_size = 0

    for card in cards:
        quantity = max(1, _as_int(card.get("quantity"), 1))
        collection_size += quantity

        set_id = str(card.get("set_id") or "").strip()
        if set_id:
            set_counter[set_id] += quantity
            set_names[set_id] = str(card.get("set_name") or set_id)

        rarity = str(card.get("rarity") or "").strip()
        if rarity:
            rarity_counter[rarity] += quantity

        affinity = _pokemon_affinity(card)
        if affinity:
            pokemon_counter[affinity["key"]] += quantity
            pokemon_names[affinity["key"]] = affinity["name"]

    return {
        "budget_usd": float(budget_usd),
        "collection_size": collection_size,
        "top_pokemon": [
            {"name": pokemon_names[key], "count": count}
            for key, count in pokemon_counter.most_common(5)
        ],
        "top_sets": [
            {"set_id": set_id, "set_name": set_names.get(set_id, set_id), "count": count}
            for set_id, count in set_counter.most_common(3)
        ],
        "top_rarities": [
            {"rarity": rarity, "count": count}
            for rarity, count in rarity_counter.most_common(3)
        ],
        "finish_affinity_status": "ignored_v1",
    }


def _weight_lookup(items: list[dict[str, Any]], key_field: str) -> dict[str, float]:
    if not items:
        return {}
    max_count = max(int(item.get("count") or 1) for item in items) or 1
    weights: dict[str, float] = {}
    for item in items:
        key = str(item.get(key_field) or "").strip()
        if not key:
            continue
        weights[key] = (int(item.get("count") or 1) / max_count) if max_count else 0.0
    return weights


def _fetch_candidate_card_rows(profile: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    set_ids = [
        str(item.get("set_id") or "").strip()
        for item in profile.get("top_sets", [])[:RAW_SET_FETCH_LIMIT]
    ]
    pokemon_names = [
        str(item.get("name") or "").strip()
        for item in profile.get("top_pokemon", [])[:RAW_POKEMON_FETCH_LIMIT]
    ]

    rows.extend(_fetch_cards_for_sets([set_id for set_id in set_ids if set_id]))
    for pokemon_name in pokemon_names:
        rows.extend(_search_cards_by_name(pokemon_name, max_rows=RAW_NAME_SEARCH_LIMIT))

    deduped: dict[str, dict[str, Any]] = {}
    for row in rows:
        card_id = str(row.get("id") or "").strip()
        if card_id and card_id not in deduped:
            deduped[card_id] = {
                "card_id": card_id,
                "name": str(row.get("name") or "").strip() or card_id,
                "set_id": str(row.get("set_id") or "").strip(),
                "card_number": str(row.get("card_number") or "").strip(),
                "price_usd": _as_float(row.get("price_usd")),
                "price_last_updated": row.get("price_last_updated"),
            }
    return list(deduped.values())


def _owned_candidate_filters(owned_cards: list[dict[str, Any]]) -> tuple[set[str], set[tuple[str, str]]]:
    owned_ids = {
        str(card.get("card_id") or "").strip()
        for card in owned_cards
        if str(card.get("card_id") or "").strip()
    }
    owned_set_numbers = {
        (
            str(card.get("set_id") or "").strip(),
            _normalize_card_number(str(card.get("card_number") or "")),
        )
        for card in owned_cards
        if card.get("set_id") and card.get("card_number")
    }
    return owned_ids, owned_set_numbers


def _filter_owned_candidates(
    candidate_cards: list[dict[str, Any]],
    owned_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    owned_ids, owned_set_numbers = _owned_candidate_filters(owned_cards)
    filtered: list[dict[str, Any]] = []
    for candidate in candidate_cards:
        card_id = str(candidate.get("card_id") or "").strip()
        set_number_key = (
            str(candidate.get("set_id") or "").strip(),
            _normalize_card_number(str(candidate.get("card_number") or "")),
        )
        if card_id and card_id in owned_ids:
            continue
        if set_number_key in owned_set_numbers:
            continue
        filtered.append(candidate)
    return filtered


def _pokemon_name_match_weight(card_name: str | None, pokemon_weights: dict[str, float]) -> float:
    compact_name = _compact_text(card_name)
    if not compact_name:
        return 0.0
    matches = [
        weight
        for pokemon_name, weight in pokemon_weights.items()
        if pokemon_name and pokemon_name in compact_name
    ]
    return max(matches, default=0.0)


def _raw_price_adjustment(price_status: str) -> float:
    if price_status == "under_budget":
        return 1.0
    if price_status == "unknown":
        return 0.25
    return -1.0


def _raw_score_candidate(card: dict[str, Any], profile: dict[str, Any], budget_usd: float) -> dict[str, Any]:
    set_weights = _weight_lookup(profile.get("top_sets", []), "set_id")
    pokemon_weights = {
        _compact_text(key): value
        for key, value in _weight_lookup(profile.get("top_pokemon", []), "name").items()
    }

    price_status = price_status_for_budget(_as_float(card.get("price_usd")), budget_usd)
    score = 0.0
    set_id = str(card.get("set_id") or "").strip()
    if set_id in set_weights:
        score += 5.0 * set_weights[set_id]
    score += 4.0 * _pokemon_name_match_weight(str(card.get("name") or ""), pokemon_weights)
    score += _raw_price_adjustment(price_status)

    return {
        **card,
        "price_status": price_status,
        "raw_score": round(score, 4),
    }


def _profile_weight_maps(profile: dict[str, Any]) -> dict[str, dict[str, float]]:
    return {
        "set_weights": _weight_lookup(profile.get("top_sets", []), "set_id"),
        "pokemon_weights": {
            _compact_text(key): value
            for key, value in _weight_lookup(profile.get("top_pokemon", []), "name").items()
        },
        "rarity_weights": _weight_lookup(profile.get("top_rarities", []), "rarity"),
    }


def _budget_score_details(price_usd: float | None, budget_usd: float) -> dict[str, Any]:
    status = price_status_for_budget(price_usd, budget_usd)
    if status == "under_budget":
        if budget_usd > 0 and price_usd is not None:
            remaining_ratio = max(0.0, 1.0 - (price_usd / budget_usd))
        else:
            remaining_ratio = 0.0
        return {
            "price_status": status,
            "score": 3.0 + remaining_ratio,
            "reason": f"Currently fits inside your ${budget_usd:,.0f} budget.",
        }
    if status == "over_budget":
        if price_usd is not None and budget_usd > 0:
            penalty = min(4.0, ((price_usd - budget_usd) / budget_usd) * 4.0 + 0.5)
        else:
            penalty = 1.5
        return {
            "price_status": status,
            "score": -penalty,
            "reason": "Sits above your current budget, so it is a stretch target.",
        }
    return {
        "price_status": status,
        "score": 0.75,
        "reason": "Price is missing, so it stays in the mix as a soft-budget option.",
    }


def _candidate_affinity_details(
    card: dict[str, Any],
    weight_maps: dict[str, dict[str, float]],
) -> dict[str, Any]:
    set_id = str(card.get("set_id") or "").strip()
    rarity = str(card.get("rarity") or "").strip()
    affinity = _pokemon_affinity(card)
    pokemon_name = affinity["name"] if affinity else None
    pokemon_key = _compact_text(pokemon_name) if pokemon_name else ""
    return {
        "set_weight": weight_maps["set_weights"].get(set_id, 0.0),
        "pokemon_weight": weight_maps["pokemon_weights"].get(pokemon_key, 0.0) if pokemon_key else 0.0,
        "rarity_weight": weight_maps["rarity_weights"].get(rarity, 0.0),
        "pokemon_name": pokemon_name,
        "set_name": str(card.get("set_name") or set_id),
        "rarity": rarity,
    }


def _sort_cards_by_score(cards: list[dict[str, Any]], score_field: str) -> None:
    cards.sort(
        key=lambda card: (
            -float(card.get(score_field) or 0.0),
            card.get("price_status") == "over_budget",
            _as_float(card.get("price_usd")) is None,
            _as_float(card.get("price_usd")) or 0.0,
            str(card.get("name") or "").lower(),
        )
    )


def _bucket_reason_text(driver_key: str, affinity: dict[str, Any], budget_reason: str) -> list[str]:
    reasons: list[str] = []
    if driver_key == "pokemon_affinity":
        if affinity["pokemon_weight"] > 0 and affinity["pokemon_name"]:
            reasons.append(f"Fits your strongest Pokemon affinity for {affinity['pokemon_name']}.")
        if affinity["set_weight"] > 0:
            reasons.append(f"Also keeps you close to the {affinity['set_name']} set.")
        if affinity["rarity_weight"] > 0 and affinity["rarity"]:
            reasons.append(f"Matches the {affinity['rarity']} cards you already collect.")
    elif driver_key == "set_affinity":
        if affinity["set_weight"] > 0:
            reasons.append(f"Deepens your collection in the {affinity['set_name']} set.")
        if affinity["pokemon_weight"] > 0 and affinity["pokemon_name"]:
            reasons.append(f"Still aligns with your interest in {affinity['pokemon_name']}.")
        if affinity["rarity_weight"] > 0 and affinity["rarity"]:
            reasons.append(f"Also fits the {affinity['rarity']} cards you already keep.")
    elif driver_key == "rarity_affinity":
        if affinity["rarity_weight"] > 0 and affinity["rarity"]:
            reasons.append(f"Matches the {affinity['rarity']} cards you already collect.")
        if affinity["set_weight"] > 0:
            reasons.append(f"It also reinforces your preference for the {affinity['set_name']} set.")
        if affinity["pokemon_weight"] > 0 and affinity["pokemon_name"]:
            reasons.append(f"It stays close to your interest in {affinity['pokemon_name']}.")

    if budget_reason:
        reasons.append(budget_reason)
    return reasons


def _score_bucket_candidate(
    card: dict[str, Any],
    weight_maps: dict[str, dict[str, float]],
    budget_usd: float,
    driver_key: str,
) -> dict[str, Any]:
    affinity = _candidate_affinity_details(card, weight_maps)
    budget_details = _budget_score_details(_as_float(card.get("price_usd")), budget_usd)
    weights_by_driver = {
        "pokemon_affinity": (10.0, 4.0, 2.0, 0.5),
        "set_affinity": (4.0, 10.0, 2.0, 0.0),
        "rarity_affinity": (2.0, 4.0, 10.0, 0.0),
    }
    pokemon_weight_factor, set_weight_factor, rarity_weight_factor, pokemon_bonus = weights_by_driver[driver_key]
    primary_weight_lookup = {
        "pokemon_affinity": affinity["pokemon_weight"],
        "set_affinity": affinity["set_weight"],
        "rarity_affinity": affinity["rarity_weight"],
    }
    score = (
        pokemon_weight_factor * affinity["pokemon_weight"]
        + set_weight_factor * affinity["set_weight"]
        + rarity_weight_factor * affinity["rarity_weight"]
        + float(budget_details["score"])
    )
    if driver_key == "pokemon_affinity" and _normalize_text(str(card.get("category") or "")) == "pokemon":
        score += pokemon_bonus

    reasons = _bucket_reason_text(driver_key, affinity, str(budget_details["reason"]))
    return {
        **card,
        "driver_key": driver_key,
        "price_status": budget_details["price_status"],
        "bucket_score": round(score, 4),
        "is_eligible": primary_weight_lookup[driver_key] > 0,
        "deterministic_reason": " ".join(reasons[:2]) if reasons else "Strong fit for your current collection patterns.",
    }


def _group_limit_lookup(limit: int) -> dict[str, int]:
    remaining = max(0, min(limit, DEFAULT_LIMIT))
    limits: dict[str, int] = {}
    for spec in RECOMMENDATION_GROUP_SPECS:
        group_limit = min(int(spec["limit"]), remaining)
        limits[str(spec["key"])] = group_limit
        remaining -= group_limit
    return limits


def _shared_candidate_pool_size(limit: int) -> int:
    group_limits = _group_limit_lookup(limit)
    active_group_pool_target = sum(
        int(spec.get("candidate_pool_size") or 0)
        for spec in RECOMMENDATION_GROUP_SPECS
        if group_limits.get(str(spec["key"]), 0) > 0
    )
    return max(DEFAULT_SHORTLIST_SIZE, limit + 5, active_group_pool_target)


def _empty_recommendation_groups(limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    _ = _group_limit_lookup(limit)
    return [
        {
            "key": str(spec["key"]),
            "title": str(spec["title"]),
            "focus": str(spec["focus"]),
            "recommendations": [],
        }
        for spec in RECOMMENDATION_GROUP_SPECS
    ]


def build_recommendation_candidate_groups(
    profile: dict[str, Any],
    candidates: list[dict[str, Any]],
    budget_usd: float,
    *,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    weight_maps = _profile_weight_maps(profile)
    group_limits = _group_limit_lookup(limit)
    groups: list[dict[str, Any]] = []

    for spec in RECOMMENDATION_GROUP_SPECS:
        driver_key = str(spec["key"])
        target_count = group_limits.get(driver_key, 0)
        scored_candidates = []
        for candidate in candidates:
            if not str(candidate.get("card_id") or "").strip():
                continue
            scored = _score_bucket_candidate(candidate, weight_maps, budget_usd, driver_key)
            if not scored["is_eligible"]:
                continue
            scored_candidates.append(scored)

        _sort_cards_by_score(scored_candidates, "bucket_score")
        configured_pool_size = int(spec.get("candidate_pool_size") or 0)
        candidate_limit = (
            max(configured_pool_size, target_count * 2, target_count + 5)
            if target_count > 0
            else 0
        )
        groups.append(
            {
                "key": driver_key,
                "title": str(spec["title"]),
                "focus": str(spec["focus"]),
                "target_count": target_count,
                "candidates": scored_candidates[:candidate_limit],
            }
        )

    return groups


def build_candidate_pool(
    profile: dict[str, Any],
    owned_cards: list[dict[str, Any]],
    budget_usd: float,
    *,
    shortlist_size: int = DEFAULT_SHORTLIST_SIZE,
    candidate_cards: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fetch_start = time.perf_counter()
    fetched_candidates = candidate_cards if candidate_cards is not None else _fetch_candidate_card_rows(profile)
    filtered_candidates = _filter_owned_candidates(fetched_candidates, owned_cards)
    pre_scored = [_raw_score_candidate(candidate, profile, budget_usd) for candidate in filtered_candidates]
    _sort_cards_by_score(pre_scored, "raw_score")
    candidate_fetch_ms = (time.perf_counter() - fetch_start) * 1000

    enrich_start = time.perf_counter()
    top_candidates = pre_scored[:shortlist_size]
    enriched_candidates = enrich_cards_with_tcgdex(top_candidates, include_images=True)
    enrichment_ms = (time.perf_counter() - enrich_start) * 1000
    return enriched_candidates, {
        "raw_candidate_count": len(fetched_candidates),
        "prefilter_count": len(filtered_candidates),
        "enriched_count": len(enriched_candidates),
        "candidate_fetch_ms": round(candidate_fetch_ms, 2),
        "tcgdex_enrichment_ms": round(enrichment_ms, 2),
    }


def _deterministic_profile_summary(profile: dict[str, Any], budget_usd: float) -> str:
    favorite_pokemon = profile.get("top_pokemon", [])
    favorite_sets = profile.get("top_sets", [])
    favorite_rarities = profile.get("top_rarities", [])

    pokemon_text = favorite_pokemon[0]["name"] if favorite_pokemon else "Pokemon cards"
    set_text = favorite_sets[0]["set_name"] if favorite_sets else "your favorite sets"
    rarity_text = favorite_rarities[0]["rarity"] if favorite_rarities else "higher-priority rarities"
    return (
        f"Your collection leans toward {pokemon_text}, especially in {set_text}. "
        f"These recommendations stay close to that profile, emphasize {rarity_text}, "
        f"and use your ${budget_usd:,.0f} budget as a soft cap."
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Model returned an empty response")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response did not contain JSON")
    parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Model JSON payload was not an object")
    return parsed


def _azure_openai_client() -> tuple[Any, str]:
    if OpenAI is None:
        raise RuntimeError("openai package is not installed")

    endpoint = (os.getenv("AZURE_OPENAI_ENDPOINT") or "").strip().rstrip("/")
    api_key = (os.getenv("AZURE_OPENAI_API_KEY") or "").strip()
    deployment = (os.getenv("MODEL") or "").strip()
    if not endpoint or not api_key or not deployment:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and MODEL are required")

    return OpenAI(api_key=api_key, base_url=f"{endpoint}/openai/v1/"), deployment


def _run_llm_recommender(
    profile: dict[str, Any],
    recommendation_candidate_groups: list[dict[str, Any]],
    budget_usd: float,
    limit: int,
) -> dict[str, Any]:
    client, deployment = _azure_openai_client()
    grouped_payload = [
        {
            "key": group.get("key"),
            "title": group.get("title"),
            "focus": group.get("focus"),
            "target_count": group.get("target_count"),
            "candidates": [
                {
                    "card_id": card.get("card_id"),
                    "name": card.get("name"),
                    "set_id": card.get("set_id"),
                    "set_name": card.get("set_name"),
                    "card_number": card.get("card_number"),
                    "rarity": card.get("rarity"),
                    "price_usd": card.get("price_usd"),
                    "price_status": card.get("price_status"),
                    "driver_key": card.get("driver_key"),
                    "heuristic_reason": card.get("deterministic_reason"),
                }
                for card in group.get("candidates", [])
            ],
        }
        for group in recommendation_candidate_groups
    ]
    response = client.responses.create(
        model=deployment,
        input=[
            {
                "role": "system",
                "content": (
                    "You are a Pokemon card recommendation agent. "
                    "Choose cards only from the supplied candidate groups. "
                    "Return strict JSON with keys profile_summary and recommendation_groups. "
                    "recommendation_groups must be an array of objects with keys key and recommendations. "
                    "Each recommendations value must be an array of objects with card_id and reason. "
                    "Select at most target_count cards for each group, do not invent card IDs, "
                    "do not use the same card_id in more than one group, "
                    "and do not include markdown or any text outside JSON."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "budget_usd": budget_usd,
                        "limit": limit,
                        "profile": profile,
                        "recommendation_groups": grouped_payload,
                    },
                    ensure_ascii=True,
                ),
            },
        ],
    )
    return _extract_json_object(getattr(response, "output_text", ""))


def apply_model_recommendations(
    recommendation_candidate_groups: list[dict[str, Any]],
    model_payload: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    budget_usd: float = DEFAULT_BUDGET_USD,
) -> dict[str, Any]:
    candidates_by_group: dict[str, dict[str, dict[str, Any]]] = {}
    for group in recommendation_candidate_groups:
        group_key = str(group.get("key") or "")
        candidates_by_group[group_key] = {
            str(card.get("card_id") or "").strip(): card
            for card in group.get("candidates", [])
            if str(card.get("card_id") or "").strip()
        }

    model_groups_by_key = {
        str(group.get("key") or "").strip(): group
        for group in (model_payload or {}).get("recommendation_groups", [])
        if str(group.get("key") or "").strip()
    }

    summary = str((model_payload or {}).get("profile_summary") or "").strip()
    if not summary:
        summary = _deterministic_profile_summary(profile or {}, budget_usd)

    finalized_groups: list[dict[str, Any]] = []
    flattened_recommendations: list[dict[str, Any]] = []
    used_card_ids: set[str] = set()
    for group in recommendation_candidate_groups:
        group_key = str(group.get("key") or "")
        target_count = int(group.get("target_count") or 0)
        group_candidates = candidates_by_group.get(group_key, {})
        model_group = model_groups_by_key.get(group_key, {})
        finalized_cards = []
        for item in model_group.get("recommendations", []):
            card_id = str(item.get("card_id") or "").strip()
            if not card_id or card_id in used_card_ids or card_id not in group_candidates:
                continue
            card = group_candidates[card_id]
            finalized_card = {
                "card_id": card.get("card_id"),
                "name": card.get("name"),
                "set_id": card.get("set_id"),
                "set_name": card.get("set_name") or card.get("set_id"),
                "card_number": card.get("card_number"),
                "rarity": card.get("rarity"),
                "price_usd": _as_float(card.get("price_usd")),
                "price_status": card.get("price_status")
                or price_status_for_budget(_as_float(card.get("price_usd")), budget_usd),
                "image_url": card.get("image_url"),
                "reason": str(item.get("reason") or "").strip()
                or str(card.get("deterministic_reason") or "Strong fit for your collection."),
                "driver_key": card.get("driver_key") or group_key,
            }
            finalized_cards.append(finalized_card)
            flattened_recommendations.append(finalized_card)
            used_card_ids.add(card_id)
            if len(finalized_cards) >= target_count:
                break

        for card in group.get("candidates", []):
            if len(finalized_cards) >= target_count:
                break
            card_id = str(card.get("card_id") or "").strip()
            if not card_id or card_id in used_card_ids:
                continue
            finalized_card = {
                "card_id": card.get("card_id"),
                "name": card.get("name"),
                "set_id": card.get("set_id"),
                "set_name": card.get("set_name") or card.get("set_id"),
                "card_number": card.get("card_number"),
                "rarity": card.get("rarity"),
                "price_usd": _as_float(card.get("price_usd")),
                "price_status": card.get("price_status")
                or price_status_for_budget(_as_float(card.get("price_usd")), budget_usd),
                "image_url": card.get("image_url"),
                "reason": str(card.get("deterministic_reason") or "Strong fit for your collection."),
                "driver_key": card.get("driver_key") or group_key,
            }
            finalized_cards.append(finalized_card)
            flattened_recommendations.append(finalized_card)
            used_card_ids.add(card_id)

        finalized_groups.append(
            {
                "key": group_key,
                "title": group.get("title"),
                "focus": group.get("focus"),
                "recommendations": finalized_cards,
            }
        )

    return {
        "profile_summary": summary,
        "recommendations": flattened_recommendations,
        "recommendation_groups": finalized_groups,
    }


def recommend_cards(
    *,
    source: str = "supabase",
    user_id: str | None = None,
    csv_path: str | os.PathLike[str] | None = None,
    budget_usd: float = DEFAULT_BUDGET_USD,
    limit: int = DEFAULT_LIMIT,
    force_refresh: bool = False,
) -> dict[str, Any]:
    total_start = time.perf_counter()
    normalized_source = (source or "supabase").strip().lower()
    if normalized_source not in {"supabase", "csv"}:
        raise ValueError("source must be 'supabase' or 'csv'")
    limit = max(1, min(int(limit), DEFAULT_LIMIT))

    collection_start = time.perf_counter()
    if normalized_source == "supabase":
        collection = load_collection_from_supabase(user_id or "")
    else:
        collection = load_collection_from_csv(csv_path)
    collection_load_ms = round((time.perf_counter() - collection_start) * 1000, 2)

    collection_signature = _collection_signature(collection, normalized_source, csv_path=csv_path)
    cache_key = _recommendation_cache_key(
        source=normalized_source,
        user_id=user_id,
        csv_path=csv_path,
        budget_usd=budget_usd,
        limit=limit,
        collection_signature=collection_signature,
    )
    cached = None if force_refresh else _get_cached_recommendation(cache_key)
    if cached is not None:
        total_ms = round((time.perf_counter() - total_start) * 1000, 2)
        LOGGER.info(
            "recommend_cards source=%s cache=hit collection_ms=%.2f total_ms=%.2f",
            normalized_source,
            collection_load_ms,
            total_ms,
        )
        return cached

    profile_start = time.perf_counter()
    enriched_collection = enrich_cards_with_tcgdex(collection, include_images=False)
    profile = infer_user_profile(enriched_collection, budget_usd=budget_usd)
    profile_ms = round((time.perf_counter() - profile_start) * 1000, 2)

    if not enriched_collection:
        response = {
            "source": normalized_source,
            "budget_usd": float(budget_usd),
            "profile": profile,
            "profile_summary": "No cards found in the collection yet, so there is not enough signal to recommend next pickups.",
            "recommendations": [],
            "recommendation_groups": _empty_recommendation_groups(limit),
        }
        _store_recommendation_cache(cache_key, response)
        total_ms = round((time.perf_counter() - total_start) * 1000, 2)
        LOGGER.info(
            "recommend_cards source=%s cache=miss collection_ms=%.2f profile_ms=%.2f candidate_fetch_ms=0.00 prefilter_count=0 enriched_count=0 gpt_ms=0.00 total_ms=%.2f",
            normalized_source,
            collection_load_ms,
            profile_ms,
            total_ms,
        )
        return response

    shortlist_size = _shared_candidate_pool_size(limit)
    candidate_pool, candidate_metrics = build_candidate_pool(
        profile,
        enriched_collection,
        budget_usd,
        shortlist_size=shortlist_size,
    )
    recommendation_candidate_groups = build_recommendation_candidate_groups(
        profile,
        candidate_pool,
        budget_usd,
        limit=limit,
    )
    candidate_count = sum(
        len(group.get("candidates", []))
        for group in recommendation_candidate_groups
    )
    if candidate_count == 0:
        response = {
            "source": normalized_source,
            "budget_usd": float(budget_usd),
            "profile": profile,
            "profile_summary": _deterministic_profile_summary(profile, budget_usd),
            "recommendations": [],
            "recommendation_groups": _empty_recommendation_groups(limit),
        }
        _store_recommendation_cache(cache_key, response)
        total_ms = round((time.perf_counter() - total_start) * 1000, 2)
        LOGGER.info(
            "recommend_cards source=%s cache=miss collection_ms=%.2f profile_ms=%.2f candidate_fetch_ms=%.2f prefilter_count=%d enriched_count=%d gpt_ms=0.00 total_ms=%.2f",
            normalized_source,
            collection_load_ms,
            profile_ms,
            candidate_metrics["candidate_fetch_ms"],
            candidate_metrics["prefilter_count"],
            candidate_metrics["enriched_count"],
            total_ms,
        )
        return response

    model_payload: dict[str, Any] | None = None
    gpt_start = time.perf_counter()
    try:
        model_payload = _run_llm_recommender(profile, recommendation_candidate_groups, budget_usd, limit)
    except Exception:
        model_payload = None
    gpt_ms = round((time.perf_counter() - gpt_start) * 1000, 2)

    finalized = apply_model_recommendations(
        recommendation_candidate_groups,
        model_payload=model_payload,
        profile=profile,
        budget_usd=budget_usd,
    )
    if not finalized["recommendations"]:
        response = {
            "source": normalized_source,
            "budget_usd": float(budget_usd),
            "profile": profile,
            "profile_summary": _deterministic_profile_summary(profile, budget_usd),
            "recommendations": [],
            "recommendation_groups": _empty_recommendation_groups(limit),
        }
        _store_recommendation_cache(cache_key, response)
        total_ms = round((time.perf_counter() - total_start) * 1000, 2)
        LOGGER.info(
            "recommend_cards source=%s cache=miss collection_ms=%.2f profile_ms=%.2f candidate_fetch_ms=%.2f prefilter_count=%d enriched_count=%d gpt_ms=%.2f total_ms=%.2f",
            normalized_source,
            collection_load_ms,
            profile_ms,
            candidate_metrics["candidate_fetch_ms"],
            candidate_metrics["prefilter_count"],
            candidate_metrics["enriched_count"],
            gpt_ms,
            total_ms,
        )
        return response
    response = {
        "source": normalized_source,
        "budget_usd": float(budget_usd),
        "profile": profile,
        "profile_summary": finalized["profile_summary"],
        "recommendations": finalized["recommendations"],
        "recommendation_groups": finalized["recommendation_groups"],
    }
    _store_recommendation_cache(cache_key, response)
    total_ms = round((time.perf_counter() - total_start) * 1000, 2)
    LOGGER.info(
        "recommend_cards source=%s cache=miss collection_ms=%.2f profile_ms=%.2f candidate_fetch_ms=%.2f prefilter_count=%d enriched_count=%d enrichment_ms=%.2f gpt_ms=%.2f total_ms=%.2f",
        normalized_source,
        collection_load_ms,
        profile_ms,
        candidate_metrics["candidate_fetch_ms"],
        candidate_metrics["prefilter_count"],
        candidate_metrics["enriched_count"],
        candidate_metrics["tcgdex_enrichment_ms"],
        gpt_ms,
        total_ms,
    )
    return response


def main() -> None:
    result = recommend_cards(source="csv", csv_path=DEFAULT_COLLECTION_CSV)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
