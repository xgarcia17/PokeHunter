# Pokemon Card Identification CLI

Minimal local CLI for Pokemon card identification using CLIP image embeddings.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Build Reference Index

```bash
python -m src.build_index_raw_images_all --raw_dir dataset/raw_images --out data/index/raw_images_all.npz
```

## Identify a Query Card

```bash
python -m src.identify --index data/index/raw_images_all.npz --query data/test_images/ex12-1.png --topk 5
```

This command prints JSON to stdout and does not save images to a run folder.

## Batch Test Images

Put test images in:

```bash
data/test_images/
```

Run top-k matching for every image in that folder:

```bash
python -m src.identify_batch --index data/index/raw_images_all.npz --query_dir data/test_images --topk 5
```

Run on one image directly (no query folder):

```bash
python -m src.identify_batch --index data/index/raw_images_all.npz --query data/test_images/ex12-1.png --topk 5
```

Batch runs are saved under `data/results/run_YYYYMMDD_HHMMSS/` with:
- `results.json` (full top-k JSON output)
- one folder per query image containing:
  - the copied query image
  - `closest/` with ranked top-k reference images (`01_...`, `02_...`, etc.)

## Example Entrypoint Functions

If you want to call module entrypoints directly from Python code, these are the functions:

- `src.build_index_raw_images_all.main()`: builds `data/index/raw_images_all.npz`
- `src.identify.main()`: runs single-image identification and prints JSON
- `src.identify_batch.main()`: runs single/batch queries and saves run folders under `data/results/`

Example:

```python
from src.identify_batch import main

if __name__ == "__main__":
    main()
```

## Useful Command Examples

```bash
# One image -> saves run folder with closest images + results.json
python -m src.identify_batch --index data/index/raw_images_all.npz --query data/test_images/aero_test1.png --topk 5

# Whole folder -> one run folder with one subfolder per query image
python -m src.identify_batch --index data/index/raw_images_all.npz --query_dir data/test_images --topk 5
```

First run will download CLIP model weights (`openai/clip-vit-base-patch32`) from Hugging Face. After that, it runs locally without API keys.
