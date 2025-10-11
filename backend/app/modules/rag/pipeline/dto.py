from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


@dataclass(slots=True)
class ArtifactPayload:
    """Intermediate representation of a document ready for chunking."""

    artifact_id: UUID
    area_slug: str
    agent_slug: str
    source_path: Path
    source_hash: str
    content_type: str | None
    text: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChunkPayload:
    """A chunk with embedding ready to persist in Qdrant."""

    chunk_id: UUID = field(default_factory=uuid4)
    artifact_id: UUID = field(default_factory=uuid4)
    index: int = 0
    text: str = ""
    token_count: int = 0
    embedding: list[float] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
