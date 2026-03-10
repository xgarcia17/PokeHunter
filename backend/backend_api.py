from __future__ import annotations

import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from http_compat import RequestException, get as http_get
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local dependency
    def load_dotenv(*_args, **_kwargs):
        return False

from recommendation_engine.recommendation_engine import (
    DEFAULT_BUDGET_USD,
    DEFAULT_LIMIT,
    recommend_cards,
)

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional until identify is used
    np = None  # type: ignore[assignment]

try:
    import torch
except ImportError:  # pragma: no cover - optional until identify is used
    torch = None  # type: ignore[assignment]

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional until identify is used
    Image = None  # type: ignore[assignment]

try:
    from identification.src.identify import load_metadata_by_card_id
    from identification.src.utils import cosine_sim_matrix, load_clip
except ImportError:  # pragma: no cover - optional until identify is used
    load_metadata_by_card_id = None  # type: ignore[assignment]
    cosine_sim_matrix = None  # type: ignore[assignment]
    load_clip = None  # type: ignore[assignment]

load_dotenv(Path(__file__).resolve().with_name(".env"))

DEFAULT_INDEX_PATH = "identification/data/index/dataset_comp_all.npz"
INDEX_PATH = os.getenv("IDENTIFICATION_INDEX_PATH", DEFAULT_INDEX_PATH)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "pokemon-images")


class AppState:
    def __init__(self) -> None:
        self.model = None
        self.processor = None
        self.device = None
        self.card_ids = None
        self.embeddings = None
        self.metadata_rows = None
        self.storage_path_to_card_ref = {}


state = AppState()


class RecommendationRequest(BaseModel):
    source: str = "supabase"
    user_id: str | None = None
    csv_path: str | None = None
    budget_usd: float = Field(default=DEFAULT_BUDGET_USD, ge=0)
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=15)
    force_refresh: bool = False


def ensure_identification_dependencies_available() -> None:
    missing: list[str] = []
    if np is None:
        missing.append("numpy")
    if torch is None:
        missing.append("torch")
    if Image is None:
        missing.append("Pillow")
    if load_clip is None or cosine_sim_matrix is None or load_metadata_by_card_id is None:
        missing.append("identification runtime")
    if missing:
        raise RuntimeError(
            "Identification dependencies are unavailable: " + ", ".join(missing)
        )


def supabase_headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }


def fetch_all_rows(table: str, select_cols: str) -> list[dict]:
    rows: list[dict] = []
    limit = 1000
    offset = 0
    while True:
        headers = {**supabase_headers(), "Range-Unit": "items", "Range": f"{offset}-{offset + limit - 1}"}
        url = f"{SUPABASE_URL}/rest/v1/{table}?select={select_cols}"
        response = http_get(url, headers=headers, timeout=30)
        response.raise_for_status()
        batch = response.json()
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return rows


def load_supabase_card_lookup() -> dict[str, dict]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required so set/card resolution comes from Supabase."
        )

    cards = fetch_all_rows("cards", "id,set_id,card_number")
    cards_by_id = {str(c["id"]): c for c in cards if c.get("id")}

    images = fetch_all_rows("card_images", "storage_path,card_id")
    lookup: dict[str, dict] = {}
    for image in images:
        storage_path = str(image.get("storage_path", "")).strip()
        card_id = str(image.get("card_id", "")).strip()
        if not storage_path or not card_id:
            continue
        card = cards_by_id.get(card_id)
        if not card:
            continue
        lookup[storage_path] = {
            "set_id": str(card.get("set_id")),
            "card_number": str(card.get("card_number")),
            "db_card_id": card_id,
            "storage_path": storage_path,
            "resolution_source": "supabase",
        }
    return lookup


def resolve_card_ref(source_row: dict | None, raw_card_id: str) -> dict:
    candidates: list[str] = []
    if source_row:
        image_path = str(source_row.get("image_path", "")).strip().lstrip("/")
        set_folder = str(source_row.get("set_folder", "")).strip()
        filename = str(source_row.get("filename", "")).strip()
        if image_path:
            candidates.append(image_path)
            if not image_path.startswith("raw_images/"):
                candidates.append(f"raw_images/{image_path}")
        if set_folder and filename:
            candidates.append(f"raw_images/{set_folder}/{filename}")
            candidates.append(f"{set_folder}/{filename}")

    seen = set()
    unique_candidates: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique_candidates.append(candidate)

    for candidate in unique_candidates:
        resolved = state.storage_path_to_card_ref.get(candidate)
        if resolved:
            return {**resolved, "raw_index_card_id": raw_card_id}

    return {
        "set_id": None,
        "card_number": None,
        "db_card_id": None,
        "storage_path": None,
        "resolution_source": "unmapped",
        "candidate_storage_paths": unique_candidates,
        "raw_index_card_id": raw_card_id,
    }


def embed_image_bytes(image_bytes: bytes) -> np.ndarray:
    ensure_identification_dependencies_available()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    inputs = state.processor(images=image, return_tensors="pt")
    inputs = {k: v.to(state.device) for k, v in inputs.items()}

    with torch.no_grad():
        features = state.model.get_image_features(**inputs)

    if isinstance(features, torch.Tensor):
        vec_t = features[0]
    elif hasattr(features, "pooler_output"):
        vec_t = features.pooler_output[0]
    elif hasattr(features, "last_hidden_state"):
        vec_t = features.last_hidden_state[0].mean(dim=0)
    else:
        raise ValueError("Unsupported CLIP image feature output type")

    vec = vec_t.detach().cpu().numpy().astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm == 0:
        raise ValueError("Zero-norm embedding for uploaded image")
    return (vec / norm).astype(np.float32)


def convert_to_webp_bytes(image_bytes: bytes) -> bytes:
    ensure_identification_dependencies_available()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=90, method=6)
    return out.getvalue()


def ensure_supabase_card_lookup_loaded() -> None:
    if state.storage_path_to_card_ref:
        return
    state.storage_path_to_card_ref = load_supabase_card_lookup()


def ensure_identification_state_loaded() -> None:
    if state.model is not None and state.embeddings is not None:
        return

    ensure_identification_dependencies_available()

    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError(
            f"Index not found at '{INDEX_PATH}'. Set IDENTIFICATION_INDEX_PATH or build the index first."
        )

    data = np.load(INDEX_PATH, allow_pickle=True)
    card_ids = data["card_ids"]
    embeddings = data["embeddings"].astype(np.float32)
    metadata_rows = load_metadata_by_card_id(data, card_ids)

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        raise ValueError("Index is empty or malformed")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, processor = load_clip(device)

    state.device = device
    state.model = model
    state.processor = processor
    state.card_ids = card_ids
    state.embeddings = embeddings
    state.metadata_rows = metadata_rows


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="PokeHunter Identification API", lifespan=lifespan)

# Set specific origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "device": state.device or "unknown",
        "supabase_card_image_mappings": str(len(state.storage_path_to_card_ref)),
    }


@app.post("/identify")
async def identify(file: UploadFile = File(...), topk: int = 5) -> dict:
    try:
        ensure_identification_state_loaded()
        ensure_supabase_card_lookup_loaded()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if topk < 1:
        raise HTTPException(status_code=400, detail="topk must be >= 1")

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        webp_bytes = convert_to_webp_bytes(image_bytes)
        query_embedding = embed_image_bytes(webp_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process image: {exc}") from exc

    scores = cosine_sim_matrix(state.embeddings, query_embedding)
    k = max(1, min(int(topk), scores.shape[0]))
    top_idx = np.argsort(scores)[::-1][:k]

    top_k = [
        {
            "card_id": str(state.card_ids[i]),
            "score": float(scores[i]),
            "source_row": state.metadata_rows[i],
            "resolved": resolve_card_ref(state.metadata_rows[i], str(state.card_ids[i])),
        }
        for i in top_idx
    ]

    return {
        "best_card_id": top_k[0]["card_id"],
        "best_set_id": top_k[0]["resolved"]["set_id"],
        "best_card_number": top_k[0]["resolved"]["card_number"],
        "best_db_card_id": top_k[0]["resolved"]["db_card_id"],
        "score": top_k[0]["score"],
        "source_row": top_k[0]["source_row"],
        "top_k": top_k,
    }


@app.post("/recommendations")
async def recommendations_route(body: RecommendationRequest) -> dict:
    source = (body.source or "supabase").strip().lower()
    if source not in {"supabase", "csv"}:
        raise HTTPException(status_code=400, detail="source must be 'supabase' or 'csv'")
    if source == "supabase" and not (body.user_id or "").strip():
        raise HTTPException(status_code=400, detail="user_id is required when source='supabase'")

    try:
        return recommend_cards(
            source=source,
            user_id=body.user_id,
            csv_path=body.csv_path,
            budget_usd=body.budget_usd,
            limit=body.limit,
            force_refresh=body.force_refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Recommendation data request failed: {exc}") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend_api:app", host="0.0.0.0", port=8000, reload=True)
