from __future__ import annotations

import numpy as np
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor


MODEL_NAME = "openai/clip-vit-base-patch32"


def load_clip(device: str):
    model = CLIPModel.from_pretrained(MODEL_NAME)
    processor = CLIPProcessor.from_pretrained(MODEL_NAME)
    model.to(device)
    model.eval()
    return model, processor


def embed_image(path: str, model, processor, device: str) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        features = model.get_image_features(**inputs)

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
        raise ValueError(f"Zero-norm embedding for image: {path}")
    vec = vec / norm
    return vec.astype(np.float32)


def cosine_sim_matrix(ref_matrix: np.ndarray, q: np.ndarray) -> np.ndarray:
    return ref_matrix @ q
