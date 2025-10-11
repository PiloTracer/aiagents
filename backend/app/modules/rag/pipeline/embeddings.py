from __future__ import annotations

import logging
from typing import Iterable, List

from langchain_core.embeddings import Embeddings

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
        from langchain_community.embeddings import OpenAIEmbeddings

        logger.info("Using OpenAI embeddings provider")
        return OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.EMBEDDING_API_KEY,
            openai_api_base=str(settings.EMBEDDING_PROVIDER_BASE_URL)
            if settings.EMBEDDING_PROVIDER_BASE_URL
            else None,
        )

    @staticmethod
    def _local() -> Embeddings:
        from langchain_community.embeddings import OpenAIEmbeddings

        base_url = str(settings.LOCAL_EMBEDDING_BASE_URL).rstrip("/")
        api_key = settings.LOCAL_EMBEDDING_API_KEY or "granite-local"
        timeout = settings.LOCAL_EMBEDDING_TIMEOUT_SECONDS
        logger.info("Using local embedding provider at %s", base_url)
        return OpenAIEmbeddings(
            model=settings.LOCAL_EMBEDDING_MODEL,
            api_key=api_key,
            openai_api_base=base_url,
            request_timeout=timeout,
            max_retries=1,
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

    def __init__(self, *, batch_size: int):
        self.embedder = EmbeddingFactory.build()
        self.batch_size = batch_size

    def embed(self, texts: Iterable[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        batch: List[str] = []
        for text in texts:
            batch.append(text)
            if len(batch) >= self.batch_size:
                vectors.extend(self.embedder.embed_documents(batch))
                batch.clear()
        if batch:
            vectors.extend(self.embedder.embed_documents(batch))
        return vectors
