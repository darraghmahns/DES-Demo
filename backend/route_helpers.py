"""Shared helpers used across multiple route modules.

Centralises _get_user_or_dev, _utcnow, and _normalize_email so that bug
fixes and behaviour changes only need to be made in one place.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from auth import AUTH_ENABLED
from db import UserProfile

log = logging.getLogger(__name__)


async def _get_user_or_dev(user) -> UserProfile:
    """Return the authenticated user, or create/return a dev user when auth is disabled."""
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
            log.info("Created dev user profile for local development")
        return dev_user

    raise HTTPException(status_code=401, detail="Authentication required")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return email.strip().lower()
