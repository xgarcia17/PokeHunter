from __future__ import annotations

import argparse
import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch
from PIL import Image

from .identify import load_metadata_by_card_id
from .utils import cosine_sim_matrix, embed_image, load_clip


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate card identification on noisy/warped random samples."
    )
    parser.add_argument(
        "--dataset_root",
        default="dataset_comp",
        help="Root containing source images (expects raw_images/* below this).",
    )
    parser.add_argument(
        "--index",
        default="data/index/dataset_comp_all.npz",
        help="Path to NPZ index.",
    )
    parser.add_argument("--sample_size", type=int, default=250, help="Number of random images to evaluate.")
    parser.add_argument("--topk", type=int, default=5, help="Top-k predictions to retain.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed.")
    parser.add_argument(
        "--out_dir",
        default="data/results",
        help="Directory where JSON results are written.",
    )
    return parser.parse_args()


def list_images(dataset_root: Path) -> list[Path]:
    return sorted(
        p
        for p in dataset_root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".")
    )


def _solve_perspective_coeffs(src: list[tuple[float, float]], dst: list[tuple[float, float]]) -> list[float]:
    matrix = []
    targets = []
    for (x, y), (u, v) in zip(src, dst):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        targets.append(u)
        targets.append(v)
    a = np.array(matrix, dtype=np.float64)
    b = np.array(targets, dtype=np.float64)
    coeffs = np.linalg.solve(a, b)
    return coeffs.tolist()


def apply_random_augmentations(image: Image.Image, rng: random.Random) -> Image.Image:
    image = image.convert("RGB")
    w, h = image.size

    # Random perspective warp.
    src = [(0.0, 0.0), (w - 1.0, 0.0), (w - 1.0, h - 1.0), (0.0, h - 1.0)]
    max_dx = w * rng.uniform(0.02, 0.10)
    max_dy = h * rng.uniform(0.02, 0.10)
    dst = [
        (rng.uniform(-max_dx, max_dx), rng.uniform(-max_dy, max_dy)),
        (w - 1.0 + rng.uniform(-max_dx, max_dx), rng.uniform(-max_dy, max_dy)),
        (w - 1.0 + rng.uniform(-max_dx, max_dx), h - 1.0 + rng.uniform(-max_dy, max_dy)),
        (rng.uniform(-max_dx, max_dx), h - 1.0 + rng.uniform(-max_dy, max_dy)),
    ]
    coeffs = _solve_perspective_coeffs(src, dst)
    warped = image.transform((w, h), Image.Transform.PERSPECTIVE, coeffs, resample=Image.Resampling.BICUBIC)

    arr = np.asarray(warped).astype(np.float32)

    # Gradient shading change.
    yy, xx = np.mgrid[0:h, 0:w]
    angle = rng.uniform(0, 2 * math.pi)
    direction = np.cos(angle) * xx + np.sin(angle) * yy
    direction = (direction - direction.min()) / (direction.max() - direction.min() + 1e-6)
    amp = rng.uniform(-0.30, 0.30)
    shading = (1.0 + amp * (direction - 0.5)).astype(np.float32)
    arr *= shading[..., None]

    # Additive gaussian noise.
    sigma = rng.uniform(6.0, 18.0)
    noise = np.random.normal(0.0, sigma, size=arr.shape).astype(np.float32)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)

    return Image.fromarray(arr, mode="RGB")


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    np.random.seed(args.seed)

    dataset_root = Path(args.dataset_root)
    index_path = Path(args.index)
    out_dir = Path(args.out_dir)

    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")
    if not index_path.exists():
        raise FileNotFoundError(f"Index not found: {index_path}")
    if args.sample_size < 1:
        raise ValueError("--sample_size must be >= 1")

    all_images = list_images(dataset_root)
    if not all_images:
        raise ValueError(f"No images found under {dataset_root}")

    sample_size = min(args.sample_size, len(all_images))
    samples = rng.sample(all_images, sample_size)

    data = np.load(index_path, allow_pickle=True)
    card_ids = data["card_ids"]
    embeddings = data["embeddings"].astype(np.float32)
    metadata_rows = load_metadata_by_card_id(data, card_ids)

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        raise ValueError("Index is empty or malformed")

    indexed_ids = {str(cid) for cid in card_ids}

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, processor = load_clip(device)

    results: list[dict] = []
    skipped = 0
    correct = 0
    confidence_sum = 0.0
    example_image_relpath: str | None = None

    with TemporaryDirectory(prefix="noisy_eval_") as tmp:
        tmp_dir = Path(tmp)
        # Save one side-by-side example so each run has a concrete visual of the augmentation.
        example_src = samples[0]
        example_aug = apply_random_augmentations(Image.open(example_src), rng)
        example_orig = Image.open(example_src).convert("RGB")
        comparison = Image.new("RGB", (example_orig.width * 2, example_orig.height))
        comparison.paste(example_orig, (0, 0))
        comparison.paste(example_aug, (example_orig.width, 0))

        for i, img_path in enumerate(samples, start=1):
            rel = img_path.relative_to(dataset_root).as_posix()
            true_card_id = Path(rel).with_suffix("").as_posix()
            if true_card_id not in indexed_ids:
                skipped += 1
                results.append(
                    {
                        "query_image": rel,
                        "true_card_id": true_card_id,
                        "skipped": True,
                        "reason": "true_card_id_not_in_index",
                    }
                )
                continue

            aug_image = apply_random_augmentations(Image.open(img_path), rng)
            tmp_query = tmp_dir / f"{i:04d}_{img_path.stem}.png"
            aug_image.save(tmp_query, format="PNG")

            q = embed_image(str(tmp_query), model, processor, device).astype(np.float32)
            scores = cosine_sim_matrix(embeddings, q)
            k = max(1, min(int(args.topk), scores.shape[0]))
            top_idx = np.argsort(scores)[::-1][:k]

            pred_card_id = str(card_ids[top_idx[0]])
            confidence = float(scores[top_idx[0]])
            is_correct = pred_card_id == true_card_id

            if is_correct:
                correct += 1
            confidence_sum += confidence

            top_k = [
                {
                    "card_id": str(card_ids[idx]),
                    "score": float(scores[idx]),
                    "source_row": metadata_rows[idx],
                }
                for idx in top_idx
            ]

            results.append(
                {
                    "query_image": rel,
                    "true_card_id": true_card_id,
                    "predicted_card_id": pred_card_id,
                    "correct": is_correct,
                    "confidence": confidence,
                    "top_k": top_k,
                }
            )
            print(f"[{i}/{sample_size}] {rel} -> {pred_card_id} | score={confidence:.4f} | correct={is_correct}")

    evaluated = sample_size - skipped
    accuracy = (correct / evaluated) if evaluated else 0.0
    avg_confidence = (confidence_sum / evaluated) if evaluated else 0.0

    now_utc = datetime.now(UTC)
    summary = {
        "timestamp_utc": now_utc.isoformat().replace("+00:00", "Z"),
        "dataset_root": str(dataset_root),
        "index": str(index_path),
        "sample_size_requested": int(args.sample_size),
        "sample_size_used": sample_size,
        "evaluated_count": evaluated,
        "skipped_count": skipped,
        "correct_count": correct,
        "accuracy": accuracy,
        "average_confidence": avg_confidence,
        "topk": int(args.topk),
        "seed": int(args.seed),
        "device": device,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = now_utc.strftime("%Y%m%d_%H%M%S")
    example_path = out_dir / f"noisy_eval_{run_stamp}_example_original_vs_augmented.png"
    comparison.save(example_path, format="PNG")
    example_image_relpath = str(example_path)

    out_path = out_dir / f"noisy_eval_{run_stamp}.json"
    summary["example_image"] = example_image_relpath
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Saved detailed results: {out_path}")


if __name__ == "__main__":
    main()
