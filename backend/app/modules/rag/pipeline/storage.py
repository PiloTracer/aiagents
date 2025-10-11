from __future__ import annotations

import logging
from typing import Iterable, List
from uuid import UUID

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.core.qdrant_client import get_qdrant_client

from .dto import ChunkPayload

logger = logging.getLogger(__name__)


def _collection_name(area_slug: str) -> str:
    return f"rag_{area_slug}"


class QdrantStorage:
    """Persist chunk embeddings into Qdrant collections."""

    def __init__(self, client: QdrantClient | None = None) -> None:
        self.client = client or get_qdrant_client()
        self.vector_size = settings.RAG_EMBEDDING_DIMENSION or settings.EMBEDDING_TARGET_DIM

    def ensure_collection(self, area_slug: str) -> None:
        name = _collection_name(area_slug)
        collections = self.client.get_collections().collections
        if any(col.name == name for col in collections):
            return
        logger.info("Creating Qdrant collection '%s' with dim=%s", name, self.vector_size)
        self.client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=self.vector_size, distance=qmodels.Distance.COSINE),
        )

    def upsert_chunks(self, area_slug: str, chunks: Iterable[ChunkPayload]) -> List[str]:
        self.ensure_collection(area_slug)
        name = _collection_name(area_slug)
        points: List[qmodels.PointStruct] = []
        point_ids: List[str] = []
        for chunk in chunks:
            emb = np.array(chunk.embedding, dtype=np.float32)
            if emb.shape[0] != self.vector_size:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {self.vector_size}, got {emb.shape[0]}"
                )
            point_id = str(chunk.chunk_id)
            payload = dict(chunk.payload)
            payload.update(
                {
                    "artifact_id": str(chunk.artifact_id),
                    "chunk_index": chunk.index,
                    "text": chunk.text,
                    "token_count": chunk.token_count,
                }
            )
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=emb.tolist(),
                    payload=payload,
                )
            )
            point_ids.append(point_id)
        if points:
            self.client.upsert(collection_name=name, points=points)
        return point_ids
