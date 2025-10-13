from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.modules.users.models import User

from .repository import ChatRepository
from .schemas import (
    ChatDeleteResponse,
    ChatMessageRead,
    ChatRequest,
    ChatResponse,
    ChatSessionRead,
    ChatSessionSummary,
)
from .service import ChatConversationService

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

DbDep = Annotated[Session, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.post("/query", response_model=ChatResponse)
async def query_chatbot(
    payload: ChatRequest,
    db: DbDep,
    current_user: UserDep,
) -> ChatResponse:
    service = ChatConversationService(db)
    return await service.handle_request(user_id=current_user.id, payload=payload)


@router.get("/sessions", response_model=list[ChatSessionSummary])
def list_sessions(
    db: DbDep,
    current_user: UserDep,
) -> list[ChatSessionSummary]:
    repo = ChatRepository(db)
    sessions = repo.list_sessions(user_id=current_user.id)
    summaries: list[ChatSessionSummary] = []
    for session in sessions:
        message_count = repo.message_count(session.id)
        summaries.append(
            ChatSessionSummary(
                id=session.id,
                title=session.title,
                created_at=session.created_at,
                updated_at=session.updated_at,
                is_archived=session.is_archived,
                message_count=message_count,
            )
        )
    return summaries


@router.get("/sessions/{session_id}", response_model=ChatSessionRead)
def read_session(
    session_id: str,
    db: DbDep,
    current_user: UserDep,
) -> ChatSessionRead:
    repo = ChatRepository(db)
    session = repo.get_session(session_id, user_id=current_user.id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    messages = repo.list_messages(session.id)
    return ChatSessionRead(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        is_archived=session.is_archived,
        messages=[
            ChatMessageRead(
                id=message.id,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
                metadata=message.payload or {},
            )
            for message in messages
        ],
    )


@router.delete("/sessions/{session_id}", response_model=ChatDeleteResponse)
def delete_session(
    session_id: str,
    db: DbDep,
    current_user: UserDep,
) -> ChatDeleteResponse:
    repo = ChatRepository(db)
    deleted = repo.delete_session(session_id, user_id=current_user.id)
    if deleted:
        db.commit()
    return ChatDeleteResponse(session_id=session_id, deleted=deleted)
