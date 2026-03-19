"""Tests for auth._find_or_create_user() — the shared user lookup/creation/sync helper.

Covers:
- First-login user creation (name + email seeded from Clerk claims)
- Existing user: email synced, name NOT overwritten
- Org sync on every request
- has_clerk_account flag set on creation
- No unnecessary DB writes when nothing changed
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import Document

from db import UserProfile


@pytest.fixture(autouse=True)
def _patch_beanie_user():
    """Bypass Beanie collection init so UserProfile can be constructed and queried.

    Patches:
    1. get_settings — so UserProfile() can be instantiated without MongoDB
    2. Class-level field attributes — so Beanie query expressions like
       ``UserProfile.clerk_user_id == "x"`` don't raise AttributeError
    3. Document.save / Document.insert — so DB writes don't hit real MongoDB
    """
    mock_settings = MagicMock()
    mock_settings.pymongo_collection = MagicMock()

    _sentinel = object()
    _originals = {}
    _fields_to_patch = ["clerk_user_id", "email"]

    with (
        patch.object(UserProfile, "get_settings", return_value=mock_settings),
        patch.object(Document, "save", new_callable=AsyncMock) as mock_save,
        patch.object(Document, "insert", new_callable=AsyncMock) as mock_insert,
    ):
        for field_name in _fields_to_patch:
            _originals[field_name] = UserProfile.__dict__.get(field_name, _sentinel)
            setattr(UserProfile, field_name, field_name)
        try:
            yield {"save": mock_save, "insert": mock_insert}
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


class TestFindOrCreateUser:
    """Tests for the _find_or_create_user() helper in auth.py."""

    @pytest.mark.asyncio
    async def test_creates_user_on_first_login(self, _patch_beanie_user):
        """First login should create a new UserProfile with name + email from claims."""
        from auth import _find_or_create_user

        claims = {"sub": "user_abc", "email": "alice@example.com", "name": "Alice Smith"}

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=None):
            user = await _find_or_create_user("user_abc", claims)

            assert user.clerk_user_id == "user_abc"
            assert user.email == "alice@example.com"
            assert user.name == "Alice Smith"
            assert user.has_clerk_account is True
            _patch_beanie_user["insert"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_user_email_synced(self, _patch_beanie_user):
        """If Clerk email changed, it should be synced to MongoDB."""
        from auth import _find_or_create_user

        existing = UserProfile(
            clerk_user_id="user_abc",
            email="old@example.com",
            name="Alice Smith",
            has_clerk_account=True,
        )
        claims = {"sub": "user_abc", "email": "new@example.com", "name": "Alice Renamed"}

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            user = await _find_or_create_user("user_abc", claims)

            assert user.email == "new@example.com"
            _patch_beanie_user["save"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_user_name_not_overwritten(self, _patch_beanie_user):
        """MongoDB owns name — Clerk name changes should NOT overwrite it."""
        from auth import _find_or_create_user

        existing = UserProfile(
            clerk_user_id="user_abc",
            email="alice@example.com",
            name="Alice Professional Name",
            has_clerk_account=True,
        )
        claims = {"sub": "user_abc", "email": "alice@example.com", "name": "Alice Nickname"}

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            user = await _find_or_create_user("user_abc", claims)

            # Name should remain unchanged (MongoDB owns it)
            assert user.name == "Alice Professional Name"
            # No save needed — nothing changed
            _patch_beanie_user["save"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_existing_user_org_synced(self, _patch_beanie_user):
        """If Clerk org changed, org_id and org_name should be synced."""
        from auth import _find_or_create_user

        existing = UserProfile(
            clerk_user_id="user_abc",
            email="alice@example.com",
            has_clerk_account=True,
        )
        claims = {
            "sub": "user_abc",
            "email": "alice@example.com",
            "org_id": "org_new",
            "org_name": "New Brokerage",
        }

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            user = await _find_or_create_user("user_abc", claims)

            assert user.org_id == "org_new"
            assert user.org_name == "New Brokerage"
            _patch_beanie_user["save"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_has_clerk_account_flag_set(self, _patch_beanie_user):
        """Users created via Clerk should have has_clerk_account=True."""
        from auth import _find_or_create_user

        claims = {"sub": "user_xyz", "email": "bob@example.com", "name": "Bob"}

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=None):
            user = await _find_or_create_user("user_xyz", claims)

            assert user.has_clerk_account is True

    @pytest.mark.asyncio
    async def test_no_save_when_nothing_changed(self, _patch_beanie_user):
        """If all fields match, don't write to the DB unnecessarily."""
        from auth import _find_or_create_user

        existing = UserProfile(
            clerk_user_id="user_abc",
            email="alice@example.com",
            name="Alice",
            has_clerk_account=True,
            org_id="org_123",
            org_name="My Brokerage",
        )
        # Claims match existing state exactly
        claims = {
            "sub": "user_abc",
            "email": "alice@example.com",
            "name": "Alice Different",  # name is ignored for existing users
            "org_id": "org_123",
            "org_name": "My Brokerage",
        }

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            user = await _find_or_create_user("user_abc", claims)

            # Nothing changed, so save should NOT be called
            _patch_beanie_user["save"].assert_not_awaited()
            assert user.email == "alice@example.com"

    @pytest.mark.asyncio
    async def test_has_clerk_account_set_for_magic_link_user(self, _patch_beanie_user):
        """A magic-link user who later signs up with Clerk should get the flag set."""
        from auth import _find_or_create_user

        existing = UserProfile(
            clerk_user_id="user_abc",
            email="alice@example.com",
            has_clerk_account=False,  # Was a magic-link-only user
        )
        claims = {"sub": "user_abc", "email": "alice@example.com"}

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            user = await _find_or_create_user("user_abc", claims)

            assert user.has_clerk_account is True
            _patch_beanie_user["save"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_user_from_primary_email_address_claim(self, _patch_beanie_user):
        """Clerk session tokens may expose email via email_addresses instead of email."""
        from auth import _find_or_create_user

        claims = {
            "sub": "user_nested",
            "email_addresses": [
                {"id": "email_secondary", "email_address": "secondary@example.com"},
                {"id": "email_primary", "email_address": "primary@example.com"},
            ],
            "primary_email_address_id": "email_primary",
            "first_name": "Casey",
            "last_name": "Jones",
        }

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=None):
            user = await _find_or_create_user("user_nested", claims)

            assert user.email == "primary@example.com"
            assert user.name == "Casey Jones"
            _patch_beanie_user["insert"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_creates_user_with_unique_placeholder_when_email_missing(self, _patch_beanie_user):
        """Missing email claims should not create duplicate blank emails."""
        from auth import _find_or_create_user

        claims = {"sub": "user_no_email", "name": "No Email"}

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=None):
            user = await _find_or_create_user("user_no_email", claims)

            assert user.email == "user_no_email@users.clerk.local"
            assert user.name == "No Email"
            _patch_beanie_user["insert"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_existing_placeholder_email_is_replaced_when_claim_email_appears(self, _patch_beanie_user):
        """A placeholder email should be upgraded once Clerk exposes the real email."""
        from auth import _find_or_create_user

        existing = UserProfile(
            clerk_user_id="user_fixup",
            email="user_fixup@users.clerk.local",
            name="Taylor",
            has_clerk_account=True,
        )
        claims = {"sub": "user_fixup", "email_address": "taylor@example.com"}

        with patch.object(UserProfile, "find_one", new_callable=AsyncMock, return_value=existing):
            user = await _find_or_create_user("user_fixup", claims)

            assert user.email == "taylor@example.com"
            _patch_beanie_user["save"].assert_awaited_once()
