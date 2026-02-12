"""OpenAI GPT-4o Vision engine — wraps existing extractor.py + verifier.py logic."""

from __future__ import annotations

from openai import OpenAI

from ocr_engine import OCREngine
from extractor import extract_from_images, extract_raw_text
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
        self, images_b64: list[str], extracted_data: dict
    ) -> tuple[list[VerificationCitation], dict]:
        return verify_extraction(images_b64, extracted_data, self._client)

    def ocr_raw_text(self, images_b64: list[str]) -> tuple[list[str], dict]:
        return extract_raw_text(images_b64, self._client)
