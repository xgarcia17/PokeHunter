import csv
from textwrap import fill

import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

from dotenv import load_dotenv
from tcgdexsdk import TCGdex

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
tcgdex = TCGdex()

recommendation_engine_client = OpenAI(
    api_key = os.getenv("AZURE_OPENAI_API_KEY"),
    base_url=f"{os.getenv("AZURE_OPENAI_ENDPOINT")}/openai/v1"
)

def create_agent_prompt():
    recommendation_engine_prompt = """

    You are PokeHunter-Recommendation-Agent.

    Goal:
    Generate high-quality Pokemon card recommendations from the user’s collection and the full card catalog.

    INPUT CONTEXT (fill at runtime):
    [BEGIN example_collection.csv]
    {{EXAMPLE_COLLECTION_CSV_CONTENT}}
    [END example_collection.csv]

    [BEGIN pokemon_cards.csv]
    {{POKEMON_CARDS_CSV_CONTENT}}
    [END pokemon_cards.csv]

    [BEGIN market_data_optional]
    {{CURRENT_PRICES_BY_CARD_AND_CONDITION}}
    {{PRICE_HISTORY_TIMESERIES}}
    {{LIQUIDITY_OR_SALES_VELOCITY}}
    [END market_data_optional]

    [BEGIN user_behavior_optional]
    {{RECENTLY_VIEWED_OR_ADDED_CARDS}}
    {{FAVORITE_SETS_OR_REGIONS}}
    {{BUDGET_RANGE}}
    [END user_behavior_optional]

    [BEGIN sentiment_optional]
    {{PUBLIC_SENTIMENT_SIGNALS_PER_CARD_OR_SET}}
    [END sentiment_optional]

    HARD RULES:
    - Recommend only cards not already owned.
    - Use only provided data; do not invent cards, sets, prices, IDs, or trends.
    - If required data is missing, state assumptions clearly.
    - Respect language/region constraints if provided.
    - Prefer recommendations that improve set completion.
    - Keep reasoning concise and tied directly to the provided context.

    TASKS:
    1) Parse collection and identify missing cards by set.
    2) Prioritize candidate cards using qualitative reasoning:
    - set completion impact
    - current deal quality (if pricing exists)
    - near-term value potential (if history exists)
    - user behavior fit (if behavior exists)
    - sentiment alignment (if sentiment exists)
    3) Return top {{TOP_N}} recommendations.
    4) Include brief market alerts when relevant.

    OUTPUT FORMAT (strict JSON):
    {
    "summary": {
        "total_cards_owned": <int>,
        "sets_in_progress": <int>,
        "priority_sets": ["<set_name>", "..."],
        "assumptions": ["<assumption>", "..."]
    },
    "recommendations": [
        {
        "rank": 1,
        "card_id": "<id>",
        "card_name": "<name>",
        "set_name": "<set>",
        "language_or_region": "<value_or_unknown>",
        "recommended_condition": "<NM/LP/etc_or_unknown>",
        "estimated_current_price": <number_or_null>,
        "reasoning": "<short concrete rationale>",
        "completion_impact": "<how this helps set completion>",
        "data_used": ["collection", "catalog", "market", "behavior", "sentiment"]
        }
    ],
    "market_alerts": [
        {
        "type": "<undervalued|momentum|set_completion_opportunity|risk>",
        "card_or_set": "<name>",
        "message": "<short alert>"
        }
    ]
    }
    """

    return recommendation_engine_prompt

def create_agent():
    recommendation_prompt = create_agent_prompt()

    response = recommendation_engine_client.responses.create(
    model = os.getenv("MODEL"),
    input=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ],
)


def read_collection(path):
    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _parse_abilities(abilities):
    if not abilities:
        return []
    return [
        {
            "type": getattr(ability, "type", None),
            "name": getattr(ability, "name", None),
            "effect": getattr(ability, "effect", None),
        }
        for ability in abilities
    ]


def _parse_attacks(attacks):
    if not attacks:
        return []
    return [
        {
            "name": getattr(attack, "name", None),
            "cost": getattr(attack, "cost", []),
            "effect": getattr(attack, "effect", None),
            "damage": getattr(attack, "damage", None),
        }
        for attack in attacks
    ]


def _parse_weak_res(entries):
    if not entries:
        return []
    return [
        {
            "type": getattr(entry, "type", None),
            "value": getattr(entry, "value", None),
        }
        for entry in entries
    ]


def parse_card_info(card, row):
    set_info = getattr(card, "set", None)
    set_count = getattr(set_info, "cardCount", None)
    variants = getattr(card, "variants", None)
    legal = getattr(card, "legal", None)

    local_id = str(getattr(card, "localId", row.get("number") or "")).strip()
    set_id = getattr(set_info, "id", row.get("set"))

    return {
        "id": getattr(card, "id", None),
        "name": getattr(card, "name", None),
        "game": row.get("game"),
        "set": set_id,
        "set_name": getattr(set_info, "name", None),
        "set_logo": getattr(set_info, "logo", None),
        "set_symbol": getattr(set_info, "symbol", None),
        "set_card_count": {
            "official": getattr(set_count, "official", None),
            "total": getattr(set_count, "total", None),
        },
        "number": local_id,
        "rarity": getattr(card, "rarity", None),
        "category": getattr(card, "category", None),
        "illustrator": getattr(card, "illustrator", None),
        "hp": getattr(card, "hp", None),
        "types": getattr(card, "types", []),
        "evolve_from": getattr(card, "evolveFrom", None),
        "description": getattr(card, "description", None),
        "level": getattr(card, "level", None),
        "stage": getattr(card, "stage", None),
        "suffix": getattr(card, "suffix", None),
        "item": getattr(card, "item", None),
        "abilities": _parse_abilities(getattr(card, "abilities", None)),
        "attacks": _parse_attacks(getattr(card, "attacks", None)),
        "weaknesses": _parse_weak_res(getattr(card, "weaknesses", None)),
        "resistances": _parse_weak_res(getattr(card, "resistances", None)),
        "retreat": getattr(card, "retreat", None),
        "effect": getattr(card, "effect", None),
        "trainer_type": getattr(card, "trainerType", None),
        "energy_type": getattr(card, "energyType", None),
        "regulation_mark": getattr(card, "regulationMark", None),
        "legal": {
            "standard": getattr(legal, "standard", None),
            "expanded": getattr(legal, "expanded", None),
        },
        "variants": {
            "normal": getattr(variants, "normal", None),
            "reverse": getattr(variants, "reverse", None),
            "holo": getattr(variants, "holo", None),
            "first_edition": getattr(variants, "firstEdition", None),
            "w_promo": getattr(variants, "wPromo", None),
        },
        "dex_id": getattr(card, "dexId", []),
        "image": getattr(card, "image", None),
        "boosters": getattr(card, "boosters", None),
        "source": {
            "set": row.get("set"),
            "number": row.get("number"),
            "name": row.get("name"),
            "tcgplayer_id": row.get("tcgplayer_id"),
            "condition": row.get("condition"),
        },
    }


def _join(values):
    if not values:
        return "None"
    return ", ".join(str(value) for value in values)


def _display(value):
    return "N/A" if value is None or value == "" else str(value)


def _format_weak_res(entries):
    if not entries:
        return "None"
    return "; ".join(f"{entry.get('type')} {entry.get('value')}" for entry in entries)


def _wrapped(prefix, value, width=110):
    text = _display(value)
    return fill(f"{prefix}{text}", width=width, subsequent_indent=" " * len(prefix))


def format_card_for_display(card):
    lines = []
    lines.append(f"{_display(card.get('name'))} ({_display(card.get('set_name'))} #{_display(card.get('number'))})")
    lines.append(f"  id: {_display(card.get('id'))}")
    lines.append(f"  category/rarity: {_display(card.get('category'))} / {_display(card.get('rarity'))}")
    lines.append(f"  illustrator: {_display(card.get('illustrator'))}")
    lines.append(
        f"  hp/types/stage: {_display(card.get('hp'))} / {_join(card.get('types', []))} / {_display(card.get('stage'))}"
    )
    lines.append(f"  evolves from: {_display(card.get('evolve_from'))}")
    lines.append(_wrapped("  description: ", card.get("description")))
    lines.append(f"  weaknesses: {_format_weak_res(card.get('weaknesses', []))}")
    lines.append(f"  resistances: {_format_weak_res(card.get('resistances', []))}")
    lines.append(f"  retreat: {_display(card.get('retreat'))}")
    lines.append(
        "  legal: "
        f"standard={card.get('legal', {}).get('standard')}, "
        f"expanded={card.get('legal', {}).get('expanded')}"
    )
    lines.append(f"  image: {_display(card.get('image'))}")

    abilities = card.get("abilities", [])
    if abilities:
        lines.append("  abilities:")
        for ability in abilities:
            lines.append(
                _wrapped(
                    f"    - {_display(ability.get('name'))} [{_display(ability.get('type'))}]: ",
                    ability.get("effect"),
                )
            )
    else:
        lines.append("  abilities: None")

    attacks = card.get("attacks", [])
    if attacks:
        lines.append("  attacks:")
        for attack in attacks:
            cost = _join(attack.get("cost", []))
            lines.append(f"    - {_display(attack.get('name'))} | cost={cost} | damage={_display(attack.get('damage'))}")
            lines.append(_wrapped("      effect: ", attack.get("effect")))
    else:
        lines.append("  attacks: None")

    return "\n".join(lines)


def parse_collection(collection, print_cards=True):
    cards = []
    cards_by_set_number = {}
    cards_by_tcgplayer_id = {}
    cards_by_tcgplayer_id_condition = {}
    missing = []

    for row in collection:
        set_id = (row.get("set") or "").strip()
        number = (row.get("number") or "").strip()
        lookup = f"{set_id}-{number}"

        if not set_id or not number:
            missing.append({"row": row, "error": "Missing set or number"})
            continue

        try:
            card = tcgdex.card.getSync(lookup)
        except Exception as exc:
            missing.append({"row": row, "lookup": lookup, "error": str(exc)})
            continue

        if not card:
            missing.append({"row": row, "lookup": lookup, "error": "Card not found"})
            continue

        parsed = parse_card_info(card, row)
        cards.append(parsed)

        cards_by_set_number[f"{set_id}:{number}"] = parsed

        tcgplayer_id = (row.get("tcgplayer_id") or "").strip()
        condition = (row.get("condition") or "").strip()
        if tcgplayer_id:
            cards_by_tcgplayer_id[tcgplayer_id] = parsed
            if condition:
                cards_by_tcgplayer_id_condition[f"{tcgplayer_id}:{condition}"] = parsed

        if print_cards:
            print(format_card_for_display(parsed))
            print("-" * 100)

    return {
        "collection": collection,
        "cards": cards,
        "cards_by_set_number": cards_by_set_number,
        "cards_by_tcgplayer_id": cards_by_tcgplayer_id,
        "cards_by_tcgplayer_id_condition": cards_by_tcgplayer_id_condition,
        "missing": missing,
    }


def main():
    csv_path = Path(__file__).with_name("example_collection.csv")
    collection = read_collection(csv_path)
    parsed_collection = parse_collection(collection, print_cards=True)

    print(f"Parsed cards: {len(parsed_collection['cards'])}")
    if parsed_collection["missing"]:
        print(f"Missing rows: {len(parsed_collection['missing'])}")


if __name__ == "__main__":
    main()
