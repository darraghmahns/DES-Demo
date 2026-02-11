"""Dotloop Connector — orchestrates sync between D.E.S. extractions and Dotloop.

Provides:
  - sync_to_dotloop(extraction_id)    — push extraction → Dotloop loop
  - process_from_dotloop(...)         — pull PDF from loop → extract → save
  - list_dotloop_loops(...)           — list loops for a profile
  - handle_webhook(payload)           — process LOOP_UPDATED events
  - get_dotloop_client()              — factory returning configured client
  - is_configured()                   — check if Dotloop env vars are set
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from dotloop_client import DotloopClient, DotloopAPIError
from db_writer import get_extraction, save_document, save_extraction
from ocr_engine import get_engine
from schemas import DotloopLoopDetails, ExtractionResult
from verifier import compute_overall_confidence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory OAuth token storage (single-user for now)
# ---------------------------------------------------------------------------

_oauth_tokens: dict[str, str] = {}


def set_oauth_tokens(access_token: str, refresh_token: str | None = None) -> None:
    """Store OAuth tokens from browser flow."""
    _oauth_tokens["access_token"] = access_token
    if refresh_token:
        _oauth_tokens["refresh_token"] = refresh_token


def get_oauth_tokens() -> dict[str, str]:
    """Get stored OAuth tokens."""
    return dict(_oauth_tokens)


def clear_oauth_tokens() -> None:
    """Clear stored OAuth tokens."""
    _oauth_tokens.clear()


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Return True if Dotloop tokens are available (env or OAuth)."""
    return bool(os.getenv("DOTLOOP_API_TOKEN") or _oauth_tokens.get("access_token"))


def get_dotloop_client() -> DotloopClient:
    """Factory: build a DotloopClient, preferring OAuth tokens over env vars."""
    api_token = _oauth_tokens.get("access_token") or os.getenv("DOTLOOP_API_TOKEN")
    refresh_token = _oauth_tokens.get("refresh_token") or os.getenv("DOTLOOP_REFRESH_TOKEN")
    return DotloopClient(
        api_token=api_token,
        refresh_token=refresh_token,
        client_id=os.getenv("DOTLOOP_CLIENT_ID"),
        client_secret=os.getenv("DOTLOOP_CLIENT_SECRET"),
    )


def _get_profile_id() -> int:
    """Read DOTLOOP_PROFILE_ID from env, raising if missing."""
    pid = os.getenv("DOTLOOP_PROFILE_ID")
    if not pid:
        raise ValueError("DOTLOOP_PROFILE_ID not set in environment")
    return int(pid)


# ---------------------------------------------------------------------------
# Flow A: Push extraction to Dotloop
# ---------------------------------------------------------------------------

async def sync_to_dotloop(extraction_id: str, loop_id: int | None = None) -> dict[str, Any]:
    """Push a saved extraction to Dotloop as a loop.

    Steps:
      1. Load extraction from DB
      2. Read dotloop_api_payload (already formatted by to_dotloop_api_format())
      3. Use specified loop, find existing, or create new
      4. Update loop details
      5. Add participants (skip duplicates by email)

    Args:
        extraction_id: Extraction reference string (doc_id:index).
        loop_id: If provided, sync to this existing loop instead of
            creating/finding one automatically.

    Returns:
        Dict with loop_id, loop_url, action, and errors list.
    """
    ext = await get_extraction(extraction_id)
    if not ext:
        return {"error": f"Extraction {extraction_id} not found"}

    payload = ext.get("dotloop_api_payload")
    if not payload:
        return {"error": "No dotloop_api_payload on this extraction (not real_estate mode?)"}

    profile_id = _get_profile_id()
    errors: list[str] = []

    loop_name = payload.get("name", "Untitled Loop")
    transaction_type = payload.get("transactionType", "PURCHASE_OFFER")
    status = payload.get("status", "PRE_OFFER")
    loop_details = payload.get("loopDetails", {})
    participants = payload.get("participants", [])

    with get_dotloop_client() as client:
        # --- Create, find, or use specified loop ---
        if loop_id:
            # User selected an existing loop
            loop_url = None
            try:
                loop_info = client.get_loop(profile_id, loop_id)
                loop_url = loop_info.get("loopUrl")
            except DotloopAPIError:
                pass
            action = "Updated"
            log.info("Using user-selected loop %s", loop_id)
        else:
            # Auto: find by name or create new
            existing = client.find_existing_loop(profile_id, loop_name)
            if existing:
                loop_id = existing["id"]
                loop_url = existing.get("loopUrl")
                action = "Updated"
                log.info("Found existing loop %s", loop_id)
            else:
                created = client.create_loop(
                    profile_id=profile_id,
                    name=loop_name,
                    transaction_type=transaction_type,
                    status=status,
                )
                loop_id = created["id"]
                loop_url = created.get("loopUrl")
                action = "Created"
                log.info("Created loop %s: %s", loop_id, loop_url)

        # --- Update loop details ---
        if loop_details:
            try:
                client.update_loop_details(
                    profile_id=profile_id,
                    loop_id=loop_id,
                    details=loop_details,
                )
                log.info("Updated %d detail sections", len(loop_details))
            except DotloopAPIError as e:
                errors.append(f"Failed to update details: {e.message}")
                log.warning("Details update failed: %s", e.message)

        # --- Add participants (skip duplicates) ---
        if participants:
            try:
                existing_parts = client.list_participants(profile_id, loop_id)
                existing_emails = {
                    p.get("email", "").lower()
                    for p in existing_parts
                    if p.get("email")
                }
            except DotloopAPIError:
                existing_emails = set()

            for p in participants:
                email = (p.get("email") or "").lower()
                if email and email in existing_emails:
                    log.info("Skipping participant %s (already exists)", p.get("fullName"))
                    continue
                try:
                    client.add_participant(
                        profile_id=profile_id,
                        loop_id=loop_id,
                        full_name=p.get("fullName", ""),
                        email=p.get("email", ""),
                        role=p.get("role", "OTHER"),
                    )
                    log.info("Added participant %s (%s)", p.get("fullName"), p.get("role"))
                except DotloopAPIError as e:
                    if "Upgrade to Premium" in e.message:
                        log.info("Participant add requires Premium plan, skipping remaining")
                        break
                    errors.append(f"Failed to add {p.get('fullName')}: {e.message}")
                    log.warning("Participant add failed: %s", e.message)

    return {
        "loop_id": str(loop_id),
        "loop_url": loop_url,
        "action": action,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Flow B: Pull PDF from Dotloop, extract, save
# ---------------------------------------------------------------------------

async def process_from_dotloop(
    profile_id: int | None = None,
    loop_id: int = 0,
    sync_back: bool = False,
) -> dict[str, Any]:
    """Download a PDF from a Dotloop loop, run OCR extraction, and save.

    Steps:
      1. Get loop metadata
      2. List folders (with documents) and find first PDF
      3. Download PDF to temp file
      4. Run OCR engine extraction + verification
      5. Save to DB with source="dotloop"
      6. Optionally sync extracted data back to Dotloop

    Args:
        profile_id: Dotloop profile ID (falls back to env).
        loop_id: The loop ID to process.
        sync_back: If True, push extracted data back to Dotloop after extraction.

    Returns:
        Dict with extraction_id, document_id, loop_id, synced_back flag.
    """
    if not profile_id:
        profile_id = _get_profile_id()

    with get_dotloop_client() as client:
        # Get loop info
        loop = client.get_loop(profile_id, loop_id)
        loop_name = loop.get("name", f"loop-{loop_id}")

        # Find the first PDF document in any folder
        folders = client.list_folders(profile_id, loop_id, include_documents=True)
        pdf_doc = None
        pdf_folder_id = None

        for folder in folders:
            for doc in folder.get("documents", []):
                if doc.get("name", "").lower().endswith(".pdf"):
                    pdf_doc = doc
                    pdf_folder_id = folder["id"]
                    break
            if pdf_doc:
                break

        if not pdf_doc or not pdf_folder_id:
            return {"error": f"No PDF document found in loop {loop_id}"}

        # Download PDF
        pdf_bytes = client.download_document(
            profile_id=profile_id,
            loop_id=loop_id,
            folder_id=pdf_folder_id,
            document_id=pdf_doc["id"],
        )

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

        result = ExtractionResult(
            mode=mode,
            source_file=pdf_doc.get("name", "dotloop_document.pdf"),
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            pages_processed=file_info["pages"],
            dotloop_data=validated_data,
            dotloop_api_payload=dotloop_api_payload,
            citations=citations,
            overall_confidence=overall_confidence,
        )

        # Save to DB
        doc_id = await save_document(
            filename=pdf_doc.get("name", "dotloop_document.pdf"),
            mode=mode,
            page_count=file_info["pages"],
            file_size_bytes=len(pdf_bytes),
            source="dotloop",
            source_id=str(loop_id),
        )
        ext_id = await save_extraction(
            document_id=doc_id,
            result=result,
            engine=engine.name,
        )

        response: dict[str, Any] = {
            "extraction_id": str(ext_id),
            "document_id": str(doc_id),
            "loop_id": str(loop_id),
            "loop_name": loop_name,
            "synced_back": False,
        }

        # Optionally sync back
        if sync_back:
            sync_result = await sync_to_dotloop(str(ext_id))
            response["synced_back"] = True
            response["sync_result"] = sync_result

        return response

    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# List loops
# ---------------------------------------------------------------------------

def list_dotloop_loops(
    profile_id: int | None = None,
    batch_size: int = 20,
) -> list[dict[str, Any]]:
    """List recent loops from Dotloop.

    Args:
        profile_id: Dotloop profile ID (falls back to env).
        batch_size: Number of loops to return.

    Returns:
        List of loop dicts with id, name, transactionType, status, etc.
    """
    if not profile_id:
        profile_id = _get_profile_id()

    with get_dotloop_client() as client:
        result = client.list_loops(profile_id, batch_size=batch_size)
        return result.get("data", [])


# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------

async def handle_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle a Dotloop webhook event.

    Currently supports LOOP_UPDATED events, which trigger a fresh extraction.

    Args:
        payload: Webhook JSON body with event_type, loop_id, profile_id.

    Returns:
        Processing result dict.
    """
    event_type = payload.get("event_type", "")
    loop_id = payload.get("loop_id")
    profile_id = payload.get("profile_id")

    if event_type != "LOOP_UPDATED":
        return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}

    if not loop_id:
        return {"status": "error", "reason": "Missing loop_id in webhook payload"}

    log.info("Processing webhook: %s for loop %s", event_type, loop_id)

    try:
        result = await process_from_dotloop(
            profile_id=int(profile_id) if profile_id else None,
            loop_id=int(loop_id),
            sync_back=False,
        )
        return {"status": "processed", **result}
    except Exception as exc:
        log.error("Webhook processing failed: %s", exc)
        return {"status": "error", "reason": str(exc)}
