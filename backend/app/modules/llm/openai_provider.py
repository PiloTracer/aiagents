from __future__ import annotations

import logging
from typing import Any, Sequence

from openai import OpenAI

from app.core.config import settings

from .base import ChatCompletionProvider

logger = logging.getLogger(__name__)


class OpenAIChatProvider(ChatCompletionProvider):
    """Wrapper around the OpenAI Chat Completions API."""

    def __init__(self) -> None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=str(settings.OPENAI_BASE_URL) if settings.OPENAI_BASE_URL else None,
            organization=settings.OPENAI_ORG,
            project=settings.OPENAI_PROJECT,
        )
        self._model = settings.OPENAI_MODEL or "gpt-4o-mini"

    def name(self) -> str:
        return f"openai:{self._model}"

    def generate(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
        }
        if temperature is not None:
            payload["temperature"] = temperature
        else:
            payload["temperature"] = settings.OPENAI_TEMPERATURE

        if max_tokens is not None and max_tokens > 0:
            payload["max_tokens"] = max_tokens

        try:
            response = self._client.chat.completions.create(**payload)
        except Exception as exc:  # noqa: BLE001
            logger.exception("OpenAI chat completion failed: %s", exc)
            raise

        choice = response.choices[0]
        return choice.message.content or ""

    def health_check(self) -> bool:
        try:
            self._client.models.list()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI provider health check failed: %s", exc)
            return False
