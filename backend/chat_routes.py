"""AI Chatbot Profile Builder API routes for D.E.S.

Conversational interface that collects profile data through natural dialogue.
The AI knows the user's profile schema, current completion state, and missing
fields — it asks targeted questions and extracts structured data from responses.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from auth import get_current_user, AUTH_ENABLED
from db import UserProfile
from schemas import (
    AgentProfile,
    BuyerProfile,
    LoanOfficerProfile,
    SellerProfile,
    UserType,
    PreApprovalStatus,
    OwnershipType,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["chat"])

# In-memory chat sessions (per user)
_chat_sessions: dict[str, list[dict]] = {}

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class ChatMessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ExtractedField(BaseModel):
    field: str
    value: str
    section: str  # "shared", "agent", "buyer", "seller", "loan_officer"


class ChatMessageResponse(BaseModel):
    reply: str
    session_id: str
    extracted_fields: list[ExtractedField] = Field(default_factory=list)
    profile_updated: bool = False
    completion_before: float = 0.0
    completion_after: float = 0.0


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


def _build_system_prompt(user: UserProfile, completion: dict) -> str:
    """Build a context-aware system prompt for the profile builder chatbot."""

    # Gather current profile state
    roles = [t.value for t in user.user_types] or ["none selected"]
    missing = completion.get("missing_fields", {})

    profile_state = f"""Current profile state:
- Name: {user.name or '(empty)'}
- Email: {user.email}
- Phone: {user.phone or '(empty)'}
- Address: {json.dumps(user.address) if user.address else '(empty)'}
- Roles: {', '.join(roles)}
- Overall completion: {completion.get('overall', 0):.0f}%"""

    # Add role-specific state
    if UserType.AGENT in user.user_types and user.agent_profile:
        ap = user.agent_profile
        profile_state += f"""

Agent profile:
- License number: {ap.license_number or '(empty)'}
- License state: {ap.license_state or '(empty)'}
- Brokerage: {ap.brokerage_name or '(empty)'}
- MLS ID: {ap.mls_id or '(empty)'}
- Areas served: {', '.join(ap.areas_served) if ap.areas_served else '(empty)'}"""

    if UserType.BUYER in user.user_types and user.buyer_profile:
        bp = user.buyer_profile
        profile_state += f"""

Buyer profile:
- Pre-approval status: {bp.pre_approval_status.value if bp.pre_approval_status else '(empty)'}
- Pre-approval amount: {bp.pre_approval_amount or '(empty)'}
- Pre-approval lender: {bp.pre_approval_lender or '(empty)'}
- Budget min: {bp.purchase_budget_min or '(empty)'}
- Budget max: {bp.purchase_budget_max or '(empty)'}
- First-time buyer: {bp.first_time_buyer if bp.first_time_buyer is not None else '(empty)'}
- Employment status: {bp.employment_status or '(empty)'}
- Employer: {bp.employer_name or '(empty)'}
- Annual income: {bp.annual_income or '(empty)'}"""

    if UserType.SELLER in user.user_types and user.seller_profile:
        sp = user.seller_profile
        profile_state += f"""

Seller profile:
- Property addresses: {json.dumps(sp.property_addresses) if sp.property_addresses else '(empty)'}
- Ownership type: {sp.ownership_type.value if sp.ownership_type else '(empty)'}"""

    if UserType.LOAN_OFFICER in user.user_types and user.loan_officer_profile:
        lo = user.loan_officer_profile
        profile_state += f"""

Loan officer profile:
- NMLS ID: {lo.nmls_id or '(empty)'}
- Company: {lo.company_name or '(empty)'}
- Company NMLS: {lo.company_nmls or '(empty)'}
- License states: {', '.join(lo.license_states) if lo.license_states else '(empty)'}
- Loan types: {', '.join(lo.loan_types_offered) if lo.loan_types_offered else '(empty)'}
- Contact preference: {lo.contact_preference or '(empty)'}"""

    # Missing fields summary
    missing_summary = ""
    for section, fields in missing.items():
        if fields:
            missing_summary += f"\n- {section}: {', '.join(fields)}"

    return f"""You are D.E.S. Profile Assistant, a friendly AI that helps users complete their real estate profile through natural conversation.

{profile_state}

Missing fields:{missing_summary if missing_summary else ' None — profile is complete!'}

INSTRUCTIONS:
1. Ask about missing fields one or two at a time in a natural, conversational way
2. When the user provides information, extract it and include a JSON block in your response
3. If no roles are selected yet, ask what role(s) they have (buyer, seller, agent, loan officer)
4. Prioritize the most important missing fields first (name, phone, then role-specific)
5. Be concise — keep responses under 3 sentences plus the JSON block
6. When all fields are complete, congratulate them and suggest they review their profile

EXTRACTION FORMAT:
When you extract data from the user's response, append a JSON block at the END of your message like this:
```json
{{"extracted": [{{"field": "name", "value": "Jane Doe", "section": "shared"}}, {{"field": "phone", "value": "555-123-4567", "section": "shared"}}]}}
```

Valid sections: "shared", "agent", "buyer", "seller", "loan_officer"

Valid fields per section:
- shared: name, phone, address (as JSON object with street, city, state, zip)
- agent: license_number, license_state, brokerage_name, mls_id, areas_served (as comma-separated list)
- buyer: pre_approval_status (none/pre_qualified/pre_approved/fully_approved), pre_approval_amount, pre_approval_lender, purchase_budget_min, purchase_budget_max, first_time_buyer (true/false), employment_status, employer_name, annual_income
- seller: ownership_type (sole/joint/trust/llc)
- loan_officer: nmls_id, company_name, company_nmls, license_states (as comma-separated list), loan_types_offered (as comma-separated list), contact_preference (email/phone/text)

ROLES:
If the user says they want to add a role, include it as:
```json
{{"extracted": [{{"field": "add_role", "value": "buyer", "section": "shared"}}]}}
```

Only output the JSON block when you actually extract new information. Do not output JSON if the user is just asking questions or chatting."""


def _get_completion(user: UserProfile) -> dict:
    """Get profile completion using the existing computation logic."""
    from profile_routes import _compute_completion
    result = _compute_completion(user)
    return {
        "overall": result.overall,
        "roles": result.roles,
        "missing_fields": result.missing_fields,
    }


def _apply_extracted_fields(
    user: UserProfile, fields: list[dict]
) -> list[ExtractedField]:
    """Apply extracted fields from chat to the user profile."""
    applied = []

    for f in fields:
        field_name = f.get("field", "")
        value = f.get("value", "")
        section = f.get("section", "shared")

        if not field_name or not value:
            continue

        try:
            if section == "shared":
                if field_name == "name":
                    user.name = value
                elif field_name == "phone":
                    user.phone = value
                elif field_name == "address":
                    user.address = json.loads(value) if isinstance(value, str) else value
                elif field_name == "add_role":
                    role = UserType(value)
                    if role not in user.user_types:
                        user.user_types.append(role)
                        # Initialize role profile
                        if role == UserType.AGENT and not user.agent_profile:
                            user.agent_profile = AgentProfile()
                        elif role == UserType.BUYER and not user.buyer_profile:
                            user.buyer_profile = BuyerProfile()
                        elif role == UserType.SELLER and not user.seller_profile:
                            user.seller_profile = SellerProfile()
                        elif role == UserType.LOAN_OFFICER and not user.loan_officer_profile:
                            user.loan_officer_profile = LoanOfficerProfile()
                else:
                    continue

            elif section == "agent" and user.agent_profile:
                ap = user.agent_profile
                if field_name == "license_number":
                    ap.license_number = value
                elif field_name == "license_state":
                    ap.license_state = value
                elif field_name == "brokerage_name":
                    ap.brokerage_name = value
                elif field_name == "mls_id":
                    ap.mls_id = value
                elif field_name == "areas_served":
                    ap.areas_served = [s.strip() for s in value.split(",")]
                else:
                    continue

            elif section == "buyer" and user.buyer_profile:
                bp = user.buyer_profile
                if field_name == "pre_approval_status":
                    bp.pre_approval_status = PreApprovalStatus(value)
                elif field_name == "pre_approval_amount":
                    bp.pre_approval_amount = float(str(value).replace(",", "").replace("$", ""))
                elif field_name == "pre_approval_lender":
                    bp.pre_approval_lender = value
                elif field_name == "purchase_budget_min":
                    bp.purchase_budget_min = float(str(value).replace(",", "").replace("$", ""))
                elif field_name == "purchase_budget_max":
                    bp.purchase_budget_max = float(str(value).replace(",", "").replace("$", ""))
                elif field_name == "first_time_buyer":
                    bp.first_time_buyer = str(value).lower() in ("true", "yes", "1")
                elif field_name == "employment_status":
                    bp.employment_status = value
                elif field_name == "employer_name":
                    bp.employer_name = value
                elif field_name == "annual_income":
                    bp.annual_income = float(str(value).replace(",", "").replace("$", ""))
                else:
                    continue

            elif section == "seller" and user.seller_profile:
                sp = user.seller_profile
                if field_name == "ownership_type":
                    sp.ownership_type = OwnershipType(value)
                else:
                    continue

            elif section == "loan_officer" and user.loan_officer_profile:
                lo = user.loan_officer_profile
                if field_name == "nmls_id":
                    lo.nmls_id = value
                elif field_name == "company_name":
                    lo.company_name = value
                elif field_name == "company_nmls":
                    lo.company_nmls = value
                elif field_name == "license_states":
                    lo.license_states = [s.strip() for s in value.split(",")]
                elif field_name == "loan_types_offered":
                    lo.loan_types_offered = [s.strip() for s in value.split(",")]
                elif field_name == "contact_preference":
                    lo.contact_preference = value
                else:
                    continue
            else:
                continue

            applied.append(ExtractedField(
                field=field_name, value=str(value), section=section,
            ))

        except Exception as e:
            log.warning("Failed to apply field %s.%s = %r: %s", section, field_name, value, e)

    return applied


def _parse_extracted_json(reply: str) -> list[dict]:
    """Parse the extracted fields JSON block from the AI response."""
    # Look for ```json ... ``` block
    import re
    pattern = r'```json\s*(\{.*?\})\s*```'
    match = re.search(pattern, reply, re.DOTALL)
    if not match:
        return []

    try:
        data = json.loads(match.group(1))
        return data.get("extracted", [])
    except (json.JSONDecodeError, AttributeError):
        return []


def _clean_reply(reply: str) -> str:
    """Remove the JSON extraction block from the reply shown to the user."""
    import re
    return re.sub(r'\s*```json\s*\{.*?\}\s*```\s*', '', reply, flags=re.DOTALL).strip()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat(
    req: ChatMessageRequest,
    user=Depends(get_current_user),
):
    """Send a message to the profile builder chatbot.

    The AI responds conversationally, extracts profile data from the user's
    message, and updates their profile in real-time.
    """
    u = await _get_user_or_dev(user)

    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Chat requires OPENAI_API_KEY to be configured",
        )

    # Get or create session
    session_id = req.session_id or f"chat-{uuid.uuid4().hex[:12]}"
    uid = str(u.id)

    if session_id not in _chat_sessions:
        _chat_sessions[session_id] = []

    history = _chat_sessions[session_id]

    # Compute completion before
    completion_before = _get_completion(u)

    # Build system prompt with current profile state
    system_prompt = _build_system_prompt(u, completion_before)

    # Build messages for OpenAI
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": req.message})

    # Call OpenAI
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.7,
        max_tokens=1024,
    )

    raw_reply = response.choices[0].message.content or ""

    # Parse extracted fields
    extracted_raw = _parse_extracted_json(raw_reply)
    clean_reply = _clean_reply(raw_reply)

    # Apply extracted fields to profile
    applied = []
    profile_updated = False
    if extracted_raw:
        applied = _apply_extracted_fields(u, extracted_raw)
        if applied:
            await u.save()
            profile_updated = True

    # Refresh completion
    u = await UserProfile.get(str(u.id))
    completion_after = _get_completion(u)

    # Save to session history
    history.append({"role": "user", "content": req.message})
    history.append({"role": "assistant", "content": raw_reply})

    return ChatMessageResponse(
        reply=clean_reply,
        session_id=session_id,
        extracted_fields=applied,
        profile_updated=profile_updated,
        completion_before=completion_before.get("overall", 0),
        completion_after=completion_after.get("overall", 0),
    )


@router.get("/chat/history")
async def get_chat_history(
    session_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    """Get chat history for a session."""
    await _get_user_or_dev(user)

    if not session_id:
        return {"messages": [], "session_id": None}

    history = _chat_sessions.get(session_id, [])

    return {
        "session_id": session_id,
        "messages": [
            {
                "role": msg["role"],
                "content": _clean_reply(msg["content"]) if msg["role"] == "assistant" else msg["content"],
            }
            for msg in history
        ],
    }
