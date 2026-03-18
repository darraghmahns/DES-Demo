from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import db


class DummyResponse:
    def __init__(self, payload: dict):
        self.status_code = 200
        self._payload = payload
        self.text = ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


@pytest.mark.asyncio
async def test_dotloop_oauth_callback_stores_profile_id_on_user():
    from server import app

    user = MagicMock()
    user.dotloop_tokens = None
    user.save = AsyncMock()

    with (
        patch("routers.integrations.AUTH_ENABLED", True),
        patch("routers.integrations.verify_oauth_state", return_value="clerk-user-1"),
        patch(
            "routers.integrations.httpx.post",
            return_value=DummyResponse(
                {"access_token": "access-token", "refresh_token": "refresh-token"}
            ),
        ),
        patch("routers.integrations._resolve_dotloop_profile_id_for_tokens", return_value=73),
        patch.object(db.UserProfile, "clerk_user_id", "clerk_user_id", create=True),
        patch("db.UserProfile.find_one", AsyncMock(return_value=user)),
        patch("routers.integrations.set_oauth_tokens"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/dotloop/oauth/callback?code=abc123&state=signed-state")

    assert response.status_code in (302, 307)
    assert response.headers["location"].endswith("/profile?dotloop_connected=true")
    assert user.dotloop_tokens.profile_id == 73
    assert user.dotloop_tokens.access_token == "access-token"
    assert user.dotloop_tokens.refresh_token == "refresh-token"
    user.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_dotloop_status_ignores_module_fallback_when_user_is_disconnected():
    from auth import get_optional_user
    from server import app

    disconnected_user = MagicMock(dotloop_tokens=None)

    app.dependency_overrides[get_optional_user] = lambda: disconnected_user
    try:
        with patch("routers.integrations.AUTH_ENABLED", True):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/dotloop/status")
    finally:
        app.dependency_overrides.pop(get_optional_user, None)

    assert response.status_code == 200
    assert response.json() == {"configured": False}
