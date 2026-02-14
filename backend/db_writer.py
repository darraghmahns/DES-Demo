"""Async persistence helpers for saving extraction results to MongoDB."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from beanie import PydanticObjectId

from db import DocumentRecord, ExtractionRecord
from schemas import ExtractionResult

log = logging.getLogger(__name__)


async def save_document(
    filename: str,
    mode: str,
    page_count: int,
    file_size_bytes: int,
    source: str = "upload",
    source_id: Optional[str] = None,
    file_hash: Optional[str] = None,
    file_path: Optional[str] = None,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
) -> PydanticObjectId:
    """Insert a document record and return its ID."""
    doc = DocumentRecord(
        filename=filename,
        file_path=file_path,
        source=source,
        source_id=source_id,
        mode=mode,
        page_count=page_count,
        file_size_bytes=file_size_bytes,
        file_hash=file_hash,
        user_id=user_id,
        org_id=org_id,
    )
    await doc.insert()
    return doc.id


async def save_extraction(
    document_id: PydanticObjectId,
    result: ExtractionResult,
    engine: str = "openai",
    duration_ms: Optional[int] = None,
) -> str:
    """Persist a full ExtractionResult as an embedded subdocument.

    Returns the extraction index (as string) within the document.
    """
    doc = await DocumentRecord.get(document_id)
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    # Build extracted_data from whichever mode populated data
    if result.dotloop_data:
        extracted_data = result.dotloop_data
    elif result.foia_data:
        extracted_data = result.foia_data
    else:
        extracted_data = None

    extraction = ExtractionRecord(
        engine=engine,
        model_used=result.model_used,
        mode=result.mode,
        extracted_data=extracted_data,
        dotloop_api_payload=result.dotloop_api_payload,
        docusign_api_payload=result.docusign_api_payload,
        validation_success=extracted_data is not None,
        overall_confidence=result.overall_confidence,
        pages_processed=result.pages_processed,
        extraction_timestamp=datetime.fromisoformat(result.extraction_timestamp),
        duration_ms=duration_ms,
        # API usage tracking
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        cost_usd=result.cost_usd,
        # Citations, PII, Compliance, and Property Enrichment embed directly
        citations=result.citations,
        pii_report=result.pii_report,
        compliance_report=result.compliance_report,
        property_enrichment=(
            result.property_enrichment.model_dump(mode="json")
            if result.property_enrichment else None
        ),
    )

    doc.extractions.append(extraction)
    await doc.save()

    idx = len(doc.extractions) - 1
    return f"{doc.id}:{idx}"


async def get_extraction(extraction_ref: str) -> dict | None:
    """Load an extraction by reference ('doc_id:index' or just 'doc_id').

    Returns a flat dict matching the shape the Dotloop connector expects.
    """
    parts = str(extraction_ref).split(":")
    doc_id = parts[0]
    idx = int(parts[1]) if len(parts) > 1 else 0

    doc = await DocumentRecord.get(doc_id)
    if not doc or idx >= len(doc.extractions):
        return None

    ext = doc.extractions[idx]
    data = ext.model_dump()
    data["id"] = extraction_ref
    data["document_id"] = str(doc.id)
    data["filename"] = doc.filename
    data["file_path"] = doc.file_path

    # Flatten timestamps to ISO strings for JSON serialization
    if isinstance(data.get("extraction_timestamp"), datetime):
        data["extraction_timestamp"] = data["extraction_timestamp"].isoformat()
    if isinstance(data.get("created_at"), datetime):
        data["created_at"] = data["created_at"].isoformat()

    return data


async def list_extractions(
    mode: str | None = None,
    limit: int = 50,
    user_id: str | None = None,
    org_id: str | None = None,
) -> list[dict]:
    """List recent extractions with basic metadata.

    Scoping rules:
    - org_id set → show all documents for that brokerage
    - user_id set (no org) → show user's own + legacy (user_id=None)
    - neither → show all (admin / dev mode)
    """
    filters: dict = {}
    if mode:
        filters["mode"] = mode

    if org_id:
        filters["org_id"] = org_id
    elif user_id:
        filters["$or"] = [
            {"user_id": user_id},
            {"user_id": None},
        ]

    query = DocumentRecord.find(filters)
    docs = await query.sort(-DocumentRecord.uploaded_at).limit(limit).to_list()

    results = []
    for doc in docs:
        for idx, ext in enumerate(doc.extractions):
            results.append({
                "id": f"{doc.id}:{idx}",
                "document_id": str(doc.id),
                "filename": doc.filename,
                "source": doc.source,
                "source_id": doc.source_id,
                "mode": ext.mode,
                "engine": ext.engine,
                "overall_confidence": ext.overall_confidence,
                "pages_processed": ext.pages_processed,
                "created_at": ext.created_at.isoformat() if ext.created_at else None,
            })
    return results[:limit]
