from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

ENGINE_PATH = Path(__file__).resolve().with_name("recommendation_engine.py")
ENGINE_SPEC = importlib.util.spec_from_file_location("recommendation_engine_module", ENGINE_PATH)
if ENGINE_SPEC is None or ENGINE_SPEC.loader is None:
    raise RuntimeError(f"Could not load recommendation engine module from {ENGINE_PATH}")
engine = importlib.util.module_from_spec(ENGINE_SPEC)
ENGINE_SPEC.loader.exec_module(engine)

GROUP_TITLES = {
    str(spec["key"]): str(spec["title"])
    for spec in engine.RECOMMENDATION_GROUP_SPECS
}
ALIGNMENT_WEIGHTS = {
    "pokemon_affinity": {"pokemon_weight": 0.50, "set_weight": 0.30, "rarity_weight": 0.20},
    "set_affinity": {"pokemon_weight": 0.30, "set_weight": 0.50, "rarity_weight": 0.20},
    "rarity_affinity": {"pokemon_weight": 0.20, "set_weight": 0.30, "rarity_weight": 0.50},
}
SCORING_FORMULAS = {
    "alignment": {
        "pokemon_affinity": "A_pokemon(c) = 0.50 * P(c) + 0.30 * S(c) + 0.20 * R(c)",
        "set_affinity": "A_set(c) = 0.50 * S(c) + 0.30 * P(c) + 0.20 * R(c)",
        "rarity_affinity": "A_rarity(c) = 0.50 * R(c) + 0.30 * S(c) + 0.20 * P(c)",
    },
    "budget_fit": {
        "missing_price": "B(c) = 0.50",
        "under_budget": "B(c) = 1 - 0.5 * (price_usd / budget_usd)",
        "over_budget": "B(c) = max(0, 0.5 - 0.5 * min(1, (price_usd - budget_usd) / budget_usd))",
    },
    "final_score": "Score_100(c, g) = round(100 * (0.80 * A_g(c) + 0.20 * B(c)), 2)",
    "lift": "Lift(g) = SelectedMean(g) - PoolMean(g)",
    "top_5_capture": "Top5Capture(g) = top-5 GPT-selected cards in group / GPT-selected cards in group",
}


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _profile_weight_maps(profile: dict[str, Any]) -> dict[str, dict[str, float]]:
    return {
        "pokemon_weights": {
            engine._compact_text(key): value
            for key, value in engine._weight_lookup(profile.get("top_pokemon", []), "name").items()
        },
        "set_weights": engine._weight_lookup(profile.get("top_sets", []), "set_id"),
        "rarity_weights": engine._weight_lookup(profile.get("top_rarities", []), "rarity"),
    }


def budget_fit_score(price_usd: float | None, budget_usd: float) -> float:
    if price_usd is None:
        return 0.50
    safe_budget = max(float(budget_usd), 1.0)
    if price_usd <= safe_budget:
        return max(0.0, 1.0 - 0.5 * (price_usd / safe_budget))
    over_ratio = min(1.0, (price_usd - safe_budget) / safe_budget)
    return max(0.0, 0.5 - 0.5 * over_ratio)


def component_weights(card: dict[str, Any], profile: dict[str, Any]) -> dict[str, float]:
    weight_maps = _profile_weight_maps(profile)
    card_name = str(card.get("name") or "")
    return {
        "pokemon_weight": engine._pokemon_name_match_weight(card_name, weight_maps["pokemon_weights"]),
        "set_weight": weight_maps["set_weights"].get(str(card.get("set_id") or "").strip(), 0.0),
        "rarity_weight": weight_maps["rarity_weights"].get(str(card.get("rarity") or "").strip(), 0.0),
    }


def alignment_score(group_key: str, weights: dict[str, float]) -> float:
    group_weights = ALIGNMENT_WEIGHTS[group_key]
    return round(
        group_weights["pokemon_weight"] * weights["pokemon_weight"]
        + group_weights["set_weight"] * weights["set_weight"]
        + group_weights["rarity_weight"] * weights["rarity_weight"],
        6,
    )


def score_100(card: dict[str, Any], profile: dict[str, Any], group_key: str, budget_usd: float) -> dict[str, float]:
    weights = component_weights(card, profile)
    budget_score = budget_fit_score(_as_float(card.get("price_usd")), budget_usd)
    affinity_score = alignment_score(group_key, weights)
    score = round(100 * (0.80 * affinity_score + 0.20 * budget_score), 2)
    return {
        **weights,
        "alignment_score": affinity_score,
        "budget_score": round(budget_score, 6),
        "score_100": score,
    }


def _group_pool_by_id(gpt_pool_groups: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        str(group.get("key") or ""): {
            str(card.get("card_id") or "").strip(): card
            for card in group.get("candidates", [])
            if str(card.get("card_id") or "").strip()
        }
        for group in gpt_pool_groups
    }


def extract_valid_gpt_selected_ids(trace: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, int]]:
    grouped_pool = _group_pool_by_id(trace.get("gpt_pool_groups", []))
    selected_by_group: dict[str, list[str]] = {key: [] for key in grouped_pool}
    invalid_by_group: dict[str, int] = {key: 0 for key in grouped_pool}
    used_ids: set[str] = set()

    raw_groups = []
    raw_payload = trace.get("gpt_response_raw")
    if isinstance(raw_payload, dict):
        raw_groups = raw_payload.get("recommendation_groups", []) or []

    for raw_group in raw_groups:
        group_key = str(raw_group.get("key") or "").strip()
        allowed_cards = grouped_pool.get(group_key, {})
        if not allowed_cards:
            continue
        for item in raw_group.get("recommendations", []) or []:
            card_id = str(item.get("card_id") or "").strip()
            if not card_id or card_id in used_ids or card_id not in allowed_cards:
                invalid_by_group[group_key] = invalid_by_group.get(group_key, 0) + 1
                continue
            selected_by_group.setdefault(group_key, []).append(card_id)
            used_ids.add(card_id)

    return selected_by_group, invalid_by_group


def build_cards_rows(trace: dict[str, Any]) -> list[dict[str, Any]]:
    profile = trace.get("profile", {})
    budget_usd = float(trace.get("budget_usd") or engine.DEFAULT_BUDGET_USD)
    selected_by_group, _ = extract_valid_gpt_selected_ids(trace)
    final_group_cards = {
        str(group.get("key") or ""): {
            str(card.get("card_id") or "").strip()
            for card in group.get("recommendations", [])
            if str(card.get("card_id") or "").strip()
        }
        for group in trace.get("final_recommendation_groups", [])
    }

    rows: list[dict[str, Any]] = []
    for group in trace.get("gpt_pool_groups", []):
        group_key = str(group.get("key") or "")
        candidates = list(group.get("candidates", []))
        scored_rows: list[dict[str, Any]] = []
        for candidate in candidates:
            card_id = str(candidate.get("card_id") or "").strip()
            scores = score_100(candidate, profile, group_key, budget_usd)
            scored_rows.append(
                {
                    "group_key": group_key,
                    "group_title": GROUP_TITLES.get(group_key, group_key),
                    "card_id": card_id,
                    "name": candidate.get("name"),
                    "set_id": candidate.get("set_id"),
                    "set_name": candidate.get("set_name"),
                    "card_number": candidate.get("card_number"),
                    "price_usd": _as_float(candidate.get("price_usd")),
                    "price_status": candidate.get("price_status"),
                    "selected_by_gpt": card_id in set(selected_by_group.get(group_key, [])),
                    "selected_in_final_response": card_id in final_group_cards.get(group_key, set()),
                    "pokemon_weight": round(scores["pokemon_weight"], 6),
                    "set_weight": round(scores["set_weight"], 6),
                    "rarity_weight": round(scores["rarity_weight"], 6),
                    "alignment_score": scores["alignment_score"],
                    "budget_score": scores["budget_score"],
                    "score_100": scores["score_100"],
                    "card_label": f"{candidate.get('name')} ({candidate.get('set_name') or candidate.get('set_id')} #{candidate.get('card_number')})",
                }
            )

        scored_rows.sort(
            key=lambda row: (
                -float(row["score_100"]),
                str(row.get("name") or "").lower(),
                str(row.get("card_id") or ""),
            )
        )
        for index, row in enumerate(scored_rows, start=1):
            row["rank_in_group_pool"] = index
        rows.extend(scored_rows)
    return rows


def summarize_rows(rows: list[dict[str, Any]], trace: dict[str, Any]) -> dict[str, Any]:
    selected_by_group, invalid_by_group = extract_valid_gpt_selected_ids(trace)
    summary = {
        "overall_pool_mean": 0.0,
        "overall_selected_mean": 0.0,
        "overall_lift": 0.0,
        "per_group": {},
        "scoring_formulas": SCORING_FORMULAS,
    }
    if not rows:
        return summary

    pool_scores = [float(row["score_100"]) for row in rows]
    selected_scores = [float(row["score_100"]) for row in rows if row["selected_by_gpt"]]
    summary["overall_pool_mean"] = round(mean(pool_scores), 2)
    summary["overall_selected_mean"] = round(mean(selected_scores), 2) if selected_scores else 0.0
    summary["overall_lift"] = round(summary["overall_selected_mean"] - summary["overall_pool_mean"], 2)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["group_key"]), []).append(row)

    for group_key, group_rows in grouped.items():
        group_pool_scores = [float(row["score_100"]) for row in group_rows]
        group_selected = [row for row in group_rows if row["selected_by_gpt"]]
        group_selected_scores = [float(row["score_100"]) for row in group_selected]
        selected_count = len(group_selected)
        top_5_ids = {row["card_id"] for row in group_rows if int(row["rank_in_group_pool"]) <= 5}
        top_5_hits = sum(1 for row in group_selected if row["card_id"] in top_5_ids)
        top_5_capture = round(top_5_hits / selected_count, 4) if selected_count else 0.0
        summary["per_group"][group_key] = {
            "title": GROUP_TITLES.get(group_key, group_key),
            "pool_count": len(group_rows),
            "selected_count": selected_count,
            "invalid_selection_count": int(invalid_by_group.get(group_key, 0)),
            "pool_mean": round(mean(group_pool_scores), 2),
            "selected_mean": round(mean(group_selected_scores), 2) if group_selected_scores else 0.0,
            "lift": round((mean(group_selected_scores) if group_selected_scores else 0.0) - mean(group_pool_scores), 2),
            "top_5_capture": top_5_capture,
            "selected_card_ids": selected_by_group.get(group_key, []),
        }
    return summary


def write_cards_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames = [
        "group_key",
        "group_title",
        "card_id",
        "name",
        "set_id",
        "set_name",
        "card_number",
        "price_usd",
        "price_status",
        "selected_by_gpt",
        "selected_in_final_response",
        "score_100",
        "pokemon_weight",
        "set_weight",
        "rarity_weight",
        "alignment_score",
        "budget_score",
        "rank_in_group_pool",
        "card_label",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_evaluation(
    *,
    user_id: str,
    budget_usd: float = engine.DEFAULT_BUDGET_USD,
    limit: int = engine.DEFAULT_LIMIT,
    force_refresh: bool = False,
    out_dir: Path | None = None,
) -> dict[str, Path]:
    output_dir = out_dir or (ROOT / "output" / "recommendation-evals" / user_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    trace = engine.recommend_cards_with_trace(
        source="supabase",
        user_id=user_id,
        budget_usd=budget_usd,
        limit=limit,
        force_refresh=force_refresh,
    )
    rows = build_cards_rows(trace)
    summary = summarize_rows(rows, trace)

    cards_path = output_dir / "cards.csv"
    summary_path = output_dir / "summary.json"
    trace_path = output_dir / "trace.json"

    write_cards_csv(rows, cards_path)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")

    return {
        "cards_csv": cards_path,
        "summary_json": summary_path,
        "trace_json": trace_path,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate GPT recommendation selections against the supplied candidate pool.")
    parser.add_argument("--user-id", required=True, help="Supabase user id to evaluate")
    parser.add_argument("--budget-usd", type=float, default=engine.DEFAULT_BUDGET_USD)
    parser.add_argument("--limit", type=int, default=engine.DEFAULT_LIMIT)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to output/recommendation-evals/<user_id>/",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    artifacts = run_evaluation(
        user_id=args.user_id,
        budget_usd=args.budget_usd,
        limit=args.limit,
        force_refresh=args.force_refresh,
        out_dir=args.out_dir,
    )
    print("Recommendation evaluation artifacts written:")
    for label, path in artifacts.items():
        print(f"- {label}: {path}")
    print("Scoring formulas:")
    print(json.dumps(SCORING_FORMULAS, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
