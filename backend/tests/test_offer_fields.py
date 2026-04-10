from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from offer_fields import (
    build_offer_field_citations,
    build_offer_fields,
    canonicalize_citation_field_name,
    ensure_required_citations,
    merge_recovered_offer_fields,
)
from schemas import VerificationCitation


def test_merge_recovered_offer_fields_only_fills_missing_values():
    extracted = {
        "financials": {
            "purchase_price": 612500.0,
            "earnest_money_amount": None,
        },
        "terms": {
            "inspection_contingency": None,
        },
        "participants": [
            {"role": "BUYER", "full_name": "Jane Buyer", "email": None, "phone": None, "company_name": None},
        ],
    }

    merged, applied = merge_recovered_offer_fields(
        extracted,
        {
            "financials.purchase_price": 700000.0,  # should not overwrite existing non-null value
            "financials.earnest_money_amount": 15000.0,
            "terms.inspection_contingency": False,
            "participants.listing_agent.full_name": "Lara Listing",
        },
    )

    assert merged["financials"]["purchase_price"] == 612500.0
    assert merged["financials"]["earnest_money_amount"] == 15000.0
    assert merged["terms"]["inspection_contingency"] is False
    assert any(p.get("role") == "LISTING_AGENT" and p.get("full_name") == "Lara Listing" for p in merged["participants"])
    assert "financials.earnest_money_amount" in applied
    assert "terms.inspection_contingency" in applied
    assert "financials.purchase_price" not in applied


def test_merge_recovered_offer_fields_normalizes_checkbox_values_for_new_fields():
    extracted = {
        "financials": {
            "purchase_price": 612500.0,
            "closing_fee_paid_by": None,
        },
        "contract_dates": {
            "inspection_release_date": None,
            "inspection_release_time": None,
        },
        "terms": {
            "inspection_release_clause_text": None,
            "buyer_physically_visited_property": None,
        },
    }

    merged, applied = merge_recovered_offer_fields(
        extracted,
        {
            "financials.closing_fee_paid_by": "split",
            "contract_dates.inspection_release_date": "04/10/2026",
            "contract_dates.inspection_release_time": "5:00 p.m. (Mountain Time)",
            "terms.inspection_release_clause_text": "Buyers to obtain a second opinion.",
            "terms.buyer_physically_visited_property": "has not physically visited the property",
        },
    )

    assert merged["financials"]["closing_fee_paid_by"] == "Equally Shared"
    assert merged["contract_dates"]["inspection_release_date"] == "04/10/2026"
    assert merged["contract_dates"]["inspection_release_time"] == "5:00 p.m. (Mountain Time)"
    assert merged["terms"]["inspection_release_clause_text"] == "Buyers to obtain a second opinion."
    assert merged["terms"]["buyer_physically_visited_property"] is False
    assert "financials.closing_fee_paid_by" in applied
    assert "terms.buyer_physically_visited_property" in applied


def test_build_offer_fields_includes_new_release_and_checkbox_keys():
    fields, raw_extras = build_offer_fields(
        {
            "contract_dates": {
                "inspection_release_date": "04/10/2026",
                "inspection_release_time": "5:00 p.m. (Mountain Time)",
            },
            "terms": {
                "inspection_release_clause_text": "Buyers to obtain a second opinion.",
                "buyer_physically_visited_property": True,
            },
        },
    )

    assert fields["inspection_release_date"] == "04/10/2026"
    assert fields["inspection_release_time"] == "5:00 p.m. (Mountain Time)"
    assert fields["inspection_release_clause_text"] == "Buyers to obtain a second opinion."
    assert fields["buyer_physically_visited_property"] is True
    assert raw_extras == {}


def test_build_offer_field_citations_derives_states_and_stale_flags():
    grouped, meta, overridden = build_offer_field_citations(
        [
            {
                "field_name": "financials.purchase_price",
                "extracted_value": "612500.0",
                "page_number": 1,
                "line_or_region": "Section 2",
                "surrounding_text": "Purchase price 612500",
                "confidence": 0.97,
            },
            {
                "field_name": "terms.inspection_contingency",
                "extracted_value": "false",
                "page_number": 0,
                "line_or_region": "Not found",
                "surrounding_text": "NOT FOUND",
                "confidence": 0.0,
            },
        ],
        overrides={"purchase_price": 620000.0},
    )

    assert grouped["purchase_price"][0]["field_name"] == "financials.purchase_price"
    assert meta["purchase_price"] == {"state": "supported", "stale": True}
    assert meta["inspection_contingency"] == {"state": "not_found", "stale": False}
    assert meta["county"] == {"state": "not_captured", "stale": False}
    assert overridden == ["purchase_price"]


def test_canonicalize_citation_field_name_maps_shorthand_and_labels():
    assert canonicalize_citation_field_name("purchase_price") == "financials.purchase_price"
    assert canonicalize_citation_field_name("Purchase Price") == "financials.purchase_price"
    assert canonicalize_citation_field_name("financials.purchase_price") == "financials.purchase_price"


def test_ensure_required_citations_does_not_add_placeholder_when_alias_matches():
    citations = [
        VerificationCitation(
            field_name="purchase_price",
            extracted_value="612500.0",
            page_number=1,
            line_or_region="Section 2",
            surrounding_text="Purchase Price: $612,500",
            confidence=0.97,
        ),
    ]

    merged = ensure_required_citations(
        citations,
        [{"path": "financials.purchase_price", "value": 612500.0}],
    )

    assert len(merged) == 1
    assert merged[0].field_name == "purchase_price"


def test_build_offer_field_citations_normalizes_shorthand_and_filters_page_zero_placeholder():
    grouped, meta, _ = build_offer_field_citations(
        [
            {
                "field_name": "purchase_price",
                "extracted_value": "612500.0",
                "page_number": 1,
                "line_or_region": "Section 2",
                "surrounding_text": "Purchase Price: $612,500",
                "confidence": 0.97,
            },
            {
                "field_name": "financials.purchase_price",
                "extracted_value": "612500.0",
                "page_number": 0,
                "line_or_region": "Not found",
                "surrounding_text": "NOT FOUND",
                "confidence": 0.0,
            },
        ],
    )

    assert meta["purchase_price"] == {"state": "supported", "stale": False}
    assert len(grouped["purchase_price"]) == 1
    assert grouped["purchase_price"][0]["field_name"] == "financials.purchase_price"
    assert grouped["purchase_price"][0]["page_number"] == 1


@pytest.mark.asyncio
async def test_compare_offers_returns_field_citations_and_meta():
    from server import compare_offers

    extraction = {
        "source_file": "offer.pdf",
        "extracted_data": {
            "financials": {"purchase_price": 612500.0},
            "terms": {"inspection_contingency": None},
            "participants": [{"role": "BUYER", "full_name": "Jane Buyer"}],
        },
        "citations": [
            {
                "field_name": "financials.purchase_price",
                "extracted_value": "612500.0",
                "page_number": 1,
                "line_or_region": "Section 2",
                "surrounding_text": "Purchase price 612500",
                "confidence": 0.97,
            },
            {
                "field_name": "terms.inspection_contingency",
                "extracted_value": "null",
                "page_number": 0,
                "line_or_region": "Not found",
                "surrounding_text": "NOT FOUND",
                "confidence": 0.0,
            },
        ],
        "field_overrides": {"purchase_price": 615000.0},
    }

    with patch("server.get_extraction", new_callable=AsyncMock, return_value=extraction):
        response = await compare_offers(extraction_ids="doc-1:0", user=None)

    offer = response["offers"][0]
    assert offer["field_citations"]["purchase_price"][0]["field_name"] == "financials.purchase_price"
    assert offer["field_citation_meta"]["purchase_price"] == {"state": "supported", "stale": True}
    assert offer["field_citation_meta"]["inspection_contingency"] == {"state": "not_found", "stale": False}
    assert offer["overridden_fields"] == ["purchase_price"]


@pytest.mark.asyncio
async def test_compare_offers_prefers_normalized_offer_projection():
    from server import compare_offers

    extraction = {
        "source_file": "inspection.pdf",
        "extracted_data": {
            "document_title": "Inspection Notice",
            "summary": "Non-comparison payload",
        },
        "normalized_offer_projection": {
            "financials": {"purchase_price": 612500.0},
            "terms": {"inspection_contingency": False},
        },
        "citations": [],
        "field_overrides": {},
    }

    with patch("server.get_extraction", new_callable=AsyncMock, return_value=extraction):
        response = await compare_offers(extraction_ids="doc-1:0", user=None)

    offer = response["offers"][0]
    assert offer["fields"]["purchase_price"] == 612500.0
    assert offer["fields"]["inspection_contingency"] is False
