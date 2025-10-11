from __future__ import annotations

import logging
from math import ceil
from typing import Iterable, List

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.core.qdrant_client import get_qdrant_client

from .dto import ChunkPayload

logger = logging.getLogger(__name__)


def _collection_name(area_slug: str) -> str:
    return f"rag_{area_slug}"


def _chunk_list(items: List[ChunkPayload], size: int) -> Iterable[List[ChunkPayload]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class QdrantStorage:
    """Persist chunk embeddings into Qdrant collections."""

    def __init__(self, client: QdrantClient | None = None) -> None:
        self.client = client or get_qdrant_client()
        self.vector_size = settings.RAG_EMBEDDING_DIMENSION or settings.EMBEDDING_TARGET_DIM
        self.batch_size = max(1, settings.QDRANT_UPSERT_BATCH_SIZE)

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
        chunk_list = list(chunks)
        if not chunk_list:
            return []

        self.ensure_collection(area_slug)
        name = _collection_name(area_slug)
        inserted_ids: List[str] = []

        total_batches = ceil(len(chunk_list) / self.batch_size)
        logger.info(
            "Preparing to upsert %d chunks to collection '%s' in %d batch(es)",
            len(chunk_list),
            name,
            total_batches,
        )

        for batch_index, batch in enumerate(_chunk_list(chunk_list, self.batch_size), start=1):
            logger.info(
                "Qdrant upsert batch %d/%d for collection '%s' (%d chunks)",
                batch_index,
                total_batches,
                name,
                len(batch),
            )
            points: List[qmodels.PointStruct] = []
            batch_ids: List[str] = []
            for chunk in batch:
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
                batch_ids.append(point_id)
            if points:
                self.client.upsert(collection_name=name, points=points)
                inserted_ids.extend(batch_ids)
        logger.info(
            "Completed Qdrant upsert for collection '%s' (%d points)",
            name,
            len(inserted_ids),
        )
        return inserted_ids
