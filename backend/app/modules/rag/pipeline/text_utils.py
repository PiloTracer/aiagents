from __future__ import annotations

import unicodedata


def sanitize_text(value: str) -> tuple[str, int]:
    """
    Remove control characters that frequently trip upstream tokenizers.

    Returns a tuple of the sanitized text and the number of characters stripped.
    """
    if not value:
        return "", 0

    normalized = unicodedata.normalize("NFKC", value)
    kept_chars: list[str] = []
    removed = 0
    for ch in normalized:
        # Preserve common whitespace; drop other control characters.
        if ch in ("\n", "\r", "\t"):
            kept_chars.append(ch)
            continue

        category = unicodedata.category(ch)
        if category in {"Cc", "Cs"}:
            removed += 1
            continue

        # Drop NULL or other non-printable characters even if category check missed them.
        if ord(ch) < 32:
            removed += 1
            continue

        kept_chars.append(ch)

    cleaned = "".join(kept_chars)
    return cleaned, removed

