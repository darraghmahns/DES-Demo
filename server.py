#!/usr/bin/env python3
"""FastAPI server wrapping the DocExtract pipeline with SSE streaming."""

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
from db_writer import save_document, save_extraction
from dotloop_connector import (
    is_configured as dotloop_configured,
    list_dotloop_loops,
    sync_to_dotloop,
    process_from_dotloop,
    handle_webhook as dotloop_handle_webhook,
    set_oauth_tokens,
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

@app.get("/api/documents")
async def list_documents() -> list[DocumentInfo]:
    """List available PDF documents in test_docs/."""
    docs: list[DocumentInfo] = []
    if not TEST_DOCS_DIR.exists():
        return docs
    for pdf in sorted(TEST_DOCS_DIR.glob("*.pdf")):
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
        headers={"Content-Disposition": f"inline; filename={name}"},
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
    """Run the extraction pipeline and stream SSE progress events."""
    pdf_path = TEST_DOCS_DIR / request.filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    if request.mode not in ("real_estate", "gov"):
        raise HTTPException(status_code=400, detail="Invalid mode")

    return StreamingResponse(
        extraction_stream(request.mode, str(pdf_path)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def extraction_stream(mode: str, pdf_path: str) -> AsyncGenerator[str, None]:
    """Generator that runs the pipeline and yields SSE events at each step."""
    total_steps = 5  # Load, Convert, Extract, Validate, Output
    total_steps += 1  # Verify citations
    if mode == "gov":
        total_steps += 1  # PII scan

    current_step = 0
    _start_time = time.monotonic()

    try:
        # --- Step 1: Load Document ---
        current_step += 1
        yield sse_event("step", {
            "step": current_step, "total": total_steps,
            "title": "Load Document", "status": "running",
        })
        await asyncio.sleep(0.1)  # Let the event flush

        file_info = await asyncio.to_thread(get_pdf_info, pdf_path)

        yield sse_event("step_complete", {
            "step": current_step, "title": "Load Document", "status": "complete",
            "data": file_info,
        })

        # --- Step 2: Convert to Images ---
        current_step += 1
        yield sse_event("step", {
            "step": current_step, "total": total_steps,
            "title": "Convert to Images", "status": "running",
        })

        images = await asyncio.to_thread(pdf_to_images, pdf_path)
        images_b64 = [image_to_base64(img) for img in images]

        yield sse_event("step_complete", {
            "step": current_step, "title": "Convert to Images", "status": "complete",
            "data": {"pages_converted": len(images)},
        })

        # --- Step 3: Neural OCR Extraction ---
        current_step += 1
        yield sse_event("step", {
            "step": current_step, "total": total_steps,
            "title": "Neural OCR Extraction", "status": "running",
        })

        engine = get_engine()
        use_file = engine.prefers_file_path
        if use_file:
            raw_extraction = await asyncio.to_thread(
                engine.extract_from_file, pdf_path, mode,
            )
        else:
            raw_extraction = await asyncio.to_thread(
                engine.extract, images_b64, mode,
            )

        yield sse_event("step_complete", {
            "step": current_step, "title": "Neural OCR Extraction", "status": "complete",
            "data": {"fields_extracted": len(raw_extraction)},
        })

        # --- Step 4: Validate Schema ---
        current_step += 1
        yield sse_event("step", {
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

        yield sse_event("extraction", {"validated_data": validated_data})
        yield sse_event("validation", {
            "success": len(validation_errors) == 0,
            "errors": validation_errors,
        })
        yield sse_event("step_complete", {
            "step": current_step, "title": "Validate Schema", "status": "complete",
            "data": {"success": len(validation_errors) == 0, "error_count": len(validation_errors)},
        })

        # --- Step 5: Verify Citations ---
        current_step += 1
        yield sse_event("step", {
            "step": current_step, "total": total_steps,
            "title": "Verify Citations", "status": "running",
        })

        if use_file:
            citations = await asyncio.to_thread(
                engine.verify_from_file, pdf_path, validated_data,
            )
        else:
            citations = await asyncio.to_thread(
                engine.verify, images_b64, validated_data,
            )
        overall_confidence = compute_overall_confidence(citations)

        citations_data = [c.model_dump(mode="json") for c in citations]

        yield sse_event("citations", {
            "citations": citations_data,
            "overall_confidence": overall_confidence,
        })
        yield sse_event("step_complete", {
            "step": current_step, "title": "Verify Citations", "status": "complete",
            "data": {"citation_count": len(citations), "overall_confidence": overall_confidence},
        })

        # --- Step 6: PII Scan (gov mode only) ---
        pii_report = None
        if mode == "gov":
            current_step += 1
            yield sse_event("step", {
                "step": current_step, "total": total_steps,
                "title": "PII Scan", "status": "running",
            })

            if use_file:
                page_texts = await asyncio.to_thread(
                    engine.ocr_raw_text_from_file, pdf_path,
                )
            else:
                page_texts = await asyncio.to_thread(
                    engine.ocr_raw_text, images_b64,
                )
            pii_report = scan_all_pages(page_texts)

            yield sse_event("pii", {
                "findings": [f.model_dump(mode="json") for f in pii_report.findings],
                "risk_score": pii_report.pii_risk_score,
                "risk_level": pii_report.risk_level.value,
            })
            yield sse_event("step_complete", {
                "step": current_step, "title": "PII Scan", "status": "complete",
                "data": {
                    "finding_count": len(pii_report.findings),
                    "risk_score": pii_report.pii_risk_score,
                },
            })

        # --- Final Step: Output ---
        current_step += 1
        yield sse_event("step", {
            "step": current_step, "total": total_steps,
            "title": "Output", "status": "running",
        })

        dotloop_api_payload = None
        if mode == "real_estate":
            source = validated or lenient_validated
            if source:
                try:
                    dotloop_api_payload = source.to_dotloop_api_format()
                except Exception:
                    pass  # Partial data couldn't be formatted — leave None

        result = ExtractionResult(
            mode=mode,
            source_file=Path(pdf_path).name,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            pages_processed=len(images),
            dotloop_data=validated_data if mode == "real_estate" else None,
            foia_data=validated_data if mode == "gov" else None,
            dotloop_api_payload=dotloop_api_payload,
            citations=citations,
            overall_confidence=overall_confidence,
            pii_report=pii_report,
        )

        # Write to dist/
        output_path = DIST_DIR / f"{Path(pdf_path).stem}_extracted.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.model_dump_json(indent=2))

        # Persist to Postgres
        duration_ms = int((time.monotonic() - _start_time) * 1000)
        extraction_id = None
        try:
            doc_id = await asyncio.to_thread(
                save_document,
                Path(pdf_path).name,
                mode,
                len(images),
                Path(pdf_path).stat().st_size,
            )
            ext_id = await asyncio.to_thread(
                save_extraction,
                doc_id,
                result,
                engine.name,
                duration_ms,
            )
            extraction_id = str(ext_id)
        except Exception as db_err:
            # DB save is best-effort — don't fail the extraction
            logging.getLogger(__name__).warning("DB save failed: %s", db_err)

        yield sse_event("step_complete", {
            "step": current_step, "title": "Output", "status": "complete",
            "data": {"output_path": str(output_path)},
        })

        complete_data = result.model_dump(mode="json")
        if extraction_id:
            complete_data["extraction_id"] = extraction_id
        yield sse_event("complete", complete_data)

    except Exception as e:
        yield sse_event("error", {"message": str(e)})


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
        result = await asyncio.to_thread(sync_to_dotloop, extraction_id, loop_id=body.loop_id)
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
        result = await asyncio.to_thread(
            process_from_dotloop, request.profile_id, loop_id, request.sync_back,
        )
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
    result = await asyncio.to_thread(dotloop_handle_webhook, payload)
    return result


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
