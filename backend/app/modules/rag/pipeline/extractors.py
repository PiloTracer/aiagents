from __future__ import annotations

import logging
from pathlib import Path
import inspect
from typing import Protocol

from app.core.config import settings

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

        self._vlm_enabled = False
        self._converter = None
        if settings.DOCLING_VLM_MODEL:
            try:
                pipeline_hint, pipeline_options = self._resolve_vlm_pipeline()
                init_kwargs: dict[str, object] = {}
                init_signature = getattr(DocumentConverter, "__init__")
                init_params = getattr(init_signature, "__code__", None)
                param_names = []
                if init_params is not None:
                    param_names = init_signature.__code__.co_varnames[: init_signature.__code__.co_argcount]
                else:  # pragma: no cover - defensive
                    import inspect

                    param_names = list(inspect.signature(DocumentConverter).parameters.keys())

                if "pipeline_profile" in param_names:
                    init_kwargs["pipeline_profile"] = pipeline_hint
                elif "pipeline" in param_names:
                    init_kwargs["pipeline"] = pipeline_hint
                elif "pipeline_hint" in param_names:  # older alias
                    init_kwargs["pipeline_hint"] = pipeline_hint

                if "pipeline_options" in param_names:
                    init_kwargs["pipeline_options"] = pipeline_options
                elif "pipeline_profile_options" in param_names:
                    init_kwargs["pipeline_profile_options"] = pipeline_options

                self._converter = DocumentConverter(**init_kwargs)
                self._vlm_enabled = True
                logger.info(
                    "Docling VLM pipeline enabled with model %s",
                    pipeline_options.get("vlm_model"),
                )
            except Exception as exc:  # pragma: no cover - fallback path
                logger.warning("Docling VLM pipeline disabled: %s", exc)

        if self._converter is None:
            self._converter = DocumentConverter()

    @staticmethod
    def _resolve_vlm_pipeline():
        model_name = settings.DOCLING_VLM_MODEL
        if not model_name:
            raise ValueError("DOCLING_VLM_MODEL is not configured")
        try:
            from docling.pipeline.pipeline_profiles import PipelineProfiles  # type: ignore

            return PipelineProfiles.VLM_PIPELINE, {"vlm_model": model_name}
        except Exception:  # pragma: no cover - compatibility path
            try:
                from docling.document_converter import PipelineProfile  # type: ignore

                return PipelineProfile.VLM_PIPELINE, {"vlm_model": model_name}
            except Exception:
                return "vlm", {"vlm_model": model_name}

    def extract(self, path: Path) -> str:
        logger.info("Docling: converting %s", path)
        result = self._converter.convert(path)
        document = getattr(result, "document", None)
        if not document:
            raise ValueError(f"Docling failed to parse document: {path}")
        text = document.export_to_text()
        pages = getattr(document, "pages", None)
        page_count = len(pages) if pages is not None else 0
        logger.info("Docling: conversion complete for %s (%d pages)", path, page_count)
        return text.strip()


class PlaintextFallbackExtractor:
    """Fallback for plain text formats."""

    def extract(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1", errors="replace")


class TesseractExtractor:
    """Fallback using locally installed Tesseract engines."""

    def __init__(self) -> None:
        self._backend: TextExtractor | None = None
        try:
            import tesserocr  # type: ignore

            class _TesserocrBackend:
                def extract(self, path: Path) -> str:
                    return tesserocr.file_to_text(str(path))

            self._backend = _TesserocrBackend()
            logger.info("Tesserocr OCR backend initialised")
        except Exception as exc:
            logger.debug("tesserocr unavailable: %s", exc)
            try:
                import pytesseract  # type: ignore
                from PIL import Image  # type: ignore

                class _PyTesseractBackend:
                    def extract(self, path: Path) -> str:
                        return pytesseract.image_to_string(Image.open(path))

                self._backend = _PyTesseractBackend()
                logger.info("pytesseract OCR backend initialised")
            except Exception as exc2:
                logger.debug("pytesseract unavailable: %s", exc2)

    def extract(self, path: Path) -> str:
        if not self._backend:
            raise RuntimeError("Tesseract backend not available")
        return self._backend.extract(path)


class ThirdPartyOCRExtractor:
    """Optional OCR engines (RapidOCR, ocrmac, EasyOCR)."""

    def __init__(self) -> None:
        self._backend: TextExtractor | None = None

        if not self._backend:
            try:
                from rapidocr_onnxruntime import RapidOCR  # type: ignore

                class _RapidOCRBackend:
                    def __init__(self) -> None:
                        self._ocr = RapidOCR()

                    def extract(self, path: Path) -> str:
                        result, _ = self._ocr(str(path))
                        return "\n".join(result or [])

                self._backend = _RapidOCRBackend()
                logger.info("RapidOCR backend initialised")
            except Exception as exc:
                logger.debug("RapidOCR unavailable: %s", exc)

        if not self._backend:
            try:
                import ocrmac  # type: ignore

                class _OcrmacBackend:
                    def extract(self, path: Path) -> str:
                        return ocrmac.ocr(str(path))

                self._backend = _OcrmacBackend()
                logger.info("ocrmac backend initialised")
            except Exception as exc:
                logger.debug("ocrmac unavailable: %s", exc)

        if not self._backend:
            try:
                import easyocr  # type: ignore

                class _EasyOCRBackend:
                    def __init__(self) -> None:
                        langs = settings.TESS_LANGS.split("+") if settings.TESS_LANGS else ["en"]
                        self.reader = easyocr.Reader(langs, gpu=False)

                    def extract(self, path: Path) -> str:
                        results = self.reader.readtext(str(path), detail=0)
                        return "\n".join(results)

                self._backend = _EasyOCRBackend()
                logger.info("EasyOCR backend initialised")
            except Exception as exc:
                logger.debug("EasyOCR unavailable: %s", exc)

    def extract(self, path: Path) -> str:
        if not self._backend:
            raise RuntimeError("No third-party OCR backend available")
        return self._backend.extract(path)


class CompositeExtractor:
    """Tries Docling, then Tesseract family, other OCR engines, then plaintext."""

    def __init__(self, docling_enabled: bool = True) -> None:
        self._docling: TextExtractor | None = None
        if docling_enabled:
            try:
                self._docling = DoclingExtractor()
            except Exception as exc:
                logger.warning("Docling extractor unavailable, falling back to plaintext. Error: %s", exc)
        self._tesseract: TextExtractor | None = None
        try:
            self._tesseract = TesseractExtractor()
        except Exception as exc:
            logger.debug("Tesseract OCR not available: %s", exc)

        self._third_party: TextExtractor | None = None
        try:
            self._third_party = ThirdPartyOCRExtractor()
        except Exception as exc:
            logger.debug("Third-party OCR not available: %s", exc)
        self._fallback = PlaintextFallbackExtractor()

    def extract(self, path: Path) -> str:
        if self._docling:
            try:
                return self._docling.extract(path)
            except Exception as exc:
                logger.warning("Docling extraction failed for %s: %s", path, exc)

        if self._tesseract:
            try:
                return self._tesseract.extract(path)
            except Exception as exc:
                logger.debug("Tesseract OCR failed for %s: %s", path, exc)

        if self._third_party:
            try:
                return self._third_party.extract(path)
            except Exception as exc:
                logger.debug("Secondary OCR failed for %s: %s", path, exc)

        return self._fallback.extract(path)
