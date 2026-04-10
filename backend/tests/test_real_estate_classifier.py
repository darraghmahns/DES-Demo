from __future__ import annotations

from real_estate_classifier import (
    build_classification_fallback_payload,
    build_text_samples,
    classify_from_samples,
    classify_with_model_fallback,
)


def test_footer_exact_classifies_montana_buy_sell_residential():
    samples = build_text_samples(
        [
            "\n".join(
                [
                    "BUY-SELL AGREEMENT (RESIDENTIAL)",
                    "Buyer and Seller agree to the following terms.",
                    "© 2022 Montana Association of REALTORS®",
                    "Buy-Sell Agreement Residential, April 2022",
                    "Page 1 of 9",
                ]
            )
        ]
    )

    result = classify_from_samples(filename="offer.pdf", samples=samples)

    assert result.document_form_id == "MAR_BUY_SELL_RESIDENTIAL"
    assert result.document_type == "PURCHASE_OFFER"
    assert result.classification_source == "footer_exact"
    assert result.document_revision == "April 2022"
    assert result.document_footer_text == "Buy-Sell Agreement Residential"


def test_header_exact_classifies_when_footer_missing():
    samples = build_text_samples(
        [
            "\n".join(
                [
                    "Counter Offer",
                    "(Residential Purchase Agreement)",
                    "Buyer and seller propose these revised terms.",
                ]
            )
        ]
    )

    result = classify_from_samples(filename="counter_offer_scan.pdf", samples=samples)

    assert result.document_form_id == "MAR_COUNTER_OFFER"
    assert result.document_type == "COUNTEROFFER"
    assert result.classification_source == "header_exact"
    assert result.document_subtitle == "(Residential Purchase Agreement)"


def test_unknown_classification_preserves_footer_metadata_for_model_fallback():
    samples = build_text_samples(
        [
            "\n".join(
                [
                    "Special Form",
                    "Some body text",
                    "© 2022 Montana Association of REALTORS®",
                    "Unrecognized Custom Addendum, April 2022",
                    "Page 1 of 1",
                ]
            )
        ]
    )

    result = classify_from_samples(filename="custom_addendum.pdf", samples=samples)
    payload = build_classification_fallback_payload("custom_addendum.pdf", result)

    assert result.document_form_id == "UNKNOWN"
    assert result.document_footer_text == "Unrecognized Custom Addendum"
    assert result.document_revision == "April 2022"
    assert payload["document_footer_text"] == "Unrecognized Custom Addendum"
    assert payload["document_revision"] == "April 2022"


def test_model_fallback_only_promotes_high_confidence_known_forms():
    deterministic = classify_from_samples(
        filename="mystery.pdf",
        samples=build_text_samples(["Mystery document with no obvious title"]),
    )

    low_confidence = classify_with_model_fallback(
        deterministic,
        {"document_form_id": "MAR_ESCALATION_ADDENDUM", "classification_confidence": 0.6},
    )
    high_confidence = classify_with_model_fallback(
        deterministic,
        {
            "document_form_id": "MAR_ESCALATION_ADDENDUM",
            "document_title": "Escalation Addendum",
            "classification_confidence": 0.91,
        },
    )

    assert low_confidence.document_form_id == "UNKNOWN"
    assert high_confidence.document_form_id == "MAR_ESCALATION_ADDENDUM"
    assert high_confidence.document_type == "ADDENDUM"
    assert high_confidence.classification_source == "model_fallback"
