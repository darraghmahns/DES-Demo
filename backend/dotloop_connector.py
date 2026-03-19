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
from db import DocumentRecord, Transaction
from db_writer import get_extraction, save_document, save_extraction
from ocr_engine import get_engine
from schemas import DotloopLoopDetails, DotloopSyncStatus, ExtractionResult
from verifier import compute_overall_confidence

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory OAuth token storage (single-user for now)
# ---------------------------------------------------------------------------

_oauth_tokens: dict[str, Any] = {}


def set_oauth_tokens(
    access_token: str,
    refresh_token: str | None = None,
    profile_id: int | None = None,
) -> None:
    """Store OAuth tokens from browser flow."""
    _oauth_tokens["access_token"] = access_token
    if refresh_token:
        _oauth_tokens["refresh_token"] = refresh_token
    if profile_id is not None:
        _oauth_tokens["profile_id"] = int(profile_id)


def get_oauth_tokens() -> dict[str, Any]:
    """Get stored OAuth tokens."""
    return dict(_oauth_tokens)


def clear_oauth_tokens() -> None:
    """Clear stored OAuth tokens."""
    _oauth_tokens.clear()


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def is_configured(
    user_tokens: dict | None = None,
    *,
    allow_fallback: bool = True,
) -> bool:
    """Return True if Dotloop tokens are available.

    Priority: user_tokens > module-level OAuth > env vars.
    """
    if user_tokens is not None:
        return bool(user_tokens.get("access_token"))
    if not allow_fallback:
        return False
    return bool(os.getenv("DOTLOOP_API_TOKEN") or _oauth_tokens.get("access_token"))


def get_dotloop_client(user_tokens: dict | None = None) -> DotloopClient:
    """Factory: build a DotloopClient.

    Priority: user_tokens > module-level OAuth > env vars.
    """
    if user_tokens and user_tokens.get("access_token"):
        api_token = user_tokens["access_token"]
        refresh_token = user_tokens.get("refresh_token")
    else:
        api_token = _oauth_tokens.get("access_token") or os.getenv("DOTLOOP_API_TOKEN")
        refresh_token = _oauth_tokens.get("refresh_token") or os.getenv("DOTLOOP_REFRESH_TOKEN")
    return DotloopClient(
        api_token=api_token,
        refresh_token=refresh_token,
        client_id=os.getenv("DOTLOOP_CLIENT_ID"),
        client_secret=os.getenv("DOTLOOP_CLIENT_SECRET"),
    )


def _coerce_profile_id(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Dotloop profile id: {value!r}") from exc


def _discover_profile_id(user_tokens: dict | None = None) -> int:
    with get_dotloop_client(user_tokens=user_tokens) as client:
        profile_id = client.resolve_default_profile_id()
    if user_tokens is not None:
        user_tokens["profile_id"] = profile_id
    else:
        _oauth_tokens["profile_id"] = profile_id
    return profile_id


def resolve_profile_id(
    profile_id: int | None = None,
    *,
    user_tokens: dict | None = None,
) -> int:
    """Resolve a Dotloop profile id for the current request.

    Priority:
      1. explicit route/function argument
      2. stored per-user Dotloop OAuth profile id
      3. discover the user's default Dotloop profile from the OAuth token
      4. module-level OAuth fallback
      5. legacy env fallback
    """
    explicit_profile_id = _coerce_profile_id(profile_id)
    if explicit_profile_id is not None:
        return explicit_profile_id

    token_profile_id = _coerce_profile_id((user_tokens or {}).get("profile_id"))
    if token_profile_id is not None:
        return token_profile_id

    fallback_profile_id = _coerce_profile_id(_oauth_tokens.get("profile_id"))
    if fallback_profile_id is not None:
        return fallback_profile_id

    if user_tokens and user_tokens.get("access_token"):
        return _discover_profile_id(user_tokens=user_tokens)

    if _oauth_tokens.get("access_token") or os.getenv("DOTLOOP_API_TOKEN"):
        return _discover_profile_id()

    env_profile_id = _coerce_profile_id(os.getenv("DOTLOOP_PROFILE_ID"))
    if env_profile_id is not None:
        return env_profile_id

    raise ValueError(
        "Dotloop profile id is unavailable. Reconnect Dotloop or configure DOTLOOP_PROFILE_ID."
    )


# ---------------------------------------------------------------------------
# Flow A: Push extraction to Dotloop
# ---------------------------------------------------------------------------

async def preview_sync_to_dotloop(
    extraction_id: str,
    mode: str = "buying",
    user_tokens: dict | None = None,
) -> dict[str, Any]:
    """Build sync preview without writing to Dotloop.

    Args:
        extraction_id: Extraction reference string.
        mode: 'selling' or 'buying'.
        user_tokens: Optional OAuth tokens.

    Returns:
        Dict with loop_name, loop_action, existing_loop, folder_name,
        participants, document_name, mode.
    """
    ext = await get_extraction(extraction_id)
    if not ext:
        return {"error": f"Extraction {extraction_id} not found"}

    payload = ext.get("dotloop_api_payload")
    if not payload:
        return {"error": "No dotloop_api_payload on this extraction (not real_estate mode?)"}

    profile_id = resolve_profile_id(user_tokens=user_tokens)
    participants = payload.get("participants", [])

    if mode == "selling":
        # Loop per property, folder per buyer
        loop_details = payload.get("loopDetails", {})
        prop_addr = loop_details.get("propertyInformation", {}).get("address", {})
        street = f"{prop_addr.get('streetNumber', '')} {prop_addr.get('streetName', '')}".strip()
        city = prop_addr.get("city", "")
        loop_name = f"{street}, {city}".strip(", ") if street else payload.get("name", "Untitled Loop")
        buyer = next((p for p in participants if p.get("role") == "BUYER"), None)
        folder_name = buyer.get("fullName", "Buyer") if buyer else "Buyer Documents"
    else:
        # Buying: loop per buyer (use loop_name from payload), fixed folder
        loop_name = payload.get("name", "Untitled Loop")
        folder_name = "Extracted Documents"

    # Check for existing loop (read-only)
    existing_loop = None
    loop_action = "create"
    if is_configured(user_tokens=user_tokens):
        try:
            with get_dotloop_client(user_tokens=user_tokens) as client:
                existing = client.find_existing_loop(profile_id, loop_name)
                if existing:
                    existing_loop = {"id": existing["id"], "name": existing.get("name", "")}
                    loop_action = "update"
        except Exception:
            pass  # Read-only preview — ignore errors

    doc_record = None
    document_name = None
    try:
        doc_record = await DocumentRecord.get(ext["document_id"])
        if doc_record:
            document_name = doc_record.filename
    except Exception:
        pass

    return {
        "loop_name": loop_name,
        "loop_action": loop_action,
        "existing_loop": existing_loop,
        "folder_name": folder_name,
        "participants": participants,
        "document_name": document_name,
        "mode": mode,
    }


async def sync_to_dotloop(
    extraction_id: str,
    loop_id: int | None = None,
    folder_name: str | None = None,
    upload_document: bool = True,
    mode: str = "buying",
    user_tokens: dict | None = None,
) -> dict[str, Any]:
    """Push a saved extraction to Dotloop as a loop.

    Steps:
      1. Load extraction from DB
      2. Read dotloop_api_payload (already formatted by to_dotloop_api_format())
      3. Use specified loop, find existing, or create new
      4. Update loop details
      5. Add participants (skip duplicates by email)
      6. Upload source PDF document (if available and upload_document=True)

    Args:
        extraction_id: Extraction reference string (doc_id:index).
        loop_id: If provided, sync to this existing loop instead of
            creating/finding one automatically.
        upload_document: If True, upload the source PDF to the loop.

    Returns:
        Dict with loop_id, loop_url, action, document_uploaded, and errors list.
    """
    ext = await get_extraction(extraction_id)
    if not ext:
        return {"error": f"Extraction {extraction_id} not found"}

    payload = ext.get("dotloop_api_payload")
    if not payload:
        return {"error": "No dotloop_api_payload on this extraction (not real_estate mode?)"}

    profile_id = resolve_profile_id(user_tokens=user_tokens)
    errors: list[str] = []

    loop_name = payload.get("name", "Untitled Loop")
    transaction_type = payload.get("transactionType", "PURCHASE_OFFER")
    status = payload.get("status", "PRE_OFFER")
    loop_details = payload.get("loopDetails", {})
    participants = payload.get("participants", [])

    with get_dotloop_client(user_tokens=user_tokens) as client:
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

        # --- Upload source PDF document ---
        document_uploaded = False
        document_name: str | None = None

        if upload_document:
            try:
                # Look up the parent DocumentRecord to get file_path
                doc_record = await DocumentRecord.get(ext["document_id"])
                file_path = doc_record.file_path if doc_record else None

                if file_path and Path(file_path).exists():
                    _folder_name = folder_name or "Extracted Documents"
                    folder = client.find_or_create_folder(
                        profile_id, loop_id, _folder_name
                    )
                    folder_id = folder["id"]
                    client.upload_document(
                        profile_id=profile_id,
                        loop_id=loop_id,
                        folder_id=folder_id,
                        file_path=file_path,
                        file_name=doc_record.filename,
                    )
                    document_uploaded = True
                    document_name = doc_record.filename
                    log.info(
                        "Uploaded document %s to folder %s in loop %s",
                        doc_record.filename, folder_id, loop_id,
                    )
                elif file_path:
                    errors.append(
                        f"Source PDF not found on disk at {file_path} — document not uploaded"
                    )
                    log.warning("Source PDF missing: %s", file_path)
                else:
                    log.info("No file_path stored for extraction — skipping document upload")
            except DotloopAPIError as e:
                errors.append(f"Failed to upload document: {e.message}")
                log.warning("Document upload failed: %s", e.message)
            except Exception as e:
                errors.append(f"Failed to upload document: {e}")
                log.warning("Document upload failed: %s", e)

    return {
        "loop_id": str(loop_id),
        "loop_url": loop_url,
        "action": action,
        "document_uploaded": document_uploaded,
        "document_name": document_name,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Flow B: Pull PDF from Dotloop, extract, save
# ---------------------------------------------------------------------------

async def process_from_dotloop(
    profile_id: int | None = None,
    loop_id: int = 0,
    sync_back: bool = False,
    user_tokens: dict | None = None,
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
        profile_id: Dotloop profile ID (falls back to the connected user's profile).
        loop_id: The loop ID to process.
        sync_back: If True, push extracted data back to Dotloop after extraction.

    Returns:
        Dict with extraction_id, document_id, loop_id, synced_back flag.
    """
    profile_id = resolve_profile_id(profile_id, user_tokens=user_tokens)

    with get_dotloop_client(user_tokens=user_tokens) as client:
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

        # Extract (engine methods return (result, usage) tuples)
        if engine.prefers_file_path:
            raw_extraction, _extract_usage = engine.extract_from_file(tmp_path, mode)
        else:
            from pdf_converter import pdf_to_base64_images
            images_b64 = pdf_to_base64_images(tmp_path)
            raw_extraction, _extract_usage = engine.extract(images_b64, mode)

        # Validate
        validated = DotloopLoopDetails.model_validate(raw_extraction)
        validated_data = validated.model_dump(mode="json")

        # Verify citations
        if engine.prefers_file_path:
            citations, _verify_usage = engine.verify_from_file(tmp_path, validated_data)
        else:
            citations, _verify_usage = engine.verify(images_b64, validated_data)  # type: ignore[possibly-undefined]

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
    user_tokens: dict | None = None,
) -> list[dict[str, Any]]:
    """List recent loops from Dotloop.

    Args:
        profile_id: Dotloop profile ID (falls back to the connected user's profile).
        batch_size: Number of loops to return.

    Returns:
        List of loop dicts with id, name, transactionType, status, etc.
    """
    profile_id = resolve_profile_id(profile_id, user_tokens=user_tokens)

    with get_dotloop_client(user_tokens=user_tokens) as client:
        result = client.list_loops(profile_id, batch_size=batch_size)
        return result.get("data", [])


def archive_dotloop_loop(
    loop_id: int,
    profile_id: int | None = None,
    user_tokens: dict | None = None,
) -> dict[str, Any]:
    """Archive a Dotloop loop by setting its status to 'Archived'."""
    profile_id = resolve_profile_id(profile_id, user_tokens=user_tokens)

    with get_dotloop_client(user_tokens=user_tokens) as client:
        return client.update_loop(profile_id, loop_id, status="Archived")


# ---------------------------------------------------------------------------
# Webhook handler
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Loop detail + document listing
# ---------------------------------------------------------------------------

def get_loop_with_details(
    loop_id: int,
    profile_id: int | None = None,
    user_tokens: dict | None = None,
) -> dict[str, Any]:
    """Get full loop metadata including details, participants, and document list.

    Returns a unified dict with:
      - Loop metadata (id, name, transactionType, status, loopUrl)
      - Loop details (property address, financials, dates)
      - Participants list
      - Documents list (across all folders)

    This is the "loop viewer" endpoint that powers the comparison UI.
    """
    profile_id = resolve_profile_id(profile_id, user_tokens=user_tokens)

    with get_dotloop_client(user_tokens=user_tokens) as client:
        # Core loop info
        loop = client.get_loop(profile_id, loop_id)

        # Structured details (property, financials, dates, etc.)
        details = client.get_loop_details(profile_id, loop_id)

        # Participants
        try:
            participants = client.list_participants(profile_id, loop_id)
        except DotloopAPIError:
            participants = []

        # Documents from all folders
        documents: list[dict[str, Any]] = []
        try:
            folders = client.list_folders(
                profile_id, loop_id, include_documents=True,
            )
            for folder in folders:
                folder_name = folder.get("name", "")
                folder_id = folder.get("id")
                for doc in folder.get("documents", []):
                    documents.append({
                        "id": doc.get("id"),
                        "name": doc.get("name", ""),
                        "folder_id": folder_id,
                        "folder_name": folder_name,
                    })
        except DotloopAPIError:
            pass

    # Build unified response
    property_address = details.get("Property Address", {})
    financials = details.get("Financials", {})
    contract_dates = details.get("Contract Dates", {})

    return {
        "id": loop.get("id"),
        "name": loop.get("name", ""),
        "transaction_type": loop.get("transactionType", ""),
        "status": loop.get("status", ""),
        "loop_url": loop.get("loopUrl", ""),
        "created": loop.get("created", ""),
        "updated": loop.get("updated", ""),
        "property_address": {
            "street_number": property_address.get("Street Number", ""),
            "street_name": property_address.get("Street Name", ""),
            "city": property_address.get("City", ""),
            "state": property_address.get("State/Prov", ""),
            "postal_code": property_address.get("Zip/Postal Code", ""),
            "county": property_address.get("County", ""),
            "unit": property_address.get("Unit Number", ""),
        },
        "financials": {
            "purchase_price": financials.get("Purchase/Sale Price", ""),
            "earnest_money": financials.get("Earnest Money Amount", ""),
            "commission_rate": financials.get("Sale Commission Rate", ""),
        },
        "contract_dates": {
            "closing_date": contract_dates.get("Closing Date", ""),
            "offer_date": contract_dates.get("Offer Date", ""),
            "offer_expiration": contract_dates.get("Offer Expiration Date", ""),
            "inspection_date": contract_dates.get("Inspection Date", ""),
        },
        "participants": [
            {
                "id": p.get("id"),
                "full_name": p.get("fullName", ""),
                "email": p.get("email", ""),
                "role": p.get("role", ""),
            }
            for p in participants
        ],
        "documents": documents,
        "details_raw": details,
    }


def search_loops(
    query: str,
    profile_id: int | None = None,
    batch_size: int = 50,
    user_tokens: dict | None = None,
) -> list[dict[str, Any]]:
    """Search loops by name or property address (client-side filter).

    Dotloop's API doesn't support server-side address search, so we
    pull recent loops and filter by name/address match.

    Args:
        query: Search string to match against loop name and property address.
        profile_id: Dotloop profile ID (falls back to the connected user's profile).
        batch_size: Number of loops to scan (max 100).

    Returns:
        List of matching loop summary dicts.
    """
    profile_id = resolve_profile_id(profile_id, user_tokens=user_tokens)

    query_lower = query.strip().lower()

    with get_dotloop_client(user_tokens=user_tokens) as client:
        result = client.list_loops(
            profile_id,
            batch_size=min(batch_size, 100),
            sort="updated:desc",
            include_details=True,
        )
        loops = result.get("data", [])

    matches: list[dict[str, Any]] = []
    for loop in loops:
        loop_name = (loop.get("name") or "").lower()
        # Also check property address in loop details
        details = loop.get("loopDetails", {})
        prop_addr = details.get("Property Address", {})
        addr_str = " ".join(str(v) for v in prop_addr.values()).lower()

        if query_lower in loop_name or query_lower in addr_str:
            matches.append({
                "id": loop.get("id"),
                "name": loop.get("name", ""),
                "transaction_type": loop.get("transactionType", ""),
                "status": loop.get("status", ""),
                "loop_url": loop.get("loopUrl", ""),
                "updated": loop.get("updated", ""),
                "property_address": {
                    "street_number": prop_addr.get("Street Number", ""),
                    "street_name": prop_addr.get("Street Name", ""),
                    "city": prop_addr.get("City", ""),
                    "state": prop_addr.get("State/Prov", ""),
                },
            })

    return matches


async def handle_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle a Dotloop webhook event.

    LOOP_UPDATED now marks linked transactions stale for manual review.

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
        linked_transactions = await Transaction.find(
            {"dotloop_loop_id": str(loop_id)}
        ).to_list()

        updated_at = datetime.now(timezone.utc)
        for txn in linked_transactions:
            txn.dotloop_sync_status = DotloopSyncStatus.STALE
            txn.dotloop_last_remote_updated_at = updated_at
            txn.dotloop_sync_error = None
            txn.updated_at = updated_at
            await txn.save()

        return {
            "status": "processed",
            "loop_id": str(loop_id),
            "marked_stale": len(linked_transactions),
            "profile_id": str(profile_id) if profile_id else None,
        }
    except Exception as exc:
        log.error("Webhook processing failed: %s", exc)
        return {"status": "error", "reason": str(exc)}
