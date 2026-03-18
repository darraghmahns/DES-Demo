#!/usr/bin/env python3
"""FastAPI server wrapping the DocExtract pipeline with SSE streaming."""

import hashlib
import json
import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field, ValidationError

from pdf_converter import get_pdf_info, pdf_to_images, image_to_base64

log = logging.getLogger(__name__)
from verifier import compute_overall_confidence
from pii_scanner import scan_all_pages
from schemas import (
    DotloopLoopDetails,
    DotloopPropertyAddress,
    DotloopFinancials,
    DotloopContractDates,
    DotloopParticipant,
    ExtractionResult,
    FOIARequest,
)
from ocr_engine import get_engine
import property_prefill
from auth import get_optional_user, get_current_user, AUTH_ENABLED
from db import init_db, close_db
from db_writer import save_document, save_extraction, get_extraction
from dotloop_connector import (
    is_configured as dotloop_configured,
    process_from_dotloop,
)
from docusign_connector import (
    is_configured as docusign_configured,
    process_from_docusign,
)
from routers.integrations import router as integrations_router
from routers.integrations import _user_dotloop_tokens, _user_docusign_tokens

load_dotenv()

# ---------------------------------------------------------------------------
# Feature flags & configuration
# ---------------------------------------------------------------------------

ENABLE_GOV_MODE = os.getenv("ENABLE_GOV_MODE", "false").lower() in ("1", "true", "yes")
WRITE_DIST_FILES = os.getenv("WRITE_DIST_FILES", "true").lower() in ("1", "true", "yes")
FRONTEND_URL = os.getenv("FRONTEND_URL", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Issue 3: Fail fast if FRONTEND_URL is not set in production
    if AUTH_ENABLED and not FRONTEND_URL:
        raise RuntimeError(
            "FRONTEND_URL must be set when auth is enabled "
            "(needed for OAuth callback redirects)"
        )
    await init_db()

    # Dev mode: restore persisted OAuth tokens from the dev user profile so
    # integrations survive backend restarts without needing to re-authenticate.
    if not AUTH_ENABLED:
        from db import UserProfile
        from dotloop_connector import set_oauth_tokens as dl_set_tokens
        from docusign_connector import set_oauth_tokens as ds_set_tokens
        dev_user = await UserProfile.find_one({"email": "dev@deslabs.local"})
        if dev_user:
            if dev_user.dotloop_tokens:
                dl_set_tokens(
                    access_token=dev_user.dotloop_tokens.access_token,
                    refresh_token=dev_user.dotloop_tokens.refresh_token,
                )
                log.info("Restored Dotloop tokens from dev user profile")
            if dev_user.docusign_tokens:
                ds_set_tokens(
                    access_token=dev_user.docusign_tokens.access_token,
                    refresh_token=dev_user.docusign_tokens.refresh_token,
                )
                log.info("Restored DocuSign tokens from dev user profile")

    yield
    await close_db()


app = FastAPI(title="DESLabs API", version="1.0.0", lifespan=lifespan)

ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:5174").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(integrations_router)

# Register Phase 2 routers
from profile_routes import router as profile_router
from profile_doc_routes import router as profile_doc_router

app.include_router(profile_router)
app.include_router(profile_doc_router)

# Register Phase 3 routers
from transaction_routes import router as transaction_router
from invitation_routes import router as invitation_router

app.include_router(transaction_router)
app.include_router(invitation_router)

# Register Phase 4 router
from chat_routes import router as chat_router

app.include_router(chat_router)

# Register Clerk webhook router
from clerk_webhook import router as clerk_webhook_router

app.include_router(clerk_webhook_router)

# ---------------------------------------------------------------------------
# Demo Login (Phase 2 — bypass Clerk for @deslabs.local demo accounts)
# ---------------------------------------------------------------------------

@app.post("/api/auth/demo-login")
async def demo_login():
    """Issue a demo session token for the dev@deslabs.local user.

    No authentication required. Only issues tokens for the hardcoded
    demo account — cannot be used to impersonate arbitrary users.
    """
    from db import UserProfile
    from auth import generate_magic_link_token, sign_magic_link, _MAGIC_LINK_TTL

    demo_email = "dev@deslabs.local"
    user = await UserProfile.find_one(UserProfile.email == demo_email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Demo user not found. Run seed_demo.py first.",
        )

    raw_token = generate_magic_link_token()
    user.magic_link_token = raw_token
    user.magic_link_expires = datetime.now(timezone.utc) + timedelta(seconds=_MAGIC_LINK_TTL)
    user.last_login = datetime.now(timezone.utc)
    await user.save()

    signed = sign_magic_link(raw_token, demo_email)
    return {"demo_token": signed, "email": user.email, "name": user.name}


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

from typing import Literal as TypingLiteral
from db import VALID_STEP_IDS, OnboardingStepStatus

# Module-level flag for e2e test resets (only used when AUTH_ENABLED=False)
_e2e_onboarding_reset: bool = False
_e2e_onboarding_state: dict = {}


def _default_v2_steps() -> list[dict]:
    """Return the default v2 step list with all steps pending."""
    return [
        {"step_id": sid, "status": "pending", "completed_at": None}
        for sid in VALID_STEP_IDS
    ]


def _coerce_completed_at(value) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _normalize_v2_step_statuses(
    step_statuses,
    *,
    completed: bool,
    completed_at,
) -> list[OnboardingStepStatus]:
    """Normalize stored onboarding steps to the current VALID_STEP_IDS schema."""
    completed_iso = _coerce_completed_at(completed_at)
    valid_statuses = {"pending", "completed", "skipped"}
    existing: dict[str, OnboardingStepStatus] = {}

    for step in step_statuses or []:
        step_id = getattr(step, "step_id", None)
        status = getattr(step, "status", None)
        step_completed_at = _coerce_completed_at(getattr(step, "completed_at", None))

        if step_id not in VALID_STEP_IDS or step_id in existing:
            continue
        if status not in valid_statuses:
            status = "pending"

        existing[step_id] = OnboardingStepStatus(
            step_id=step_id,
            status=status,
            completed_at=step_completed_at if status == "completed" else None,
        )

    normalized: list[OnboardingStepStatus] = []
    for step_id in VALID_STEP_IDS:
        if step_id in existing:
            normalized.append(existing[step_id])
        elif completed:
            normalized.append(
                OnboardingStepStatus(
                    step_id=step_id,
                    status="completed",
                    completed_at=completed_iso,
                )
            )
        else:
            normalized.append(
                OnboardingStepStatus(
                    step_id=step_id,
                    status="pending",
                    completed_at=None,
                )
            )

    return normalized


def _all_steps_resolved(step_statuses: list[OnboardingStepStatus]) -> bool:
    return all(step.status in ("completed", "skipped") for step in step_statuses)


def _next_pending_step_index(step_statuses: list[OnboardingStepStatus]) -> int:
    for index, step in enumerate(step_statuses):
        if step.status == "pending":
            return index
    return len(VALID_STEP_IDS)


def _step_signature(step_statuses: list[OnboardingStepStatus]) -> list[tuple[str, str, Optional[str]]]:
    return [
        (step.step_id, step.status, step.completed_at)
        for step in step_statuses
    ]


async def _reconcile_user_onboarding_state(user) -> None:
    """Repair stale onboarding state to the current 5-step schema."""
    completed = bool(user.onboarding_completed)
    completed_at = user.onboarding_completed_at

    normalized_steps = _normalize_v2_step_statuses(
        user.onboarding_step_statuses,
        completed=completed,
        completed_at=completed_at,
    )

    if not completed and _all_steps_resolved(normalized_steps):
        completed = True

    if completed and completed_at is None:
        completed_at = datetime.now(timezone.utc)

    if completed:
        normalized_steps = _normalize_v2_step_statuses(
            normalized_steps,
            completed=True,
            completed_at=completed_at,
        )
        current_step = len(VALID_STEP_IDS)
    else:
        completed_at = None
        current_step = _next_pending_step_index(normalized_steps)

    skipped_steps = [step.step_id for step in normalized_steps if step.status == "skipped"]

    changed = (
        user.onboarding_version != 2
        or user.onboarding_completed != completed
        or user.onboarding_completed_at != completed_at
        or user.onboarding_current_step != current_step
        or user.onboarding_skipped_steps != skipped_steps
        or _step_signature(user.onboarding_step_statuses or []) != _step_signature(normalized_steps)
    )

    if not changed:
        return

    user.onboarding_version = 2
    user.onboarding_completed = completed
    user.onboarding_completed_at = completed_at
    user.onboarding_current_step = current_step
    user.onboarding_skipped_steps = skipped_steps
    user.onboarding_step_statuses = normalized_steps
    await user.save()


def _build_v2_status_response(user, dotloop_connected: bool, docusign_connected: bool) -> dict:
    """Build the v2 onboarding status response from a UserProfile."""
    steps = [
        {
            "step_id": s.step_id,
            "status": s.status,
            "completed_at": s.completed_at,
        }
        for s in _normalize_v2_step_statuses(
            user.onboarding_step_statuses,
            completed=bool(user.onboarding_completed),
            completed_at=user.onboarding_completed_at,
        )
    ]

    return {
        "version": 2,
        "completed": user.onboarding_completed,
        "completed_at": user.onboarding_completed_at.isoformat() if user.onboarding_completed_at else None,
        "current_step": user.onboarding_current_step,
        "steps": steps,
        "dotloop_connected": dotloop_connected,
        "docusign_connected": docusign_connected,
    }


@app.get("/api/onboarding/status")
async def onboarding_status(user=Depends(get_current_user)):
    """Return onboarding completion state and integration status for the wizard.

    v2 response includes step-level progress. Migration logic:
    - v1 completed users: return completed=True (don't force re-onboarding)
    - v1 mid-flow users (not completed): upgrade to v2, start at step 0
    """
    if not user:
        # Auth disabled — check e2e reset flag
        if _e2e_onboarding_reset:
            return {
                "version": 2,
                "completed": _e2e_onboarding_state.get("completed", False),
                "completed_at": _e2e_onboarding_state.get("completed_at"),
                "current_step": _e2e_onboarding_state.get("current_step", 0),
                "steps": _e2e_onboarding_state.get("steps", _default_v2_steps()),
                "dotloop_connected": False,
                "docusign_connected": False,
            }
        # Default: auth disabled, no onboarding needed
        return {
            "version": 2,
            "completed": True,
            "completed_at": None,
            "current_step": len(VALID_STEP_IDS),
            "steps": [
                {"step_id": sid, "status": "completed", "completed_at": None}
                for sid in VALID_STEP_IDS
            ],
            "dotloop_connected": False,
            "docusign_connected": False,
        }

    dotloop_connected = bool(user.dotloop_tokens and user.dotloop_tokens.access_token)
    docusign_connected = bool(user.docusign_tokens and user.docusign_tokens.access_token)

    await _reconcile_user_onboarding_state(user)

    return _build_v2_status_response(user, dotloop_connected, docusign_connected)


class OnboardingStepUpdate(BaseModel):
    step_id: str
    status: TypingLiteral["completed", "skipped"]


@app.patch("/api/onboarding/step")
async def onboarding_step_update(request: OnboardingStepUpdate, user=Depends(get_current_user)):
    """Mark a single onboarding step as completed or skipped, advance current_step."""
    if not user:
        # Auth disabled — update e2e state if reset flag is active
        if _e2e_onboarding_reset:
            if request.step_id not in VALID_STEP_IDS:
                raise HTTPException(status_code=400, detail=f"Invalid step_id: {request.step_id}")
            steps = _e2e_onboarding_state.get("steps", _default_v2_steps())
            now_iso = datetime.now(timezone.utc).isoformat()
            for s in steps:
                if s["step_id"] == request.step_id:
                    s["status"] = request.status
                    s["completed_at"] = now_iso if request.status == "completed" else None
                    break
            _e2e_onboarding_state["steps"] = steps
            # Advance current_step to next pending step
            next_step = len(VALID_STEP_IDS)
            for i, s in enumerate(steps):
                if s["status"] == "pending":
                    next_step = i
                    break
            _e2e_onboarding_state["current_step"] = next_step
            # Check if all done
            all_done = all(s["status"] in ("completed", "skipped") for s in steps)
            if all_done:
                _e2e_onboarding_state["completed"] = True
                _e2e_onboarding_state["completed_at"] = now_iso
            return {
                "version": 2,
                "completed": _e2e_onboarding_state.get("completed", False),
                "completed_at": _e2e_onboarding_state.get("completed_at"),
                "current_step": _e2e_onboarding_state["current_step"],
                "steps": steps,
            }
        return {"completed": True}

    # Validate step_id
    if request.step_id not in VALID_STEP_IDS:
        raise HTTPException(status_code=400, detail=f"Invalid step_id: {request.step_id}")

    await _reconcile_user_onboarding_state(user)

    # Update the step
    now_iso = datetime.now(timezone.utc).isoformat()
    found = False
    for step in user.onboarding_step_statuses:
        if step.step_id == request.step_id:
            step.status = request.status
            step.completed_at = now_iso if request.status == "completed" else None
            found = True
            break

    if not found:
        raise HTTPException(status_code=400, detail=f"Step {request.step_id} not found in user state")

    # Advance current_step to the index of the next pending step
    next_step = len(VALID_STEP_IDS)
    for i, step in enumerate(user.onboarding_step_statuses):
        if step.status == "pending":
            next_step = i
            break
    user.onboarding_current_step = next_step

    # If all steps are completed/skipped, mark onboarding as done
    all_done = all(s.status in ("completed", "skipped") for s in user.onboarding_step_statuses)
    if all_done and not user.onboarding_completed:
        user.onboarding_completed = True
        user.onboarding_completed_at = datetime.now(timezone.utc)
        # Sync skipped_steps for backward compat
        user.onboarding_skipped_steps = [
            s.step_id for s in user.onboarding_step_statuses if s.status == "skipped"
        ]

    await user.save()

    dotloop_connected = bool(user.dotloop_tokens and user.dotloop_tokens.access_token)
    docusign_connected = bool(user.docusign_tokens and user.docusign_tokens.access_token)
    return _build_v2_status_response(user, dotloop_connected, docusign_connected)


class OnboardingCompleteRequest(BaseModel):
    skipped_steps: List[str] = Field(default_factory=list)


@app.patch("/api/onboarding/complete")
async def onboarding_complete(request: OnboardingCompleteRequest, user=Depends(get_current_user)):
    """Mark onboarding as completed. Idempotent — won't overwrite existing timestamp.

    Backward compat endpoint (v1). Also syncs v2 step statuses when invoked.
    """
    if not user:
        return {"completed": True}
    if not user.onboarding_completed:
        valid_skipped_steps = [
            step_id for step_id in request.skipped_steps if step_id in VALID_STEP_IDS
        ]
        user.onboarding_completed = True
        user.onboarding_completed_at = datetime.now(timezone.utc)
        user.onboarding_skipped_steps = valid_skipped_steps

        # Sync v2 step statuses
        now_iso = user.onboarding_completed_at.isoformat()
        user.onboarding_version = 2
        user.onboarding_step_statuses = [
            OnboardingStepStatus(
                step_id=sid,
                status="skipped" if sid in valid_skipped_steps else "completed",
                completed_at=now_iso if sid not in valid_skipped_steps else None,
            )
            for sid in VALID_STEP_IDS
        ]
        user.onboarding_current_step = len(VALID_STEP_IDS)

        await user.save()
    return {
        "completed": user.onboarding_completed,
        "completed_at": user.onboarding_completed_at.isoformat() if user.onboarding_completed_at else None,
    }


@app.post("/api/test/reset-onboarding")
async def test_reset_onboarding(user=Depends(get_current_user)):
    """Reset onboarding state for e2e testing. Only works when AUTH_ENABLED=False."""
    global _e2e_onboarding_reset, _e2e_onboarding_state

    if AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="Only available when AUTH_ENABLED=False")

    # When auth is disabled, user is None — reset the e2e state
    _e2e_onboarding_reset = True
    _e2e_onboarding_state = {
        "completed": False,
        "completed_at": None,
        "current_step": 0,
        "steps": _default_v2_steps(),
    }
    return {"reset": True, "version": 2}


@app.post("/api/test/complete-onboarding")
async def test_complete_onboarding(user=Depends(get_current_user)):
    """Mark onboarding as completed for e2e testing. Only works when AUTH_ENABLED=False.

    Clears the e2e reset flag, returning to the default state where auth-disabled
    mode returns completed=True. This ensures subsequent test specs don't see the wizard.
    """
    global _e2e_onboarding_reset, _e2e_onboarding_state

    if AUTH_ENABLED:
        raise HTTPException(status_code=403, detail="Only available when AUTH_ENABLED=False")

    _e2e_onboarding_reset = False
    _e2e_onboarding_state = {}
    return {"completed": True, "version": 2}


TEST_DOCS_DIR = Path(__file__).parent / "test_docs"
DIST_DIR = Path(__file__).parent / "dist"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ExtractRequest(BaseModel):
    mode: str  # "real_estate" or "gov"
    filename: str  # e.g. "sample_purchase_agreement.pdf"


class DocumentInfo(BaseModel):
    name: str
    size_human: str
    pages: int


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def sse_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def _classify_document(filename: str) -> str:
    """Classify a PDF as 'gov' or 'real_estate' based on filename."""
    lower = filename.lower()
    gov_keywords = ("foia", "gov", "freedom", "fbi", "epa", "records_request")
    if any(kw in lower for kw in gov_keywords):
        return "gov"
    return "real_estate"


@app.get("/api/documents")
async def list_documents(mode: str | None = None) -> list[DocumentInfo]:
    """List available PDF documents in test_docs/, optionally filtered by mode."""
    docs: list[DocumentInfo] = []
    if not TEST_DOCS_DIR.exists():
        return docs
    for pdf in sorted(TEST_DOCS_DIR.glob("*.pdf")):
        doc_mode = _classify_document(pdf.name)
        if mode and doc_mode != mode:
            continue
        if not ENABLE_GOV_MODE and doc_mode == "gov":
            continue
        info = get_pdf_info(str(pdf))
        docs.append(DocumentInfo(
            name=pdf.name,
            size_human=info["size_human"],
            pages=info["pages"],
        ))
    return docs


@app.get("/api/documents/{name}")
async def get_document(name: str):
    """Serve a PDF file for inline preview."""
    pdf_path = TEST_DOCS_DIR / name
    if not pdf_path.exists() or not pdf_path.suffix.lower() == ".pdf":
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename={name}",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    mode: str = Query("real_estate"),
    user=Depends(get_current_user),
):
    """Upload a PDF document for extraction."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    TEST_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    dest = TEST_DOCS_DIR / file.filename
    contents = await file.read()
    dest.write_bytes(contents)

    info = await asyncio.to_thread(get_pdf_info, str(dest))
    return {
        "filename": file.filename,
        "pages": info["pages"],
        "size_human": info["size_human"],
    }


@app.post("/api/extract")
async def extract(request: ExtractRequest, user=Depends(get_current_user)):
    """Start the extraction pipeline as a background task, return task_id.

    The extraction runs independently of the HTTP connection.
    Use GET /api/extract/{task_id}/stream to subscribe to SSE events.
    """
    from task_manager import create_task, get_active_task, TaskStatus

    pdf_path = TEST_DOCS_DIR / request.filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    allowed_modes = ["real_estate"]
    if ENABLE_GOV_MODE:
        allowed_modes.append("gov")
    if request.mode not in allowed_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Allowed: {allowed_modes}")

    # Check for already-running task for this file+mode
    existing = get_active_task(request.mode, request.filename)
    if existing:
        return {"task_id": existing.task_id, "status": existing.status.value}

    # Create and launch background task
    user_id = user.clerk_user_id if user else None
    org_id = user.org_id if user else None
    task = create_task(request.mode, request.filename)
    asyncio_task = asyncio.create_task(
        _run_extraction_task(task, request.mode, str(pdf_path), user_id=user_id, org_id=org_id)
    )
    task._asyncio_task = asyncio_task

    return {"task_id": task.task_id, "status": "pending"}


@app.get("/api/extract/{task_id}/stream")
async def extract_stream(task_id: str, user=Depends(get_optional_user)):
    """Reconnectable SSE stream for a background extraction task.

    Replays all past events, then streams new ones in real time.
    Disconnecting does NOT stop the extraction — reconnect to resume.
    """
    from task_manager import get_task

    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return StreamingResponse(
        _task_sse_stream(task),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/extract/{task_id}/status")
async def extract_task_status(task_id: str):
    """Get current status of an extraction task."""
    from task_manager import get_task

    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task.task_id,
        "mode": task.mode,
        "filename": task.filename,
        "status": task.status.value,
        "event_count": len(task.events),
    }


@app.get("/api/tasks")
async def list_extraction_tasks():
    """List all extraction tasks."""
    from task_manager import list_tasks
    return {"tasks": list_tasks()}


async def _task_sse_stream(task) -> AsyncGenerator[str, None]:
    """SSE generator that replays past events and streams new ones."""
    from task_manager import TaskStatus

    cursor = 0
    waiter = task.add_waiter()

    try:
        while True:
            # Yield all events we haven't sent yet
            while cursor < len(task.events):
                ev = task.events[cursor]
                yield sse_event(ev["type"], ev["data"])
                cursor += 1

            # If task is done, stop streaming
            if task.status in (TaskStatus.COMPLETE, TaskStatus.ERROR):
                break

            # Wait for new events
            waiter.clear()
            try:
                await asyncio.wait_for(waiter.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send keepalive comment to prevent proxy timeouts
                yield ": keepalive\n\n"
    finally:
        task.remove_waiter(waiter)


async def _run_extraction_task(task, mode: str, pdf_path: str, user_id: str | None = None, org_id: str | None = None) -> None:
    """Run the extraction pipeline as a background task, storing events."""
    from task_manager import TaskStatus, cleanup_old_tasks

    task.status = TaskStatus.RUNNING

    def emit(event_type: str, data: dict) -> None:
        task.append_event({"type": event_type, "data": data})

    await _extraction_pipeline(mode, pdf_path, emit, user_id=user_id, org_id=org_id)

    # Mark final status based on last event
    if task.events and task.events[-1]["type"] == "error":
        task.mark_complete(TaskStatus.ERROR)
    else:
        task.mark_complete(TaskStatus.COMPLETE)

    cleanup_old_tasks()


async def _extraction_pipeline(
    mode: str, pdf_path: str, emit,
    user_id: str | None = None, org_id: str | None = None,
) -> None:
    """Core extraction pipeline logic, decoupled from SSE streaming.

    Args:
        mode: 'real_estate' or 'gov'
        pdf_path: Absolute path to the PDF file
        emit: Callable(event_type: str, data: dict) to publish events
    """
    total_steps = 5  # Load, Convert, Extract, Validate, Output
    total_steps += 1  # Verify citations
    if mode == "real_estate":
        if property_prefill.is_configured():
            total_steps += 1  # Property enrichment
    if mode == "gov":
        total_steps += 1  # PII scan

    current_step = 0
    _start_time = time.monotonic()

    # Accumulate API token usage across all steps
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _add_usage(usage: dict) -> None:
        for k in total_usage:
            total_usage[k] += usage.get(k, 0)

    try:
        # --- Step 1: Load Document ---
        current_step += 1
        emit("step", {
            "step": current_step, "total": total_steps,
            "title": "Load Document", "status": "running",
        })
        await asyncio.sleep(0.05)

        file_info = await asyncio.to_thread(get_pdf_info, pdf_path)
        file_hash = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()

        emit("step_complete", {
            "step": current_step, "title": "Load Document", "status": "complete",
            "data": file_info,
        })

        # --- Step 2: Convert to Images ---
        current_step += 1
        emit("step", {
            "step": current_step, "total": total_steps,
            "title": "Convert to Images", "status": "running",
        })

        images = await asyncio.to_thread(pdf_to_images, pdf_path)
        images_b64 = [image_to_base64(img) for img in images]

        emit("step_complete", {
            "step": current_step, "title": "Convert to Images", "status": "complete",
            "data": {"pages_converted": len(images)},
        })

        # --- Step 3: Neural OCR Extraction ---
        current_step += 1
        emit("step", {
            "step": current_step, "total": total_steps,
            "title": "Neural OCR Extraction", "status": "running",
        })

        engine = get_engine()
        use_file = engine.prefers_file_path
        if use_file:
            raw_extraction, extract_usage = await asyncio.to_thread(
                engine.extract_from_file, pdf_path, mode,
            )
        else:
            raw_extraction, extract_usage = await asyncio.to_thread(
                engine.extract, images_b64, mode,
            )
        _add_usage(extract_usage)

        emit("step_complete", {
            "step": current_step, "title": "Neural OCR Extraction", "status": "complete",
            "data": {"fields_extracted": len(raw_extraction)},
        })

        # --- Step 4: Validate Schema ---
        current_step += 1
        emit("step", {
            "step": current_step, "total": total_steps,
            "title": "Validate Schema", "status": "running",
        })

        validated = None
        validated_data = None
        validation_errors: list[str] = []

        try:
            if mode == "real_estate":
                validated = DotloopLoopDetails.model_validate(raw_extraction)
            else:
                validated = FOIARequest.model_validate(raw_extraction)
            validated_data = validated.model_dump(mode="json")
        except ValidationError as e:
            for err in e.errors():
                loc = " -> ".join(str(x) for x in err["loc"])
                validation_errors.append(f"{loc}: {err['msg']}")
            validated_data = raw_extraction

        # Lenient fallback: build partial model even when strict validation fails
        lenient_validated = None
        if mode == "real_estate" and validated is None:
            try:
                nested = dict(raw_extraction)
                if isinstance(nested.get("property_address"), dict):
                    nested["property_address"] = DotloopPropertyAddress.model_construct(**nested["property_address"])
                if isinstance(nested.get("financials"), dict):
                    nested["financials"] = DotloopFinancials.model_construct(**nested["financials"])
                if isinstance(nested.get("contract_dates"), dict):
                    nested["contract_dates"] = DotloopContractDates.model_construct(**nested["contract_dates"])
                if isinstance(nested.get("participants"), list):
                    nested["participants"] = [
                        DotloopParticipant.model_construct(**p) if isinstance(p, dict) else p
                        for p in nested["participants"]
                    ]
                lenient_validated = DotloopLoopDetails.model_construct(**nested)
            except (TypeError, KeyError, ValidationError):
                pass

        emit("extraction", {"validated_data": validated_data})
        emit("validation", {
            "success": len(validation_errors) == 0,
            "errors": validation_errors,
        })
        emit("step_complete", {
            "step": current_step, "title": "Validate Schema", "status": "complete",
            "data": {"success": len(validation_errors) == 0, "error_count": len(validation_errors)},
        })

        # --- Step 5: Verify Citations ---
        current_step += 1
        emit("step", {
            "step": current_step, "total": total_steps,
            "title": "Verify Citations", "status": "running",
        })

        if use_file:
            citations, verify_usage = await asyncio.to_thread(
                engine.verify_from_file, pdf_path, validated_data,
            )
        else:
            citations, verify_usage = await asyncio.to_thread(
                engine.verify, images_b64, validated_data,
            )
        _add_usage(verify_usage)
        overall_confidence = compute_overall_confidence(citations)

        citations_data = [c.model_dump(mode="json") for c in citations]

        emit("citations", {
            "citations": citations_data,
            "overall_confidence": overall_confidence,
        })
        emit("step_complete", {
            "step": current_step, "title": "Verify Citations", "status": "complete",
            "data": {"citation_count": len(citations), "overall_confidence": overall_confidence},
        })

        # --- Property Enrichment (real_estate, when Regrid configured) ---
        property_enrichment_data = None
        if mode == "real_estate" and property_prefill.is_configured():
            current_step += 1
            emit("step", {
                "step": current_step, "total": total_steps,
                "title": "Property Enrichment", "status": "running",
            })

            addr = (validated_data or {}).get("property_address", {})
            enrichment = await property_prefill.enrich_property(addr if isinstance(addr, dict) else {})

            if enrichment and enrichment.parcel_id:
                # Auto-populate parcel_tax_id if the extraction didn't capture it
                if validated_data and isinstance(validated_data.get("property_address"), dict):
                    if not validated_data["property_address"].get("parcel_tax_id"):
                        validated_data["property_address"]["parcel_tax_id"] = enrichment.parcel_id

            property_enrichment_data = enrichment
            log.info("Property enrichment result: match_quality=%s, parcel_id=%s",
                     enrichment.match_quality if enrichment else "none",
                     enrichment.parcel_id if enrichment else None)

            emit("property_enrichment", {
                "match_quality": enrichment.match_quality if enrichment else "none",
                "parcel_id": enrichment.parcel_id if enrichment else None,
                "assessed_total": enrichment.assessed_total if enrichment else None,
                "year_built": enrichment.year_built if enrichment else None,
                "lot_size_acres": enrichment.lot_size_acres if enrichment else None,
                "zoning": enrichment.zoning if enrichment else None,
                "owner_name": enrichment.owner_name if enrichment else None,
            })
            emit("step_complete", {
                "step": current_step, "title": "Property Enrichment", "status": "complete",
                "data": {
                    "match_quality": enrichment.match_quality if enrichment else "none",
                    "parcel_id": enrichment.parcel_id if enrichment else None,
                },
            })

        # --- PII Scan (gov mode only) ---
        pii_report = None
        if mode == "gov":
            current_step += 1
            emit("step", {
                "step": current_step, "total": total_steps,
                "title": "PII Scan", "status": "running",
            })

            if use_file:
                page_texts, ocr_usage = await asyncio.to_thread(
                    engine.ocr_raw_text_from_file, pdf_path,
                )
            else:
                page_texts, ocr_usage = await asyncio.to_thread(
                    engine.ocr_raw_text, images_b64,
                )
            _add_usage(ocr_usage)
            pii_report = scan_all_pages(page_texts)

            emit("pii", {
                "findings": [f.model_dump(mode="json") for f in pii_report.findings],
                "risk_score": pii_report.pii_risk_score,
                "risk_level": pii_report.risk_level.value,
            })
            emit("step_complete", {
                "step": current_step, "title": "PII Scan", "status": "complete",
                "data": {
                    "finding_count": len(pii_report.findings),
                    "risk_score": pii_report.pii_risk_score,
                },
            })

        # --- Final Step: Output ---
        current_step += 1
        emit("step", {
            "step": current_step, "total": total_steps,
            "title": "Output", "status": "running",
        })

        dotloop_api_payload = None
        docusign_api_payload = None
        if mode == "real_estate":
            source = validated or lenient_validated
            if source:
                try:
                    dotloop_api_payload = source.to_dotloop_api_format()
                except (AttributeError, ValueError, KeyError) as e:
                    log.warning("Dotloop API format failed: %s", e)
                try:
                    docusign_api_payload = source.to_docusign_api_format()
                except (AttributeError, ValueError, KeyError) as e:
                    log.warning("DocuSign API format failed: %s", e)

        # Compute cost: GPT-4o pricing ($2.50/1M input, $10.00/1M output)
        cost_usd = (
            total_usage["prompt_tokens"] * 2.50 / 1_000_000
            + total_usage["completion_tokens"] * 10.00 / 1_000_000
        )

        result = ExtractionResult(
            mode=mode,
            source_file=Path(pdf_path).name,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            pages_processed=len(images),
            dotloop_data=validated_data if mode == "real_estate" else None,
            foia_data=validated_data if mode == "gov" else None,
            dotloop_api_payload=dotloop_api_payload,
            docusign_api_payload=docusign_api_payload,
            citations=citations,
            overall_confidence=overall_confidence,
            pii_report=pii_report,
            compliance_report=None,
            property_enrichment=property_enrichment_data,
            prompt_tokens=total_usage["prompt_tokens"],
            completion_tokens=total_usage["completion_tokens"],
            total_tokens=total_usage["total_tokens"],
            cost_usd=round(cost_usd, 6),
        )

        # Write to dist/ (disabled in production via WRITE_DIST_FILES=false)
        output_path = DIST_DIR / f"{Path(pdf_path).stem}_extracted.json"
        if WRITE_DIST_FILES:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result.model_dump_json(indent=2))

        # Persist to MongoDB
        duration_ms = int((time.monotonic() - _start_time) * 1000)
        extraction_id = None
        try:
            doc_id = await save_document(
                Path(pdf_path).name,
                mode,
                len(images),
                Path(pdf_path).stat().st_size,
                file_hash=file_hash,
                file_path=str(Path(pdf_path).resolve()),
                user_id=user_id,
                org_id=org_id,
            )
            ext_id = await save_extraction(
                doc_id,
                result,
                engine.name,
                duration_ms,
            )
            extraction_id = str(ext_id)
        except Exception as db_err:
            log.warning("DB save failed: %s", db_err)

        emit("step_complete", {
            "step": current_step, "title": "Output", "status": "complete",
            "data": {"output_path": str(output_path)},
        })

        complete_data = result.model_dump(mode="json")
        if extraction_id:
            complete_data["extraction_id"] = extraction_id
        emit("complete", complete_data)

    except Exception as e:
        emit("error", {"message": str(e)})


# ---------------------------------------------------------------------------
# Extraction Cache Endpoint
# ---------------------------------------------------------------------------

@app.get("/api/extractions/cached")
async def check_cached_extraction(
    file_hash: str = Query(...),
    mode: str = Query("real_estate"),
):
    """Check if a document with this hash and mode has already been extracted."""
    from db import DocumentRecord

    doc = await DocumentRecord.find_one({"file_hash": file_hash, "mode": mode})
    if not doc or not doc.extractions:
        return {"cached": False}

    # Return the latest extraction
    from db_writer import get_extraction
    ext_ref = f"{doc.id}:{len(doc.extractions) - 1}"
    ext_data = await get_extraction(ext_ref)
    if not ext_data:
        return {"cached": False}

    return {"cached": True, "extraction": ext_data}


@app.delete("/api/extractions/cache")
async def clear_extraction_cache(mode: str = Query(None), user=Depends(get_current_user)):
    """Clear cached extractions, optionally filtered by mode. Scoped to user/org."""
    from db import DocumentRecord

    filters: dict = {}
    if mode:
        filters["mode"] = mode

    # Scope to user's org or own documents
    if user:
        if user.org_id:
            filters["org_id"] = user.org_id
        else:
            filters["$or"] = [
                {"user_id": user.clerk_user_id},
                {"user_id": None},
            ]

    docs = await DocumentRecord.find(filters).to_list()
    deleted_count = 0
    for doc in docs:
        await doc.delete()
        deleted_count += 1

    return {"deleted": deleted_count, "mode": mode or "all"}


@app.get("/api/extractions")
async def get_extractions(mode: str | None = None, limit: int = Query(50), user=Depends(get_optional_user)):
    """List recent extractions with metadata for dropdown selection."""
    from db_writer import list_extractions
    user_id = user.clerk_user_id if user else None
    org_id = user.org_id if user else None
    results = await list_extractions(mode=mode, limit=limit, user_id=user_id, org_id=org_id)
    return {"extractions": results}


@app.delete("/api/extractions/{doc_id}")
async def delete_extraction(doc_id: str, user=Depends(get_current_user)):
    """Permanently delete a DocumentRecord and remove it from any linked transactions."""
    from db import DocumentRecord, Transaction
    doc = await DocumentRecord.get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Extraction not found")
    # Remove from any transactions that reference this doc
    async for txn in Transaction.find({"extraction_ids": doc_id}):
        txn.extraction_ids = [eid for eid in txn.extraction_ids if eid != doc_id]
        await txn.save()
    await doc.delete()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Batch Extraction (Multi-Source)
# ---------------------------------------------------------------------------


class BatchSource(BaseModel):
    type: str  # "dotloop" or "docusign"
    id: str    # loop_id or envelope_id


class BatchExtractRequest(BaseModel):
    sources: list[BatchSource]


@app.post("/api/extract-batch")
async def extract_batch(request: BatchExtractRequest, user=Depends(get_current_user)):
    """Extract from multiple Dotloop loops / DocuSign envelopes in parallel.

    Runs process_from_dotloop / process_from_docusign concurrently and
    returns a list of extraction results (or errors) for each source.
    """
    if not request.sources:
        raise HTTPException(status_code=400, detail="No sources provided")
    if len(request.sources) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 sources per batch")

    dl_tokens = _user_dotloop_tokens(user)
    ds_tokens = _user_docusign_tokens(user)

    async def _process_one(source: BatchSource) -> dict:
        try:
            if source.type == "dotloop":
                if not dotloop_configured(user_tokens=dl_tokens, allow_fallback=not AUTH_ENABLED):
                    return {"source": source.model_dump(), "error": "Dotloop not configured"}
                result = await process_from_dotloop(loop_id=int(source.id), user_tokens=dl_tokens)
                return {"source": source.model_dump(), **result}
            elif source.type == "docusign":
                if not docusign_configured(user_tokens=ds_tokens):
                    return {"source": source.model_dump(), "error": "DocuSign not configured"}
                result = await process_from_docusign(envelope_id=source.id, user_tokens=ds_tokens)
                return {"source": source.model_dump(), **result}
            else:
                return {"source": source.model_dump(), "error": f"Unknown source type: {source.type}"}
        except Exception as e:
            return {"source": source.model_dump(), "error": str(e)}

    results = await asyncio.gather(
        *[_process_one(s) for s in request.sources],
        return_exceptions=False,
    )

    extraction_ids = [
        r.get("extraction_id") for r in results if r.get("extraction_id")
    ]

    return {
        "results": results,
        "extraction_ids": extraction_ids,
        "total": len(request.sources),
        "succeeded": len(extraction_ids),
    }


# ---------------------------------------------------------------------------
# Comparison Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/comparisons")
async def create_comparison(
    from_extraction_id: str = Query(..., description="Extraction ID of the base document"),
    to_extraction_id: str = Query(..., description="Extraction ID of the document to compare"),
    user=Depends(get_optional_user),
):
    """Compare two document extractions and return field-level deltas.

    Designed for Julie's workflow: comparing an offer with a counteroffer,
    or an inspection notice with an inspection response.
    """
    from comparison_engine import compare_extractions

    # Load both extractions from DB
    from_data = await get_extraction(from_extraction_id)
    if not from_data:
        raise HTTPException(status_code=404, detail=f"Extraction {from_extraction_id} not found")

    to_data = await get_extraction(to_extraction_id)
    if not to_data:
        raise HTTPException(status_code=404, detail=f"Extraction {to_extraction_id} not found")

    result = compare_extractions(
        from_data=from_data,
        to_data=to_data,
        from_extraction_id=from_extraction_id,
        to_extraction_id=to_extraction_id,
        from_source=from_data.get("source_file"),
        to_source=to_data.get("source_file"),
    )

    return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Offer Comparison (N-way)
# ---------------------------------------------------------------------------
#
# FIELD_REGISTRY is the single source of truth for what we can display.
# Each entry maps a dot-notation path into extracted_data → a display key.
# To add a new displayed field: add one entry here. That's it.
#
# Participant paths use the pattern  participants.<role_lowercase>.<field>
# Everything extracted by the LLM that is NOT in the registry is still
# returned as raw_extras so nothing is silently dropped.
# ---------------------------------------------------------------------------

FIELD_REGISTRY = [
    # Parties
    {"path": "participants.buyer.full_name",          "key": "buyer_name",          "label": "Buyer's Name",       "type": "string", "group": "Parties"},
    {"path": "participants.buyer.email",              "key": "buyer_email",         "label": "Buyer Email",        "type": "string", "group": "Parties"},
    {"path": "participants.buyer.phone",              "key": "buyer_phone",         "label": "Buyer Phone",        "type": "string", "group": "Parties"},
    {"path": "participants.seller.full_name",         "key": "seller_name",         "label": "Seller Name",        "type": "string", "group": "Parties"},
    {"path": "participants.seller.email",             "key": "seller_email",        "label": "Seller Email",       "type": "string", "group": "Parties"},
    {"path": "participants.buying_agent.full_name",   "key": "agent_name",          "label": "Agent Name",         "type": "string", "group": "Parties"},
    {"path": "participants.buying_agent.email",       "key": "agent_email",         "label": "Agent Email",        "type": "string", "group": "Parties"},
    {"path": "participants.buying_agent.phone",       "key": "agent_phone",         "label": "Agent Phone",        "type": "string", "group": "Parties"},
    {"path": "participants.buying_agent.company_name","key": "agent_company",       "label": "Agent Company",      "type": "string", "group": "Parties"},
    {"path": "participants.listing_agent.full_name",  "key": "listing_agent_name",  "label": "Listing Agent",      "type": "string", "group": "Parties"},
    {"path": "participants.listing_agent.email",      "key": "listing_agent_email", "label": "Listing Agent Email","type": "string", "group": "Parties"},
    # Financials
    {"path": "financials.purchase_price",        "key": "purchase_price",        "label": "Purchase Price",             "type": "currency", "group": "Financials"},
    {"path": "financials.earnest_money_amount",  "key": "earnest_money_amount",  "label": "Earnest Money",              "type": "currency", "group": "Financials"},
    {"path": "financials.earnest_money_held_by", "key": "earnest_money_held_by", "label": "Earnest Money Held By",      "type": "string",   "group": "Financials"},
    {"path": "financials.down_payment_amount",     "key": "down_payment_amount",     "label": "Down Payment ($)",           "type": "currency", "group": "Financials"},
    {"path": "financials.down_payment_percentage","key": "down_payment_percentage", "label": "Down Payment (%)",           "type": "string",   "group": "Financials"},
    {"path": "financials.financing_type",        "key": "financing_type",        "label": "Financing Terms / Loan Type","type": "string",   "group": "Financials"},
    {"path": "financials.sale_commission_rate",  "key": "sale_commission_rate",  "label": "Commission Rate",            "type": "string",   "group": "Financials"},
    {"path": "financials.sale_commission_total", "key": "sale_commission_total", "label": "Commission Total",           "type": "currency", "group": "Financials"},
    {"path": "financials.closing_fee_paid_by",   "key": "closing_fee_paid_by",   "label": "Title Company Closing Fee",  "type": "string",   "group": "Financials"},
    {"path": "financials.fincen_fee_paid_by",    "key": "fincen_fee_paid_by",    "label": "FinCEN Reports Fee (503)",   "type": "string",   "group": "Financials"},
    # Property
    {"path": "property_address.mls_number",    "key": "mls_number",    "label": "MLS Number",   "type": "string", "group": "Property"},
    {"path": "property_address.county",        "key": "county",        "label": "County",       "type": "string", "group": "Property"},
    {"path": "property_address.parcel_tax_id", "key": "parcel_tax_id", "label": "Parcel/Tax ID","type": "string", "group": "Property"},
    # Key Dates
    {"path": "contract_dates.offer_date",              "key": "offer_date",              "label": "Offer Date",           "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.offer_expiration_date",   "key": "offer_expiration_date",   "label": "Offer Expiration",     "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.contract_agreement_date", "key": "contract_agreement_date", "label": "Contract Date",        "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.closing_date",            "key": "closing_date",            "label": "Closing Date",         "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.possession_date",         "key": "possession_date",         "label": "Possession",           "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.opd_delivery_date",       "key": "opd_delivery_date",       "label": "Delivery of OPD",      "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.seller_response_time",    "key": "seller_response_time",    "label": "Seller Response Time", "type": "date", "group": "Key Dates"},
    # Contingency Deadlines
    {"path": "contract_dates.loan_application_deadline",       "key": "loan_application_deadline",       "label": "Loan Application Deadline",       "type": "date", "group": "Contingency Deadlines"},
    {"path": "contract_dates.inspection_date",                 "key": "inspection_date",                 "label": "Inspection Deadline",             "type": "date", "group": "Contingency Deadlines"},
    {"path": "contract_dates.inspection_negotiation_deadline", "key": "inspection_negotiation_deadline", "label": "Inspection Negotiation Deadline", "type": "date", "group": "Contingency Deadlines"},
    {"path": "contract_dates.insurance_contingency_date",      "key": "insurance_contingency_date",      "label": "Insurance Contingency Deadline",  "type": "date", "group": "Contingency Deadlines"},
    {"path": "contract_dates.title_contingency_date",          "key": "title_contingency_date",          "label": "Title Review Deadline",           "type": "date", "group": "Contingency Deadlines"},
    # Contingencies
    {"path": "terms.escalation_clause",         "key": "escalation_clause",         "label": "Escalation Clause",          "type": "boolean", "group": "Contingencies"},
    {"path": "terms.opd_delivered",             "key": "opd_delivered",             "label": "OPD Contingency",            "type": "boolean", "group": "Contingencies"},
    {"path": "terms.inspection_contingency",    "key": "inspection_contingency",    "label": "Inspection Contingency",     "type": "boolean", "group": "Contingencies"},
    {"path": "terms.financing_contingency",     "key": "financing_contingency",     "label": "Financing Contingency",      "type": "boolean", "group": "Contingencies"},
    {"path": "terms.appraisal_contingency",        "key": "appraisal_contingency",        "label": "Appraisal Contingency",       "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.appraisal_contingency_amount","key": "appraisal_contingency_amount","label": "Appraisal Amount",            "type": "currency", "group": "Contingencies"},
    {"path": "terms.title_contingency",           "key": "title_contingency",           "label": "Title Contingency",           "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.insurance_contingency",     "key": "insurance_contingency",     "label": "Insurance Contingency",      "type": "boolean", "group": "Contingencies"},
    {"path": "terms.sale_of_home_contingency",  "key": "sale_of_home_contingency",  "label": "Sale of House Contingency",  "type": "boolean", "group": "Contingencies"},
    {"path": "terms.home_warranty",             "key": "home_warranty",             "label": "Home Warranty",              "type": "boolean", "group": "Contingencies"},
    {"path": "terms.hoa_approval_contingency",  "key": "hoa_approval_contingency",  "label": "HOA Contingency",            "type": "boolean", "group": "Contingencies"},
    {"path": "terms.survey_contingency",        "key": "survey_contingency",        "label": "Survey Contingency",         "type": "boolean", "group": "Contingencies"},
    {"path": "terms.as_is",                     "key": "as_is",                     "label": "As-Is",                      "type": "boolean", "group": "Contingencies"},
    # Personal Property
    {"path": "terms.inclusions",    "key": "inclusions",    "label": "Personal Property Included",         "type": "text", "group": "Personal Property"},
    {"path": "terms.exclusions",    "key": "exclusions",    "label": "Excluded Fixtures",                  "type": "text", "group": "Personal Property"},
    {"path": "terms.leased_items",  "key": "leased_items",  "label": "Leased / Rented Personal Property",  "type": "text", "group": "Personal Property"},
    # Additional
    {"path": "terms.detection_devices",    "key": "detection_devices",    "label": "Detection Devices",    "type": "text", "group": "Additional"},
    {"path": "terms.additional_provisions","key": "additional_provisions","label": "Additional Provisions","type": "text", "group": "Additional"},
    {"path": "terms.notes",                "key": "notes",                "label": "Other / Notes",         "type": "text", "group": "Additional"},
]

# field_definitions sent to frontend: strip internal 'path' field
_FIELD_DEFINITIONS = [
    {k: v for k, v in entry.items() if k != "path"}
    for entry in FIELD_REGISTRY
]


def _flatten_extracted(extracted_data: dict) -> dict:
    """Flatten extracted_data's nested structure to dot-notation key → value.

    Participants are indexed by role:  participants.<role_lower>.<field>
    All other sections:                <section>.<field>
    Top-level scalars:                 <key>
    """
    flat: dict = {}
    for section, values in extracted_data.items():
        if section == "participants":
            for p in (values or []):
                role = (p.get("role") or "UNKNOWN").lower()
                for k, v in p.items():
                    if k != "role":
                        flat[f"participants.{role}.{k}"] = v
        elif isinstance(values, dict):
            for k, v in values.items():
                flat[f"{section}.{k}"] = v
        else:
            flat[section] = values
    return flat


def _build_offer_fields(extracted_data: dict) -> tuple[dict, dict]:
    """Return (structured_fields, raw_extras).

    structured_fields  — FIELD_REGISTRY keys → values (None when not extracted)
    raw_extras         — every non-None extracted value NOT covered by the registry
                         so nothing the LLM pulls is silently dropped
    """
    flat = _flatten_extracted(extracted_data)
    registered_paths = {entry["path"] for entry in FIELD_REGISTRY}

    fields = {entry["key"]: flat.get(entry["path"]) for entry in FIELD_REGISTRY}
    raw_extras = {k: v for k, v in flat.items() if k not in registered_paths and v is not None}

    return fields, raw_extras


@app.get("/api/offers/compare")
async def compare_offers(
    extraction_ids: str = Query(..., description="Comma-separated extraction IDs"),
    user=Depends(get_optional_user),
):
    """N-way offer comparison. Returns structured field rows for each extraction."""
    ids = [eid.strip() for eid in extraction_ids.split(",") if eid.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="No extraction IDs provided")

    offers = []
    for eid in ids:
        ext = await get_extraction(eid)
        if not ext:
            raise HTTPException(status_code=404, detail=f"Extraction {eid} not found")
        extracted_data = ext.get("extracted_data") or ext.get("result") or {}
        fields, raw_extras = _build_offer_fields(extracted_data)
        # Apply user overrides on top of extracted values
        overrides = ext.get("field_overrides") or {}
        fields.update({k: v for k, v in overrides.items() if k in fields})
        offers.append({
            "extraction_id": eid,
            "filename": ext.get("source_file") or ext.get("filename") or eid,
            "fields": fields,
            "raw_extras": raw_extras,
        })

    return {"offers": offers, "field_definitions": _FIELD_DEFINITIONS}


class _OfferFieldUpdates(BaseModel):
    updates: dict


@app.patch("/api/offers/{extraction_id}/fields")
async def update_offer_fields(
    extraction_id: str,
    body: _OfferFieldUpdates,
    user=Depends(get_optional_user),
):
    """Persist user-edited field overrides for an offer extraction."""
    from db import DocumentRecord
    parts = str(extraction_id).split(":")
    doc_id = parts[0]
    idx = int(parts[1]) if len(parts) > 1 else 0

    doc = await DocumentRecord.get(doc_id)
    if not doc or idx >= len(doc.extractions):
        raise HTTPException(status_code=404, detail="Extraction not found")

    doc.extractions[idx].field_overrides.update(body.updates)
    await doc.save()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Property Enrichment Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/property/status")
async def property_enrichment_status():
    """Check if the Regrid property enrichment API is configured."""
    return {"configured": property_prefill.is_configured()}


@app.get("/api/property/lookup")
async def property_lookup(
    street: str = Query(..., description="Street address (e.g., '4738 Ridgeline Ct')"),
    city: str = Query(...),
    state: str = Query(...),
    zip: str = Query("", alias="zip"),
    user=Depends(get_optional_user),
):
    """Manual property/parcel lookup by address via Regrid API."""
    if not property_prefill.is_configured():
        raise HTTPException(status_code=503, detail="Property enrichment not configured (REGRID_API_KEY missing)")

    enrichment = await property_prefill.enrich_property({
        "street_number": "",
        "street_name": street,  # Pass full street as street_name; prefill handles it
        "city": city,
        "state_or_province": state,
        "postal_code": zip,
    })

    if not enrichment:
        raise HTTPException(status_code=404, detail="No parcel found for this address")

    return enrichment.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Brokerage Profile Endpoints
# ---------------------------------------------------------------------------


class BrokerageProfilePayload(BaseModel):
    name: str
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    active_markets: List[str] = []


class BrokerageDefaultsPayload(BaseModel):
    default_commission_rate: Optional[str] = None
    preferred_title_company: Optional[str] = None
    preferred_escrow_company: Optional[str] = None
    default_earnest_money_pct: Optional[float] = None
    required_insurance_providers: List[str] = []


def _require_admin(user):
    """Raise 403 if user is not an admin with an org_id."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not getattr(user, "org_id", None):
        raise HTTPException(status_code=400, detail="No organization set — join or create one first")
    if getattr(user, "role", "agent") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


@app.get("/api/brokerage/profile")
async def get_brokerage_profile(user=Depends(get_current_user)):
    """Get the brokerage profile for the current user's organization."""
    from db import BrokerageProfile

    if not getattr(user, "org_id", None):
        raise HTTPException(status_code=400, detail="No organization set")
    profile = await BrokerageProfile.find_one({"org_id": user.org_id})
    if not profile:
        return {"exists": False, "org_id": user.org_id}
    return profile.model_dump(mode="json")


@app.put("/api/brokerage/profile")
async def upsert_brokerage_profile(payload: BrokerageProfilePayload, user=Depends(get_current_user)):
    """Create or update the brokerage profile for the current org (admin only)."""
    from db import BrokerageProfile

    _require_admin(user)
    profile = await BrokerageProfile.find_one({"org_id": user.org_id})
    now = datetime.now(timezone.utc)
    if profile:
        profile.name = payload.name
        profile.license_number = payload.license_number
        profile.license_state = payload.license_state
        profile.address = payload.address
        profile.phone = payload.phone
        profile.active_markets = payload.active_markets
        profile.updated_at = now
        await profile.save()
    else:
        profile = BrokerageProfile(
            org_id=user.org_id,
            name=payload.name,
            license_number=payload.license_number,
            license_state=payload.license_state,
            address=payload.address,
            phone=payload.phone,
            active_markets=payload.active_markets,
            created_at=now,
            updated_at=now,
        )
        await profile.insert()
    return profile.model_dump(mode="json")


@app.put("/api/brokerage/defaults")
async def update_brokerage_defaults(payload: BrokerageDefaultsPayload, user=Depends(get_current_user)):
    """Update brokerage default settings (admin only)."""
    from db import BrokerageProfile, BrokerageDefaultSettings

    _require_admin(user)
    profile = await BrokerageProfile.find_one({"org_id": user.org_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Create a brokerage profile first")
    profile.defaults = BrokerageDefaultSettings(**payload.model_dump())
    profile.updated_at = datetime.now(timezone.utc)
    await profile.save()
    return profile.defaults.model_dump(mode="json")


# API Usage & Cost Tracking
# ---------------------------------------------------------------------------

@app.get("/api/usage")
async def get_usage():
    """Return aggregate API usage and cost across all extractions."""
    from db import DocumentRecord

    docs = await DocumentRecord.find_all().to_list()
    total_extractions = 0
    total_prompt = 0
    total_completion = 0
    total_tokens = 0
    total_cost = 0.0

    for doc in docs:
        for ext in doc.extractions:
            total_extractions += 1
            total_prompt += ext.prompt_tokens
            total_completion += ext.completion_tokens
            total_tokens += ext.total_tokens
            total_cost += ext.cost_usd

    avg_cost = total_cost / total_extractions if total_extractions else 0.0

    return {
        "total_extractions": total_extractions,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "avg_cost_per_extraction": round(avg_cost, 6),
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
