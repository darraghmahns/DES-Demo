"""Tests for clerk_webhook.py — Clerk webhook handler for user sync.

Covers:
- Svix signature verification (valid and invalid)
- user.updated event: email sync, org sync, name NOT synced
- user.deleted event: soft-delete
- Unknown event: 200 OK (no-op)
- Unknown user in webhook: 200 OK (no error)
- Webhook not configured: 501
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import Document
from fastapi import HTTPException

from db import UserProfile


@pytest.fixture(autouse=True)
def _patch_beanie_user():
    """Bypass Beanie collection init so UserProfile can be constructed and queried.

    Patches:
    1. get_settings — so UserProfile() can be instantiated without MongoDB
    2. Class-level field attributes — so Beanie query expressions like
       ``UserProfile.clerk_user_id == "x"`` don't raise AttributeError
    3. Document.save — so DB writes don't hit real MongoDB
    """
    mock_settings = MagicMock()
    mock_settings.pymongo_collection = MagicMock()

    _sentinel = object()
    _originals = {}
    _fields_to_patch = ["clerk_user_id", "email"]

    with (
        patch.object(UserProfile, "get_settings", return_value=mock_settings),
        patch.object(Document, "save", new_callable=AsyncMock) as mock_save,
    ):
        for field_name in _fields_to_patch:
            _originals[field_name] = UserProfile.__dict__.get(field_name, _sentinel)
            setattr(UserProfile, field_name, field_name)
        try:
            yield {"save": mock_save}
        finally:
            for field_name in _fields_to_patch:
                orig = _originals[field_name]
                if orig is _sentinel:
                    try:
                        delattr(UserProfile, field_name)
                    except AttributeError:
                        pass
                else:
                    setattr(UserProfile, field_name, orig)


class TestClerkWebhookSignature:
    """Webhook signature verification tests."""

    @pytest.mark.asyncio
    @patch("clerk_webhook.CLERK_WEBHOOK_SECRET", "whsec_test123")
    async def test_valid_signature_accepted(self):
        """A valid Svix signature should pass verification and return 200."""
        from clerk_webhook import handle_clerk_webhook

        payload = {"type": "user.updated", "data": {"id": "user_abc"}}
        body = json.dumps(payload).encode()

        mock_request = MagicMock()
        mock_request.headers = {"svix-id": "msg_123", "svix-timestamp": "1234567890", "svix-signature": "v1,test"}
        mock_request.body = AsyncMock(return_value=body)

        with patch("clerk_webhook.Webhook") as MockWebhook:
            mock_wh = MagicMock()
            mock_wh.verify.return_value = payload
            MockWebhook.return_value = mock_wh

            with patch("clerk_webhook._handle_user_updated", new_callable=AsyncMock) as mock_handler:
                result = await handle_clerk_webhook(mock_request)

                assert result == {"received": True}
                mock_wh.verify.assert_called_once_with(body, dict(mock_request.headers))
                mock_handler.assert_awaited_once_with({"id": "user_abc"})

    @pytest.mark.asyncio
    @patch("clerk_webhook.CLERK_WEBHOOK_SECRET", "whsec_test123")
    async def test_invalid_signature_returns_401(self):
        """An invalid Svix signature should raise 401."""
        from clerk_webhook import handle_clerk_webhook
        from svix.webhooks import WebhookVerificationError

        mock_request = MagicMock()
        mock_request.headers = {"svix-id": "msg_123"}
        mock_request.body = AsyncMock(return_value=b'{"type":"user.updated"}')

        with patch("clerk_webhook.Webhook") as MockWebhook:
            mock_wh = MagicMock()
            mock_wh.verify.side_effect = WebhookVerificationError("bad sig")
            MockWebhook.return_value = mock_wh

            with pytest.raises(HTTPException) as exc_info:
                await handle_clerk_webhook(mock_request)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    @patch("clerk_webhook.CLERK_WEBHOOK_SECRET", "")
    async def test_webhook_not_configured_returns_501(self):
        """If CLERK_WEBHOOK_SECRET is empty, should return 501."""
        from clerk_webhook import handle_clerk_webhook

        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.body = AsyncMock(return_value=b"{}")

        with pytest.raises(HTTPException) as exc_info:
            await handle_clerk_webhook(mock_request)

        assert exc_info.value.status_code == 501


class TestUserUpdatedEvent:
    """Tests for user.updated webhook event handling."""

    @pytest.mark.asyncio
    async def test_syncs_email(self, _patch_beanie_user):
        """user.updated should sync a changed email."""
        from clerk_webhook import _handle_user_updated

        existing = UserProfile(
            clerk_user_id="user_abc",
            email="old@example.com",
            name="Alice",
            has_clerk_account=True,
        )

        data = {
            "id": "user_abc",
            "email_addresses": [{"email_address": "new@example.com"}],
        }

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            await _handle_user_updated(data)

            assert existing.email == "new@example.com"
            _patch_beanie_user["save"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_does_not_sync_name(self, _patch_beanie_user):
        """user.updated should NOT overwrite name (MongoDB owns name)."""
        from clerk_webhook import _handle_user_updated

        existing = UserProfile(
            clerk_user_id="user_abc",
            email="alice@example.com",
            name="Alice Professional",
            has_clerk_account=True,
        )

        # Clerk sends a name change, but our handler doesn't touch name
        data = {
            "id": "user_abc",
            "first_name": "Alice",
            "last_name": "Nickname",
            "email_addresses": [{"email_address": "alice@example.com"}],
        }

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            await _handle_user_updated(data)

            # Name unchanged
            assert existing.name == "Alice Professional"
            # No save — email didn't change either
            _patch_beanie_user["save"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_user_no_error(self):
        """user.updated for an unknown clerk_id should return without error."""
        from clerk_webhook import _handle_user_updated

        data = {
            "id": "user_unknown",
            "email_addresses": [{"email_address": "nobody@example.com"}],
        }

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=None):
            # Should not raise
            await _handle_user_updated(data)

    @pytest.mark.asyncio
    async def test_syncs_org(self, _patch_beanie_user):
        """user.updated should sync org_id and org_name from organization_memberships."""
        from clerk_webhook import _handle_user_updated

        existing = UserProfile(
            clerk_user_id="user_abc",
            email="alice@example.com",
            name="Alice",
            has_clerk_account=True,
        )

        data = {
            "id": "user_abc",
            "email_addresses": [{"email_address": "alice@example.com"}],
            "organization_memberships": [
                {"organization": {"id": "org_new", "name": "New Brokerage"}}
            ],
        }

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            await _handle_user_updated(data)

            assert existing.org_id == "org_new"
            assert existing.org_name == "New Brokerage"
            _patch_beanie_user["save"].assert_awaited_once()


class TestUserDeletedEvent:
    """Tests for user.deleted webhook event handling."""

    @pytest.mark.asyncio
    async def test_soft_deletes_user(self, _patch_beanie_user):
        """user.deleted should clear clerk_user_id and set has_clerk_account=False."""
        from clerk_webhook import _handle_user_deleted

        existing = UserProfile(
            clerk_user_id="user_abc",
            email="alice@example.com",
            name="Alice",
            has_clerk_account=True,
        )

        data = {"id": "user_abc"}

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            await _handle_user_deleted(data)

            assert existing.clerk_user_id is None
            assert existing.has_clerk_account is False
            _patch_beanie_user["save"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_user_no_error(self):
        """user.deleted for an unknown clerk_id should return without error."""
        from clerk_webhook import _handle_user_deleted

        data = {"id": "user_unknown"}

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=None):
            # Should not raise
            await _handle_user_deleted(data)


class TestUnknownEvent:
    """Tests for unhandled webhook event types."""

    @pytest.mark.asyncio
    @patch("clerk_webhook.CLERK_WEBHOOK_SECRET", "whsec_test123")
    async def test_unknown_event_returns_200(self):
        """Unrecognized event types should return 200 (no retry)."""
        from clerk_webhook import handle_clerk_webhook

        payload = {"type": "organization.created", "data": {"id": "org_xyz"}}
        body = json.dumps(payload).encode()

        mock_request = MagicMock()
        mock_request.headers = {"svix-id": "msg_456"}
        mock_request.body = AsyncMock(return_value=body)

        with patch("clerk_webhook.Webhook") as MockWebhook:
            mock_wh = MagicMock()
            mock_wh.verify.return_value = payload
            MockWebhook.return_value = mock_wh

            result = await handle_clerk_webhook(mock_request)
            assert result == {"received": True}
