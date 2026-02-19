import json
from typing import List

import numpy as np

from config import settings


def embed_texts(texts: List[str]) -> np.ndarray:
    # SentenceTransformers embeddings
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(settings.embed_model)
    emb = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.array(emb, dtype=np.float32)


def dumps_vec(vec) -> str:
    return json.dumps([float(x) for x in vec])


def loads_vec(s: str):
    return np.array(json.loads(s), dtype=np.float32)
