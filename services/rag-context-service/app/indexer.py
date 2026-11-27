"""Qdrant-backed document index.

Idempotent upsert keyed by a stable doc_id (e.g. pr-myorg/backend-142), so
re-indexing the same PR overwrites rather than duplicating — the local
equivalent of LlamaIndex refresh_ref_docs().
"""
import hashlib
import logging

from qdrant_client import QdrantClient, models

from .config import settings
from .embeddings import embed, vector_size

log = logging.getLogger("rag-context-service.indexer")

_client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


def _point_id(doc_id: str) -> int:
    # Qdrant point ids must be int or UUID; hash the stable doc_id to an int.
    return int(hashlib.md5(doc_id.encode()).hexdigest()[:15], 16)


def ensure_collection() -> None:
    existing = {c.name for c in _client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        _client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=vector_size(), distance=models.Distance.COSINE
            ),
        )
        log.info("Created Qdrant collection %s", settings.qdrant_collection)


def index_document(doc_id: str, text: str, metadata: dict) -> None:
    ensure_collection()
    payload = {"doc_id": doc_id, "text": text, **metadata}
    _client.upsert(
        collection_name=settings.qdrant_collection,
        points=[models.PointStruct(id=_point_id(doc_id), vector=embed(text), payload=payload)],
    )
    log.info("Indexed %s", doc_id)


def search(query: str, repo: str | None = None, limit: int = 20) -> list[dict]:
    ensure_collection()
    flt = None
    if repo:
        flt = models.Filter(
            must=[models.FieldCondition(key="repo", match=models.MatchValue(value=repo))]
        )
    hits = _client.search(
        collection_name=settings.qdrant_collection,
        query_vector=embed(query),
        query_filter=flt,
        limit=limit,
    )
    return [h.payload for h in hits if h.payload]


def count(repo: str | None = None) -> int:
    ensure_collection()
    flt = None
    if repo:
        flt = models.Filter(
            must=[models.FieldCondition(key="repo", match=models.MatchValue(value=repo))]
        )
    return _client.count(settings.qdrant_collection, count_filter=flt).count
