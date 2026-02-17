from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import torch

from .utils import embed_image, load_clip


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Pokemon card embedding index")
    parser.add_argument("--csv", default="cards.csv", help="Path to cards CSV")
    parser.add_argument("--ref_dir", default="data/refs", help="Directory for reference images")
    parser.add_argument("--out", default="data/index/index.npz", help="Output NPZ index path")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for quick testing")
    return parser.parse_args()


def download_image(url: str, out_path: Path) -> bool:
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        return True
    except Exception:
        return False


def main() -> None:
    args = parse_args()

    csv_path = Path(args.csv)
    ref_dir = Path(args.ref_dir)
    out_path = Path(args.out)

    ref_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    df = pd.read_csv(csv_path)
    id_col = "card_id" if "card_id" in df.columns else "id" if "id" in df.columns else None
    required = {"image_url"}
    if id_col is None:
        missing = {"card_id (or id)"} - set(df.columns)
        raise ValueError(f"Missing required columns in CSV: {sorted(missing)}")
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in CSV: {sorted(missing)}")

    if args.limit is not None:
        df = df.head(args.limit)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, processor = load_clip(device)

    card_ids: list[str] = []
    embeddings: list[np.ndarray] = []
    metadata_json: list[str] = []
    failed = 0

    for row in df.to_dict(orient="records"):
        card_id = str(row[id_col])
        image_url = str(row["image_url"])
        image_path = ref_dir / f"{card_id}.png"

        if not image_path.exists():
            ok = download_image(image_url, image_path)
            if not ok:
                failed += 1
                print(f"FAILED_DOWNLOAD {card_id} {image_url}", file=sys.stderr)
                continue

        try:
            emb = embed_image(str(image_path), model, processor, device)
        except Exception:
            failed += 1
            print(f"FAILED_EMBED {card_id} {image_path}", file=sys.stderr)
            continue

        card_ids.append(card_id)
        embeddings.append(emb.astype(np.float32))
        metadata_json.append(json.dumps(row, ensure_ascii=False))

    if embeddings:
        emb_matrix = np.vstack(embeddings).astype(np.float32)
    else:
        emb_matrix = np.empty((0, 0), dtype=np.float32)

    np.savez(
        out_path,
        card_ids=np.array(card_ids, dtype=object),
        embeddings=emb_matrix,
        metadata_json=np.array(metadata_json, dtype=object),
    )

    print(f"{len(card_ids)} indexed, {failed} failed")


if __name__ == "__main__":
    main()
