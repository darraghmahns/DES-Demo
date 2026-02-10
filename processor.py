#!/usr/bin/env python3
"""DocExtract — AI-powered document extraction for Real Estate and Government workflows.

Usage:
    python processor.py --mode real_estate --input test_docs/sample_purchase_agreement.pdf
    python processor.py --mode gov --input test_docs/sample_foia_request.pdf
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pydantic import ValidationError

from schemas import (
    DotloopLoopDetails,
    ExtractionResult,
    FOIARequest,
    VerificationCitation,
)
from pdf_converter import (
    check_poppler_installed,
    get_pdf_info,
    image_to_base64,
    pdf_to_images,
)
from verifier import compute_overall_confidence
from pii_scanner import scan_all_pages
from ocr_engine import get_engine
from terminal_ui import (
    console,
    show_banner,
    show_citation_table,
    show_complete,
    show_confidence_bar,
    show_error,
    show_extraction_table,
    show_file_info,
    show_json_output,
    show_mode_info,
    show_pii_findings,
    show_pii_risk_score,
    show_step,
    show_validation_result,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="docextract",
        description="AI-powered document extraction for Real Estate and Government workflows.",
    )
    parser.add_argument(
        "--mode",
        choices=["real_estate", "gov"],
        required=True,
        help="Extraction mode: real_estate (Dotloop) or gov (FOIA)",
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Path to input PDF file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON path (default: dist/<filename>_extracted.json)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show raw API responses",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip verification citation pass",
    )
    return parser.parse_args()


def count_fields(data: dict) -> int:
    """Count non-null fields in a nested dict."""
    count = 0
    for v in data.values():
        if isinstance(v, dict):
            count += count_fields(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    count += count_fields(item)
                elif item is not None:
                    count += 1
        elif v is not None:
            count += 1
    return count


def main():
    load_dotenv()
    args = parse_args()

    # Determine total steps based on mode and flags
    total_steps = 5  # Load, Convert, Extract, Validate, Output
    if not args.no_verify:
        total_steps += 1
    if args.mode == "gov":
        total_steps += 1
    current_step = 0

    # --- Banner ---
    show_banner()
    show_mode_info(args.mode, args.input)

    # --- Preflight Checks ---
    engine_name = os.environ.get("ENGINE", "openai")
    if engine_name == "openai" and not os.environ.get("OPENAI_API_KEY"):
        show_error(
            "Missing API Key",
            "OPENAI_API_KEY not found (required when ENGINE=openai).\n\n"
            "  1. Copy .env.example to .env\n"
            "  2. Add your API key\n"
            "  3. Run again",
        )
        sys.exit(1)

    if not check_poppler_installed():
        show_error(
            "Missing Dependency",
            "poppler-utils is required for PDF processing.\n\n"
            "  macOS:   brew install poppler\n"
            "  Ubuntu:  sudo apt-get install poppler-utils\n"
            "  Windows: choco install poppler",
        )
        sys.exit(1)

    # --- Step 1: Load Document ---
    current_step += 1
    show_step(current_step, total_steps, "Load Document", "Validating input PDF...")

    input_path = Path(args.input)
    if not input_path.exists():
        show_error("File Not Found", f"Cannot find: {args.input}")
        sys.exit(1)
    if not input_path.suffix.lower() == ".pdf":
        show_error("Invalid File", f"Expected a PDF file, got: {input_path.suffix}")
        sys.exit(1)

    file_info = get_pdf_info(str(input_path))
    show_file_info(file_info["name"], file_info["size_human"], file_info["pages"])

    # --- Step 2: Convert to Images ---
    current_step += 1
    show_step(current_step, total_steps, "Convert to Images", "Rendering PDF pages for neural OCR analysis...")

    with console.status("[bold green]Converting PDF pages...", spinner="dots"):
        images = pdf_to_images(str(input_path))
        images_b64 = [image_to_base64(img) for img in images]

    console.print(f"  [green]\u2713[/] Converted {len(images)} page(s) to images")

    # --- Step 3: Neural OCR Extraction ---
    current_step += 1
    show_step(
        current_step,
        total_steps,
        "Neural OCR Extraction",
        f"Analyzing {len(images)} page(s) with neural OCR for structured extraction...",
    )

    engine = get_engine()
    use_file = engine.prefers_file_path

    with console.status("[bold green]Running neural OCR extraction...", spinner="dots"):
        if use_file:
            raw_extraction = engine.extract_from_file(str(input_path), args.mode)
        else:
            raw_extraction = engine.extract(images_b64, args.mode)

    if args.verbose:
        console.print("\n[dim]Raw API response:[/]")
        console.print(json.dumps(raw_extraction, indent=2))

    # --- Step 4: Validate Schema ---
    current_step += 1
    show_step(current_step, total_steps, "Validate Schema", "Running Pydantic schema validation...")

    validated_data = None
    validation_errors: list[str] = []

    try:
        if args.mode == "real_estate":
            validated = DotloopLoopDetails.model_validate(raw_extraction)
            validated_data = validated.model_dump(mode="json")
            show_extraction_table(validated_data, args.mode)
            show_validation_result(True)
        else:
            validated = FOIARequest.model_validate(raw_extraction)
            validated_data = validated.model_dump(mode="json")
            show_extraction_table(validated_data, args.mode)
            show_validation_result(True)
    except ValidationError as e:
        for err in e.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            validation_errors.append(f"{loc}: {err['msg']}")
        show_validation_result(False, validation_errors)

        # Attempt to use raw extraction even if validation partially fails
        console.print("\n  [yellow]Using raw extraction with partial validation...[/]")
        validated_data = raw_extraction
        show_extraction_table(validated_data, args.mode)

    # --- Step 5: Verify Citations (optional) ---
    citations: list[VerificationCitation] = []
    overall_confidence = 0.0

    if not args.no_verify:
        current_step += 1
        show_step(
            current_step,
            total_steps,
            "Verify Citations",
            "Verifying source locations for each extracted value...",
        )

        with console.status("[bold green]Verifying extraction sources...", spinner="dots"):
            if use_file:
                citations = engine.verify_from_file(str(input_path), validated_data)
            else:
                citations = engine.verify(images_b64, validated_data)

        overall_confidence = compute_overall_confidence(citations)

        show_citation_table([c.model_dump() for c in citations])
        show_confidence_bar(overall_confidence)

    # --- Step 6: PII Scan (gov mode only) ---
    pii_report = None

    if args.mode == "gov":
        current_step += 1
        show_step(
            current_step,
            total_steps,
            "PII Scan",
            "Scanning for personally identifiable information...",
        )

        with console.status("[bold green]Extracting text for PII analysis...", spinner="dots"):
            if use_file:
                page_texts = engine.ocr_raw_text_from_file(str(input_path))
            else:
                page_texts = engine.ocr_raw_text(images_b64)

        pii_report = scan_all_pages(page_texts)

        show_pii_findings([f.model_dump() for f in pii_report.findings])
        show_pii_risk_score(pii_report.pii_risk_score, pii_report.risk_level.value)

    # --- Final Step: Output ---
    current_step += 1
    output_path = args.output or f"dist/{input_path.stem}_extracted.json"
    show_step(current_step, total_steps, "Output", f"Writing results to {output_path}")

    # Build the final result
    dotloop_api_payload = None
    if args.mode == "real_estate" and not validation_errors:
        dotloop_api_payload = validated.to_dotloop_api_format()

    result = ExtractionResult(
        mode=args.mode,
        source_file=str(input_path),
        extraction_timestamp=datetime.now(timezone.utc).isoformat(),
        pages_processed=len(images),
        dotloop_data=validated_data if args.mode == "real_estate" else None,
        foia_data=validated_data if args.mode == "gov" else None,
        dotloop_api_payload=dotloop_api_payload,
        citations=citations,
        overall_confidence=overall_confidence,
        pii_report=pii_report,
    )

    # Write output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(result.model_dump_json(indent=2))

    # Display output
    show_json_output(result.model_dump(), output_path)

    # Final summary
    field_count = count_fields(validated_data) if validated_data else 0
    show_complete(args.mode, len(images), field_count, output_path)


if __name__ == "__main__":
    main()
