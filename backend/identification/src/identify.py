from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from .utils import cosine_sim_matrix, embed_image, load_clip


def load_metadata_by_card_id(index_data, card_ids: np.ndarray) -> list[dict | None]:
    if "metadata_json" not in index_data:
        return [None] * len(card_ids)
    metadata_raw = index_data["metadata_json"]
    if len(metadata_raw) != len(card_ids):
        return [None] * len(card_ids)
    out: list[dict | None] = []
    for item in metadata_raw:
        try:
            out.append(json.loads(str(item)))
        except Exception:
            out.append(None)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Identify best-matching Pokemon card")
    parser.add_argument("--index", default="data/index/index.npz", help="Path to NPZ index")
    parser.add_argument("--query", required=True, help="Path to query PNG/JPG")
    parser.add_argument("--topk", type=int, default=5, help="Number of top matches")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    index_path = Path(args.index)
    query_path = Path(args.query)

    if not index_path.exists():
        raise FileNotFoundError(f"Index not found: {index_path}")
    if not query_path.exists():
        raise FileNotFoundError(f"Query image not found: {query_path}")

    data = np.load(index_path, allow_pickle=True)
    card_ids = data["card_ids"]
    embeddings = data["embeddings"].astype(np.float32)
    metadata_rows = load_metadata_by_card_id(data, card_ids)

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        raise ValueError("Index is empty or malformed")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, processor = load_clip(device)
    q = embed_image(str(query_path), model, processor, device).astype(np.float32)

    scores = cosine_sim_matrix(embeddings, q)
    k = max(1, min(int(args.topk), scores.shape[0]))

    top_idx = np.argsort(scores)[::-1][:k]
    top_k = [
        {
            "card_id": str(card_ids[i]),
            "score": float(scores[i]),
            "source_row": metadata_rows[i],
        }
        for i in top_idx
    ]

    result = {
        "best_card_id": top_k[0]["card_id"],
        "score": top_k[0]["score"],
        "source_row": top_k[0]["source_row"],
        "top_k": top_k,
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
