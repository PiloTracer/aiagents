from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence


class ChatCompletionProvider(ABC):
    """Abstract contract for chat completion providers."""

    @abstractmethod
    def generate(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a chat completion string from message history."""

    @abstractmethod
    def name(self) -> str:
        """Return provider identifier."""

    def health_check(self) -> bool:
        """Optional health-check hook."""
        return True

