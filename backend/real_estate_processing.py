"""Shared classification and extraction helpers for real-estate documents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from extractor import EMPTY_USAGE
from offer_fields import (
    get_missing_offer_field_targets,
    get_offer_field_targets,
    merge_recovered_offer_fields,
)
from ocr_engine import OCREngine
from pdf_converter import get_pdf_info
from real_estate_classifier import (
    RealEstateClassification,
    build_classification_fallback_payload,
    build_text_samples,
    classify_from_samples,
    classify_with_model_fallback,
    extract_pdf_text_samples,
)
from schemas import (
    DocumentSupportLevel,
    DocumentType,
    DotloopContractDates,
    DotloopFinancials,
    DotloopLoopDetails,
    DotloopParticipant,
    DotloopPropertyAddress,
    ExtractionResult,
    RealEstateDocumentSummary,
)
from verifier import compute_overall_confidence


_OFFER_LIKE_TYPES = {
    DocumentType.PURCHASE_OFFER.value,
    DocumentType.COUNTEROFFER.value,
    DocumentType.INSPECTION_NOTICE.value,
    DocumentType.INSPECTION_RESPONSE.value,
    DocumentType.ADDENDUM.value,
    DocumentType.AMENDMENT.value,
}


@dataclass
class RealEstateProcessingOutcome:
    result: ExtractionResult
    validated_data: dict[str, Any] | None
    classification: RealEstateClassification
    validation_errors: list[str]
    citations: list[Any]
    usage: dict[str, int]
    route: str


def _combine_usage(*usages: dict[str, Any] | None) -> dict[str, int]:
    combined = dict(EMPTY_USAGE)
    for usage in usages:
        if not usage:
            continue
        for key in combined:
            combined[key] += int(usage.get(key, 0) or 0)
    return combined


def _estimate_cost(usage: dict[str, int]) -> float:
    return round(
        usage["prompt_tokens"] * 2.50 / 1_000_000
        + usage["completion_tokens"] * 10.00 / 1_000_000,
        6,
    )


def _sample_page_numbers(page_count: int) -> list[int]:
    numbers = [1]
    if page_count >= 2:
        numbers.append(2)
    if page_count > 2:
        numbers.append(page_count)
    seen: list[int] = []
    for number in numbers:
        if number not in seen:
            seen.append(number)
    return seen


def classify_real_estate_document(
    *,
    engine: OCREngine,
    pdf_path: str,
    filename: str,
    images_b64: list[str] | None = None,
) -> tuple[RealEstateClassification, dict[str, int]]:
    file_info = get_pdf_info(pdf_path)
    page_numbers = _sample_page_numbers(file_info["pages"])
    digital_samples = extract_pdf_text_samples(pdf_path, page_numbers)
    classification = classify_from_samples(filename=filename, samples=digital_samples)
    total_usage = dict(EMPTY_USAGE)

    if classification.is_unknown:
        if engine.prefers_file_path:
            page_texts, ocr_usage = engine.ocr_raw_text_from_file(pdf_path)
            total_usage = _combine_usage(total_usage, ocr_usage)
            sampled_texts = [page_texts[number - 1] for number in page_numbers if number - 1 < len(page_texts)]
            sampled_pages = [number for number in page_numbers if number - 1 < len(page_texts)]
            ocr_samples = build_text_samples(sampled_texts, page_numbers=sampled_pages)
        elif images_b64:
            sampled_images = [images_b64[number - 1] for number in page_numbers if number - 1 < len(images_b64)]
            page_texts, ocr_usage = engine.ocr_raw_text(sampled_images)
            total_usage = _combine_usage(total_usage, ocr_usage)
            sampled_pages = page_numbers[: len(page_texts)]
            ocr_samples = build_text_samples(page_texts, page_numbers=sampled_pages)
        else:
            ocr_samples = []
        if ocr_samples:
            classification = classify_from_samples(filename=filename, samples=ocr_samples)

    if classification.is_unknown:
        metadata = build_classification_fallback_payload(filename, classification)
        model_result, classify_usage = engine.classify_real_estate_metadata(metadata)
        total_usage = _combine_usage(total_usage, classify_usage)
        classification = classify_with_model_fallback(classification, model_result)

    return classification, total_usage


def build_lenient_offer_model(raw_extraction: dict[str, Any]) -> DotloopLoopDetails | None:
    try:
        nested = dict(raw_extraction)
        if isinstance(nested.get("property_address"), dict):
            nested["property_address"] = DotloopPropertyAddress.model_construct(**nested["property_address"])
        if isinstance(nested.get("financials"), dict):
            nested["financials"] = DotloopFinancials.model_construct(**nested["financials"])
        if isinstance(nested.get("contract_dates"), dict):
            nested["contract_dates"] = DotloopContractDates.model_construct(**nested["contract_dates"])
        if isinstance(nested.get("participants"), list):
            nested["participants"] = [
                DotloopParticipant.model_construct(**item) if isinstance(item, dict) else item
                for item in nested["participants"]
            ]
        return DotloopLoopDetails.model_construct(**nested)
    except Exception:
        return None


def get_processing_route(classification: RealEstateClassification) -> str:
    if (
        classification.support_level in (
            DocumentSupportLevel.FULL.value,
            DocumentSupportLevel.PARTIAL.value,
        )
        and classification.document_type in _OFFER_LIKE_TYPES
    ):
        return "offer_projection"
    return "summary"


def process_real_estate_document(
    *,
    engine: OCREngine,
    pdf_path: str,
    filename: str,
    images_b64: list[str] | None = None,
    classification: RealEstateClassification | None = None,
    classification_usage: dict[str, int] | None = None,
) -> RealEstateProcessingOutcome:
    usage = _combine_usage(classification_usage)
    file_info = get_pdf_info(pdf_path)

    if classification is None:
        classification, discovered_usage = classify_real_estate_document(
            engine=engine,
            pdf_path=pdf_path,
            filename=filename,
            images_b64=images_b64,
        )
        usage = _combine_usage(usage, discovered_usage)

    route = get_processing_route(classification)
    validation_errors: list[str] = []
    citations: list[Any] = []
    validated_data: dict[str, Any] | None = None
    dotloop_api_payload = None
    docusign_api_payload = None
    overall_confidence = 0.0

    if route == "offer_projection":
        if engine.prefers_file_path:
            raw_extraction, extract_usage = engine.extract_from_file(pdf_path, "real_estate")
        else:
            if images_b64 is None:
                raise ValueError("images_b64 required for image-based engine")
            raw_extraction, extract_usage = engine.extract(images_b64, "real_estate")
        usage = _combine_usage(usage, extract_usage)

        validated = None
        try:
            validated = DotloopLoopDetails.model_validate(raw_extraction)
            validated_data = validated.model_dump(mode="json")
        except ValidationError as exc:
            validation_errors = [
                f"{' -> '.join(str(item) for item in err['loc'])}: {err['msg']}"
                for err in exc.errors()
            ]
            lenient = build_lenient_offer_model(raw_extraction)
            validated_data = lenient.model_dump(mode="json") if lenient else dict(raw_extraction)
            validated = lenient

        recovery_targets = get_missing_offer_field_targets(validated_data or {})
        if recovery_targets:
            if engine.prefers_file_path:
                recovered_values, recovery_usage = engine.recover_missing_fields_from_file(
                    pdf_path,
                    validated_data or {},
                    recovery_targets,
                )
            else:
                recovered_values, recovery_usage = engine.recover_missing_fields(
                    images_b64 or [],
                    validated_data or {},
                    recovery_targets,
                )
            usage = _combine_usage(usage, recovery_usage)
            validated_data, _ = merge_recovered_offer_fields(validated_data or {}, recovered_values)

        required_targets = get_offer_field_targets(validated_data or {})
        if engine.prefers_file_path:
            citations, verify_usage = engine.verify_from_file(pdf_path, validated_data or {}, required_targets)
        else:
            citations, verify_usage = engine.verify(images_b64 or [], validated_data or {}, required_targets)
        usage = _combine_usage(usage, verify_usage)
        overall_confidence = compute_overall_confidence(citations)

        api_model = None
        try:
            api_model = DotloopLoopDetails.model_validate(validated_data or {})
        except ValidationError:
            api_model = validated
        if api_model:
            try:
                dotloop_api_payload = api_model.to_dotloop_api_format()
            except Exception:
                dotloop_api_payload = None
            try:
                docusign_api_payload = api_model.to_docusign_api_format()
            except Exception:
                docusign_api_payload = None
    else:
        if engine.prefers_file_path:
            summary, summary_usage = engine.summarize_real_estate_document_from_file(
                pdf_path,
                classification.model_dump(mode="json"),
            )
        else:
            summary, summary_usage = engine.summarize_real_estate_document(
                images_b64 or [],
                classification.model_dump(mode="json"),
            )
        usage = _combine_usage(usage, summary_usage)
        validated = RealEstateDocumentSummary.model_validate(summary)
        validated_data = validated.model_dump(mode="json")

    result = ExtractionResult(
        mode="real_estate",
        source_file=filename,
        extraction_timestamp=datetime.now(timezone.utc).isoformat(),
        pages_processed=file_info["pages"],
        dotloop_data=validated_data,
        dotloop_api_payload=dotloop_api_payload,
        docusign_api_payload=docusign_api_payload,
        citations=citations,
        overall_confidence=overall_confidence,
        document_type=classification.document_type,
        document_form_id=classification.document_form_id,
        document_title=classification.document_title,
        document_subtitle=classification.document_subtitle,
        document_revision=classification.document_revision,
        document_publisher=classification.document_publisher,
        document_footer_text=classification.document_footer_text,
        classification_source=classification.classification_source,
        classification_confidence=classification.classification_confidence,
        classification_evidence=classification.classification_evidence,
        support_level=classification.support_level,
        normalized_offer_projection=validated_data if route == "offer_projection" else None,
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
        cost_usd=_estimate_cost(usage),
    )
    return RealEstateProcessingOutcome(
        result=result,
        validated_data=validated_data,
        classification=classification,
        validation_errors=validation_errors,
        citations=citations,
        usage=usage,
        route=route,
    )
