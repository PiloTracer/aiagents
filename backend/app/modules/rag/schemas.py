from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class IngestionLocation(BaseModel):
    """Represents a document source to ingest."""

    uri: str = Field(..., description="Absolute path, sharepoint URL, or S3 URI to ingest.")
    area_slug: str = Field(..., description="Area bucket slug (e.g., area1).")
    agent_slug: str = Field(..., description="Agent responsible for this area.")
    recursive: bool = Field(True, description="Whether to traverse subdirectories.")


class IngestionRequest(BaseModel):
    """Endpoint payload to trigger ingestion."""

    locations: list[IngestionLocation]
    force_reprocess: bool = Field(
        False,
        description="Reingest even if source hash already exists.",
    )


class JobSummary(BaseModel):
    id: UUID
    area_slug: str
    agent_slug: str
    source_uri: str
    status: str
    total_artifacts: int
    processed_artifacts: int
    created_at: datetime
    updated_at: datetime | None = None
    error_message: str | None = None


class ArtifactSummary(BaseModel):
    id: UUID
    source_path: str
    status: str
    chunk_count: int
    metadata: dict | None = None
    created_at: datetime


class IngestionResponse(BaseModel):
    job: JobSummary
    artifacts: list[ArtifactSummary] = []


class ListJobsResponse(BaseModel):
    jobs: list[JobSummary]
