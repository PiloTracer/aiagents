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
            "You are a senior legal and financial analyst tasked with drafting exhaustive advisory memoranda—provide reasoning, deep analysis, references. "
            "Deliver responses in thoughtful Spanish, organised with numbered headings, sub-points and clearly argued paragraphs. "
            "Every factual statement must cite the supporting snippet using [#] notation. "
            "Highlight opposing arguments, regulatory risks, client obligations, and recommended next actions. "
            "When the user explicitly requests numbered lists, reproduce them faithfully within the relevant section using nested headings such as '2.1 …' and '2.2 …', ensuring the requested item counts are satisfied. "
            "If the context is insufficient for any claim, state the uncertainty explicitly instead of inventing information and advise how to obtain the missing evidence."
        )
        compiled_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        compiled_messages.extend(conversation)

        user_prompt = (
            "Context snippets:\n"
            f"{context_block}\n\n"
            f"Consulta actual del usuario: {query}\n\n"
            "Produce un informe estructurado con:\n"
            "1. Resumen ejecutivo de máximo tres párrafos.\n"
            "2. Desarrollo extenso con argumentos a favor y en contra, impactos legales/regulatorios y referencias a políticas internas.\n"
            "   - Si la solicitud del usuario incluye listas enumeradas (por ejemplo '20 pasos', '15 errores'), crea subsecciones dentro de este apartado siguiendo el formato '2.x Título…' y presenta exactamente el número de elementos solicitado, cada uno con sus citas correspondientes.\n"
            "3. Listado de riesgos, supuestos y vacíos de información (cuando aplique), destacando cualquier carencia documental o ambigüedad en la evidencia.\n"
            "4. Recomendaciones accionables y próximos pasos.\n"
            "Mantén el tono profesional, fundamenta cada afirmación con citas [#] y señala explícitamente aquello que no pueda confirmarse con la evidencia disponible."
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
