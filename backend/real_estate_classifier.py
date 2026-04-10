"""Deterministic-first classification for Montana real-estate forms."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field

from schemas import ClassificationSource, DocumentSupportLevel, DocumentType


_PUBLISHER_RE = re.compile(r"montana association of realtors", re.IGNORECASE)
_PAGE_RE = re.compile(r"page\s+\d+\s+of\s+\d+", re.IGNORECASE)
_REVISION_RE = re.compile(
    r"^(?P<title>.+?),\s+(?P<revision>(January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})$",
    re.IGNORECASE,
)
_NOISE_RES = [
    re.compile(r"^dotloop signature verification", re.IGNORECASE),
    re.compile(r"^dtlp\.us/", re.IGNORECASE),
    re.compile(r"^dotloop verified$", re.IGNORECASE),
    re.compile(r"^produced with zipform", re.IGNORECASE),
    re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}(\s+\d{1,2}:\d{2})?.*$", re.IGNORECASE),
    re.compile(r"^[A-Z]{1,3}$"),
]


class ClassificationEvidencePayload(BaseModel):
    kind: str
    text: str
    page_number: int | None = None


class PageTextSample(BaseModel):
    page_number: int
    raw_text: str = ""
    normalized_lines: list[str] = Field(default_factory=list)


class RealEstateClassification(BaseModel):
    document_form_id: str
    document_type: str
    document_title: str | None = None
    document_subtitle: str | None = None
    document_revision: str | None = None
    document_publisher: str | None = None
    document_footer_text: str | None = None
    classification_source: str = ClassificationSource.UNKNOWN.value
    classification_confidence: float = 0.0
    classification_evidence: list[dict] = Field(default_factory=list)
    support_level: str = DocumentSupportLevel.METADATA_ONLY.value
    header_text: str | None = None
    first_page_excerpt: str | None = None

    @property
    def is_unknown(self) -> bool:
        return self.document_form_id == "UNKNOWN"


@dataclass(frozen=True)
class FormDefinition:
    form_id: str
    document_type: str
    support_level: str
    aliases: tuple[str, ...]


_FORM_DEFINITIONS: tuple[FormDefinition, ...] = (
    FormDefinition(
        form_id="MAR_BUY_SELL_RESIDENTIAL",
        document_type=DocumentType.PURCHASE_OFFER.value,
        support_level=DocumentSupportLevel.FULL.value,
        aliases=("BUY SELL AGREEMENT RESIDENTIAL",),
    ),
    FormDefinition(
        form_id="MAR_BUY_SELL_LAND",
        document_type=DocumentType.PURCHASE_OFFER.value,
        support_level=DocumentSupportLevel.FULL.value,
        aliases=("BUY SELL AGREEMENT LAND",),
    ),
    FormDefinition(
        form_id="MAR_BUY_SELL_COMMERCIAL",
        document_type=DocumentType.PURCHASE_OFFER.value,
        support_level=DocumentSupportLevel.PARTIAL.value,
        aliases=("BUY SELL AGREEMENT COMMERCIAL",),
    ),
    FormDefinition(
        form_id="MAR_COUNTER_OFFER",
        document_type=DocumentType.COUNTEROFFER.value,
        support_level=DocumentSupportLevel.FULL.value,
        aliases=("COUNTER OFFER",),
    ),
    FormDefinition(
        form_id="MAR_MULTIPLE_COUNTER_OFFER",
        document_type=DocumentType.COUNTEROFFER.value,
        support_level=DocumentSupportLevel.PARTIAL.value,
        aliases=("MULTIPLE COUNTER OFFER",),
    ),
    FormDefinition(
        form_id="MAR_ESCALATION_ADDENDUM",
        document_type=DocumentType.ADDENDUM.value,
        support_level=DocumentSupportLevel.PARTIAL.value,
        aliases=("ESCALATION ADDENDUM",),
    ),
    FormDefinition(
        form_id="MAR_INSPECTION_NOTICE_RESULTS_REMEDIES",
        document_type=DocumentType.INSPECTION_NOTICE.value,
        support_level=DocumentSupportLevel.PARTIAL.value,
        aliases=("INSPECTION NOTICE RESULTS REMEDIES",),
    ),
    FormDefinition(
        form_id="MAR_INSPECTION_NOTICE_SELLERS_RESPONSE",
        document_type=DocumentType.INSPECTION_RESPONSE.value,
        support_level=DocumentSupportLevel.PARTIAL.value,
        aliases=("INSPECTION NOTICE SELLERS RESPONSE", "INSPECTION NOTICE SELLER S RESPONSE"),
    ),
    FormDefinition(
        form_id="MAR_AMENDMENT_EXISTING_TERMS",
        document_type=DocumentType.AMENDMENT.value,
        support_level=DocumentSupportLevel.PARTIAL.value,
        aliases=("AMENDMENT TO AGREEMENT BETWEEN PARTIES FOR EXISTING TERMS AND CONDITIONS",),
    ),
    FormDefinition(
        form_id="MAR_PROPERTY_DISCLOSURE_STATEMENT",
        document_type=DocumentType.DISCLOSURE.value,
        support_level=DocumentSupportLevel.METADATA_ONLY.value,
        aliases=("PROPERTY DISCLOSURE STATEMENT",),
    ),
    FormDefinition(
        form_id="MAR_BUYER_BROKER_AGREEMENT_SHORT",
        document_type=DocumentType.BROKERAGE_FORM.value,
        support_level=DocumentSupportLevel.METADATA_ONLY.value,
        aliases=("BUYER BROKER AGREEMENT SHORT",),
    ),
    FormDefinition(
        form_id="MAR_BUYER_BROKER_AGREEMENT",
        document_type=DocumentType.BROKERAGE_FORM.value,
        support_level=DocumentSupportLevel.METADATA_ONLY.value,
        aliases=("BUYER BROKER AGREEMENT",),
    ),
    FormDefinition(
        form_id="MAR_COOPERATING_BROKER_COMPENSATION_AGREEMENT",
        document_type=DocumentType.COMPENSATION_AGREEMENT.value,
        support_level=DocumentSupportLevel.METADATA_ONLY.value,
        aliases=("COOPERATING BROKER COMPENSATION AGREEMENT",),
    ),
    FormDefinition(
        form_id="MAR_RELATIONSHIPS_CONSENT_IN_REAL_ESTATE",
        document_type=DocumentType.AGENCY_FORM.value,
        support_level=DocumentSupportLevel.METADATA_ONLY.value,
        aliases=("RELATIONSHIPS CONSENT IN REAL ESTATE", "RELATIONSHIPS CONSENTS IN REAL ESTATE"),
    ),
    FormDefinition(
        form_id="MAR_OPTION_TO_PURCHASE",
        document_type=DocumentType.OPTION_FORM.value,
        support_level=DocumentSupportLevel.METADATA_ONLY.value,
        aliases=("OPTION TO PURCHASE",),
    ),
    FormDefinition(
        form_id="MAR_NOTICE_TO_EXERCISE_OPTION",
        document_type=DocumentType.NOTICE_FORM.value,
        support_level=DocumentSupportLevel.METADATA_ONLY.value,
        aliases=("NOTICE TO EXERCISE OPTION",),
    ),
)

FORM_DEFINITIONS = _FORM_DEFINITIONS


def _normalize_line(text: str) -> str:
    normalized = text.replace("®", " ").replace("©", " ")
    normalized = normalized.replace("–", "-").replace("—", "-")
    normalized = normalized.replace("(", " ").replace(")", " ")
    normalized = normalized.replace("/", " ")
    normalized = normalized.replace("'", " ")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r"[^A-Z0-9, ]+", " ", normalized.upper())
    normalized = re.sub(r"\s+", " ", normalized).strip(" ,")
    return normalized


def _line_is_noise(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    for pattern in _NOISE_RES:
        if pattern.match(stripped):
            return True
    return False


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _normalize_lines(lines: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for line in lines:
        if _line_is_noise(line):
            continue
        normalized.append(line.strip())
    return normalized


def extract_pdf_text_samples(pdf_path: str, page_numbers: list[int]) -> list[PageTextSample]:
    samples: list[PageTextSample] = []
    pdf = Path(pdf_path)
    if not pdf.exists():
        return samples

    for page_number in page_numbers:
        if page_number < 1:
            continue
        try:
            proc = subprocess.run(
                ["pdftotext", "-layout", "-f", str(page_number), "-l", str(page_number), str(pdf), "-"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError:
            return samples
        raw_text = proc.stdout or ""
        samples.append(
            PageTextSample(
                page_number=page_number,
                raw_text=raw_text,
                normalized_lines=_normalize_lines(_split_lines(raw_text)),
            )
        )
    return samples


def build_text_samples(page_texts: list[str], *, page_numbers: list[int] | None = None) -> list[PageTextSample]:
    numbers = page_numbers or list(range(1, len(page_texts) + 1))
    samples: list[PageTextSample] = []
    for idx, raw_text in enumerate(page_texts):
        page_number = numbers[idx] if idx < len(numbers) else idx + 1
        samples.append(
            PageTextSample(
                page_number=page_number,
                raw_text=raw_text or "",
                normalized_lines=_normalize_lines(_split_lines(raw_text or "")),
            )
        )
    return samples


def _extract_footer_candidate(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    if not lines:
        return None, None, None
    window = lines[-30:]
    publisher = None
    title_line = None
    revision = None

    for idx, line in enumerate(window):
        if _PUBLISHER_RE.search(line):
            publisher = line.strip()
            trailing = window[idx + 1 : idx + 6]
            for candidate in trailing:
                match = _REVISION_RE.match(candidate.strip())
                if match:
                    title_line = match.group("title").strip()
                    revision = match.group("revision").strip()
                    break
                if title_line is None and _PAGE_RE.search(candidate) is None:
                    # Handle forms where revision line parsing fails but a plain title is still present.
                    title_line = candidate.strip()
            break
    return title_line, revision, publisher


def _extract_header_block(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    if not lines:
        return None, None, None
    top = lines[:12]
    header_lines: list[str] = []
    subtitle = None
    excerpt_lines: list[str] = []
    started = False

    for line in top:
        if len(excerpt_lines) < 6:
            excerpt_lines.append(line)
        normalized = _normalize_line(line)
        if not normalized:
            continue
        if not started:
            if any(token in normalized for token in ("AGREEMENT", "ADDENDUM", "NOTICE", "DISCLOSURE", "OFFER", "CONSENT", "OPTION", "COMPENSATION")):
                started = True
                header_lines.append(line)
                continue
        elif len(header_lines) < 3:
            if (
                len(line.split()) > 6
                and "(" not in line
                and ")" not in line
                and not any(
                    token in normalized
                    for token in ("AGREEMENT", "ADDENDUM", "NOTICE", "DISCLOSURE", "OFFER", "CONSENT", "OPTION", "COMPENSATION")
                )
            ):
                break
            header_lines.append(line)
            continue
        break

    if not header_lines:
        return None, None, "\n".join(excerpt_lines) or None

    title = header_lines[0]
    if len(header_lines) > 1:
        subtitle = " ".join(header_lines[1:])
    return title.strip(), subtitle.strip() if subtitle else None, "\n".join(excerpt_lines) or None


def _match_alias(value: str | None) -> FormDefinition | None:
    if not value:
        return None
    normalized = _normalize_line(value)
    for definition in _FORM_DEFINITIONS:
        for alias in definition.aliases:
            if alias in normalized:
                return definition
    return None


def _build_classification(
    definition: FormDefinition,
    *,
    title: str | None,
    subtitle: str | None,
    revision: str | None,
    publisher: str | None,
    footer_text: str | None,
    source: ClassificationSource,
    confidence: float,
    evidence: list[ClassificationEvidencePayload],
    excerpt: str | None,
) -> RealEstateClassification:
    return RealEstateClassification(
        document_form_id=definition.form_id,
        document_type=definition.document_type,
        document_title=title,
        document_subtitle=subtitle,
        document_revision=revision,
        document_publisher=publisher,
        document_footer_text=footer_text,
        classification_source=source.value,
        classification_confidence=confidence,
        classification_evidence=[item.model_dump(mode="json") for item in evidence],
        support_level=definition.support_level,
        header_text=title,
        first_page_excerpt=excerpt,
    )


def classify_from_samples(
    *,
    filename: str,
    samples: list[PageTextSample],
) -> RealEstateClassification:
    page_one = samples[0] if samples else PageTextSample(page_number=1)
    header_title, header_subtitle, first_page_excerpt = _extract_header_block(page_one.normalized_lines)

    footer_votes: dict[str, tuple[int, str | None, str | None, str | None, int]] = {}
    for sample in samples:
        footer_title, revision, publisher = _extract_footer_candidate(sample.normalized_lines)
        if not footer_title:
            continue
        normalized_title = _normalize_line(footer_title)
        count, _, _, _, _ = footer_votes.get(normalized_title, (0, None, None, None, sample.page_number))
        footer_votes[normalized_title] = (
            count + 1,
            footer_title,
            revision,
            publisher,
            sample.page_number,
        )

    best_footer_title = None
    best_footer_revision = None
    best_footer_publisher = None
    if footer_votes:
        _, footer_title, revision, publisher, page_number = max(footer_votes.values(), key=lambda item: item[0])
        best_footer_title = footer_title
        best_footer_revision = revision
        best_footer_publisher = publisher
        definition = _match_alias(footer_title)
        if definition:
            evidence = [
                ClassificationEvidencePayload(kind="footer_title", text=footer_title or "", page_number=page_number),
            ]
            if publisher:
                evidence.append(ClassificationEvidencePayload(kind="publisher", text=publisher, page_number=page_number))
            return _build_classification(
                definition,
                title=footer_title,
                subtitle=header_subtitle,
                revision=revision,
                publisher=publisher,
                footer_text=footer_title,
                source=ClassificationSource.FOOTER_EXACT,
                confidence=1.0,
                evidence=evidence,
                excerpt=first_page_excerpt,
            )

    definition = _match_alias(header_title)
    if definition:
        evidence = [ClassificationEvidencePayload(kind="header_title", text=header_title or "", page_number=1)]
        return _build_classification(
            definition,
            title=header_title,
            subtitle=header_subtitle,
            revision=None,
            publisher=None,
            footer_text=None,
            source=ClassificationSource.HEADER_EXACT,
            confidence=0.97,
            evidence=evidence,
            excerpt=first_page_excerpt,
        )

    definition = _match_alias(filename)
    if definition:
        evidence = [ClassificationEvidencePayload(kind="filename", text=filename, page_number=None)]
        return _build_classification(
            definition,
            title=header_title or filename,
            subtitle=header_subtitle,
            revision=None,
            publisher=None,
            footer_text=None,
            source=ClassificationSource.FILENAME_ALIAS,
            confidence=0.8,
            evidence=evidence,
            excerpt=first_page_excerpt,
        )

    return RealEstateClassification(
        document_form_id="UNKNOWN",
        document_type=DocumentType.UNKNOWN.value,
        document_title=header_title or Path(filename).stem,
        document_subtitle=header_subtitle,
        document_revision=best_footer_revision,
        document_publisher=best_footer_publisher,
        document_footer_text=best_footer_title,
        classification_source=ClassificationSource.UNKNOWN.value,
        classification_confidence=0.0,
        classification_evidence=[],
        support_level=DocumentSupportLevel.METADATA_ONLY.value,
        header_text=header_title,
        first_page_excerpt=first_page_excerpt,
    )


def classify_with_model_fallback(
    deterministic: RealEstateClassification,
    model_result: dict | None,
) -> RealEstateClassification:
    if not deterministic.is_unknown:
        return deterministic
    if not model_result:
        return deterministic

    form_id = str(model_result.get("document_form_id") or "UNKNOWN").strip().upper()
    confidence = float(model_result.get("classification_confidence") or 0.0)
    if form_id == "UNKNOWN" or confidence < 0.75:
        return deterministic

    definition = next((item for item in _FORM_DEFINITIONS if item.form_id == form_id), None)
    if not definition:
        return deterministic

    evidence = [ClassificationEvidencePayload(kind="model_fallback", text=form_id, page_number=None)]
    return _build_classification(
        definition,
        title=str(model_result.get("document_title") or deterministic.document_title or form_id).strip(),
        subtitle=str(model_result.get("document_subtitle") or deterministic.document_subtitle or "").strip() or None,
        revision=str(model_result.get("document_revision") or "").strip() or None,
        publisher=str(model_result.get("document_publisher") or "").strip() or None,
        footer_text=str(model_result.get("document_footer_text") or "").strip() or None,
        source=ClassificationSource.MODEL_FALLBACK,
        confidence=confidence,
        evidence=evidence,
        excerpt=deterministic.first_page_excerpt,
    )


def build_classification_fallback_payload(
    filename: str,
    deterministic: RealEstateClassification,
) -> dict:
    return {
        "filename": filename,
        "header_title": deterministic.header_text,
        "header_subtitle": deterministic.document_subtitle,
        "document_footer_text": deterministic.document_footer_text,
        "document_revision": deterministic.document_revision,
        "document_publisher": deterministic.document_publisher,
        "first_page_excerpt": deterministic.first_page_excerpt,
        "candidate_form_ids": [definition.form_id for definition in _FORM_DEFINITIONS],
    }
