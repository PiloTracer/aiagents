from __future__ import annotations

import logging
from pathlib import Path
import inspect
import io
import os
import re
import tempfile
from typing import Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

try:  # Optional dependencies used for OCR/image processing
    import numpy as np
except Exception:  # pragma: no cover - optional
    np = None  # type: ignore

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None  # type: ignore

try:
    from PIL import Image  # type: ignore
except Exception:  # pragma: no cover
    Image = None  # type: ignore


class TextExtractor(Protocol):
    def extract(self, path: Path) -> str: ...


def _is_meaningful_text(value: str, *, min_chars: int = 80, min_alnum_ratio: float = 0.02) -> bool:
    if not value:
        return False
    text = value.strip()
    if not text:
        return False
    length = len(text)
    if length >= min_chars:
        return True
    alnum = sum(1 for ch in text if ch.isalnum())
    return length > 0 and (alnum / length) >= min_alnum_ratio


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
        text = text.strip()
        if not _is_meaningful_text(text):
            raise ValueError("Docling produced insufficient textual content")
        return text


class PdfMinerExtractor:
    """Text extractor leveraging pdfminer.six for digital PDFs."""

    def __init__(self) -> None:
        try:
            from pdfminer.high_level import extract_text  # type: ignore

            self._extract_text = extract_text
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.debug("pdfminer not available: %s", exc)
            self._extract_text = None

    def extract(self, path: Path) -> str:
        if not self._extract_text:
            raise RuntimeError("pdfminer backend unavailable")
        text = self._extract_text(str(path))
        if not text:
            raise RuntimeError("pdfminer returned no text")
        text = text.strip()
        if not _is_meaningful_text(text):
            raise RuntimeError("pdfminer produced insufficient text")
        return text


class OCRPipeline:
    """Shared OCR pipeline with ordered fallbacks."""

    def __init__(self) -> None:
        self._languages = (settings.TESS_LANGS or "spa").replace(",", "+").replace(" ", "")
        self._rapidocr = None
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore

            self._rapidocr = RapidOCR(use_angle_cls=True)
            logger.info("RapidOCR backend initialised")
        except Exception as exc:
            logger.debug("RapidOCR unavailable: %s", exc)

        self._pytesseract = None
        if Image is not None:
            try:
                import pytesseract  # type: ignore

                self._pytesseract = pytesseract
            except Exception as exc:
                logger.debug("pytesseract unavailable: %s", exc)
        else:
            logger.debug("Pillow not available; pytesseract disabled")

        self._tesserocr = None
        try:
            import tesserocr  # type: ignore

            self._tesserocr = tesserocr
        except Exception as exc:
            logger.debug("tesserocr unavailable: %s", exc)

        self._easyocr_reader = None
        self._easyocr_failed = False
        self._ocrmac = None
        try:
            import ocrmac  # type: ignore

            self._ocrmac = ocrmac
        except Exception as exc:
            logger.debug("ocrmac unavailable: %s", exc)

        self._available = cv2 is not None and np is not None and Image is not None

    def _enhance_image(self, image_bgr):
        if cv2 is None:
            return image_bgr
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        if gray.mean() < 80:
            gray = cv2.bitwise_not(gray)
        thresh = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            11,
        )
        return cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

    def _get_easyocr_reader(self):
        if self._easyocr_reader or self._easyocr_failed:
            return self._easyocr_reader
        try:
            import easyocr  # type: ignore

            langs = [lang.strip() for lang in self._languages.split("+") if lang.strip()]
            if not langs:
                langs = ["en"]
            self._easyocr_reader = easyocr.Reader(langs, gpu=False)
            logger.info("EasyOCR backend initialised")
        except Exception as exc:
            self._easyocr_failed = True
            logger.debug("EasyOCR unavailable: %s", exc)
        return self._easyocr_reader

    def _rapidocr_text(self, image_bgr):
        if not self._rapidocr:
            return ""
        try:
            result, _ = self._rapidocr(image_bgr)
            texts = [item[1].strip() for item in (result or []) if item[1].strip()]
            return "\n".join(texts)
        except Exception as exc:
            logger.debug("RapidOCR inference failed: %s", exc)
            return ""

    def _pytesseract_text(self, image_bgr):
        if not (self._pytesseract and Image is not None and cv2 is not None):
            return ""
        try:
            rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
            return self._pytesseract.image_to_string(Image.fromarray(rgb), lang=self._languages)
        except Exception as exc:
            logger.debug("pytesseract inference failed: %s", exc)
            return ""

    def _tesserocr_text(self, image_bgr):
        if not (self._tesserocr and Image is not None and cv2 is not None):
            return ""
        try:
            with self._tesserocr.PyTessBaseAPI(lang=self._languages) as api:
                rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
                api.SetImage(Image.fromarray(rgb))
                return api.GetUTF8Text()
        except Exception as exc:
            logger.debug("tesserocr inference failed: %s", exc)
            return ""

    def _easyocr_text(self, image_bgr):
        reader = self._get_easyocr_reader()
        if not reader:
            return ""
        try:
            results = reader.readtext(image_bgr, detail=0)
            return "\n".join(item.strip() for item in results if item.strip())
        except Exception as exc:
            logger.debug("EasyOCR inference failed: %s", exc)
            return ""

    def _ocrmac_text(self, image_bgr):
        if not (self._ocrmac and cv2 is not None):
            return ""
        tmp_path = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_path = tmp.name
            tmp.close()
            cv2.imwrite(tmp_path, image_bgr)
            result = self._ocrmac.ocr(tmp_path)
            if isinstance(result, (list, tuple)):
                result = "\n".join(str(item) for item in result if str(item).strip())
            return (result or "").strip()
        except Exception as exc:
            logger.debug("OCRMac inference failed: %s", exc)
            return ""
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def run_on_image(self, image_bgr):
        if not self._available:
            return ""
        enhanced = self._enhance_image(image_bgr)
        for candidate in (
            self._rapidocr_text(enhanced),
            self._pytesseract_text(enhanced),
            self._tesserocr_text(enhanced),
            self._easyocr_text(enhanced),
            self._ocrmac_text(enhanced),
            self._rapidocr_text(image_bgr),
            self._pytesseract_text(image_bgr),
            self._tesserocr_text(image_bgr),
            self._easyocr_text(image_bgr),
            self._ocrmac_text(image_bgr),
        ):
            candidate = (candidate or "").strip()
            if _is_meaningful_text(candidate):
                return candidate
        return ""

    def run_on_path(self, path: Path) -> str:
        if not (self._available and cv2 is not None):
            return ""
        image_bgr = cv2.imread(str(path))
        if image_bgr is None:
            return ""
        return self.run_on_image(image_bgr)



class PdfImageOCRExtractor:
    """Render PDF pages and run OCR for scanned/image-only documents."""

    def __init__(self) -> None:
        try:
            import fitz  # type: ignore

            self._fitz = fitz
            self._matrix = fitz.Matrix(4, 4)  # ~288 DPI render
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.debug("PyMuPDF unavailable: %s", exc)
            self._fitz = None
            self._matrix = None
        self._ocr = OCRPipeline()

    def _pix_to_bgr(self, pix) -> "np.ndarray":
        if np is None or cv2 is None:
            raise RuntimeError("OpenCV and numpy are required for OCR pipeline")
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 4:
            arr = arr[:, :, :3]
        elif pix.n == 1:
            arr = np.repeat(arr, 3, axis=2)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    def extract(self, path: Path) -> str:
        if not (self._fitz and self._matrix):
            raise RuntimeError("PDF image OCR backend not available")
        doc = self._fitz.open(str(path))
        try:
            snippets: list[str] = []
            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                pix = page.get_pixmap(matrix=self._matrix, alpha=False)
                bgr = self._pix_to_bgr(pix)
                text = self._ocr.run_on_image(bgr)
                if _is_meaningful_text(text):
                    snippets.append(text.strip())
            if not snippets:
                raise RuntimeError("PDF image OCR produced no text")
            return "\n\n".join(snippets)
        finally:
            doc.close()


class PlaintextFallbackExtractor:
    """Fallback for plain text formats."""

    def extract(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1", errors="replace")


class CompositeExtractor:
    """Tries Docling, then PDF text/image fallbacks, then general OCR, then plaintext."""

    PDF_SUFFIXES = {".pdf"}
    IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}

    def __init__(self, docling_enabled: bool = True) -> None:
        self._docling: TextExtractor | None = None
        if docling_enabled:
            try:
                self._docling = DoclingExtractor()
            except Exception as exc:
                logger.warning("Docling extractor unavailable, falling back to plaintext. Error: %s", exc)
        self._pdf_text: PdfMinerExtractor | None = None
        try:
            self._pdf_text = PdfMinerExtractor()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("pdfminer extractor unavailable: %s", exc)
        self._pdf_image: PdfImageOCRExtractor | None = None
        try:
            self._pdf_image = PdfImageOCRExtractor()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("PDF image OCR extractor unavailable: %s", exc)
        self._image_ocr = OCRPipeline()
        self._fallback = PlaintextFallbackExtractor()

    def extract(self, path: Path) -> str:
        suffix = path.suffix.lower()

        if self._docling:
            try:
                return self._docling.extract(path)
            except Exception as exc:
                logger.warning("Docling extraction failed for %s: %s", path, exc)

        if suffix in self.PDF_SUFFIXES:
            if self._pdf_text:
                try:
                    text = self._pdf_text.extract(path)
                    if _is_meaningful_text(text):
                        return text
                except Exception as exc:
                    logger.debug("pdfminer fallback failed for %s: %s", path, exc)
            if self._pdf_image:
                try:
                    text = self._pdf_image.extract(path)
                    if _is_meaningful_text(text):
                        return text
                except Exception as exc:
                    logger.debug("PDF image OCR fallback failed for %s: %s", path, exc)

        if suffix in self.IMAGE_SUFFIXES and self._image_ocr:
            try:
                text = self._image_ocr.run_on_path(path)
                if _is_meaningful_text(text):
                    return text
            except Exception as exc:
                logger.debug("Image OCR pipeline failed for %s: %s", path, exc)

        return self._fallback.extract(path)
