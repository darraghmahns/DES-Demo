"""
All extraction engines (OpenAI, local VLM, etc.) must implement this interface.
Use get_engine() to get the configured engine instance.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any

from schemas import VerificationCitation


class OCREngine(ABC):
    """Base class for document extraction engines."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable engine name (e.g., 'openai', 'local')."""
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Model identifier for logging (e.g., 'gpt-4o', 'qwen2.5-vl-32b')."""
        ...

    @property
    def prefers_file_path(self) -> bool:
        """Whether this engine works better with file paths than base64 images.

        Engines like Docling benefit from native PDF parsing (layout, tables,
        reading order) rather than receiving pre-rasterized images.
        Override to return True and implement the *_from_file methods.
        """
        return False

    @abstractmethod
    def extract(self, images_b64: list[str], mode: str) -> tuple[dict, dict]:
        """Extract structured data from document page images.

        Args:
            images_b64: List of base64-encoded PNG strings, one per page.
            mode: 'real_estate' or 'gov'.

        Returns:
            Tuple of (parsed dict matching target schema, usage dict with token counts).
        """
        ...

    def extract_from_file(self, file_path: str, mode: str) -> tuple[dict, dict]:
        """Extract structured data directly from a PDF file.

        Engines that set prefers_file_path=True should override this.
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(f"{self.name} engine does not support file-based extraction")

    @abstractmethod
    def verify(
        self,
        images_b64: list[str],
        extracted_data: dict,
        required_field_targets: list[dict[str, Any]] | None = None,
    ) -> tuple[list[VerificationCitation], dict]:
        """Verify extraction by citing source locations for each value.

        Args:
            images_b64: List of base64-encoded page images.
            extracted_data: The previously extracted data dict.

        Returns:
            Tuple of (list of VerificationCitation objects, usage dict with token counts).
        """
        ...

    def verify_from_file(
        self,
        file_path: str,
        extracted_data: dict,
        required_field_targets: list[dict[str, Any]] | None = None,
    ) -> tuple[list[VerificationCitation], dict]:
        """Verify extraction using the original PDF file.

        Engines that set prefers_file_path=True should override this.
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(f"{self.name} engine does not support file-based verification")

    def recover_missing_fields(
        self,
        images_b64: list[str],
        extracted_data: dict,
        field_targets: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict]:
        """Recover missing comparison-visible fields from page images.

        Engines may override this to perform a targeted follow-up extraction pass.
        Default behavior is a no-op.
        """
        return {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def recover_missing_fields_from_file(
        self,
        file_path: str,
        extracted_data: dict,
        field_targets: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict]:
        """Recover missing comparison-visible fields using the original PDF file."""
        return {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @abstractmethod
    def ocr_raw_text(self, images_b64: list[str]) -> tuple[list[str], dict]:
        """Extract raw text from images for PII scanning.

        Args:
            images_b64: List of base64-encoded PNG strings.

        Returns:
            Tuple of (list of raw text strings one per page, usage dict with token counts).
        """
        ...

    def ocr_raw_text_from_file(self, file_path: str) -> tuple[list[str], dict]:
        """Extract raw text directly from a PDF file.

        Engines that set prefers_file_path=True should override this.
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(f"{self.name} engine does not support file-based OCR")

    def classify_real_estate_metadata(self, metadata: dict[str, Any]) -> tuple[dict, dict]:
        """Classify a real-estate document from parsed metadata only.

        Engines may override this to provide a lightweight model fallback when
        deterministic classification fails.
        """
        return {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def summarize_real_estate_document(
        self,
        images_b64: list[str],
        classification: dict[str, Any],
    ) -> tuple[dict, dict]:
        """Extract a generic structured summary for non-offer real-estate forms."""
        return {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def summarize_real_estate_document_from_file(
        self,
        file_path: str,
        classification: dict[str, Any],
    ) -> tuple[dict, dict]:
        """File-based generic real-estate summary extraction."""
        return {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def get_engine(engine_name: str | None = None) -> OCREngine:
    """Factory: return the configured OCR engine.

    Args:
        engine_name: 'openai' or 'local'. If None, reads ENGINE from env
                     (defaults to 'openai').

    Returns:
        An OCREngine instance.
    """
    name = engine_name or os.getenv("ENGINE", "openai")

    if name == "openai":
        from openai_engine import OpenAIEngine
        return OpenAIEngine()
    elif name == "local":
        from local_engine import LocalEngine
        return LocalEngine()
    else:
        raise ValueError(f"Unknown engine: {name!r}. Use 'openai' or 'local'.")
