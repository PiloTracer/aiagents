from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Optional

from qdrant_client import QdrantClient

from .config import settings

logger = logging.getLogger(__name__)


def _create_client() -> QdrantClient:
    kwargs: dict[str, object] = {
        "url": str(settings.DBRAG_QDRANT_URL),
        "api_key": settings.DBRAG_QDRANT_API_KEY or None,
        "timeout": settings.DBRAG_QDRANT_TIMEOUT_SECONDS,
        "prefer_grpc": False,
    }
    grpc_url: Optional[str] = None
    if settings.DBRAG_QDRANT_GRPC_URL:
        grpc_url = str(settings.DBRAG_QDRANT_GRPC_URL)
    if grpc_url:
        kwargs["grpc_url"] = grpc_url
    return QdrantClient(**kwargs)


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    return _create_client()


def ensure_qdrant_ready(retries: int = 5, delay_seconds: float = 2.5) -> None:
    client = get_qdrant_client()
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            client.get_collections()
            if attempt > 1:
                logger.info("Qdrant connection succeeded on attempt %s", attempt)
            return
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "Qdrant not ready yet (attempt %s/%s): %s",
                attempt,
                retries,
                exc,
            )
            time.sleep(delay_seconds)
    raise RuntimeError("Failed to reach Qdrant service") from last_exc
