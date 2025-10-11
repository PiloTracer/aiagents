from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings

from .models import DocumentArtifact, DocumentIngestionJob
from .pipeline.ingest import IngestionPipeline
from .pipeline.sources import LocalDirectoryAdapter, SourceFile, SourceRegistry
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

    def ingest(self, locations: Iterable[IngestionLocation], *, force_reprocess: bool) -> List[IngestionResult]:
        results: List[IngestionResult] = []
        for location in locations:
            resolved_uri = self._resolve_uri(location.uri)
            job = self.repo.create_job(
                area_slug=location.area_slug,
                agent_slug=location.agent_slug,
                source_uri=resolved_uri,
            )
            self.session.commit()
            self.repo.mark_job_status(job.id, status="running")
            self.session.commit()

            pipeline = IngestionPipeline(
                self.session,
                chunk_size=settings.RAG_CHUNK_SIZE,
                chunk_overlap=settings.RAG_CHUNK_OVERLAP,
                batch_size=settings.RAG_MAX_BATCH_SIZE,
            )
            files = list(self.sources.discover(resolved_uri, recursive=location.recursive))
            logger.info(
                "Starting ingestion job %s for %s (%d files)",
                job.id,
                resolved_uri,
                len(files),
            )
            try:
                pipeline.run_job(
                    job.id,
                    area_slug=location.area_slug,
                    agent_slug=location.agent_slug,
                    files=files,
                    force_reprocess=force_reprocess,
                )
                self.session.commit()
            except Exception as exc:
                self.session.rollback()
                self.repo.mark_job_status(job.id, status="failed", error_message=str(exc))
                self.session.commit()
                raise
            refreshed_job = self.repo.get_job(job.id)
            artifacts = refreshed_job.artifacts if refreshed_job else []
            results.append(IngestionResult(job=refreshed_job or job, artifacts=list(artifacts)))
        return results

    def list_jobs(self, limit: int = 50) -> List[DocumentIngestionJob]:
        return list(self.repo.list_jobs(limit=limit))

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
