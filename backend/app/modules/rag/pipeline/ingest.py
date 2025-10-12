from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Iterable, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings

from ..models import DocumentChunkMetadata
from ..repository import RagRepository
from .chunking import Chunker
from .dto import ArtifactPayload, ChunkPayload
from .embeddings import EmbeddingEncoder
from .extractors import CompositeExtractor
from .sources import SourceFile
from .storage import QdrantStorage
from .text_utils import sanitize_text
from .token_utils import TokenAnalyzer

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
        provider = (settings.EMBEDDING_PROVIDER or "local").lower()
        token_model = settings.LOCAL_EMBEDDING_MODEL if provider in {"local", "granite"} else settings.EMBEDDING_MODEL
        self.token_analyzer = TokenAnalyzer(model_name=token_model)
        self.encoder = EmbeddingEncoder(
            batch_size=batch_size,
            token_analyzer=self.token_analyzer,
            provider=provider,
        )
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

        sanitized_doc = sanitize_text(raw_text)
        text = sanitized_doc.text
        if sanitized_doc.removed_count:
            logger.info(
                "Sanitized %s by stripping %d control characters",
                source.path,
                sanitized_doc.removed_count,
            )
            if sanitized_doc.removed_samples:
                logger.info(
                    "Sanitized characters (sample) for %s: %s",
                    source.path,
                    ", ".join(sanitized_doc.removed_samples),
                )

        doc_payload = {
            "source_uri": source.uri,
            "document_sanitization": sanitized_doc.as_dict(),
        }

        artifact = self.repo.create_artifact(
            job_id=job_id,
            area_slug=area_slug,
            agent_slug=agent_slug,
            source_path=str(source.path),
            source_hash=source_hash,
            content_type=source.content_type,
            payload=doc_payload,
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
        chunk_reports = []
        dropped_empty_chunks = 0

        for chunk in raw_chunks:
            report = self.token_analyzer.prepare_text(chunk.text, chunk_index=chunk.index)
            sanitized_text = report.sanitized.text
            if sanitized_text.strip():
                chunk.text = sanitized_text
                chunk.token_count = report.token_count
                chunk.payload = {
                    **(chunk.payload or {}),
                    "token_report": report.as_dict(),
                }
                chunks.append(chunk)
                chunk_reports.append(report)
            else:
                dropped_empty_chunks += 1

        initial_removed_chars = sum(report.sanitized.removed_count for report in chunk_reports)
        initial_invalid_tokens = sum(report.invalid_characters for report in chunk_reports)
        initial_total_tokens = sum(report.token_count for report in chunk_reports)

        if initial_removed_chars:
            logger.info(
                "Sanitized %d characters across chunk set for %s",
                initial_removed_chars,
                source.path,
            )
        if initial_invalid_tokens:
            logger.info(
                "Tokenizer adjusted %d character(s) across chunk set for %s",
                initial_invalid_tokens,
                source.path,
            )
        if dropped_empty_chunks:
            logger.info(
                "Removed %d empty chunks for %s after sanitization/token checks",
                dropped_empty_chunks,
                source.path,
            )
        logger.info(
            "Chunked %s into %d segments in %.2f sec (avg chars=%.1f, total_tokens=%d, invalid_tokens=%d)",
            source.path,
            len(chunks),
            chunk_duration,
            (sum(len(chunk.text) for chunk in chunks) / len(chunks)) if chunks else 0,
            initial_total_tokens,
            initial_invalid_tokens,
        )
        if not chunks:
            self.repo.mark_artifact_status(
                artifact.id,
                status="skipped",
                payload={"reason": "empty_text"},
            )
            return

        dropped_after_embedding = 0
        embedding_start = time.perf_counter()
        embedded_chunks, embeddings = self.encoder.embed(chunks)
        embedding_duration = time.perf_counter() - embedding_start
        if len(embedded_chunks) != len(chunks):
            dropped_after_embedding = len(chunks) - len(embedded_chunks)
            logger.warning(
                "Dropped %d chunk(s) for %s during embedding due to invalid tokens",
                dropped_after_embedding,
                source.path,
            )
        else:
            dropped_after_embedding = 0
        chunks = embedded_chunks
        if not chunks:
            self.repo.mark_artifact_status(
                artifact.id,
                status="failed",
                payload={"reason": "embedding_failed_all_chunks"},
            )
            logger.error("All chunks failed to embed for %s; skipping artifact", source.path)
            return

        logger.info(
            "Embedded %d chunks for %s in %.2f sec",
            len(chunks),
            source.path,
            embedding_duration,
        )
        for chunk, vector in zip(chunks, embeddings, strict=False):
            chunk.embedding = vector

        final_total_tokens = sum(chunk.token_count for chunk in chunks)
        final_invalid_tokens = 0
        final_removed_chars = 0
        final_samples: list[dict] = []
        fallback_chunks: list[int] = []
        failed_chunks = 0

        for chunk in chunks:
            payload_meta = (chunk.payload or {})
            token_report = payload_meta.get("token_report") if payload_meta else None
            if token_report:
                final_invalid_tokens += int(token_report.get("invalid_characters", 0) or 0)
                final_removed_chars += int(token_report.get("removed_characters", 0) or 0)
                if len(final_samples) < 5:
                    final_samples.append(token_report)
            if payload_meta.get("fallback"):
                fallback_chunks.append(chunk.index)
            if payload_meta.get("embedding_failed"):
                failed_chunks += 1

        if fallback_chunks:
            logger.warning(
                "Fallback normalization triggered for chunks %s in %s",
                fallback_chunks,
                source.path,
            )

        valid_tokens = max(final_total_tokens - final_invalid_tokens, 0)
        logger.info(
            "Token summary for %s: total_tokens=%d valid_tokens=%d invalid_tokens=%d removed_chars=%d fallback=%s dropped=%d failed=%d",
            source.path,
            final_total_tokens,
            valid_tokens,
            final_invalid_tokens,
            final_removed_chars,
            fallback_chunks or "none",
            dropped_after_embedding,
            failed_chunks,
        )

        artifact.payload = {
            **(artifact.payload or {}),
            "token_analysis": {
                "total_chunks": len(chunks),
                "total_tokens": final_total_tokens,
                "valid_tokens": valid_tokens,
                "removed_characters": final_removed_chars,
                "invalid_tokens": final_invalid_tokens,
                "fallback_chunks": fallback_chunks,
                "dropped_chunks": dropped_after_embedding,
                "failed_chunks": failed_chunks,
                "samples": final_samples,
            },
        }

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
