"""Neural OCR extraction logic for real estate and government documents."""

import json
import logging
import re
from typing import Any

from openai import OpenAI

from offer_fields import stringify_field_value

log = logging.getLogger(__name__)

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
    "sale_commission_total": null,
    "financing_type": null,
    "down_payment_amount": null,
    "down_payment_percentage": null,
    "closing_fee_paid_by": null,
    "fincen_fee_paid_by": null
  },
  "contract_dates": {
    "contract_agreement_date": null,
    "closing_date": null,
    "offer_date": null,
    "offer_expiration_date": null,
    "inspection_date": null,
    "inspection_negotiation_deadline": null,
    "insurance_contingency_date": null,
    "loan_application_deadline": null,
    "seller_response_time": null,
    "possession_date": null,
    "opd_delivery_date": null
  },
  "terms": {
    "escalation_clause": null,
    "home_warranty": null,
    "hoa_approval_contingency": null,
    "survey_contingency": null,
    "as_is": null,
    "inclusions": null,
    "exclusions": null,
    "leased_items": null,
    "detection_devices": null,
    "opd_delivered": null,
    "inspection_contingency": null,
    "financing_contingency": null,
    "appraisal_contingency": null,
    "title_contingency": null,
    "insurance_contingency": null,
    "sale_of_home_contingency": null,
    "additional_provisions": null,
    "notes": null
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
- Include ALL participants found anywhere in the document: buyers, sellers, agents, and brokers.
  Use the printed name whenever possible — not a signature.

  BUYERS: Look near the top of the document for names identified as the buyer. Common patterns:
    - A name written on a line labeled "Buyer:", "Purchaser:", or similar
    - A name written above or below a tenancy-type clause (e.g. "as joint tenants", "as tenants in common", "individually")
    - Names printed in the buyer signature/commitment block (near "Name Printed:", "Buyer's Printed Name", etc.)

  SELLERS: Look in the seller signature/acceptance block near the end of the document. Common patterns:
    - A name written on a line labeled "Name Printed:", "Seller:", "Seller's Name:", or "Owner:"
    - The section may be titled "SELLER'S COMMITMENT", "SELLER ACCEPTANCE", "SELLER'S AGREEMENT", or similar
    - May include estate or trust names (e.g. "Charles T. Coston Estate, Thomas Coston PR")

  AGENTS & BROKERS: Look for a licensee/agent disclosure section, usually near the end of the document
  (often after the signature blocks). This section discloses which real estate licensees are involved
  and in what capacity. It may be titled:
    - "RELATIONSHIP CONFIRMATION", "AGENCY DISCLOSURE", "LICENSEE DISCLOSURE",
      "BROKER INFORMATION", "AGENT INFORMATION", or similar
  In this section, extract:
    - The licensee's full name (may appear as plain text, above a label like "(name of licensee)", or on a
      line labeled "Licensee:", "Agent:", "Salesperson:", "Broker:", etc.)
    - Their brokerage/company name (often on the same line after "of [brokerage name]", or labeled
      "Brokerage:", "Company:", "(name of brokerage company)", etc.)
    - Their phone number and email address
    - Their role — look for a checked checkbox or statement indicating Buyer's Agent / Seller's Agent /
      Dual Agent / Transaction Broker / Listing Agent / Selling Agent. Map:
        Buyer's Agent / Selling Agent / Buyer's Representative -> BUYING_AGENT
        Seller's Agent / Listing Agent / Seller's Representative -> LISTING_AGENT
        Dual Agent -> create two entries, one BUYING_AGENT and one LISTING_AGENT with the same name
    - If multiple licensee names appear in a single entry (e.g. "Jane Smith and John Doe"), create a
      separate participant for each name with the same role, company, phone, and email.

- For financials:
  - financing_type: the loan/financing type (e.g. "Conventional", "FHA", "VA", "USDA", "Cash"). Use null if not stated.
  - down_payment_amount: numeric dollar amount of the down payment. Use null if not a dollar figure.
  - down_payment_percentage: if the down payment is expressed as a percentage (e.g. "5% of Purchase Price"), store the exact string here (e.g. "5%"). Use null if a dollar amount is given instead. Do NOT calculate a dollar figure from a percentage — store the percentage string as-is.
  - closing_fee_paid_by: who pays the title company / closing agent / settlement fee. Look for a section
    or line about closing costs or closing fees — may be labeled "CLOSING FEE", "CLOSING COSTS",
    "SETTLEMENT FEE", "TITLE/CLOSING FEE", or similar. Look for Seller / Buyer / Equally Shared / Split
    checkboxes on that line. Extract the checked option as a string (e.g. "Equally Shared", "Seller", "Buyer"). Use null if not present.
  - fincen_fee_paid_by: who pays the FinCEN reporting fee. Look for a section mentioning FinCEN,
    federal reporting, financial crimes reporting, or similar — may be labeled "FINCEN FEE",
    "FINCEN REPORTS", "FEDERAL REPORTING FEE". Look for Seller / Buyer / Equally Shared checkboxes.
    Extract the checked option as a string. Use null if not present.

- For contract_dates:
  - contract_agreement_date: the date this agreement/offer was made or signed. Usually found near the
    very top of the document — look for "Date:", "Agreement Date:", "Offer Date:", or a sentence like
    "This Agreement is made this ___ day of ___". NOT the closing date.
  - closing_date: the anticipated closing/settlement date.
  - offer_date: use the same value as contract_agreement_date if no separate offer date is stated.
  - offer_expiration_date: the deadline by which the seller must accept. May be labeled
    "Offer Expiration", "Acceptance Deadline", "Buyer's Commitment" deadline, or found in a sentence
    like "Buyer grants Seller until [date] to accept".
  - inspection_date: the inspection contingency deadline (last day to complete inspection).
  - inspection_negotiation_deadline: the deadline to complete negotiations following inspection.
  - insurance_contingency_date: the insurance contingency deadline date.
  - loan_application_deadline: the date by which the buyer must submit their loan application.
  - seller_response_time: same as offer_expiration_date if no separate field exists; otherwise the
    specific time/date by which the seller must respond.
  - possession_date: when the buyer takes physical possession. If a specific date is stated, use
    MM/DD/YYYY. If possession is described conditionally (e.g. "upon recording of the deed", "at
    closing", "at time of closing"), store that phrase as a string. Use null only if not mentioned.
  - opd_delivery_date: deadline for seller to deliver the Owner's Property Disclosure (OPD) form. Use null if only a checkbox (delivered/not delivered) is present without a specific date.

- For terms (read the ENTIRE document including all addenda and every checkbox):

  IMPORTANT — Checkbox reading: These forms use named contingency sections with checkboxes. A filled or
  checked box (checked box symbol, checkmark, [X], bold X, or any filled square/circle) means the item
  IS included (true). An empty box (empty box symbol or blank line) means NOT included (false). Read
  every checkbox carefully — do not skip sections. Also look for: explicit "YES/NO" checkboxes, radio
  buttons marked with dots, written "N/A" or "Waived" which means false, and addenda checklist items
  where a checked box next to an addendum title confirms its inclusion.

  - escalation_clause: true if an escalation clause or addendum is checked/present. May be labeled
    "ESCALATION CLAUSE", "ESCALATION ADDENDUM", or listed in an addenda checklist as checked.
    false if explicitly unchecked/absent; null if the section does not appear.
  - home_warranty: true if a HOME WARRANTY section is checked or buyer requests one; false if explicitly waived or unchecked; null if not mentioned.
  - hoa_approval_contingency: true if the offer is contingent on HOA approval or HOA documents review; null if not mentioned.
  - survey_contingency: true if the offer is contingent on a satisfactory survey; null if not mentioned.
  - as_is: true if property is sold "as-is" with no repairs; false if seller agrees to make repairs; null if not stated.
  - inclusions: comma-separated list of personal property/fixtures included in the sale (e.g. "refrigerator, washer, dryer, window treatments"). Look for an INCLUSIONS or PERSONAL PROPERTY INCLUDED section. null if none stated.
  - exclusions: comma-separated list of items explicitly excluded from the sale. Look for an EXCLUSIONS section. null if none stated.
  - leased_items: look for a section about leased or rented personal property — may be labeled
    "LEASED/RENTED PERSONAL PROPERTY", "LEASED ITEMS", "RENTED ITEMS", or similar. If items are checked
    (e.g. solar panels, water softener, propane tank), list them comma-separated. If the section
    indicates "None" or no items are checked, use null.
  - detection_devices: look for a section about detection devices — may be labeled "DETECTION DEVICES",
    "SMOKE DETECTORS", "SAFETY DEVICES", or similar. List ONLY the device types whose checkbox is
    explicitly checked/filled in the document, comma-separated (e.g. "Smoke detector, Carbon monoxide
    detector"). CRITICAL: do NOT list devices that are merely printed on the form as options — only
    list them if their checkbox is visibly checked. If the section is present but no boxes are checked,
    use null. If the section is absent, use null.
  - opd_delivered: look for a section about Owner's Property Disclosure / Property Disclosure Statement
    delivery — may be labeled "DELIVERY OF OWNER'S PROPERTY DISCLOSURE", "OPD", "PROPERTY DISCLOSURE
    CONTINGENCY", or similar. true if a checkbox or statement indicates it HAS been delivered to the
    buyer — common phrasing includes "Has Received A Copy of the OPD", "OPD has been delivered",
    "Buyer acknowledges receipt", or a checked "Delivered" box. false if NOT yet delivered (e.g.
    "Has Not Received", "OPD to be delivered within X days"). null if the section is not present.
  - inspection_contingency: true if the document contains an active inspection contingency giving the
    buyer the right to inspect. May be in a section labeled "INSPECTION CONTINGENCY", "PROPERTY
    INSPECTION CONTINGENCY", "INSPECTION CLAUSE", or similar. A checked box at the start of such a
    section = true. A crossed-out, waived, or explicitly unchecked section = false. null if absent.
  - financing_contingency: true if contingent on buyer obtaining a loan/mortgage. Section may be labeled
    "FINANCING CONTINGENCY", "LOAN CONTINGENCY", "FINANCING CONDITIONS", "MORTGAGE CONTINGENCY".
    false if the section has an explicitly checked "NO" box, is crossed out, or states the offer is
    NOT contingent on financing / is a cash offer. null if absent entirely.
    IMPORTANT: the presence of financing details (loan type, down payment) does NOT by itself mean
    there is a financing contingency — only mark true if a contingency section is explicitly checked.
  - appraisal_contingency: true if contingent on the property appraising at/above purchase price.
    Section may be labeled "APPRAISAL CONTINGENCY", "APPRAISAL PROVISION", "APPRAISAL CLAUSE".
    false if explicitly waived or unchecked; null if absent.
  - title_contingency: true if contingent on satisfactory title review. Section may be labeled
    "TITLE CONTINGENCY", "TITLE INSURANCE", "TITLE REVIEW CONTINGENCY", "COMMITMENT CONTINGENCY".
    false if explicitly waived; null if absent.
  - insurance_contingency: true if contingent on buyer obtaining homeowner's/hazard insurance. Section
    may be labeled "INSURANCE CONTINGENCY", "HAZARD INSURANCE CONTINGENCY", "HOMEOWNER'S INSURANCE".
    false if explicitly waived; null if absent.
  - sale_of_home_contingency: look for a SALE OF HOME or SALE OF BUYER'S PROPERTY contingency section. true if checked/included; false if explicitly waived; null if absent.
  - additional_provisions: verbatim text of any ADDITIONAL PROVISIONS, special conditions, or addendum titles listed in the contract. null if none.
  - notes: any other noteworthy terms, conditions, or information not captured above. null if none.

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

MISSING_FIELD_RECOVERY_SYSTEM_PROMPT = """You are a real estate extraction specialist doing a second pass over a purchase agreement.

You are given:
- the document pages
- the current extraction result
- a list of comparison-visible fields that are still empty or missing

Your job is to search ONLY for those missing fields.

Rules:
- Return a JSON object with a single top-level key: "recoveries"
- recoveries must map each exact field_path string to either the recovered value or null
- Use the exact field_path strings provided; do not invent new keys
- Use exact document values only
- If a field is still not present, return null
- Do not change fields that are not listed
- For booleans, return true or false only when the document explicitly supports that reading
- For currency, return a number
- For dates, return the exact date string found in the document
"""


EMPTY_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _usage_dict(usage) -> dict:
    """Extract token counts from an OpenAI Usage object."""
    if not usage:
        return dict(EMPTY_USAGE)
    return {
        "prompt_tokens": usage.prompt_tokens or 0,
        "completion_tokens": usage.completion_tokens or 0,
        "total_tokens": usage.total_tokens or 0,
    }


def _combine_usage(*usages: dict | None) -> dict:
    combined = dict(EMPTY_USAGE)
    for usage in usages:
        if not usage:
            continue
        for key in combined:
            combined[key] += int(usage.get(key, 0) or 0)
    return combined


def _extract_balanced_json(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _parse_json_payload(text: str) -> dict:
    raw = (text or "").strip()
    if not raw:
        raise json.JSONDecodeError("Empty response content", raw, 0)

    candidates = [raw]

    fenced = re.findall(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL | re.IGNORECASE)
    candidates.extend(chunk.strip() for chunk in fenced if chunk.strip())

    balanced = _extract_balanced_json(raw)
    if balanced:
        candidates.append(balanced.strip())

    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            raise json.JSONDecodeError("Top-level JSON value must be an object", candidate, 0)
        except json.JSONDecodeError as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise json.JSONDecodeError("Unable to parse JSON response", raw, 0)


def _repair_json_payload(
    malformed_content: str,
    client: OpenAI,
) -> tuple[dict, dict]:
    """Ask the model to repair malformed JSON without inventing new values."""
    repair_prompt = (
        "Repair the following malformed JSON into a valid JSON object. "
        "Return only valid JSON. Preserve keys and values exactly where possible. "
        "If a string is truncated, keep only the visible substring and close it cleanly. "
        "Do not invent missing values.\n\n"
        f"Malformed JSON:\n{malformed_content}"
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You repair malformed JSON. Return only a valid JSON object.",
            },
            {"role": "user", "content": repair_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=8192,
        timeout=120.0,
    )

    repaired_content = response.choices[0].message.content or ""
    return _parse_json_payload(repaired_content), _usage_dict(response.usage)


def _build_recovery_request_text(extracted_data: dict, field_targets: list[dict[str, Any]]) -> str:
    lines = []
    for entry in field_targets:
        lines.append(
            f'- field_path: "{entry["path"]}" | label: "{entry["label"]}" | type: "{entry["type"]}"'
            f' | current_value: "{stringify_field_value(entry.get("value"))}"'
        )
    return (
        "Current extraction result:\n"
        f"{json.dumps(extracted_data, indent=2)}\n\n"
        "Recover only these missing comparison fields:\n"
        f"{chr(10).join(lines)}\n\n"
        "Return only JSON like {\"recoveries\": {\"field.path\": value_or_null}}."
    )


def recover_missing_fields_from_images(
    images_b64: list[str],
    extracted_data: dict,
    field_targets: list[dict[str, Any]],
    client: OpenAI,
) -> tuple[dict[str, Any], dict]:
    """Run a targeted second-pass extraction for missing comparison fields."""
    if not field_targets:
        return {}, dict(EMPTY_USAGE)

    content: list[dict] = []
    for i, img_b64 in enumerate(images_b64):
        content.append({"type": "text", "text": f"--- Page {i + 1} of {len(images_b64)} ---"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"},
        })

    content.append({"type": "text", "text": _build_recovery_request_text(extracted_data, field_targets)})

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": MISSING_FIELD_RECOVERY_SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=4096,
        timeout=120.0,
    )

    usage = _usage_dict(response.usage)
    content = response.choices[0].message.content or ""
    try:
        payload = _parse_json_payload(content)
    except json.JSONDecodeError as exc:
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        log.warning("Malformed recovery JSON from model (finish_reason=%s): %s", finish_reason, exc)
        payload, repair_usage = _repair_json_payload(content, client)
        usage = _combine_usage(usage, repair_usage)
    recoveries = payload.get("recoveries")
    if not isinstance(recoveries, dict):
        return {}, usage
    return recoveries, usage


def extract_from_images(
    images_b64: list[str],
    mode: str,
    client: OpenAI,
) -> tuple[dict, dict]:
    """Send document page images to GPT-4o Vision and get structured extraction.

    Args:
        images_b64: List of base64-encoded PNG strings, one per page.
        mode: 'real_estate' or 'gov'.
        client: OpenAI client instance.

    Returns:
        Tuple of (parsed JSON dict, usage dict with prompt/completion/total tokens).
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
        max_tokens=8192,
        timeout=120.0,
    )

    usage = _usage_dict(response.usage)
    content = response.choices[0].message.content or ""
    try:
        return _parse_json_payload(content), usage
    except json.JSONDecodeError as exc:
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        log.warning("Malformed extraction JSON from model (finish_reason=%s): %s", finish_reason, exc)
        repaired, repair_usage = _repair_json_payload(content, client)
        return repaired, _combine_usage(usage, repair_usage)


def extract_raw_text(images_b64: list[str], client: OpenAI) -> tuple[list[str], dict]:
    """Extract raw text from document images for PII scanning.

    Args:
        images_b64: List of base64-encoded PNG strings.
        client: OpenAI client instance.

    Returns:
        Tuple of (list of text strings per page, aggregated usage dict).
    """
    page_texts: list[str] = []
    total_usage = dict(EMPTY_USAGE)

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
            timeout=120.0,
        )

        page_texts.append(response.choices[0].message.content)
        u = _usage_dict(response.usage)
        for k in total_usage:
            total_usage[k] += u[k]

    return page_texts, total_usage
