"""Transaction invitation API routes.

Handles creating invitations, listing delivery state, validating invite links,
accepting invitations, submitting profile data via invite links, and upgrading
placeholder users to Clerk accounts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import AUTH_ENABLED, CLERK_SECRET_KEY, generate_magic_link_token, get_current_user
from rate_limiter import limiter
from route_helpers import _get_user_or_dev, _normalize_email, _utcnow
from db import Transaction, TransactionInvitation, UserProfile
from invitation_delivery import build_invite_url, send_invitation_email
from schemas import InvitationStatus, ParticipantRole, ParticipantStatus, TransactionParticipant, UserType

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["invitations"])

_INVITATION_TTL_SECONDS = 86400
_INVITATION_SECRET = os.getenv("INVITATION_LINK_SECRET", "") or CLERK_SECRET_KEY or "dev-invitation-secret"


class CreateInvitationRequest(BaseModel):
    email: str
    role: ParticipantRole
    transaction_id: str
    name: Optional[str] = None


class ProfileSubmitRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[dict] = None


_CLERK_USER_ID_RE = re.compile(r"^user_[A-Za-z0-9]+$")


class UpgradeRequest(BaseModel):
    clerk_user_id: str


def _hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _sign_invitation_token(token: str, email: str, transaction_id: str, invitation_id: str) -> str:
    payload = json.dumps(
        {
            "token": token,
            "email": email,
            "txn_id": transaction_id,
            "invite_id": invitation_id,
            "ts": int(time.time()),
        }
    )
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(_INVITATION_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def _verify_invitation_token(signed_token: str) -> dict:
    parts = signed_token.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid invitation link")

    payload_b64, sig = parts
    expected_sig = hmac.new(_INVITATION_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=400, detail="Invalid invitation signature")

    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Malformed invitation link") from exc

    ts = payload.get("ts", 0)
    if time.time() - ts > _INVITATION_TTL_SECONDS:
        raise HTTPException(status_code=400, detail="Invitation link expired")

    return payload


async def _get_invitation_for_token(signed_token: str) -> tuple[TransactionInvitation, dict]:
    payload = _verify_invitation_token(signed_token)
    invitation_id = payload.get("invite_id")
    if not invitation_id:
        raise HTTPException(status_code=400, detail="Invitation link missing invitation id")

    invitation = await TransactionInvitation.get(invitation_id)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    now = _utcnow()
    expires_at = invitation.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if invitation.status == InvitationStatus.REVOKED:
        raise HTTPException(status_code=401, detail="Invitation has been revoked")

    if expires_at and expires_at < now:
        invitation.status = InvitationStatus.EXPIRED
        invitation.updated_at = now
        await invitation.save()
        raise HTTPException(status_code=401, detail="Invitation has expired")

    if invitation.email != payload.get("email") or invitation.transaction_id != payload.get("txn_id"):
        raise HTTPException(status_code=401, detail="Invitation link mismatch")

    token_hash = invitation.token_hash or ""
    if not token_hash or not hmac.compare_digest(token_hash, _hash_invitation_token(payload.get("token", ""))):
        raise HTTPException(status_code=401, detail="Invalid or replaced invitation link")

    return invitation, payload


def _role_label(role: ParticipantRole) -> str:
    return role.value.replace("_", " ").title()


def _role_to_user_type(role: ParticipantRole) -> Optional[UserType]:
    role_map = {
        ParticipantRole.BUYER: UserType.BUYER,
        ParticipantRole.SELLER: UserType.SELLER,
        ParticipantRole.LISTING_AGENT: UserType.AGENT,
        ParticipantRole.BUYING_AGENT: UserType.AGENT,
        ParticipantRole.LOAN_OFFICER: UserType.LOAN_OFFICER,
    }
    return role_map.get(role)


async def _ensure_transaction_participant(
    txn: Transaction,
    *,
    invitee_user: UserProfile,
    role: ParticipantRole,
    actor_id: str,
) -> None:
    participant = next((p for p in txn.participants if p.user_id == str(invitee_user.id)), None)
    if participant:
        if participant.status == ParticipantStatus.REMOVED:
            participant.status = ParticipantStatus.INVITED
            participant.removed_at = None
        participant.role = role
        participant.added_at = participant.added_at or _utcnow()
        participant.added_by = participant.added_by or actor_id
    else:
        txn.participants.append(
            TransactionParticipant(
                user_id=str(invitee_user.id),
                role=role,
                status=ParticipantStatus.INVITED,
                added_at=_utcnow(),
                added_by=actor_id,
            )
        )


def serialize_invitation(invitation: TransactionInvitation) -> dict:
    return {
        "id": str(invitation.id),
        "transaction_id": invitation.transaction_id,
        "invitee_user_id": invitation.invitee_user_id,
        "email": invitation.email,
        "name": invitation.name,
        "role": invitation.role.value,
        "status": invitation.status.value,
        "expires_at": invitation.expires_at.isoformat() if invitation.expires_at else None,
        "sent_at": invitation.sent_at.isoformat() if invitation.sent_at else None,
        "opened_at": invitation.opened_at.isoformat() if invitation.opened_at else None,
        "accepted_at": invitation.accepted_at.isoformat() if invitation.accepted_at else None,
        "revoked_at": invitation.revoked_at.isoformat() if invitation.revoked_at else None,
        "provider": invitation.provider,
        "provider_message_id": invitation.provider_message_id,
        "last_error": invitation.last_error,
        "invite_url": build_invite_url(invitation.signed_token) if invitation.signed_token else None,
    }


async def _load_transaction_for_owner(transaction_id: str, user: UserProfile) -> Transaction:
    txn = await Transaction.get(transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.created_by != str(user.id):
        raise HTTPException(status_code=403, detail="Only the creator can manage invitations")
    return txn


async def _prepare_invitation(
    invitation: TransactionInvitation,
    *,
    email: str,
    name: Optional[str],
    role: ParticipantRole,
    transaction_id: str,
) -> None:
    invitation.email = email
    invitation.name = name
    invitation.role = role
    invitation.transaction_id = transaction_id
    invitation.updated_at = _utcnow()
    if invitation.id is None:
        await invitation.insert()

    raw_token = generate_magic_link_token()
    signed_token = _sign_invitation_token(raw_token, email, transaction_id, str(invitation.id))
    invitation.token_hash = _hash_invitation_token(raw_token)
    invitation.signed_token = signed_token
    invitation.expires_at = _utcnow() + timedelta(seconds=_INVITATION_TTL_SECONDS)
    invitation.status = InvitationStatus.CREATED
    invitation.sent_at = None
    invitation.opened_at = None
    invitation.accepted_at = None
    invitation.revoked_at = None
    invitation.provider = None
    invitation.provider_message_id = None
    invitation.last_error = None
    invitation.updated_at = _utcnow()


async def _deliver_invitation(invitation: TransactionInvitation, txn: Transaction) -> None:
    invite_url = build_invite_url(invitation.signed_token or "")
    delivery = await send_invitation_email(
        to_email=invitation.email,
        invitee_name=invitation.name,
        transaction_name=txn.name,
        role_label=_role_label(invitation.role),
        invite_url=invite_url,
    )

    now = _utcnow()
    invitation.provider = delivery.provider
    invitation.provider_message_id = delivery.provider_message_id
    invitation.updated_at = now

    if delivery.delivered:
        invitation.status = InvitationStatus.SENT
        invitation.sent_at = now
        invitation.last_error = None
        return

    if delivery.provider:
        invitation.status = InvitationStatus.FAILED
        invitation.last_error = delivery.error or "Invitation delivery failed"
        return

    invitation.status = InvitationStatus.CREATED
    invitation.last_error = None


@router.post("/invitations")
async def create_invitation(
    req: CreateInvitationRequest,
    user=Depends(get_current_user),
):
    """Create or refresh a transaction invitation and attempt delivery."""
    u = await _get_user_or_dev(user)
    txn = await _load_transaction_for_owner(req.transaction_id, u)

    email = _normalize_email(req.email)
    invitee = await UserProfile.find_one({"email": email})
    if not invitee:
        invitee = UserProfile(email=email, name=req.name or "", has_clerk_account=False)
        await invitee.insert()
        log.info("Created placeholder user for invitation: %s", email)
    elif req.name and not invitee.name:
        invitee.name = req.name
        await invitee.save()

    await _ensure_transaction_participant(txn, invitee_user=invitee, role=req.role, actor_id=str(u.id))
    txn.updated_at = _utcnow()
    await txn.save()

    existing = await TransactionInvitation.find(
        {
            "transaction_id": str(txn.id),
            "email": email,
            "status": {"$ne": InvitationStatus.ACCEPTED.value},
        }
    ).sort("-updated_at").first_or_none()

    if existing and existing.status == InvitationStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Invitation already accepted")

    invitation = existing or TransactionInvitation(
        transaction_id=str(txn.id),
        invitee_user_id=str(invitee.id),
        email=email,
        name=req.name or invitee.name or None,
        role=req.role,
        created_by=str(u.id),
    )
    invitation.invitee_user_id = str(invitee.id)
    invitation.created_by = str(u.id)
    invitation.name = req.name or invitee.name or invitation.name

    await _prepare_invitation(invitation, email=email, name=invitation.name, role=req.role, transaction_id=str(txn.id))
    await _deliver_invitation(invitation, txn)
    await invitation.save()

    return serialize_invitation(invitation)


@router.get("/transactions/{txn_id}/invitations")
async def list_transaction_invitations(txn_id: str, user=Depends(get_current_user)):
    """List invitations belonging to a transaction."""
    u = await _get_user_or_dev(user)
    await _load_transaction_for_owner(txn_id, u)
    invitations = await TransactionInvitation.find(
        {"transaction_id": txn_id}
    ).sort("-updated_at").to_list()
    return {"invitations": [serialize_invitation(inv) for inv in invitations]}


@router.post("/invitations/{invitation_id}/resend")
async def resend_invitation(invitation_id: str, user=Depends(get_current_user)):
    """Refresh an invitation token and attempt delivery again."""
    u = await _get_user_or_dev(user)
    invitation = await TransactionInvitation.get(invitation_id)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    txn = await _load_transaction_for_owner(invitation.transaction_id, u)
    if invitation.status == InvitationStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Accepted invitations cannot be resent")
    if invitation.status == InvitationStatus.REVOKED:
        raise HTTPException(status_code=400, detail="Revoked invitations cannot be resent")

    await _prepare_invitation(
        invitation,
        email=invitation.email,
        name=invitation.name,
        role=invitation.role,
        transaction_id=invitation.transaction_id,
    )
    await _deliver_invitation(invitation, txn)
    await invitation.save()
    return serialize_invitation(invitation)


@router.post("/invitations/{invitation_id}/revoke")
async def revoke_invitation(invitation_id: str, user=Depends(get_current_user)):
    """Revoke a pending invitation."""
    u = await _get_user_or_dev(user)
    invitation = await TransactionInvitation.get(invitation_id)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    await _load_transaction_for_owner(invitation.transaction_id, u)
    if invitation.status == InvitationStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Accepted invitations cannot be revoked")

    invitation.status = InvitationStatus.REVOKED
    invitation.revoked_at = _utcnow()
    invitation.signed_token = None
    invitation.token_hash = None
    invitation.updated_at = _utcnow()
    await invitation.save()
    return serialize_invitation(invitation)


@router.get("/invitations/{token}/validate")
@limiter.limit("30/minute")
async def validate_invitation(request: Request, token: str):
    """Validate a transaction invitation link and return the landing payload."""
    invitation, _payload = await _get_invitation_for_token(token)
    invitee = await UserProfile.get(invitation.invitee_user_id) if invitation.invitee_user_id else None
    if not invitee:
        invitee = await UserProfile.find_one({"email": invitation.email})
    if not invitee:
        raise HTTPException(status_code=404, detail="Invitation user not found")

    now = _utcnow()
    if invitation.opened_at is None:
        invitation.opened_at = now
    if invitation.status in (InvitationStatus.CREATED, InvitationStatus.SENT, InvitationStatus.FAILED):
        invitation.status = InvitationStatus.OPENED
    invitation.updated_at = now
    await invitation.save()

    result = {
        "valid": True,
        "email": invitation.email,
        "name": invitee.name,
        "has_clerk_account": invitee.has_clerk_account,
        "user_id": str(invitee.id),
        "invitation_status": invitation.status.value,
    }

    txn = await Transaction.get(invitation.transaction_id)
    if txn:
        participant = next((p for p in txn.participants if p.user_id == str(invitee.id)), None)
        result["transaction"] = {
            "id": str(txn.id),
            "name": txn.name,
            "role": (participant.role.value if participant else invitation.role.value),
        }

    return result


@router.post("/invitations/{token}/accept")
@limiter.limit("20/minute")
async def accept_invitation(request: Request, token: str):
    """Accept an invitation and mark the participant active."""
    invitation, _payload = await _get_invitation_for_token(token)
    invitee = await UserProfile.get(invitation.invitee_user_id) if invitation.invitee_user_id else None
    if not invitee:
        invitee = await UserProfile.find_one({"email": invitation.email})
    if not invitee:
        raise HTTPException(status_code=404, detail="Invitation user not found")

    txn = await Transaction.get(invitation.transaction_id)
    if txn:
        participant = next((p for p in txn.participants if p.user_id == str(invitee.id)), None)
        if participant:
            participant.status = ParticipantStatus.ACTIVE
            participant.role = invitation.role
            txn.updated_at = _utcnow()
            await txn.save()

    now = _utcnow()
    invitee.last_login = now
    await invitee.save()

    invitation.status = InvitationStatus.ACCEPTED
    invitation.opened_at = invitation.opened_at or now
    invitation.accepted_at = invitation.accepted_at or now
    invitation.updated_at = now
    await invitation.save()

    return {
        "accepted": True,
        "user_id": str(invitee.id),
        "transaction_id": invitation.transaction_id,
    }


@router.post("/invitations/{token}/profile")
async def submit_profile_via_magic_link(token: str, req: ProfileSubmitRequest):
    """Update a placeholder profile using a valid invitation link."""
    invitation, _payload = await _get_invitation_for_token(token)
    invitee = await UserProfile.get(invitation.invitee_user_id) if invitation.invitee_user_id else None
    if not invitee:
        invitee = await UserProfile.find_one({"email": invitation.email})
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found")

    if req.name:
        invitee.name = req.name
    if req.phone:
        invitee.phone = req.phone
    if req.address:
        invitee.address = req.address

    user_type = _role_to_user_type(invitation.role)
    if user_type and user_type not in invitee.user_types:
        invitee.user_types.append(user_type)

    await invitee.save()

    if invitation.status == InvitationStatus.CREATED:
        invitation.status = InvitationStatus.OPENED
        invitation.opened_at = invitation.opened_at or _utcnow()
        invitation.updated_at = _utcnow()
        await invitation.save()

    return {
        "updated": True,
        "user_id": str(invitee.id),
        "name": invitee.name,
    }


@router.post("/invitations/{token}/upgrade")
@limiter.limit("10/minute")
async def upgrade_to_clerk(request: Request, token: str, req: UpgradeRequest):
    """Link a Clerk account to a placeholder user created via invitation."""
    invitation, _payload = await _get_invitation_for_token(token)
    if not _CLERK_USER_ID_RE.match(req.clerk_user_id):
        raise HTTPException(status_code=400, detail="Invalid Clerk user ID format")

    invitee = await UserProfile.get(invitation.invitee_user_id) if invitation.invitee_user_id else None
    if not invitee:
        invitee = await UserProfile.find_one({"email": invitation.email})
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found")

    if invitee.clerk_user_id and invitee.has_clerk_account:
        raise HTTPException(status_code=409, detail="Account already linked to a Clerk user")

    invitee.clerk_user_id = req.clerk_user_id
    invitee.has_clerk_account = True
    await invitee.save()

    invitation.status = InvitationStatus.ACCEPTED
    invitation.signed_token = None
    invitation.token_hash = None
    invitation.updated_at = _utcnow()
    await invitation.save()
    log.info("User %s upgraded to Clerk account %s", invitee.id, req.clerk_user_id)

    return {
        "upgraded": True,
        "user_id": str(invitee.id),
        "clerk_user_id": req.clerk_user_id,
    }
