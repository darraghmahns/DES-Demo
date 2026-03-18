"""Transaction management API routes for D.E.S.

Handles transaction CRUD, participant management, document linking,
auto-fill from profiles, Dotloop intake, and setup-progress tracking.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ValidationError

from auth import AUTH_ENABLED, get_current_user
from db import DocumentRecord, Transaction, TransactionDocument, UserDocument, UserProfile
from db_writer import save_document, save_extraction
from dotloop_client import DotloopAPIError
from dotloop_connector import (
    get_dotloop_client,
    get_loop_with_details,
    is_configured as dotloop_configured,
)
from ocr_engine import get_engine
from pdf_converter import get_pdf_info, image_to_base64, pdf_to_images
from schemas import (
    DEFAULT_PURCHASE_REQUIREMENTS,
    DocumentRequirement,
    DotloopLoopDetails,
    DotloopPropertyAddress,
    DotloopSyncStatus,
    ExtractionResult,
    ParticipantRole,
    ParticipantStatus,
    TransactionParticipant,
    TransactionStatus,
)
from verifier import compute_overall_confidence

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class CreateTransactionRequest(BaseModel):
    name: str
    transaction_type: str = "purchase"
    property_address: Optional[dict] = None
    mls_number: Optional[str] = None
    purchase_price: Optional[float] = None
    earnest_money: Optional[float] = None
    closing_date: Optional[str] = None
    agent_role: Optional[str] = None  # "listing_agent" | "buying_agent"


class CreateTransactionFromDotloopRequest(BaseModel):
    name_override: Optional[str] = None
    agent_role: Optional[str] = None  # "listing_agent" | "buying_agent"


class SetDotloopLoopBody(BaseModel):
    loop_id: str


class UpdateTransactionRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[TransactionStatus] = None
    transaction_type: Optional[str] = None
    property_address: Optional[dict] = None
    mls_number: Optional[str] = None
    purchase_price: Optional[float] = None
    earnest_money: Optional[float] = None
    closing_date: Optional[str] = None
    document_requirements: Optional[list[dict]] = None


class AddParticipantRequest(BaseModel):
    email: str
    role: ParticipantRole
    name: Optional[str] = None


class UpdateParticipantRequest(BaseModel):
    role: Optional[ParticipantRole] = None


class LinkDocumentRequest(BaseModel):
    user_document_id: str
    doc_type: str
    offer_extraction_id: Optional[str] = None


class DotloopImportDocumentRequest(BaseModel):
    folder_id: int
    document_id: int
    name: str


class DotloopImportDocumentsBody(BaseModel):
    documents: list[DotloopImportDocumentRequest]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TXN_DOCS_DIR = os.path.join(os.path.dirname(__file__), "test_docs", "txn_docs")
_DOTLOOP_IMPORTS_DIR = os.path.join(os.path.dirname(__file__), "test_docs", "dotloop_imports")
_SETUP_BUCKET_WEIGHTS = {
    "transaction_fields": 35,
    "participant_acceptance": 20,
    "participant_profiles": 20,
    "required_documents": 25,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _get_user_or_dev(user) -> UserProfile:
    if user is not None:
        return user
    if not AUTH_ENABLED:
        dev_user = await UserProfile.find_one({"email": "dev@deslabs.local"})
        if not dev_user:
            dev_user = UserProfile(
                email="dev@deslabs.local",
                name="Dev User",
                has_clerk_account=False,
            )
            await dev_user.insert()
        return dev_user
    raise HTTPException(status_code=401, detail="Authentication required")


def _serialize_transaction(txn: Transaction) -> dict:
    data = txn.model_dump(mode="json")
    data["_id"] = str(txn.id)
    return data


async def _get_transaction_for_user(txn_id: str, user: UserProfile) -> Transaction:
    """Fetch a transaction and verify the user is involved."""
    txn = await Transaction.get(txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    uid = str(user.id)
    is_creator = txn.created_by == uid
    is_participant = any(p.user_id == uid for p in txn.participants)

    if not is_creator and not is_participant:
        raise HTTPException(status_code=403, detail="Not authorized for this transaction")

    return txn


async def _get_owned_transaction(txn_id: str, user: UserProfile) -> Transaction:
    txn = await _get_transaction_for_user(txn_id, user)
    if txn.created_by != str(user.id):
        raise HTTPException(status_code=403, detail="Only the creator can update this transaction")
    return txn


def _merge_property_address(
    existing: Optional[DotloopPropertyAddress],
    updates: Optional[dict],
) -> Optional[DotloopPropertyAddress]:
    """Merge partial property address updates onto the existing address."""
    if updates is None:
        return existing

    cleaned_updates = {}
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
        if value == "":
            continue
        cleaned_updates[key] = value

    merged = existing.model_dump(mode="json") if existing else {}
    merged.update(cleaned_updates)

    if not merged:
        return None

    return DotloopPropertyAddress.model_validate(merged)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _user_dotloop_tokens(user: UserProfile | None) -> dict | None:
    if not user or not getattr(user, "dotloop_tokens", None):
        return None
    tokens = user.dotloop_tokens
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
    }


def _parse_datetimeish(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _get_dotloop_profile_id() -> int:
    profile_id = os.getenv("DOTLOOP_PROFILE_ID")
    if not profile_id:
        raise HTTPException(status_code=500, detail="DOTLOOP_PROFILE_ID is not configured")
    return int(profile_id)


def _parse_floatish(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        cleaned = str(value).replace(",", "").replace("$", "").strip()
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _is_complete_property_address(address: dict[str, Any] | None) -> bool:
    if not address:
        return False
    required = [
        "street_number",
        "street_name",
        "city",
        "state_or_province",
        "postal_code",
    ]
    return all(bool(str(address.get(field, "")).strip()) for field in required)


def _default_agent_role_for_loop(loop_detail: dict[str, Any]) -> str:
    transaction_type = str(loop_detail.get("transaction_type") or "").lower()
    return "listing_agent" if "listing" in transaction_type else "buying_agent"


def _agent_role_to_participant_role(agent_role: str) -> ParticipantRole:
    return ParticipantRole.LISTING_AGENT if agent_role == "listing_agent" else ParticipantRole.BUYING_AGENT


def _agent_role_to_side(agent_role: str) -> str:
    return "seller" if agent_role == "listing_agent" else "buyer"


def _dotloop_role_to_participant_role(role: str | None) -> ParticipantRole:
    normalized = (role or "").strip().upper().replace(" ", "_")
    mapping = {
        "BUYER": ParticipantRole.BUYER,
        "SELLER": ParticipantRole.SELLER,
        "LISTING_AGENT": ParticipantRole.LISTING_AGENT,
        "BUYING_AGENT": ParticipantRole.BUYING_AGENT,
        "LISTING_BROKER": ParticipantRole.LISTING_BROKER,
        "BUYING_BROKER": ParticipantRole.BUYING_BROKER,
        "ESCROW_TITLE_REP": ParticipantRole.ESCROW_TITLE_REP,
        "LOAN_OFFICER": ParticipantRole.LOAN_OFFICER,
        "INSPECTOR": ParticipantRole.INSPECTOR,
        "APPRAISER": ParticipantRole.APPRAISER,
        "TRANSACTION_COORDINATOR": ParticipantRole.TRANSACTION_COORDINATOR,
    }
    return mapping.get(normalized, ParticipantRole.OTHER)


async def _mark_transaction_dotloop_state(
    txn: Transaction,
    *,
    status: DotloopSyncStatus,
    last_synced_at: Optional[datetime] = None,
    last_remote_updated_at: Optional[datetime] = None,
    error: Optional[str] = None,
) -> None:
    txn.dotloop_sync_status = status
    if last_synced_at is not None:
        txn.dotloop_last_synced_at = last_synced_at
    if last_remote_updated_at is not None:
        txn.dotloop_last_remote_updated_at = last_remote_updated_at
    txn.dotloop_sync_error = error
    txn.updated_at = _utcnow()
    await txn.save()


def _setup_bucket_status(score: float) -> str:
    if score >= 100:
        return "complete"
    if score <= 0:
        return "missing"
    return "partial"


async def _build_setup_progress(txn: Transaction) -> dict[str, Any]:
    from profile_routes import _compute_completion

    participant_status: list[dict[str, Any]] = []
    total_profile_completion = 0.0
    active_count = 0
    non_removed_count = 0

    for participant in txn.participants:
        if participant.status == ParticipantStatus.REMOVED:
            continue

        p_user = await UserProfile.get(participant.user_id)
        profile_completion = 0.0
        if p_user:
            profile_completion = _compute_completion(p_user).overall

        if participant.status == ParticipantStatus.ACTIVE:
            active_count += 1
        non_removed_count += 1
        total_profile_completion += profile_completion

        participant_status.append({
            "user_id": participant.user_id,
            "role": participant.role.value,
            "status": participant.status.value,
            "name": p_user.name if p_user else "",
            "email": p_user.email if p_user else "",
            "profile_completion": round(profile_completion, 1),
        })

    total_required = sum(1 for req in txn.document_requirements if req.required)
    satisfied = sum(1 for req in txn.document_requirements if req.required and req.satisfied)
    doc_completion = round((satisfied / total_required * 100) if total_required else 100.0, 1)

    transaction_field_reasons: list[str] = []
    if not txn.name or not txn.name.strip():
        transaction_field_reasons.append("Transaction name is missing.")
    if not txn.transaction_type or not str(txn.transaction_type).strip():
        transaction_field_reasons.append("Transaction type is missing.")
    if not txn.agent_side:
        transaction_field_reasons.append("Deal side is missing.")
    address = txn.property_address.model_dump(mode="json") if txn.property_address else None
    if not _is_complete_property_address(address):
        transaction_field_reasons.append(
            "Property address needs street number, street name, city, state, and ZIP."
        )
    transaction_fields_score = 100.0 if not transaction_field_reasons else round(
        ((4 - len(transaction_field_reasons)) / 4) * 100,
        1,
    )

    if non_removed_count <= 1:
        participant_acceptance_score = 100.0
        participant_acceptance_reasons: list[str] = []
    else:
        participant_acceptance_score = round((active_count / non_removed_count) * 100, 1)
        pending = non_removed_count - active_count
        participant_acceptance_reasons = [] if pending == 0 else [
            f"{pending} participant{'s' if pending != 1 else ''} still need to accept the invitation."
        ]

    participant_profiles_score = round(
        (total_profile_completion / len(participant_status)) if participant_status else 0.0,
        1,
    )
    participant_profile_reasons = [
        f"{participant['name'] or participant['email'] or 'Participant'} profile is only {round(participant['profile_completion'])}% complete."
        for participant in participant_status
        if participant["profile_completion"] < 100
    ]

    missing_requirements = [
        f"{req.role.value.replace('_', ' ').title()}: {req.doc_type.value.replace('_', ' ')}"
        for req in txn.document_requirements
        if req.required and not req.satisfied
    ]
    document_reasons = [] if not missing_requirements else [
        f"Missing required documents: {', '.join(missing_requirements[:4])}{'...' if len(missing_requirements) > 4 else ''}."
    ]

    buckets = [
        {
            "key": "transaction_fields",
            "label": "Transaction Fields",
            "weight": _SETUP_BUCKET_WEIGHTS["transaction_fields"],
            "score": transaction_fields_score,
            "status": _setup_bucket_status(transaction_fields_score),
            "reasons": transaction_field_reasons,
        },
        {
            "key": "participant_acceptance",
            "label": "Participant Acceptance",
            "weight": _SETUP_BUCKET_WEIGHTS["participant_acceptance"],
            "score": participant_acceptance_score,
            "status": _setup_bucket_status(participant_acceptance_score),
            "reasons": participant_acceptance_reasons,
        },
        {
            "key": "participant_profiles",
            "label": "Participant Profiles",
            "weight": _SETUP_BUCKET_WEIGHTS["participant_profiles"],
            "score": participant_profiles_score,
            "status": _setup_bucket_status(participant_profiles_score),
            "reasons": participant_profile_reasons,
        },
        {
            "key": "required_documents",
            "label": "Required Documents",
            "weight": _SETUP_BUCKET_WEIGHTS["required_documents"],
            "score": doc_completion,
            "status": _setup_bucket_status(doc_completion),
            "reasons": document_reasons,
        },
    ]

    overall = round(
        sum(bucket["score"] * bucket["weight"] for bucket in buckets) / 100,
        1,
    )

    blockers: list[str] = []
    for bucket in buckets:
        blockers.extend(bucket["reasons"])

    return {
        "kind": "setup_progress",
        "overall": overall,
        "blockers": blockers,
        "buckets": buckets,
        "participants": participant_status,
        "documents": {
            "total_required": total_required,
            "satisfied": satisfied,
            "completion": doc_completion,
            "requirements": [
                {
                    "doc_type": req.doc_type.value,
                    "role": req.role.value,
                    "required": req.required,
                    "satisfied": req.satisfied,
                }
                for req in txn.document_requirements
            ],
        },
    }


def _build_dotloop_preview(loop_detail: dict[str, Any], existing_transaction_id: Optional[str] = None) -> dict[str, Any]:
    warnings: list[str] = []
    property_address = dict(loop_detail.get("property_address") or {})
    if not _is_complete_property_address(property_address):
        warnings.append("Dotloop loop is missing a complete property address.")

    closing_dt = _parse_datetimeish((loop_detail.get("contract_dates") or {}).get("closing_date"))
    purchase_price = _parse_floatish((loop_detail.get("financials") or {}).get("purchase_price"))
    earnest_money = _parse_floatish((loop_detail.get("financials") or {}).get("earnest_money"))

    participant_suggestions = []
    for participant in loop_detail.get("participants") or []:
        role = _dotloop_role_to_participant_role(participant.get("role"))
        email = (participant.get("email") or "").strip()
        if not email:
            warnings.append(
                f"Skipped Dotloop participant '{participant.get('full_name') or participant.get('role') or 'Unknown'}' because no email was provided."
            )
        participant_suggestions.append({
            "name": participant.get("full_name") or "",
            "email": email or None,
            "role": role.value,
            "source_role": participant.get("role") or "",
            "can_invite": bool(email),
        })

    documents = loop_detail.get("documents") or []
    pdf_count = sum(1 for document in documents if str(document.get("name", "")).lower().endswith(".pdf"))

    return {
        "normalized_transaction": {
            "name": loop_detail.get("name") or f"Dotloop Loop {loop_detail.get('id')}",
            "transaction_type": loop_detail.get("transaction_type") or "purchase",
            "property_address": property_address if property_address else None,
            "purchase_price": purchase_price,
            "earnest_money": earnest_money,
            "closing_date": closing_dt.isoformat() if closing_dt else None,
            "dotloop_loop_id": str(loop_detail.get("id")),
        },
        "participant_suggestions": participant_suggestions,
        "available_documents": {
            "total": len(documents),
            "pdf_count": pdf_count,
            "documents": documents,
        },
        "warnings": warnings,
        "existing_transaction_id": existing_transaction_id,
    }


async def _ensure_transaction_document_link(
    txn: Transaction,
    *,
    doc_record: DocumentRecord,
    uploaded_by: str,
    filename: str,
    file_hash: str,
    doc_type: str = "dotloop_document",
) -> Optional[TransactionDocument]:
    existing_link = await TransactionDocument.find_one(
        {
            "transaction_id": str(txn.id),
            "document_record_id": str(doc_record.id),
        }
    )
    if existing_link:
        return None

    link = TransactionDocument(
        transaction_id=str(txn.id),
        doc_type=doc_type,
        source="dotloop",
        filename=filename,
        file_path=doc_record.file_path or "",
        file_hash=file_hash,
        document_record_id=str(doc_record.id),
        uploaded_by=uploaded_by,
    )
    await link.insert()
    return link


async def _import_dotloop_document(
    *,
    txn: Transaction,
    user: UserProfile,
    profile_id: int,
    loop_id: int,
    folder_id: int,
    document_id: int,
    name: str,
    user_tokens: dict | None,
) -> dict[str, Any]:
    composite_source_id = f"{loop_id}:{folder_id}:{document_id}"
    existing_doc = await DocumentRecord.find_one({"source_id": composite_source_id})
    if existing_doc:
        linked = await _ensure_transaction_document_link(
            txn,
            doc_record=existing_doc,
            uploaded_by=str(user.id),
            filename=existing_doc.filename,
            file_hash=existing_doc.file_hash or "",
        )
        latest_extraction_id = f"{existing_doc.id}:{len(existing_doc.extractions) - 1}" if existing_doc.extractions else None
        if latest_extraction_id and str(existing_doc.id) not in txn.extraction_ids:
            txn.extraction_ids.append(str(existing_doc.id))
            txn.updated_at = _utcnow()
            await txn.save()
        return {
            "local_document_id": str(existing_doc.id),
            "extraction_id": latest_extraction_id,
            "filename": existing_doc.filename,
            "duplicate": True,
            "linked_existing": bool(linked),
        }

    os.makedirs(_DOTLOOP_IMPORTS_DIR, exist_ok=True)

    with get_dotloop_client(user_tokens=user_tokens) as client:
        pdf_bytes = client.download_document(
            profile_id=profile_id,
            loop_id=loop_id,
            folder_id=folder_id,
            document_id=document_id,
        )

    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    safe_name = name or f"dotloop-{document_id}.pdf"
    dest_filename = f"{file_hash[:12]}_{safe_name}"
    dest_path = os.path.join(_DOTLOOP_IMPORTS_DIR, dest_filename)
    with open(dest_path, "wb") as handle:
        handle.write(pdf_bytes)

    try:
        engine = get_engine()
        mode = "real_estate"
        if engine.prefers_file_path:
            raw_extraction, _ = engine.extract_from_file(dest_path, mode)
        else:
            images = pdf_to_images(dest_path)
            images_b64 = [image_to_base64(img) for img in images]
            raw_extraction, _ = engine.extract(images_b64, mode)

        validated = DotloopLoopDetails.model_validate(raw_extraction)
        validated_data = validated.model_dump(mode="json")
        if engine.prefers_file_path:
            citations, _ = engine.verify_from_file(dest_path, validated_data)
        else:
            citations, _ = engine.verify(images_b64, validated_data)  # type: ignore[name-defined]

        overall_confidence = compute_overall_confidence(citations)
        file_info = get_pdf_info(dest_path)
        result = ExtractionResult(
            mode=mode,
            source_file=safe_name,
            extraction_timestamp=_utcnow().isoformat(),
            pages_processed=file_info["pages"],
            dotloop_data=validated_data,
            dotloop_api_payload=validated.to_dotloop_api_format(),
            citations=citations,
            overall_confidence=overall_confidence,
        )

        doc_id = await save_document(
            filename=safe_name,
            mode=mode,
            page_count=file_info["pages"],
            file_size_bytes=len(pdf_bytes),
            source="dotloop",
            source_id=composite_source_id,
            file_hash=file_hash,
            file_path=dest_path,
            user_id=str(user.id),
            org_id=user.org_id,
        )
        extraction_id = await save_extraction(document_id=doc_id, result=result, engine=engine.name)
        doc_record = await DocumentRecord.get(doc_id)
        if not doc_record:
            raise RuntimeError("Imported Dotloop document was not persisted")
        await _ensure_transaction_document_link(
            txn,
            doc_record=doc_record,
            uploaded_by=str(user.id),
            filename=safe_name,
            file_hash=file_hash,
        )
        if str(doc_record.id) not in txn.extraction_ids:
            txn.extraction_ids.append(str(doc_record.id))
        txn.updated_at = _utcnow()
        await txn.save()
        return {
            "local_document_id": str(doc_record.id),
            "extraction_id": extraction_id,
            "filename": safe_name,
            "duplicate": False,
            "linked_existing": False,
        }
    except Exception:
        if os.path.exists(dest_path):
            os.unlink(dest_path)
        raise


# ---------------------------------------------------------------------------
# Dotloop create/import flows
# ---------------------------------------------------------------------------


@router.post("/from-dotloop/{loop_id}/preview")
async def preview_transaction_from_dotloop(
    loop_id: int,
    body: CreateTransactionFromDotloopRequest = CreateTransactionFromDotloopRequest(),
    user=Depends(get_current_user),
):
    """Preview a local transaction draft created from a Dotloop loop."""
    u = await _get_user_or_dev(user)
    user_tokens = _user_dotloop_tokens(u)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=400, detail="Dotloop is not connected")

    try:
        loop_detail = await asyncio.to_thread(get_loop_with_details, loop_id, None, user_tokens)
    except DotloopAPIError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    existing = await Transaction.find_one({"dotloop_loop_id": str(loop_id)})
    preview = _build_dotloop_preview(loop_detail, str(existing.id) if existing else None)
    normalized = preview["normalized_transaction"]
    if body.name_override:
        normalized["name"] = body.name_override.strip()
    agent_role = body.agent_role or _default_agent_role_for_loop(loop_detail)
    normalized["agent_role"] = agent_role
    normalized["agent_side"] = _agent_role_to_side(agent_role)
    return preview


@router.post("/from-dotloop/{loop_id}")
async def create_transaction_from_dotloop(
    loop_id: int,
    body: CreateTransactionFromDotloopRequest = CreateTransactionFromDotloopRequest(),
    user=Depends(get_current_user),
):
    """Create a local transaction from an existing Dotloop loop."""
    u = await _get_user_or_dev(user)
    existing = await Transaction.find_one({"dotloop_loop_id": str(loop_id)})
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "A transaction is already linked to this Dotloop loop",
                "existing_transaction_id": str(existing.id),
            },
        )

    user_tokens = _user_dotloop_tokens(u)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=400, detail="Dotloop is not connected")

    try:
        loop_detail = await asyncio.to_thread(get_loop_with_details, loop_id, None, user_tokens)
    except DotloopAPIError as exc:
        raise HTTPException(status_code=502, detail=exc.message) from exc

    preview = _build_dotloop_preview(loop_detail)
    draft = preview["normalized_transaction"]
    agent_role = body.agent_role or _default_agent_role_for_loop(loop_detail)
    creator_role = _agent_role_to_participant_role(agent_role)
    creator_participant = TransactionParticipant(
        user_id=str(u.id),
        role=creator_role,
        status=ParticipantStatus.ACTIVE,
        added_at=_utcnow(),
    )

    property_address = None
    if _is_complete_property_address(draft.get("property_address")):
        property_address = DotloopPropertyAddress.model_validate(draft["property_address"])

    txn = Transaction(
        name=body.name_override.strip() if body.name_override else draft["name"],
        transaction_type=str(draft.get("transaction_type") or "purchase"),
        status=TransactionStatus.DRAFT,
        property_address=property_address,
        purchase_price=draft.get("purchase_price"),
        earnest_money=draft.get("earnest_money"),
        closing_date=_parse_datetimeish(draft.get("closing_date")),
        participants=[creator_participant],
        document_requirements=(
            [r.model_copy() for r in DEFAULT_PURCHASE_REQUIREMENTS]
            if str(draft.get("transaction_type") or "purchase") == "purchase"
            else []
        ),
        created_by=str(u.id),
        org_id=u.org_id,
        agent_side=_agent_role_to_side(agent_role),
        dotloop_loop_id=str(loop_id),
        dotloop_sync_status=DotloopSyncStatus.CURRENT,
        dotloop_last_synced_at=_utcnow(),
        dotloop_last_remote_updated_at=_parse_datetimeish(loop_detail.get("updated")),
        dotloop_sync_error=None,
    )

    participants_by_user_id = {str(u.id)}
    for participant in preview["participant_suggestions"]:
        email = participant.get("email")
        if not email:
            continue
        email = _normalize_email(str(email))
        existing_user = await UserProfile.find_one({"email": email})
        if not existing_user:
            existing_user = UserProfile(
                email=email,
                name=str(participant.get("name") or ""),
                has_clerk_account=False,
            )
            await existing_user.insert()
        if str(existing_user.id) in participants_by_user_id:
            continue
        participants_by_user_id.add(str(existing_user.id))
        txn.participants.append(
            TransactionParticipant(
                user_id=str(existing_user.id),
                role=ParticipantRole(participant["role"]),
                status=ParticipantStatus.INVITED,
                added_at=_utcnow(),
                added_by=str(u.id),
            )
        )

    await txn.insert()
    log.info("Transaction %s created from Dotloop loop %s", txn.id, loop_id)
    return _serialize_transaction(txn)


@router.get("/{txn_id}/dotloop/documents")
async def list_dotloop_documents_for_transaction(txn_id: str, user=Depends(get_current_user)):
    """List importable Dotloop documents for the linked loop on a transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)
    if not txn.dotloop_loop_id:
        raise HTTPException(status_code=400, detail="Transaction is not linked to a Dotloop loop")

    user_tokens = _user_dotloop_tokens(u)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=400, detail="Dotloop is not connected")

    try:
        loop_detail = await asyncio.to_thread(get_loop_with_details, int(txn.dotloop_loop_id), None, user_tokens)
    except DotloopAPIError as exc:
        await _mark_transaction_dotloop_state(txn, status=DotloopSyncStatus.ERROR, error=exc.message)
        raise HTTPException(status_code=502, detail=exc.message) from exc

    documents = loop_detail.get("documents") or []
    composite_ids = [f"{txn.dotloop_loop_id}:{doc.get('folder_id')}:{doc.get('id')}" for doc in documents]
    imported_docs = await DocumentRecord.find({"source_id": {"$in": composite_ids}}).to_list() if composite_ids else []
    imported_ids = {doc.source_id for doc in imported_docs}

    folders: dict[str, dict[str, Any]] = {}
    for document in documents:
        folder_key = str(document.get("folder_id"))
        folder = folders.setdefault(
            folder_key,
            {
                "folder_id": document.get("folder_id"),
                "folder_name": document.get("folder_name") or "Unfiled",
                "documents": [],
            },
        )
        composite_id = f"{txn.dotloop_loop_id}:{document.get('folder_id')}:{document.get('id')}"
        name = str(document.get("name") or "")
        folder["documents"].append({
            "folder_id": document.get("folder_id"),
            "folder_name": document.get("folder_name") or "Unfiled",
            "document_id": document.get("id"),
            "name": name,
            "is_pdf": name.lower().endswith(".pdf"),
            "already_imported": composite_id in imported_ids,
        })

    return {
        "loop_id": txn.dotloop_loop_id,
        "folders": list(folders.values()),
    }


@router.post("/{txn_id}/dotloop/import-documents")
async def import_dotloop_documents(
    txn_id: str,
    body: DotloopImportDocumentsBody,
    user=Depends(get_current_user),
):
    """Import selected Dotloop PDFs into the local transaction."""
    if len(body.documents) == 0:
        raise HTTPException(status_code=400, detail="Select at least one document to import")
    if len(body.documents) > 5:
        raise HTTPException(status_code=400, detail="You can import at most 5 documents at a time")

    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)
    if not txn.dotloop_loop_id:
        raise HTTPException(status_code=400, detail="Transaction is not linked to a Dotloop loop")

    user_tokens = _user_dotloop_tokens(u)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=400, detail="Dotloop is not connected")

    results = []
    failures = 0
    loop_id = int(txn.dotloop_loop_id)
    for document in body.documents:
        if not document.name.lower().endswith(".pdf"):
            results.append({
                "name": document.name,
                "document_id": document.document_id,
                "duplicate": False,
                "failed": True,
                "error": "Only PDF documents can be imported.",
            })
            failures += 1
            continue

        try:
            imported = await _import_dotloop_document(
                txn=txn,
                user=u,
                profile_id=_get_dotloop_profile_id(),
                loop_id=loop_id,
                folder_id=document.folder_id,
                document_id=document.document_id,
                name=document.name,
                user_tokens=user_tokens,
            )
            results.append({
                "name": document.name,
                "document_id": document.document_id,
                "failed": False,
                **imported,
            })
        except DotloopAPIError as exc:
            failures += 1
            results.append({
                "name": document.name,
                "document_id": document.document_id,
                "duplicate": False,
                "failed": True,
                "error": exc.message,
            })
        except Exception as exc:  # pragma: no cover - exercised via endpoint behavior
            failures += 1
            log.exception("Failed to import Dotloop document %s from loop %s", document.document_id, loop_id)
            results.append({
                "name": document.name,
                "document_id": document.document_id,
                "duplicate": False,
                "failed": True,
                "error": str(exc),
            })

    if failures == len(body.documents):
        await _mark_transaction_dotloop_state(txn, status=DotloopSyncStatus.ERROR, error="All selected Dotloop imports failed")
    else:
        await _mark_transaction_dotloop_state(
            txn,
            status=DotloopSyncStatus.CURRENT,
            last_synced_at=_utcnow(),
            error=None,
        )

    return {
        "results": results,
        "imported": sum(1 for result in results if not result.get("failed") and not result.get("duplicate")),
        "duplicates": sum(1 for result in results if result.get("duplicate")),
        "failed": failures,
    }


# ---------------------------------------------------------------------------
# Transaction CRUD
# ---------------------------------------------------------------------------


@router.post("")
async def create_transaction(
    req: CreateTransactionRequest,
    user=Depends(get_current_user),
):
    """Create a new transaction. Creator is auto-added as a participant."""
    u = await _get_user_or_dev(user)

    prop_addr = None
    if req.property_address:
        try:
            prop_addr = _merge_property_address(None, req.property_address)
        except Exception:
            pass

    closing = _parse_datetimeish(req.closing_date)

    from schemas import UserType

    if req.agent_role == "listing_agent":
        creator_role = ParticipantRole.LISTING_AGENT
        agent_side = "seller"
    elif req.agent_role == "buying_agent":
        creator_role = ParticipantRole.BUYING_AGENT
        agent_side = "buyer"
    elif UserType.AGENT in u.user_types:
        creator_role = ParticipantRole.LISTING_AGENT
        agent_side = "seller"
    elif UserType.BUYER in u.user_types:
        creator_role = ParticipantRole.BUYER
        agent_side = "buyer"
    elif UserType.SELLER in u.user_types:
        creator_role = ParticipantRole.SELLER
        agent_side = "seller"
    else:
        creator_role = ParticipantRole.OTHER
        agent_side = None

    creator_participant = TransactionParticipant(
        user_id=str(u.id),
        role=creator_role,
        status=ParticipantStatus.ACTIVE,
        added_at=_utcnow(),
    )

    doc_reqs = [r.model_copy() for r in DEFAULT_PURCHASE_REQUIREMENTS] if req.transaction_type == "purchase" else []

    txn = Transaction(
        name=req.name,
        transaction_type=req.transaction_type,
        status=TransactionStatus.DRAFT,
        property_address=prop_addr,
        mls_number=req.mls_number,
        purchase_price=req.purchase_price,
        earnest_money=req.earnest_money,
        closing_date=closing,
        participants=[creator_participant],
        document_requirements=doc_reqs,
        created_by=str(u.id),
        org_id=u.org_id,
        agent_side=agent_side,
    )
    await txn.insert()
    log.info("Transaction created: %s by user %s", txn.id, u.id)
    return _serialize_transaction(txn)


@router.get("")
async def list_transactions(
    status: Optional[TransactionStatus] = Query(None),
    user=Depends(get_current_user),
):
    """List transactions the current user is involved in."""
    u = await _get_user_or_dev(user)
    uid = str(u.id)

    query = {"$or": [{"created_by": uid}, {"participants.user_id": uid}]}
    if status:
        query["status"] = status.value

    txns = await Transaction.find(query).sort("-created_at").to_list()
    results = []
    for txn in txns:
        is_creator = txn.created_by == uid
        is_active_participant = any(
            participant.user_id == uid and participant.status != ParticipantStatus.REMOVED
            for participant in txn.participants
        )
        if is_creator or is_active_participant:
            results.append(_serialize_transaction(txn))
    return results


@router.get("/{txn_id}")
async def get_transaction(txn_id: str, user=Depends(get_current_user)):
    """Get a transaction's full details."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)
    return _serialize_transaction(txn)


@router.put("/{txn_id}")
async def update_transaction(
    txn_id: str,
    req: UpdateTransactionRequest,
    user=Depends(get_current_user),
):
    """Update a transaction's details. Only creator can update."""
    u = await _get_user_or_dev(user)
    txn = await _get_owned_transaction(txn_id, u)

    if req.name is not None:
        txn.name = req.name
    if req.status is not None:
        txn.status = req.status
    if req.transaction_type is not None:
        txn.transaction_type = req.transaction_type
    if req.mls_number is not None:
        txn.mls_number = req.mls_number
    if req.purchase_price is not None:
        txn.purchase_price = req.purchase_price
    if req.earnest_money is not None:
        txn.earnest_money = req.earnest_money
    if req.closing_date is not None:
        parsed = _parse_datetimeish(req.closing_date)
        if parsed:
            txn.closing_date = parsed
    if req.property_address is not None:
        try:
            txn.property_address = _merge_property_address(txn.property_address, req.property_address)
        except ValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Property address is incomplete. Street number, street name, city, "
                    "state, and ZIP are required to save the address."
                ),
            ) from exc
    if req.document_requirements is not None:
        txn.document_requirements = [
            DocumentRequirement.model_validate(requirement) for requirement in req.document_requirements
        ]

    txn.updated_at = _utcnow()
    await txn.save()
    return _serialize_transaction(txn)


@router.delete("/{txn_id}")
async def delete_transaction(txn_id: str, user=Depends(get_current_user)):
    """Delete a transaction. Only allowed for DRAFT status."""
    u = await _get_user_or_dev(user)
    txn = await _get_owned_transaction(txn_id, u)

    if txn.status != TransactionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft transactions can be deleted")

    await txn.delete()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Dotloop Loop Linking
# ---------------------------------------------------------------------------


@router.patch("/{txn_id}/dotloop-loop")
async def set_dotloop_loop(
    txn_id: str,
    body: SetDotloopLoopBody,
    user=Depends(get_current_user),
):
    """Link a Dotloop loop ID to a transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_owned_transaction(txn_id, u)

    existing = await Transaction.find_one({"dotloop_loop_id": body.loop_id, "_id": {"$ne": txn.id}})
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "That Dotloop loop is already linked to another transaction",
                "existing_transaction_id": str(existing.id),
            },
        )

    txn.dotloop_loop_id = body.loop_id
    txn.dotloop_sync_status = DotloopSyncStatus.NEVER
    txn.dotloop_sync_error = None
    txn.updated_at = _utcnow()
    await txn.save()
    return _serialize_transaction(txn)


# ---------------------------------------------------------------------------
# Participant Management
# ---------------------------------------------------------------------------


@router.post("/{txn_id}/participants")
async def add_participant(
    txn_id: str,
    req: AddParticipantRequest,
    user=Depends(get_current_user),
):
    """Add a participant to a transaction by email. Creates user if needed."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    participant_user = await UserProfile.find_one({"email": _normalize_email(req.email)})
    if not participant_user:
        participant_user = UserProfile(
            email=_normalize_email(req.email),
            name=req.name or "",
            has_clerk_account=False,
        )
        await participant_user.insert()
        log.info("Created placeholder user for %s", req.email)

    pid = str(participant_user.id)
    existing = next((participant for participant in txn.participants if participant.user_id == pid), None)
    if existing:
        if existing.status == ParticipantStatus.REMOVED:
            existing.status = ParticipantStatus.INVITED
            existing.role = req.role
            existing.removed_at = None
            existing.added_at = _utcnow()
            existing.added_by = str(u.id)
        elif existing.status in (ParticipantStatus.INVITED, ParticipantStatus.ACTIVE):
            raise HTTPException(status_code=400, detail="Participant already in transaction")
    else:
        txn.participants.append(
            TransactionParticipant(
                user_id=pid,
                role=req.role,
                status=ParticipantStatus.INVITED,
                added_at=_utcnow(),
                added_by=str(u.id),
            )
        )

    txn.updated_at = _utcnow()
    await txn.save()
    return {
        "participant": {
            "user_id": pid,
            "email": participant_user.email,
            "name": participant_user.name,
            "role": req.role.value,
            "status": ParticipantStatus.INVITED.value,
        },
        "transaction_id": str(txn.id),
    }


@router.put("/{txn_id}/participants/{participant_uid}")
async def update_participant(
    txn_id: str,
    participant_uid: str,
    req: UpdateParticipantRequest,
    user=Depends(get_current_user),
):
    """Update a participant's role."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    participant = next((item for item in txn.participants if item.user_id == participant_uid), None)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    if req.role is not None:
        participant.role = req.role

    txn.updated_at = _utcnow()
    await txn.save()
    return {"updated": True}


@router.delete("/{txn_id}/participants/{participant_uid}")
async def remove_participant(
    txn_id: str,
    participant_uid: str,
    user=Depends(get_current_user),
):
    """Soft-remove a participant from a transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    if txn.created_by != str(u.id) and participant_uid != str(u.id):
        raise HTTPException(status_code=403, detail="Only the creator can remove participants")

    participant = next((item for item in txn.participants if item.user_id == participant_uid), None)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    participant.status = ParticipantStatus.REMOVED
    participant.removed_at = _utcnow()
    txn.updated_at = _utcnow()
    await txn.save()
    return {"removed": True}


# ---------------------------------------------------------------------------
# Transaction Documents
# ---------------------------------------------------------------------------


@router.get("/{txn_id}/documents")
async def list_transaction_documents(
    txn_id: str,
    user=Depends(get_current_user),
):
    """List all documents attached to a transaction."""
    u = await _get_user_or_dev(user)
    await _get_transaction_for_user(txn_id, u)

    docs = await TransactionDocument.find({"transaction_id": txn_id}).sort("-uploaded_at").to_list()
    return [{"_id": str(doc.id), **doc.model_dump(mode="json")} for doc in docs]


@router.post("/{txn_id}/documents")
async def link_document_to_transaction(
    txn_id: str,
    req: LinkDocumentRequest,
    user=Depends(get_current_user),
):
    """Link a user's profile document to a transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    user_doc = await UserDocument.get(req.user_document_id)
    if not user_doc:
        raise HTTPException(status_code=404, detail="User document not found")

    txn_doc = TransactionDocument(
        transaction_id=str(txn.id),
        doc_type=req.doc_type,
        source="user_profile",
        source_user_document_id=req.user_document_id,
        filename=user_doc.filename,
        file_path=user_doc.file_path,
        file_hash=user_doc.file_hash,
        uploaded_by=str(u.id),
        offer_extraction_id=req.offer_extraction_id,
    )
    await txn_doc.insert()

    for requirement in txn.document_requirements:
        if requirement.doc_type.value == req.doc_type and not requirement.satisfied:
            participant = next((item for item in txn.participants if item.user_id == user_doc.user_id), None)
            if participant and participant.role == requirement.role:
                requirement.satisfied = True
                requirement.satisfied_by = req.user_document_id
                break

    txn.updated_at = _utcnow()
    await txn.save()
    return {"_id": str(txn_doc.id), **txn_doc.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Offer-Scoped Document Upload
# ---------------------------------------------------------------------------


@router.post("/{txn_id}/documents/upload-file")
async def upload_offer_document(
    txn_id: str,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    offer_extraction_id: Optional[str] = Form(None),
    user=Depends(get_current_user),
):
    """Upload a supporting document scoped to a specific offer (no OCR extraction)."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    u = await _get_user_or_dev(user)
    await _get_transaction_for_user(txn_id, u)

    os.makedirs(_TXN_DOCS_DIR, exist_ok=True)
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()
    dest_filename = f"{file_hash[:12]}_{file.filename}"
    dest_path = os.path.join(_TXN_DOCS_DIR, dest_filename)
    with open(dest_path, "wb") as handle:
        handle.write(contents)

    txn_doc = TransactionDocument(
        transaction_id=txn_id,
        doc_type=doc_type,
        source="upload",
        filename=file.filename,
        file_path=dest_path,
        file_hash=file_hash,
        uploaded_by=str(u.id),
        offer_extraction_id=offer_extraction_id,
    )
    await txn_doc.insert()
    return {"_id": str(txn_doc.id), **txn_doc.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Auto-Fill & Setup Progress
# ---------------------------------------------------------------------------


@router.post("/{txn_id}/auto-fill")
async def auto_fill_transaction(
    txn_id: str,
    user=Depends(get_current_user),
):
    """Pull profile data from participants into the transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    filled_fields = []
    from profile_routes import _compute_completion

    for participant in txn.participants:
        if participant.status == ParticipantStatus.REMOVED:
            continue

        p_user = await UserProfile.get(participant.user_id)
        if not p_user:
            continue

        if participant.role == ParticipantRole.BUYER and p_user.buyer_profile:
            buyer_profile = p_user.buyer_profile
            if buyer_profile.pre_approval_amount and not txn.purchase_price:
                txn.purchase_price = buyer_profile.pre_approval_amount
                filled_fields.append("purchase_price (from buyer pre-approval)")

        completion = _compute_completion(p_user)
        participant.profile_completion = completion.overall

    txn.updated_at = _utcnow()
    await txn.save()
    return {"filled_fields": filled_fields, "transaction": _serialize_transaction(txn)}


@router.get("/{txn_id}/completion")
async def get_transaction_completion(
    txn_id: str,
    user=Depends(get_current_user),
):
    """Get setup progress for the transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)
    return await _build_setup_progress(txn)


# ---------------------------------------------------------------------------
# Extraction Linking
# ---------------------------------------------------------------------------


@router.post("/{txn_id}/extractions/{extraction_id}")
async def link_extraction(
    txn_id: str,
    extraction_id: str,
    user=Depends(get_current_user),
):
    """Link an extraction (DocumentRecord) to a transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    doc_id = extraction_id.split(":")[0] if ":" in extraction_id else extraction_id
    try:
        doc_record = await DocumentRecord.get(doc_id)
    except Exception:
        doc_record = None
    if not doc_record:
        raise HTTPException(status_code=404, detail="Extraction not found")

    if doc_id not in txn.extraction_ids:
        txn.extraction_ids.append(doc_id)
        await txn.save()
    return _serialize_transaction(txn)


@router.delete("/{txn_id}/extractions/{extraction_id}")
async def unlink_extraction(
    txn_id: str,
    extraction_id: str,
    user=Depends(get_current_user),
):
    """Unlink an extraction from a transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    if extraction_id in txn.extraction_ids:
        txn.extraction_ids.remove(extraction_id)
        await txn.save()
    return _serialize_transaction(txn)


@router.get("/{txn_id}/extractions")
async def list_transaction_extractions(
    txn_id: str,
    user=Depends(get_current_user),
):
    """List extraction summaries linked to a transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    summaries = []
    for extraction_ref in txn.extraction_ids:
        doc_id = extraction_ref.split(":")[0] if ":" in extraction_ref else extraction_ref
        try:
            doc_record = await DocumentRecord.get(doc_id)
        except Exception:
            continue
        if not doc_record:
            continue
        latest = doc_record.extractions[-1] if doc_record.extractions else None
        summaries.append(
            {
                "id": str(doc_record.id),
                "filename": doc_record.filename,
                "mode": latest.mode if latest else doc_record.mode,
                "overall_confidence": latest.overall_confidence if latest else 0.0,
                "pages_processed": latest.pages_processed if latest else doc_record.page_count,
                "created_at": latest.created_at.isoformat() if latest and latest.created_at else None,
            }
        )

    return {"extractions": summaries}
