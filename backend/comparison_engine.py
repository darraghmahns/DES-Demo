"""Multi-offer comparison engine for D.E.S.

Compares two document extractions field-by-field and produces a structured
diff with significance classification. Designed for Julie's workflow:
comparing an offer with a counteroffer, or an inspection notice with an
inspection response.

Usage:
    result = compare_extractions(extraction_a, extraction_b)
    print(result.summary)
    for delta in result.deltas:
        print(f"  {delta.field_label}: {delta.original_value} → {delta.new_value}")
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from schemas import (
    ComparisonFieldDelta,
    ComparisonResult,
    FieldSignificance,
)


# ---------------------------------------------------------------------------
# Significance classification
# ---------------------------------------------------------------------------

# Fields that directly affect the deal price or timeline
CRITICAL_FIELDS = {
    "financials.purchase_price",
    "financials.earnest_money_amount",
    "contract_dates.closing_date",
}

# Fields that are important but not deal-breaking
MAJOR_FIELDS = {
    "financials.sale_commission_rate",
    "financials.sale_commission_amount",
    "financials.listing_commission_rate",
    "financials.listing_commission_amount",
    "contract_dates.offer_expiration_date",
    "contract_dates.inspection_date",
    "contract_dates.appraisal_date",
    "contract_dates.loan_commitment_date",
    "financials.down_payment",
    "financials.loan_amount",
    "transaction_type",
    "transaction_status",
}

# Human-readable labels for common field paths
FIELD_LABELS: dict[str, str] = {
    "financials.purchase_price": "Purchase Price",
    "financials.earnest_money_amount": "Earnest Money",
    "financials.sale_commission_rate": "Sale Commission Rate",
    "financials.sale_commission_amount": "Sale Commission Amount",
    "financials.listing_commission_rate": "Listing Commission Rate",
    "financials.listing_commission_amount": "Listing Commission Amount",
    "financials.down_payment": "Down Payment",
    "financials.loan_amount": "Loan Amount",
    "contract_dates.closing_date": "Closing Date",
    "contract_dates.offer_date": "Offer Date",
    "contract_dates.offer_expiration_date": "Offer Expiration",
    "contract_dates.inspection_date": "Inspection Deadline",
    "contract_dates.appraisal_date": "Appraisal Date",
    "contract_dates.loan_commitment_date": "Loan Commitment Date",
    "property_address.street_number": "Street Number",
    "property_address.street_name": "Street Name",
    "property_address.city": "City",
    "property_address.state_or_province": "State",
    "property_address.postal_code": "ZIP Code",
    "property_address.county": "County",
    "transaction_type": "Transaction Type",
    "transaction_status": "Transaction Status",
    "loop_name": "Loop Name",
}


def _classify_significance(field_path: str) -> FieldSignificance:
    """Classify a field change as critical, major, or minor."""
    if field_path in CRITICAL_FIELDS:
        return FieldSignificance.CRITICAL
    if field_path in MAJOR_FIELDS:
        return FieldSignificance.MAJOR
    # Participant changes are major
    if field_path.startswith("participants"):
        return FieldSignificance.MAJOR
    return FieldSignificance.MINOR


def _get_label(field_path: str) -> str:
    """Get a human-readable label for a field path."""
    if field_path in FIELD_LABELS:
        return FIELD_LABELS[field_path]
    # Auto-generate from path: "financials.down_payment" → "Down Payment"
    parts = field_path.split(".")
    last = parts[-1]
    return last.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Flattening
# ---------------------------------------------------------------------------

def flatten_extraction(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Flatten a nested extraction dict into dot-separated field paths.

    Args:
        data: Nested dict (e.g., DotloopLoopDetails as dict).
        prefix: Path prefix for recursion.

    Returns:
        Flat dict: {"financials.purchase_price": "612500", ...}
        All values are stringified for easy comparison.
    """
    flat: dict[str, str] = {}

    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key

        if isinstance(value, dict):
            flat.update(flatten_extraction(value, path))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    flat.update(flatten_extraction(item, f"{path}[{i}]"))
                elif item is not None:
                    flat[f"{path}[{i}]"] = str(item)
        elif value is not None:
            flat[path] = str(value)

    return flat


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------

# Fields to skip in comparison (metadata, not meaningful for offer comparison)
SKIP_FIELDS = {
    "mode",
    "source_file",
    "extraction_timestamp",
    "model_used",
    "pages_processed",
    "overall_confidence",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd",
    "document_type",
}


def _should_skip(field_path: str) -> bool:
    """Check if a field should be excluded from comparison."""
    # Skip top-level metadata fields
    if field_path in SKIP_FIELDS:
        return True
    # Skip citation/verification data
    if field_path.startswith("citations"):
        return True
    if field_path.startswith("pii_report"):
        return True
    if field_path.startswith("compliance_report"):
        return True
    if field_path.startswith("dotloop_api_payload"):
        return True
    if field_path.startswith("docusign_api_payload"):
        return True
    return False


def compare_extractions(
    from_data: dict[str, Any],
    to_data: dict[str, Any],
    from_extraction_id: str = "",
    to_extraction_id: str = "",
    from_source: Optional[str] = None,
    to_source: Optional[str] = None,
) -> ComparisonResult:
    """Compare two extraction result dicts and produce a structured diff.

    Args:
        from_data: The "original" document extraction (e.g., the offer).
        to_data: The "new" document extraction (e.g., the counteroffer).
        from_extraction_id: DB reference for the original extraction.
        to_extraction_id: DB reference for the new extraction.
        from_source: Display label for original (e.g., "Offer - Loop 123").
        to_source: Display label for new (e.g., "Counteroffer - Loop 456").

    Returns:
        ComparisonResult with field-level deltas sorted by significance.
    """
    # If extractions contain nested dotloop_data/foia_data, use that
    from_flat = flatten_extraction(
        from_data.get("dotloop_data") or from_data.get("foia_data") or from_data
    )
    to_flat = flatten_extraction(
        to_data.get("dotloop_data") or to_data.get("foia_data") or to_data
    )

    all_keys = set(from_flat.keys()) | set(to_flat.keys())
    deltas: list[ComparisonFieldDelta] = []

    for key in sorted(all_keys):
        if _should_skip(key):
            continue

        from_val = from_flat.get(key)
        to_val = to_flat.get(key)

        if from_val == to_val:
            continue

        if from_val is None:
            change_type = "added"
        elif to_val is None:
            change_type = "removed"
        else:
            change_type = "modified"

        deltas.append(ComparisonFieldDelta(
            field_path=key,
            field_label=_get_label(key),
            original_value=from_val,
            new_value=to_val,
            change_type=change_type,
            significance=_classify_significance(key),
        ))

    # Sort: critical first, then major, then minor
    significance_order = {
        FieldSignificance.CRITICAL: 0,
        FieldSignificance.MAJOR: 1,
        FieldSignificance.MINOR: 2,
    }
    deltas.sort(key=lambda d: significance_order.get(d.significance, 3))

    # Counts
    critical = sum(1 for d in deltas if d.significance == FieldSignificance.CRITICAL)
    major = sum(1 for d in deltas if d.significance == FieldSignificance.MAJOR)
    minor = sum(1 for d in deltas if d.significance == FieldSignificance.MINOR)

    # Generate summary
    summary_parts: list[str] = []
    critical_deltas = [d for d in deltas if d.significance == FieldSignificance.CRITICAL]
    if critical_deltas:
        changes = ", ".join(
            f"{d.field_label}: {d.original_value} → {d.new_value}"
            for d in critical_deltas[:3]
        )
        summary_parts.append(f"{critical} critical change{'s' if critical > 1 else ''}: {changes}")
    if major:
        summary_parts.append(f"{major} major change{'s' if major > 1 else ''}")
    if minor:
        summary_parts.append(f"{minor} minor change{'s' if minor > 1 else ''}")
    if not summary_parts:
        summary_parts.append("No differences found")

    return ComparisonResult(
        comparison_id=str(uuid.uuid4()),
        from_extraction_id=from_extraction_id,
        to_extraction_id=to_extraction_id,
        from_source=from_source,
        to_source=to_source,
        deltas=deltas,
        summary=". ".join(summary_parts),
        critical_count=critical,
        major_count=major,
        minor_count=minor,
        total_changes=len(deltas),
        comparison_timestamp=datetime.now(timezone.utc).isoformat(),
    )
