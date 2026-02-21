"""Transaction management API routes for D.E.S.

Handles transaction CRUD, participant management, document linking,
auto-fill from profiles, and transaction completion tracking.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import get_current_user, AUTH_ENABLED
from db import Transaction, UserProfile, UserDocument, TransactionDocument
from schemas import (
    DotloopPropertyAddress,
    DocumentRequirement,
    ParticipantRole,
    ParticipantStatus,
    TransactionParticipant,
    TransactionStatus,
    UserDocumentType,
    DEFAULT_PURCHASE_REQUIREMENTS,
)

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


class UpdateTransactionRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[TransactionStatus] = None
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_user_or_dev(user) -> UserProfile:
    if user is not None:
        return user
    if not AUTH_ENABLED:
        dev_user = await UserProfile.find_one(UserProfile.email == "dev@deslabs.local")
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

    # Parse property address if provided
    prop_addr = None
    if req.property_address:
        try:
            prop_addr = DotloopPropertyAddress.model_validate(req.property_address)
        except Exception:
            pass  # Allow partial address data

    # Parse closing date
    closing = None
    if req.closing_date:
        try:
            closing = datetime.fromisoformat(req.closing_date)
        except ValueError:
            pass

    # Determine creator's role
    from schemas import UserType
    if UserType.AGENT in u.user_types:
        creator_role = ParticipantRole.LISTING_AGENT
    elif UserType.BUYER in u.user_types:
        creator_role = ParticipantRole.BUYER
    elif UserType.SELLER in u.user_types:
        creator_role = ParticipantRole.SELLER
    else:
        creator_role = ParticipantRole.OTHER

    creator_participant = TransactionParticipant(
        user_id=str(u.id),
        role=creator_role,
        status=ParticipantStatus.ACTIVE,
        added_at=datetime.now(timezone.utc),
    )

    # Default document requirements for purchase transactions
    doc_reqs = []
    if req.transaction_type == "purchase":
        doc_reqs = [r.model_copy() for r in DEFAULT_PURCHASE_REQUIREMENTS]

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

    # Find transactions where user is creator or participant
    query = {
        "$or": [
            {"created_by": uid},
            {"participants.user_id": uid},
        ]
    }
    if status:
        query["status"] = status.value

    txns = await Transaction.find(query).sort("-created_at").to_list()

    # Filter out removed participants from the user's perspective
    results = []
    for txn in txns:
        is_creator = txn.created_by == uid
        is_active_participant = any(
            p.user_id == uid and p.status != ParticipantStatus.REMOVED
            for p in txn.participants
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
    txn = await _get_transaction_for_user(txn_id, u)

    if txn.created_by != str(u.id):
        raise HTTPException(status_code=403, detail="Only the creator can update this transaction")

    if req.name is not None:
        txn.name = req.name
    if req.status is not None:
        txn.status = req.status
    if req.mls_number is not None:
        txn.mls_number = req.mls_number
    if req.purchase_price is not None:
        txn.purchase_price = req.purchase_price
    if req.earnest_money is not None:
        txn.earnest_money = req.earnest_money
    if req.closing_date is not None:
        try:
            txn.closing_date = datetime.fromisoformat(req.closing_date)
        except ValueError:
            pass
    if req.property_address is not None:
        try:
            txn.property_address = DotloopPropertyAddress.model_validate(req.property_address)
        except Exception:
            pass
    if req.document_requirements is not None:
        txn.document_requirements = [
            DocumentRequirement.model_validate(r) for r in req.document_requirements
        ]

    txn.updated_at = datetime.now(timezone.utc)
    await txn.save()

    return _serialize_transaction(txn)


@router.delete("/{txn_id}")
async def delete_transaction(txn_id: str, user=Depends(get_current_user)):
    """Delete a transaction. Only allowed for DRAFT status."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    if txn.created_by != str(u.id):
        raise HTTPException(status_code=403, detail="Only the creator can delete this transaction")

    if txn.status != TransactionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft transactions can be deleted")

    await txn.delete()
    return {"deleted": True}


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

    # Find or create the participant user
    participant_user = await UserProfile.find_one(UserProfile.email == req.email)
    if not participant_user:
        participant_user = UserProfile(
            email=req.email,
            name=req.name or "",
            has_clerk_account=False,
        )
        await participant_user.insert()
        log.info("Created placeholder user for %s", req.email)

    pid = str(participant_user.id)

    # Check for duplicates (allow re-adding removed participants)
    existing = next(
        (p for p in txn.participants if p.user_id == pid),
        None,
    )
    if existing:
        if existing.status == ParticipantStatus.REMOVED:
            existing.status = ParticipantStatus.INVITED
            existing.role = req.role
            existing.removed_at = None
            existing.added_at = datetime.now(timezone.utc)
            existing.added_by = str(u.id)
        elif existing.status in (ParticipantStatus.INVITED, ParticipantStatus.ACTIVE):
            raise HTTPException(status_code=400, detail="Participant already in transaction")
    else:
        participant = TransactionParticipant(
            user_id=pid,
            role=req.role,
            status=ParticipantStatus.INVITED,
            added_at=datetime.now(timezone.utc),
            added_by=str(u.id),
        )
        txn.participants.append(participant)

    txn.updated_at = datetime.now(timezone.utc)
    await txn.save()

    return {
        "participant": {
            "user_id": pid,
            "email": participant_user.email,
            "name": participant_user.name,
            "role": req.role.value,
            "status": "invited",
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

    participant = next(
        (p for p in txn.participants if p.user_id == participant_uid),
        None,
    )
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    if req.role is not None:
        participant.role = req.role

    txn.updated_at = datetime.now(timezone.utc)
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

    # Only creator can remove participants (or self-remove)
    if txn.created_by != str(u.id) and participant_uid != str(u.id):
        raise HTTPException(status_code=403, detail="Only the creator can remove participants")

    participant = next(
        (p for p in txn.participants if p.user_id == participant_uid),
        None,
    )
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")

    participant.status = ParticipantStatus.REMOVED
    participant.removed_at = datetime.now(timezone.utc)

    txn.updated_at = datetime.now(timezone.utc)
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

    docs = await TransactionDocument.find(
        TransactionDocument.transaction_id == txn_id
    ).sort("-uploaded_at").to_list()

    return [
        {
            "_id": str(d.id),
            **d.model_dump(mode="json"),
        }
        for d in docs
    ]


@router.post("/{txn_id}/documents")
async def link_document_to_transaction(
    txn_id: str,
    req: LinkDocumentRequest,
    user=Depends(get_current_user),
):
    """Link a user's profile document to a transaction."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    # Get the source user document
    user_doc = await UserDocument.get(req.user_document_id)
    if not user_doc:
        raise HTTPException(status_code=404, detail="User document not found")

    # Create transaction document reference
    txn_doc = TransactionDocument(
        transaction_id=str(txn.id),
        doc_type=req.doc_type,
        source="user_profile",
        source_user_document_id=req.user_document_id,
        filename=user_doc.filename,
        file_path=user_doc.file_path,
        file_hash=user_doc.file_hash,
        uploaded_by=str(u.id),
    )
    await txn_doc.insert()

    # Check if this satisfies a document requirement
    for dreq in txn.document_requirements:
        if dreq.doc_type.value == req.doc_type and not dreq.satisfied:
            # Check if the uploader has the right role
            participant = next(
                (p for p in txn.participants if p.user_id == user_doc.user_id),
                None,
            )
            if participant and participant.role == dreq.role:
                dreq.satisfied = True
                dreq.satisfied_by = req.user_document_id
                break

    txn.updated_at = datetime.now(timezone.utc)
    await txn.save()

    return {
        "_id": str(txn_doc.id),
        **txn_doc.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Auto-Fill & Completion
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

    for participant in txn.participants:
        if participant.status == ParticipantStatus.REMOVED:
            continue

        p_user = await UserProfile.get(participant.user_id)
        if not p_user:
            continue

        # Auto-fill from buyer's pre-approval
        if participant.role == ParticipantRole.BUYER and p_user.buyer_profile:
            bp = p_user.buyer_profile
            if bp.pre_approval_amount and not txn.purchase_price:
                txn.purchase_price = bp.pre_approval_amount
                filled_fields.append("purchase_price (from buyer pre-approval)")

        # Update participant completion
        from profile_routes import _compute_completion
        completion = _compute_completion(p_user)
        participant.profile_completion = completion.overall

    txn.updated_at = datetime.now(timezone.utc)
    await txn.save()

    return {
        "filled_fields": filled_fields,
        "transaction": _serialize_transaction(txn),
    }


@router.get("/{txn_id}/completion")
async def get_transaction_completion(
    txn_id: str,
    user=Depends(get_current_user),
):
    """Get transaction readiness: participant profiles + document requirements."""
    u = await _get_user_or_dev(user)
    txn = await _get_transaction_for_user(txn_id, u)

    # Participant readiness
    participant_status = []
    for p in txn.participants:
        if p.status == ParticipantStatus.REMOVED:
            continue

        p_user = await UserProfile.get(p.user_id)
        p_info = {
            "user_id": p.user_id,
            "role": p.role.value,
            "status": p.status.value,
            "name": p_user.name if p_user else "",
            "email": p_user.email if p_user else "",
            "profile_completion": 0.0,
        }

        if p_user:
            from profile_routes import _compute_completion
            completion = _compute_completion(p_user)
            p_info["profile_completion"] = completion.overall

        participant_status.append(p_info)

    # Document requirements
    total_required = sum(1 for r in txn.document_requirements if r.required)
    satisfied = sum(1 for r in txn.document_requirements if r.required and r.satisfied)
    doc_completion = (satisfied / total_required * 100) if total_required else 100.0

    # Overall readiness
    avg_profile = (
        sum(p["profile_completion"] for p in participant_status) / len(participant_status)
        if participant_status else 0
    )
    overall = round((avg_profile * 0.5 + doc_completion * 0.5), 1)

    return {
        "overall": overall,
        "participants": participant_status,
        "documents": {
            "total_required": total_required,
            "satisfied": satisfied,
            "completion": round(doc_completion, 1),
            "requirements": [
                {
                    "doc_type": r.doc_type.value,
                    "role": r.role.value,
                    "required": r.required,
                    "satisfied": r.satisfied,
                }
                for r in txn.document_requirements
            ],
        },
    }
