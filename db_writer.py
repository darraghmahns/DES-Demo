"""Persistence helpers for saving extraction results to Postgres."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from db import (
    SessionLocal,
    Citation,
    Document,
    Extraction,
    PIIFindingRow,
    PIIReportRow,
)
from schemas import ExtractionResult


def save_document(
    filename: str,
    mode: str,
    page_count: int,
    file_size_bytes: int,
    source: str = "upload",
    source_id: Optional[str] = None,
) -> uuid.UUID:
    """Insert a document record and return its ID."""
    with SessionLocal() as session:
        doc = Document(
            filename=filename,
            source=source,
            source_id=source_id,
            mode=mode,
            page_count=page_count,
            file_size_bytes=file_size_bytes,
        )
        session.add(doc)
        session.commit()
        return doc.id


def save_extraction(
    document_id: uuid.UUID,
    result: ExtractionResult,
    engine: str = "openai",
    duration_ms: Optional[int] = None,
) -> uuid.UUID:
    """Persist a full ExtractionResult to the database.

    Writes to extractions, citations, pii_findings, and pii_reports tables.
    """
    with SessionLocal() as session:
        # Build extracted_data JSON from whichever mode populated data
        # dotloop_data / foia_data are already plain dicts (or None)
        if result.dotloop_data:
            extracted_data = result.dotloop_data
        elif result.foia_data:
            extracted_data = result.foia_data
        else:
            extracted_data = None

        extraction = Extraction(
            document_id=document_id,
            engine=engine,
            model_used=result.model_used,
            mode=result.mode,
            extracted_data=extracted_data,
            dotloop_api_payload=result.dotloop_api_payload,
            validation_success=extracted_data is not None,
            validation_errors=None,
            overall_confidence=result.overall_confidence,
            pages_processed=result.pages_processed,
            extraction_timestamp=datetime.fromisoformat(result.extraction_timestamp),
            duration_ms=duration_ms,
        )
        session.add(extraction)
        session.flush()  # get extraction.id before adding children

        # Citations
        for c in result.citations:
            session.add(Citation(
                extraction_id=extraction.id,
                field_name=c.field_name,
                extracted_value=c.extracted_value,
                page_number=c.page_number,
                line_or_region=c.line_or_region,
                surrounding_text=c.surrounding_text,
                confidence=c.confidence,
            ))

        # PII findings + report
        if result.pii_report:
            for f in result.pii_report.findings:
                session.add(PIIFindingRow(
                    extraction_id=extraction.id,
                    pii_type=f.pii_type.value,
                    value_redacted=f.value_redacted,
                    severity=f.severity.value,
                    confidence=f.confidence,
                    location=f.location,
                    recommendation=f.recommendation,
                ))

            session.add(PIIReportRow(
                extraction_id=extraction.id,
                risk_score=result.pii_report.pii_risk_score,
                risk_level=result.pii_report.risk_level.value,
                finding_count=len(result.pii_report.findings),
            ))

        session.commit()
        return extraction.id


def get_extraction(extraction_id: uuid.UUID) -> dict | None:
    """Load an extraction and its related data from the database."""
    with SessionLocal() as session:
        ext = session.get(Extraction, extraction_id)
        if not ext:
            return None

        return {
            "id": str(ext.id),
            "document_id": str(ext.document_id),
            "engine": ext.engine,
            "model_used": ext.model_used,
            "mode": ext.mode,
            "extracted_data": ext.extracted_data,
            "dotloop_api_payload": ext.dotloop_api_payload,
            "validation_success": ext.validation_success,
            "overall_confidence": ext.overall_confidence,
            "pages_processed": ext.pages_processed,
            "extraction_timestamp": ext.extraction_timestamp.isoformat() if ext.extraction_timestamp else None,
            "duration_ms": ext.duration_ms,
            "citations": [
                {
                    "field_name": c.field_name,
                    "extracted_value": c.extracted_value,
                    "page_number": c.page_number,
                    "line_or_region": c.line_or_region,
                    "surrounding_text": c.surrounding_text,
                    "confidence": c.confidence,
                }
                for c in ext.citations
            ],
            "pii_report": {
                "risk_score": ext.pii_report.risk_score,
                "risk_level": ext.pii_report.risk_level,
                "finding_count": ext.pii_report.finding_count,
                "findings": [
                    {
                        "pii_type": f.pii_type,
                        "value_redacted": f.value_redacted,
                        "severity": f.severity,
                        "confidence": f.confidence,
                        "location": f.location,
                        "recommendation": f.recommendation,
                    }
                    for f in ext.pii_findings
                ],
            } if ext.pii_report else None,
        }


def list_extractions(mode: str | None = None, limit: int = 50) -> list[dict]:
    """List recent extractions with basic metadata."""
    with SessionLocal() as session:
        query = session.query(Extraction).order_by(Extraction.created_at.desc())
        if mode:
            query = query.filter(Extraction.mode == mode)
        query = query.limit(limit)

        return [
            {
                "id": str(ext.id),
                "document_id": str(ext.document_id),
                "mode": ext.mode,
                "engine": ext.engine,
                "overall_confidence": ext.overall_confidence,
                "pages_processed": ext.pages_processed,
                "created_at": ext.created_at.isoformat() if ext.created_at else None,
            }
            for ext in query.all()
        ]
