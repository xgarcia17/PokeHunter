from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


TCGDEX_BASE_URL = "https://api.tcgdex.net/v2/en"
EUR_TO_USD_RATE = 1.08


@dataclass
class ScrapedRow:
    product_id: int | None
    name: str
    number: str | None
    market_price_usd: float | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare scraped TCGPlayer prices against frontend-equivalent TCGdex cardmarket trend price."
    )
    parser.add_argument("--input-json", default="pricing/tcgplayer_scrape_rows.json")
    parser.add_argument("--output-json", default="pricing/frontend_price_comparison_metrics.json")
    parser.add_argument(
        "--tcgdex-set-prefix",
        default="sv03.5",
        help="TCGdex set prefix used in card IDs, e.g. sv03.5 (card ID = sv03.5-<number>).",
    )
    parser.add_argument("--timeout", type=float, default=12.0)
    return parser.parse_args()


def to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def normalize_card_number(number: str | None) -> str | None:
    if not number:
        return None
    digits = "".join(ch for ch in number if ch.isdigit())
    return digits if digits else None


def convert_eur_to_usd(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value * EUR_TO_USD_RATE, 2)


def load_scraped_rows(path: Path) -> list[ScrapedRow]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows: list[ScrapedRow] = []
    for item in raw:
        rows.append(
            ScrapedRow(
                product_id=int(item["product_id"]) if isinstance(item.get("product_id"), int) else None,
                name=str(item.get("name") or "").strip(),
                number=str(item.get("number")).strip() if item.get("number") is not None else None,
                market_price_usd=to_float(item.get("market_price_usd")),
            )
        )
    return rows


def fetch_tcgdex_card(card_id: str, timeout: float) -> dict[str, Any] | None:
    url = f"{TCGDEX_BASE_URL}/cards/{card_id}"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 404:
            return None
        if not resp.ok:
            return None
        payload = resp.json()
        return payload if isinstance(payload, dict) else None
    except requests.RequestException:
        return None


def fetch_frontend_equivalent_price_usd(
    set_prefix: str,
    card_number: str | None,
    timeout: float,
    cache: dict[str, dict[str, Any] | None],
) -> tuple[float | None, str | None, dict[str, Any] | None]:
    normalized = normalize_card_number(card_number)
    if not normalized:
        return None, None, None

    candidates = [
        f"{set_prefix}-{normalized}",
        f"{set_prefix}-{int(normalized)}",
        f"{set_prefix}-{normalized.zfill(3)}",
    ]

    seen: set[str] = set()
    for card_id in candidates:
        if card_id in seen:
            continue
        seen.add(card_id)
        if card_id not in cache:
            cache[card_id] = fetch_tcgdex_card(card_id, timeout)
        payload = cache[card_id]
        if not payload:
            continue

        cardmarket = ((payload.get("pricing") or {}).get("cardmarket") or {})
        trend_eur = to_float(cardmarket.get("trend"))
        trend_usd = convert_eur_to_usd(trend_eur)
        if trend_usd is not None:
            return trend_usd, card_id, payload

    return None, None, None


def safe_mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def safe_median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def run_comparison(rows: list[ScrapedRow], set_prefix: str, timeout: float) -> dict[str, Any]:
    cache: dict[str, dict[str, Any] | None] = {}
    per_card: list[dict[str, Any]] = []

    signed_diffs: list[float] = []
    abs_diffs: list[float] = []
    pct_abs_diffs: list[float] = []

    for row in rows:
        frontend_price_usd, matched_card_id, tcgdex_payload = fetch_frontend_equivalent_price_usd(
            set_prefix=set_prefix,
            card_number=row.number,
            timeout=timeout,
            cache=cache,
        )

        signed_diff = None
        abs_diff = None
        abs_diff_pct = None

        if row.market_price_usd is not None and frontend_price_usd is not None:
            signed_diff = round(frontend_price_usd - row.market_price_usd, 4)
            abs_diff = abs(signed_diff)
            if row.market_price_usd > 0:
                abs_diff_pct = round((abs_diff / row.market_price_usd) * 100.0, 4)

            signed_diffs.append(signed_diff)
            abs_diffs.append(abs_diff)
            if abs_diff_pct is not None:
                pct_abs_diffs.append(abs_diff_pct)

        per_card.append(
            {
                "product_id": row.product_id,
                "card_name": row.name,
                "card_number": row.number,
                "tcgplayer_market_price_usd": row.market_price_usd,
                "frontend_price_usd": frontend_price_usd,
                "frontend_tcgdex_card_id": matched_card_id,
                "signed_diff_usd": signed_diff,
                "abs_diff_usd": abs_diff,
                "abs_diff_pct": abs_diff_pct,
                "tcgdex_card_name": (tcgdex_payload or {}).get("name") if tcgdex_payload else None,
            }
        )

    comparable_count = len(abs_diffs)
    rmse = math.sqrt(sum(d * d for d in signed_diffs) / comparable_count) if comparable_count else None

    within_010 = sum(1 for d in abs_diffs if d <= 0.10)
    within_025 = sum(1 for d in abs_diffs if d <= 0.25)
    within_050 = sum(1 for d in abs_diffs if d <= 0.50)

    outliers = sorted(
        (row for row in per_card if row["abs_diff_usd"] is not None),
        key=lambda r: r["abs_diff_usd"],
        reverse=True,
    )[:20]

    return {
        "summary": {
            "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "tcgdex_base_url": TCGDEX_BASE_URL,
            "tcgdex_set_prefix": set_prefix,
            "eur_to_usd_rate": EUR_TO_USD_RATE,
            "total_scraped_rows": len(rows),
            "comparable_rows": comparable_count,
            "missing_frontend_price_rows": sum(1 for r in per_card if r["frontend_price_usd"] is None),
            "missing_tcgplayer_price_rows": sum(1 for r in per_card if r["tcgplayer_market_price_usd"] is None),
            "average_signed_diff_usd": safe_mean(signed_diffs),
            "average_abs_diff_usd": safe_mean(abs_diffs),
            "median_abs_diff_usd": safe_median(abs_diffs),
            "rmse_usd": rmse,
            "mape_percent": safe_mean(pct_abs_diffs),
            "max_abs_diff_usd": max(abs_diffs) if abs_diffs else None,
            "min_abs_diff_usd": min(abs_diffs) if abs_diffs else None,
            "within_0_10_usd_count": within_010,
            "within_0_25_usd_count": within_025,
            "within_0_50_usd_count": within_050,
            "within_0_10_usd_rate": (within_010 / comparable_count) if comparable_count else None,
            "within_0_25_usd_rate": (within_025 / comparable_count) if comparable_count else None,
            "within_0_50_usd_rate": (within_050 / comparable_count) if comparable_count else None,
        },
        "outliers_top_abs_diff": outliers,
        "per_card": per_card,
    }


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_json)
    output_path = Path(args.output_json)

    if not input_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_path}")

    rows = load_scraped_rows(input_path)
    payload = run_comparison(rows, args.tcgdex_set_prefix, args.timeout)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote comparison JSON: {output_path}")
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
