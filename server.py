#!/usr/bin/env python3
"""FastAPI server wrapping the DocExtract pipeline with SSE streaming."""

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from pdf_converter import get_pdf_info, pdf_to_images, image_to_base64
from extractor import extract_from_images, extract_raw_text
from verifier import verify_extraction, compute_overall_confidence
from pii_scanner import scan_all_pages
from schemas import (
    DotloopLoopDetails,
    ExtractionResult,
    FOIARequest,
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

        client = OpenAI()
        raw_extraction = await asyncio.to_thread(
            extract_from_images, images_b64, mode, client,
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

        citations = await asyncio.to_thread(
            verify_extraction, images_b64, validated_data, client,
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

            page_texts = await asyncio.to_thread(
                extract_raw_text, images_b64, client,
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
        if mode == "real_estate" and validated and not validation_errors:
            dotloop_api_payload = validated.to_dotloop_api_format()

        result = ExtractionResult(
            mode=mode,
            source_file=Path(pdf_path).name,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            pages_processed=len(images),
            dotloop_data=validated if mode == "real_estate" and not validation_errors else None,
            foia_data=validated if mode == "gov" and not validation_errors else None,
            dotloop_api_payload=dotloop_api_payload,
            citations=citations,
            overall_confidence=overall_confidence,
            pii_report=pii_report,
        )

        # Write to dist/
        output_path = DIST_DIR / f"{Path(pdf_path).stem}_extracted.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.model_dump_json(indent=2))

        yield sse_event("step_complete", {
            "step": current_step, "title": "Output", "status": "complete",
            "data": {"output_path": str(output_path)},
        })

        yield sse_event("complete", result.model_dump(mode="json"))

    except Exception as e:
        yield sse_event("error", {"message": str(e)})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
