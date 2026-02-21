"""Tests for onboarding fields on UserProfile."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

from db import UserProfile


@pytest.fixture(autouse=True)
def _patch_beanie_user():
    """Bypass Beanie collection init so UserProfile can be constructed without MongoDB."""
    mock_settings = MagicMock()
    mock_settings.pymongo_collection = MagicMock()
    with patch.object(UserProfile, "get_settings", return_value=mock_settings):
        yield


class TestUserProfileOnboardingDefaults:
    """New UserProfile instances should have onboarding fields with correct defaults."""

    def test_onboarding_completed_defaults_false(self):
        user = UserProfile(clerk_user_id="test_123", email="test@example.com")
        assert user.onboarding_completed is False

    def test_onboarding_completed_at_defaults_none(self):
        user = UserProfile(clerk_user_id="test_123", email="test@example.com")
        assert user.onboarding_completed_at is None

    def test_onboarding_skipped_steps_defaults_empty(self):
        user = UserProfile(clerk_user_id="test_123", email="test@example.com")
        assert user.onboarding_skipped_steps == []

    def test_onboarding_skipped_steps_not_shared_across_instances(self):
        user_a = UserProfile(clerk_user_id="test_a", email="a@example.com")
        user_b = UserProfile(clerk_user_id="test_b", email="b@example.com")
        user_a.onboarding_skipped_steps.append("integration")
        assert user_b.onboarding_skipped_steps == []


class TestOnboardingStatusEndpoint:
    """GET /api/onboarding/status returns onboarding + integration state."""

    def _make_user(self, **overrides):
        """Build a mock UserProfile."""
        user = MagicMock()
        user.onboarding_completed = False
        user.onboarding_completed_at = None
        user.onboarding_skipped_steps = []
        user.dotloop_tokens = None
        user.docusign_tokens = None
        for k, v in overrides.items():
            setattr(user, k, v)
        return user

    @pytest.mark.asyncio
    async def test_new_user_returns_not_completed(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = self._make_user()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is False
        assert data["completed_at"] is None
        assert data["skipped_steps"] == []
        assert data["dotloop_connected"] is False
        assert data["docusign_connected"] is False

    @pytest.mark.asyncio
    async def test_completed_user_returns_completed(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        ts = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
        user = self._make_user(
            onboarding_completed=True,
            onboarding_completed_at=ts,
            onboarding_skipped_steps=["integration"],
        )

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        data = resp.json()
        assert data["completed"] is True
        assert data["skipped_steps"] == ["integration"]

    @pytest.mark.asyncio
    async def test_dotloop_connected_when_tokens_present(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        tokens = MagicMock()
        tokens.access_token = "tok_123"
        user = self._make_user(dotloop_tokens=tokens)

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.json()["dotloop_connected"] is True

    @pytest.mark.asyncio
    async def test_returns_401_when_no_auth(self):
        """With AUTH_ENABLED, missing token should 401."""
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient
        from fastapi import HTTPException

        def raise_401():
            raise HTTPException(status_code=401, detail="Auth required")

        app.dependency_overrides[get_current_user] = raise_401
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 401


class TestOnboardingCompleteEndpoint:
    """PATCH /api/onboarding/complete marks onboarding done."""

    @pytest.mark.asyncio
    async def test_marks_completed(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = MagicMock()
        user.onboarding_completed = False
        user.onboarding_completed_at = None
        user.onboarding_skipped_steps = []
        user.save = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/complete",
                    json={"skipped_steps": ["integration"]},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        assert user.onboarding_completed is True
        assert user.onboarding_completed_at is not None
        assert user.onboarding_skipped_steps == ["integration"]
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_skipped_steps(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = MagicMock()
        user.onboarding_completed = False
        user.onboarding_completed_at = None
        user.onboarding_skipped_steps = []
        user.save = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/complete",
                    json={"skipped_steps": []},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is True
        assert user.onboarding_skipped_steps == []

    @pytest.mark.asyncio
    async def test_idempotent_when_already_completed(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        ts = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
        user = MagicMock()
        user.onboarding_completed = True
        user.onboarding_completed_at = ts
        user.onboarding_skipped_steps = ["extraction"]
        user.save = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/complete",
                    json={"skipped_steps": []},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        # Should succeed but not overwrite the original timestamp
        assert resp.status_code == 200
        assert user.onboarding_completed_at == ts
