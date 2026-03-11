from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from recommendation_engine import evaluate_recommendations as evaluation
from recommendation_engine import recommendation_engine as engine


class RecommendationEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        engine._RECOMMENDATION_CACHE.clear()
        engine._RECOMMENDATION_TRACE_CACHE.clear()

    def test_budget_fit_score_handles_missing_under_and_over_budget(self) -> None:
        self.assertEqual(evaluation.budget_fit_score(None, 1000), 0.5)
        self.assertEqual(evaluation.budget_fit_score(1000, 1000), 0.5)
        self.assertEqual(evaluation.budget_fit_score(0, 1000), 1.0)
        self.assertEqual(evaluation.budget_fit_score(2000, 1000), 0.0)

    def test_score_100_stays_within_bounds(self) -> None:
        profile = {
            "top_pokemon": [{"name": "Charizard", "count": 4}],
            "top_sets": [{"set_id": "base3", "set_name": "Jungle", "count": 2}],
            "top_rarities": [{"rarity": "Holo Rare", "count": 3}],
        }
        card = {
            "name": "Charizard ex",
            "set_id": "base3",
            "rarity": "Holo Rare",
            "price_usd": 250.0,
        }
        scores = evaluation.score_100(card, profile, "pokemon_affinity", 1000)
        self.assertGreaterEqual(scores["score_100"], 0.0)
        self.assertLessEqual(scores["score_100"], 100.0)
        self.assertGreater(scores["pokemon_weight"], 0.0)
        self.assertGreater(scores["set_weight"], 0.0)
        self.assertGreater(scores["rarity_weight"], 0.0)

    def test_extract_valid_gpt_selected_ids_ignores_invalid_and_duplicate_ids(self) -> None:
        trace = {
            "gpt_pool_groups": [
                {
                    "key": "pokemon_affinity",
                    "candidates": [{"card_id": "card-1", "name": "Charizard", "set_id": "sv1", "rarity": "Rare"}],
                },
                {
                    "key": "set_affinity",
                    "candidates": [{"card_id": "card-2", "name": "Pikachu", "set_id": "base3", "rarity": "Common"}],
                },
            ],
            "gpt_response_raw": {
                "recommendation_groups": [
                    {"key": "pokemon_affinity", "recommendations": [{"card_id": "card-1"}, {"card_id": "fake"}]},
                    {"key": "set_affinity", "recommendations": [{"card_id": "card-1"}, {"card_id": "card-2"}]},
                ]
            },
        }
        selected_by_group, invalid_by_group = evaluation.extract_valid_gpt_selected_ids(trace)
        self.assertEqual(selected_by_group["pokemon_affinity"], ["card-1"])
        self.assertEqual(selected_by_group["set_affinity"], ["card-2"])
        self.assertEqual(invalid_by_group["pokemon_affinity"], 1)
        self.assertEqual(invalid_by_group["set_affinity"], 1)

    def test_recommend_cards_with_trace_returns_pool_and_final_subset(self) -> None:
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
        candidate_pool = [
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
                "driver_key": "pokemon_affinity",
            }
        ]
        candidate_groups = [
            {
                "key": "pokemon_affinity",
                "title": "Pokemon Affinity",
                "focus": "Cards that match the Pokemon you collect most.",
                "target_count": 1,
                "candidates": candidate_pool,
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
                    "driver_key": "pokemon_affinity",
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
                return_value=(candidate_pool, {
                    "candidate_fetch_ms": 1.0,
                    "prefilter_count": 1,
                    "enriched_count": 1,
                    "tcgdex_enrichment_ms": 1.0,
                    "raw_candidate_count": 1,
                }),
            ),
            mock.patch.object(engine, "build_recommendation_candidate_groups", return_value=candidate_groups),
            mock.patch.object(engine, "_run_llm_recommender", return_value={
                "profile_summary": "summary",
                "recommendation_groups": [
                    {"key": "pokemon_affinity", "recommendations": [{"card_id": "base3-21", "reason": "GPT choice"}]}
                ],
            }),
            mock.patch.object(engine, "apply_model_recommendations", return_value=finalized),
        ):
            trace = engine.recommend_cards_with_trace(source="csv", csv_path="example_collection.csv")

        self.assertEqual(trace["recommendations"][0]["card_id"], "base3-21")
        self.assertEqual(trace["final_recommendation_groups"][0]["recommendations"][0]["card_id"], "base3-21")
        self.assertEqual(trace["gpt_pool_groups"][0]["candidates"][0]["card_id"], "base3-21")

    def test_run_evaluation_writes_cards_summary_and_trace_files(self) -> None:
        trace = {
            "source": "supabase",
            "budget_usd": 1000.0,
            "profile": {
                "top_pokemon": [{"name": "Charizard", "count": 3}],
                "top_sets": [{"set_id": "base3", "set_name": "Jungle", "count": 5}],
                "top_rarities": [{"rarity": "Holo Rare", "count": 4}],
            },
            "profile_summary": "summary",
            "recommendations": [],
            "recommendation_groups": [],
            "final_recommendation_groups": [
                {
                    "key": "pokemon_affinity",
                    "recommendations": [{"card_id": "card-1", "name": "Charizard", "set_id": "base3", "set_name": "Jungle", "card_number": "21", "rarity": "Holo Rare", "price_usd": 100.0}],
                }
            ],
            "gpt_pool_groups": [
                {
                    "key": "pokemon_affinity",
                    "title": "Pokemon Affinity",
                    "focus": "Cards that match the Pokemon you collect most.",
                    "target_count": 5,
                    "candidates": [
                        {"card_id": "card-1", "name": "Charizard", "set_id": "base3", "set_name": "Jungle", "card_number": "21", "rarity": "Holo Rare", "price_usd": 100.0, "price_status": "under_budget"},
                        {"card_id": "card-2", "name": "Pikachu", "set_id": "base3", "set_name": "Jungle", "card_number": "22", "rarity": "Common", "price_usd": 25.0, "price_status": "under_budget"},
                    ],
                }
            ],
            "gpt_response_raw": {
                "recommendation_groups": [
                    {"key": "pokemon_affinity", "recommendations": [{"card_id": "card-1", "reason": "Best match"}]}
                ]
            },
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            with mock.patch.object(evaluation.engine, "recommend_cards_with_trace", return_value=trace):
                artifacts = evaluation.run_evaluation(user_id="user-1", out_dir=out_dir)

            self.assertTrue(artifacts["cards_csv"].exists())
            self.assertTrue(artifacts["summary_json"].exists())
            self.assertTrue(artifacts["trace_json"].exists())

            with artifacts["cards_csv"].open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["group_key"], "pokemon_affinity")

            summary = json.loads(artifacts["summary_json"].read_text(encoding="utf-8"))
            self.assertIn("overall_pool_mean", summary)
            self.assertIn("pokemon_affinity", summary["per_group"])
            self.assertIn("scoring_formulas", summary)


if __name__ == "__main__":
    unittest.main()
