from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests


DEFAULT_TCGPLAYER_URL = (
    "https://www.tcgplayer.com/search/pokemon/sv-scarlet-and-violet-151"
    "?productLineName=pokemon&page=1&view=grid&setName=sv-scarlet-and-violet-151"
)


@dataclass
class TcgplayerCardRow:
    product_id: int | None
    name: str
    number: str | None
    market_price_usd: float | None
    raw_price_text: str | None
    product_url: str | None


@dataclass
class ComparisonRow:
    name: str
    number: str | None
    tcgplayer_market_price_usd: float | None
    api_price_usd: float | None
    delta_usd: float | None
    matched: bool
    notes: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold: compare TCGPlayer listing prices against our pricing API."
    )
    parser.add_argument("--tcgplayer-url", default=DEFAULT_TCGPLAYER_URL)
    parser.add_argument(
        "--pricing-api-url",
        default="http://127.0.0.1:8000/pricing-insight",
        help="Pricing API endpoint to test against (placeholder default).",
    )
    parser.add_argument(
        "--output-dir",
        default="pricing",
        help="Where to write scaffold outputs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max rows in final combined output (0 means no limit).",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="Number of pages to scrape (starting from page 1).",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=24,
        help="Number of results per page from the backing search API.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="HTTP timeout in seconds.",
    )
    return parser.parse_args()


def fetch_tcgplayer_html(url: str, timeout: float) -> str:
    resp = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            )
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def _to_float(price_text: str | None) -> float | None:
    if not price_text:
        return None
    cleaned = re.sub(r"[^0-9.]", "", price_text)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_card_number(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"#?\s*(\d{1,3})\s*/\s*\d{1,3}", value)
    if match:
        return match.group(1)
    return None


def _search_request_body(product_line_name: str, set_name: str, from_idx: int, page_size: int) -> dict[str, Any]:
    return {
        "algorithm": "",
        "from": from_idx,
        "size": page_size,
        "filters": {
            "term": {
                "productLineName": [product_line_name],
                "setName": [set_name],
            },
            "range": {},
            "match": {},
        },
        "listingSearch": {
            "context": {"cart": {}},
            "filters": {"term": {}},
        },
        "context": {"cart": {}, "shippingCountry": "US"},
    }


def fetch_tcgplayer_cards(tcgplayer_url: str, pages: int, page_size: int, timeout: float) -> list[TcgplayerCardRow]:
    parsed = urlparse(tcgplayer_url)
    query = parse_qs(parsed.query)
    product_line_name = (query.get("productLineName", ["pokemon"])[0] or "pokemon").strip().lower()
    set_name = (query.get("setName", [""])[0] or "").strip().lower()
    if not set_name:
        raise ValueError("setName query param is required in --tcgplayer-url")

    api_url = "https://mp-search-api.tcgplayer.com/v1/search/request"
    headers = {
        "origin": "https://www.tcgplayer.com",
        "referer": "https://www.tcgplayer.com/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
    }

    all_rows: list[TcgplayerCardRow] = []
    for page in range(1, pages + 1):
        from_idx = (page - 1) * page_size
        body = _search_request_body(product_line_name, set_name, from_idx, page_size)
        resp = requests.post(api_url, params={"q": "", "isList": "false"}, json=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        results = (payload.get("results") or [{}])[0].get("results") or []

        for item in results:
            custom_attrs = item.get("customAttributes") if isinstance(item.get("customAttributes"), dict) else {}
            number = _extract_card_number(custom_attrs.get("number")) or _extract_card_number(item.get("productName"))
            raw_market = item.get("marketPrice")
            market_price = _to_float(str(raw_market)) if raw_market is not None else None
            all_rows.append(
                TcgplayerCardRow(
                    product_id=int(item["productId"]) if isinstance(item.get("productId"), (int, float)) else None,
                    name=str(item.get("productName") or "").strip(),
                    number=number,
                    market_price_usd=market_price,
                    raw_price_text=str(raw_market) if raw_market is not None else None,
                    product_url=str(item.get("productUrlName") or "").strip() or None,
                )
            )
    return all_rows


def fetch_api_price_for_card(
    pricing_api_url: str, card: TcgplayerCardRow, timeout: float
) -> tuple[float | None, dict[str, Any] | None]:
    """
    Placeholder API adapter.

    This is intentionally conservative until you confirm your target endpoint contract.
    For now it sends a minimal payload to keep wiring in place and returns no price if
    the response does not include one.
    """
    payload = {
        "cards": [
            {
                "name": card.name,
                "set_name": "Scarlet & Violet 151",
                "price_usd": card.market_price_usd,
                "quantity": 1,
            }
        ],
        "budget_usd": 1000,
    }

    try:
        resp = requests.post(pricing_api_url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        return None, {"error": str(exc)}

    # Placeholder extraction; will be updated once you confirm endpoint response schema.
    candidate = data.get("price_usd") if isinstance(data, dict) else None
    price = float(candidate) if isinstance(candidate, (int, float)) else None
    return price, data if isinstance(data, dict) else None


def compare_prices(
    cards: list[TcgplayerCardRow], pricing_api_url: str, timeout: float
) -> list[ComparisonRow]:
    out: list[ComparisonRow] = []
    for card in cards:
        api_price, api_raw = fetch_api_price_for_card(pricing_api_url, card, timeout)
        delta = None
        matched = api_price is not None and card.market_price_usd is not None
        if matched:
            delta = round(api_price - card.market_price_usd, 4)
        note = None
        if api_price is None:
            note = "API price not parsed yet (scaffold mode)"
            if api_raw and "error" in api_raw:
                note = f"API error: {api_raw['error']}"
        out.append(
            ComparisonRow(
                name=card.name,
                number=card.number,
                tcgplayer_market_price_usd=card.market_price_usd,
                api_price_usd=api_price,
                delta_usd=delta,
                matched=matched,
                notes=note,
            )
        )
    return out


def write_outputs(output_dir: Path, cards: list[TcgplayerCardRow], comparisons: list[ComparisonRow]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "tcgplayer_scrape_rows.json"
    cmp_json_path = output_dir / "pricing_comparison_scaffold.json"
    cmp_csv_path = output_dir / "pricing_comparison_scaffold.csv"

    raw_path.write_text(
        json.dumps([asdict(c) for c in cards], indent=2, ensure_ascii=False), encoding="utf-8"
    )
    cmp_json_path.write_text(
        json.dumps([asdict(c) for c in comparisons], indent=2, ensure_ascii=False), encoding="utf-8"
    )

    with cmp_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(comparisons[0]).keys()) if comparisons else [])
        if comparisons:
            writer.writeheader()
            for row in comparisons:
                writer.writerow(asdict(row))

    print(f"Wrote: {raw_path}")
    print(f"Wrote: {cmp_json_path}")
    print(f"Wrote: {cmp_csv_path}")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    if args.pages < 1:
        raise ValueError("--pages must be >= 1")
    if args.page_size < 1:
        raise ValueError("--page-size must be >= 1")

    print(f"Fetching TCGPlayer pages 1..{args.pages}: {args.tcgplayer_url}")
    cards_raw = fetch_tcgplayer_cards(args.tcgplayer_url, args.pages, args.page_size, args.timeout)
    seen: set[str] = set()
    cards: list[TcgplayerCardRow] = []
    for card in cards_raw:
        key = str(card.product_id) if card.product_id is not None else f"{card.name}|{card.number}|{card.market_price_usd}"
        if key in seen:
            continue
        seen.add(key)
        cards.append(card)
        if args.limit > 0 and len(cards) >= args.limit:
            break
    print(f"Parsed {len(cards_raw)} rows across {args.pages} pages, kept {len(cards)} unique cards.")

    comparisons = compare_prices(cards, args.pricing_api_url, args.timeout)
    matched = sum(1 for c in comparisons if c.matched)
    print(f"Compared {len(comparisons)} rows. Matched price pairs: {matched}")
    print("Note: API mapping/parsing is placeholder until endpoint contract is finalized.")

    write_outputs(output_dir, cards, comparisons)


if __name__ == "__main__":
    main()
