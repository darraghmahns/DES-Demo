"""Neural OCR extraction logic for real estate and government documents."""

import json

from openai import OpenAI

REAL_ESTATE_SYSTEM_PROMPT = """You are an expert real estate document analyzer. Extract ALL relevant fields from this purchase agreement into the exact JSON schema below.

You MUST return a JSON object with this exact structure:
{
  "loop_name": "<Buyer Name>, <Street Number> <Street Name>, <City>, <State> <ZIP>",
  "transaction_type": "PURCHASE_OFFER",
  "transaction_status": "PRE_OFFER",
  "property_address": {
    "street_number": "",
    "street_name": "",
    "unit_number": null,
    "city": "",
    "state_or_province": "",
    "postal_code": "",
    "country": "US",
    "county": null,
    "mls_number": null,
    "parcel_tax_id": null
  },
  "financials": {
    "purchase_price": 0.0,
    "earnest_money_amount": null,
    "earnest_money_held_by": null,
    "sale_commission_rate": null,
    "sale_commission_total": null
  },
  "contract_dates": {
    "contract_agreement_date": null,
    "closing_date": null,
    "offer_date": null,
    "offer_expiration_date": null,
    "inspection_date": null
  },
  "participants": [
    {"full_name": "", "role": "BUYER", "email": null, "phone": null, "company_name": null}
  ]
}

Rules:
- Extract values EXACTLY as written in the document.
- For prices, use numeric values only (no $ signs or commas). Example: 485000.0
- For dates, use MM/DD/YYYY format.
- Valid participant roles: BUYER, SELLER, LISTING_AGENT, BUYING_AGENT, LISTING_BROKER, BUYING_BROKER, ESCROW_TITLE_REP, LOAN_OFFICER, OTHER
- Include ALL participants found (buyers, sellers, agents, brokers, title reps).
- If a field is not present in the document, use null.
- Do NOT make up or infer values that are not explicitly stated.
"""

GOV_SYSTEM_PROMPT = """You are an expert government document analyzer specializing in FOIA (Freedom of Information Act) requests. Extract ALL relevant fields from this FOIA request into the exact JSON schema below.

You MUST return a JSON object with this exact structure:
{
  "requester": {
    "first_name": "",
    "last_name": "",
    "email": null,
    "phone": null,
    "address_street": null,
    "address_city": null,
    "address_state": null,
    "address_zip": null,
    "organization": null
  },
  "request_description": "",
  "request_category": null,
  "agency": "",
  "agency_component_name": null,
  "fee_amount_willing": null,
  "fee_waiver": false,
  "expedited_processing": false,
  "date_range_start": null,
  "date_range_end": null
}

Rules:
- Extract requester information exactly as written in the letter.
- Capture the FULL request description (what records are being sought).
- request_category must be one of: "commercial", "educational", "media", "other", or null.
- For dates, use MM/DD/YYYY format.
- fee_waiver and expedited_processing are boolean — set to true if the letter requests them.
- If a field is not present in the document, use null.
- Do NOT make up or infer values that are not explicitly stated.
"""

# Used to get raw text from images for PII scanning
OCR_SYSTEM_PROMPT = """You are an OCR engine. Extract ALL text from this document image exactly as it appears, preserving line breaks and formatting. Return ONLY the raw text, nothing else. Include every character, number, and symbol visible on the page."""


def extract_from_images(
    images_b64: list[str],
    mode: str,
    client: OpenAI,
) -> dict:
    """Send document page images to GPT-4o Vision and get structured extraction.

    Args:
        images_b64: List of base64-encoded PNG strings, one per page.
        mode: 'real_estate' or 'gov'.
        client: OpenAI client instance.

    Returns:
        Parsed JSON dict matching the target schema.
    """
    system_prompt = REAL_ESTATE_SYSTEM_PROMPT if mode == "real_estate" else GOV_SYSTEM_PROMPT

    content: list[dict] = []
    for i, img_b64 in enumerate(images_b64):
        content.append({"type": "text", "text": f"--- Page {i + 1} of {len(images_b64)} ---"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"},
        })

    content.append({
        "type": "text",
        "text": "Extract all data from the above document pages into the JSON schema specified. Return ONLY valid JSON.",
    })

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=4096,
    )

    return json.loads(response.choices[0].message.content)


def extract_raw_text(images_b64: list[str], client: OpenAI) -> list[str]:
    """Extract raw text from document images for PII scanning.

    Args:
        images_b64: List of base64-encoded PNG strings.
        client: OpenAI client instance.

    Returns:
        List of text strings, one per page.
    """
    page_texts: list[str] = []

    for i, img_b64 in enumerate(images_b64):
        content = [
            {"type": "text", "text": f"Extract all text from page {i + 1}:"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"},
            },
        ]

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": OCR_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0.0,
            max_tokens=4096,
        )

        page_texts.append(response.choices[0].message.content)

    return page_texts
