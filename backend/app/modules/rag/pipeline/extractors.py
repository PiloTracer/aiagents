from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class TextExtractor(Protocol):
    def extract(self, path: Path) -> str: ...


class DoclingExtractor:
    """High fidelity extractor backed by Docling."""

    def __init__(self) -> None:
        try:
            from docling.document_converter import DocumentConverter  # type: ignore
        except ImportError as exc:  # pragma: no cover - import guard
            raise RuntimeError(
                "Docling is not installed. Ensure 'docling' is present in the environment."
            ) from exc
        self._converter = DocumentConverter()

    def extract(self, path: Path) -> str:
        result = self._converter.convert(path)
        document = getattr(result, "document", None)
        if not document:
            raise ValueError(f"Docling failed to parse document: {path}")
        text = document.export_to_text()
        return text.strip()


class PlaintextFallbackExtractor:
    """Fallback for plain text formats if Docling is unavailable."""

    def extract(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1", errors="replace")


class CompositeExtractor:
    """Tries Docling first, then falls back to a plain text extractor."""

    def __init__(self, docling_enabled: bool = True) -> None:
        self._docling: TextExtractor | None = None
        if docling_enabled:
            try:
                self._docling = DoclingExtractor()
            except Exception as exc:
                logger.warning("Docling extractor unavailable, falling back to plaintext. Error: %s", exc)
        self._fallback = PlaintextFallbackExtractor()

    def extract(self, path: Path) -> str:
        if self._docling:
            try:
                return self._docling.extract(path)
            except Exception as exc:
                logger.warning("Docling extraction failed for %s: %s", path, exc)
        return self._fallback.extract(path)
