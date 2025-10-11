from __future__ import annotations

import logging
from math import ceil
from typing import Iterable, List

from langchain_core.embeddings import Embeddings

try:
    from langchain_openai import OpenAIEmbeddings as NewOpenAIEmbeddings
except ImportError:  # pragma: no cover - optional dependency
    NewOpenAIEmbeddings = None
from langchain_community.embeddings import OpenAIEmbeddings as LegacyOpenAIEmbeddings

from app.core.config import settings

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
        if NewOpenAIEmbeddings:
            return NewOpenAIEmbeddings(**kwargs)
        logger.warning(
            "Package 'langchain-openai' not installed; falling back to deprecated langchain-community OpenAIEmbeddings. "
            "Install langchain-openai>=0.2.1 to silence this warning."
        )
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop("tiktoken_model_name", None)
        fallback_kwargs.pop("disallowed_special", None)
        return LegacyOpenAIEmbeddings(**fallback_kwargs)

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
        if NewOpenAIEmbeddings:
            return NewOpenAIEmbeddings(**kwargs)
        logger.warning(
            "Package 'langchain-openai' not installed; falling back to deprecated langchain-community OpenAIEmbeddings. "
            "Install langchain-openai>=0.2.1 to silence this warning."
        )
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop("tiktoken_model_name", None)
        fallback_kwargs.pop("disallowed_special", None)
        return LegacyOpenAIEmbeddings(**fallback_kwargs)

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

    def __init__(self, *, batch_size: int):
        self.embedder = EmbeddingFactory.build()
        self.batch_size = batch_size

    def embed(self, texts: Iterable[str]) -> List[List[float]]:
        prepared: List[str] = list(texts)
        if not prepared:
            return []

        vectors: List[List[float]] = []
        total_batches = ceil(len(prepared) / self.batch_size)
        for batch_index in range(total_batches):
            start = batch_index * self.batch_size
            end = start + self.batch_size
            batch = prepared[start:end]
            logger.info(
                "Embedding batch %d/%d (size=%d)",
                batch_index + 1,
                total_batches,
                len(batch),
            )
            vectors.extend(self.embedder.embed_documents(batch))
        return vectors
