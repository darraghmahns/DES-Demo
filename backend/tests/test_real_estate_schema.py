from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas import DotloopLoopDetails


def _base_offer_payload() -> dict:
    return {
        "loop_name": "Jane Doe, 100 Main St, Dallas, TX 75201",
        "transaction_type": "PURCHASE_OFFER",
        "transaction_status": "PRE_OFFER",
        "property_address": {
            "street_number": "100",
            "street_name": "Main St",
            "city": "Dallas",
            "state_or_province": "TX",
            "postal_code": "75201",
            "country": "US",
        },
        "financials": {
            "purchase_price": 350000.0,
            "closing_fee_paid_by": "Equally Shared",
        },
        "contract_dates": {
            "contract_agreement_date": "01/15/2026",
            "inspection_release_date": "04/10/2026",
            "inspection_release_time": "5:00 p.m. (Mountain Time)",
        },
        "terms": {
            "inspection_release_clause_text": "Buyers to obtain a second opinion from a licensed contractor regarding the recommended repair and/or replacement of the downstairs washing machine drain line.",
            "buyer_physically_visited_property": True,
        },
        "participants": [
            {
                "role": "BUYER",
                "full_name": "Jane Doe",
                "email": "jane@example.com",
                "phone": None,
                "company_name": None,
            },
        ],
    }


def test_dotloop_loop_details_accepts_release_and_checkbox_fields():
    validated = DotloopLoopDetails.model_validate(_base_offer_payload())

    assert validated.financials.closing_fee_paid_by == "Equally Shared"
    assert validated.contract_dates.inspection_release_date == "04/10/2026"
    assert validated.contract_dates.inspection_release_time == "5:00 p.m. (Mountain Time)"
    assert validated.terms.inspection_release_clause_text.startswith("Buyers to obtain")
    assert validated.terms.buyer_physically_visited_property is True


def test_dotloop_loop_details_rejects_unknown_fee_responsibility():
    payload = _base_offer_payload()
    payload["financials"]["closing_fee_paid_by"] = "Split Between Parties"

    with pytest.raises(ValidationError):
        DotloopLoopDetails.model_validate(payload)
