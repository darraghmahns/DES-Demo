"""Invitation delivery helpers.

Resend is the default delivery provider. If not configured, callers can still
create invitations and share the returned invite URL manually.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from html import escape

import httpx


FRONTEND_URL = os.getenv("FRONTEND_URL", "").rstrip("/")
DEFAULT_FRONTEND_URL = FRONTEND_URL or "http://localhost:5173"
RESEND_API_URL = "https://api.resend.com/emails"


@dataclass
class InvitationDeliveryResult:
    delivered: bool
    provider: str | None = None
    provider_message_id: str | None = None
    error: str | None = None


def build_invite_url(signed_token: str) -> str:
    """Build the public invite landing URL for a signed invitation token."""
    return f"{DEFAULT_FRONTEND_URL}/invite/{signed_token}"


async def send_invitation_email(
    *,
    to_email: str,
    invitee_name: str | None,
    transaction_name: str,
    role_label: str,
    invite_url: str,
) -> InvitationDeliveryResult:
    """Deliver a transaction invite email through Resend when configured."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    from_email = (
        os.getenv("INVITATION_FROM_EMAIL", "").strip()
        or os.getenv("RESEND_FROM_EMAIL", "").strip()
    )

    if not api_key or not from_email:
        return InvitationDeliveryResult(delivered=False)

    greeting = escape(invitee_name.strip()) if invitee_name and invitee_name.strip() else "there"
    safe_txn_name = escape(transaction_name)
    safe_role = escape(role_label)
    safe_invite_url = escape(invite_url)

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": f"You're invited to {safe_txn_name} in Comparari",
        "html": (
            f"<p>Hi {greeting},</p>"
            f"<p>You were invited to join <strong>{safe_txn_name}</strong> as <strong>{safe_role}</strong>.</p>"
            f"<p><a href=\"{safe_invite_url}\">Open your invitation</a></p>"
            "<p>If the button does not work, copy and paste this URL into your browser:</p>"
            f"<p>{safe_invite_url}</p>"
        ),
        "text": (
            f"Hi {invitee_name or 'there'},\n\n"
            f"You were invited to join {transaction_name} as {role_label}.\n\n"
            f"Open your invitation: {invite_url}\n"
        ),
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(RESEND_API_URL, json=payload, headers=headers)

    if resp.status_code >= 400:
        try:
            error_payload = resp.json()
            detail = (
                error_payload.get("message")
                or error_payload.get("error")
                or str(error_payload)
            )
        except Exception:
            detail = resp.text.strip() or f"HTTP {resp.status_code}"
        return InvitationDeliveryResult(
            delivered=False,
            provider="resend",
            error=detail,
        )

    data = resp.json()
    return InvitationDeliveryResult(
        delivered=True,
        provider="resend",
        provider_message_id=data.get("id"),
    )
