from __future__ import annotations

from typing import List

from pydantic import AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    # Core
    DATABASE_URL: str
    ALLOWED_ORIGINS: str | None = "*"

    # Vector store configuration
    DBRAG_QDRANT_URL: AnyUrl | str = "http://dbrag:6333"
    DBRAG_QDRANT_GRPC_URL: AnyUrl | str | None = None
    DBRAG_QDRANT_API_KEY: str | None = None
    DBRAG_QDRANT_TIMEOUT_SECONDS: int = 120
    QDRANT_UPSERT_BATCH_SIZE: int = 128

    # Document ingestion parameters
    RAG_DOCUMENT_ROOT: str | None = None
    RAG_ALLOWED_EXTENSIONS: str = ".pdf,.docx,.doc,.txt,.pptx,.ppt,.md"
    RAG_CHUNK_SIZE: int = 1000
    RAG_CHUNK_OVERLAP: int = 200
    RAG_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    RAG_EMBEDDING_DIMENSION: int = 1024
    RAG_MAX_BATCH_SIZE: int = 16

    # Embedding provider selection
    EMBEDDING_PROVIDER: str = "local"
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_TARGET_DIM: int = 1024
    EMBEDDING_PROVIDER_BASE_URL: AnyUrl | str | None = None
    EMBEDDING_API_KEY: str | None = None

    # Local embedding (Granite) settings
    LOCAL_EMBEDDING_MODEL: str = "BAAI/bge-m3"
    LOCAL_EMBEDDING_BASE_URL: AnyUrl | str = "http://host.docker.internal:18082"
    LOCAL_EMBEDDING_URL: AnyUrl | str = "http://host.docker.internal:18082/embed"
    LOCAL_EMBEDDING_API_KEY: str | None = None
    LOCAL_EMBEDDING_TIMEOUT_SECONDS: int = 120
    DOCLING_VLM_MODEL: str | None = None

    # Auth
    AUTH_TOKEN_SECRET: str
    AUTH_TOKEN_TTL_SECONDS: int = 86400

    # Misc
    DEBUGPY: int | None = None
    AUTOGEN_MIGRATIONS_DEV: bool = False
    AUTOGEN_MIGRATIONS_PROD: bool = False

    # Default administrator bootstrap
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None
    ADMIN_FULL_NAME: str | None = None

    @property
    def cors_origins(self) -> List[str]:
        if not self.ALLOWED_ORIGINS:
            return []
        raw = self.ALLOWED_ORIGINS
        if isinstance(raw, str):
            return [o.strip() for o in raw.split(",") if o.strip()]
        return list(raw)

    @property
    def is_dev(self) -> bool:
        try:
            return bool(int(self.DEBUGPY or 0))
        except Exception:
            return False


settings = Settings()  # type: ignore[call-arg]
