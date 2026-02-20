"""Integration tests for the _extraction_pipeline function in server.py.

Covers:
- Happy path (real_estate mode): all SSE events emitted in order,
  schema validation passes, compliance + enrichment steps run.
- Error path: invalid PDF triggers an "error" SSE event.
- Gov mode: PII scan step runs, compliance and enrichment are skipped.
- Validation errors: malformed extraction data emits validation errors
  but pipeline still completes (lenient fallback).

All LLM calls, DB writes, and external services are mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas import (
    ComplianceOverallStatus,
    ComplianceReport,
    PropertyEnrichment,
    VerificationCitation,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_PDF_CONTENT = b"%PDF-1.4 fake minimal pdf content for testing purposes"


@pytest.fixture
def tmp_pdf(tmp_path: Path) -> str:
    """Write a fake PDF and return its path."""
    pdf = tmp_path / "test_purchase.pdf"
    pdf.write_bytes(FAKE_PDF_CONTENT)
    return str(pdf)


@pytest.fixture
def mock_engine():
    """A mock OCREngine that returns realistic extraction + verification data."""
    engine = MagicMock()
    engine.name = "mock-test"
    engine.prefers_file_path = False

    # extract() returns (dict, usage_dict)
    engine.extract.return_value = (
        {
            "loop_name": "Jane Doe, 100 Main St",
            "transaction_type": "PURCHASE_OFFER",
            "transaction_status": "PRE_OFFER",
            "property_address": {
                "street_number": "100",
                "street_name": "Main St",
                "unit_number": None,
                "city": "Dallas",
                "state_or_province": "TX",
                "postal_code": "75201",
                "county": "Dallas",
                "country": "US",
                "mls_number": "MLS-123",
                "parcel_tax_id": "",
            },
            "financials": {
                "purchase_price": "350000",
                "earnest_money": "5000",
                "loan_amount": "280000",
                "down_payment": "70000",
                "commission_rate": "3%",
            },
            "contract_dates": {
                "contract_date": "2026-01-15",
                "closing_date": "2026-02-28",
                "inspection_deadline": "2026-01-25",
                "financing_deadline": "2026-02-10",
            },
            "participants": [
                {
                    "role": "BUYER",
                    "name": "Jane Doe",
                    "email": "jane@example.com",
                    "phone": "555-0100",
                },
                {
                    "role": "SELLER",
                    "name": "John Smith",
                    "email": "john@example.com",
                    "phone": "555-0200",
                },
            ],
        },
        {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200},
    )

    # verify() returns ([VerificationCitation, ...], usage_dict)
    engine.verify.return_value = (
        [
            VerificationCitation(
                field_name="loop_name",
                extracted_value="Jane Doe, 100 Main St",
                page_number=1,
                line_or_region="top",
                surrounding_text="... Jane Doe, 100 Main ...",
                confidence=0.95,
            ),
            VerificationCitation(
                field_name="purchase_price",
                extracted_value="350000",
                page_number=1,
                line_or_region="section 3",
                surrounding_text="... Purchase Price: $350,000 ...",
                confidence=0.90,
            ),
        ],
        {"prompt_tokens": 500, "completion_tokens": 100, "total_tokens": 600},
    )

    return engine


@pytest.fixture
def mock_compliance_report():
    """A minimal ComplianceReport for testing."""
    return ComplianceReport(
        jurisdiction_key="TX:Dallas:Dallas",
        jurisdiction_display="Dallas, Dallas County, TX",
        jurisdiction_type="city",
        overall_status=ComplianceOverallStatus.PASS,
        requirements=[],
        transaction_type="PURCHASE_OFFER",
        notes=None,
    )


@pytest.fixture
def mock_enrichment():
    """A PropertyEnrichment result for testing."""
    return PropertyEnrichment(
        source="regrid",
        lookup_timestamp="2026-02-20T00:00:00+00:00",
        match_quality="exact",
        parcel_id="12345678",
        assessed_total=280000,
        year_built=1995,
        lot_size_acres=0.25,
        zoning="R-1",
        owner_name="John Smith",
    )


def _collect_emitter():
    """Return an emit function and the list it appends (event_type, data) to."""
    events: list[tuple[str, dict]] = []

    def emit(event_type: str, data: dict):
        events.append((event_type, data))

    return emit, events


# ---------------------------------------------------------------------------
# Patch targets — all in server module namespace
# ---------------------------------------------------------------------------

_SERVER = "server"


def _standard_patches(
    mock_engine,
    mock_compliance_report,
    mock_enrichment,
    *,
    regrid_configured: bool = True,
):
    """Return a list of context managers for the standard pipeline mocks."""
    return [
        patch(f"{_SERVER}.WRITE_DIST_FILES", False),
        patch(f"{_SERVER}.get_pdf_info", return_value={
            "name": "test_purchase.pdf", "size_bytes": 1024,
            "size_human": "1.0 KB", "pages": 1,
        }),
        patch(f"{_SERVER}.pdf_to_images", return_value=[MagicMock()]),
        patch(f"{_SERVER}.image_to_base64", return_value="base64data"),
        patch(f"{_SERVER}.get_engine", return_value=mock_engine),
        patch(f"{_SERVER}.property_prefill.is_configured", return_value=regrid_configured),
        patch(f"{_SERVER}.property_prefill.enrich_property", new_callable=AsyncMock, return_value=mock_enrichment),
        patch(f"{_SERVER}.async_run_compliance_check", new_callable=AsyncMock, return_value=mock_compliance_report),
        patch(f"{_SERVER}.save_document", new_callable=AsyncMock, return_value="doc-id-123"),
        patch(f"{_SERVER}.save_extraction", new_callable=AsyncMock, return_value="ext-id-456"),
    ]


# ---------------------------------------------------------------------------
# Tests — real_estate happy path
# ---------------------------------------------------------------------------


class TestRealEstateHappyPath:
    """Pipeline completes with all steps for real_estate mode."""

    @pytest.mark.asyncio
    async def test_emits_all_step_events(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        # Apply all patches
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        event_types = [e[0] for e in events]

        # Must have step + step_complete pairs, plus data events
        assert "step" in event_types
        assert "step_complete" in event_types
        assert "extraction" in event_types
        assert "validation" in event_types
        assert "citations" in event_types
        assert "property_enrichment" in event_types
        assert "compliance" in event_types
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_no_error_event(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        assert "error" not in [e[0] for e in events]

    @pytest.mark.asyncio
    async def test_step_count_matches(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        """Total steps should be 8 for real_estate with Regrid configured."""
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        # First step event tells us the total
        step_events = [e for e in events if e[0] == "step"]
        assert step_events[0][1]["total"] == 8  # Load,Convert,Extract,Validate,Verify,Enrich,Compliance,Output

    @pytest.mark.asyncio
    async def test_validation_succeeds(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        validation = [e[1] for e in events if e[0] == "validation"][0]
        assert validation["success"] is True
        assert validation["errors"] == []

    @pytest.mark.asyncio
    async def test_citations_emitted(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        citations_event = [e[1] for e in events if e[0] == "citations"][0]
        assert len(citations_event["citations"]) == 2
        assert citations_event["overall_confidence"] == pytest.approx(0.925)

    @pytest.mark.asyncio
    async def test_complete_has_extraction_id(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        complete_data = [e[1] for e in events if e[0] == "complete"][0]
        assert complete_data["extraction_id"] == "ext-id-456"
        assert complete_data["mode"] == "real_estate"

    @pytest.mark.asyncio
    async def test_enrichment_populates_parcel_id(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        """When enrichment finds a parcel, it back-fills parcel_tax_id."""
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        enrichment_event = [e[1] for e in events if e[0] == "property_enrichment"][0]
        assert enrichment_event["match_quality"] == "exact"
        assert enrichment_event["parcel_id"] == "12345678"

    @pytest.mark.asyncio
    async def test_token_usage_accumulated(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        complete_data = [e[1] for e in events if e[0] == "complete"][0]
        # extract: 1000+200=1200, verify: 500+100=600 → total: 1800
        assert complete_data["total_tokens"] == 1800
        assert complete_data["prompt_tokens"] == 1500
        assert complete_data["completion_tokens"] == 300


# ---------------------------------------------------------------------------
# Tests — no Regrid configured
# ---------------------------------------------------------------------------


class TestNoRegridConfigured:
    """When Regrid is not configured, enrichment step is skipped."""

    @pytest.mark.asyncio
    async def test_no_enrichment_event(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(
            mock_engine, mock_compliance_report, mock_enrichment,
            regrid_configured=False,
        )

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        event_types = [e[0] for e in events]
        assert "property_enrichment" not in event_types
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_step_count_without_enrichment(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()
        patches = _standard_patches(
            mock_engine, mock_compliance_report, mock_enrichment,
            regrid_configured=False,
        )

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        step_events = [e for e in events if e[0] == "step"]
        assert step_events[0][1]["total"] == 7  # No enrichment step


# ---------------------------------------------------------------------------
# Tests — error path
# ---------------------------------------------------------------------------


class TestErrorPath:
    """Pipeline emits 'error' event when an exception occurs."""

    @pytest.mark.asyncio
    async def test_pdf_conversion_failure_emits_error(self, tmp_pdf, mock_engine):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()

        patches = [
            patch(f"{_SERVER}.WRITE_DIST_FILES", False),
            patch(f"{_SERVER}.get_pdf_info", side_effect=ValueError("Not a valid PDF")),
            patch(f"{_SERVER}.get_engine", return_value=mock_engine),
            patch(f"{_SERVER}.save_document", new_callable=AsyncMock),
            patch(f"{_SERVER}.save_extraction", new_callable=AsyncMock),
        ]

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        error_events = [e for e in events if e[0] == "error"]
        assert len(error_events) == 1
        assert "Not a valid PDF" in error_events[0][1]["message"]

    @pytest.mark.asyncio
    async def test_engine_extract_failure_emits_error(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        mock_engine.extract.side_effect = RuntimeError("API timeout")
        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        error_events = [e for e in events if e[0] == "error"]
        assert len(error_events) == 1
        assert "API timeout" in error_events[0][1]["message"]

    @pytest.mark.asyncio
    async def test_no_complete_event_on_error(self, tmp_pdf, mock_engine):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()

        patches = [
            patch(f"{_SERVER}.WRITE_DIST_FILES", False),
            patch(f"{_SERVER}.get_pdf_info", side_effect=ValueError("Bad PDF")),
            patch(f"{_SERVER}.get_engine", return_value=mock_engine),
            patch(f"{_SERVER}.save_document", new_callable=AsyncMock),
            patch(f"{_SERVER}.save_extraction", new_callable=AsyncMock),
        ]

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        assert "complete" not in [e[0] for e in events]


# ---------------------------------------------------------------------------
# Tests — validation errors (lenient fallback)
# ---------------------------------------------------------------------------


class TestValidationErrors:
    """When schema validation fails, pipeline still completes via lenient fallback."""

    @pytest.mark.asyncio
    async def test_bad_extraction_still_completes(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        # Return malformed data that won't validate against DotloopLoopDetails
        mock_engine.extract.return_value = (
            {"loop_name": "Test", "bad_field": True},
            {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )

        emit, events = _collect_emitter()
        patches = _standard_patches(mock_engine, mock_compliance_report, mock_enrichment)

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        # Validation should report errors
        validation = [e[1] for e in events if e[0] == "validation"][0]
        assert validation["success"] is False
        assert len(validation["errors"]) > 0

        # Pipeline should still complete (not error)
        assert "complete" in [e[0] for e in events]
        assert "error" not in [e[0] for e in events]


# ---------------------------------------------------------------------------
# Tests — gov mode
# ---------------------------------------------------------------------------


class TestGovMode:
    """Gov mode runs PII scan and skips compliance + enrichment."""

    @pytest.fixture
    def mock_gov_engine(self):
        """Engine that returns gov-mode (FOIA) extraction data."""
        engine = MagicMock()
        engine.name = "mock-test"
        engine.prefers_file_path = False

        engine.extract.return_value = (
            {
                "request_number": "FOIA-2026-001",
                "agency": "Department of Records",
                "requester_name": "Alice Johnson",
                "requester_email": "alice@example.com",
                "date_submitted": "2026-01-10",
                "description": "All records related to contract #123.",
                "status": "PENDING",
            },
            {"prompt_tokens": 800, "completion_tokens": 150, "total_tokens": 950},
        )

        engine.verify.return_value = (
            [
                VerificationCitation(
                    field_name="request_number",
                    extracted_value="FOIA-2026-001",
                    page_number=1,
                    line_or_region="header",
                    surrounding_text="... FOIA-2026-001 ...",
                    confidence=0.98,
                ),
            ],
            {"prompt_tokens": 400, "completion_tokens": 80, "total_tokens": 480},
        )

        engine.ocr_raw_text.return_value = (
            ["Page 1 text with SSN 123-45-6789 and phone 555-0100"],
            {"prompt_tokens": 200, "completion_tokens": 50, "total_tokens": 250},
        )

        return engine

    @pytest.mark.asyncio
    async def test_gov_mode_emits_pii_event(self, tmp_pdf, mock_gov_engine):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()

        patches = [
            patch(f"{_SERVER}.WRITE_DIST_FILES", False),
            patch(f"{_SERVER}.get_pdf_info", return_value={
                "name": "foia_request.pdf", "size_bytes": 512,
                "size_human": "512 B", "pages": 1,
            }),
            patch(f"{_SERVER}.pdf_to_images", return_value=[MagicMock()]),
            patch(f"{_SERVER}.image_to_base64", return_value="base64data"),
            patch(f"{_SERVER}.get_engine", return_value=mock_gov_engine),
            patch(f"{_SERVER}.property_prefill.is_configured", return_value=False),
            patch(f"{_SERVER}.save_document", new_callable=AsyncMock, return_value="doc-id-gov"),
            patch(f"{_SERVER}.save_extraction", new_callable=AsyncMock, return_value="ext-id-gov"),
        ]

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)

            # Gov mode must be enabled for the pipeline function (it's gated at the route level, not here)
            await _extraction_pipeline("gov", tmp_pdf, emit)

        event_types = [e[0] for e in events]
        assert "pii" in event_types
        assert "compliance" not in event_types
        assert "property_enrichment" not in event_types
        assert "complete" in event_types

    @pytest.mark.asyncio
    async def test_gov_mode_pii_has_findings(self, tmp_pdf, mock_gov_engine):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()

        patches = [
            patch(f"{_SERVER}.WRITE_DIST_FILES", False),
            patch(f"{_SERVER}.get_pdf_info", return_value={
                "name": "foia_request.pdf", "size_bytes": 512,
                "size_human": "512 B", "pages": 1,
            }),
            patch(f"{_SERVER}.pdf_to_images", return_value=[MagicMock()]),
            patch(f"{_SERVER}.image_to_base64", return_value="base64data"),
            patch(f"{_SERVER}.get_engine", return_value=mock_gov_engine),
            patch(f"{_SERVER}.property_prefill.is_configured", return_value=False),
            patch(f"{_SERVER}.save_document", new_callable=AsyncMock, return_value="doc-id-gov"),
            patch(f"{_SERVER}.save_extraction", new_callable=AsyncMock, return_value="ext-id-gov"),
        ]

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("gov", tmp_pdf, emit)

        pii_event = [e[1] for e in events if e[0] == "pii"][0]
        assert pii_event["risk_score"] > 0
        assert len(pii_event["findings"]) > 0


# ---------------------------------------------------------------------------
# Tests — DB save failure is non-fatal
# ---------------------------------------------------------------------------


class TestDBFailureNonFatal:
    """Pipeline completes even when DB save raises."""

    @pytest.mark.asyncio
    async def test_db_error_still_completes(
        self, tmp_pdf, mock_engine, mock_compliance_report, mock_enrichment,
    ):
        from server import _extraction_pipeline

        emit, events = _collect_emitter()

        patches = [
            patch(f"{_SERVER}.WRITE_DIST_FILES", False),
            patch(f"{_SERVER}.get_pdf_info", return_value={
                "name": "test.pdf", "size_bytes": 1024,
                "size_human": "1.0 KB", "pages": 1,
            }),
            patch(f"{_SERVER}.pdf_to_images", return_value=[MagicMock()]),
            patch(f"{_SERVER}.image_to_base64", return_value="base64data"),
            patch(f"{_SERVER}.get_engine", return_value=mock_engine),
            patch(f"{_SERVER}.property_prefill.is_configured", return_value=True),
            patch(f"{_SERVER}.property_prefill.enrich_property", new_callable=AsyncMock, return_value=mock_enrichment),
            patch(f"{_SERVER}.async_run_compliance_check", new_callable=AsyncMock, return_value=mock_compliance_report),
            patch(f"{_SERVER}.save_document", new_callable=AsyncMock, side_effect=Exception("DB connection refused")),
            patch(f"{_SERVER}.save_extraction", new_callable=AsyncMock),
        ]

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            await _extraction_pipeline("real_estate", tmp_pdf, emit)

        event_types = [e[0] for e in events]
        assert "complete" in event_types
        assert "error" not in event_types

        # extraction_id should be absent since DB save failed
        complete_data = [e[1] for e in events if e[0] == "complete"][0]
        assert "extraction_id" not in complete_data
