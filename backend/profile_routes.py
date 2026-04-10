"""Profile management API routes for D.E.S.

Handles user profile CRUD, role management, profile completion tracking,
and user search/lookup.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user, AUTH_ENABLED
from route_helpers import _get_user_or_dev
from db import UserProfile
from schemas import (
    AgentProfile,
    BuyerProfile,
    LoanOfficerProfile,
    SellerProfile,
    UserType,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["profile"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class ProfileUpdateRequest(BaseModel):
    """Shared profile fields update."""
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[dict] = None


class AddRoleRequest(BaseModel):
    role: UserType


class ProfileCompletionResponse(BaseModel):
    overall: float
    roles: dict[str, float]
    missing_fields: dict[str, list[str]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_completion(user: UserProfile) -> ProfileCompletionResponse:
    """Compute profile completion percentage per role and overall."""
    shared_fields = ["name", "email", "phone", "address"]
    shared_filled = sum(1 for f in shared_fields if getattr(user, f, None))
    shared_total = len(shared_fields)

    role_completions: dict[str, float] = {}
    role_missing: dict[str, list[str]] = {}

    for user_type in user.user_types:
        profile_attr = f"{user_type.value}_profile"
        profile = getattr(user, profile_attr, None)
        if profile is None:
            role_completions[user_type.value] = 0.0
            role_missing[user_type.value] = [f"No {user_type.value} profile data"]
            continue

        fields = _role_tracked_fields(user_type)
        filled = 0
        missing = []
        for field_name, label in fields:
            val = getattr(profile, field_name, None)
            if val is not None and val != "" and val != []:
                filled += 1
            else:
                missing.append(label)

        pct = (filled / len(fields) * 100) if fields else 100.0
        role_completions[user_type.value] = round(pct, 1)
        role_missing[user_type.value] = missing

    # Overall: shared fields + average of role completions
    shared_pct = (shared_filled / shared_total * 100) if shared_total else 100.0
    if role_completions:
        roles_avg = sum(role_completions.values()) / len(role_completions)
        overall = round((shared_pct * 0.3 + roles_avg * 0.7), 1)
    else:
        overall = round(shared_pct * 0.3, 1)  # No roles = low completion

    shared_missing = [f for f in shared_fields if not getattr(user, f, None)]
    if shared_missing:
        role_missing["shared"] = shared_missing

    return ProfileCompletionResponse(
        overall=overall,
        roles=role_completions,
        missing_fields=role_missing,
    )


def _role_tracked_fields(user_type: UserType) -> list[tuple[str, str]]:
    """Return (field_name, label) pairs tracked for completion per role."""
    if user_type == UserType.AGENT:
        return [
            ("license_number", "License Number"),
            ("license_state", "License State"),
            ("brokerage_name", "Brokerage Name"),
            ("mls_id", "MLS ID"),
        ]
    elif user_type == UserType.BUYER:
        return [
            ("pre_approval_status", "Pre-Approval Status"),
            ("pre_approval_amount", "Pre-Approval Amount"),
            ("pre_approval_lender", "Pre-Approval Lender"),
            ("employment_status", "Employment Status"),
            ("employer_name", "Employer Name"),
            ("annual_income", "Annual Income"),
        ]
    elif user_type == UserType.SELLER:
        return [
            ("property_addresses", "Property Addresses"),
            ("ownership_type", "Ownership Type"),
        ]
    elif user_type == UserType.LOAN_OFFICER:
        return [
            ("nmls_id", "NMLS ID"),
            ("company_name", "Company Name"),
            ("license_states", "License States"),
            ("loan_types_offered", "Loan Types Offered"),
        ]
    return []


def _serialize_profile(user: UserProfile) -> dict:
    """Serialize UserProfile to a JSON-safe dict."""
    data = user.model_dump(mode="json")
    data["_id"] = str(user.id)
    return data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/profile")
async def get_profile(user=Depends(get_current_user)):
    """Get the current user's full profile."""
    u = await _get_user_or_dev(user)
    return _serialize_profile(u)


@router.put("/profile")
async def update_profile(body: ProfileUpdateRequest, user=Depends(get_current_user)):
    """Update shared profile fields (name, phone, address, photo)."""
    u = await _get_user_or_dev(user)

    if body.name is not None:
        u.name = body.name
    if body.phone is not None:
        u.phone = body.phone
    if body.address is not None:
        u.address = body.address

    await u.save()
    return _serialize_profile(u)


@router.put("/profile/agent")
async def update_agent_profile(body: AgentProfile, user=Depends(get_current_user)):
    """Update agent-specific profile fields."""
    u = await _get_user_or_dev(user)
    if UserType.AGENT not in u.user_types:
        raise HTTPException(status_code=400, detail="User does not have the agent role")
    u.agent_profile = body
    await u.save()
    return _serialize_profile(u)


@router.put("/profile/buyer")
async def update_buyer_profile(body: BuyerProfile, user=Depends(get_current_user)):
    """Update buyer-specific profile fields."""
    u = await _get_user_or_dev(user)
    if UserType.BUYER not in u.user_types:
        raise HTTPException(status_code=400, detail="User does not have the buyer role")
    u.buyer_profile = body
    await u.save()
    return _serialize_profile(u)


@router.put("/profile/seller")
async def update_seller_profile(body: SellerProfile, user=Depends(get_current_user)):
    """Update seller-specific profile fields."""
    u = await _get_user_or_dev(user)
    if UserType.SELLER not in u.user_types:
        raise HTTPException(status_code=400, detail="User does not have the seller role")
    u.seller_profile = body
    await u.save()
    return _serialize_profile(u)


@router.put("/profile/loan-officer")
async def update_loan_officer_profile(
    body: LoanOfficerProfile, user=Depends(get_current_user)
):
    """Update loan officer-specific profile fields."""
    u = await _get_user_or_dev(user)
    if UserType.LOAN_OFFICER not in u.user_types:
        raise HTTPException(status_code=400, detail="User does not have the loan_officer role")
    u.loan_officer_profile = body
    await u.save()
    return _serialize_profile(u)


@router.post("/profile/roles")
async def add_role(body: AddRoleRequest, user=Depends(get_current_user)):
    """Add a new role to the user's profile."""
    u = await _get_user_or_dev(user)

    if body.role in u.user_types:
        raise HTTPException(status_code=400, detail=f"User already has the {body.role.value} role")

    u.user_types.append(body.role)

    # Initialize the corresponding sub-document
    profile_attr = f"{body.role.value}_profile"
    if getattr(u, profile_attr, None) is None:
        defaults = {
            UserType.AGENT: AgentProfile,
            UserType.BUYER: BuyerProfile,
            UserType.SELLER: SellerProfile,
            UserType.LOAN_OFFICER: LoanOfficerProfile,
        }
        setattr(u, profile_attr, defaults[body.role]())

    await u.save()
    return _serialize_profile(u)


@router.delete("/profile/roles/{role}")
async def remove_role(role: UserType, user=Depends(get_current_user)):
    """Remove a role from the user's profile."""
    u = await _get_user_or_dev(user)

    if role not in u.user_types:
        raise HTTPException(status_code=400, detail=f"User does not have the {role.value} role")

    u.user_types.remove(role)
    # Keep the sub-document data in case they re-add the role
    await u.save()
    return _serialize_profile(u)


@router.get("/profile/completion")
async def get_profile_completion(user=Depends(get_current_user)):
    """Get profile completion percentage per role and overall."""
    u = await _get_user_or_dev(user)
    return _compute_completion(u)


@router.get("/users/{user_id}")
async def get_user_by_id(user_id: str, user=Depends(get_current_user)):
    """View another user's profile (filtered — no sensitive fields)."""
    await _get_user_or_dev(user)  # Require auth

    target = await UserProfile.get(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    data = _serialize_profile(target)
    # Remove sensitive fields
    for key in ("magic_link_token", "magic_link_expires", "dotloop_tokens", "docusign_tokens"):
        data.pop(key, None)
    return data


@router.get("/users/search")
async def search_users(email: str, user=Depends(get_current_user)):
    """Search users by email (for invitations)."""
    await _get_user_or_dev(user)  # Require auth

    results = await UserProfile.find(
        UserProfile.email == email
    ).to_list()

    return [
        {
            "_id": str(u.id),
            "email": u.email,
            "name": u.name,
            "user_types": [t.value for t in u.user_types],
        }
        for u in results
    ]
