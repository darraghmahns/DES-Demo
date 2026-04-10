"""Profile document management API routes for D.E.S.

Handles user document upload, listing, deletion, AI extraction triggering,
and SSE streaming for extraction progress.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from auth import get_current_user
from route_helpers import _get_user_or_dev
from db import UserDocument, UserProfile
from schemas import UserDocumentType, FINANCIAL_EXTRACTION_SCHEMAS

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile-documents"])

# Directory for user-uploaded profile documents
PROFILE_UPLOADS_DIR = Path(os.getenv("PROFILE_UPLOADS_DIR", "profile_uploads"))
PROFILE_UPLOADS_DIR.mkdir(exist_ok=True)

# Max file size: 20 MB
MAX_FILE_SIZE = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif"}

# In-memory task store for profile document extractions
_extraction_tasks: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_doc(doc: UserDocument) -> dict:
    data = doc.model_dump()
    data["_id"] = str(doc.id)
    if doc.uploaded_at:
        data["uploaded_at"] = doc.uploaded_at.isoformat()
    return data


async def _compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: UserDocumentType = Query(...),
    description: Optional[str] = Query(None),
    user=Depends(get_current_user),
):
    """Upload a document to the user's profile.

    Saves the file, creates a UserDocument record, and optionally
    triggers auto-extraction if the doc_type has a financial schema.
    """
    u = await _get_user_or_dev(user)

    # Validate file extension
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type {ext} not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read and validate size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 20 MB limit")

    file_hash = await _compute_file_hash(content)

    # Check for duplicate
    existing = await UserDocument.find_one(
        UserDocument.user_id == str(u.id),
        UserDocument.file_hash == file_hash,
        UserDocument.doc_type == doc_type,
    )
    if existing:
        return {
            "message": "Document already uploaded",
            "document": _serialize_doc(existing),
            "duplicate": True,
        }

    # Save file to disk
    user_dir = PROFILE_UPLOADS_DIR / str(u.id)
    user_dir.mkdir(exist_ok=True)
    file_path = user_dir / f"{uuid.uuid4().hex}{ext}"
    file_path.write_bytes(content)

    # Create DB record
    doc = UserDocument(
        user_id=str(u.id),
        doc_type=doc_type,
        filename=file.filename or "unknown",
        file_path=str(file_path),
        file_hash=file_hash,
        file_size_bytes=len(content),
        extraction_status="pending",
        description=description,
    )
    await doc.insert()

    # Auto-trigger extraction if this doc type has a financial schema
    extraction_id = None
    if doc_type in FINANCIAL_EXTRACTION_SCHEMAS:
        extraction_id = await _start_extraction(doc)
        doc.extraction_id = extraction_id
        doc.extraction_status = "processing"
        await doc.save()

    result = {
        "document": _serialize_doc(doc),
        "duplicate": False,
    }
    if extraction_id:
        result["extraction_id"] = extraction_id
    return result


@router.get("/documents")
async def list_documents(
    doc_type: Optional[UserDocumentType] = Query(None),
    user=Depends(get_current_user),
):
    """List the current user's profile documents."""
    u = await _get_user_or_dev(user)

    query = {"user_id": str(u.id)}
    if doc_type:
        query["doc_type"] = doc_type.value

    docs = await UserDocument.find(query).sort("-uploaded_at").to_list()
    return [_serialize_doc(d) for d in docs]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str, user=Depends(get_current_user)):
    """Get a specific document's details including extraction results."""
    u = await _get_user_or_dev(user)

    doc = await UserDocument.get(doc_id)
    if not doc or doc.user_id != str(u.id):
        raise HTTPException(status_code=404, detail="Document not found")

    return _serialize_doc(doc)


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user=Depends(get_current_user)):
    """Delete a profile document and its file."""
    u = await _get_user_or_dev(user)

    doc = await UserDocument.get(doc_id)
    if not doc or doc.user_id != str(u.id):
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from disk
    try:
        Path(doc.file_path).unlink(missing_ok=True)
    except Exception as e:
        log.warning("Failed to delete file %s: %s", doc.file_path, e)

    await doc.delete()
    return {"deleted": True}


@router.post("/documents/{doc_id}/extract")
async def trigger_extraction(doc_id: str, user=Depends(get_current_user)):
    """Trigger or re-trigger AI extraction on a profile document."""
    u = await _get_user_or_dev(user)

    doc = await UserDocument.get(doc_id)
    if not doc or doc.user_id != str(u.id):
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.doc_type not in FINANCIAL_EXTRACTION_SCHEMAS:
        raise HTTPException(
            status_code=400,
            detail=f"No extraction schema for doc type: {doc.doc_type.value}",
        )

    extraction_id = await _start_extraction(doc)
    doc.extraction_id = extraction_id
    doc.extraction_status = "processing"
    doc.extracted_data = None
    doc.overall_confidence = None
    doc.citations = []
    await doc.save()

    return {"extraction_id": extraction_id, "status": "processing"}


@router.get("/documents/{doc_id}/stream")
async def stream_extraction(doc_id: str, user=Depends(get_current_user)):
    """SSE stream for extraction progress on a profile document."""
    u = await _get_user_or_dev(user)

    doc = await UserDocument.get(doc_id)
    if not doc or doc.user_id != str(u.id):
        raise HTTPException(status_code=404, detail="Document not found")

    extraction_id = doc.extraction_id
    if not extraction_id or extraction_id not in _extraction_tasks:
        raise HTTPException(status_code=404, detail="No active extraction for this document")

    return StreamingResponse(
        _sse_generator(extraction_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Extraction Engine
# ---------------------------------------------------------------------------


async def _start_extraction(doc: UserDocument) -> str:
    """Start a background extraction task for a profile document.

    Returns the extraction task ID.
    """
    extraction_id = f"profile-ext-{uuid.uuid4().hex[:12]}"

    task = {
        "id": extraction_id,
        "doc_id": str(doc.id),
        "status": "pending",
        "events": [],
        "waiters": [],
    }
    _extraction_tasks[extraction_id] = task

    # Run extraction in background
    asyncio.create_task(_run_extraction(extraction_id, doc))

    return extraction_id


async def _run_extraction(extraction_id: str, doc: UserDocument):
    """Background task: extract structured data from a financial document."""
    task = _extraction_tasks.get(extraction_id)
    if not task:
        return

    task["status"] = "running"
    total_steps = 5

    try:
        # Step 1: Load document
        _emit(task, "step", {"step": 1, "total": total_steps, "title": "Load Document", "status": "running"})
        file_path = Path(doc.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {doc.file_path}")
        _emit(task, "step_complete", {"step": 1, "title": "Load Document", "status": "complete", "data": {"filename": doc.filename}})

        # Step 2: Convert to images
        _emit(task, "step", {"step": 2, "total": total_steps, "title": "Convert to Images", "status": "running"})
        from pdf_converter import pdf_to_images, image_to_base64

        ext = file_path.suffix.lower()
        if ext == ".pdf":
            images = pdf_to_images(str(file_path))
            images_b64 = [image_to_base64(img) for img in images]
        else:
            # Image file — read directly
            import base64
            with open(file_path, "rb") as f:
                images_b64 = [base64.b64encode(f.read()).decode()]

        _emit(task, "step_complete", {"step": 2, "title": "Convert to Images", "status": "complete", "data": {"pages": len(images_b64)}})

        # Step 3: AI extraction with financial schema
        _emit(task, "step", {"step": 3, "total": total_steps, "title": "AI Extraction", "status": "running"})

        from profile_extraction import extract_financial_document
        extracted_data, usage = await extract_financial_document(
            images_b64, doc.doc_type
        )

        _emit(task, "step_complete", {"step": 3, "title": "AI Extraction", "status": "complete", "data": {"fields_extracted": len(extracted_data) if extracted_data else 0}})
        _emit(task, "extraction", {"extracted_data": extracted_data, "doc_type": doc.doc_type.value})

        # Step 4: Validate against schema
        _emit(task, "step", {"step": 4, "total": total_steps, "title": "Validate Schema", "status": "running"})

        schema_cls = FINANCIAL_EXTRACTION_SCHEMAS.get(doc.doc_type)
        validated = None
        validation_errors = []
        if schema_cls and extracted_data:
            try:
                validated = schema_cls.model_validate(extracted_data)
            except Exception as e:
                validation_errors = [str(e)]

        _emit(task, "step_complete", {"step": 4, "title": "Validate Schema", "status": "complete", "data": {"valid": not validation_errors}})
        _emit(task, "validation", {"success": not validation_errors, "errors": validation_errors})

        # Step 5: Update document record
        _emit(task, "step", {"step": 5, "total": total_steps, "title": "Save Results", "status": "running"})

        # Refresh from DB in case it was modified
        fresh_doc = await UserDocument.get(str(doc.id))
        if fresh_doc:
            fresh_doc.extraction_status = "completed"
            fresh_doc.extracted_data = validated.model_dump() if validated else extracted_data
            fresh_doc.overall_confidence = usage.get("confidence", 0.85)
            await fresh_doc.save()

            # Apply extraction results to user profile
            from profile_extraction import apply_extraction_to_profile
            await apply_extraction_to_profile(fresh_doc)

        _emit(task, "step_complete", {"step": 5, "title": "Save Results", "status": "complete", "data": {}})

        # Final complete event
        _emit(task, "complete", {
            "extraction_id": extraction_id,
            "doc_id": str(doc.id),
            "extracted_data": validated.model_dump() if validated else extracted_data,
            "status": "completed",
        })

        task["status"] = "completed"

    except Exception as e:
        log.exception("Profile document extraction failed: %s", e)
        _emit(task, "error", {"message": str(e)})
        task["status"] = "failed"

        # Update doc status
        try:
            fresh_doc = await UserDocument.get(str(doc.id))
            if fresh_doc:
                fresh_doc.extraction_status = "failed"
                await fresh_doc.save()
        except Exception:
            pass


def _emit(task: dict, event_type: str, data: dict):
    """Emit an SSE event to all waiters."""
    event = {"type": event_type, "data": data}
    task["events"].append(event)
    for waiter in task["waiters"]:
        waiter.set()


async def _sse_generator(extraction_id: str):
    """Generate SSE events for a profile extraction task."""
    task = _extraction_tasks.get(extraction_id)
    if not task:
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Task not found'}})}\n\n"
        return

    event_index = 0
    waiter = asyncio.Event()
    task["waiters"].append(waiter)

    try:
        while True:
            # Replay any events we haven't sent yet
            while event_index < len(task["events"]):
                event = task["events"][event_index]
                yield f"data: {json.dumps(event)}\n\n"
                event_index += 1

                if event["type"] in ("complete", "error"):
                    return

            # If task is done, stop
            if task["status"] in ("completed", "failed"):
                return

            # Wait for new events
            waiter.clear()
            try:
                await asyncio.wait_for(waiter.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive
                yield ": keepalive\n\n"
    finally:
        task["waiters"].remove(waiter)
