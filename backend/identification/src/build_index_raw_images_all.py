from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

from .utils import embed_image, load_clip


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one CLIP index from all images under dataset/raw_images"
    )
    parser.add_argument(
        "--raw_dir",
        default="dataset/raw_images",
        help="Root directory that contains card-set subfolders",
    )
    parser.add_argument(
        "--out",
        default="data/index/raw_images_all.npz",
        help="Output NPZ index path",
    )
    return parser.parse_args()


def list_all_images(raw_root: Path) -> list[Path]:
    return sorted(
        p
        for p in raw_root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".")
    )


def main() -> None:
    args = parse_args()
    raw_root = Path(args.raw_dir)
    out_path = Path(args.out)

    if not raw_root.exists():
        raise FileNotFoundError(f"Raw image directory not found: {raw_root}")
    if not raw_root.is_dir():
        raise NotADirectoryError(f"Not a directory: {raw_root}")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    image_paths = list_all_images(raw_root)
    if not image_paths:
        raise ValueError(f"No images found under {raw_root}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, processor = load_clip(device)

    card_ids: list[str] = []
    embeddings: list[np.ndarray] = []
    metadata_json: list[str] = []
    failed = 0

    total = len(image_paths)
    current_set = ""

    for idx, image_path in enumerate(image_paths, start=1):
        rel = image_path.relative_to(raw_root).as_posix()
        set_folder = image_path.parent.relative_to(raw_root).as_posix()
        if set_folder != current_set:
            current_set = set_folder
            print(f"\nSET {current_set}")

        percent = (idx / total) * 100.0
        print(
            f"\r[{idx}/{total}] {percent:6.2f}% | set={set_folder} | file={image_path.name}",
            end="",
            flush=True,
        )
        card_id = f"{set_folder}/{image_path.stem}"

        try:
            emb = embed_image(str(image_path), model, processor, device)
        except Exception as exc:
            failed += 1
            print(f"\nFAILED_EMBED {rel}: {exc}", file=sys.stderr)
            continue

        card_ids.append(card_id)
        embeddings.append(emb.astype(np.float32))
        metadata_json.append(
            json.dumps(
                {
                    "card_id": card_id,
                    "set_folder": set_folder,
                    "filename": image_path.name,
                    "image_path": rel,
                }
            )
        )

    emb_matrix = np.vstack(embeddings).astype(np.float32) if embeddings else np.empty((0, 0), dtype=np.float32)

    np.savez(
        out_path,
        card_ids=np.array(card_ids, dtype=object),
        embeddings=emb_matrix,
        metadata_json=np.array(metadata_json, dtype=object),
    )

    print()
    print(f"{len(card_ids)} indexed, {failed} failed -> {out_path}")


if __name__ == "__main__":
    main()
