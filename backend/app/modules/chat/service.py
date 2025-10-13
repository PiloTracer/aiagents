from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Sequence

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.qdrant_client import get_qdrant_client
from app.modules.catalog.models import Area
from app.modules.llm import get_chat_provider
from app.modules.rag.pipeline.embeddings import EmbeddingFactory

from .models import ChatMessage, ChatSession
from .repository import ChatRepository
from .schemas import ChatRequest, ChatResponse, ChatMessageRead, RetrievedSource

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_embedder():
    return EmbeddingFactory.build()


@dataclass
class RetrievedChunk:
    chunk_id: str
    area_slug: str
    text: str
    score: float
    artifact_id: str | None = None
    chunk_index: int | None = None
    source_path: str | None = None


class RetrievalService:
    def __init__(self, db: Session):
        self.db = db
        self.qdrant = get_qdrant_client()
        self.embedder = _get_embedder()

    def _resolve_areas(self, candidate_slugs: Sequence[str] | None) -> List[str]:
        stmt = select(Area.slug).where(Area.is_active.is_(True))
        if candidate_slugs:
            stmt = stmt.filter(Area.slug.in_([slug.lower() for slug in candidate_slugs]))
        result = self.db.execute(stmt).scalars().all()
        return list(result)

    def _collection_name(self, slug: str) -> str:
        return f"rag_{slug}"

    def retrieve(self, query: str, *, area_slugs: Sequence[str] | None, top_k: int) -> List[RetrievedChunk]:
        areas = self._resolve_areas(area_slugs)
        if not areas:
            logger.warning("No active areas matched request; falling back to all active areas.")
            areas = self._resolve_areas(None)
        if not areas:
            return []

        vector = self.embedder.embed_query(query)
        limit_per_area = max(1, top_k)
        collected: list[RetrievedChunk] = []

        for slug in areas:
            collection = self._collection_name(slug)
            try:
                points = self.qdrant.search(
                    collection_name=collection,
                    query_vector=vector,
                    limit=limit_per_area,
                    with_payload=True,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Qdrant search failed for collection %s: %s", collection, exc)
                continue

            for point in points:
                payload = point.payload or {}
                text = payload.get("text") or ""
                if not text:
                    continue
                collected.append(
                    RetrievedChunk(
                        chunk_id=str(point.id),
                        area_slug=slug,
                        text=text,
                        score=float(point.score or 0.0),
                        artifact_id=payload.get("artifact_id"),
                        chunk_index=payload.get("chunk_index"),
                        source_path=payload.get("source_path"),
                    )
                )

        collected.sort(key=lambda item: item.score, reverse=True)
        max_chunks = settings.CHAT_CONTEXT_MAX_CHUNKS or top_k
        return collected[:max_chunks]


class ChatConversationService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ChatRepository(db)
        self.retriever = RetrievalService(db)
        self.provider = get_chat_provider()

    async def handle_request(self, *, user_id: str | None, payload: ChatRequest) -> ChatResponse:
        session = self._ensure_session(payload.session_id, user_id=user_id)
        top_k = payload.top_k or settings.CHAT_DEFAULT_TOP_K

        if not session.title:
            preview = payload.message.strip().splitlines()[0]
            session.title = preview[:80]
            self.db.add(session)

        # Persist user message
        user_message = self.repo.add_message(
            session_id=session.id,
            role="user",
            content=payload.message,
            metadata=None,
        )

        assistant_message: ChatMessage | None = None

        try:
            contexts = self.retriever.retrieve(
                payload.message,
                area_slugs=payload.area_slugs,
                top_k=top_k,
            )

            assistant_text = await self._generate_response(
                query=payload.message,
                conversation=self._history_for_session(session.id, exclude_last=True),
                contexts=contexts,
            )

            assistant_metadata = {
                "sources": [context.__dict__ for context in contexts],
                "provider": self.provider.name(),
            }
            assistant_message = self.repo.add_message(
                session_id=session.id,
                role="assistant",
                content=assistant_text,
                metadata=assistant_metadata,
            )

            session.updated_at = assistant_message.created_at
            self.db.add(session)
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("Chat conversation processing failed")
            raise

        if assistant_message is None:
            raise RuntimeError("Assistant response could not be generated.")

        message_count = self.repo.message_count(session.id)
        return ChatResponse(
            session_id=session.id,
            message=self._to_message_read(assistant_message),
            sources=[RetrievedSource(**context.__dict__) for context in contexts],
            total_messages=message_count,
        )

    def _ensure_session(self, session_id: str | None, *, user_id: str | None) -> ChatSession:
        if session_id:
            session = self.repo.get_session(session_id, user_id=user_id)
            if session:
                return session
            logger.warning("Requested session %s not found; creating new session.", session_id)
        session = self.repo.create_session(user_id=user_id)
        return session

    def _history_for_session(self, session_id: str, *, exclude_last: bool) -> list[dict[str, str]]:
        messages = self.repo.list_messages(session_id)
        if exclude_last and messages:
            messages = messages[:-1]
        if not messages:
            return []
        limit = max(1, settings.CHAT_MAX_HISTORY_MESSAGES)
        subset = messages[-limit:]
        return [{"role": message.role, "content": message.content} for message in subset]

    async def _generate_response(
        self,
        *,
        query: str,
        conversation: list[dict[str, str]],
        contexts: Sequence[RetrievedChunk],
    ) -> str:
        prompt_messages = self._build_prompt_messages(query=query, contexts=contexts, conversation=conversation)
        return await run_in_threadpool(
            self.provider.generate,
            prompt_messages,
            temperature=settings.OPENAI_TEMPERATURE,
            max_tokens=settings.OPENAI_MAX_TOKENS,
        )

    def _build_prompt_messages(
        self,
        *,
        query: str,
        contexts: Sequence[RetrievedChunk],
        conversation: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        context_lines: list[str] = []
        for idx, item in enumerate(contexts, start=1):
            snippet = item.text.strip()
            if len(snippet) > 1000:
                snippet = snippet[:1000] + "..."
            source = item.source_path or f"artifact:{item.artifact_id}"
            context_lines.append(
                f"[{idx}] Area: {item.area_slug} | Score: {item.score:.3f} | Source: {source}\n{snippet}"
            )
        context_block = "\n\n".join(context_lines) if context_lines else "No matching documents were retrieved."

        system_prompt = (
            "You are a professional legal and business assistant. "
            "Craft structured, factual responses using only the provided context snippets. "
            "When citing evidence, reference the snippet number in [#] format. "
            "If the context is insufficient, explicitly state what information is missing."
        )
        compiled_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        compiled_messages.extend(conversation)

        user_prompt = (
            "Context snippets:\n"
            f"{context_block}\n\n"
            f"User question: {query}\n\n"
            "Return a concise executive summary followed by detailed analysis with citations."
        )
        compiled_messages.append({"role": "user", "content": user_prompt})
        return compiled_messages

    def _to_message_read(self, message: ChatMessage) -> ChatMessageRead:
        return ChatMessageRead(
            id=message.id,
            role=message.role,
            content=message.content,
            created_at=message.created_at,
            metadata=message.payload or {},
        )
