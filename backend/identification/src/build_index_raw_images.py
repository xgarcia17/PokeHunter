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
        description="Build per-folder CLIP indexes from dataset/raw_images"
    )
    parser.add_argument(
        "--raw_dir",
        default="dataset/raw_images",
        help="Root directory that contains many card-set subfolders",
    )
    parser.add_argument(
        "--out_dir",
        default="data/index/raw_images",
        help="Output directory for per-folder NPZ indexes",
    )
    parser.add_argument(
        "--num_folders",
        type=int,
        default=2,
        help="How many top-level folders to index (default: 2)",
    )
    return parser.parse_args()


def list_image_files(folder: Path) -> list[Path]:
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".")
    )


def build_index_for_folder(
    folder: Path, raw_root: Path, out_dir: Path, model, processor, device: str
) -> tuple[int, int]:
    card_ids: list[str] = []
    embeddings: list[np.ndarray] = []
    metadata_json: list[str] = []
    failed = 0

    image_paths = list_image_files(folder)
    for image_path in image_paths:
        rel = image_path.relative_to(raw_root).as_posix()
        card_id = f"{folder.name}/{image_path.stem}"

        try:
            emb = embed_image(str(image_path), model, processor, device)
        except Exception:
            failed += 1
            print(f"FAILED_EMBED {rel}", file=sys.stderr)
            continue

        card_ids.append(card_id)
        embeddings.append(emb.astype(np.float32))
        metadata_json.append(
            json.dumps(
                {
                    "card_id": card_id,
                    "set_folder": folder.name,
                    "filename": image_path.name,
                    "image_path": rel,
                }
            )
        )

    if embeddings:
        emb_matrix = np.vstack(embeddings).astype(np.float32)
    else:
        emb_matrix = np.empty((0, 0), dtype=np.float32)

    out_path = out_dir / f"{folder.name}.npz"
    np.savez(
        out_path,
        card_ids=np.array(card_ids, dtype=object),
        embeddings=emb_matrix,
        metadata_json=np.array(metadata_json, dtype=object),
    )
    return len(card_ids), failed


def main() -> None:
    args = parse_args()
    raw_root = Path(args.raw_dir)
    out_dir = Path(args.out_dir)

    if args.num_folders <= 0:
        raise ValueError("--num_folders must be >= 1")
    if not raw_root.exists():
        raise FileNotFoundError(f"Raw image directory not found: {raw_root}")
    if not raw_root.is_dir():
        raise NotADirectoryError(f"Not a directory: {raw_root}")

    out_dir.mkdir(parents=True, exist_ok=True)

    folders = sorted(p for p in raw_root.iterdir() if p.is_dir() and not p.name.startswith("."))
    selected = folders[: args.num_folders]
    if not selected:
        raise ValueError(f"No subfolders found under {raw_root}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, processor = load_clip(device)

    total_ok = 0
    total_failed = 0
    for folder in selected:
        ok, failed = build_index_for_folder(folder, raw_root, out_dir, model, processor, device)
        total_ok += ok
        total_failed += failed
        print(f"{folder.name}: {ok} indexed, {failed} failed")

    print(
        f"done: {len(selected)} folders, {total_ok} total indexed, {total_failed} total failed"
    )


if __name__ == "__main__":
    main()
