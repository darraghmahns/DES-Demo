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
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse
from pydantic import BaseModel, ValidationError

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
from db import init_db, close_db
from db_writer import save_document, save_extraction
from dotloop_connector import (
    is_configured as dotloop_configured,
    list_dotloop_loops,
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

load_dotenv()

app = FastAPI(title="DocExtract API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await init_db()


@app.on_event("shutdown")
async def shutdown():
    await close_db()


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
        if mode and _classify_document(pdf.name) != mode:
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
async def extract(request: ExtractRequest):
    """Start the extraction pipeline as a background task, return task_id.

    The extraction runs independently of the HTTP connection.
    Use GET /api/extract/{task_id}/stream to subscribe to SSE events.
    """
    from task_manager import create_task, get_active_task, TaskStatus

    pdf_path = TEST_DOCS_DIR / request.filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    if request.mode not in ("real_estate", "gov"):
        raise HTTPException(status_code=400, detail="Invalid mode")

    # Check for already-running task for this file+mode
    existing = get_active_task(request.mode, request.filename)
    if existing:
        return {"task_id": existing.task_id, "status": existing.status.value}

    # Create and launch background task
    task = create_task(request.mode, request.filename)
    asyncio_task = asyncio.create_task(
        _run_extraction_task(task, request.mode, str(pdf_path))
    )
    task._asyncio_task = asyncio_task

    return {"task_id": task.task_id, "status": "pending"}


@app.get("/api/extract/{task_id}/stream")
async def extract_stream(task_id: str):
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


async def _run_extraction_task(task, mode: str, pdf_path: str) -> None:
    """Run the extraction pipeline as a background task, storing events."""
    from task_manager import TaskStatus, cleanup_old_tasks

    task.status = TaskStatus.RUNNING

    def emit(event_type: str, data: dict) -> None:
        task.append_event({"type": event_type, "data": data})

    await _extraction_pipeline(mode, pdf_path, emit)

    # Mark final status based on last event
    if task.events and task.events[-1]["type"] == "error":
        task.status = TaskStatus.ERROR
    else:
        task.status = TaskStatus.COMPLETE

    cleanup_old_tasks()


async def _extraction_pipeline(
    mode: str, pdf_path: str, emit,
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
            except Exception:
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

        # --- Step 6 (real_estate): Compliance Check ---
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
                except Exception:
                    pass
                try:
                    docusign_api_payload = source.to_docusign_api_format()
                except Exception:
                    pass

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
            prompt_tokens=total_usage["prompt_tokens"],
            completion_tokens=total_usage["completion_tokens"],
            total_tokens=total_usage["total_tokens"],
            cost_usd=round(cost_usd, 6),
        )

        # Write to dist/
        output_path = DIST_DIR / f"{Path(pdf_path).stem}_extracted.json"
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
async def clear_extraction_cache(mode: str = Query(None)):
    """Clear cached extractions, optionally filtered by mode."""
    from db import DocumentRecord

    filters = {}
    if mode:
        filters["mode"] = mode

    docs = await DocumentRecord.find(filters).to_list()
    deleted_count = 0
    for doc in docs:
        await doc.delete()
        deleted_count += 1

    return {"deleted": deleted_count, "mode": mode or "all"}


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
):
    """Standalone compliance check without an extraction — for public API.

    Uses async DB-first lookup so AI Scout results are automatically included.
    """
    report = await async_run_compliance_check(
        {"property_address": {
            "state_or_province": state,
            "county": county,
            "city": city,
        }},
        transaction_type=transaction_type,
    )
    return report.model_dump(mode="json")


# ---------------------------------------------------------------------------
# AI Scout Endpoints
# ---------------------------------------------------------------------------


class ScoutRequest(BaseModel):
    state: str
    county: str = ""
    city: str = ""


@app.post("/api/scout/research")
async def scout_research(request: ScoutRequest):
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
    except Exception:
        raise HTTPException(status_code=404, detail="Scout result not found")

    if not result:
        raise HTTPException(status_code=404, detail="Scout result not found")

    return result.model_dump(mode="json")


@app.put("/api/scout/results/{result_id}/verify")
async def scout_verify_result(result_id: str, verified_by: str = Query("admin")):
    """Mark a scout result as verified and activate it for compliance checks."""
    from scout_models import ScoutResult
    from bson import ObjectId

    try:
        result = await ScoutResult.get(ObjectId(result_id))
    except Exception:
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
    except Exception:
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
# Dotloop Integration Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/dotloop/status")
async def dotloop_status():
    """Check whether Dotloop integration is configured."""
    return {"configured": dotloop_configured()}


@app.get("/api/dotloop/loops")
async def dotloop_loops(profile_id: int | None = None, batch_size: int = 20):
    """List recent loops from Dotloop."""
    if not dotloop_configured():
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    try:
        loops = await asyncio.to_thread(list_dotloop_loops, profile_id, batch_size)
        return {"loops": loops}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DotloopSyncRequest(BaseModel):
    loop_id: int | None = None


@app.post("/api/dotloop/sync/{extraction_id}")
async def dotloop_sync(extraction_id: str, body: DotloopSyncRequest = DotloopSyncRequest()):
    """Push a saved extraction to Dotloop as a loop."""
    if not dotloop_configured():
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    try:
        result = await sync_to_dotloop(extraction_id, loop_id=body.loop_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ProcessFromDotloopRequest(BaseModel):
    profile_id: int | None = None
    sync_back: bool = False


@app.post("/api/dotloop/process/{loop_id}")
async def dotloop_process(loop_id: int, request: ProcessFromDotloopRequest):
    """Pull a PDF from a Dotloop loop, extract, and optionally sync back."""
    if not dotloop_configured():
        raise HTTPException(status_code=503, detail="Dotloop not configured")
    try:
        result = await process_from_dotloop(request.profile_id, loop_id, request.sync_back)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Dotloop OAuth Endpoints
# ---------------------------------------------------------------------------

DOTLOOP_AUTH_BASE = "https://auth.dotloop.com"


@app.get("/api/dotloop/oauth/connect")
async def dotloop_oauth_connect():
    """Redirect browser to Dotloop authorization page."""
    client_id = os.getenv("DOTLOOP_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="DOTLOOP_CLIENT_ID not configured")

    redirect_uri = os.getenv(
        "DOTLOOP_REDIRECT_URI",
        "http://localhost:8000/api/dotloop/oauth/callback",
    )
    auth_url = (
        f"{DOTLOOP_AUTH_BASE}/oauth/authorize"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
    )
    return RedirectResponse(url=auth_url)


@app.get("/api/dotloop/oauth/callback")
async def dotloop_oauth_callback(code: str | None = None, error: str | None = None):
    """Handle OAuth callback from Dotloop, exchange code for tokens."""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

    if error:
        return RedirectResponse(url=f"{frontend_url}?dotloop_error={error}")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    client_id = os.getenv("DOTLOOP_CLIENT_ID")
    client_secret = os.getenv("DOTLOOP_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "DOTLOOP_REDIRECT_URI",
        "http://localhost:8000/api/dotloop/oauth/callback",
    )

    import httpx
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
        resp.raise_for_status()
        token_data = resp.json()
    except Exception as e:
        logging.getLogger(__name__).error("Dotloop token exchange failed: %s", e)
        return RedirectResponse(url=f"{frontend_url}?dotloop_error=token_exchange_failed")

    set_oauth_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
    )

    return RedirectResponse(url=f"{frontend_url}?dotloop_connected=true")


# ---------------------------------------------------------------------------
# Dotloop Webhook
# ---------------------------------------------------------------------------

@app.post("/api/webhooks/dotloop")
async def dotloop_webhook(payload: dict):
    """Receive Dotloop LOOP_UPDATED webhook events."""
    result = await dotloop_handle_webhook(payload)
    return result


# ---------------------------------------------------------------------------
# DocuSign Integration Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/docusign/status")
async def docusign_status():
    """Check whether DocuSign integration is configured."""
    from docusign_connector import get_oauth_tokens, _jwt_available
    configured = docusign_configured()  # May trigger JWT auth
    tokens = get_oauth_tokens()  # Read after JWT may have set tokens
    return {
        "configured": configured,
        "has_access_token": bool(tokens.get("access_token") or os.getenv("DOCUSIGN_ACCESS_TOKEN")),
        "has_account_id": bool(tokens.get("account_id") or os.getenv("DOCUSIGN_ACCOUNT_ID")),
        "jwt_available": _jwt_available(),
        "account_id": tokens.get("account_id") or os.getenv("DOCUSIGN_ACCOUNT_ID", ""),
    }


@app.get("/api/docusign/envelopes")
async def docusign_envelopes(
    from_date: str | None = None,
    status: str | None = None,
    count: int = 50,
):
    """List recent envelopes from DocuSign."""
    if not docusign_configured():
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    # Default to all active statuses so drafts are included
    if not status:
        status = "created,sent,delivered,signed,completed"
    try:
        envelopes = await asyncio.to_thread(
            list_docusign_envelopes, from_date, status, count
        )
        return {"envelopes": envelopes}
    except Exception as e:
        log.error("DocuSign envelope listing failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class DocuSignSyncRequest(BaseModel):
    envelope_id: str | None = None


@app.post("/api/docusign/sync/{extraction_id}")
async def docusign_sync(extraction_id: str, body: DocuSignSyncRequest = DocuSignSyncRequest()):
    """Push a saved extraction to DocuSign as an envelope."""
    if not docusign_configured():
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    try:
        result = await sync_to_docusign(extraction_id, envelope_id=body.envelope_id)
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


@app.delete("/api/docusign/envelopes/{envelope_id}")
async def docusign_remove_envelope(envelope_id: str):
    """Remove a DocuSign envelope — voids sent/delivered, deletes drafts."""
    if not docusign_configured():
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    try:
        result = await asyncio.to_thread(remove_docusign_envelope, envelope_id)
        return {"status": "removed", "envelope_id": envelope_id, "detail": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/docusign/envelopes")
async def docusign_remove_all_envelopes():
    """Remove all DocuSign envelopes — voids sent/delivered, deletes drafts."""
    if not docusign_configured():
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    try:
        envelopes = await asyncio.to_thread(
            list_docusign_envelopes, None, "created,sent,delivered", 100
        )
        results = []
        for env in envelopes:
            eid = env.get("envelopeId")
            if eid:
                try:
                    r = await asyncio.to_thread(remove_docusign_envelope, eid)
                    results.append({"envelope_id": eid, "result": "removed"})
                except Exception as e:
                    results.append({"envelope_id": eid, "result": str(e)})
        return {"removed": len(results), "details": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ProcessFromDocuSignRequest(BaseModel):
    sync_back: bool = False


@app.post("/api/docusign/process/{envelope_id}")
async def docusign_process(envelope_id: str, request: ProcessFromDocuSignRequest = ProcessFromDocuSignRequest()):
    """Pull a PDF from a DocuSign envelope, extract, and optionally sync back."""
    if not docusign_configured():
        raise HTTPException(status_code=503, detail="DocuSign not configured")
    try:
        result = await process_from_docusign(envelope_id, request.sync_back)
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

DOCUSIGN_AUTH_SERVER = os.getenv("DOCUSIGN_AUTH_SERVER", "account-d.docusign.com")


@app.get("/api/docusign/oauth/connect")
async def docusign_oauth_connect():
    """Redirect browser to DocuSign authorization page."""
    client_id = os.getenv("DOCUSIGN_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=500, detail="DOCUSIGN_CLIENT_ID not configured")

    redirect_uri = os.getenv(
        "DOCUSIGN_REDIRECT_URI",
        "http://localhost:8000/api/docusign/oauth/callback",
    )
    from urllib.parse import urlencode
    auth_params = urlencode({
        "response_type": "code",
        "scope": "signature",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    })
    auth_url = f"https://{DOCUSIGN_AUTH_SERVER}/oauth/auth?{auth_params}"
    return RedirectResponse(url=auth_url)


@app.get("/api/docusign/oauth/callback")
async def docusign_oauth_callback(code: str | None = None, error: str | None = None):
    """Handle OAuth callback from DocuSign, exchange code for tokens."""
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")

    if error:
        return RedirectResponse(url=f"{frontend_url}?docusign_error={error}")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received")

    client_id = os.getenv("DOCUSIGN_CLIENT_ID")
    client_secret = os.getenv("DOCUSIGN_CLIENT_SECRET")
    redirect_uri = os.getenv(
        "DOCUSIGN_REDIRECT_URI",
        "http://localhost:8000/api/docusign/oauth/callback",
    )

    import httpx
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
        logging.getLogger(__name__).error("DocuSign token exchange failed: %s", e)
        return RedirectResponse(url=f"{frontend_url}?docusign_error=token_exchange_failed")

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
        logging.getLogger(__name__).warning("DocuSign userinfo failed: %s", e)

    docusign_set_oauth_tokens(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        account_id=account_id,
    )

    return RedirectResponse(url=f"{frontend_url}?docusign_connected=true")


# ---------------------------------------------------------------------------
# DocuSign Webhook
# ---------------------------------------------------------------------------

@app.post("/api/webhooks/docusign")
async def docusign_webhook(payload: dict):
    """Receive DocuSign Connect webhook events."""
    result = await docusign_handle_webhook(payload)
    return result


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
# Serve frontend (production — only when frontend/dist exists)
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path("frontend/dist")
if _FRONTEND_DIR.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIR / "assets")), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Catch-all: serve index.html for SPA client-side routing."""
        return FileResponse(str(_FRONTEND_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
