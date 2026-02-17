from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from .utils import cosine_sim_matrix, embed_image, load_clip


SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


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
    parser = argparse.ArgumentParser(description="Identify top-k Pokemon cards for one image or all images in a directory")
    parser.add_argument("--index", default="data/index/index.npz", help="Path to NPZ index")
    parser.add_argument("--query", default=None, help="Single query image path")
    parser.add_argument("--query_dir", default="data/test_images", help="Directory containing query images")
    parser.add_argument("--topk", type=int, default=5, help="Number of top matches per image")
    parser.add_argument("--ref_dir", default="data/refs", help="Directory containing reference card images")
    parser.add_argument("--results_root", default="data/results", help="Root directory for saved run outputs")
    return parser.parse_args()


def safe_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in name)
    return cleaned.strip("._") or "query"


def main() -> None:
    args = parse_args()

    index_path = Path(args.index)
    query_dir = Path(args.query_dir)
    ref_dir = Path(args.ref_dir)
    results_root = Path(args.results_root)

    if not index_path.exists():
        raise FileNotFoundError(f"Index not found: {index_path}")
    if not ref_dir.exists() or not ref_dir.is_dir():
        raise FileNotFoundError(f"Reference directory not found: {ref_dir}")

    data = np.load(index_path, allow_pickle=True)
    card_ids = data["card_ids"]
    embeddings = data["embeddings"].astype(np.float32)
    metadata_rows = load_metadata_by_card_id(data, card_ids)

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        raise ValueError("Index is empty or malformed")

    if args.query:
        query_path = Path(args.query)
        if not query_path.exists() or not query_path.is_file():
            raise FileNotFoundError(f"Query image not found: {query_path}")
        if query_path.suffix.lower() not in SUPPORTED_EXTS:
            raise ValueError(f"Unsupported query image format: {query_path.suffix}")
        query_paths = [query_path]
    else:
        if not query_dir.exists() or not query_dir.is_dir():
            raise FileNotFoundError(f"Query directory not found: {query_dir}")
        query_paths = sorted(
            p for p in query_dir.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        )
    if not query_paths:
        raise ValueError(f"No query images found in: {query_dir}")

    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = results_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, processor = load_clip(device)

    k = max(1, min(int(args.topk), embeddings.shape[0]))
    results = []

    for query_path in query_paths:
        q = embed_image(str(query_path), model, processor, device).astype(np.float32)
        scores = cosine_sim_matrix(embeddings, q)
        top_idx = np.argsort(scores)[::-1][:k]
        top_k = [
            {
                "card_id": str(card_ids[i]),
                "score": float(scores[i]),
                "source_row": metadata_rows[i],
            }
            for i in top_idx
        ]

        query_out_dir = run_dir / safe_name(query_path.stem)
        closest_dir = query_out_dir / "closest"
        query_out_dir.mkdir(parents=True, exist_ok=True)
        closest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(query_path, query_out_dir / query_path.name)

        for rank, item in enumerate(top_k, start=1):
            card_id = item["card_id"]
            score = item["score"]
            src_img = ref_dir / f"{card_id}.png"
            if src_img.exists():
                dst_name = f"{rank:02d}_{card_id}_{score:.4f}.png"
                shutil.copy2(src_img, closest_dir / dst_name)

        results.append(
            {
                "query_image": query_path.name,
                "best_card_id": top_k[0]["card_id"],
                "score": top_k[0]["score"],
                "source_row": top_k[0]["source_row"],
                "top_k": top_k,
            }
        )

    (run_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
