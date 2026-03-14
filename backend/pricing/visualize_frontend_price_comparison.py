from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create PNG dashboard from frontend price comparison metrics JSON.")
    parser.add_argument(
        "--input-json",
        default="pricing/frontend_price_comparison_metrics.json",
        help="Path to comparison metrics JSON.",
    )
    parser.add_argument(
        "--output-png",
        default=None,
        help="Output PNG path. Defaults to <input_stem>_dashboard.png",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_json)
    if not input_path.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    rows = payload.get("per_card", [])

    comparable = [r for r in rows if r.get("abs_diff_usd") is not None]
    diffs_abs = np.array([float(r["abs_diff_usd"]) for r in comparable], dtype=float) if comparable else np.array([])
    diffs_signed = np.array([float(r["signed_diff_usd"]) for r in comparable], dtype=float) if comparable else np.array([])
    x_price = np.array([float(r["tcgplayer_market_price_usd"]) for r in comparable], dtype=float) if comparable else np.array([])
    y_price = np.array([float(r["frontend_price_usd"]) for r in comparable], dtype=float) if comparable else np.array([])

    total = int(summary.get("total_scraped_rows", len(rows)))
    comp = int(summary.get("comparable_rows", len(comparable)))
    missing = int(summary.get("missing_frontend_price_rows", max(total - comp, 0)))

    fig, axs = plt.subplots(2, 1, figsize=(11, 9), constrained_layout=True)
    fig.suptitle(
        "TCGPlayer (External - Webscraped) vs TCGDex (Internal- API)",
        fontsize=16,
        fontweight="bold",
    )

    ax = axs[0]
    if diffs_abs.size:
        ax.hist(diffs_abs, bins=24, color="#3182bd", alpha=0.85, edgecolor="white")
        mean_abs = float(summary.get("average_abs_diff_usd", float(np.mean(diffs_abs))))
        median_abs = float(summary.get("median_abs_diff_usd", float(np.median(diffs_abs))))
        ax.axvline(mean_abs, color="red", linestyle="--", linewidth=1.5, label=f"Mean {mean_abs:.3f}")
        ax.axvline(median_abs, color="orange", linestyle="--", linewidth=1.5, label=f"Median {median_abs:.3f}")
        ax.legend(loc="upper right")
    ax.set_title("Absolute Difference (USD): TCGPlayer (External - Webscraped) vs TCGDex (Internal- API)")
    ax.set_xlabel("|frontend - tcgplayer|")
    ax.set_ylabel("Frequency")
    ax.grid(alpha=0.25)

    ax = axs[1]
    rates = [
        float(summary.get("within_0_10_usd_rate") or 0.0) * 100.0,
        float(summary.get("within_0_25_usd_rate") or 0.0) * 100.0,
        float(summary.get("within_0_50_usd_rate") or 0.0) * 100.0,
    ]
    labels = ["<= $0.10", "<= $0.25", "<= $0.50"]
    bars = ax.bar(labels, rates, color=["#66c2a4", "#41ab5d", "#238b45"])
    ax.set_ylim(0, 100)
    ax.set_title("Agreement Thresholds: TCGPlayer (External - Webscraped) vs TCGDex (Internal- API)")
    ax.set_ylabel("Percent of comparable cards")
    ax.grid(axis="y", alpha=0.25)
    for bar in bars:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{bar.get_height():.1f}%",
                ha="center", va="bottom", fontsize=9, fontweight="bold")

    text = (
        f"Rows: {total}\n"
        f"Comparable: {comp}\n"
        f"Avg signed diff: {summary.get('average_signed_diff_usd')}\n"
        f"Avg abs diff: {summary.get('average_abs_diff_usd')}\n"
        f"RMSE: {summary.get('rmse_usd')}\n"
        f"MAPE (%): {summary.get('mape_percent')}"
    )
    fig.text(
        0.72,
        0.67,
        text,
        ha="left",
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "#f6f6f6", "edgecolor": "#cccccc"},
    )

    output_path = Path(args.output_png) if args.output_png else input_path.with_name(f"{input_path.stem}_dashboard.png")
    fig.savefig(output_path, dpi=180)
    print(f"Saved dashboard PNG: {output_path}")


if __name__ == "__main__":
    main()
