"""Financial document extraction and profile field mapping for D.E.S.

Provides:
1. Extraction prompts for 5 financial document types
2. Logic to map extraction results back to user profile fields
"""

import json
import logging
from typing import Optional

from schemas import (
    UserDocumentType,
    FINANCIAL_EXTRACTION_SCHEMAS,
    PreApprovalExtraction,
    BankStatementExtraction,
    PayStubExtraction,
    W2Extraction,
    ProofOfFundsExtraction,
    PreApprovalStatus,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System Prompts for Financial Document Extraction
# ---------------------------------------------------------------------------

FINANCIAL_SYSTEM_PROMPTS: dict[UserDocumentType, str] = {
    UserDocumentType.PRE_APPROVAL_LETTER: """You are a financial document extraction AI. Extract structured data from this pre-approval letter.

Return a JSON object with these fields (use null for missing values):
{
  "lender_name": "Name of the lending institution",
  "lender_address": "Lender's address",
  "lender_nmls": "Lender's NMLS ID number",
  "loan_officer_name": "Name of the loan officer",
  "loan_officer_nmls": "Loan officer's NMLS ID",
  "borrower_name": "Primary borrower's full name",
  "co_borrower_name": "Co-borrower's name if present",
  "approval_amount": 0.00,
  "loan_type": "conventional, FHA, VA, USDA, or jumbo",
  "interest_rate": 0.00,
  "approval_date": "MM/DD/YYYY",
  "expiration_date": "MM/DD/YYYY",
  "conditions": ["list of conditions for final approval"],
  "property_type": "SFR, condo, townhouse, multi-family, etc."
}

Rules:
- Extract values exactly as they appear in the document
- Numeric values should be plain numbers without $ or , symbols
- Dates in MM/DD/YYYY format
- Use null for any field not found in the document
- Do NOT infer or fabricate values""",

    UserDocumentType.BANK_STATEMENT: """You are a financial document extraction AI. Extract structured data from this bank statement.

Return a JSON object with these fields (use null for missing values):
{
  "institution_name": "Bank or financial institution name",
  "account_holder": "Account holder's name",
  "account_type": "checking, savings, or money market",
  "account_number_last4": "Last 4 digits of account number ONLY",
  "statement_period_start": "MM/DD/YYYY",
  "statement_period_end": "MM/DD/YYYY",
  "beginning_balance": 0.00,
  "ending_balance": 0.00,
  "total_deposits": 0.00,
  "total_withdrawals": 0.00,
  "average_daily_balance": 0.00
}

Rules:
- Extract values exactly as they appear
- Only capture the LAST 4 digits of account numbers (PII protection)
- Numeric values as plain numbers without $ or , symbols
- Dates in MM/DD/YYYY format
- Use null for any field not found""",

    UserDocumentType.PAY_STUB: """You are a financial document extraction AI. Extract structured data from this pay stub.

Return a JSON object with these fields (use null for missing values):
{
  "employer_name": "Employer company name",
  "employer_address": "Employer address",
  "employee_name": "Employee full name",
  "employee_id": "Employee ID number",
  "pay_period_start": "MM/DD/YYYY",
  "pay_period_end": "MM/DD/YYYY",
  "pay_date": "MM/DD/YYYY",
  "pay_frequency": "weekly, biweekly, semi-monthly, or monthly",
  "gross_pay": 0.00,
  "net_pay": 0.00,
  "federal_tax": 0.00,
  "state_tax": 0.00,
  "ytd_gross": 0.00,
  "ytd_net": 0.00
}

Rules:
- Extract values exactly as written
- Numeric values as plain numbers
- Dates in MM/DD/YYYY format
- Use null for missing fields
- Do NOT calculate or infer values""",

    UserDocumentType.W2: """You are a financial document extraction AI. Extract structured data from this W-2 form.

Return a JSON object with these fields (use null for missing values):
{
  "tax_year": 2024,
  "employer_name": "Employer name (Box c)",
  "employer_ein": "Employer EIN (Box b)",
  "employer_address": "Employer address (Box c)",
  "employee_name": "Employee name (Box e)",
  "employee_ssn_last4": "Last 4 digits of SSN ONLY (Box a)",
  "wages_tips_compensation": 0.00,
  "federal_tax_withheld": 0.00,
  "social_security_wages": 0.00,
  "social_security_tax": 0.00,
  "medicare_wages": 0.00,
  "medicare_tax": 0.00,
  "state": "State abbreviation (Box 15)",
  "state_wages": 0.00,
  "state_tax_withheld": 0.00
}

Rules:
- Box numbers correspond to standard W-2 form layout
- Only capture LAST 4 digits of SSN (PII protection)
- Numeric values as plain numbers
- Use null for empty boxes
- Tax year is typically shown at top of form""",

    UserDocumentType.PROOF_OF_FUNDS: """You are a financial document extraction AI. Extract structured data from this proof of funds letter.

Return a JSON object with these fields (use null for missing values):
{
  "institution_name": "Bank or financial institution name",
  "account_holder": "Account holder's name",
  "letter_date": "MM/DD/YYYY",
  "account_type": "checking, savings, investment, etc.",
  "available_funds": 0.00,
  "currency": "USD",
  "officer_name": "Bank officer who signed the letter",
  "officer_title": "Bank officer's title",
  "contact_phone": "Contact phone number"
}

Rules:
- Extract values exactly as written
- Numeric values as plain numbers
- Dates in MM/DD/YYYY format
- Use null for missing fields
- Do NOT calculate or infer values""",
}


# ---------------------------------------------------------------------------
# Extraction Function
# ---------------------------------------------------------------------------


async def extract_financial_document(
    images_b64: list[str],
    doc_type: UserDocumentType,
) -> tuple[Optional[dict], dict]:
    """Extract structured data from a financial document using GPT-4o Vision.

    Args:
        images_b64: Base64-encoded page images
        doc_type: Type of financial document

    Returns:
        (extracted_data dict, usage dict with token counts)
    """
    system_prompt = FINANCIAL_SYSTEM_PROMPTS.get(doc_type)
    if not system_prompt:
        return None, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    try:
        from ocr_engine import get_engine
        engine = get_engine()

        # Build the message content with images
        content = []
        for img_b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"},
            })
        content.append({"type": "text", "text": "Extract the structured data from this document according to the schema."})

        # Use the engine's client directly for the financial extraction
        client = engine.client
        response = client.chat.completions.create(
            model=engine.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=4096,
        )

        raw_text = response.choices[0].message.content or "{}"
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
            "confidence": 0.85,
        }

        extracted = json.loads(raw_text)
        return extracted, usage

    except Exception as e:
        log.exception("Financial document extraction failed: %s", e)
        return None, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# Profile Field Mapping: Extraction Results → User Profile
# ---------------------------------------------------------------------------


async def apply_extraction_to_profile(doc) -> bool:
    """Map extraction results from a UserDocument to the owner's UserProfile.

    This is the core "fill it out once" logic: when a financial document
    is extracted, relevant fields are auto-populated on the user's profile.

    Returns True if any profile fields were updated.
    """
    from db import UserProfile, UserDocument

    if not doc.extracted_data:
        return False

    user = await UserProfile.get(doc.user_id)
    if not user:
        log.warning("Cannot apply extraction: user %s not found", doc.user_id)
        return False

    changed = False
    data = doc.extracted_data

    if doc.doc_type == UserDocumentType.PRE_APPROVAL_LETTER:
        changed = _apply_pre_approval(user, data)

    elif doc.doc_type == UserDocumentType.BANK_STATEMENT:
        changed = _apply_bank_statement(user, data)

    elif doc.doc_type == UserDocumentType.PAY_STUB:
        changed = _apply_pay_stub(user, data)

    elif doc.doc_type == UserDocumentType.W2:
        changed = _apply_w2(user, data)

    elif doc.doc_type == UserDocumentType.PROOF_OF_FUNDS:
        changed = _apply_proof_of_funds(user, data)

    if changed:
        await user.save()
        log.info("Updated profile fields for user %s from %s extraction", doc.user_id, doc.doc_type.value)

    return changed


def _ensure_buyer_profile(user) -> bool:
    """Ensure user has buyer role and profile. Returns True if created."""
    from schemas import BuyerProfile, UserType
    if UserType.BUYER not in user.user_types:
        user.user_types.append(UserType.BUYER)
    if user.buyer_profile is None:
        user.buyer_profile = BuyerProfile()
    return True


def _apply_pre_approval(user, data: dict) -> bool:
    """Map pre-approval extraction → buyer profile fields."""
    _ensure_buyer_profile(user)
    bp = user.buyer_profile
    changed = False

    if data.get("approval_amount") and bp.pre_approval_amount is None:
        bp.pre_approval_amount = data["approval_amount"]
        changed = True

    if data.get("lender_name") and bp.pre_approval_lender is None:
        bp.pre_approval_lender = data["lender_name"]
        changed = True

    # Upgrade pre-approval status
    if bp.pre_approval_status in (PreApprovalStatus.NONE, None):
        bp.pre_approval_status = PreApprovalStatus.PRE_APPROVED
        changed = True

    # Set name from borrower if user name is empty
    if data.get("borrower_name") and not user.name:
        user.name = data["borrower_name"]
        changed = True

    return changed


def _apply_bank_statement(user, data: dict) -> bool:
    """Map bank statement extraction → buyer profile fields."""
    _ensure_buyer_profile(user)
    changed = False

    if data.get("account_holder") and not user.name:
        user.name = data["account_holder"]
        changed = True

    return changed


def _apply_pay_stub(user, data: dict) -> bool:
    """Map pay stub extraction → buyer profile fields."""
    _ensure_buyer_profile(user)
    bp = user.buyer_profile
    changed = False

    if data.get("employer_name") and bp.employer_name is None:
        bp.employer_name = data["employer_name"]
        changed = True

    if data.get("employee_name") and not user.name:
        user.name = data["employee_name"]
        changed = True

    # Infer employment status
    if bp.employment_status is None:
        bp.employment_status = "employed"
        changed = True

    # Calculate annual income from pay stub if not set
    if bp.annual_income is None and data.get("ytd_gross"):
        bp.annual_income = data["ytd_gross"]
        changed = True
    elif bp.annual_income is None and data.get("gross_pay") and data.get("pay_frequency"):
        multipliers = {"weekly": 52, "biweekly": 26, "semi-monthly": 24, "monthly": 12}
        mult = multipliers.get(data["pay_frequency"], 12)
        bp.annual_income = round(data["gross_pay"] * mult, 2)
        changed = True

    return changed


def _apply_w2(user, data: dict) -> bool:
    """Map W-2 extraction → buyer profile fields."""
    _ensure_buyer_profile(user)
    bp = user.buyer_profile
    changed = False

    if data.get("employer_name") and bp.employer_name is None:
        bp.employer_name = data["employer_name"]
        changed = True

    if data.get("employee_name") and not user.name:
        user.name = data["employee_name"]
        changed = True

    if data.get("wages_tips_compensation") and bp.annual_income is None:
        bp.annual_income = data["wages_tips_compensation"]
        changed = True

    if bp.employment_status is None:
        bp.employment_status = "employed"
        changed = True

    return changed


def _apply_proof_of_funds(user, data: dict) -> bool:
    """Map proof of funds extraction → buyer profile fields."""
    _ensure_buyer_profile(user)
    changed = False

    if data.get("account_holder") and not user.name:
        user.name = data["account_holder"]
        changed = True

    return changed
