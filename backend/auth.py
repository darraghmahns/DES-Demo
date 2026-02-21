"""Clerk JWT authentication + magic link support for FastAPI.

If CLERK_SECRET_KEY is not set, auth is disabled — all endpoints work
without tokens (backward compatibility during development).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request

load_dotenv()

log = logging.getLogger(__name__)

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "")
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")
AUTH_ENABLED = bool(CLERK_SECRET_KEY)

# Cache the JWKS keys in memory (refreshed every 60 min)
_jwks_cache: dict = {}
_jwks_fetched_at: float = 0
_JWKS_TTL = 3600  # seconds


def _get_jwks() -> dict:
    """Fetch (or return cached) Clerk JWKS keyset."""
    global _jwks_cache, _jwks_fetched_at

    if _jwks_cache and (time.time() - _jwks_fetched_at < _JWKS_TTL):
        return _jwks_cache

    if not CLERK_JWKS_URL:
        raise HTTPException(status_code=500, detail="CLERK_JWKS_URL not configured")

    try:
        resp = httpx.get(CLERK_JWKS_URL, timeout=10.0)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = time.time()
        return _jwks_cache
    except Exception as e:
        log.error("Failed to fetch Clerk JWKS: %s", e)
        if _jwks_cache:
            return _jwks_cache  # stale cache better than nothing
        raise HTTPException(status_code=500, detail="Failed to fetch auth keys")


def verify_clerk_token(token: str) -> dict:
    """Decode and verify a Clerk JWT. Returns the decoded claims dict."""
    jwks = _get_jwks()
    try:
        jwks_client = jwt.PyJWKClient.__new__(jwt.PyJWKClient)
        jwks_client.jwk_set = jwt.PyJWKSet.from_dict(jwks)
        unverified_header = jwt.get_unverified_header(token)
        signing_key = jwks_client.jwk_set[unverified_header["kid"]]
    except Exception as e:
        log.warning("JWT key lookup failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        log.warning("JWT validation failed: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")


def _extract_bearer(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


async def get_current_user(request: Request):
    """FastAPI dependency — returns UserProfile or raises 401.

    When auth is disabled (no CLERK_SECRET_KEY), returns None so
    endpoints can check `if user:` to behave differently.
    """
    if not AUTH_ENABLED:
        return None

    token = _extract_bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    claims = verify_clerk_token(token)
    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Invalid token: no subject")

    from db import UserProfile

    user = await UserProfile.find_one(UserProfile.clerk_user_id == clerk_user_id)
    if not user:
        user = UserProfile(
            clerk_user_id=clerk_user_id,
            email=claims.get("email", ""),
            name=claims.get("name", ""),
            org_id=claims.get("org_id"),
            org_name=claims.get("org_name"),
            has_clerk_account=True,
        )
        await user.insert()
        log.info("Auto-created user %s (%s)", clerk_user_id, user.email)
    else:
        changed = False
        if claims.get("org_id") and user.org_id != claims.get("org_id"):
            user.org_id = claims["org_id"]
            user.org_name = claims.get("org_name")
            changed = True
        if claims.get("email") and user.email != claims.get("email"):
            user.email = claims["email"]
            changed = True
        if not user.has_clerk_account:
            user.has_clerk_account = True
            changed = True
        if changed:
            await user.save()

    return user


async def get_optional_user(request: Request):
    """Same as get_current_user but returns None instead of 401."""
    if not AUTH_ENABLED:
        return None

    token = _extract_bearer(request)
    if not token:
        return None

    try:
        claims = verify_clerk_token(token)
    except HTTPException:
        return None

    clerk_user_id = claims.get("sub")
    if not clerk_user_id:
        return None

    from db import UserProfile

    user = await UserProfile.find_one(UserProfile.clerk_user_id == clerk_user_id)
    if not user:
        user = UserProfile(
            clerk_user_id=clerk_user_id,
            email=claims.get("email", ""),
            name=claims.get("name", ""),
            org_id=claims.get("org_id"),
            org_name=claims.get("org_name"),
            has_clerk_account=True,
        )
        await user.insert()

    return user


# ---------------------------------------------------------------------------
# OAuth state parameter signing (ties OAuth flow to a specific user)
# ---------------------------------------------------------------------------

_STATE_TTL = 900  # 15 minutes


def sign_oauth_state(clerk_user_id: str) -> str:
    """Create a signed state parameter containing the user ID.

    Format: base64(json({uid, ts})).signature
    Uses CLERK_SECRET_KEY as HMAC key.
    """
    payload = json.dumps({"uid": clerk_user_id, "ts": int(time.time())})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(
        CLERK_SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_oauth_state(state: str) -> str:
    """Verify a signed state parameter and return the clerk_user_id.

    Raises HTTPException on invalid/expired state.
    """
    parts = state.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    payload_b64, sig = parts
    expected_sig = hmac.new(
        CLERK_SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=400, detail="Invalid OAuth state signature")

    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed OAuth state")

    ts = payload.get("ts", 0)
    if time.time() - ts > _STATE_TTL:
        raise HTTPException(status_code=400, detail="OAuth state expired")

    uid = payload.get("uid")
    if not uid:
        raise HTTPException(status_code=400, detail="OAuth state missing user ID")

    return uid


# ---------------------------------------------------------------------------
# Magic Link Token Generation & Validation
# ---------------------------------------------------------------------------

_MAGIC_LINK_TTL = 86400  # 24 hours
_MAGIC_LINK_SECRET = CLERK_SECRET_KEY or "dev-magic-link-secret"


def generate_magic_link_token() -> str:
    """Generate a cryptographically secure random token for magic links."""
    return secrets.token_urlsafe(48)


def sign_magic_link(token: str, email: str, transaction_id: Optional[str] = None) -> str:
    """Create a signed magic link payload.

    Format: base64(json({token, email, txn_id, ts})).signature
    """
    payload_dict: dict = {
        "token": token,
        "email": email,
        "ts": int(time.time()),
    }
    if transaction_id:
        payload_dict["txn_id"] = transaction_id

    payload = json.dumps(payload_dict)
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(
        _MAGIC_LINK_SECRET.encode(), payload_b64.encode(), hashlib.sha256,
    ).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_magic_link(signed_token: str) -> dict:
    """Verify a signed magic link and return the payload.

    Returns dict with: token, email, txn_id (optional), ts.
    Raises HTTPException on invalid/expired token.
    """
    parts = signed_token.split(".", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid magic link")

    payload_b64, sig = parts
    expected_sig = hmac.new(
        _MAGIC_LINK_SECRET.encode(), payload_b64.encode(), hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=400, detail="Invalid magic link signature")

    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed magic link")

    ts = payload.get("ts", 0)
    if time.time() - ts > _MAGIC_LINK_TTL:
        raise HTTPException(status_code=400, detail="Magic link expired")

    return payload


async def get_magic_link_user(request: Request):
    """FastAPI dependency — authenticate via magic link token in header or query.

    Looks for X-Magic-Token header or ?magic_token= query param.
    Returns UserProfile or raises 401.
    """
    token = request.headers.get("X-Magic-Token") or request.query_params.get("magic_token")
    if not token:
        raise HTTPException(status_code=401, detail="Magic link token required")

    payload = verify_magic_link(token)
    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Magic link missing email")

    from db import UserProfile

    user = await UserProfile.find_one(UserProfile.email == email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found for this magic link")

    # Verify the token matches what's stored on the user
    if user.magic_link_token != payload.get("token"):
        raise HTTPException(status_code=401, detail="Magic link token mismatch")

    if user.magic_link_expires and user.magic_link_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Magic link expired")

    return user
