from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Iterable, List
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import DocumentChunkMetadata
from ..repository import RagRepository
from .chunking import Chunker
from .dto import ArtifactPayload, ChunkPayload
from .embeddings import EmbeddingEncoder
from .extractors import CompositeExtractor
from .sources import SourceFile
from .storage import QdrantStorage
from .text_utils import sanitize_text

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Coordinates extraction, chunking, embedding, and storage for a single job."""

    def __init__(
        self,
        session: Session,
        *,
        chunk_size: int,
        chunk_overlap: int,
        batch_size: int,
    ) -> None:
        self.repo = RagRepository(session)
        self.extractor = CompositeExtractor()
        self.chunker = Chunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.encoder = EmbeddingEncoder(batch_size=batch_size)
        self.storage = QdrantStorage()

    def run_job(
        self,
        job_id: UUID,
        *,
        area_slug: str,
        agent_slug: str,
        files: Iterable[SourceFile],
        force_reprocess: bool,
    ) -> None:
        files = list(files)
        self.repo.set_job_totals(job_id, total_artifacts=len(files))

        for file_info in files:
            try:
                logger.info(
                    "Job %s: starting processing for %s (content_type=%s)",
                    job_id,
                    file_info.path,
                    file_info.content_type,
                )
                self._process_file(
                    job_id,
                    area_slug=area_slug,
                    agent_slug=agent_slug,
                    source=file_info,
                    force_reprocess=force_reprocess,
                )
                self.repo.increment_job_progress(job_id)
                logger.info(
                    "Job %s: completed processing for %s",
                    job_id,
                    file_info.path,
                )
            except Exception as exc:
                logger.exception("Failed to ingest %s: %s", file_info.path, exc)
                self.repo.mark_job_status(job_id, status="failed", error_message=str(exc))
                raise
        self.repo.mark_job_status(job_id, status="completed")

    # ------------------------------------------------------------------
    def _process_file(
        self,
        job_id: UUID,
        *,
        area_slug: str,
        agent_slug: str,
        source: SourceFile,
        force_reprocess: bool,
    ) -> None:
        source_hash = self._hash_file(source.path)
        if not force_reprocess:
            existing = self.repo.get_artifact_by_hash(source_hash)
            if existing:
                logger.info("Skipping %s (hash already processed)", source.path)
                return

        extraction_start = time.perf_counter()
        logger.info("Starting text extraction for %s", source.path)
        raw_text = self.extractor.extract(source.path)
        extraction_duration = time.perf_counter() - extraction_start
        logger.info(
            "Finished text extraction for %s in %.2f sec (raw chars=%d)",
            source.path,
            extraction_duration,
            len(raw_text),
        )

        text, removed_chars = sanitize_text(raw_text)
        if removed_chars:
            logger.info(
                "Sanitized %s by stripping %d control characters",
                source.path,
                removed_chars,
            )

        artifact = self.repo.create_artifact(
            job_id=job_id,
            area_slug=area_slug,
            agent_slug=agent_slug,
            source_path=str(source.path),
            source_hash=source_hash,
            content_type=source.content_type,
            payload={"source_uri": source.uri},
        )

        artifact_payload = ArtifactPayload(
            artifact_id=artifact.id,
            area_slug=area_slug,
            agent_slug=agent_slug,
            source_path=source.path,
            source_hash=source_hash,
            content_type=source.content_type,
            text=text,
            payload={"job_id": str(job_id)},
        )

        chunk_start = time.perf_counter()
        raw_chunks = list(self.chunker.run(artifact_payload))
        chunk_duration = time.perf_counter() - chunk_start
        chunks: List[ChunkPayload] = []
        removed_from_chunks = 0
        dropped_empty_chunks = 0
        for chunk in raw_chunks:
            cleaned_text, removed = sanitize_text(chunk.text)
            if removed:
                removed_from_chunks += removed
                chunk.text = cleaned_text
            if chunk.text.strip():
                chunks.append(chunk)
            else:
                dropped_empty_chunks += 1
        if removed_from_chunks:
            logger.info(
                "Sanitized %d control characters across chunk set for %s",
                removed_from_chunks,
                source.path,
            )
        if dropped_empty_chunks:
            logger.info(
                "Removed %d empty chunks for %s after sanitation",
                dropped_empty_chunks,
                source.path,
            )
        logger.info(
            "Chunked %s into %d segments in %.2f sec (avg chars=%.1f)",
            source.path,
            len(chunks),
            chunk_duration,
            (sum(len(chunk.text) for chunk in chunks) / len(chunks)) if chunks else 0,
        )
        if not chunks:
            self.repo.mark_artifact_status(
                artifact.id,
                status="skipped",
                payload={"reason": "empty_text"},
            )
            return

        embedding_start = time.perf_counter()
        embeddings = self.encoder.embed(chunk.text for chunk in chunks)
        embedding_duration = time.perf_counter() - embedding_start
        logger.info(
            "Embedded %d chunks for %s in %.2f sec",
            len(chunks),
            source.path,
            embedding_duration,
        )
        for chunk, vector in zip(chunks, embeddings, strict=False):
            chunk.embedding = vector

        storage_start = time.perf_counter()
        qdrant_ids = self.storage.upsert_chunks(area_slug, chunks)
        storage_duration = time.perf_counter() - storage_start
        logger.info(
            "Stored %d chunks for %s in Qdrant in %.2f sec",
            len(qdrant_ids),
            source.path,
            storage_duration,
        )
        chunk_meta_rows: List[DocumentChunkMetadata] = []
        for idx, (chunk, point_id) in enumerate(zip(chunks, qdrant_ids, strict=False)):
            chunk_meta_rows.append(
                DocumentChunkMetadata(
                    artifact_id=artifact.id,
                    chunk_index=chunk.index,
                    text_preview=chunk.text[:5000],
                    token_count=chunk.token_count,
                    qdrant_point_id=point_id,
                    payload=chunk.payload,
                )
            )
        self.repo.create_chunks(artifact.id, chunk_meta_rows)
        self.repo.mark_artifact_status(
            artifact.id,
            status="completed",
            chunk_count=len(chunk_meta_rows),
        )

    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()
