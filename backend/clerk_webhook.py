"""Clerk webhook handler — syncs user identity changes from Clerk to MongoDB.

Handles:
- user.updated: Syncs email and org (NOT name — MongoDB owns name)
- user.deleted: Soft-deletes user (clears clerk_user_id, sets has_clerk_account=False)

Webhook signatures are verified using the Svix library (Clerk's delivery mechanism).
Configure in Clerk Dashboard: Settings > Webhooks > Add Endpoint.
"""

import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Request
from svix.webhooks import Webhook, WebhookVerificationError

load_dotenv()

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

CLERK_WEBHOOK_SECRET = os.getenv("CLERK_WEBHOOK_SECRET", "")


@router.post("/clerk")
async def handle_clerk_webhook(request: Request):
    """Process Clerk webhook events with Svix signature verification."""
    if not CLERK_WEBHOOK_SECRET:
        raise HTTPException(status_code=501, detail="Webhook not configured")

    headers = dict(request.headers)
    body = await request.body()

    try:
        wh = Webhook(CLERK_WEBHOOK_SECRET)
        payload = wh.verify(body, headers)
    except WebhookVerificationError:
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event_type = payload.get("type")
    data = payload.get("data", {})

    if event_type == "user.updated":
        await _handle_user_updated(data)
    elif event_type == "user.deleted":
        await _handle_user_deleted(data)
    # Unknown events -> 200 OK (no-op, prevents Clerk from retrying)

    return {"received": True}


async def _handle_user_updated(data: dict):
    """Sync email and org from Clerk. Does NOT touch name (MongoDB owns name)."""
    from db import UserProfile

    clerk_id = data.get("id")
    if not clerk_id:
        return

    user = await UserProfile.find_one(UserProfile.clerk_user_id == clerk_id)
    if not user:
        log.warning("Webhook user.updated for unknown clerk_id: %s", clerk_id)
        return

    changed = False

    # Sync email (Clerk owns email)
    email_addresses = data.get("email_addresses") or []
    if email_addresses:
        new_email = email_addresses[0].get("email_address")
        if new_email and new_email != user.email:
            user.email = new_email
            changed = True

    # Sync org if present
    org_memberships = data.get("organization_memberships") or []
    if org_memberships:
        org = org_memberships[0].get("organization", {})
        org_id = org.get("id")
        if org_id and org_id != user.org_id:
            user.org_id = org_id
            user.org_name = org.get("name")
            changed = True

    if changed:
        await user.save()
        log.info("Webhook synced user %s", clerk_id)


async def _handle_user_deleted(data: dict):
    """Soft-delete: clear Clerk association, keep profile data."""
    from db import UserProfile

    clerk_id = data.get("id")
    if not clerk_id:
        return

    user = await UserProfile.find_one(UserProfile.clerk_user_id == clerk_id)
    if not user:
        return

    user.clerk_user_id = None
    user.has_clerk_account = False
    await user.save()
    log.info("Webhook soft-deleted user for clerk_id: %s", clerk_id)
