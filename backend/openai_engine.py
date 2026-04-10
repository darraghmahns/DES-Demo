"""OpenAI GPT-4o Vision engine — wraps existing extractor.py + verifier.py logic."""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from ocr_engine import OCREngine
from extractor import (
    classify_real_estate_metadata,
    extract_from_images,
    extract_raw_text,
    extract_real_estate_summary_from_images,
    recover_missing_fields_from_images,
)
from verifier import verify_extraction
from schemas import VerificationCitation


class OpenAIEngine(OCREngine):
    """Extraction engine backed by OpenAI GPT-4o Vision API."""

    def __init__(self) -> None:
        self._client = OpenAI()

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model_id(self) -> str:
        return "gpt-4o"

    def extract(self, images_b64: list[str], mode: str) -> tuple[dict, dict]:
        return extract_from_images(images_b64, mode, self._client)

    def verify(
        self,
        images_b64: list[str],
        extracted_data: dict,
        required_field_targets: list[dict[str, Any]] | None = None,
    ) -> tuple[list[VerificationCitation], dict]:
        return verify_extraction(images_b64, extracted_data, self._client, required_field_targets)

    def recover_missing_fields(
        self,
        images_b64: list[str],
        extracted_data: dict,
        field_targets: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict]:
        return recover_missing_fields_from_images(images_b64, extracted_data, field_targets, self._client)

    def ocr_raw_text(self, images_b64: list[str]) -> tuple[list[str], dict]:
        return extract_raw_text(images_b64, self._client)

    def classify_real_estate_metadata(self, metadata: dict[str, Any]) -> tuple[dict, dict]:
        return classify_real_estate_metadata(metadata, self._client)

    def summarize_real_estate_document(
        self,
        images_b64: list[str],
        classification: dict[str, Any],
    ) -> tuple[dict, dict]:
        return extract_real_estate_summary_from_images(images_b64, classification, self._client)
