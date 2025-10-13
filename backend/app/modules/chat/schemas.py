from __future__ import annotations

from datetime import datetime
from typing import Any, List

from pydantic import BaseModel, Field, constr


class RetrievedSource(BaseModel):
    chunk_id: str
    area_slug: str
    score: float = Field(..., ge=0)
    text: str
    chunk_index: int | None = None
    artifact_id: str | None = None
    source_path: str | None = None


class ChatMessageRead(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] | None = None


class ChatSessionSummary(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    is_archived: bool
    message_count: int


class ChatSessionRead(BaseModel):
    id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime
    is_archived: bool
    messages: List[ChatMessageRead]


class ChatRequest(BaseModel):
    message: constr(min_length=1, max_length=4000)  # type: ignore[valid-type]
    session_id: str | None = None
    area_slugs: list[str] | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class ChatResponse(BaseModel):
    session_id: str
    message: ChatMessageRead
    sources: list[RetrievedSource]
    total_messages: int


class ChatDeleteResponse(BaseModel):
    session_id: str
    deleted: bool
