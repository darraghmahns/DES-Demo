from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from offer_fields import build_offer_field_citations, merge_recovered_offer_fields


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
