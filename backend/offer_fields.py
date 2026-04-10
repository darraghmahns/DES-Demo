"""Shared offer-comparison field registry and field/citation helpers."""

from __future__ import annotations

import copy
import re
from typing import Any

from schemas import VerificationCitation

# Single source of truth for comparison-visible offer fields.
FIELD_REGISTRY = [
    # Parties
    {"path": "participants.buyer.full_name",          "key": "buyer_name",          "label": "Buyer's Name",       "type": "string", "group": "Parties"},
    {"path": "participants.buyer.email",              "key": "buyer_email",         "label": "Buyer Email",        "type": "string", "group": "Parties"},
    {"path": "participants.buyer.phone",              "key": "buyer_phone",         "label": "Buyer Phone",        "type": "string", "group": "Parties"},
    {"path": "participants.seller.full_name",         "key": "seller_name",         "label": "Seller Name",        "type": "string", "group": "Parties"},
    {"path": "participants.seller.email",             "key": "seller_email",        "label": "Seller Email",       "type": "string", "group": "Parties"},
    {"path": "participants.buying_agent.full_name",   "key": "agent_name",          "label": "Agent Name",         "type": "string", "group": "Parties"},
    {"path": "participants.buying_agent.email",       "key": "agent_email",         "label": "Agent Email",        "type": "string", "group": "Parties"},
    {"path": "participants.buying_agent.phone",       "key": "agent_phone",         "label": "Agent Phone",        "type": "string", "group": "Parties"},
    {"path": "participants.buying_agent.company_name","key": "agent_company",       "label": "Agent Company",      "type": "string", "group": "Parties"},
    {"path": "participants.listing_agent.full_name",  "key": "listing_agent_name",  "label": "Listing Agent",      "type": "string", "group": "Parties"},
    {"path": "participants.listing_agent.email",      "key": "listing_agent_email", "label": "Listing Agent Email","type": "string", "group": "Parties"},
    # Financials
    {"path": "financials.purchase_price",        "key": "purchase_price",        "label": "Purchase Price",             "type": "currency", "group": "Financials"},
    {"path": "financials.earnest_money_amount",  "key": "earnest_money_amount",  "label": "Earnest Money",              "type": "currency", "group": "Financials"},
    {"path": "financials.earnest_money_held_by", "key": "earnest_money_held_by", "label": "Earnest Money Held By",      "type": "string",   "group": "Financials"},
    {"path": "financials.down_payment_amount",   "key": "down_payment_amount",   "label": "Down Payment ($)",           "type": "currency", "group": "Financials"},
    {"path": "financials.down_payment_percentage","key": "down_payment_percentage", "label": "Down Payment (%)",        "type": "string",   "group": "Financials"},
    {"path": "financials.financing_type",        "key": "financing_type",        "label": "Financing Terms / Loan Type","type": "string",   "group": "Financials"},
    {"path": "financials.sale_commission_rate",  "key": "sale_commission_rate",  "label": "Commission Rate",            "type": "string",   "group": "Financials"},
    {"path": "financials.sale_commission_total", "key": "sale_commission_total", "label": "Commission Total",           "type": "currency", "group": "Financials"},
    {"path": "financials.closing_fee_paid_by",   "key": "closing_fee_paid_by",   "label": "Title Company Closing Fee",  "type": "string",   "group": "Financials"},
    {"path": "financials.fincen_fee_paid_by",    "key": "fincen_fee_paid_by",    "label": "FinCEN Reports Fee (503)",   "type": "string",   "group": "Financials"},
    # Property
    {"path": "property_address.mls_number",      "key": "mls_number",    "label": "MLS Number",    "type": "string", "group": "Property"},
    {"path": "property_address.county",          "key": "county",        "label": "County",        "type": "string", "group": "Property"},
    {"path": "property_address.parcel_tax_id",   "key": "parcel_tax_id", "label": "Parcel/Tax ID", "type": "string", "group": "Property"},
    # Key Dates
    {"path": "contract_dates.offer_date",              "key": "offer_date",              "label": "Offer Date",           "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.offer_expiration_date",   "key": "offer_expiration_date",   "label": "Offer Expiration",     "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.contract_agreement_date", "key": "contract_agreement_date", "label": "Contract Date",        "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.closing_date",            "key": "closing_date",            "label": "Closing Date",         "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.possession_date",         "key": "possession_date",         "label": "Possession",           "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.opd_delivery_date",       "key": "opd_delivery_date",       "label": "Delivery of OPD",      "type": "date", "group": "Key Dates"},
    {"path": "contract_dates.seller_response_time",    "key": "seller_response_time",    "label": "Seller Response Time", "type": "date", "group": "Key Dates"},
    # Contingency Deadlines
    {"path": "contract_dates.loan_application_deadline",       "key": "loan_application_deadline",       "label": "Loan Application Deadline",       "type": "date", "group": "Contingency Deadlines"},
    {"path": "contract_dates.inspection_date",                 "key": "inspection_date",                 "label": "Inspection Deadline",             "type": "date", "group": "Contingency Deadlines"},
    {"path": "contract_dates.inspection_release_date",         "key": "inspection_release_date",         "label": "Inspection Release Date",         "type": "date", "group": "Contingency Deadlines"},
    {"path": "contract_dates.inspection_release_time",         "key": "inspection_release_time",         "label": "Inspection Release Time",         "type": "string", "group": "Contingency Deadlines"},
    {"path": "contract_dates.inspection_negotiation_deadline", "key": "inspection_negotiation_deadline", "label": "Inspection Negotiation Deadline", "type": "date", "group": "Contingency Deadlines"},
    {"path": "contract_dates.insurance_contingency_date",      "key": "insurance_contingency_date",      "label": "Insurance Contingency Deadline",  "type": "date", "group": "Contingency Deadlines"},
    {"path": "contract_dates.title_contingency_date",          "key": "title_contingency_date",          "label": "Title Review Deadline",           "type": "date", "group": "Contingency Deadlines"},
    # Contingencies
    {"path": "terms.escalation_clause",         "key": "escalation_clause",         "label": "Escalation Clause",         "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.opd_delivered",             "key": "opd_delivered",             "label": "OPD Contingency",           "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.inspection_contingency",    "key": "inspection_contingency",    "label": "Inspection Contingency",    "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.inspection_release_clause_text","key": "inspection_release_clause_text","label": "Inspection Release Clause", "type": "text",     "group": "Contingencies"},
    {"path": "terms.financing_contingency",     "key": "financing_contingency",     "label": "Financing Contingency",     "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.appraisal_contingency",     "key": "appraisal_contingency",     "label": "Appraisal Contingency",     "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.appraisal_contingency_amount","key": "appraisal_contingency_amount","label": "Appraisal Amount",      "type": "currency", "group": "Contingencies"},
    {"path": "terms.title_contingency",         "key": "title_contingency",         "label": "Title Contingency",         "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.insurance_contingency",     "key": "insurance_contingency",     "label": "Insurance Contingency",     "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.sale_of_home_contingency",  "key": "sale_of_home_contingency",  "label": "Sale of House Contingency", "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.home_warranty",             "key": "home_warranty",             "label": "Home Warranty",             "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.hoa_approval_contingency",  "key": "hoa_approval_contingency",  "label": "HOA Contingency",           "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.survey_contingency",        "key": "survey_contingency",        "label": "Survey Contingency",        "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.as_is",                     "key": "as_is",                     "label": "As-Is",                     "type": "boolean",  "group": "Contingencies"},
    {"path": "terms.buyer_physically_visited_property","key": "buyer_physically_visited_property","label": "Buyer Physically Visited Property", "type": "boolean", "group": "Contingencies"},
    # Personal Property
    {"path": "terms.inclusions",                "key": "inclusions",                "label": "Personal Property Included",        "type": "text", "group": "Personal Property"},
    {"path": "terms.exclusions",                "key": "exclusions",                "label": "Excluded Fixtures",                 "type": "text", "group": "Personal Property"},
    {"path": "terms.leased_items",              "key": "leased_items",              "label": "Leased / Rented Personal Property", "type": "text", "group": "Personal Property"},
    # Additional
    {"path": "terms.detection_devices",         "key": "detection_devices",         "label": "Detection Devices",    "type": "text", "group": "Additional"},
    {"path": "terms.additional_provisions",     "key": "additional_provisions",     "label": "Additional Provisions","type": "text", "group": "Additional"},
    {"path": "terms.notes",                     "key": "notes",                     "label": "Other / Notes",       "type": "text", "group": "Additional"},
]

FIELD_DEFINITIONS = [{k: v for k, v in entry.items() if k != "path"} for entry in FIELD_REGISTRY]
FIELD_PATH_TO_ENTRY = {entry["path"]: entry for entry in FIELD_REGISTRY}
FIELD_KEY_TO_ENTRY = {entry["key"]: entry for entry in FIELD_REGISTRY}
FIELD_PATH_TO_KEY = {entry["path"]: entry["key"] for entry in FIELD_REGISTRY}
FIELD_KEY_TO_PATH = {entry["key"]: entry["path"] for entry in FIELD_REGISTRY}

_FEE_PAYER_PATHS = {
    "financials.closing_fee_paid_by",
    "financials.fincen_fee_paid_by",
}
_FEE_PAYER_NORMALIZATION = {
    "seller": "Seller",
    "buyer": "Buyer",
    "equally shared": "Equally Shared",
    "equally-shared": "Equally Shared",
    "shared equally": "Equally Shared",
    "split equally": "Equally Shared",
    "split": "Equally Shared",
}


def _normalize_citation_alias(value: str) -> str:
    normalized = value.strip().lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return re.sub(r"_+", "_", normalized).strip("_")


def _build_citation_field_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for entry in FIELD_REGISTRY:
        path = entry["path"]
        for alias in {path, entry["key"], entry["label"], path.replace(".", "_")}:
            normalized = _normalize_citation_alias(alias)
            if normalized:
                aliases[normalized] = path
    return aliases


FIELD_NAME_ALIASES = _build_citation_field_aliases()


def flatten_extracted(extracted_data: dict) -> dict:
    """Flatten extracted_data's nested structure to dot-notation key → value."""
    flat: dict = {}
    for section, values in extracted_data.items():
        if section == "participants":
            for participant in (values or []):
                role = (participant.get("role") or "UNKNOWN").lower()
                for key, value in participant.items():
                    if key != "role":
                        flat[f"participants.{role}.{key}"] = value
        elif isinstance(values, dict):
            for key, value in values.items():
                flat[f"{section}.{key}"] = value
        else:
            flat[section] = values
    return flat


def build_offer_fields(extracted_data: dict) -> tuple[dict, dict]:
    flat = flatten_extracted(extracted_data)
    registered_paths = {entry["path"] for entry in FIELD_REGISTRY}
    fields = {entry["key"]: flat.get(entry["path"]) for entry in FIELD_REGISTRY}
    raw_extras = {key: value for key, value in flat.items() if key not in registered_paths and value is not None}
    return fields, raw_extras


def canonicalize_citation_field_name(field_name: str | None) -> str | None:
    if field_name is None:
        return None
    raw = str(field_name).strip()
    if not raw:
        return None
    if raw in FIELD_PATH_TO_KEY:
        return raw
    return FIELD_NAME_ALIASES.get(_normalize_citation_alias(raw), raw)


def _field_missing(entry: dict, value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    # Purchase price is the one comparison field whose schema cannot be null.
    if entry["path"] == "financials.purchase_price" and value in (0, 0.0, "0", "0.0", "$0"):
        return True
    return False


def get_offer_field_targets(extracted_data: dict) -> list[dict]:
    flat = flatten_extracted(extracted_data)
    return [{**entry, "value": flat.get(entry["path"])} for entry in FIELD_REGISTRY]


def get_missing_offer_field_targets(extracted_data: dict) -> list[dict]:
    return [entry for entry in get_offer_field_targets(extracted_data) if _field_missing(entry, entry["value"])]


def _coerce_offer_field_value(entry: dict, value: Any) -> Any:
    if value is None:
        return None

    field_type = entry["type"]
    if field_type == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if entry["path"] == "terms.buyer_physically_visited_property":
                if normalized in {
                    "has physically visited the property",
                    "physically visited",
                    "visited",
                    "yes, visited",
                }:
                    return True
                if normalized in {
                    "has not physically visited the property",
                    "has not physically visited",
                    "not physically visited",
                    "did not visit",
                    "no, not visited",
                }:
                    return False
            if normalized in {"true", "yes", "y", "checked", "included"}:
                return True
            if normalized in {"false", "no", "n", "unchecked", "waived", "not delivered"}:
                return False
        return None

    if field_type == "currency":
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.replace("$", "").replace(",", "").strip()
            if not normalized:
                return None
            try:
                return float(normalized)
            except ValueError:
                return None
        return None

    if isinstance(value, str):
        stripped = value.strip()
        if entry["path"] in _FEE_PAYER_PATHS:
            normalized = _FEE_PAYER_NORMALIZATION.get(stripped.lower())
            return normalized or (stripped or None)
        return stripped or None

    return str(value)


def _set_nested_path(target: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cursor = target
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    cursor[parts[-1]] = value


def _set_participant_path(target: dict, path: str, value: Any) -> None:
    _, role, field_name = path.split(".", 2)
    participants = target.setdefault("participants", [])
    if not isinstance(participants, list):
        participants = []
        target["participants"] = participants

    role_upper = role.upper()
    participant = next((item for item in participants if (item.get("role") or "").upper() == role_upper), None)
    if participant is None:
        participant = {
            "role": role_upper,
            "full_name": "",
            "email": None,
            "phone": None,
            "company_name": None,
        }
        participants.append(participant)
    participant[field_name] = value


def merge_recovered_offer_fields(extracted_data: dict, recovered_values: dict[str, Any]) -> tuple[dict, list[str]]:
    """Apply recovered comparison values without overwriting existing extracted values."""
    merged = copy.deepcopy(extracted_data)
    applied_paths: list[str] = []
    current_targets = {entry["path"]: entry for entry in get_offer_field_targets(extracted_data)}

    for path, raw_value in (recovered_values or {}).items():
        entry = current_targets.get(path)
        if not entry:
            continue
        if not _field_missing(entry, entry["value"]):
            continue
        value = _coerce_offer_field_value(entry, raw_value)
        if value is None and entry["type"] != "boolean":
            continue

        if path.startswith("participants."):
            _set_participant_path(merged, path, value)
        else:
            _set_nested_path(merged, path, value)
        applied_paths.append(path)

    return merged, applied_paths


def stringify_field_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def ensure_required_citations(
    citations: list[VerificationCitation],
    required_targets: list[dict],
) -> list[VerificationCitation]:
    required_paths = {entry["path"]: entry for entry in required_targets}
    by_field: dict[str, list[VerificationCitation]] = {}
    for citation in citations:
        canonical = canonicalize_citation_field_name(citation.field_name) or citation.field_name
        by_field.setdefault(canonical, []).append(citation)

    merged = list(citations)
    for path, entry in required_paths.items():
        if path in by_field:
            continue
        merged.append(
            VerificationCitation(
                field_name=path,
                extracted_value=stringify_field_value(entry["value"]),
                page_number=0,
                line_or_region="Not found",
                surrounding_text="NOT FOUND",
                confidence=0.0,
            )
        )
    return merged


def _citation_is_not_found(citation: dict | VerificationCitation) -> bool:
    surrounding_text = citation.surrounding_text if isinstance(citation, VerificationCitation) else citation.get("surrounding_text")
    confidence = citation.confidence if isinstance(citation, VerificationCitation) else citation.get("confidence", 0)
    return str(surrounding_text or "").strip().upper() == "NOT FOUND" or float(confidence or 0) <= 0.0


def build_offer_field_citations(
    citations: list[dict] | list[VerificationCitation],
    overrides: dict | None = None,
) -> tuple[dict[str, list[dict]], dict[str, dict[str, Any]], list[str]]:
    grouped: dict[str, list[dict]] = {}
    overrides = overrides or {}

    for raw in citations or []:
        citation = raw.model_dump(mode="json") if isinstance(raw, VerificationCitation) else dict(raw)
        canonical_field_name = canonicalize_citation_field_name(citation.get("field_name"))
        if canonical_field_name:
            citation["field_name"] = canonical_field_name
        key = FIELD_PATH_TO_KEY.get(canonical_field_name)
        if not key:
            continue
        grouped.setdefault(key, []).append(citation)

    for key, citation_list in grouped.items():
        citation_list.sort(key=lambda item: float(item.get("confidence", 0) or 0), reverse=True)
        if any(not _citation_is_not_found(item) for item in citation_list):
            grouped[key] = [item for item in citation_list if not _citation_is_not_found(item)]

    overridden_fields = sorted(key for key in overrides.keys() if key in FIELD_KEY_TO_ENTRY)
    meta: dict[str, dict[str, Any]] = {}
    for entry in FIELD_REGISTRY:
        key = entry["key"]
        citation_list = grouped.get(key, [])
        if citation_list:
            state = "not_found" if all(_citation_is_not_found(item) for item in citation_list) else "supported"
        else:
            state = "not_captured"
        meta[key] = {
            "state": state,
            "stale": key in overridden_fields,
        }

    return grouped, meta, overridden_fields
