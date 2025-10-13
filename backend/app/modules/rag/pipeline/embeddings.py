from __future__ import annotations

import logging
from math import ceil
from typing import Iterable, List, Sequence

import requests
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from openai import BadRequestError
from requests import RequestException

from app.core.config import settings

from .dto import ChunkPayload
from .token_utils import TokenAnalyzer, TokenReport

logger = logging.getLogger(__name__)


def _resolve_local_embedding_endpoint() -> str:
    base = str(settings.LOCAL_EMBEDDING_BASE_URL or "").rstrip("/")
    explicit = str(settings.LOCAL_EMBEDDING_URL or "").strip()
    if explicit:
        return explicit.rstrip("/")
    if base:
        return f"{base}/embed"
    raise ValueError("LOCAL_EMBEDDING_BASE_URL or LOCAL_EMBEDDING_URL must be configured")


class TextEmbeddingsInferenceEmbeddings(Embeddings):
    """Client for Hugging Face Text Embeddings Inference /embed endpoint."""

    def __init__(self, *, endpoint: str, timeout: int, model: str) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.model = model
        self.session = requests.Session()

    @staticmethod
    def _coerce_vectors(raw: object) -> List[List[float]]:
        if not isinstance(raw, list):
            return []
        if not raw:
            return []
        first_item = raw[0]
        if isinstance(first_item, dict):
            if "embedding" in first_item:
                return [item.get("embedding", []) for item in raw]
            if "vector" in first_item:
                return [item.get("vector", []) for item in raw]
        elif isinstance(first_item, (list, tuple)):
            return [list(item) for item in raw]
        elif isinstance(first_item, (int, float)):
            return [list(raw)]
        return []

    def _embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        payload = {"inputs": texts}
        response = self.session.post(self.endpoint, json=payload, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        vectors: List[List[float]] = []
        if isinstance(data, dict):
            if "data" in data:
                vectors = [item.get("embedding", []) for item in data.get("data", [])]
            elif "items" in data:
                vectors = [item.get("vector", []) for item in data.get("items", [])]
            elif "embeddings" in data:
                vectors = data.get("embeddings", [])
            elif "value" in data and isinstance(data["value"], list):
                vectors = self._coerce_vectors(data["value"])
        elif isinstance(data, list):
            vectors = self._coerce_vectors(data)
        if not vectors:
            raise ValueError(f"Unexpected response from embedding endpoint: {data}")
        return vectors

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(list(texts))

    def embed_query(self, text: str) -> List[float]:
        vectors = self._embed([text])
        return vectors[0]


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
        endpoint = _resolve_local_embedding_endpoint()
        timeout = settings.LOCAL_EMBEDDING_TIMEOUT_SECONDS
        logger.info("Using local embedding provider at %s", endpoint)
        return TextEmbeddingsInferenceEmbeddings(
            endpoint=endpoint,
            timeout=timeout,
            model=settings.LOCAL_EMBEDDING_MODEL,
        )

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

    def __init__(self, *, batch_size: int, token_analyzer: TokenAnalyzer | None = None, provider: str):
        self.embedder = EmbeddingFactory.build()
        self.batch_size = batch_size
        self.token_analyzer = token_analyzer
        self.provider = (provider or "local").lower()

        if self.provider in {"local", "granite"}:
            self.model_name = settings.LOCAL_EMBEDDING_MODEL
            self.embedding_endpoint = _resolve_local_embedding_endpoint()
        elif self.provider == "openai":
            self.model_name = settings.EMBEDDING_MODEL
            provider_base = settings.EMBEDDING_PROVIDER_BASE_URL or "https://api.openai.com/v1"
            self.embedding_endpoint = f"{str(provider_base).rstrip('/')}/embeddings"
        else:
            self.model_name = settings.EMBEDDING_MODEL
            self.embedding_endpoint = ""

        self.vector_dim = settings.RAG_EMBEDDING_DIMENSION or settings.EMBEDDING_TARGET_DIM

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
            except (BadRequestError, RequestException) as exc:
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

    def _log_embedding_failure(
        self,
        chunk: ChunkPayload,
        batch_index: int,
        total_batches: int,
        attempt_label: str,
        error: Exception,
    ) -> None:
        endpoint = self.embedding_endpoint or "<unavailable>"
        snippet = chunk.text.replace("\n", " ")[:200]
        logger.error(
            "Embedding failure (%s) chunk=%d batch=%d/%d model=%s endpoint=%s error=%s input_length=%d payload_preview=%r",
            attempt_label,
            chunk.index,
            batch_index + 1,
            total_batches,
            self.model_name,
            endpoint,
            error,
            len(chunk.text),
            snippet,
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
            last_error: Exception | None = None
            success = False

            if not self.token_analyzer:
                logger.error("Token analyzer unavailable; cannot recover chunk %d", chunk.index)
                continue

            fallback_reports: list[tuple[str, TokenReport]] = []
            ascii_report = self.token_analyzer.enforce_ascii(chunk.text, chunk_index=chunk.index)
            fallback_reports.append(("ascii", ascii_report))
            restricted_report = self.token_analyzer.enforce_restricted_charset(
                ascii_report.sanitized.text, chunk_index=chunk.index
            )
            fallback_reports.append(("restricted", restricted_report))

            for label, report in fallback_reports:
                chunk.text = report.sanitized.text
                chunk.token_count = report.token_count
                chunk.payload = {
                    **(chunk.payload or {}),
                    "token_report": report.as_dict(),
                    "fallback": label,
                }
                try:
                    vector = self.embedder.embed_documents([chunk.text])[0]
                    recovered_chunks.append(chunk)
                    recovered_vectors.append(vector)
                    success = True
                    break
                except (BadRequestError, RequestException) as exc:
                    if "invalid tokens" not in str(exc).lower():
                        raise
                    last_error = exc
                    self._log_embedding_failure(chunk, batch_index, total_batches, label, exc)
                    continue

            if not success:
                if last_error:
                    self._log_embedding_failure(chunk, batch_index, total_batches, "final", last_error)
                if self.vector_dim:
                    zero_vector = [0.0] * self.vector_dim
                    chunk.payload = {
                        **(chunk.payload or {}),
                        "embedding_failed": True,
                        "embedding_failure_reason": str(last_error) if last_error else "unknown_error",
                    }
                    recovered_chunks.append(chunk)
                    recovered_vectors.append(zero_vector)
                    logger.error(
                        "Chunk %d in batch %d/%d replaced with zero vector after repeated embedding failures.",
                        chunk.index,
                        batch_index + 1,
                        total_batches,
                    )
                else:
                    logger.error(
                        "Chunk %d dropped due to embedding failure; unknown vector dimension.",
                        chunk.index,
                    )

        return recovered_chunks, recovered_vectors

