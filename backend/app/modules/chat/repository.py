from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .models import ChatMessage, ChatSession


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    # Sessions -------------------------------------------------------------
    def create_session(self, *, user_id: str | None, title: str | None = None) -> ChatSession:
        session = ChatSession(user_id=user_id, title=title)
        self.db.add(session)
        self.db.flush()
        return session

    def get_session(self, session_id: str, *, user_id: str | None) -> ChatSession | None:
        stmt = (
            select(ChatSession)
            .where(ChatSession.id == session_id)
            .options(selectinload(ChatSession.messages))
        )
        session = self.db.scalar(stmt)
        if session and user_id and session.user_id and session.user_id != user_id:
            return None
        return session

    def list_sessions(self, *, user_id: str | None, limit: int = 50) -> Sequence[ChatSession]:
        stmt = select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit)
        if user_id:
            stmt = stmt.where(ChatSession.user_id == user_id)
        else:
            stmt = stmt.where(ChatSession.user_id.is_(None))
        return list(self.db.scalars(stmt))

    def delete_session(self, session_id: str, *, user_id: str | None) -> bool:
        session = self.get_session(session_id, user_id=user_id)
        if not session:
            return False
        self.db.delete(session)
        return True

    def update_session_title(self, session: ChatSession, title: str | None) -> None:
        session.title = title
        self.db.add(session)

    # Messages -------------------------------------------------------------
    def add_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None,
    ) -> ChatMessage:
        message = ChatMessage(session_id=session_id, role=role, content=content, payload=metadata or {})
        self.db.add(message)
        self.db.flush()
        return message

    def list_messages(self, session_id: str, limit: int | None = None) -> Sequence[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
        )
        if limit:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt))

    def message_count(self, session_id: str) -> int:
        stmt = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
        return self.db.scalar(stmt) or 0
