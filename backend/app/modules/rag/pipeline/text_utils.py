from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


_PRESERVED_WHITESPACE = {"\n", "\r", "\t"}
_WHITESPACE_CATEGORIES = {"Zs"}
_NEWLINE_CATEGORIES = {"Zl", "Zp"}


@dataclass(slots=True)
class SanitizedText:
    text: str
    removed_count: int = 0
    removed_samples: list[str] = field(default_factory=list)
    newline_normalized: int = 0

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "removed_count": self.removed_count,
            "removed_samples": self.removed_samples,
            "newline_normalized": self.newline_normalized,
        }


def sanitize_text(value: str) -> SanitizedText:
    """
    Normalise unicode text and strip characters that frequently trip upstream tokenizers.

    Returns a SanitizedText with the cleaned result and metadata about removals.
    """
    if not value:
        return SanitizedText(text="")

    normalized = unicodedata.normalize("NFKC", value)
    kept_chars: list[str] = []
    removed_samples: list[str] = []
    removed = 0
    newline_normalized = 0

    for ch in normalized:
        if ch in _PRESERVED_WHITESPACE:
            kept_chars.append(ch)
            continue

        category = unicodedata.category(ch)

        if category in _NEWLINE_CATEGORIES:
            kept_chars.append("\n")
            newline_normalized += 1
            continue

        if category in _WHITESPACE_CATEGORIES:
            kept_chars.append(" ")
            continue

        # Drop all characters that fall under the "Other" unicode categories.
        if category.startswith("C"):
            removed += 1
            if len(removed_samples) < 10:
                removed_samples.append(f"U+{ord(ch):04X}")
            continue

        # Drop NULL or other non-printable characters even if category check missed them.
        if ord(ch) < 32:
            removed += 1
            if len(removed_samples) < 10:
                removed_samples.append(f"U+{ord(ch):04X}")
            continue

        kept_chars.append(ch)

    cleaned = "".join(kept_chars)
    return SanitizedText(
        text=cleaned,
        removed_count=removed,
        removed_samples=removed_samples,
        newline_normalized=newline_normalized,
    )

