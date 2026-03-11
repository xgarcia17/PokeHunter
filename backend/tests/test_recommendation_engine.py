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
    def setUp(self) -> None:
        engine._RECOMMENDATION_CACHE.clear()
        engine._PRICING_INSIGHT_CACHE.clear()

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

    def test_profile_inference_counts_quantity_when_category_missing(self) -> None:
        collection = [
            {
                "card_id": "sv1-17",
                "set_id": "sv1",
                "card_number": "17",
                "name": "Turtwig",
                "quantity": 2,
                "rarity": "Common",
                "category": None,
            }
        ]

        profile = engine.infer_user_profile(collection, budget_usd=1000)

        self.assertEqual(profile["collection_size"], 2)
        self.assertEqual(profile["top_pokemon"][0]["name"], "Turtwig")
        self.assertEqual(profile["top_pokemon"][0]["count"], 2)

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
            side_effect=lambda cards, include_images=True: cards,
        ):
            ranked, _ = engine.build_candidate_pool(
                profile,
                owned_cards,
                budget_usd=1000,
                shortlist_size=10,
                candidate_cards=candidate_cards,
            )

        self.assertEqual([card["card_id"] for card in ranked], ["base3-21"])

    def test_build_candidate_pool_enriches_only_top_20_candidates(self) -> None:
        profile = {
            "top_sets": [{"set_id": "base3", "set_name": "Jungle", "count": 5}],
            "top_pokemon": [{"name": "Charizard", "count": 3}],
            "top_rarities": [{"rarity": "Holo Rare", "count": 3}],
        }
        candidate_cards = [
            {
                "card_id": f"base3-{index}",
                "set_id": "base3",
                "set_name": "Jungle",
                "card_number": str(100 + index),
                "name": f"Charizard Variant {index}",
                "rarity": "Holo Rare",
                "category": "Pokemon",
                "price_usd": 50.0 + index,
                "image_url": None,
            }
            for index in range(25)
        ]

        captured_lengths: list[int] = []

        def passthrough(cards, include_images=True):
            captured_lengths.append(len(cards))
            return cards

        with mock.patch.object(engine, "enrich_cards_with_tcgdex", side_effect=passthrough):
            ranked, metrics = engine.build_candidate_pool(
                profile,
                [],
                budget_usd=1000,
                shortlist_size=20,
                candidate_cards=candidate_cards,
            )

        self.assertEqual(len(captured_lengths), 1)
        self.assertEqual(captured_lengths[0], 20)
        self.assertEqual(len(ranked), 20)
        self.assertEqual(metrics["enriched_count"], 20)

    def test_build_recommendation_candidate_groups_respects_bucket_focus(self) -> None:
        profile = {
            "top_sets": [{"set_id": "base3", "set_name": "Jungle", "count": 5}],
            "top_pokemon": [{"name": "Charizard", "count": 3}],
            "top_rarities": [{"rarity": "Holo Rare", "count": 4}],
        }
        candidates = [
            {
                "card_id": "charizard-1",
                "name": "Charizard ex",
                "set_id": "sv1",
                "set_name": "Scarlet & Violet",
                "card_number": "1",
                "rarity": "Ultra Rare",
                "category": "Pokemon",
                "price_usd": 55.0,
                "image_url": None,
            },
            {
                "card_id": "charizard-2",
                "name": "Charizard",
                "set_id": "swsh1",
                "set_name": "Sword & Shield",
                "card_number": "2",
                "rarity": "Rare",
                "category": "Pokemon",
                "price_usd": 75.0,
                "image_url": None,
            },
            {
                "card_id": "set-card-1",
                "name": "Pikachu",
                "set_id": "base3",
                "set_name": "Jungle",
                "card_number": "11",
                "rarity": "Common",
                "category": "Pokemon",
                "price_usd": 20.0,
                "image_url": None,
            },
            {
                "card_id": "set-card-2",
                "name": "Potion",
                "set_id": "base3",
                "set_name": "Jungle",
                "card_number": "21",
                "rarity": "Common",
                "category": "Trainer",
                "price_usd": 10.0,
                "image_url": None,
            },
            {
                "card_id": "rarity-card-1",
                "name": "Mewtwo",
                "set_id": "xy1",
                "set_name": "XY",
                "card_number": "50",
                "rarity": "Holo Rare",
                "category": "Pokemon",
                "price_usd": 45.0,
                "image_url": None,
            },
            {
                "card_id": "rarity-card-2",
                "name": "Switch",
                "set_id": "sv2",
                "set_name": "Paldea Evolved",
                "card_number": "100",
                "rarity": "Holo Rare",
                "category": "Trainer",
                "price_usd": 8.0,
                "image_url": None,
            },
        ]

        groups = engine.build_recommendation_candidate_groups(
            profile,
            candidates,
            budget_usd=1000,
            budget_policy="soft_cap",
            limit=15,
        )

        pokemon_group = next(group for group in groups if group["key"] == "pokemon_affinity")
        set_group = next(group for group in groups if group["key"] == "set_affinity")
        self.assertTrue(all("Charizard" in card["name"] for card in pokemon_group["candidates"][:2]))
        self.assertTrue(all(card["set_id"] == "base3" for card in set_group["candidates"][:2]))
        self.assertEqual({group["key"] for group in groups}, {"pokemon_affinity", "set_affinity"})

    def test_build_recommendation_candidate_groups_uses_configured_candidate_depth(self) -> None:
        profile = {
            "top_sets": [{"set_id": "base3", "set_name": "Jungle", "count": 5}],
            "top_pokemon": [{"name": "Charizard", "count": 3}],
            "top_rarities": [{"rarity": "Holo Rare", "count": 4}],
        }
        candidates = [
            {
                "card_id": f"rarity-{index}",
                "name": f"Card {index}",
                "set_id": "base3",
                "set_name": "Jungle",
                "card_number": str(index),
                "rarity": "Holo Rare",
                "category": "Trainer" if index % 2 else "Pokemon",
                "price_usd": 10.0 + index,
                "image_url": None,
            }
            for index in range(24)
        ] + [
            {
                "card_id": f"pokemon-{index}",
                "name": "Charizard",
                "set_id": "sv1",
                "set_name": "Scarlet & Violet",
                "card_number": str(100 + index),
                "rarity": "Rare",
                "category": "Pokemon",
                "price_usd": 20.0 + index,
                "image_url": None,
            }
            for index in range(12)
        ]

        groups = engine.build_recommendation_candidate_groups(
            profile,
            candidates,
            budget_usd=1000,
            budget_policy="soft_cap",
            limit=15,
        )

        pokemon_group = next(group for group in groups if group["key"] == "pokemon_affinity")
        set_group = next(group for group in groups if group["key"] == "set_affinity")

        self.assertEqual(len(pokemon_group["candidates"]), 10)
        self.assertEqual(len(set_group["candidates"]), 10)

    def test_build_recommendation_candidate_groups_has_no_rarity_bucket(self) -> None:
        profile = {
            "top_sets": [{"set_id": "sv1", "set_name": "Scarlet & Violet", "count": 2}],
            "top_pokemon": [{"name": "Turtwig", "count": 2}],
            "top_rarities": [],
        }
        candidates = [
            {
                "card_id": "sv1-1",
                "name": "Turtwig",
                "set_id": "sv1",
                "set_name": "Scarlet & Violet",
                "card_number": "1",
                "rarity": "Common",
                "category": "Pokemon",
                "price_usd": 2.0,
                "image_url": None,
            },
            {
                "card_id": "sv1-2",
                "name": "Potion",
                "set_id": "sv1",
                "set_name": "Scarlet & Violet",
                "card_number": "2",
                "rarity": "Uncommon",
                "category": "Trainer",
                "price_usd": 1.0,
                "image_url": None,
            },
        ]

        groups = engine.build_recommendation_candidate_groups(
            profile,
            candidates,
            budget_usd=1000,
            budget_policy="soft_cap",
            limit=15,
        )
        self.assertEqual({group["key"] for group in groups}, {"pokemon_affinity", "set_affinity"})

    def test_apply_model_recommendations_falls_back_for_invalid_or_duplicate_card_ids(self) -> None:
        candidate_groups = [
            {
                "key": "pokemon_affinity",
                "title": "Pokemon Affinity",
                "focus": "Cards that match the Pokemon you collect most.",
                "target_count": 1,
                "candidates": [
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
                        "driver_key": "pokemon_affinity",
                        "deterministic_reason": "Matches your Charizard affinity.",
                    }
                ],
            },
            {
                "key": "set_affinity",
                "title": "Set Affinity",
                "focus": "Cards that deepen the sets you already favor.",
                "target_count": 1,
                "candidates": [
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
                        "driver_key": "set_affinity",
                        "deterministic_reason": "Strong set fit.",
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
                        "driver_key": "set_affinity",
                        "deterministic_reason": "Backup set fit.",
                    },
                ],
            },
        ]

        result = engine.apply_model_recommendations(
            candidate_groups,
            model_payload={
                "profile_summary": "",
                "recommendation_groups": [
                    {
                        "key": "pokemon_affinity",
                        "recommendations": [{"card_id": "sv1-1", "reason": "Model chose Charizard."}],
                    },
                    {
                        "key": "set_affinity",
                        "recommendations": [{"card_id": "sv1-1", "reason": "Duplicate choice"}],
                    },
                ],
            },
            profile={"top_pokemon": [], "top_sets": [], "top_rarities": []},
            budget_usd=1000,
        )

        self.assertEqual(result["recommendations"][0]["card_id"], "sv1-1")
        self.assertEqual(result["recommendations"][0]["reason"], "Model chose Charizard.")
        self.assertEqual(result["recommendations"][1]["card_id"], "sv1-2")
        self.assertEqual(result["recommendations"][1]["reason"], "Backup set fit.")
        self.assertEqual(
            [group["key"] for group in result["recommendation_groups"]],
            ["pokemon_affinity", "set_affinity"],
        )

    def test_apply_model_recommendations_allows_overlap_when_later_group_would_be_empty(self) -> None:
        candidate_groups = [
            {
                "key": "pokemon_affinity",
                "title": "Pokemon Affinity",
                "focus": "Cards that match the Pokemon you collect most.",
                "target_count": 1,
                "candidates": [
                    {
                        "card_id": "sv1-1",
                        "name": "Turtwig",
                        "set_id": "sv1",
                        "set_name": "Scarlet & Violet",
                        "card_number": "1",
                        "rarity": "Common",
                        "price_usd": 2.0,
                        "price_status": "under_budget",
                        "image_url": None,
                        "driver_key": "pokemon_affinity",
                        "deterministic_reason": "Pokemon fit.",
                    }
                ],
            },
            {
                "key": "rarity_affinity",
                "title": "Rarity Affinity",
                "focus": "Cards that match the rarities you tend to keep.",
                "target_count": 1,
                "candidates": [
                    {
                        "card_id": "sv1-1",
                        "name": "Turtwig",
                        "set_id": "sv1",
                        "set_name": "Scarlet & Violet",
                        "card_number": "1",
                        "rarity": "Common",
                        "price_usd": 2.0,
                        "price_status": "under_budget",
                        "image_url": None,
                        "driver_key": "rarity_affinity",
                        "deterministic_reason": "Rarity fit.",
                    }
                ],
            },
        ]

        result = engine.apply_model_recommendations(
            candidate_groups,
            model_payload={"profile_summary": "", "recommendation_groups": []},
            profile={"top_pokemon": [], "top_sets": [], "top_rarities": []},
            budget_usd=1000,
        )

        pokemon_group = next(group for group in result["recommendation_groups"] if group["key"] == "pokemon_affinity")
        rarity_group = next(group for group in result["recommendation_groups"] if group["key"] == "rarity_affinity")
        self.assertEqual(len(pokemon_group["recommendations"]), 1)
        self.assertEqual(len(rarity_group["recommendations"]), 1)
        self.assertEqual(rarity_group["recommendations"][0]["card_id"], "sv1-1")

    def test_price_status_unknown_when_price_missing(self) -> None:
        self.assertEqual(engine.price_status_for_budget(None, 1000), "unknown")
        self.assertEqual(engine.price_status_for_budget(999.99, 1000), "under_budget")
        self.assertEqual(engine.price_status_for_budget(1000.01, 1000), "over_budget")

    def test_recommend_cards_uses_cache_for_same_collection_signature(self) -> None:
        collection = [
            {
                "card_id": None,
                "set_id": "base3",
                "card_number": "4",
                "name": "Dragonite",
                "quantity": 1,
                "price_usd": None,
            }
        ]
        enriched_collection = [
            {
                **collection[0],
                "set_name": "Jungle",
                "rarity": "Holo Rare",
                "category": "Pokemon",
            }
        ]
        shortlist = [
            {
                "card_id": "base3-21",
                "name": "Charizard",
                "set_id": "base3",
                "set_name": "Jungle",
                "card_number": "21",
                "rarity": "Holo Rare",
                "price_usd": 100.0,
                "price_status": "under_budget",
                "image_url": None,
                "deterministic_reason": "Matches your collection.",
            }
        ]
        finalized = {
            "profile_summary": "summary",
            "recommendations": [
                {
                    "card_id": "base3-21",
                    "name": "Charizard",
                    "set_id": "base3",
                    "set_name": "Jungle",
                    "card_number": "21",
                    "rarity": "Holo Rare",
                    "price_usd": 100.0,
                    "price_status": "under_budget",
                    "image_url": None,
                    "reason": "Matches your collection.",
                }
            ],
            "recommendation_groups": [
                {
                    "key": "pokemon_affinity",
                    "title": "Pokemon Affinity",
                    "focus": "Cards that match the Pokemon you collect most.",
                    "recommendations": [
                        {
                            "card_id": "base3-21",
                            "name": "Charizard",
                            "set_id": "base3",
                            "set_name": "Jungle",
                            "card_number": "21",
                            "rarity": "Holo Rare",
                            "price_usd": 100.0,
                            "price_status": "under_budget",
                            "image_url": None,
                            "reason": "Matches your collection.",
                            "driver_key": "pokemon_affinity",
                        }
                    ],
                }
            ],
        }
        profile = {
            "budget_usd": 1000,
            "collection_size": 1,
            "top_pokemon": [{"name": "Dragonite", "count": 1}],
            "top_sets": [{"set_id": "base3", "set_name": "Jungle", "count": 1}],
            "top_rarities": [{"rarity": "Holo Rare", "count": 1}],
            "finish_affinity_status": "ignored_v1",
        }

        with (
            mock.patch.object(engine, "load_collection_from_csv", return_value=collection),
            mock.patch.object(engine, "enrich_cards_with_tcgdex", return_value=enriched_collection),
            mock.patch.object(engine, "infer_user_profile", return_value=profile),
            mock.patch.object(engine, "build_candidate_pool", return_value=(shortlist, {
                "candidate_fetch_ms": 1.0,
                "prefilter_count": 1,
                "enriched_count": 1,
                "tcgdex_enrichment_ms": 1.0,
                "raw_candidate_count": 1,
            })) as build_pool,
            mock.patch.object(engine, "_run_llm_recommender", return_value={"recommendation_groups": []}) as llm_call,
            mock.patch.object(engine, "apply_model_recommendations", return_value=finalized),
        ):
            first = engine.recommend_cards(source="csv", csv_path="example_collection.csv")
            second = engine.recommend_cards(source="csv", csv_path="example_collection.csv")

        self.assertEqual(first, second)
        self.assertEqual(build_pool.call_count, 1)
        self.assertEqual(llm_call.call_count, 1)

    def test_recommend_cards_force_refresh_bypasses_cache(self) -> None:
        collection = [
            {
                "card_id": None,
                "set_id": "base3",
                "card_number": "4",
                "name": "Dragonite",
                "quantity": 1,
                "price_usd": None,
            }
        ]
        enriched_collection = [
            {
                **collection[0],
                "set_name": "Jungle",
                "rarity": "Holo Rare",
                "category": "Pokemon",
            }
        ]
        shortlist = [
            {
                "card_id": "base3-21",
                "name": "Charizard",
                "set_id": "base3",
                "set_name": "Jungle",
                "card_number": "21",
                "rarity": "Holo Rare",
                "price_usd": 100.0,
                "price_status": "under_budget",
                "image_url": None,
                "deterministic_reason": "Matches your collection.",
            }
        ]
        finalized = {
            "profile_summary": "summary",
            "recommendations": [
                {
                    "card_id": "base3-21",
                    "name": "Charizard",
                    "set_id": "base3",
                    "set_name": "Jungle",
                    "card_number": "21",
                    "rarity": "Holo Rare",
                    "price_usd": 100.0,
                    "price_status": "under_budget",
                    "image_url": None,
                    "reason": "Matches your collection.",
                }
            ],
            "recommendation_groups": [
                {
                    "key": "pokemon_affinity",
                    "title": "Pokemon Affinity",
                    "focus": "Cards that match the Pokemon you collect most.",
                    "recommendations": [
                        {
                            "card_id": "base3-21",
                            "name": "Charizard",
                            "set_id": "base3",
                            "set_name": "Jungle",
                            "card_number": "21",
                            "rarity": "Holo Rare",
                            "price_usd": 100.0,
                            "price_status": "under_budget",
                            "image_url": None,
                            "reason": "Matches your collection.",
                            "driver_key": "pokemon_affinity",
                        }
                    ],
                }
            ],
        }
        profile = {
            "budget_usd": 1000,
            "collection_size": 1,
            "top_pokemon": [{"name": "Dragonite", "count": 1}],
            "top_sets": [{"set_id": "base3", "set_name": "Jungle", "count": 1}],
            "top_rarities": [{"rarity": "Holo Rare", "count": 1}],
            "finish_affinity_status": "ignored_v1",
        }

        with (
            mock.patch.object(engine, "load_collection_from_csv", return_value=collection),
            mock.patch.object(engine, "enrich_cards_with_tcgdex", return_value=enriched_collection),
            mock.patch.object(engine, "infer_user_profile", return_value=profile),
            mock.patch.object(
                engine,
                "build_candidate_pool",
                return_value=(
                    shortlist,
                    {
                        "candidate_fetch_ms": 1.0,
                        "prefilter_count": 1,
                        "enriched_count": 1,
                        "tcgdex_enrichment_ms": 1.0,
                        "raw_candidate_count": 1,
                    },
                ),
            ) as build_pool,
            mock.patch.object(engine, "_run_llm_recommender", return_value={"recommendation_groups": []}) as llm_call,
            mock.patch.object(engine, "apply_model_recommendations", return_value=finalized),
        ):
            first = engine.recommend_cards(source="csv", csv_path="example_collection.csv")
            second = engine.recommend_cards(
                source="csv",
                csv_path="example_collection.csv",
                force_refresh=True,
            )

        self.assertEqual(first, second)
        self.assertEqual(build_pool.call_count, 2)
        self.assertEqual(llm_call.call_count, 2)

    def test_generate_pricing_insight_uses_cache_for_same_collection_signature(self) -> None:
        cards = [
            {
                "name": "Turtwig",
                "set_name": "Scarlet & Violet",
                "price_usd": 2.5,
                "quantity": 2,
                "date_added": "2026-03-10T12:00:00Z",
            },
            {
                "name": "Charizard",
                "set_name": "Base Set",
                "price_usd": 100.0,
                "quantity": 1,
                "date_added": "2026-03-08T12:00:00Z",
            },
        ]
        reordered_cards = [cards[1], cards[0]]
        llm_payload = {
            "insight": "Collection value concentration is healthy.",
            "highlights": ["Top value anchored by Charizard."],
        }

        with mock.patch.object(engine, "_run_llm_pricing_analyst", return_value=llm_payload) as llm_call:
            first = engine.generate_pricing_insight(cards, budget_usd=1000)
            second = engine.generate_pricing_insight(reordered_cards, budget_usd=1000)

        self.assertEqual(first, second)
        self.assertEqual(llm_call.call_count, 1)
        self.assertEqual(first["source"], "llm")

    def test_generate_pricing_insight_cache_miss_when_collection_changes(self) -> None:
        cards = [
            {
                "name": "Turtwig",
                "set_name": "Scarlet & Violet",
                "price_usd": 2.5,
                "quantity": 2,
                "date_added": "2026-03-10T12:00:00Z",
            }
        ]
        changed_cards = [
            {
                "name": "Turtwig",
                "set_name": "Scarlet & Violet",
                "price_usd": 2.5,
                "quantity": 3,
                "date_added": "2026-03-10T12:00:00Z",
            }
        ]
        llm_payload = {
            "insight": "Collection momentum is improving.",
            "highlights": ["Recent adds are accelerating."],
        }

        with mock.patch.object(engine, "_run_llm_pricing_analyst", return_value=llm_payload) as llm_call:
            engine.generate_pricing_insight(cards, budget_usd=1000)
            engine.generate_pricing_insight(changed_cards, budget_usd=1000)

        self.assertEqual(llm_call.call_count, 2)


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

    def test_pricing_insight_route_returns_payload(self) -> None:
        request = backend_api.PricingInsightRequest(
            cards=[
                backend_api.PricingInsightCard(
                    name="Turtwig",
                    set_name="Scarlet & Violet",
                    price_usd=2.5,
                    quantity=2,
                    date_added="2026-03-10T12:00:00Z",
                )
            ],
            budget_usd=1000,
        )
        expected = {
            "source": "llm",
            "insight": "Your collection is healthy and growing.",
            "highlights": ["Strong set concentration in Scarlet & Violet."],
            "stats": {"card_count": 2},
        }

        with mock.patch.object(backend_api, "generate_pricing_insight", return_value=expected):
            payload = asyncio.run(backend_api.pricing_insight_route(request))

        self.assertEqual(payload, expected)


if __name__ == "__main__":
    unittest.main()
