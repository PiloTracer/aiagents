from __future__ import annotations

import logging
from math import ceil
from typing import Iterable, List, Sequence

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from openai import BadRequestError

from app.core.config import settings

from .dto import ChunkPayload
from .token_utils import TokenAnalyzer

logger = logging.getLogger(__name__)


class EmbeddingFactory:
    """Factory that builds a LangChain embeddings instance based on settings."""

    @staticmethod
    def build() -> Embeddings:
        provider = (settings.EMBEDDING_PROVIDER or "local").lower()
        logger.info("Initialising embedding provider: %s", provider)
        if provider in {"local", "granite"}:
            return EmbeddingFactory._local()
        if provider == "openai":
            return EmbeddingFactory._openai()
        if provider == "ollama":
            return EmbeddingFactory._ollama()
        if provider in {"huggingface", "hf"}:
            return EmbeddingFactory._huggingface()
        raise ValueError(f"Unsupported embedding provider: {provider}")

    @staticmethod
    def _openai() -> Embeddings:
        logger.info("Using OpenAI embeddings provider")
        kwargs = {
            "model": settings.EMBEDDING_MODEL,
            "api_key": settings.EMBEDDING_API_KEY,
            "openai_api_base": str(settings.EMBEDDING_PROVIDER_BASE_URL)
            if settings.EMBEDDING_PROVIDER_BASE_URL
            else None,
            "tiktoken_model_name": "cl100k_base",
            "disallowed_special": (),
        }
        return OpenAIEmbeddings(**kwargs)

    @staticmethod
    def _local() -> Embeddings:
        base_url = str(settings.LOCAL_EMBEDDING_BASE_URL).rstrip("/")
        api_key = settings.LOCAL_EMBEDDING_API_KEY or "granite-local"
        timeout = settings.LOCAL_EMBEDDING_TIMEOUT_SECONDS
        logger.info("Using local embedding provider at %s", base_url)
        kwargs = {
            "model": settings.LOCAL_EMBEDDING_MODEL,
            "api_key": api_key,
            "openai_api_base": base_url,
            "request_timeout": timeout,
            "max_retries": 1,
            "tiktoken_model_name": "cl100k_base",
            "disallowed_special": (),
        }
        return OpenAIEmbeddings(**kwargs)

    @staticmethod
    def _ollama() -> Embeddings:
        from langchain_community.embeddings import OllamaEmbeddings

        return OllamaEmbeddings(
            model=settings.EMBEDDING_MODEL,
            base_url=str(settings.EMBEDDING_PROVIDER_BASE_URL)
            if settings.EMBEDDING_PROVIDER_BASE_URL
            else None,
        )

    @staticmethod
    def _huggingface() -> Embeddings:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)


class EmbeddingEncoder:
    """Embeds chunks into dense vectors, batching for efficiency."""

    def __init__(self, *, batch_size: int, token_analyzer: TokenAnalyzer | None = None):
        self.embedder = EmbeddingFactory.build()
        self.batch_size = batch_size
        self.token_analyzer = token_analyzer

    def embed(self, chunks: Iterable[ChunkPayload]) -> tuple[List[ChunkPayload], List[List[float]]]:
        chunk_list: List[ChunkPayload] = list(chunks)
        if not chunk_list:
            return [], []

        kept_chunks: List[ChunkPayload] = []
        vectors: List[List[float]] = []
        total_batches = ceil(len(chunk_list) / self.batch_size)
        for batch_index in range(total_batches):
            start = batch_index * self.batch_size
            end = start + self.batch_size
            batch_chunks = chunk_list[start:end]
            self._log_batch_tokens(batch_index, total_batches, batch_chunks)
            texts = [chunk.text for chunk in batch_chunks]
            try:
                batch_vectors = self.embedder.embed_documents(texts)
                vectors.extend(batch_vectors)
                kept_chunks.extend(batch_chunks)
            except BadRequestError as exc:
                if "invalid tokens" in str(exc).lower():
                    logger.warning(
                        "Embedding batch %d/%d encountered invalid tokens; attempting recovery",
                        batch_index + 1,
                        total_batches,
                    )
                    recovered_chunks, recovered_vectors = self._recover_batch(
                        batch_chunks, batch_index, total_batches
                    )
                    kept_chunks.extend(recovered_chunks)
                    vectors.extend(recovered_vectors)
                else:
                    raise
        return kept_chunks, vectors

    def _log_batch_tokens(
        self,
        batch_index: int,
        total_batches: int,
        batch_chunks: Sequence[ChunkPayload],
    ) -> None:
        if not batch_chunks:
            return

        valid_tokens = sum(chunk.token_count for chunk in batch_chunks)
        invalid_tokens = 0
        sample_tokens: List[int] = []
        validation_note = "Token report unavailable."
        sample_text = ""

        for chunk in batch_chunks:
            report = (chunk.payload or {}).get("token_report") if chunk.payload else None
            if report:
                invalid_tokens += report.get("invalid_characters", 0)
                if not sample_tokens:
                    sample_tokens = report.get("sample_tokens", [])
                    validation_note = report.get("validation_note", validation_note)
                    sample_text = report.get("sample_text", "")

        logger.info(
            "Embedding batch %d/%d (size=%d) token stats: valid=%d invalid=%d sample_tokens=%s sample_text=%r reason=%s",
            batch_index + 1,
            total_batches,
            len(batch_chunks),
            valid_tokens,
            invalid_tokens,
            sample_tokens,
            sample_text[:120],
            validation_note,
        )

    def _recover_batch(
        self,
        batch_chunks: Sequence[ChunkPayload],
        batch_index: int,
        total_batches: int,
    ) -> tuple[List[ChunkPayload], List[List[float]]]:
        recovered_chunks: List[ChunkPayload] = []
        recovered_vectors: List[List[float]] = []
        for chunk in batch_chunks:
            try:
                vector = self.embedder.embed_documents([chunk.text])[0]
                recovered_chunks.append(chunk)
                recovered_vectors.append(vector)
                continue
            except BadRequestError as exc:
                if "invalid tokens" not in str(exc).lower():
                    raise

            logger.warning(
                "Chunk %d in batch %d/%d failed token validation; forcing ASCII fallback. Snippet=%r",
                chunk.index,
                batch_index + 1,
                total_batches,
                chunk.text[:120],
            )

            if self.token_analyzer:
                report = self.token_analyzer.enforce_ascii(chunk.text, chunk_index=chunk.index)
                chunk.text = report.sanitized.text
                chunk.token_count = report.token_count
                chunk.payload = {
                    **(chunk.payload or {}),
                    "token_report": report.as_dict(),
                    "fallback": "ascii",
                }
                logger.info(
                    "ASCII fallback for chunk %d produced %d tokens; sample_tokens=%s",
                    chunk.index,
                    report.token_count,
                    report.sample_tokens,
                )
                logger.debug(
                    "ASCII fallback chunk %d text snippet: %r",
                    chunk.index,
                    report.sample_text,
                )
            else:
                ascii_text = chunk.text.encode("ascii", "ignore").decode("ascii")
                logger.warning(
                    "Chunk %d falling back to ASCII via naive strip; original length=%d ascii length=%d",
                    chunk.index,
                    len(chunk.text),
                    len(ascii_text),
                )
                chunk.text = ascii_text

            try:
                vector = self.embedder.embed_documents([chunk.text])[0]
                recovered_chunks.append(chunk)
                recovered_vectors.append(vector)
            except BadRequestError as final_exc:
                logger.error(
                    "Chunk %d in batch %d/%d failed embedding after ASCII fallback; dropping chunk. Error: %s",
                    chunk.index,
                    batch_index + 1,
                    total_batches,
                    final_exc,
                )
                chunk.payload = {
                    **(chunk.payload or {}),
                    "embedding_failed": str(final_exc),
                }
                logger.error(
                    "Dropped chunk %d due to embedding failure. Text snippet: %r",
                    chunk.index,
                    chunk.text[:120],
                )

        return recovered_chunks, recovered_vectors
