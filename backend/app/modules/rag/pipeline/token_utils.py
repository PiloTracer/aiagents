from __future__ import annotations

import logging
from dataclasses import dataclass, field
import re
import unicodedata
from typing import Iterable, List, Sequence

try:
    import tiktoken
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    tiktoken = None  # type: ignore[assignment]

from .text_utils import sanitize_text, SanitizedText

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TokenReport:
    chunk_index: int
    sanitized: SanitizedText
    token_count: int
    tokens: List[int]
    sample_tokens: List[int]
    sample_text: str
    invalid_characters: int
    validation_note: str

    def as_dict(self) -> dict:
        return {
            "chunk_index": self.chunk_index,
            "token_count": self.token_count,
            "invalid_characters": self.invalid_characters,
            "removed_characters": self.sanitized.removed_count,
            "removed_samples": self.sanitized.removed_samples,
            "sample_tokens": self.sample_tokens,
            "sample_text": self.sample_text,
            "validation_note": self.validation_note,
        }


@dataclass(slots=True)
class BatchTokenSummary:
    total_chunks: int
    total_tokens: int
    total_removed_chars: int
    total_invalid_tokens: int
    reports: List[TokenReport] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total_chunks": self.total_chunks,
            "total_tokens": self.total_tokens,
            "total_removed_characters": self.total_removed_chars,
            "total_invalid_tokens": self.total_invalid_tokens,
            "samples": [report.as_dict() for report in self.reports[:5]],
        }


class TokenAnalyzer:
    """
    Utility responsible for preparing text before embedding and collecting token statistics.
    """

    def __init__(self, *, model_name: str | None = None) -> None:
        self.encoding = self._load_encoding(model_name)
        self.using_fallback = tiktoken is None

    @staticmethod
    def _load_encoding(model_name: str | None):
        if tiktoken is None:
            logger.warning(
                "tiktoken not available; using basic UTF-8 tokenizer fallback. "
                "Install 'tiktoken' for accurate token accounting."
            )
            return _BasicEncoding()
        try:
            if model_name:
                return tiktoken.encoding_for_model(model_name)
        except Exception:
            logger.debug("tiktoken encoding_for_model failed for %s, falling back to cl100k_base", model_name)
        return tiktoken.get_encoding("cl100k_base")

    def _basic_cleanup(self, sanitized: SanitizedText) -> SanitizedText:
        text = sanitized.text
        whitespace_collapsed = sanitized.whitespace_collapsed
        newline_normalized = sanitized.newline_normalized

        replacements = {
            "\u00A0": " ",
            "\u2028": " ",
            "\u2029": " ",
            "\r": " ",
        }
        for src, dst in replacements.items():
            if src in text:
                text = text.replace(src, dst)
                whitespace_collapsed += 1
        if "\n" in text:
            text = text.replace("\n", " ")
            newline_normalized += 1

        collapsed_text = re.sub(r"\s+", " ", text).strip()
        if collapsed_text != text:
            whitespace_collapsed += 1

        return SanitizedText(
            text=collapsed_text,
            removed_count=sanitized.removed_count,
            removed_samples=list(sanitized.removed_samples),
            newline_normalized=newline_normalized,
            whitespace_collapsed=whitespace_collapsed,
        )

    def prepare_chunks(self, texts: Sequence[str]) -> BatchTokenSummary:
        reports: List[TokenReport] = []
        total_tokens = 0
        total_removed = 0
        total_invalid = 0

        for idx, text in enumerate(texts):
            report = self.prepare_text(text, chunk_index=idx)
            reports.append(report)
            total_tokens += report.token_count
            total_removed += report.sanitized.removed_count
            total_invalid += report.invalid_characters

        summary = BatchTokenSummary(
            total_chunks=len(texts),
            total_tokens=total_tokens,
            total_removed_chars=total_removed,
            total_invalid_tokens=total_invalid,
            reports=reports,
        )

        logger.info(
            "Token analysis: chunks=%d, total_tokens=%d, removed_chars=%d, invalid_tokens=%d, sample_tokens=%s",
            summary.total_chunks,
            summary.total_tokens,
            summary.total_removed_chars,
            summary.total_invalid_tokens,
            summary.reports[0].sample_tokens if summary.reports else [],
        )
        return summary

    def prepare_text(self, text: str, *, chunk_index: int) -> TokenReport:
        sanitized = self._basic_cleanup(sanitize_text(text))
        encoded_tokens = self.encoding.encode(sanitized.text, disallowed_special=())
        decoded_text = self.encoding.decode(encoded_tokens)

        invalid_chars = 0
        validation_note = "Round-trip encoding matches sanitized text."
        if decoded_text != sanitized.text:
            invalid_chars = len(sanitized.text) - len(decoded_text)
            validation_note = (
                "Round-trip encoding adjusted text to match tokenizer output; "
                f"{invalid_chars} character(s) replaced."
            )
            sanitized = SanitizedText(
                text=decoded_text,
                removed_count=sanitized.removed_count + invalid_chars,
                removed_samples=sanitized.removed_samples,
                newline_normalized=sanitized.newline_normalized,
            )

        sample_tokens = encoded_tokens[:10]
        sample_text = sanitized.text[:120]

        logger.debug(
            "Chunk %d token report: tokens=%d, removed_chars=%d, invalid_chars=%d, sample_tokens=%s",
            chunk_index,
            len(encoded_tokens),
            sanitized.removed_count,
            invalid_chars,
            sample_tokens,
        )

        return TokenReport(
            chunk_index=chunk_index,
            sanitized=sanitized,
            token_count=len(encoded_tokens),
            tokens=encoded_tokens,
            sample_tokens=sample_tokens,
            sample_text=sample_text,
            invalid_characters=invalid_chars,
            validation_note=validation_note,
        )

    def enforce_ascii(self, text: str, *, chunk_index: int) -> TokenReport:
        ascii_text = text.encode("ascii", "ignore").decode("ascii")
        logger.warning(
            "Chunk %d required ASCII fallback; original length=%d, ascii length=%d",
            chunk_index,
            len(text),
            len(ascii_text),
        )
        report = self.prepare_text(ascii_text, chunk_index=chunk_index)
        removed_chars = max(len(text) - len(ascii_text), 0)
        if removed_chars:
            report.sanitized.removed_count += removed_chars
            available = max(0, 10 - len(report.sanitized.removed_samples))
            if available:
                report.sanitized.removed_samples.append("ASCII_TRIM")
        return report

    def enforce_restricted_charset(self, text: str, *, chunk_index: int) -> TokenReport:
        normalized = unicodedata.normalize("NFKD", text)
        allowed_chars = []
        removed = 0
        samples: list[str] = []
        for ch in normalized:
            category = unicodedata.category(ch)
            if category == "Mn":
                removed += 1
                if len(samples) < 10:
                    samples.append(f"COMBINING:{unicodedata.name(ch, 'UNKNOWN')}")
                continue
            if ch.isalnum() or ch in {" ", ".", ",", ";", ":", "-", "'", '"', "/", "?", "!", "(", ")", "%"}:
                if ch == "\n":
                    ch = " "
                allowed_chars.append(ch)
                continue
            if ch in {"\t", "\r"}:
                allowed_chars.append(" ")
                removed += 1
                continue
            removed += 1
            if len(samples) < 10:
                samples.append(f"REMOVED:{unicodedata.name(ch, 'UNKNOWN')}")
        restricted = "".join(allowed_chars)
        restricted = re.sub(r"\s+", " ", restricted).strip()
        logger.warning(
            "Chunk %d required restricted charset fallback; removed=%d",
            chunk_index,
            removed,
        )
        report = self.prepare_text(restricted, chunk_index=chunk_index)
        report.sanitized.removed_count += removed
        if samples:
            available = max(0, 10 - len(report.sanitized.removed_samples))
            if available:
                report.sanitized.removed_samples.extend(samples[:available])
        return report


class _BasicEncoding:
    """Minimal tokenizer used when tiktoken is unavailable."""

    def encode(self, text: str, disallowed_special: Iterable[str] | None = None) -> list[int]:
        _ = disallowed_special  # unused
        return list(text.encode("utf-8", errors="ignore"))

    def decode(self, tokens: Iterable[int]) -> str:
        data = bytes(int(token) & 0xFF for token in tokens)
        return data.decode("utf-8", errors="ignore")
