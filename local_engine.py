"""Local self-hosted OCR engine — Docling + Ollama.

Pipeline:
  PDF → Docling (layout-aware parsing) → Structured Markdown
      → Ollama LLM (JSON extraction) → Pydantic validation

Requirements:
  pip install docling ollama
  ollama pull qwen3:4b       (or qwen3:8b for better quality)

Configuration (.env):
  ENGINE=local
  OLLAMA_MODEL=qwen3:4b      (optional, default qwen3:4b)
  OLLAMA_HOST=http://localhost:11434  (optional)
"""

from __future__ import annotations

import json
import logging
import os
import base64
import tempfile
from collections import defaultdict
from io import BytesIO

from PIL import Image
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from ollama import Client as OllamaClient

from ocr_engine import OCREngine
from schemas import (
    DotloopLoopDetails,
    FOIARequest,
    VerificationCitation,
)
from extractor import REAL_ESTATE_SYSTEM_PROMPT, GOV_SYSTEM_PROMPT, OCR_SYSTEM_PROMPT
from verifier import VERIFICATION_SYSTEM_PROMPT

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapted system prompts for text-based (non-vision) extraction
# ---------------------------------------------------------------------------

_EXTRACT_PREAMBLE = (
    "You will receive the full text of a document converted to Markdown. "
    "Tables are preserved as Markdown tables. "
    "Extract data ONLY from what is explicitly written in the text below.\n\n"
)

_VERIFY_PREAMBLE = (
    "You will receive the full Markdown text of a document, followed by "
    "previously extracted data. Verify each field by citing its source location.\n\n"
)


class LocalEngine(OCREngine):
    """Self-hosted extraction engine using Docling + Ollama."""

    def __init__(self) -> None:
        self._model = os.getenv("OLLAMA_MODEL", "qwen3:4b")
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self._ollama = OllamaClient(host=host)

        # Configure Docling for high-quality PDF parsing
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.table_structure_options.do_cell_matching = True

        self._converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pipeline_options
                )
            }
        )
        log.info(f"LocalEngine initialized: model={self._model}, host={host}")

    # -- Properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        return "local"

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def prefers_file_path(self) -> bool:
        return True

    # -- Internal helpers ----------------------------------------------------

    def _convert_pdf(self, file_path: str) -> str:
        """Convert a PDF to Markdown using Docling."""
        log.info(f"Docling converting: {file_path}")
        result = self._converter.convert(file_path)
        markdown = result.document.export_to_markdown()
        log.info(f"Docling conversion complete: {len(markdown)} chars")
        return markdown

    def _convert_pdf_per_page(self, file_path: str) -> list[str]:
        """Convert a PDF and return text grouped by page number."""
        result = self._converter.convert(file_path)
        pages: dict[int, list[str]] = defaultdict(list)

        for item, _level in result.document.iterate_items():
            text = getattr(item, "text", "").strip()
            if not text:
                continue
            if hasattr(item, "prov") and item.prov:
                page_no = item.prov[0].page_no
                pages[page_no].append(text)

        # Return list ordered by page number
        if not pages:
            return [result.document.export_to_markdown()]
        return ["\n".join(pages[p]) for p in sorted(pages.keys())]

    def _b64_images_to_temp_pdf(self, images_b64: list[str]) -> str:
        """Reconstruct a temporary PDF from base64-encoded PNG images.

        This is a fallback for when only images_b64 is available (e.g. the
        server.py SSE path). Quality is lower than using the original PDF.
        """
        pil_images = []
        for b64 in images_b64:
            img_bytes = base64.b64decode(b64)
            pil_images.append(Image.open(BytesIO(img_bytes)).convert("RGB"))

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        if len(pil_images) == 1:
            pil_images[0].save(tmp.name, format="PDF")
        else:
            pil_images[0].save(
                tmp.name, format="PDF", save_all=True, append_images=pil_images[1:]
            )
        log.info(f"Reconstructed temp PDF from {len(images_b64)} images: {tmp.name}")
        return tmp.name

    def _chat(
        self,
        system_prompt: str,
        user_content: str,
        json_schema: dict | None = None,
    ) -> str:
        """Send a chat completion request to Ollama.

        Args:
            system_prompt: System message.
            user_content: User message (the document text).
            json_schema: Optional JSON schema to constrain output format.

        Returns:
            The model's response text.
        """
        kwargs: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "options": {"temperature": 0},
        }
        if json_schema is not None:
            kwargs["format"] = json_schema

        response = self._ollama.chat(**kwargs)
        return response.message.content

    def _get_schema_for_mode(self, mode: str) -> type:
        """Return the Pydantic model class for the given mode."""
        if mode == "real_estate":
            return DotloopLoopDetails
        return FOIARequest

    # -- File-based methods (preferred) --------------------------------------

    def extract_from_file(self, file_path: str, mode: str) -> dict:
        """Extract structured data directly from a PDF file using Docling + Ollama."""
        markdown = self._convert_pdf(file_path)
        schema_cls = self._get_schema_for_mode(mode)
        system_prompt = (
            REAL_ESTATE_SYSTEM_PROMPT if mode == "real_estate" else GOV_SYSTEM_PROMPT
        )

        user_msg = (
            _EXTRACT_PREAMBLE
            + "--- DOCUMENT TEXT ---\n\n"
            + markdown
            + "\n\n--- END DOCUMENT ---\n\n"
            + "Extract all data from the above document into the JSON schema specified. "
            + "Return ONLY valid JSON."
        )

        raw_json = self._chat(
            system_prompt=system_prompt,
            user_content=user_msg,
            json_schema=schema_cls.model_json_schema(),
        )

        return json.loads(raw_json)

    def verify_from_file(
        self, file_path: str, extracted_data: dict
    ) -> list[VerificationCitation]:
        """Verify extraction using the original PDF via Docling + Ollama."""
        markdown = self._convert_pdf(file_path)

        user_msg = (
            _VERIFY_PREAMBLE
            + "--- DOCUMENT TEXT ---\n\n"
            + markdown
            + "\n\n--- END DOCUMENT ---\n\n"
            + "Here is the data that was extracted from the above document. "
            + "Verify each field by citing its exact source location.\n\n"
            + f"Extracted data:\n{json.dumps(extracted_data, indent=2)}"
        )

        citation_schema = {
            "type": "object",
            "properties": {
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_name": {"type": "string"},
                            "extracted_value": {"type": "string"},
                            "page_number": {"type": "integer"},
                            "line_or_region": {"type": "string"},
                            "surrounding_text": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": [
                            "field_name",
                            "extracted_value",
                            "page_number",
                            "line_or_region",
                            "surrounding_text",
                            "confidence",
                        ],
                    },
                }
            },
            "required": ["citations"],
        }

        raw_json = self._chat(
            system_prompt=VERIFICATION_SYSTEM_PROMPT,
            user_content=user_msg,
            json_schema=citation_schema,
        )

        raw = json.loads(raw_json)
        citations_raw = raw.get("citations", [])
        citations: list[VerificationCitation] = []
        for c in citations_raw:
            try:
                citations.append(VerificationCitation.model_validate(c))
            except Exception:
                continue

        return citations

    def ocr_raw_text_from_file(self, file_path: str) -> list[str]:
        """Extract raw text per page directly from a PDF file using Docling."""
        return self._convert_pdf_per_page(file_path)

    # -- Image-based methods (fallback, for server.py SSE path) --------------

    def extract(self, images_b64: list[str], mode: str) -> dict:
        """Fallback: reconstruct PDF from images, then extract via Docling."""
        tmp_pdf = self._b64_images_to_temp_pdf(images_b64)
        try:
            return self.extract_from_file(tmp_pdf, mode)
        finally:
            os.unlink(tmp_pdf)

    def verify(
        self, images_b64: list[str], extracted_data: dict
    ) -> list[VerificationCitation]:
        """Fallback: reconstruct PDF from images, then verify via Docling."""
        tmp_pdf = self._b64_images_to_temp_pdf(images_b64)
        try:
            return self.verify_from_file(tmp_pdf, extracted_data)
        finally:
            os.unlink(tmp_pdf)

    def ocr_raw_text(self, images_b64: list[str]) -> list[str]:
        """Fallback: reconstruct PDF from images, then OCR via Docling."""
        tmp_pdf = self._b64_images_to_temp_pdf(images_b64)
        try:
            return self.ocr_raw_text_from_file(tmp_pdf)
        finally:
            os.unlink(tmp_pdf)
