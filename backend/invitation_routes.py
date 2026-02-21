"""Magic link invitation API routes for D.E.S.

Handles generating invitations, validating magic links, accepting invitations,
submitting profile data via magic link, and upgrading to a Clerk account.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import (
    AUTH_ENABLED,
    generate_magic_link_token,
    get_current_user,
    sign_magic_link,
    verify_magic_link,
)
from db import Transaction, UserProfile
from schemas import (
    ParticipantRole,
    ParticipantStatus,
    UserType,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class CreateInvitationRequest(BaseModel):
    email: str
    role: ParticipantRole
    transaction_id: str
    name: Optional[str] = None


class ProfileSubmitRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[dict] = None


class UpgradeRequest(BaseModel):
    clerk_user_id: str


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("")
async def create_invitation(
    req: CreateInvitationRequest,
    user=Depends(get_current_user),
):
    """Generate a magic link invitation for a participant.

    Creates or finds the user by email, adds them to the transaction,
    stores the magic link token on their profile, and returns the signed token.
    """
    u = await _get_user_or_dev(user)

    # Verify the transaction exists and user has access
    txn = await Transaction.get(req.transaction_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if txn.created_by != str(u.id):
        raise HTTPException(status_code=403, detail="Only the creator can send invitations")

    # Find or create participant user
    invitee = await UserProfile.find_one(UserProfile.email == req.email)
    if not invitee:
        invitee = UserProfile(
            email=req.email,
            name=req.name or "",
            has_clerk_account=False,
        )
        await invitee.insert()
        log.info("Created placeholder user for invitation: %s", req.email)

    # Generate and store magic link token
    token = generate_magic_link_token()
    invitee.magic_link_token = token
    invitee.magic_link_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    await invitee.save()

    # Add to transaction if not already present
    pid = str(invitee.id)
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
    else:
        from schemas import TransactionParticipant
        txn.participants.append(TransactionParticipant(
            user_id=pid,
            role=req.role,
            status=ParticipantStatus.INVITED,
            added_at=datetime.now(timezone.utc),
            added_by=str(u.id),
        ))

    txn.updated_at = datetime.now(timezone.utc)
    await txn.save()

    # Sign the magic link
    signed_token = sign_magic_link(token, req.email, req.transaction_id)

    return {
        "signed_token": signed_token,
        "email": req.email,
        "transaction_id": req.transaction_id,
        "role": req.role.value,
        "expires_at": invitee.magic_link_expires.isoformat(),
    }


@router.get("/{token}/validate")
async def validate_invitation(token: str):
    """Validate a magic link token and return invitation details.

    This is the first endpoint called when a user clicks a magic link.
    No auth required — the token itself is the credential.
    """
    payload = verify_magic_link(token)
    email = payload.get("email")
    txn_id = payload.get("txn_id")

    invitee = await UserProfile.find_one(UserProfile.email == email)
    if not invitee:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitee.magic_link_token != payload.get("token"):
        raise HTTPException(status_code=401, detail="Invalid or used magic link")

    if invitee.magic_link_expires and invitee.magic_link_expires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Magic link expired")

    result = {
        "valid": True,
        "email": email,
        "name": invitee.name,
        "has_clerk_account": invitee.has_clerk_account,
        "user_id": str(invitee.id),
    }

    if txn_id:
        txn = await Transaction.get(txn_id)
        if txn:
            participant = next(
                (p for p in txn.participants if p.user_id == str(invitee.id)),
                None,
            )
            result["transaction"] = {
                "id": str(txn.id),
                "name": txn.name,
                "role": participant.role.value if participant else None,
            }

    return result


@router.post("/{token}/accept")
async def accept_invitation(token: str):
    """Accept an invitation and activate the participant in the transaction.

    No auth required — the magic link token is the credential.
    """
    payload = verify_magic_link(token)
    email = payload.get("email")
    txn_id = payload.get("txn_id")

    invitee = await UserProfile.find_one(UserProfile.email == email)
    if not invitee:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitee.magic_link_token != payload.get("token"):
        raise HTTPException(status_code=401, detail="Invalid or used magic link")

    # Activate in transaction
    if txn_id:
        txn = await Transaction.get(txn_id)
        if txn:
            participant = next(
                (p for p in txn.participants if p.user_id == str(invitee.id)),
                None,
            )
            if participant:
                participant.status = ParticipantStatus.ACTIVE
                txn.updated_at = datetime.now(timezone.utc)
                await txn.save()

    # Update last login
    invitee.last_login = datetime.now(timezone.utc)
    await invitee.save()

    return {
        "accepted": True,
        "user_id": str(invitee.id),
        "transaction_id": txn_id,
    }


@router.post("/{token}/profile")
async def submit_profile_via_magic_link(
    token: str,
    req: ProfileSubmitRequest,
):
    """Submit profile data via a magic link (no Clerk account needed).

    Used during the invitation onboarding flow.
    """
    payload = verify_magic_link(token)
    email = payload.get("email")
    txn_id = payload.get("txn_id")

    invitee = await UserProfile.find_one(UserProfile.email == email)
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found")

    if invitee.magic_link_token != payload.get("token"):
        raise HTTPException(status_code=401, detail="Invalid or used magic link")

    # Update profile fields
    if req.name:
        invitee.name = req.name
    if req.phone:
        invitee.phone = req.phone
    if req.address:
        invitee.address = req.address

    # Auto-assign role based on transaction participation
    if txn_id:
        txn = await Transaction.get(txn_id)
        if txn:
            participant = next(
                (p for p in txn.participants if p.user_id == str(invitee.id)),
                None,
            )
            if participant:
                role_map = {
                    ParticipantRole.BUYER: UserType.BUYER,
                    ParticipantRole.SELLER: UserType.SELLER,
                    ParticipantRole.LISTING_AGENT: UserType.AGENT,
                    ParticipantRole.BUYING_AGENT: UserType.AGENT,
                    ParticipantRole.LOAN_OFFICER: UserType.LOAN_OFFICER,
                }
                user_type = role_map.get(participant.role)
                if user_type and user_type not in invitee.user_types:
                    invitee.user_types.append(user_type)

    await invitee.save()

    return {
        "updated": True,
        "user_id": str(invitee.id),
        "name": invitee.name,
    }


@router.post("/{token}/upgrade")
async def upgrade_to_clerk(
    token: str,
    req: UpgradeRequest,
):
    """Link a Clerk account to a magic-link-only profile.

    Called after the user creates a Clerk account during onboarding.
    Consumes the magic link token.
    """
    payload = verify_magic_link(token)
    email = payload.get("email")

    invitee = await UserProfile.find_one(UserProfile.email == email)
    if not invitee:
        raise HTTPException(status_code=404, detail="User not found")

    if invitee.magic_link_token != payload.get("token"):
        raise HTTPException(status_code=401, detail="Invalid or used magic link")

    # Link Clerk account
    invitee.clerk_user_id = req.clerk_user_id
    invitee.has_clerk_account = True

    # Consume the magic link (one-time use for upgrade)
    invitee.magic_link_token = None
    invitee.magic_link_expires = None

    await invitee.save()
    log.info("User %s upgraded to Clerk account %s", invitee.id, req.clerk_user_id)

    return {
        "upgraded": True,
        "user_id": str(invitee.id),
        "clerk_user_id": req.clerk_user_id,
    }
