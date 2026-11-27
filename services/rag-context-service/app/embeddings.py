"""Embedding provider.

Default "hash" mode: a deterministic, dependency-free bag-of-words hashing
embedding. Good enough to demonstrate vector storage + similarity retrieval
locally without downloading a multi-GB model. Set EMBEDDING_MODE=st to use
sentence-transformers (requires adding it to requirements.txt).
"""
import hashlib
import math
import re

from .config import settings

_WORD = re.compile(r"[A-Za-z0-9_]+")
_st_model = None


def _hash_embed(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    tokens = _WORD.findall(text.lower()) or ["empty"]
    for tok in tokens:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _st_embed(text: str) -> list[float]:
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer  # lazy import
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _st_model.encode(text, normalize_embeddings=True).tolist()


def embed(text: str) -> list[float]:
    if settings.embedding_mode == "st":
        return _st_embed(text)
    return _hash_embed(text, settings.embedding_dim)


def vector_size() -> int:
    # all-MiniLM-L6-v2 is 384-dim; hash mode uses the configured dim.
    return 384 if settings.embedding_mode == "st" else settings.embedding_dim
