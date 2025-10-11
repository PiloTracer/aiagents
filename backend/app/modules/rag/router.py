from __future__ import annotations

from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db

from .models import DocumentArtifact, DocumentIngestionJob
from .schemas import (
    ArtifactSummary,
    IngestionRequest,
    IngestionResponse,
    JobSummary,
    ListJobsResponse,
)
from .service import IngestionResult, RagIngestionService

router = APIRouter(prefix="/rag", tags=["rag"])

DbSession = Annotated[Session, Depends(get_db)]
AuthUser = Annotated[object, Depends(get_current_user)]


@router.post("/ingest", response_model=list[IngestionResponse], status_code=status.HTTP_202_ACCEPTED)
def trigger_ingestion(
    payload: IngestionRequest,
    db: DbSession,
    _: AuthUser,
) -> list[IngestionResponse]:
    if not payload.locations:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No locations provided")
    service = RagIngestionService(db)
    results = service.ingest(payload.locations, force_reprocess=payload.force_reprocess)
    return [_map_result(result) for result in results]


@router.get("/jobs", response_model=ListJobsResponse)
def list_jobs(db: DbSession, _: AuthUser) -> ListJobsResponse:
    service = RagIngestionService(db)
    jobs = service.list_jobs()
    return ListJobsResponse(jobs=[_map_job(job) for job in jobs])


# ---------------------------------------------------------------------------
def _map_result(result: IngestionResult) -> IngestionResponse:
    job_summary = _map_job(result.job)
    artifacts = [_map_artifact(artifact) for artifact in result.artifacts]
    return IngestionResponse(job=job_summary, artifacts=artifacts)


def _map_job(job: DocumentIngestionJob) -> JobSummary:
    return JobSummary(
        id=job.id,
        area_slug=job.area_slug,
        agent_slug=job.agent_slug,
        source_uri=job.source_uri,
        status=job.status,
        total_artifacts=job.total_artifacts,
        processed_artifacts=job.processed_artifacts,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error_message=job.error_message,
    )


def _map_artifact(artifact: DocumentArtifact) -> ArtifactSummary:
    return ArtifactSummary(
        id=artifact.id,
        source_path=artifact.source_path,
        status=artifact.status,
        chunk_count=artifact.chunk_count,
        metadata=artifact.payload,
        created_at=artifact.created_at,
    )
