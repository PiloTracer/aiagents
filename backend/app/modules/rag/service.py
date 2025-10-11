from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal

from .models import DocumentArtifact, DocumentIngestionJob
from .pipeline.ingest import IngestionPipeline
from .pipeline.sources import LocalDirectoryAdapter, SourceRegistry
from .repository import RagRepository
from .schemas import IngestionLocation

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestionResult:
    job: DocumentIngestionJob
    artifacts: List[DocumentArtifact]


class RagIngestionService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = RagRepository(session)
        allowed = {ext.strip().lower() for ext in settings.RAG_ALLOWED_EXTENSIONS.split(",") if ext.strip()}
        self.sources = SourceRegistry([LocalDirectoryAdapter(allowed)])

    def ingest(
        self,
        locations: Iterable[IngestionLocation],
        *,
        force_reprocess: bool,
        background_tasks: BackgroundTasks | None = None,
    ) -> List[IngestionResult]:
        results: List[IngestionResult] = []
        for location in locations:
            resolved_uri = self._resolve_uri(location.uri)
            job = self.repo.create_job(
                area_slug=location.area_slug,
                agent_slug=location.agent_slug,
                source_uri=resolved_uri,
            )
            self.session.commit()

            if background_tasks:
                logger.info(
                    "Queued ingestion job %s for %s (area=%s, agent=%s)",
                    job.id,
                    resolved_uri,
                    location.area_slug,
                    location.agent_slug,
                )
                background_tasks.add_task(
                    _run_ingestion_job_task,
                    job.id,
                    location.area_slug,
                    location.agent_slug,
                    resolved_uri,
                    location.recursive,
                    force_reprocess,
                )
                refreshed_job = self.repo.get_job(job.id) or job
                results.append(IngestionResult(job=refreshed_job, artifacts=[]))
                continue

            refreshed_job = self._run_ingestion_job(
                job_id=job.id,
                area_slug=location.area_slug,
                agent_slug=location.agent_slug,
                resolved_uri=resolved_uri,
                recursive=location.recursive,
                force_reprocess=force_reprocess,
                raise_errors=True,
            )
            artifacts = refreshed_job.artifacts if refreshed_job else []
            results.append(IngestionResult(job=refreshed_job or job, artifacts=list(artifacts)))
        return results

    def list_jobs(self, limit: int = 50) -> List[DocumentIngestionJob]:
        jobs = list(self.repo.list_jobs(limit=limit))
        for job in jobs:
            job.token_summary = self._build_token_summary(job)
        return jobs

    def _build_token_summary(self, job: DocumentIngestionJob) -> dict | None:
        total_tokens = 0
        invalid_tokens = 0
        valid_tokens = 0
        samples: list[dict] = []
        fallback_chunks: set[int] = set()
        total_removed_chars = 0
        total_dropped_chunks = 0

        for artifact in job.artifacts:
            metadata = (artifact.payload or {}).get("token_analysis") if artifact.payload else None
            if not metadata:
                continue
            total_tokens += int(metadata.get("total_tokens", 0) or 0)
            invalid_tokens += int(metadata.get("invalid_tokens", 0) or 0)
            valid_tokens += int(metadata.get("valid_tokens", 0) or 0)
            total_removed_chars += int(metadata.get("removed_characters", 0) or 0)
            total_dropped_chunks += int(metadata.get("dropped_chunks", 0) or 0)
            for sample in (metadata.get("samples") or []):
                samples.append(
                    {
                        "chunk_index": sample.get("chunk_index"),
                        "token_count": sample.get("token_count"),
                        "invalid_characters": sample.get("invalid_characters"),
                        "sample_tokens": sample.get("sample_tokens"),
                        "sample_text": sample.get("sample_text"),
                        "validation_note": sample.get("validation_note"),
                    }
                )
            for chunk_index in metadata.get("fallback_chunks", []) or []:
                if chunk_index is not None:
                    fallback_chunks.add(int(chunk_index))

        if total_tokens == 0 and invalid_tokens == 0 and not samples and total_removed_chars == 0 and total_dropped_chunks == 0 and valid_tokens == 0:
            return None

        return {
            "total_tokens": total_tokens,
            "valid_tokens": valid_tokens,
            "invalid_tokens": invalid_tokens,
            "removed_characters": total_removed_chars,
            "fallback_chunks": sorted(fallback_chunks),
            "dropped_chunks": total_dropped_chunks,
            "samples": samples[:5],
        }

    def _run_ingestion_job(
        self,
        *,
        job_id: UUID,
        area_slug: str,
        agent_slug: str,
        resolved_uri: str,
        recursive: bool,
        force_reprocess: bool,
        raise_errors: bool,
    ) -> DocumentIngestionJob | None:
        pipeline = IngestionPipeline(
            self.session,
            chunk_size=settings.RAG_CHUNK_SIZE,
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,
            batch_size=settings.RAG_MAX_BATCH_SIZE,
        )
        files = list(self.sources.discover(resolved_uri, recursive=recursive))
        logger.info(
            "Starting ingestion job %s for %s (%d files)",
            job_id,
            resolved_uri,
            len(files),
        )
        self.repo.set_job_totals(job_id, total_artifacts=len(files))
        self.repo.mark_job_status(job_id, status="running", error_message=None)
        self.session.commit()
        try:
            pipeline.run_job(
                job_id,
                area_slug=area_slug,
                agent_slug=agent_slug,
                files=files,
                force_reprocess=force_reprocess,
            )
            self.session.commit()
        except Exception as exc:
            self.session.rollback()
            logger.exception(
                "Ingestion job %s for %s failed: %s",
                job_id,
                resolved_uri,
                exc,
            )
            self.repo.mark_job_status(job_id, status="failed", error_message=str(exc))
            self.session.commit()
            if raise_errors:
                raise
        refreshed_job = self.repo.get_job(job_id)
        return refreshed_job

    # ------------------------------------------------------------------
    def _resolve_uri(self, uri: str) -> str:
        parsed = Path(uri)
        if parsed.is_absolute() or uri.startswith(("s3://", "http://", "https://", "sharepoint://", "file://")):
            return uri
        if not settings.RAG_DOCUMENT_ROOT:
            raise ValueError(
                "RAG_DOCUMENT_ROOT is not configured. Provide an absolute path or set the environment variable."
            )
        base = Path(settings.RAG_DOCUMENT_ROOT).expanduser()
        resolved = base / uri
        return str(resolved.resolve())


def _run_ingestion_job_task(
    job_id: UUID,
    area_slug: str,
    agent_slug: str,
    resolved_uri: str,
    recursive: bool,
    force_reprocess: bool,
) -> None:
    session = SessionLocal()
    try:
        service = RagIngestionService(session)
        service._run_ingestion_job(
            job_id=job_id,
            area_slug=area_slug,
            agent_slug=agent_slug,
            resolved_uri=resolved_uri,
            recursive=recursive,
            force_reprocess=force_reprocess,
            raise_errors=False,
        )
    finally:
        session.close()
