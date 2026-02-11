"""DocuSign Connector — orchestrates sync between D.E.S. extractions and DocuSign.

Provides:
  - sync_to_docusign(extraction_id)    — push extraction → DocuSign envelope
  - process_from_docusign(...)         — pull PDF from envelope → extract → save
  - list_docusign_envelopes(...)       — list recent envelopes
  - handle_webhook(payload)            — process envelope-completed events
  - get_docusign_client()              — factory returning configured client
  - is_configured()                    — check if DocuSign tokens are available
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docusign_client import DocuSignClient, DocuSignAPIError
from db_writer import get_extraction, save_document, save_extraction
from ocr_engine import get_engine
from schemas import DotloopLoopDetails, ExtractionResult
from verifier import compute_overall_confidence

log = logging.getLogger(__name__)

_TOKEN_FILE = Path(__file__).parent / ".docusign_tokens.json"

# ---------------------------------------------------------------------------
# Persistent OAuth token storage (single-user, file-backed)
# ---------------------------------------------------------------------------

_oauth_tokens: dict[str, str] = {}


def _load_tokens_from_disk() -> None:
    """Load persisted tokens from disk on startup."""
    global _oauth_tokens
    if _TOKEN_FILE.exists():
        try:
            data = json.loads(_TOKEN_FILE.read_text())
            if isinstance(data, dict):
                _oauth_tokens.update(data)
                log.info("Loaded DocuSign tokens from %s", _TOKEN_FILE)
        except Exception as e:
            log.warning("Failed to load DocuSign tokens: %s", e)


def _save_tokens_to_disk() -> None:
    """Persist current tokens to disk."""
    try:
        _TOKEN_FILE.write_text(json.dumps(_oauth_tokens, indent=2))
    except Exception as e:
        log.warning("Failed to save DocuSign tokens: %s", e)


# Auto-load on module import
_load_tokens_from_disk()


def set_oauth_tokens(
    access_token: str,
    refresh_token: str | None = None,
    account_id: str | None = None,
) -> None:
    """Store OAuth tokens from browser flow (persisted to disk)."""
    _oauth_tokens["access_token"] = access_token
    if refresh_token:
        _oauth_tokens["refresh_token"] = refresh_token
    if account_id:
        _oauth_tokens["account_id"] = account_id
    _save_tokens_to_disk()


def get_oauth_tokens() -> dict[str, str]:
    """Get stored OAuth tokens."""
    return dict(_oauth_tokens)


def clear_oauth_tokens() -> None:
    """Clear stored OAuth tokens (and remove file)."""
    _oauth_tokens.clear()
    if _TOKEN_FILE.exists():
        _TOKEN_FILE.unlink()


# ---------------------------------------------------------------------------
# JWT token generation
# ---------------------------------------------------------------------------

_PRIVATE_KEY_PATH = Path(__file__).parent / "docusign_private.pem"


def _jwt_available() -> bool:
    """Check if JWT auth prerequisites are met."""
    return bool(
        os.getenv("DOCUSIGN_CLIENT_ID")
        and os.getenv("DOCUSIGN_USER_ID")
        and _PRIVATE_KEY_PATH.exists()
    )


def _obtain_jwt_token() -> str | None:
    """Generate a JWT assertion and exchange it for an access token.

    Returns the access_token string, or None on failure.
    """
    import time as _time

    client_id = os.getenv("DOCUSIGN_CLIENT_ID", "")
    user_id = os.getenv("DOCUSIGN_USER_ID", "")
    auth_server = os.getenv("DOCUSIGN_AUTH_SERVER", "account-d.docusign.com")

    if not (client_id and user_id and _PRIVATE_KEY_PATH.exists()):
        return None

    try:
        import jwt as pyjwt
    except ImportError:
        log.warning("PyJWT not installed — cannot use JWT auth (pip install PyJWT cryptography)")
        return None

    try:
        private_key = _PRIVATE_KEY_PATH.read_text()
        now = int(_time.time())
        payload = {
            "iss": client_id,
            "sub": user_id,
            "aud": auth_server,
            "iat": now,
            "exp": now + 3600,
            "scope": "signature",
        }
        assertion = pyjwt.encode(payload, private_key, algorithm="RS256")

        import httpx
        resp = httpx.post(
            f"https://{auth_server}/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data["access_token"]

        # Persist the token
        set_oauth_tokens(access_token=access_token)
        log.info("Obtained DocuSign access token via JWT grant")
        return access_token

    except Exception as e:
        log.error("JWT token generation failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Return True if DocuSign tokens are available (env, OAuth, or JWT)."""
    if os.getenv("DOCUSIGN_ACCESS_TOKEN") or _oauth_tokens.get("access_token"):
        return True
    # Try JWT auto-auth if prerequisites are met
    if _jwt_available():
        token = _obtain_jwt_token()
        return token is not None
    return False


def get_docusign_client() -> DocuSignClient:
    """Factory: build a DocuSignClient, preferring OAuth tokens over env vars.

    If no access token is available but JWT prerequisites are met,
    automatically obtains a token via JWT grant.
    """
    access_token = _oauth_tokens.get("access_token") or os.getenv("DOCUSIGN_ACCESS_TOKEN")
    refresh_token = _oauth_tokens.get("refresh_token") or os.getenv("DOCUSIGN_REFRESH_TOKEN")
    account_id = _oauth_tokens.get("account_id") or os.getenv("DOCUSIGN_ACCOUNT_ID")

    # Auto-obtain token via JWT if none available
    if not access_token and _jwt_available():
        access_token = _obtain_jwt_token()

    client = DocuSignClient(
        access_token=access_token,
        refresh_token=refresh_token,
        client_id=os.getenv("DOCUSIGN_CLIENT_ID"),
        client_secret=os.getenv("DOCUSIGN_CLIENT_SECRET"),
        account_id=account_id,
        base_url=os.getenv("DOCUSIGN_BASE_URL"),
        auth_server=os.getenv("DOCUSIGN_AUTH_SERVER"),
    )

    # If no account_id, try to discover it
    if not account_id:
        try:
            discovered_id = client.discover_account_id()
            _oauth_tokens["account_id"] = discovered_id
            _save_tokens_to_disk()
            log.info("Discovered DocuSign account_id: %s", discovered_id)
        except DocuSignAPIError as e:
            log.warning("Could not discover account_id: %s", e)

    return client


# ---------------------------------------------------------------------------
# Flow A: Push extraction to DocuSign
# ---------------------------------------------------------------------------

async def sync_to_docusign(
    extraction_id: str,
    envelope_id: str | None = None,
) -> dict[str, Any]:
    """Push a saved extraction to DocuSign as an envelope.

    Steps:
      1. Load extraction from DB
      2. Read docusign_api_payload (already formatted by to_docusign_api_format())
      3. Create new envelope or use existing
      4. Set custom fields with property/financial data
      5. Return result

    Args:
        extraction_id: Extraction reference string (doc_id:index).
        envelope_id: If provided, update this existing envelope instead of
            creating a new one.

    Returns:
        Dict with envelope_id, action, and errors list.
    """
    ext = await get_extraction(extraction_id)
    if not ext:
        return {"error": f"Extraction {extraction_id} not found"}

    payload = ext.get("docusign_api_payload")
    if not payload:
        return {"error": "No docusign_api_payload on this extraction (not real_estate mode?)"}

    errors: list[str] = []

    email_subject = payload.get("emailSubject", "Purchase Agreement")
    custom_fields = payload.get("customFields")
    recipients = payload.get("recipients")

    with get_docusign_client() as client:
        if envelope_id:
            # Update existing envelope
            action = "Updated"

            # Update custom fields
            if custom_fields:
                try:
                    client.update_custom_fields(
                        envelope_id,
                        custom_fields.get("textCustomFields", []),
                    )
                except DocuSignAPIError as e:
                    errors.append(f"Failed to update custom fields: {e.message}")
                    log.warning("Custom fields update failed: %s", e.message)

            # Add recipients
            if recipients:
                try:
                    client.add_recipients(
                        envelope_id,
                        signers=recipients.get("signers"),
                        carbon_copies=recipients.get("carbonCopies"),
                    )
                except DocuSignAPIError as e:
                    errors.append(f"Failed to add recipients: {e.message}")
                    log.warning("Recipients add failed: %s", e.message)
        else:
            # Create new envelope (as draft)
            try:
                result = client.create_envelope(
                    email_subject=email_subject,
                    status="created",
                    recipients=recipients,
                    custom_fields=custom_fields,
                )
                envelope_id = result.get("envelopeId")
                action = "Created"
                log.info("Created DocuSign envelope: %s", envelope_id)
            except DocuSignAPIError as e:
                return {"error": f"Failed to create envelope: {e.message}"}

    return {
        "envelope_id": envelope_id,
        "action": action,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Flow B: Pull PDF from DocuSign, extract, save
# ---------------------------------------------------------------------------

async def process_from_docusign(
    envelope_id: str,
    sync_back: bool = False,
) -> dict[str, Any]:
    """Download a PDF from a DocuSign envelope, run OCR extraction, and save.

    Steps:
      1. Get envelope metadata
      2. Download combined PDF
      3. Run OCR engine extraction + verification
      4. Save to DB with source="docusign"
      5. Optionally sync back

    Args:
        envelope_id: The DocuSign envelope ID to process.
        sync_back: If True, push extracted data back to DocuSign after extraction.

    Returns:
        Dict with extraction_id, document_id, envelope_id.
    """
    with get_docusign_client() as client:
        # Get envelope info
        envelope = client.get_envelope(envelope_id)
        envelope_subject = envelope.get("emailSubject", f"envelope-{envelope_id}")

        # Download combined PDF
        pdf_bytes = client.download_combined(envelope_id)

    # Write to temp file for OCR processing
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        engine = get_engine()
        mode = "real_estate"

        # Extract
        if engine.prefers_file_path:
            raw_extraction = engine.extract_from_file(tmp_path, mode)
        else:
            from pdf_converter import pdf_to_images, image_to_base64
            images = pdf_to_images(tmp_path)
            images_b64 = [image_to_base64(img) for img in images]
            raw_extraction = engine.extract(images_b64, mode)

        # Validate
        validated = DotloopLoopDetails.model_validate(raw_extraction)
        validated_data = validated.model_dump(mode="json")

        # Verify citations
        if engine.prefers_file_path:
            citations = engine.verify_from_file(tmp_path, validated_data)
        else:
            citations = engine.verify(images_b64, validated_data)  # type: ignore[possibly-undefined]

        overall_confidence = compute_overall_confidence(citations)

        # Build result
        from pdf_converter import get_pdf_info
        file_info = get_pdf_info(tmp_path)

        dotloop_api_payload = validated.to_dotloop_api_format()
        docusign_api_payload = validated.to_docusign_api_format()

        result = ExtractionResult(
            mode=mode,
            source_file=f"docusign:{envelope_id}",
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            pages_processed=file_info["pages"],
            dotloop_data=validated_data,
            dotloop_api_payload=dotloop_api_payload,
            docusign_api_payload=docusign_api_payload,
            citations=citations,
            overall_confidence=overall_confidence,
        )

        # Save to DB
        doc_id = await save_document(
            filename=f"{envelope_subject}.pdf",
            mode=mode,
            page_count=file_info["pages"],
            file_size_bytes=len(pdf_bytes),
            source="docusign",
            source_id=envelope_id,
        )
        ext_id = await save_extraction(
            document_id=doc_id,
            result=result,
            engine=engine.name,
        )

        response: dict[str, Any] = {
            "extraction_id": str(ext_id),
            "document_id": str(doc_id),
            "envelope_id": envelope_id,
            "envelope_subject": envelope_subject,
            "synced_back": False,
        }

        # Optionally sync back
        if sync_back:
            sync_result = await sync_to_docusign(str(ext_id))
            response["synced_back"] = True
            response["sync_result"] = sync_result

        return response

    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# List envelopes
# ---------------------------------------------------------------------------

def list_docusign_envelopes(
    from_date: str | None = None,
    status: str | None = None,
    count: int = 20,
) -> list[dict[str, Any]]:
    """List recent envelopes from DocuSign.

    Args:
        from_date: ISO 8601 start date (defaults to 365 days ago).
        status: Filter by status (e.g. 'completed', 'sent').
        count: Number of envelopes to return.

    Returns:
        List of envelope dicts.
    """
    with get_docusign_client() as client:
        result = client.list_envelopes(
            from_date=from_date,
            status=status,
            count=count,
        )
        envelopes = result.get("envelopes", [])
        total = result.get("totalSetSize", "?")
        log.info(
            "DocuSign list_envelopes: totalSetSize=%s, returned=%d, from_date=%s",
            total, len(envelopes), from_date,
        )
        return envelopes


def void_docusign_envelope(
    envelope_id: str,
    reason: str = "Voided from D.E.S.",
) -> dict[str, Any]:
    """Void/discard a DocuSign envelope (works for drafts and sent envelopes)."""
    with get_docusign_client() as client:
        result = client.void_envelope(envelope_id, reason=reason)
        log.info("Voided DocuSign envelope: %s", envelope_id)
        return result


# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------

async def handle_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle a DocuSign Connect webhook event.

    Currently supports envelope-completed events, which trigger a fresh extraction.

    Args:
        payload: Webhook JSON body from DocuSign Connect.

    Returns:
        Processing result dict.
    """
    event = payload.get("event", "")
    envelope_id = payload.get("data", {}).get("envelopeId") or payload.get("envelopeId")

    if event != "envelope-completed":
        return {"status": "ignored", "reason": f"Unhandled event type: {event}"}

    if not envelope_id:
        return {"status": "error", "reason": "Missing envelopeId in webhook payload"}

    log.info("Processing DocuSign webhook: %s for envelope %s", event, envelope_id)

    try:
        result = await process_from_docusign(
            envelope_id=envelope_id,
            sync_back=False,
        )
        return {"status": "processed", **result}
    except Exception as exc:
        log.error("DocuSign webhook processing failed: %s", exc)
        return {"status": "error", "reason": str(exc)}
