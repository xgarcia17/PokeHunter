from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from recommendation_engine import recommendation_engine as engine

try:
    import backend_api
except Exception as exc:  # pragma: no cover - environment dependent
    backend_api = None
    BACKEND_API_IMPORT_ERROR = exc
else:
    BACKEND_API_IMPORT_ERROR = None


class RecommendationEngineTests(unittest.TestCase):
    def test_csv_profile_inference_prefers_charizard_and_base3(self) -> None:
        collection = engine.load_collection_from_csv(
            BACKEND_ROOT / "recommendation_engine" / "example_collection.csv"
        )

        enriched_collection = []
        for card in collection:
            enriched_card = dict(card)
            enriched_card["set_name"] = card["set_id"]
            enriched_card["rarity"] = "Holo Rare"
            enriched_card["category"] = "Trainer" if card["name"] == "Mr.Fuji" else "Pokemon"
            enriched_collection.append(enriched_card)

        profile = engine.infer_user_profile(enriched_collection, budget_usd=1000)

        self.assertEqual(profile["top_pokemon"][0]["name"], "Charizard")
        self.assertEqual(profile["top_pokemon"][0]["count"], 3)
        self.assertEqual(profile["top_sets"][0]["set_id"], "base3")
        self.assertEqual(profile["top_sets"][0]["count"], 5)
        self.assertEqual(profile["finish_affinity_status"], "ignored_v1")

    def test_build_candidate_pool_excludes_owned_cards(self) -> None:
        profile = {
            "top_sets": [{"set_id": "base3", "set_name": "Jungle", "count": 5}],
            "top_pokemon": [{"name": "Charizard", "count": 3}],
            "top_rarities": [{"rarity": "Holo Rare", "count": 3}],
        }
        owned_cards = [
            {
                "card_id": "base3-4",
                "set_id": "base3",
                "card_number": "4",
                "name": "Dragonite",
                "quantity": 1,
            }
        ]
        candidate_cards = [
            {
                "card_id": "base3-4",
                "set_id": "base3",
                "set_name": "Jungle",
                "card_number": "4",
                "name": "Dragonite",
                "rarity": "Holo Rare",
                "category": "Pokemon",
                "price_usd": 100.0,
                "image_url": None,
            },
            {
                "card_id": "base3-999",
                "set_id": "base3",
                "set_name": "Jungle",
                "card_number": "4",
                "name": "Dragonite alt",
                "rarity": "Holo Rare",
                "category": "Pokemon",
                "price_usd": 120.0,
                "image_url": None,
            },
            {
                "card_id": "base3-21",
                "set_id": "base3",
                "set_name": "Jungle",
                "card_number": "21",
                "name": "Charizard",
                "rarity": "Holo Rare",
                "category": "Pokemon",
                "price_usd": 250.0,
                "image_url": None,
            },
        ]

        with mock.patch.object(
            engine,
            "enrich_cards_with_tcgdex",
            return_value=candidate_cards,
        ):
            ranked = engine.build_candidate_pool(
                profile,
                owned_cards,
                budget_usd=1000,
                shortlist_size=10,
                candidate_cards=candidate_cards,
            )

        self.assertEqual([card["card_id"] for card in ranked], ["base3-21"])

    def test_apply_model_recommendations_falls_back_for_invalid_card_ids(self) -> None:
        shortlist = [
            {
                "card_id": "sv1-1",
                "name": "Charizard ex",
                "set_id": "sv1",
                "set_name": "Scarlet & Violet",
                "card_number": "1",
                "rarity": "Ultra Rare",
                "price_usd": 55.0,
                "price_status": "under_budget",
                "image_url": None,
                "deterministic_reason": "Matches your Charizard affinity.",
            },
            {
                "card_id": "sv1-2",
                "name": "Gengar ex",
                "set_id": "sv1",
                "set_name": "Scarlet & Violet",
                "card_number": "2",
                "rarity": "Ultra Rare",
                "price_usd": None,
                "price_status": "unknown",
                "image_url": None,
                "deterministic_reason": "Strong fit for your preferred rarities.",
            },
        ]

        result = engine.apply_model_recommendations(
            shortlist,
            1,
            model_payload={
                "profile_summary": "",
                "recommendations": [{"card_id": "made-up-card", "reason": "Bad choice"}],
            },
            profile={"top_pokemon": [], "top_sets": [], "top_rarities": []},
            budget_usd=1000,
        )

        self.assertEqual(result["recommendations"][0]["card_id"], "sv1-1")
        self.assertEqual(
            result["recommendations"][0]["reason"],
            "Matches your Charizard affinity.",
        )

    def test_price_status_unknown_when_price_missing(self) -> None:
        self.assertEqual(engine.price_status_for_budget(None, 1000), "unknown")
        self.assertEqual(engine.price_status_for_budget(999.99, 1000), "under_budget")
        self.assertEqual(engine.price_status_for_budget(1000.01, 1000), "over_budget")


@unittest.skipIf(backend_api is None, f"backend_api import failed: {BACKEND_API_IMPORT_ERROR}")
class RecommendationApiTests(unittest.TestCase):
    def test_recommendations_route_requires_user_id_for_supabase(self) -> None:
        request = backend_api.RecommendationRequest(source="supabase")
        with self.assertRaises(backend_api.HTTPException) as ctx:
            asyncio.run(backend_api.recommendations_route(request))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_recommendations_route_returns_recommendation_payload(self) -> None:
        request = backend_api.RecommendationRequest(source="csv", csv_path="example_collection.csv")
        expected = {
            "source": "csv",
            "budget_usd": 1000,
            "profile": {
                "budget_usd": 1000,
                "collection_size": 10,
                "top_pokemon": [],
                "top_sets": [],
                "top_rarities": [],
                "finish_affinity_status": "ignored_v1",
            },
            "profile_summary": "test summary",
            "recommendations": [],
        }

        with mock.patch.object(backend_api, "recommend_cards", return_value=expected):
            payload = asyncio.run(backend_api.recommendations_route(request))

        self.assertEqual(payload, expected)


if __name__ == "__main__":
    unittest.main()
