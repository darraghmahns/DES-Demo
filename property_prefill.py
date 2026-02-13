"""Property enrichment orchestrator — Layer 2 of the cadastral integration.

Takes an extracted property address (from GPT-4o OCR) and enriches it with
parcel/assessor data from the Regrid API.  Sits between the raw HTTP client
(cadastral_client.py) and the FastAPI routes (server.py).

Key function:
    enrich_property(address_dict) -> PropertyEnrichment | None

Architecture follows the same pattern as dotloop_connector.py:
  Layer 1: cadastral_client.py (RegridClient)
  Layer 2: property_prefill.py  (this file)
  Layer 3: server.py            (FastAPI routes + pipeline step)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from schemas import PropertyEnrichment
from cadastral_client import RegridClient

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """Return True if the Regrid API key is set in environment."""
    return bool(os.getenv("REGRID_API_KEY"))


# ---------------------------------------------------------------------------
# State normalization
# ---------------------------------------------------------------------------

US_STATE_ABBREVIATIONS: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}


def _normalize_state(state: str) -> str:
    """Convert full US state name to 2-letter abbreviation for Regrid API."""
    if len(state) == 2:
        return state.upper()
    return US_STATE_ABBREVIATIONS.get(state.lower(), state)


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------


async def enrich_property(address: dict[str, Any]) -> PropertyEnrichment | None:
    """Look up cadastral data for an extracted property address.

    Args:
        address: Dict with keys matching DotloopPropertyAddress fields:
                 street_number, street_name, city, state_or_province,
                 postal_code, county (all optional strings).

    Returns:
        PropertyEnrichment with match data, or None if unconfigured / missing
        required address fields.  Returns a "none" match_quality result if the
        lookup ran but found no parcels.
    """
    if not is_configured():
        log.debug("Regrid not configured — skipping property enrichment")
        return None

    # Build street line from components
    street_number = (address.get("street_number") or "").strip()
    street_name = (address.get("street_name") or "").strip()
    street = f"{street_number} {street_name}".strip()

    city = (address.get("city") or "").strip()
    raw_state = (address.get("state_or_province") or "").strip()
    state = _normalize_state(raw_state)
    zip_code = (address.get("postal_code") or "").strip()

    log.info("Property enrichment input: street=%r city=%r state=%r (raw=%r) zip=%r", street, city, state, raw_state, zip_code)

    if not street or not city or not state:
        log.info(
            "Insufficient address for enrichment: street=%r city=%r state=%r",
            street, city, state,
        )
        return None

    now = datetime.now(timezone.utc).isoformat()

    # Run synchronous HTTP call in a thread to avoid blocking the event loop
    client = RegridClient()
    try:
        result = await asyncio.to_thread(
            client.lookup_by_address, street, city, state, zip_code,
        )
        log.info("Regrid lookup result: %s", result)
    except Exception:
        log.exception("Regrid lookup failed for %s, %s, %s", street, city, state)
        return PropertyEnrichment(
            source="regrid",
            lookup_timestamp=now,
            match_quality="none",
        )
    finally:
        client.close()

    if not result:
        return PropertyEnrichment(
            source="regrid",
            lookup_timestamp=now,
            match_quality="none",
        )

    # Map Regrid result fields to PropertyEnrichment fields
    enrichment_fields = {
        k: v
        for k, v in result.items()
        if k in PropertyEnrichment.model_fields and v is not None
    }

    return PropertyEnrichment(
        **enrichment_fields,
        source="regrid",
        lookup_timestamp=now,
        match_quality="exact",
    )


async def lookup_by_parcel_id(parcel_id: str) -> PropertyEnrichment | None:
    """Direct parcel lookup by APN / tax ID.

    Useful for manual lookups via the /api/property/lookup endpoint.
    """
    if not is_configured():
        return None

    now = datetime.now(timezone.utc).isoformat()
    client = RegridClient()
    try:
        result = await asyncio.to_thread(client.lookup_by_parcel_id, parcel_id)
    except Exception:
        log.exception("Regrid parcel ID lookup failed for %s", parcel_id)
        return PropertyEnrichment(
            source="regrid",
            lookup_timestamp=now,
            match_quality="none",
        )
    finally:
        client.close()

    if not result:
        return PropertyEnrichment(
            source="regrid",
            lookup_timestamp=now,
            match_quality="none",
        )

    enrichment_fields = {
        k: v
        for k, v in result.items()
        if k in PropertyEnrichment.model_fields and v is not None
    }

    return PropertyEnrichment(
        **enrichment_fields,
        source="regrid",
        lookup_timestamp=now,
        match_quality="exact",
    )
