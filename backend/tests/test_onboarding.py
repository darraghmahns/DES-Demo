"""Tests for onboarding fields on UserProfile."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

from db import UserProfile, OnboardingStepStatus, VALID_STEP_IDS


@pytest.fixture(autouse=True)
def _patch_beanie_user():
    """Bypass Beanie collection init so UserProfile can be constructed without MongoDB."""
    mock_settings = MagicMock()
    mock_settings.pymongo_collection = MagicMock()
    with patch.object(UserProfile, "get_settings", return_value=mock_settings):
        yield


@pytest.fixture(autouse=True)
def _reset_e2e_state():
    """Reset module-level e2e onboarding state between tests."""
    import server
    server._e2e_onboarding_reset = False
    server._e2e_onboarding_state = {}
    yield
    server._e2e_onboarding_reset = False
    server._e2e_onboarding_state = {}


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

    def test_onboarding_v2_defaults(self):
        user = UserProfile(clerk_user_id="test_123", email="test@example.com")
        assert user.onboarding_version == 1
        assert user.onboarding_step_statuses == []
        assert user.onboarding_current_step == 0

    def test_onboarding_v2_fields_not_shared(self):
        user_a = UserProfile(clerk_user_id="test_a", email="a@example.com")
        user_b = UserProfile(clerk_user_id="test_b", email="b@example.com")
        user_a.onboarding_step_statuses.append(
            OnboardingStepStatus(step_id="welcome", status="completed")
        )
        assert user_b.onboarding_step_statuses == []


def _make_v2_user(**overrides):
    """Build a mock UserProfile with v2 onboarding fields."""
    user = MagicMock()
    user.onboarding_completed = False
    user.onboarding_completed_at = None
    user.onboarding_skipped_steps = []
    user.dotloop_tokens = None
    user.docusign_tokens = None
    # v2 fields
    user.onboarding_version = 2
    user.onboarding_step_statuses = [
        OnboardingStepStatus(step_id=sid, status="pending", completed_at=None)
        for sid in VALID_STEP_IDS
    ]
    user.onboarding_current_step = 0
    user.save = AsyncMock()
    for k, v in overrides.items():
        setattr(user, k, v)
    return user


def _make_v1_user(**overrides):
    """Build a mock UserProfile with v1 onboarding fields (pre-migration)."""
    user = MagicMock()
    user.onboarding_completed = False
    user.onboarding_completed_at = None
    user.onboarding_skipped_steps = []
    user.dotloop_tokens = None
    user.docusign_tokens = None
    # v1 fields
    user.onboarding_version = 1
    user.onboarding_step_statuses = []
    user.onboarding_current_step = 0
    user.save = AsyncMock()
    for k, v in overrides.items():
        setattr(user, k, v)
    return user


class TestOnboardingStatusEndpoint:
    """GET /api/onboarding/status returns v2 onboarding + integration state."""

    @pytest.mark.asyncio
    async def test_new_v2_user_returns_not_completed(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = _make_v2_user()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2
        assert data["completed"] is False
        assert data["completed_at"] is None
        assert data["current_step"] == 0
        assert len(data["steps"]) == 6
        assert all(s["status"] == "pending" for s in data["steps"])
        assert data["dotloop_connected"] is False
        assert data["docusign_connected"] is False

    @pytest.mark.asyncio
    async def test_completed_v2_user_returns_completed(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        ts = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
        user = _make_v2_user(
            onboarding_completed=True,
            onboarding_completed_at=ts,
            onboarding_current_step=len(VALID_STEP_IDS),
            onboarding_step_statuses=[
                OnboardingStepStatus(step_id=sid, status="completed", completed_at=ts.isoformat())
                for sid in VALID_STEP_IDS
            ],
        )

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        data = resp.json()
        assert data["version"] == 2
        assert data["completed"] is True
        assert data["current_step"] == len(VALID_STEP_IDS)
        assert all(s["status"] == "completed" for s in data["steps"])

    @pytest.mark.asyncio
    async def test_v1_completed_user_migrates_to_v2(self):
        """v1 completed users should auto-migrate to v2 with all steps completed."""
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        ts = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
        user = _make_v1_user(
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
        assert data["version"] == 2
        assert data["completed"] is True
        # v1 completed user should have all steps marked completed
        assert all(s["status"] == "completed" for s in data["steps"])
        assert user.onboarding_version == 2
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_v1_midflow_user_starts_fresh_at_v2(self):
        """v1 mid-flow (not completed) users should start fresh at v2 step 0."""
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = _make_v1_user()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/onboarding/status")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        data = resp.json()
        assert data["version"] == 2
        assert data["completed"] is False
        assert data["current_step"] == 0
        assert all(s["status"] == "pending" for s in data["steps"])
        assert user.onboarding_version == 2
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dotloop_connected_when_tokens_present(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        tokens = MagicMock()
        tokens.access_token = "tok_123"
        user = _make_v2_user(dotloop_tokens=tokens)

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


class TestOnboardingStepEndpoint:
    """PATCH /api/onboarding/step marks individual steps."""

    @pytest.mark.asyncio
    async def test_complete_step(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = _make_v2_user()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/step",
                    json={"step_id": "welcome", "status": "completed"},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["version"] == 2
        # welcome is index 0 so current_step should advance to 1 (profile)
        assert data["current_step"] == 1
        welcome_step = next(s for s in data["steps"] if s["step_id"] == "welcome")
        assert welcome_step["status"] == "completed"
        assert welcome_step["completed_at"] is not None
        user.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skip_step(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = _make_v2_user()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/step",
                    json={"step_id": "welcome", "status": "skipped"},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        data = resp.json()
        welcome_step = next(s for s in data["steps"] if s["step_id"] == "welcome")
        assert welcome_step["status"] == "skipped"
        assert welcome_step["completed_at"] is None

    @pytest.mark.asyncio
    async def test_invalid_step_id_returns_400(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = _make_v2_user()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/step",
                    json={"step_id": "nonexistent", "status": "completed"},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_status_returns_422(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = _make_v2_user()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/step",
                    json={"step_id": "welcome", "status": "invalid"},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_all_steps_done_marks_completed(self):
        """Completing all steps should set onboarding_completed=True."""
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        # Pre-complete all steps except "complete"
        user = _make_v2_user()
        for step in user.onboarding_step_statuses:
            if step.step_id != "complete":
                step.status = "completed"
                step.completed_at = datetime.now(timezone.utc).isoformat()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/step",
                    json={"step_id": "complete", "status": "completed"},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        data = resp.json()
        assert data["completed"] is True
        assert data["completed_at"] is not None
        assert user.onboarding_completed is True

    @pytest.mark.asyncio
    async def test_v1_user_auto_upgrades_on_step(self):
        """Calling step endpoint on a v1 user should auto-upgrade to v2."""
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient

        user = _make_v1_user()

        app.dependency_overrides[get_current_user] = lambda: user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.patch(
                    "/api/onboarding/step",
                    json={"step_id": "welcome", "status": "completed"},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        assert user.onboarding_version == 2


class TestOnboardingCompleteEndpoint:
    """PATCH /api/onboarding/complete marks onboarding done (backward compat)."""

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
    async def test_syncs_v2_step_statuses(self):
        """Calling /complete should also sync v2 step statuses."""
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
                    json={"skipped_steps": ["documents"]},
                )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        assert user.onboarding_version == 2
        assert user.onboarding_current_step == len(VALID_STEP_IDS)
        # Check v2 step statuses were set
        assert len(user.onboarding_step_statuses) == len(VALID_STEP_IDS)

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


class TestResetOnboardingEndpoint:
    """POST /api/test/reset-onboarding for e2e testing."""

    @pytest.mark.asyncio
    async def test_reset_works_when_auth_disabled(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient
        import server

        # Simulate auth disabled (user=None)
        app.dependency_overrides[get_current_user] = lambda: None
        try:
            with patch.object(server, "AUTH_ENABLED", False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post("/api/test/reset-onboarding")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        data = resp.json()
        assert data["reset"] is True
        assert data["version"] == 2

    @pytest.mark.asyncio
    async def test_reset_blocked_when_auth_enabled(self):
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient
        import server

        app.dependency_overrides[get_current_user] = lambda: None
        try:
            with patch.object(server, "AUTH_ENABLED", True):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post("/api/test/reset-onboarding")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_status_returns_v2_wizard_after_reset(self):
        """After reset, status endpoint should return non-completed v2 state."""
        from server import app
        from auth import get_current_user
        from httpx import ASGITransport, AsyncClient
        import server

        app.dependency_overrides[get_current_user] = lambda: None
        try:
            with patch.object(server, "AUTH_ENABLED", False):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    # First reset
                    reset_resp = await client.post("/api/test/reset-onboarding")
                    assert reset_resp.status_code == 200

                    # Then check status
                    status_resp = await client.get("/api/onboarding/status")
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        data = status_resp.json()
        assert data["version"] == 2
        assert data["completed"] is False
        assert data["current_step"] == 0
        assert len(data["steps"]) == 6
        assert all(s["status"] == "pending" for s in data["steps"])
