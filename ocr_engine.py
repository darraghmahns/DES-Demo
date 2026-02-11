"""Abstract OCR engine interface for D.E.S.

All extraction engines (OpenAI, local VLM, etc.) must implement this interface.
Use get_engine() to get the configured engine instance.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

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
        self, images_b64: list[str], extracted_data: dict
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
        self, file_path: str, extracted_data: dict
    ) -> tuple[list[VerificationCitation], dict]:
        """Verify extraction using the original PDF file.

        Engines that set prefers_file_path=True should override this.
        Default implementation raises NotImplementedError.
        """
        raise NotImplementedError(f"{self.name} engine does not support file-based verification")

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
