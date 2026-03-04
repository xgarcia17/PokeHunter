from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
import torch

from .utils import cosine_sim_matrix, embed_image, load_clip


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch identify Pokemon cards and save run outputs")
    parser.add_argument("--index", default="data/index/index.npz", help="Path to NPZ index")
    parser.add_argument("--query_dir", help="Directory of query images")
    parser.add_argument("--query", help="Single query image path")
    parser.add_argument("--topk", type=int, default=5, help="Number of top matches")
    parser.add_argument("--out_dir", default="data/results", help="Root output directory for runs")
    parser.add_argument(
        "--raw_dir",
        default="dataset/raw_images",
        help="Root directory for indexed reference images",
    )
    parser.add_argument(
        "--ref_dir",
        default="data/refs",
        help="Fallback directory for reference images (flat or nested by card_id)",
    )
    return parser.parse_args()


def load_metadata(index_data, card_ids: np.ndarray) -> list[dict | None]:
    if "metadata_json" not in index_data:
        return [None] * len(card_ids)
    metadata_raw = index_data["metadata_json"]
    if len(metadata_raw) != len(card_ids):
        return [None] * len(card_ids)

    parsed: list[dict | None] = []
    for item in metadata_raw:
        try:
            parsed.append(json.loads(str(item)))
        except Exception:
            parsed.append(None)
    return parsed


def collect_queries(query: str | None, query_dir: str | None) -> list[Path]:
    if query and query_dir:
        raise ValueError("Use either --query or --query_dir, not both")
    if not query and not query_dir:
        raise ValueError("Pass one of --query or --query_dir")

    if query:
        q = Path(query)
        if not q.exists():
            raise FileNotFoundError(f"Query image not found: {q}")
        if not q.is_file():
            raise ValueError(f"Query path is not a file: {q}")
        return [q]

    root = Path(query_dir)  # type: ignore[arg-type]
    if not root.exists():
        raise FileNotFoundError(f"Query directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a query directory: {root}")

    queries = sorted(
        p for p in root.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".")
    )
    if not queries:
        raise ValueError(f"No query images found in {root}")
    return queries


def sanitize_for_filename(value: str) -> str:
    return value.replace("/", "_").replace("\\", "_").replace(" ", "_")


def unique_subdir(base_dir: Path, preferred_name: str) -> Path:
    candidate = base_dir / preferred_name
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = base_dir / f"{preferred_name}_{n}"
        if not candidate.exists():
            return candidate
        n += 1


def resolve_reference_path(card_id: str, metadata: dict | None, raw_dir: Path, ref_dir: Path) -> Path | None:
    candidates: list[Path] = []

    if metadata:
        image_path = metadata.get("image_path")
        if isinstance(image_path, str) and image_path:
            candidates.append(raw_dir / image_path)
        set_folder = metadata.get("set_folder")
        filename = metadata.get("filename")
        if isinstance(set_folder, str) and isinstance(filename, str) and set_folder and filename:
            candidates.append(raw_dir / set_folder / filename)
        if isinstance(filename, str) and filename:
            candidates.append(ref_dir / filename)

    candidates.append(ref_dir / card_id)
    candidates.append(ref_dir / f"{card_id}.png")
    candidates.append(ref_dir / f"{card_id}.jpg")
    candidates.append(ref_dir / f"{card_id}.jpeg")
    candidates.append(raw_dir / card_id)
    candidates.append(raw_dir / f"{card_id}.png")
    candidates.append(raw_dir / f"{card_id}.jpg")
    candidates.append(raw_dir / f"{card_id}.jpeg")

    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def main() -> None:
    args = parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        raise FileNotFoundError(f"Index not found: {index_path}")

    query_paths = collect_queries(args.query, args.query_dir)

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    run_name = datetime.now().strftime("run_%Y%m%d_%H%M%S")
    run_dir = out_root / run_name
    run_dir.mkdir(parents=True, exist_ok=False)

    data = np.load(index_path, allow_pickle=True)
    card_ids = data["card_ids"]
    embeddings = data["embeddings"].astype(np.float32)
    metadata_rows = load_metadata(data, card_ids)

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        raise ValueError("Index is empty or malformed")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, processor = load_clip(device)

    raw_dir = Path(args.raw_dir)
    ref_dir = Path(args.ref_dir)

    all_results: list[dict] = []

    total = len(query_paths)
    for n, query_path in enumerate(query_paths, start=1):
        print(f"[{n}/{total}] {query_path.name}")
        q = embed_image(str(query_path), model, processor, device).astype(np.float32)
        scores = cosine_sim_matrix(embeddings, q)
        k = max(1, min(int(args.topk), scores.shape[0]))
        top_idx = np.argsort(scores)[::-1][:k]

        top_k: list[dict] = []
        for i in top_idx:
            top_k.append(
                {
                    "card_id": str(card_ids[i]),
                    "score": float(scores[i]),
                }
            )

        result = {
            "query_image": query_path.name,
            "best_card_id": top_k[0]["card_id"],
            "score": top_k[0]["score"],
            "top_k": top_k,
        }
        all_results.append(result)

        query_dir_out = unique_subdir(run_dir, sanitize_for_filename(query_path.stem))
        query_dir_out.mkdir(parents=True, exist_ok=False)
        shutil.copy2(query_path, query_dir_out / query_path.name)

        closest_dir = query_dir_out / "closest"
        closest_dir.mkdir(parents=True, exist_ok=True)

        for rank, i in enumerate(top_idx, start=1):
            card_id = str(card_ids[i])
            score = float(scores[i])
            metadata = metadata_rows[i] if i < len(metadata_rows) else None
            ref_path = resolve_reference_path(card_id, metadata, raw_dir, ref_dir)
            if ref_path is None:
                continue

            safe_card = sanitize_for_filename(card_id)
            dest_name = f"{rank:02d}_{safe_card}_{score:.4f}{ref_path.suffix.lower()}"
            shutil.copy2(ref_path, closest_dir / dest_name)

    results_path = run_dir / "results.json"
    with results_path.open("w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"Saved results: {results_path}")


if __name__ == "__main__":
    main()
