"""Dotloop & DocuSign integration routes.

Extracted from server.py to keep the main module focused on core
extraction endpoints.  Mounted with ``app.include_router(router)``.
"""

import asyncio
import logging
import os
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from auth import (
    AUTH_ENABLED,
    get_current_user,
    get_optional_user,
    sign_oauth_state,
    verify_oauth_state,
)


def _external_base_url(request: Request) -> str:
    """Derive the external base URL, respecting X-Forwarded-Proto behind a reverse proxy."""
    base = str(request.base_url).rstrip("/")
    # Behind a reverse proxy (Render, etc.), base_url reports http:// but
    # the real external URL is https://.  Honour the forwarded header.
    proto = request.headers.get("x-forwarded-proto")
    if proto == "https" and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return base


from dotloop_connector import (
    is_configured as dotloop_configured,
    list_dotloop_loops,
    archive_dotloop_loop,
    sync_to_dotloop,
    process_from_dotloop,
    handle_webhook as dotloop_handle_webhook,
    set_oauth_tokens,
)
from docusign_connector import (
    is_configured as docusign_configured,
    list_docusign_envelopes,
    remove_docusign_envelope,
    sync_to_docusign,
    process_from_docusign,
    handle_webhook as docusign_handle_webhook,
    set_oauth_tokens as docusign_set_oauth_tokens,
)

log = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FRONTEND_URL = os.getenv("FRONTEND_URL", "")
DOTLOOP_AUTH_BASE = "https://auth.dotloop.com"
DOCUSIGN_AUTH_SERVER = os.getenv("DOCUSIGN_AUTH_SERVER", "account-d.docusign.com")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class DotloopSyncRequest(BaseModel):
    loop_id: int | None = None
    upload_document: bool = True


class ProcessFromDotloopRequest(BaseModel):
    profile_id: int | None = None
    sync_back: bool = False


class DocuSignSyncRequest(BaseModel):
    envelope_id: str | None = None


class ProcessFromDocuSignRequest(BaseModel):
    sync_back: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_dotloop_tokens(user) -> dict | None:
    """Extract Dotloop token dict from UserRecord, or None."""
    if not user or not getattr(user, "dotloop_tokens", None):
        return None
    t = user.dotloop_tokens
    return {"access_token": t.access_token, "refresh_token": t.refresh_token}


def _user_docusign_tokens(user) -> dict | None:
    """Extract DocuSign token dict from UserRecord, or None."""
    if not user or not getattr(user, "docusign_tokens", None):
        return None
    t = user.docusign_tokens
    return {
        "access_token": t.access_token,
        "refresh_token": t.refresh_token,
        "account_id": t.account_id,
    }


# ---------------------------------------------------------------------------
# Dotloop Integration Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/dotloop/status")
async def dotloop_status(user=Depends(get_optional_user)):
    """Check whether Dotloop integration is configured for this user."""
    user_tokens = _user_dotloop_tokens(user)
    return {"configured": dotloop_configured(user_tokens=user_tokens)}


@router.get("/api/dotloop/loops")
async def dotloop_loops(profile_id: int | None = None, batch_size: int = 20, user=Depends(get_optional_user)):
    """List recent loops from Dotloop."""
    user_tokens = _user_dotloop_tokens(user)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    try:
        loops = await asyncio.to_thread(list_dotloop_loops, profile_id, batch_size, user_tokens=user_tokens)
        return {"loops": loops}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dotloop/loops/search")
async def dotloop_search_loops(
    q: str = Query(..., description="Search query for loop name or property address"),
    profile_id: int | None = None,
    user=Depends(get_optional_user),
):
    """Search Dotloop loops by name or property address."""
    user_tokens = _user_dotloop_tokens(user)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    from dotloop_connector import search_loops
    try:
        matches = await asyncio.to_thread(search_loops, q, profile_id, user_tokens=user_tokens)
        return {"loops": matches, "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dotloop/loops/{loop_id}")
async def dotloop_loop_detail(loop_id: int, profile_id: int | None = None, user=Depends(get_optional_user)):
    """Get full loop detail including property, participants, and documents."""
    user_tokens = _user_dotloop_tokens(user)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    from dotloop_connector import get_loop_with_details
    try:
        detail = await asyncio.to_thread(get_loop_with_details, loop_id, profile_id, user_tokens=user_tokens)
        return detail
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/dotloop/sync/{extraction_id}")
async def dotloop_sync(extraction_id: str, body: DotloopSyncRequest = DotloopSyncRequest(), user=Depends(get_current_user)):
    """Push a saved extraction to Dotloop as a loop."""
    user_tokens = _user_dotloop_tokens(user)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    try:
        result = await sync_to_dotloop(
            extraction_id,
            loop_id=body.loop_id,
            upload_document=body.upload_document,
            user_tokens=user_tokens,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/dotloop/process/{loop_id}")
async def dotloop_process(loop_id: int, request: ProcessFromDotloopRequest, user=Depends(get_current_user)):
    """Pull a PDF from a Dotloop loop, extract, and optionally sync back."""
    user_tokens = _user_dotloop_tokens(user)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    try:
        result = await process_from_dotloop(request.profile_id, loop_id, request.sync_back, user_tokens=user_tokens)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/dotloop/loops/{loop_id}")
async def dotloop_archive_loop(loop_id: int, user=Depends(get_current_user)):
    """Archive a single Dotloop loop."""
    user_tokens = _user_dotloop_tokens(user)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    try:
        result = await asyncio.to_thread(archive_dotloop_loop, loop_id, user_tokens=user_tokens)
        return {"status": "archived", "loop_id": loop_id, "detail": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/dotloop/loops")
async def dotloop_archive_all_loops(user=Depends(get_current_user)):
    """Archive all Dotloop loops."""
    user_tokens = _user_dotloop_tokens(user)
    if not dotloop_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    try:
        loops = await asyncio.to_thread(list_dotloop_loops, None, 100, user_tokens=user_tokens)
        results = []
        for loop in loops:
            lid = loop.get("loopId")
            if lid:
                try:
                    await asyncio.to_thread(archive_dotloop_loop, lid, user_tokens=user_tokens)
                    results.append({"loop_id": lid, "result": "archived"})
                except Exception as e:
                    results.append({"loop_id": lid, "result": str(e)})
        return {"archived": len(results), "details": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Dotloop OAuth Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/dotloop/oauth/connect")
async def dotloop_oauth_connect(request: Request, user=Depends(get_optional_user)):
    """Redirect browser to Dotloop authorization page."""
    client_id = os.getenv("DOTLOOP_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="DOTLOOP_CLIENT_ID not configured")

    redirect_uri = os.getenv(
        "DOTLOOP_REDIRECT_URI",
        f"{_external_base_url(request)}/api/dotloop/oauth/callback",
    )

    # Include signed state with user ID so callback can store tokens on the right user
    state_param = ""
    if user and AUTH_ENABLED:
        state = sign_oauth_state(user.clerk_user_id)
        state_param = f"&state={state}"

    auth_url = (
        f"{DOTLOOP_AUTH_BASE}/oauth/authorize"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"{state_param}"
    )
    return RedirectResponse(url=auth_url)


@router.get("/api/dotloop/oauth/callback")
async def dotloop_oauth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    state: str | None = None,
):
    """Handle OAuth callback from Dotloop, exchange code for tokens."""
    frontend_url = FRONTEND_URL or "http://localhost:5173"

    if error:
        desc = error_description or error
        return RedirectResponse(url=f"{frontend_url}/profile?dotloop_error={desc}")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    client_id = os.getenv("DOTLOOP_CLIENT_ID")
    client_secret = os.getenv("DOTLOOP_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "DOTLOOP_REDIRECT_URI",
        f"{_external_base_url(request)}/api/dotloop/oauth/callback",
    )

    try:
        resp = httpx.post(
            f"{DOTLOOP_AUTH_BASE}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(client_id, client_secret),
            timeout=15.0,
        )
        if resp.status_code != 200:
            log.error(
                "Dotloop token exchange HTTP %s – redirect_uri=%s body=%s",
                resp.status_code, redirect_uri, resp.text[:500],
            )
        resp.raise_for_status()
        token_data = resp.json()
    except Exception as e:
        log.error("Dotloop token exchange failed: %s", e)
        return RedirectResponse(url=f"{frontend_url}/profile?dotloop_error=token_exchange_failed")

    # If we have a signed state, store tokens on the user's record
    if state and AUTH_ENABLED:
        try:
            clerk_user_id = verify_oauth_state(state)
            from db import UserRecord, OAuthTokenSet
            user = await UserRecord.find_one(UserRecord.clerk_user_id == clerk_user_id)
            if user:
                user.dotloop_tokens = OAuthTokenSet(
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token"),
                )
                await user.save()
                log.info("Stored Dotloop tokens on user %s", clerk_user_id)
        except HTTPException:
            log.warning("Invalid OAuth state in Dotloop callback, falling back to module-level storage")

    # Always store module-level as fallback (for webhooks, etc.)
    set_oauth_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
    )

    return RedirectResponse(url=f"{frontend_url}/profile?dotloop_connected=true")


@router.delete("/api/dotloop/oauth/disconnect")
async def dotloop_oauth_disconnect(user=Depends(get_current_user)):
    """Remove Dotloop OAuth tokens from the user's profile."""
    if not user or not user.dotloop_tokens:
        return {"status": "not_connected"}
    user.dotloop_tokens = None
    await user.save()
    log.info("Disconnected Dotloop for user %s", getattr(user, "clerk_user_id", "unknown"))
    return {"status": "disconnected"}


# ---------------------------------------------------------------------------
# Dotloop Webhook
# ---------------------------------------------------------------------------

@router.post("/api/webhooks/dotloop")
async def dotloop_webhook(payload: dict):
    """Receive Dotloop LOOP_UPDATED webhook events."""
    result = await dotloop_handle_webhook(payload)
    return result


# ---------------------------------------------------------------------------
# DocuSign Integration Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/docusign/status")
async def docusign_status(user=Depends(get_optional_user)):
    """Check whether DocuSign integration is configured for this user."""
    from docusign_connector import get_oauth_tokens, _jwt_available
    user_tokens = _user_docusign_tokens(user)
    configured = docusign_configured(user_tokens=user_tokens)
    tokens = get_oauth_tokens()
    return {
        "configured": configured,
        "has_access_token": bool(
            (user_tokens and user_tokens.get("access_token"))
            or tokens.get("access_token")
            or os.getenv("DOCUSIGN_ACCESS_TOKEN")
        ),
        "has_account_id": bool(
            (user_tokens and user_tokens.get("account_id"))
            or tokens.get("account_id")
            or os.getenv("DOCUSIGN_ACCOUNT_ID")
        ),
        "jwt_available": _jwt_available(),
        "account_id": (
            (user_tokens or {}).get("account_id")
            or tokens.get("account_id")
            or os.getenv("DOCUSIGN_ACCOUNT_ID", "")
        ),
    }


@router.get("/api/docusign/envelopes")
async def docusign_envelopes(
    from_date: str | None = None,
    status: str | None = None,
    count: int = 50,
    user=Depends(get_optional_user),
):
    """List recent envelopes from DocuSign."""
    user_tokens = _user_docusign_tokens(user)
    if not docusign_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    # Default to all active statuses so drafts are included
    if not status:
        status = "created,sent,delivered,signed,completed"
    try:
        envelopes = await asyncio.to_thread(
            list_docusign_envelopes, from_date, status, count, user_tokens=user_tokens
        )
        return {"envelopes": envelopes}
    except Exception as e:
        log.error("DocuSign envelope listing failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/docusign/envelopes/{envelope_id}")
async def docusign_envelope_detail(envelope_id: str, user=Depends(get_optional_user)):
    """Get full envelope detail including recipients and documents."""
    user_tokens = _user_docusign_tokens(user)
    if not docusign_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    from docusign_connector import get_envelope_with_details
    try:
        detail = await asyncio.to_thread(get_envelope_with_details, envelope_id, user_tokens=user_tokens)
        return detail
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/docusign/sync/{extraction_id}")
async def docusign_sync(extraction_id: str, body: DocuSignSyncRequest = DocuSignSyncRequest(), user=Depends(get_current_user)):
    """Push a saved extraction to DocuSign as an envelope."""
    user_tokens = _user_docusign_tokens(user)
    if not docusign_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    try:
        result = await sync_to_docusign(extraction_id, envelope_id=body.envelope_id, user_tokens=user_tokens)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        # Construct envelope web URL
        if result.get("envelope_id"):
            base_url = os.getenv("DOCUSIGN_BASE_URL", "https://demo.docusign.net/restapi")
            if "demo.docusign.net" in base_url:
                portal_base = "https://appdemo.docusign.com"
            else:
                portal_base = "https://app.docusign.com"
            result["envelope_url"] = f"{portal_base}/documents/details/{result['envelope_id']}"
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/docusign/envelopes/{envelope_id}")
async def docusign_remove_envelope(envelope_id: str, user=Depends(get_current_user)):
    """Remove a DocuSign envelope -- voids sent/delivered, deletes drafts."""
    user_tokens = _user_docusign_tokens(user)
    if not docusign_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    try:
        result = await asyncio.to_thread(remove_docusign_envelope, envelope_id, user_tokens=user_tokens)
        return {"status": "removed", "envelope_id": envelope_id, "detail": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/docusign/envelopes")
async def docusign_remove_all_envelopes(user=Depends(get_current_user)):
    """Remove all DocuSign envelopes -- voids sent/delivered, deletes drafts."""
    user_tokens = _user_docusign_tokens(user)
    if not docusign_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    try:
        envelopes = await asyncio.to_thread(
            list_docusign_envelopes, None, "created,sent,delivered", 100, user_tokens=user_tokens
        )
        results = []
        for env in envelopes:
            eid = env.get("envelopeId")
            if eid:
                try:
                    r = await asyncio.to_thread(remove_docusign_envelope, eid, user_tokens=user_tokens)
                    results.append({"envelope_id": eid, "result": "removed"})
                except Exception as e:
                    results.append({"envelope_id": eid, "result": str(e)})
        return {"removed": len(results), "details": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/docusign/process/{envelope_id}")
async def docusign_process(envelope_id: str, request: ProcessFromDocuSignRequest = ProcessFromDocuSignRequest(), user=Depends(get_current_user)):
    """Pull a PDF from a DocuSign envelope, extract, and optionally sync back."""
    user_tokens = _user_docusign_tokens(user)
    if not docusign_configured(user_tokens=user_tokens):
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    try:
        result = await process_from_docusign(envelope_id, request.sync_back, user_tokens=user_tokens)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# DocuSign OAuth Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/docusign/oauth/connect")
async def docusign_oauth_connect(request: Request, user=Depends(get_optional_user)):
    """Redirect browser to DocuSign authorization page."""
    client_id = os.getenv("DOCUSIGN_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="DOCUSIGN_CLIENT_ID not configured")

    redirect_uri = os.getenv(
        "DOCUSIGN_REDIRECT_URI",
        f"{_external_base_url(request)}/api/docusign/oauth/callback",
    )
    params: dict = {
        "response_type": "code",
        "scope": "signature",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    # Include signed state with user ID so callback can store tokens on the right user
    if user and AUTH_ENABLED:
        params["state"] = sign_oauth_state(user.clerk_user_id)

    auth_url = f"https://{DOCUSIGN_AUTH_SERVER}/oauth/auth?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/api/docusign/oauth/callback")
async def docusign_oauth_callback(
    request: Request,
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
):
    """Handle OAuth callback from DocuSign, exchange code for tokens."""
    frontend_url = FRONTEND_URL or "http://localhost:5173"

    if error:
        return RedirectResponse(url=f"{frontend_url}/profile?docusign_error={error}")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    client_id = os.getenv("DOCUSIGN_CLIENT_ID")
    client_secret = os.getenv("DOCUSIGN_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "DOCUSIGN_REDIRECT_URI",
        f"{_external_base_url(request)}/api/docusign/oauth/callback",
    )

    try:
        resp = httpx.post(
            f"https://{DOCUSIGN_AUTH_SERVER}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(client_id, client_secret),
            timeout=15.0,
        )
        resp.raise_for_status()
        token_data = resp.json()
    except Exception as e:
        log.error("DocuSign token exchange failed: %s", e)
        return RedirectResponse(url=f"{frontend_url}/profile?docusign_error=token_exchange_failed")

    # Discover account_id from userinfo
    account_id = None
    try:
        userinfo_resp = httpx.get(
            f"https://{DOCUSIGN_AUTH_SERVER}/oauth/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
            timeout=15.0,
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()
        for acct in userinfo.get("accounts", []):
            if acct.get("is_default"):
                account_id = acct["account_id"]
                break
        if not account_id:
            accounts = userinfo.get("accounts", [])
            if accounts:
                account_id = accounts[0]["account_id"]
    except Exception as e:
        log.warning("DocuSign userinfo failed: %s", e)

    # If we have a signed state, store tokens on the user's record
    if state and AUTH_ENABLED:
        try:
            clerk_user_id = verify_oauth_state(state)
            from db import UserRecord, OAuthTokenSet
            user = await UserRecord.find_one(UserRecord.clerk_user_id == clerk_user_id)
            if user:
                user.docusign_tokens = OAuthTokenSet(
                    access_token=token_data["access_token"],
                    refresh_token=token_data.get("refresh_token"),
                    account_id=account_id,
                )
                await user.save()
                log.info("Stored DocuSign tokens on user %s", clerk_user_id)
        except HTTPException:
            log.warning("Invalid OAuth state in DocuSign callback, falling back to module-level storage")

    # Always store module-level as fallback (for webhooks, etc.)
    docusign_set_oauth_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        account_id=account_id,
    )

    return RedirectResponse(url=f"{frontend_url}/profile?docusign_connected=true")


@router.delete("/api/docusign/oauth/disconnect")
async def docusign_oauth_disconnect(user=Depends(get_current_user)):
    """Remove DocuSign OAuth tokens from the user's profile."""
    if not user or not user.docusign_tokens:
        return {"status": "not_connected"}
    user.docusign_tokens = None
    await user.save()
    log.info("Disconnected DocuSign for user %s", getattr(user, "clerk_user_id", "unknown"))
    return {"status": "disconnected"}


# ---------------------------------------------------------------------------
# DocuSign Webhook
# ---------------------------------------------------------------------------

@router.post("/api/webhooks/docusign")
async def docusign_webhook(payload: dict):
    """Receive DocuSign Connect webhook events."""
    result = await docusign_handle_webhook(payload)
    return result
