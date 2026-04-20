"""Helpers for seller offer threads built from root offers and attached docs."""

from __future__ import annotations

from typing import Any

from db import DocumentRecord, TransactionDocument
from route_helpers import _utcnow
from db_writer import get_extraction
from offer_fields import build_offer_field_citations, build_offer_fields
from schemas import DocumentType

ROOT_OFFER_TYPES = {DocumentType.PURCHASE_OFFER.value}
ATTACHABLE_OFFER_DOC_TYPES = {
    DocumentType.COUNTEROFFER.value,
    DocumentType.ADDENDUM.value,
    DocumentType.AMENDMENT.value,
    DocumentType.INSPECTION_NOTICE.value,
    DocumentType.INSPECTION_RESPONSE.value,
}
EXTRACT_AND_MERGE_DOC_TYPES = {
    "escalation_addendum",
    "inspection_addendum",
    "sale_contingency_addendum",
    "appraisal_contingency_addendum",
}
ATTACHMENT_ONLY_DOC_TYPES = {
    "pre_approval_letter",
    "hoa_documents",
}


def _latest_extraction(doc_record: DocumentRecord):
    return doc_record.extractions[-1] if doc_record and doc_record.extractions else None


def _latest_extraction_ref(doc_record: DocumentRecord) -> str | None:
    latest = _latest_extraction(doc_record)
    if not latest:
        return None
    return f"{doc_record.id}:{len(doc_record.extractions) - 1}"


def _summary_from_extraction(doc_record: DocumentRecord) -> dict[str, Any]:
    latest = _latest_extraction(doc_record)
    buyer_name: str | None = None
    if latest:
        projection = (
            latest.normalized_offer_projection
            or latest.extracted_data
            or {}
        )
        fields, _extras = build_offer_fields(projection)
        overrides = latest.field_overrides or {}
        raw_buyer = overrides.get("buyer_name") if "buyer_name" in overrides else fields.get("buyer_name")
        if raw_buyer is not None:
            text = str(raw_buyer).strip()
            buyer_name = text or None
    return {
        "id": str(doc_record.id),
        "filename": doc_record.filename,
        "mode": latest.mode if latest else doc_record.mode,
        "overall_confidence": latest.overall_confidence if latest else 0.0,
        "pages_processed": latest.pages_processed if latest else doc_record.page_count,
        "created_at": latest.created_at.isoformat() if latest and latest.created_at else None,
        "document_type": latest.document_type if latest else None,
        "document_form_id": latest.document_form_id if latest else None,
        "document_title": latest.document_title if latest else None,
        "document_revision": latest.document_revision if latest else None,
        "support_level": latest.support_level if latest else None,
        "buyer_name": buyer_name,
    }


def _transaction_doc_summary(doc: TransactionDocument) -> dict[str, Any]:
    return {
        "_id": str(doc.id),
        "transaction_id": doc.transaction_id,
        "doc_type": doc.doc_type,
        "source": doc.source,
        "filename": doc.filename,
        "uploaded_by": doc.uploaded_by,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "offer_extraction_id": doc.offer_extraction_id,
        "document_record_id": doc.document_record_id,
        "attachment_role": doc.attachment_role,
        "attached_at": doc.attached_at.isoformat() if doc.attached_at else None,
    }


def is_root_offer_doc(doc_record: DocumentRecord) -> bool:
    latest = _latest_extraction(doc_record)
    return bool(latest and latest.document_type in ROOT_OFFER_TYPES)


def is_attachable_offer_doc(doc_record: DocumentRecord) -> bool:
    latest = _latest_extraction(doc_record)
    return bool(latest and latest.document_type in ATTACHABLE_OFFER_DOC_TYPES)


def is_metadata_only_doc(doc_record: DocumentRecord) -> bool:
    latest = _latest_extraction(doc_record)
    if not latest:
        return False
    return (latest.support_level or "").lower() == "metadata_only" or latest.document_type == DocumentType.UNKNOWN.value


def _field_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _load_offer_projection(ext_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    extracted_data = (
        ext_payload.get("normalized_offer_projection")
        or ext_payload.get("extracted_data")
        or ext_payload.get("result")
        or {}
    )
    fields, raw_extras = build_offer_fields(extracted_data)
    field_citations, field_citation_meta, _ = build_offer_field_citations(ext_payload.get("citations") or [], {})
    overrides = ext_payload.get("field_overrides") or {}
    return {
        "fields": fields,
        "raw_extras": raw_extras,
        "field_citations": field_citations,
        "field_citation_meta": field_citation_meta,
        "overrides": overrides,
    }, extracted_data


async def build_offer_thread(
    transaction_id: str,
    *,
    root_doc: DocumentRecord,
    attached_links: list[TransactionDocument],
) -> dict[str, Any]:
    root_ref = _latest_extraction_ref(root_doc)
    if not root_ref:
        raise RuntimeError("Root offer has no extraction")

    root_payload = await get_extraction(root_ref)
    if not root_payload:
        raise RuntimeError("Root offer extraction not found")

    merged, _ = _load_offer_projection(root_payload)
    merged_fields = dict(merged["fields"])
    merged_raw_extras = dict(merged["raw_extras"])
    merged_field_citations = {key: list(value) for key, value in merged["field_citations"].items()}
    merged_field_citation_meta = {key: dict(value) for key, value in merged["field_citation_meta"].items()}
    root_overrides = dict(merged["overrides"])

    attached_summaries: list[dict[str, Any]] = []
    supporting_docs: list[dict[str, Any]] = []
    sorted_links = sorted(
        attached_links,
        key=lambda item: item.attached_at or item.uploaded_at or _utcnow(),
    )

    for link in sorted_links:
        if link.document_record_id:
            child_doc = await DocumentRecord.get(link.document_record_id)
            if not child_doc:
                continue
            child_summary = _summary_from_extraction(child_doc)
            child_summary["attached_at"] = (
                link.attached_at.isoformat() if link.attached_at else None
            )
            attached_summaries.append(child_summary)

            child_ref = _latest_extraction_ref(child_doc)
            if not child_ref:
                continue
            child_payload = await get_extraction(child_ref)
            if not child_payload:
                continue
            child_projection, _ = _load_offer_projection(child_payload)
            for key, value in child_projection["fields"].items():
                if _field_missing(value):
                    continue
                merged_fields[key] = value
                if key in child_projection["field_citations"]:
                    merged_field_citations[key] = list(child_projection["field_citations"][key])
                merged_field_citation_meta[key] = dict(
                    child_projection["field_citation_meta"].get(
                        key,
                        {"state": "not_captured", "stale": False},
                    )
                )
            for raw_key, raw_value in child_projection["raw_extras"].items():
                if raw_value is not None:
                    merged_raw_extras[raw_key] = raw_value
        else:
            supporting_docs.append(_transaction_doc_summary(link))

    overridden_fields = sorted(key for key in root_overrides.keys() if key in merged_fields)
    for key in overridden_fields:
        merged_fields[key] = root_overrides[key]
        merged_field_citation_meta.setdefault(key, {"state": "not_captured", "stale": False})
        merged_field_citation_meta[key]["stale"] = True

    return {
        "extraction_id": root_ref,
        "document_id": str(root_doc.id),
        "summary": _summary_from_extraction(root_doc),
        "fields": merged_fields,
        "raw_extras": merged_raw_extras,
        "field_citations": merged_field_citations,
        "field_citation_meta": merged_field_citation_meta,
        "overridden_fields": overridden_fields,
        "attached_extractions": attached_summaries,
        "supporting_documents": supporting_docs,
    }


async def build_offer_workspace(transaction_id: str, extraction_ids: list[str]) -> dict[str, Any]:
    docs: list[DocumentRecord] = []
    for extraction_ref in extraction_ids:
        doc_id = extraction_ref.split(":")[0] if ":" in extraction_ref else extraction_ref
        try:
            doc_record = await DocumentRecord.get(doc_id)
        except Exception:
            doc_record = None
        if doc_record:
            docs.append(doc_record)

    docs_by_id = {str(doc.id): doc for doc in docs}
    attached_links = await TransactionDocument.find(
        {
            "transaction_id": transaction_id,
            "offer_extraction_id": {"$ne": None},
        }
    ).to_list()

    child_doc_ids = {
        link.document_record_id
        for link in attached_links
        if link.document_record_id
    }
    root_docs = [
        doc for doc in docs
        if is_root_offer_doc(doc) and str(doc.id) not in child_doc_ids
    ]
    offers = []
    for root_doc in root_docs:
        root_ref = _latest_extraction_ref(root_doc)
        if not root_ref:
            continue
        root_links = [link for link in attached_links if link.offer_extraction_id == root_ref]
        offers.append(await build_offer_thread(transaction_id, root_doc=root_doc, attached_links=root_links))

    offer_doc_ids = {offer["document_id"] for offer in offers}
    loose_extractions = [
        _summary_from_extraction(doc)
        for doc in docs
        if str(doc.id) not in offer_doc_ids and str(doc.id) not in child_doc_ids
    ]

    loose_documents = [
        _transaction_doc_summary(doc)
        for doc in await TransactionDocument.find(
            {
                "transaction_id": transaction_id,
                "offer_extraction_id": None,
                "document_record_id": None,
            }
        ).sort("-uploaded_at").to_list()
    ]

    root_offer_ids = [offer["extraction_id"] for offer in offers]
    attachment_candidates = [
        {"extraction_id": offer["extraction_id"], "label": offer["summary"]["document_title"] or offer["summary"]["filename"]}
        for offer in offers
    ]

    return {
        "offers": offers,
        "loose_extractions": loose_extractions,
        "loose_documents": loose_documents,
        "root_offer_ids": root_offer_ids,
        "attachment_candidates": attachment_candidates,
        "docs_by_id": docs_by_id,
    }
