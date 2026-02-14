"""Regrid (Loveland) Parcel Data API client.

Provides property/parcel lookups by address or APN (Assessor's Parcel Number).
Returns normalized property enrichment data including assessed values, lot size,
zoning, year built, and parcel coordinates.

API docs: https://regrid.com/api
Free tier: 100 lookups/month.

Follows the same 3-layer architecture as dotloop_client.py:
  Layer 1: Raw HTTP client (this file)
  Layer 2: Business logic orchestrator (property_prefill.py)
  Layer 3: FastAPI routes (server.py)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class RegridClient:
    """Regrid Parcel Data API v2 client."""

    BASE_URL = "https://app.regrid.com/api/v2"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._api_key = api_key or os.getenv("REGRID_API_KEY", "")
        self._timeout = timeout
        self._client: httpx.Client | None = None

    # -- lifecycle -----------------------------------------------------------

    def _build_client(self) -> httpx.Client:
        """Build an httpx client with token query param auth."""
        return httpx.Client(
            base_url=self.BASE_URL,
            headers={"Accept": "application/json"},
            params={"token": self._api_key},
            timeout=self._timeout,
        )

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    # -- lookups -------------------------------------------------------------

    def lookup_by_address(
        self,
        street: str,
        city: str,
        state: str,
        zip_code: str = "",
    ) -> dict[str, Any] | None:
        """Search parcels by street address.

        Builds a single-line query from the components and returns the
        first (best) match, or *None* if nothing found.
        """
        query = f"{street}, {city}, {state}"
        if zip_code:
            query += f" {zip_code}"
        query = query.strip()

        log.info("Regrid address lookup: %s", query)
        try:
            resp = self.client.get(
                "/parcels/address",
                params={"query": query, "limit": 1},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning("Regrid HTTP error %s for query: %s", exc.response.status_code, query)
            return None
        except httpx.RequestError as exc:
            log.warning("Regrid request error for query %s: %s", query, exc)
            return None

        data = resp.json()
        log.info("Regrid response keys: %s", list(data.keys()))
        log.info("Regrid response preview: %.500s", resp.text[:500])
        parcels = data.get("parcels", data)  # Regrid v2 wraps under "parcels"
        features = parcels.get("features", [])
        if not features:
            log.info("Regrid: no parcels matched for %s", query)
            return None

        return self._normalize(features[0])

    def lookup_by_parcel_id(self, parcel_id: str) -> dict[str, Any] | None:
        """Look up a parcel by APN / tax ID.

        Uses the Regrid search endpoint with the parcel number filter.
        """
        log.info("Regrid parcel ID lookup: %s", parcel_id)
        try:
            resp = self.client.get(
                "/parcels/apn",
                params={"parcelnumb": parcel_id, "limit": 1},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.warning("Regrid HTTP error %s for parcel %s", exc.response.status_code, parcel_id)
            return None
        except httpx.RequestError as exc:
            log.warning("Regrid request error for parcel %s: %s", parcel_id, exc)
            return None

        data = resp.json()
        parcels = data.get("parcels", data)  # Regrid v2 wraps under "parcels"
        features = parcels.get("features", [])
        if not features:
            log.info("Regrid: no parcels matched for APN %s", parcel_id)
            return None

        return self._normalize(features[0])

    # -- normalization -------------------------------------------------------

    @staticmethod
    def _normalize(feature: dict[str, Any]) -> dict[str, Any]:
        """Extract key fields from a GeoJSON Feature into a flat dict.

        Maps Regrid's property names to our internal PropertyEnrichment
        field names.
        """
        props = feature.get("properties", {})
        fields = props.get("fields", props)  # Regrid v2 nests under "fields"

        def _float(val: Any) -> float | None:
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        def _int(val: Any) -> int | None:
            if val is None:
                return None
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return None

        return {
            "parcel_id": fields.get("parcelnumb") or fields.get("parcelnumb_no_formatting"),
            "apn": fields.get("parcelnumb_no_formatting") or fields.get("parcelnumb"),
            "owner_name": fields.get("owner"),
            "address_full": fields.get("address"),
            "city": fields.get("scity") or fields.get("saddcity"),
            "state": fields.get("state2") or fields.get("saddstab"),
            "zip_code": fields.get("szip") or fields.get("saddzip"),
            "county": fields.get("county"),
            "lot_size_sqft": _float(fields.get("ll_gissqft")),
            "lot_size_acres": _float(fields.get("ll_gisacre")),
            "year_built": _int(fields.get("yearbuilt")),
            "assessed_total": _float(fields.get("asmttotal")),
            "assessed_land": _float(fields.get("assdland")),
            "assessed_improvement": _float(fields.get("assdimprv")),
            "zoning": fields.get("zoning") or fields.get("zoning_description"),
            "land_use": fields.get("usedesc") or fields.get("usecode"),
            "latitude": _float(fields.get("lat")),
            "longitude": _float(fields.get("lon")),
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """Return True if a Regrid API key is set."""
    return bool(os.getenv("REGRID_API_KEY"))
