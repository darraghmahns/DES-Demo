"""Shared OAuth helpers used by both Dotloop and DocuSign clients.

Extracts the common refresh-token exchange pattern to avoid duplication
between dotloop_client.py and docusign_client.py.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


def refresh_oauth_token(
    token_url: str,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    timeout: float = 15.0,
) -> dict[str, Any] | None:
    """Exchange a refresh token for a new access token.

    Args:
        token_url: The OAuth token endpoint URL.
        refresh_token: The current refresh token.
        client_id: OAuth client ID.
        client_secret: OAuth client secret.
        timeout: HTTP request timeout in seconds.

    Returns:
        Token response dict with at least ``access_token`` (and optionally
        ``refresh_token``), or *None* if the refresh failed.
    """
    if not all([refresh_token, client_id, client_secret]):
        log.warning("Cannot refresh token: missing refresh_token, client_id, or client_secret")
        return None

    try:
        resp = httpx.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(client_id, client_secret),
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.warning("Token refresh HTTP error %s: %s", exc.response.status_code, exc)
        return None
    except httpx.RequestError as exc:
        log.warning("Token refresh request error: %s", exc)
        return None
