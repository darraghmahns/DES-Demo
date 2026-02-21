"""Tests for auth.py — HMAC OAuth state signing/verification and JWT basics.

Covers:
- sign_oauth_state / verify_oauth_state roundtrip
- Empty CLERK_SECRET_KEY guard (Issue #8)
- HMAC tamper detection (signature and payload)
- State expiry after _STATE_TTL (900s)
- Malformed / missing JWT rejection
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# HMAC state signing / verification roundtrip
# ---------------------------------------------------------------------------


class TestSignVerifyRoundtrip:
    """sign_oauth_state(uid) -> verify_oauth_state(state) should return uid."""

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    def test_roundtrip_returns_same_user_id(self):
        from auth import sign_oauth_state, verify_oauth_state

        user_id = "user_2nFGKP3abc123"
        state = sign_oauth_state(user_id)
        recovered = verify_oauth_state(state)

        assert recovered == user_id

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    def test_roundtrip_with_different_user_ids(self):
        from auth import sign_oauth_state, verify_oauth_state

        for uid in ["user_aaa", "user_bbb", "org_admin_xyz"]:
            state = sign_oauth_state(uid)
            assert verify_oauth_state(state) == uid

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    def test_state_format_is_base64_dot_signature(self):
        from auth import sign_oauth_state

        state = sign_oauth_state("user_123")
        parts = state.split(".")
        assert len(parts) == 2, "State must be payload_b64.signature"

        # payload_b64 should decode to JSON with uid and ts
        payload = json.loads(base64.urlsafe_b64decode(parts[0]))
        assert payload["uid"] == "user_123"
        assert isinstance(payload["ts"], int)


# ---------------------------------------------------------------------------
# HMAC empty key guard (Issue #8)
# ---------------------------------------------------------------------------


class TestEmptyKeyGuard:
    """When CLERK_SECRET_KEY is empty, both sign and verify must raise 500."""

    @patch("auth.CLERK_SECRET_KEY", "")
    def test_sign_raises_500_when_key_empty(self):
        from auth import sign_oauth_state

        with pytest.raises(HTTPException) as exc_info:
            sign_oauth_state("user_123")

        assert exc_info.value.status_code == 500
        assert "CLERK_SECRET_KEY" in exc_info.value.detail

    @patch("auth.CLERK_SECRET_KEY", "")
    def test_verify_raises_500_when_key_empty(self):
        from auth import verify_oauth_state

        with pytest.raises(HTTPException) as exc_info:
            verify_oauth_state("some.state")

        assert exc_info.value.status_code == 500
        assert "CLERK_SECRET_KEY" in exc_info.value.detail


# ---------------------------------------------------------------------------
# HMAC tamper detection
# ---------------------------------------------------------------------------


class TestTamperDetection:
    """Modified signature or payload must be rejected with 400."""

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    def test_modified_signature_raises_400(self):
        from auth import sign_oauth_state, verify_oauth_state

        state = sign_oauth_state("user_123")
        payload_b64, sig = state.split(".")

        # Flip the last character of the signature
        tampered_char = "a" if sig[-1] != "a" else "b"
        tampered_sig = sig[:-1] + tampered_char
        tampered_state = f"{payload_b64}.{tampered_sig}"

        with pytest.raises(HTTPException) as exc_info:
            verify_oauth_state(tampered_state)

        assert exc_info.value.status_code == 400
        assert "signature" in exc_info.value.detail.lower()

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    def test_modified_payload_raises_400(self):
        from auth import sign_oauth_state, verify_oauth_state

        state = sign_oauth_state("user_123")
        payload_b64, sig = state.split(".")

        # Replace payload with a different user id (re-encode, keep old sig)
        tampered_payload = json.dumps({"uid": "user_EVIL", "ts": int(time.time())})
        tampered_b64 = base64.urlsafe_b64encode(tampered_payload.encode()).decode()
        tampered_state = f"{tampered_b64}.{sig}"

        with pytest.raises(HTTPException) as exc_info:
            verify_oauth_state(tampered_state)

        assert exc_info.value.status_code == 400
        assert "signature" in exc_info.value.detail.lower()

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    def test_missing_dot_separator_raises_400(self):
        from auth import verify_oauth_state

        with pytest.raises(HTTPException) as exc_info:
            verify_oauth_state("nodothere")

        assert exc_info.value.status_code == 400

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    def test_garbage_base64_payload_raises_400(self):
        """Payload that is valid base64 but not valid JSON should raise 400."""
        from auth import verify_oauth_state

        import hashlib
        import hmac as hmac_mod

        # Create a valid HMAC for garbage (non-JSON) base64 payload
        garbage_b64 = base64.urlsafe_b64encode(b"not json at all").decode()
        sig = hmac_mod.new(
            "test-secret-key-abc123".encode(),
            garbage_b64.encode(),
            hashlib.sha256,
        ).hexdigest()
        crafted_state = f"{garbage_b64}.{sig}"

        with pytest.raises(HTTPException) as exc_info:
            verify_oauth_state(crafted_state)

        assert exc_info.value.status_code == 400
        assert "malformed" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# HMAC expiry
# ---------------------------------------------------------------------------


class TestStateExpiry:
    """State older than _STATE_TTL (900s) should be rejected."""

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    def test_expired_state_raises_400(self):
        from auth import sign_oauth_state, verify_oauth_state

        # Sign state at "current" time
        fake_now = 1_700_000_000.0
        with patch("auth.time") as mock_time:
            mock_time.time.return_value = fake_now
            state = sign_oauth_state("user_123")

        # Verify at fake_now + 901 seconds (just past the 900s TTL)
        with patch("auth.time") as mock_time:
            mock_time.time.return_value = fake_now + 901

            with pytest.raises(HTTPException) as exc_info:
                verify_oauth_state(state)

            assert exc_info.value.status_code == 400
            assert "expired" in exc_info.value.detail.lower()

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    def test_state_just_within_ttl_is_valid(self):
        from auth import sign_oauth_state, verify_oauth_state

        fake_now = 1_700_000_000.0
        with patch("auth.time") as mock_time:
            mock_time.time.return_value = fake_now
            state = sign_oauth_state("user_123")

        # Verify at exactly 900 seconds (boundary -- should still be valid)
        with patch("auth.time") as mock_time:
            mock_time.time.return_value = fake_now + 900

            uid = verify_oauth_state(state)
            assert uid == "user_123"


# ---------------------------------------------------------------------------
# JWT verification (basic rejection tests)
# ---------------------------------------------------------------------------


class TestJWTVerification:
    """Basic JWT rejection: malformed tokens and missing headers."""

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    @patch("auth.AUTH_ENABLED", True)
    @patch("auth.CLERK_JWKS_URL", "https://fake.clerk.dev/.well-known/jwks.json")
    def test_malformed_token_raises_401(self):
        from auth import verify_clerk_token

        # _get_jwks will be called, mock it to return a minimal JWKS
        mock_jwks = {"keys": []}
        with patch("auth._get_jwks", return_value=mock_jwks):
            with pytest.raises(HTTPException) as exc_info:
                verify_clerk_token("not.a.valid.jwt.token")

            assert exc_info.value.status_code == 401
            assert "invalid" in exc_info.value.detail.lower()

    @patch("auth.CLERK_SECRET_KEY", "test-secret-key-abc123")
    @patch("auth.AUTH_ENABLED", True)
    def test_completely_garbage_token_raises_401(self):
        from auth import verify_clerk_token

        mock_jwks = {"keys": []}
        with patch("auth._get_jwks", return_value=mock_jwks):
            with pytest.raises(HTTPException) as exc_info:
                verify_clerk_token("garbage")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.AUTH_ENABLED", True)
    async def test_missing_authorization_header_raises_401(self):
        from auth import get_current_user

        mock_request = MagicMock()
        mock_request.headers = {}  # No Authorization header

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request)

        assert exc_info.value.status_code == 401
        assert "authentication required" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    @patch("auth.AUTH_ENABLED", True)
    async def test_empty_bearer_token_raises_401(self):
        from auth import get_current_user

        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer "}

        # "Bearer " followed by empty string -- _extract_bearer returns ""
        # which is falsy, so get_current_user should raise 401
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("auth.AUTH_ENABLED", False)
    async def test_auth_disabled_returns_none(self):
        from auth import get_current_user

        mock_request = MagicMock()
        mock_request.headers = {}

        result = await get_current_user(mock_request)
        assert result is None
