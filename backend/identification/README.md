# Pokemon Card Identification CLI

Minimal local CLI for Pokemon card identification using CLIP image embeddings.

## Setup

```bash
pip install -r requirements.txt
```

## Build Reference Index

```bash
python -m src.build_index --csv cards.csv --ref_dir data/refs --out data/index/index.npz
```

## Identify a Query Card

```bash
python -m src.identify --index data/index/index.npz --query query.png --topk 5
```

## Batch Test Images

Put test images in:

```bash
data/test_images/
```

Run top-k matching for every image in that folder:

```bash
python -m src.identify_batch --index data/index/index.npz --query_dir data/test_images --topk 5
```

Run on one image directly (no query folder):

```bash
python -m src.identify_batch --index data/index/index.npz --query path/to/image.png --topk 5
```

Batch runs are saved under `data/results/run_YYYYMMDD_HHMMSS/` with:
- `results.json` (full top-k JSON output)
- one folder per query image containing:
  - the copied query image
  - `closest/` with ranked top-k reference images (`01_...`, `02_...`, etc.)

First run will download CLIP model weights (`openai/clip-vit-base-patch32`) from Hugging Face. After that, it runs locally without API keys.
