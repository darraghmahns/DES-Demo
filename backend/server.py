#!/usr/bin/env python3
"""FastAPI server wrapping the DocExtract pipeline with SSE streaming."""

import hashlib
import json
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
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
from compliance_engine import run_compliance_check, async_run_compliance_check
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

# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

@app.get("/api/onboarding/status")
async def onboarding_status(user=Depends(get_current_user)):
    """Return onboarding completion state and integration status for the wizard."""
    if not user:
        # Auth disabled — no onboarding
        return {"completed": True, "completed_at": None, "skipped_steps": [],
                "dotloop_connected": False, "docusign_connected": False}
    return {
        "completed": user.onboarding_completed,
        "completed_at": user.onboarding_completed_at.isoformat() if user.onboarding_completed_at else None,
        "skipped_steps": user.onboarding_skipped_steps,
        "dotloop_connected": bool(user.dotloop_tokens and user.dotloop_tokens.access_token),
        "docusign_connected": bool(user.docusign_tokens and user.docusign_tokens.access_token),
    }


class OnboardingCompleteRequest(BaseModel):
    skipped_steps: List[str] = Field(default_factory=list)


@app.patch("/api/onboarding/complete")
async def onboarding_complete(request: OnboardingCompleteRequest, user=Depends(get_current_user)):
    """Mark onboarding as completed. Idempotent — won't overwrite existing timestamp."""
    if not user:
        return {"completed": True}
    if not user.onboarding_completed:
        user.onboarding_completed = True
        user.onboarding_completed_at = datetime.now(timezone.utc)
        user.onboarding_skipped_steps = request.skipped_steps
        await user.save()
    return {
        "completed": user.onboarding_completed,
        "completed_at": user.onboarding_completed_at.isoformat() if user.onboarding_completed_at else None,
    }


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
        total_steps += 1  # Compliance check
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

        # --- Compliance Check (real_estate) ---
        compliance_report = None
        if mode == "real_estate":
            current_step += 1
            emit("step", {
                "step": current_step, "total": total_steps,
                "title": "Compliance Check", "status": "running",
            })

            compliance_report = await async_run_compliance_check(
                validated_data or {},
                transaction_type=(validated.transaction_type if validated else None),
                org_id=org_id,
            )

            emit("compliance", {
                "jurisdiction_key": compliance_report.jurisdiction_key,
                "jurisdiction_display": compliance_report.jurisdiction_display,
                "jurisdiction_type": compliance_report.jurisdiction_type,
                "overall_status": compliance_report.overall_status.value,
                "requirements": [r.model_dump(mode="json") for r in compliance_report.requirements],
                "requirement_count": compliance_report.requirement_count,
                "action_items": compliance_report.action_items,
                "transaction_type": compliance_report.transaction_type,
                "notes": compliance_report.notes,
            })
            emit("step_complete", {
                "step": current_step, "title": "Compliance Check", "status": "complete",
                "data": {
                    "jurisdiction": compliance_report.jurisdiction_display,
                    "requirement_count": compliance_report.requirement_count,
                    "action_items": compliance_report.action_items,
                    "status": compliance_report.overall_status.value,
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
            compliance_report=compliance_report,
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
                if not dotloop_configured(user_tokens=dl_tokens):
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
# Compliance Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/compliance/{extraction_ref:path}")
async def get_compliance_report(extraction_ref: str):
    """Retrieve the compliance report for a saved extraction."""
    from db_writer import get_extraction
    ext = await get_extraction(extraction_ref)
    if not ext:
        raise HTTPException(status_code=404, detail="Extraction not found")
    report = ext.get("compliance_report")
    if not report:
        return {"status": "none", "message": "No compliance report for this extraction"}
    return report


@app.get("/api/compliance-check")
async def standalone_compliance_check(
    state: str = Query(...),
    county: str = Query(""),
    city: str = Query(""),
    transaction_type: str = Query(None),
    org_id: str = Query(None),
    user=Depends(get_optional_user),
):
    """Standalone compliance check without an extraction — for public API.

    Uses async DB-first lookup so AI Scout results are automatically included.
    When *org_id* is provided (or inferred from the authenticated user),
    brokerage-specific requirements are layered on top.
    """
    effective_org_id = org_id or (getattr(user, "org_id", None) if user else None)
    report = await async_run_compliance_check(
        {"property_address": {
            "state_or_province": state,
            "county": county,
            "city": city,
        }},
        transaction_type=transaction_type,
        org_id=effective_org_id,
    )
    return report.model_dump(mode="json")


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


class BrokerageRequirementPayload(BaseModel):
    name: str
    code: Optional[str] = None
    category: str = "FORM"
    description: str = ""
    authority: Optional[str] = None
    fee: Optional[str] = None
    url: Optional[str] = None
    status: str = "REQUIRED"
    notes: Optional[str] = None


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


@app.post("/api/brokerage/requirements")
async def add_brokerage_requirement(payload: BrokerageRequirementPayload, user=Depends(get_current_user)):
    """Add a custom compliance requirement to the brokerage profile (admin only)."""
    from db import BrokerageProfile

    _require_admin(user)
    profile = await BrokerageProfile.find_one({"org_id": user.org_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Create a brokerage profile first")
    req = payload.model_dump()
    req["source"] = "BROKERAGE"
    profile.custom_requirements.append(req)
    profile.updated_at = datetime.now(timezone.utc)
    await profile.save()
    return {"index": len(profile.custom_requirements) - 1, "requirement": req}


@app.delete("/api/brokerage/requirements/{index}")
async def remove_brokerage_requirement(index: int, user=Depends(get_current_user)):
    """Remove a custom compliance requirement by index (admin only)."""
    from db import BrokerageProfile

    _require_admin(user)
    profile = await BrokerageProfile.find_one({"org_id": user.org_id})
    if not profile:
        raise HTTPException(status_code=404, detail="Brokerage profile not found")
    if index < 0 or index >= len(profile.custom_requirements):
        raise HTTPException(status_code=400, detail=f"Invalid index {index} — {len(profile.custom_requirements)} requirements exist")
    removed = profile.custom_requirements.pop(index)
    profile.updated_at = datetime.now(timezone.utc)
    await profile.save()
    return {"removed": removed, "remaining": len(profile.custom_requirements)}


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


# ---------------------------------------------------------------------------
# AI Scout Endpoints
# ---------------------------------------------------------------------------


class ScoutRequest(BaseModel):
    state: str
    county: str = ""
    city: str = ""


@app.post("/api/scout/research")
async def scout_research(request: ScoutRequest, user=Depends(get_optional_user)):
    """Trigger AI Scout research for a jurisdiction.

    Runs the two-pass GPT-4o pipeline (research → verify) and saves results
    to MongoDB with is_verified=False, is_active=False.
    """
    from scout import run_scout

    if not request.state:
        raise HTTPException(status_code=400, detail="state is required")

    try:
        result = await run_scout(
            state=request.state.strip(),
            county=request.county.strip() or None,
            city=request.city.strip() or None,
            save_to_db=True,
        )
        return {
            "id": str(result.id),
            "jurisdiction_key": result.jurisdiction_key,
            "jurisdiction_type": result.jurisdiction_type,
            "requirement_count": len(result.requirements),
            "is_verified": result.is_verified,
            "is_active": result.is_active,
            "research_timestamp": result.research_timestamp.isoformat(),
            "notes": result.notes,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scout/results")
async def scout_list_results(
    state: str = Query(None),
    verified: bool = Query(None),
):
    """List AI Scout results, optionally filtered by state or verification status."""
    from scout_models import ScoutResult

    filters = {}
    if state:
        filters["state"] = state.strip().upper()
    if verified is not None:
        filters["is_verified"] = verified

    results = await ScoutResult.find(filters).sort("-research_timestamp").to_list(100)

    return [
        {
            "id": str(r.id),
            "jurisdiction_key": r.jurisdiction_key,
            "jurisdiction_type": r.jurisdiction_type,
            "state": r.state,
            "county": r.county,
            "city": r.city,
            "requirement_count": len(r.requirements),
            "is_verified": r.is_verified,
            "is_active": r.is_active,
            "source": r.source,
            "research_timestamp": r.research_timestamp.isoformat(),
            "notes": r.notes,
        }
        for r in results
    ]


@app.get("/api/scout/results/{result_id}")
async def scout_get_result(result_id: str):
    """Get a specific AI Scout result with full requirements."""
    from scout_models import ScoutResult
    from bson import ObjectId

    try:
        result = await ScoutResult.get(ObjectId(result_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Scout result not found")

    if not result:
        raise HTTPException(status_code=404, detail="Scout result not found")

    return result.model_dump(mode="json")


@app.put("/api/scout/results/{result_id}/verify")
async def scout_verify_result(result_id: str, verified_by: str = Query("admin"), user=Depends(get_optional_user)):
    """Mark a scout result as verified and activate it for compliance checks."""
    from scout_models import ScoutResult
    from bson import ObjectId

    try:
        result = await ScoutResult.get(ObjectId(result_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Scout result not found")

    if not result:
        raise HTTPException(status_code=404, detail="Scout result not found")

    result.is_verified = True
    result.is_active = True
    result.verified_by = verified_by
    result.verification_timestamp = datetime.now(timezone.utc)
    await result.save()

    return {
        "id": str(result.id),
        "jurisdiction_key": result.jurisdiction_key,
        "is_verified": True,
        "is_active": True,
        "verified_by": verified_by,
        "verification_timestamp": result.verification_timestamp.isoformat(),
    }


@app.put("/api/scout/results/{result_id}/reject")
async def scout_reject_result(result_id: str):
    """Mark a scout result as rejected (is_active=False, is_verified stays False)."""
    from scout_models import ScoutResult
    from bson import ObjectId

    try:
        result = await ScoutResult.get(ObjectId(result_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Scout result not found")

    if not result:
        raise HTTPException(status_code=404, detail="Scout result not found")

    result.is_active = False
    result.is_verified = False
    result.notes = (result.notes or "") + " [REJECTED]"
    await result.save()

    return {
        "id": str(result.id),
        "jurisdiction_key": result.jurisdiction_key,
        "is_verified": False,
        "is_active": False,
        "status": "rejected",
    }


# ---------------------------------------------------------------------------
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
