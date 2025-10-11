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
        provider = (settings.EMBEDDING_PROVIDER or "openai").lower()
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

        return OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            api_key=settings.EMBEDDING_API_KEY,
            openai_api_base=str(settings.EMBEDDING_PROVIDER_BASE_URL) if settings.EMBEDDING_PROVIDER_BASE_URL else None,
        )

    @staticmethod
    def _ollama() -> Embeddings:
        from langchain_community.embeddings import OllamaEmbeddings

        return OllamaEmbeddings(
            model=settings.EMBEDDING_MODEL,
            base_url=str(settings.EMBEDDING_PROVIDER_BASE_URL) if settings.EMBEDDING_PROVIDER_BASE_URL else None,
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
