"""Jurisdiction-Aware Compliance Engine (JACE) v1.

Resolves extracted property addresses to political jurisdictions and looks up
required documents, inspections, disclosures, and fees from a seeded rules
database.  Demonstrates the "Last Mile" municipal compliance problem:

  - LA City requires a 9A Report; unincorporated LA County does not.
  - Missoula City requires "Connect on Sale" sewer verification; unincorporated
    Missoula County does not.
  - Helena, MT has Water Rights Form 608 + septic/well inspections specific to
    Lewis and Clark County.

v1 scope: no geocoding API, no AI Scout — manually seeded rules for demo
markets (Helena MT, Missoula MT, LA City, LA County) with a city → county →
state fallback cascade.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from schemas import (
    ComplianceOverallStatus,
    ComplianceReport,
    ComplianceRequirement,
    RequirementCategory,
    RequirementStatus,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Jurisdiction resolver
# ---------------------------------------------------------------------------

def resolve_jurisdiction(
    state: str,
    county: Optional[str] = None,
    city: Optional[str] = None,
) -> tuple[str, str, str]:
    """Normalize address fields and build a jurisdiction lookup key.

    Returns:
        (key, display_name, jurisdiction_type)
        - key: "ST:County Name:City Name" (empty segments for missing fields)
        - display_name: human-readable like "Helena, Lewis And Clark County, MT"
        - jurisdiction_type: "city", "county", or "state"
    """
    s = (state or "").strip().upper()
    co = (county or "").strip().title()
    ci = (city or "").strip().title()

    key = f"{s}:{co}:{ci}"

    if ci:
        display = f"{ci}, {co + ' County, ' if co else ''}{s}"
        jtype = "city"
    elif co:
        display = f"{co} County, {s} (unincorporated)"
        jtype = "county"
    else:
        display = f"{s} (statewide)"
        jtype = "state"

    return key, display, jtype


# ---------------------------------------------------------------------------
# Seed rules database
# ---------------------------------------------------------------------------
# Keyed by jurisdiction key (state:county:city).  Each value is a list of
# requirement dicts that get validated into ComplianceRequirement models.

SEED_RULES: dict[str, list[dict[str, Any]]] = {
    # -----------------------------------------------------------------------
    # Montana — Helena (Lewis and Clark County)
    # -----------------------------------------------------------------------
    "MT:Lewis And Clark:Helena": [
        {
            "name": "Water Rights Form 608",
            "code": "DNRC-608",
            "category": RequirementCategory.FORM,
            "description": "Montana DNRC Form 608 — Ownership Update for water rights "
                           "attached to the property. Required whenever water rights "
                           "are conveyed with real property.",
            "authority": "Montana DNRC",
            "fee": "$100 (first right) + $20 each additional",
            "url": "https://dnrc.mt.gov/water-rights/",
            "status": RequirementStatus.REQUIRED,
            "notes": "Submit to local Water Resources Regional Office with copy of "
                     "recorded deed. Must be filed within 60 days of closing.",
        },
        {
            "name": "Realty Transfer Certificate",
            "code": "RTC",
            "category": RequirementCategory.CERTIFICATE,
            "description": "Montana Realty Transfer Certificate filed with the county "
                           "clerk and recorder at closing. Required for all real "
                           "property transfers. Includes water rights disclosure "
                           "(Boxes A-D).",
            "authority": "Montana DOR",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Seller Property Disclosure",
            "code": "SPD",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Montana Seller Property Condition Disclosure Statement. "
                           "Seller must disclose known material defects including water "
                           "service, wastewater systems, structural issues, and "
                           "environmental hazards.",
            "authority": "Montana Legislature (MCA 70-9-313)",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Septic System Inspection",
            "code": None,
            "category": RequirementCategory.INSPECTION,
            "description": "Inspection of private septic system if property is not "
                           "connected to municipal sewer. Lewis and Clark County has "
                           "more stringent regulations than state standards based on "
                           "soil type and depth to groundwater.",
            "authority": "Lewis and Clark County Health Dept",
            "fee": "$150-$300",
            "status": RequirementStatus.LIKELY_REQUIRED,
            "notes": "Only required if property has a private septic system. County "
                     "may require pressure dosed or level 2 treatment systems.",
        },
        {
            "name": "Well Water Quality Test",
            "code": None,
            "category": RequirementCategory.INSPECTION,
            "description": "Water quality test for private wells — bacteria, nitrates, "
                           "and recommended broader sampling (pH, dissolved solids, "
                           "alkalinity) every 5 years.",
            "authority": "Montana DEQ",
            "fee": "$50-$150",
            "status": RequirementStatus.LIKELY_REQUIRED,
            "notes": "Required by most lenders; FHA/VA loans always require this.",
        },
        {
            "name": "Radon Disclosure",
            "code": "MCA 75-3-606",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Montana Radon Control Act disclosure. Seller must disclose "
                           "whether property has been tested for radon gas or radon "
                           "progeny, and attach test results and evidence of any "
                           "mitigation or treatment.",
            "authority": "Montana DEQ — Radon Control Program",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Lead-Based Paint Disclosure",
            "code": "42 USC §4852d",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Federal requirement for homes built before 1978. Seller "
                           "must disclose known lead-based paint hazards and provide "
                           "EPA pamphlet. Buyer has 10-day inspection period.",
            "authority": "EPA / HUD",
            "status": RequirementStatus.LIKELY_REQUIRED,
            "notes": "Only applies to homes built before 1978.",
        },
    ],

    # -----------------------------------------------------------------------
    # Montana — Missoula (Missoula County)
    # -----------------------------------------------------------------------
    "MT:Missoula:Missoula": [
        {
            "name": "Connect on Sale — Sewer Connection",
            "code": "MMC 13.04.020",
            "category": RequirementCategory.CERTIFICATE,
            "description": "City of Missoula 'Connect on Sale' ordinance. It is "
                           "unlawful to sell, transfer, or convey any real property "
                           "containing plumbed buildings with available public sewer "
                           "until connected. 'Sewer available' = within 200 feet of "
                           "public sewer system.",
            "authority": "City of Missoula Public Works",
            "url": "https://www.ci.missoula.mt.us/837/Connect-on-Sale",
            "status": RequirementStatus.REQUIRED,
            "notes": "Unique to Missoula City — not required outside city limits. "
                     "City Engineer may grant a one-time 6-month delay with evidence "
                     "of negotiated financial holdback.",
        },
        {
            "name": "Sewer Line TV Inspection",
            "code": None,
            "category": RequirementCategory.INSPECTION,
            "description": "TV inspection of sewer lateral by licensed 3rd-party "
                           "contractor to verify connection to public sewer. Both "
                           "property owner and contractor must sign the inspection "
                           "form. Contractor applies for no-fee sewer permit via "
                           "city citizen portal.",
            "authority": "City of Missoula Public Works",
            "status": RequirementStatus.REQUIRED,
            "notes": "Required when connection cannot be verified with a ditch card. "
                     "Recommended to hire a contractor who can also perform root "
                     "cutting or maintenance during inspection.",
        },
        {
            "name": "Water Rights Form 608",
            "code": "DNRC-608",
            "category": RequirementCategory.FORM,
            "description": "Montana DNRC Form 608 — Ownership Update for water rights "
                           "attached to the property. Required whenever water rights "
                           "are conveyed with real property.",
            "authority": "Montana DNRC",
            "fee": "$100 (first right) + $20 each additional",
            "url": "https://dnrc.mt.gov/water-rights/",
            "status": RequirementStatus.REQUIRED,
            "notes": "Submit to local Water Resources Regional Office with copy of "
                     "recorded deed.",
        },
        {
            "name": "Realty Transfer Certificate",
            "code": "RTC",
            "category": RequirementCategory.CERTIFICATE,
            "description": "Montana Realty Transfer Certificate filed with the county "
                           "clerk and recorder at closing. Includes water rights "
                           "disclosure (Boxes A-D).",
            "authority": "Montana DOR",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Seller Property Disclosure",
            "code": "SPD",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Montana Seller Property Condition Disclosure Statement. "
                           "Seller must disclose known material defects including water "
                           "service, wastewater systems, structural issues, and "
                           "environmental hazards.",
            "authority": "Montana Legislature (MCA 70-9-313)",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Radon Disclosure",
            "code": "MCA 75-3-606",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Montana Radon Control Act disclosure. Seller must disclose "
                           "whether property has been tested for radon gas or radon "
                           "progeny, and attach test results and evidence of any "
                           "mitigation or treatment.",
            "authority": "Montana DEQ — Radon Control Program",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Lead-Based Paint Disclosure",
            "code": "42 USC §4852d",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Federal requirement for homes built before 1978. Seller "
                           "must disclose known lead-based paint hazards and provide "
                           "EPA pamphlet. Buyer has 10-day inspection period.",
            "authority": "EPA / HUD",
            "status": RequirementStatus.LIKELY_REQUIRED,
            "notes": "Only applies to homes built before 1978.",
        },
    ],

    # Montana — unincorporated Missoula County (NO Connect on Sale / TV Inspection)
    "MT:Missoula:": [
        {
            "name": "Water Rights Form 608",
            "code": "DNRC-608",
            "category": RequirementCategory.FORM,
            "description": "Montana DNRC Form 608 — Ownership Update for water rights "
                           "attached to the property.",
            "authority": "Montana DNRC",
            "fee": "$100 (first right) + $20 each additional",
            "url": "https://dnrc.mt.gov/water-rights/",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Realty Transfer Certificate",
            "code": "RTC",
            "category": RequirementCategory.CERTIFICATE,
            "description": "Montana Realty Transfer Certificate filed with the county "
                           "clerk and recorder at closing.",
            "authority": "Montana DOR",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Seller Property Disclosure",
            "code": "SPD",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Montana Seller Property Condition Disclosure Statement.",
            "authority": "Montana Legislature (MCA 70-9-313)",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Radon Disclosure",
            "code": "MCA 75-3-606",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Montana Radon Control Act disclosure. Seller must disclose "
                           "radon test results and mitigation if tested.",
            "authority": "Montana DEQ — Radon Control Program",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Lead-Based Paint Disclosure",
            "code": "42 USC §4852d",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Federal requirement for homes built before 1978. Seller "
                           "must disclose known lead-based paint hazards.",
            "authority": "EPA / HUD",
            "status": RequirementStatus.LIKELY_REQUIRED,
            "notes": "Only applies to homes built before 1978.",
        },
    ],

    # Montana statewide fallback
    "MT::": [
        {
            "name": "Water Rights Form 608",
            "code": "DNRC-608",
            "category": RequirementCategory.FORM,
            "description": "Montana DNRC Form 608 — Ownership Update for water rights "
                           "attached to the property.",
            "authority": "Montana DNRC",
            "fee": "$100 (first right) + $20 each additional",
            "url": "https://dnrc.mt.gov/water-rights/",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Realty Transfer Certificate",
            "code": "RTC",
            "category": RequirementCategory.CERTIFICATE,
            "description": "Montana Realty Transfer Certificate filed with the county "
                           "clerk and recorder at closing.",
            "authority": "Montana DOR",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Seller Property Disclosure",
            "code": "SPD",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Montana Seller Property Condition Disclosure Statement.",
            "authority": "Montana Legislature (MCA 70-9-313)",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Radon Disclosure",
            "code": "MCA 75-3-606",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Montana Radon Control Act disclosure. Seller must disclose "
                           "radon test results and mitigation if tested.",
            "authority": "Montana DEQ — Radon Control Program",
            "status": RequirementStatus.REQUIRED,
        },
    ],

    # -----------------------------------------------------------------------
    # California — Los Angeles City
    # -----------------------------------------------------------------------
    "CA:Los Angeles:Los Angeles": [
        {
            "name": "9A Report (Residential Property Report)",
            "code": "9A/LADBS",
            "category": RequirementCategory.FORM,
            "description": "City of LA Department of Building and Safety report "
                           "disclosing any open/unpermitted work, code violations, "
                           "and zoning information. REQUIRED for all residential "
                           "sales within LA City limits.",
            "authority": "LA Dept of Building & Safety",
            "fee": "$225",
            "url": "https://www.ladbs.org/",
            "status": RequirementStatus.REQUIRED,
            "notes": "Unique to LA City — not required in unincorporated LA County.",
        },
        {
            "name": "Low-Flow Plumbing Retrofit",
            "code": "LAMC 94.1010",
            "category": RequirementCategory.CERTIFICATE,
            "description": "Certificate of compliance for water-conserving plumbing "
                           "fixtures. Seller must retrofit or certify compliance "
                           "before transfer.",
            "authority": "LA Dept of Water & Power",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Transfer Disclosure Statement",
            "code": "TDS",
            "category": RequirementCategory.DISCLOSURE,
            "description": "California statutory disclosure of known material facts "
                           "and defects affecting the property.",
            "authority": "California Civil Code §1102",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Natural Hazard Disclosure",
            "code": "NHD",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Report identifying natural hazard zones (flood, fire, "
                           "earthquake fault, seismic hazard, wildfire).",
            "authority": "California Civil Code §1103",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Smoke & CO Detector Compliance",
            "code": "CA HSC §13113.8",
            "category": RequirementCategory.CERTIFICATE,
            "description": "Written statement of compliance confirming operable smoke "
                           "and carbon monoxide detectors installed per state law.",
            "authority": "California Health & Safety Code",
            "status": RequirementStatus.REQUIRED,
        },
    ],

    # California — unincorporated Los Angeles County (NO 9A Report)
    "CA:Los Angeles:": [
        {
            "name": "Transfer Disclosure Statement",
            "code": "TDS",
            "category": RequirementCategory.DISCLOSURE,
            "description": "California statutory disclosure of known material facts "
                           "and defects affecting the property.",
            "authority": "California Civil Code §1102",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Natural Hazard Disclosure",
            "code": "NHD",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Report identifying natural hazard zones (flood, fire, "
                           "earthquake fault, seismic hazard, wildfire).",
            "authority": "California Civil Code §1103",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Smoke & CO Detector Compliance",
            "code": "CA HSC §13113.8",
            "category": RequirementCategory.CERTIFICATE,
            "description": "Written statement of compliance confirming operable smoke "
                           "and carbon monoxide detectors installed per state law.",
            "authority": "California Health & Safety Code",
            "status": RequirementStatus.REQUIRED,
        },
    ],

    # California statewide fallback
    "CA::": [
        {
            "name": "Transfer Disclosure Statement",
            "code": "TDS",
            "category": RequirementCategory.DISCLOSURE,
            "description": "California statutory disclosure of known material facts "
                           "and defects affecting the property.",
            "authority": "California Civil Code §1102",
            "status": RequirementStatus.REQUIRED,
        },
        {
            "name": "Natural Hazard Disclosure",
            "code": "NHD",
            "category": RequirementCategory.DISCLOSURE,
            "description": "Report identifying natural hazard zones.",
            "authority": "California Civil Code §1103",
            "status": RequirementStatus.REQUIRED,
        },
    ],
}


# ---------------------------------------------------------------------------
# Lookup with fallback cascade
# ---------------------------------------------------------------------------

def lookup_requirements(
    jurisdiction_key: str,
    state: str,
) -> tuple[list[dict[str, Any]], str]:
    """Look up compliance requirements with city → county → state fallback.

    Args:
        jurisdiction_key: Full key like "CA:Los Angeles:Los Angeles"
        state: State abbreviation (e.g., "CA") for fallback

    Returns:
        (requirements_list, matched_key) — the list of rule dicts and which
        key actually matched.
    """
    # Try exact city match
    if jurisdiction_key in SEED_RULES:
        return SEED_RULES[jurisdiction_key], jurisdiction_key

    # Try county (city portion empty)
    parts = jurisdiction_key.split(":")
    if len(parts) == 3 and parts[2]:
        county_key = f"{parts[0]}:{parts[1]}:"
        if county_key in SEED_RULES:
            return SEED_RULES[county_key], county_key

    # Try state fallback
    state_key = f"{state.upper()}::"
    if state_key in SEED_RULES:
        return SEED_RULES[state_key], state_key

    return [], ""


# ---------------------------------------------------------------------------
# Main compliance check function
# ---------------------------------------------------------------------------

def run_compliance_check(
    extracted_data: dict[str, Any],
    transaction_type: Optional[str] = None,
) -> ComplianceReport:
    """Run a compliance check against extracted document data.

    Extracts the property address, resolves the jurisdiction, looks up
    requirements from the seed rules database, and returns a ComplianceReport.

    Args:
        extracted_data: Validated extraction dict (from DotloopLoopDetails).
        transaction_type: Optional transaction type for context.

    Returns:
        ComplianceReport with requirements and overall status.
    """
    # Extract address fields from nested structure
    addr = extracted_data.get("property_address", {})
    if isinstance(addr, dict):
        state = addr.get("state_or_province", "")
        county = addr.get("county", "")
        city = addr.get("city", "")
    else:
        state = county = city = ""

    if not state:
        log.warning("No state found in extracted data — cannot run compliance check")
        return ComplianceReport(
            jurisdiction_key="",
            jurisdiction_display="Unknown",
            jurisdiction_type="unknown",
            overall_status=ComplianceOverallStatus.UNKNOWN_JURISDICTION,
            transaction_type=transaction_type,
            notes="No state found in extracted property address.",
        )

    # Resolve jurisdiction
    key, display, jtype = resolve_jurisdiction(state, county, city)
    log.info("Resolved jurisdiction: %s (%s, type=%s)", key, display, jtype)

    # Look up rules
    rules, matched_key = lookup_requirements(key, state)

    if not rules:
        log.info("No compliance rules found for jurisdiction: %s", key)
        return ComplianceReport(
            jurisdiction_key=key,
            jurisdiction_display=display,
            jurisdiction_type=jtype,
            overall_status=ComplianceOverallStatus.UNKNOWN_JURISDICTION,
            transaction_type=transaction_type,
            notes=f"No compliance rules seeded for {display}. "
                  f"This jurisdiction may still have requirements.",
        )

    # Build requirement models
    requirements = [
        ComplianceRequirement.model_validate(rule)
        for rule in rules
    ]

    # Determine overall status
    has_required = any(
        r.status in (RequirementStatus.REQUIRED, RequirementStatus.LIKELY_REQUIRED)
        for r in requirements
    )
    overall = (
        ComplianceOverallStatus.ACTION_NEEDED
        if has_required
        else ComplianceOverallStatus.PASS
    )

    # Note if we fell back from a more specific jurisdiction
    fallback_note = None
    if matched_key != key:
        _, matched_display, matched_type = resolve_jurisdiction(
            *matched_key.split(":")
        )
        fallback_note = (
            f"No city-level rules found for {display}. "
            f"Showing {matched_type}-level rules for {matched_display}."
        )

    report = ComplianceReport(
        jurisdiction_key=key,
        jurisdiction_display=display,
        jurisdiction_type=jtype,
        overall_status=overall,
        requirements=requirements,
        transaction_type=transaction_type,
        notes=fallback_note,
    )

    log.info(
        "Compliance check complete: %s — %d requirements, %d action items, status=%s",
        display,
        report.requirement_count,
        report.action_items,
        overall.value,
    )

    return report


# ---------------------------------------------------------------------------
# Async DB-first lookup (uses AI Scout results from MongoDB)
# ---------------------------------------------------------------------------

async def async_lookup_requirements(
    jurisdiction_key: str,
    state: str,
) -> tuple[list[dict[str, Any]], str]:
    """Look up compliance requirements with MongoDB-first, SEED_RULES fallback.

    Checks the compliance_rules collection for verified + active ScoutResult
    documents before falling back to the hardcoded SEED_RULES dict.
    Uses the same city → county → state cascade as lookup_requirements().

    Args:
        jurisdiction_key: Full key like "CA:Los Angeles:Los Angeles"
        state: State abbreviation (e.g., "CA") for fallback

    Returns:
        (requirements_list, matched_key)
    """
    from scout_models import ScoutResult

    # Build cascade keys
    parts = jurisdiction_key.split(":")
    cascade_keys = [jurisdiction_key]
    if len(parts) == 3 and parts[2]:
        cascade_keys.append(f"{parts[0]}:{parts[1]}:")
    cascade_keys.append(f"{state.upper()}::")

    # Try each cascade level in MongoDB first
    for key in cascade_keys:
        result = await ScoutResult.find_one(
            {"jurisdiction_key": key, "is_active": True, "is_verified": True}
        )
        if result and result.requirements:
            log.info("DB lookup hit for %s (matched %s)", jurisdiction_key, key)
            return [r.model_dump() for r in result.requirements], key

    # Fallback to SEED_RULES
    log.info("No DB rules found for %s — falling back to SEED_RULES", jurisdiction_key)
    return lookup_requirements(jurisdiction_key, state)


async def async_run_compliance_check(
    extracted_data: dict[str, Any],
    transaction_type: Optional[str] = None,
) -> ComplianceReport:
    """Async compliance check — uses DB-first lookup for AI Scout results.

    Same logic as run_compliance_check() but uses async_lookup_requirements()
    to check MongoDB before falling back to SEED_RULES.
    """
    addr = extracted_data.get("property_address", {})
    if isinstance(addr, dict):
        state = addr.get("state_or_province", "")
        county = addr.get("county", "")
        city = addr.get("city", "")
    else:
        state = county = city = ""

    if not state:
        log.warning("No state found in extracted data — cannot run compliance check")
        return ComplianceReport(
            jurisdiction_key="",
            jurisdiction_display="Unknown",
            jurisdiction_type="unknown",
            overall_status=ComplianceOverallStatus.UNKNOWN_JURISDICTION,
            transaction_type=transaction_type,
            notes="No state found in extracted property address.",
        )

    key, display, jtype = resolve_jurisdiction(state, county, city)
    log.info("Resolved jurisdiction: %s (%s, type=%s)", key, display, jtype)

    # Async DB-first lookup
    rules, matched_key = await async_lookup_requirements(key, state)

    if not rules:
        log.info("No compliance rules found for jurisdiction: %s", key)
        return ComplianceReport(
            jurisdiction_key=key,
            jurisdiction_display=display,
            jurisdiction_type=jtype,
            overall_status=ComplianceOverallStatus.UNKNOWN_JURISDICTION,
            transaction_type=transaction_type,
            notes=f"No compliance rules found for {display}. "
                  f"This jurisdiction may still have requirements.",
        )

    requirements = [
        ComplianceRequirement.model_validate(rule)
        for rule in rules
    ]

    has_required = any(
        r.status in (RequirementStatus.REQUIRED, RequirementStatus.LIKELY_REQUIRED)
        for r in requirements
    )
    overall = (
        ComplianceOverallStatus.ACTION_NEEDED
        if has_required
        else ComplianceOverallStatus.PASS
    )

    fallback_note = None
    if matched_key != key:
        _, matched_display, matched_type = resolve_jurisdiction(
            *matched_key.split(":")
        )
        fallback_note = (
            f"No city-level rules found for {display}. "
            f"Showing {matched_type}-level rules for {matched_display}."
        )

    report = ComplianceReport(
        jurisdiction_key=key,
        jurisdiction_display=display,
        jurisdiction_type=jtype,
        overall_status=overall,
        requirements=requirements,
        transaction_type=transaction_type,
        notes=fallback_note,
    )

    log.info(
        "Async compliance check complete: %s — %d requirements, %d action items, status=%s",
        display,
        report.requirement_count,
        report.action_items,
        overall.value,
    )

    return report
