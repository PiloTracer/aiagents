from __future__ import annotations

import logging
from functools import lru_cache

from app.core.config import settings

from .base import ChatCompletionProvider
from .openai_provider import OpenAIChatProvider

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_chat_provider() -> ChatCompletionProvider:
    """Instantiate the configured chat completion provider."""
    provider_name = (settings.LLM_PROVIDER or "openai").lower()
    logger.info("Initialising chat completion provider: %s", provider_name)
    if provider_name in {"openai", "gpt", "openai_chat"}:
        return OpenAIChatProvider()
    raise ValueError(f"Unsupported LLM provider: {provider_name}")

