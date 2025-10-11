from __future__ import annotations

from typing import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import DocumentArtifact, DocumentChunkMetadata, DocumentIngestionJob


class RagRepository:
    """Persistence helpers for RAG ingestion state."""

    def __init__(self, session: Session):
        self.session = session

    # Jobs -----------------------------------------------------------------
    def create_job(self, *, area_slug: str, agent_slug: str, source_uri: str) -> DocumentIngestionJob:
        job = DocumentIngestionJob(
            area_slug=area_slug,
            agent_slug=agent_slug,
            source_uri=source_uri,
            status="queued",
        )
        self.session.add(job)
        self.session.flush()
        return job

    def get_job(self, job_id: UUID) -> DocumentIngestionJob | None:
        return self.session.get(DocumentIngestionJob, job_id)

    def list_jobs(self, limit: int = 50) -> Sequence[DocumentIngestionJob]:
        stmt = select(DocumentIngestionJob).order_by(DocumentIngestionJob.created_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))

    def mark_job_status(self, job_id: UUID, *, status: str, error_message: str | None = None) -> None:
        stmt = (
            update(DocumentIngestionJob)
            .where(DocumentIngestionJob.id == job_id)
            .values(status=status, error_message=error_message)
        )
        self.session.execute(stmt)

    def set_job_totals(self, job_id: UUID, *, total_artifacts: int) -> None:
        stmt = (
            update(DocumentIngestionJob)
            .where(DocumentIngestionJob.id == job_id)
            .values(total_artifacts=total_artifacts)
        )
        self.session.execute(stmt)

    def increment_job_progress(self, job_id: UUID) -> None:
        stmt = (
            update(DocumentIngestionJob)
            .where(DocumentIngestionJob.id == job_id)
            .values(processed_artifacts=DocumentIngestionJob.processed_artifacts + 1)
        )
        self.session.execute(stmt)

    # Artifacts ------------------------------------------------------------
    def create_artifact(
        self,
        *,
        job_id: UUID,
        area_slug: str,
        agent_slug: str,
        source_path: str,
        source_hash: str,
        content_type: str | None,
        payload: dict | None,
    ) -> DocumentArtifact:
        artifact = DocumentArtifact(
            job_id=job_id,
            area_slug=area_slug,
            agent_slug=agent_slug,
            source_path=source_path,
            source_hash=source_hash,
            content_type=content_type,
            payload=payload or {},
            status="processing",
        )
        self.session.add(artifact)
        self.session.flush()
        return artifact

    def get_artifact_by_hash(self, source_hash: str) -> DocumentArtifact | None:
        stmt = select(DocumentArtifact).where(DocumentArtifact.source_hash == source_hash).limit(1)
        return self.session.scalars(stmt).first()

    def mark_artifact_status(
        self,
        artifact_id: UUID,
        *,
        status: str,
        chunk_count: int | None = None,
        payload: dict | None = None,
        error_message: str | None = None,
    ) -> None:
        values: dict = {"status": status}
        if chunk_count is not None:
            values["chunk_count"] = chunk_count
        merged_payload = dict(payload or {})
        if error_message:
            merged_payload["error"] = error_message
        if merged_payload:
            values["payload"] = merged_payload
        stmt = update(DocumentArtifact).where(DocumentArtifact.id == artifact_id).values(**values)
        self.session.execute(stmt)

    # Chunks ---------------------------------------------------------------
    def create_chunks(self, artifact_id: UUID, rows: Iterable[DocumentChunkMetadata]) -> None:
        for row in rows:
            row.artifact_id = artifact_id
            self.session.add(row)

    def get_chunks_for_artifact(self, artifact_id: UUID) -> Sequence[DocumentChunkMetadata]:
        stmt = (
            select(DocumentChunkMetadata)
            .where(DocumentChunkMetadata.artifact_id == artifact_id)
            .order_by(DocumentChunkMetadata.chunk_index.asc())
        )
        return list(self.session.scalars(stmt))
