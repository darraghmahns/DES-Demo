"""Tests for property enrichment modules — property_prefill.py and cadastral_client.py.

Covers:
  1. State normalization (_normalize_state)
  2. RegridClient._normalize (GeoJSON Feature -> flat dict)
  3. enrich_property with mocked Regrid responses
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from cadastral_client import RegridClient
from property_prefill import PropertyEnrichment, _normalize_state, enrich_property


# =============================================================================
# 1. State normalization (_normalize_state)
# =============================================================================


class TestNormalizeState:
    """Tests for _normalize_state: full name -> 2-letter abbreviation."""

    def test_full_name_texas(self):
        assert _normalize_state("Texas") == "TX"

    def test_full_name_california(self):
        assert _normalize_state("California") == "CA"

    def test_full_name_new_york(self):
        assert _normalize_state("New York") == "NY"

    def test_already_abbreviated_tx(self):
        assert _normalize_state("TX") == "TX"

    def test_already_abbreviated_ca(self):
        assert _normalize_state("CA") == "CA"

    def test_mixed_case_lowercase(self):
        """'texas' has len > 2, so it goes through the dict lookup."""
        assert _normalize_state("texas") == "TX"

    def test_mixed_case_uppercase_full(self):
        """'TEXAS' has len > 2, so .lower() lookup finds it."""
        assert _normalize_state("TEXAS") == "TX"

    def test_lowercase_abbreviation(self):
        """'tx' has len == 2, so it gets uppercased directly."""
        assert _normalize_state("tx") == "TX"

    def test_unknown_value_passes_through(self):
        """A value not in the lookup table is returned as-is."""
        assert _normalize_state("Ontario") == "Ontario"

    def test_empty_string(self):
        assert _normalize_state("") == ""

    def test_district_of_columbia(self):
        assert _normalize_state("District of Columbia") == "DC"

    def test_multi_word_state_west_virginia(self):
        assert _normalize_state("West Virginia") == "WV"

    def test_multi_word_state_north_carolina(self):
        assert _normalize_state("North Carolina") == "NC"


# =============================================================================
# 2. RegridClient._normalize (static method)
# =============================================================================


def _make_geojson_feature(**field_overrides) -> dict:
    """Build a minimal GeoJSON Feature with Regrid-style nested properties."""
    fields = {
        "parcelnumb": "12-345-678",
        "parcelnumb_no_formatting": "12345678",
        "owner": "Jane Doe",
        "address": "123 Main St",
        "scity": "Austin",
        "state2": "TX",
        "szip": "78701",
        "county": "Travis",
        "ll_gissqft": "5000.5",
        "ll_gisacre": "0.115",
        "yearbuilt": "1985",
        "asmttotal": "350000",
        "assdland": "150000",
        "assdimprv": "200000",
        "zoning": "R-1",
        "usedesc": "Single Family Residential",
        "lat": "30.2672",
        "lon": "-97.7431",
    }
    fields.update(field_overrides)
    return {
        "type": "Feature",
        "properties": {
            "fields": fields,
        },
    }


class TestRegridNormalize:
    """Tests for RegridClient._normalize static method."""

    def test_well_formed_feature_returns_flat_dict(self):
        feature = _make_geojson_feature()
        result = RegridClient._normalize(feature)

        assert result["parcel_id"] == "12-345-678"
        assert result["apn"] == "12345678"
        assert result["owner_name"] == "Jane Doe"
        assert result["address_full"] == "123 Main St"
        assert result["city"] == "Austin"
        assert result["state"] == "TX"
        assert result["zip_code"] == "78701"
        assert result["county"] == "Travis"
        assert result["zoning"] == "R-1"
        assert result["land_use"] == "Single Family Residential"

    def test_numeric_conversions(self):
        feature = _make_geojson_feature()
        result = RegridClient._normalize(feature)

        assert result["lot_size_sqft"] == pytest.approx(5000.5)
        assert result["lot_size_acres"] == pytest.approx(0.115)
        assert result["year_built"] == 1985
        assert result["assessed_total"] == pytest.approx(350000.0)
        assert result["assessed_land"] == pytest.approx(150000.0)
        assert result["assessed_improvement"] == pytest.approx(200000.0)
        assert result["latitude"] == pytest.approx(30.2672)
        assert result["longitude"] == pytest.approx(-97.7431)

    def test_missing_fields_return_none(self):
        """A feature with no fields at all should produce None values."""
        feature = {"type": "Feature", "properties": {"fields": {}}}
        result = RegridClient._normalize(feature)

        assert result["parcel_id"] is None
        assert result["apn"] is None
        assert result["owner_name"] is None
        assert result["lot_size_sqft"] is None
        assert result["year_built"] is None
        assert result["assessed_total"] is None
        assert result["latitude"] is None

    def test_null_fields_return_none(self):
        """Explicit None values in fields should produce None in output."""
        feature = _make_geojson_feature(
            ll_gissqft=None,
            yearbuilt=None,
            asmttotal=None,
            lat=None,
        )
        result = RegridClient._normalize(feature)

        assert result["lot_size_sqft"] is None
        assert result["year_built"] is None
        assert result["assessed_total"] is None
        assert result["latitude"] is None

    def test_float_conversion_with_string_number(self):
        feature = _make_geojson_feature(ll_gissqft="1234.56")
        result = RegridClient._normalize(feature)
        assert result["lot_size_sqft"] == pytest.approx(1234.56)

    def test_float_conversion_with_non_numeric_string(self):
        """Non-numeric strings should convert to None, not raise."""
        feature = _make_geojson_feature(ll_gissqft="N/A")
        result = RegridClient._normalize(feature)
        assert result["lot_size_sqft"] is None

    def test_int_conversion_with_float_string(self):
        """Year built '1985.0' should become int 1985."""
        feature = _make_geojson_feature(yearbuilt="1985.0")
        result = RegridClient._normalize(feature)
        assert result["year_built"] == 1985

    def test_int_conversion_with_non_numeric(self):
        feature = _make_geojson_feature(yearbuilt="unknown")
        result = RegridClient._normalize(feature)
        assert result["year_built"] is None

    def test_fallback_field_mappings(self):
        """When primary field is missing, fallback field should be used."""
        feature = {
            "type": "Feature",
            "properties": {
                "fields": {
                    "parcelnumb_no_formatting": "99887766",
                    # parcelnumb missing -> parcel_id falls back to parcelnumb_no_formatting
                    "saddcity": "Dallas",
                    # scity missing -> city falls back to saddcity
                    "saddstab": "TX",
                    # state2 missing -> state falls back to saddstab
                    "saddzip": "75201",
                    # szip missing -> zip_code falls back to saddzip
                    "zoning_description": "Commercial",
                    # zoning missing -> falls back to zoning_description
                    "usecode": "COMM",
                    # usedesc missing -> falls back to usecode
                },
            },
        }
        result = RegridClient._normalize(feature)

        assert result["parcel_id"] == "99887766"
        assert result["apn"] == "99887766"
        assert result["city"] == "Dallas"
        assert result["state"] == "TX"
        assert result["zip_code"] == "75201"
        assert result["zoning"] == "Commercial"
        assert result["land_use"] == "COMM"

    def test_properties_without_fields_key(self):
        """If 'fields' key is absent, properties dict itself is used."""
        feature = {
            "type": "Feature",
            "properties": {
                "parcelnumb": "DIRECT-123",
                "owner": "Direct Owner",
            },
        }
        result = RegridClient._normalize(feature)
        assert result["parcel_id"] == "DIRECT-123"
        assert result["owner_name"] == "Direct Owner"

    def test_empty_properties(self):
        feature = {"type": "Feature", "properties": {}}
        result = RegridClient._normalize(feature)
        assert result["parcel_id"] is None
        assert result["owner_name"] is None


# =============================================================================
# 3. enrich_property with mocked Regrid responses
# =============================================================================


def _make_regrid_result(**overrides) -> dict:
    """Build a successful Regrid lookup result dict."""
    base = {
        "parcel_id": "12-345-678",
        "apn": "12345678",
        "owner_name": "Jane Doe",
        "address_full": "123 Main St",
        "city": "Austin",
        "state": "TX",
        "zip_code": "78701",
        "county": "Travis",
        "lot_size_sqft": 5000.5,
        "lot_size_acres": 0.115,
        "year_built": 1985,
        "assessed_total": 350000.0,
        "assessed_land": 150000.0,
        "assessed_improvement": 200000.0,
        "zoning": "R-1",
        "land_use": "Single Family Residential",
        "latitude": 30.2672,
        "longitude": -97.7431,
    }
    base.update(overrides)
    return base


def _make_address(**overrides) -> dict:
    """Build a property address dict matching DotloopPropertyAddress fields."""
    base = {
        "street_number": "123",
        "street_name": "Main St",
        "city": "Austin",
        "state_or_province": "TX",
        "postal_code": "78701",
        "county": "Travis",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
class TestEnrichPropertySuccess:
    """enrich_property returns PropertyEnrichment with match_quality='exact' on success."""

    async def test_successful_lookup(self):
        mock_result = _make_regrid_result()

        with (
            patch("property_prefill.is_configured", return_value=True),
            patch("property_prefill._get_regrid_client") as mock_get_client,
            patch("property_prefill.asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)),
        ):
            mock_client = MagicMock()
            mock_client.lookup_by_address.return_value = mock_result
            mock_get_client.return_value = mock_client

            result = await enrich_property(_make_address())

        assert result is not None
        assert isinstance(result, PropertyEnrichment)
        assert result.match_quality == "exact"
        assert result.source == "regrid"
        assert result.parcel_id == "12-345-678"
        assert result.owner_name == "Jane Doe"
        assert result.assessed_total == pytest.approx(350000.0)
        assert result.year_built == 1985
        assert result.lookup_timestamp is not None

    async def test_successful_lookup_maps_all_fields(self):
        """All PropertyEnrichment-recognized fields from the result are mapped."""
        mock_result = _make_regrid_result()

        with (
            patch("property_prefill.is_configured", return_value=True),
            patch("property_prefill._get_regrid_client") as mock_get_client,
            patch("property_prefill.asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)),
        ):
            mock_client = MagicMock()
            mock_client.lookup_by_address.return_value = mock_result
            mock_get_client.return_value = mock_client

            result = await enrich_property(_make_address())

        assert result.apn == "12345678"
        assert result.lot_size_sqft == pytest.approx(5000.5)
        assert result.lot_size_acres == pytest.approx(0.115)
        assert result.assessed_land == pytest.approx(150000.0)
        assert result.assessed_improvement == pytest.approx(200000.0)
        assert result.zoning == "R-1"
        assert result.land_use == "Single Family Residential"
        assert result.latitude == pytest.approx(30.2672)
        assert result.longitude == pytest.approx(-97.7431)

    async def test_state_normalization_in_lookup(self):
        """Full state name 'Texas' in address should be normalized to 'TX' for the API call."""
        mock_result = _make_regrid_result()

        with (
            patch("property_prefill.is_configured", return_value=True),
            patch("property_prefill._get_regrid_client") as mock_get_client,
            patch("property_prefill.asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)),
        ):
            mock_client = MagicMock()
            mock_client.lookup_by_address.return_value = mock_result
            mock_get_client.return_value = mock_client

            result = await enrich_property(_make_address(state_or_province="Texas"))

        assert result is not None
        assert result.match_quality == "exact"
        # Verify the client was called with normalized state
        mock_client.lookup_by_address.assert_called_once()
        call_args = mock_client.lookup_by_address.call_args
        assert call_args[0][2] == "TX"  # third positional arg is state


@pytest.mark.asyncio
class TestEnrichPropertyNoMatch:
    """enrich_property returns match_quality='none' when lookup finds nothing."""

    async def test_lookup_returns_none(self):
        with (
            patch("property_prefill.is_configured", return_value=True),
            patch("property_prefill._get_regrid_client") as mock_get_client,
            patch("property_prefill.asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)),
        ):
            mock_client = MagicMock()
            mock_client.lookup_by_address.return_value = None
            mock_get_client.return_value = mock_client

            result = await enrich_property(_make_address())

        assert result is not None
        assert isinstance(result, PropertyEnrichment)
        assert result.match_quality == "none"
        assert result.source == "regrid"
        assert result.parcel_id is None


@pytest.mark.asyncio
class TestEnrichPropertyHttpError:
    """enrich_property handles HTTP errors gracefully (no crash, returns match_quality='none')."""

    async def test_httpx_http_error(self):
        with (
            patch("property_prefill.is_configured", return_value=True),
            patch("property_prefill._get_regrid_client") as mock_get_client,
            patch(
                "property_prefill.asyncio.to_thread",
                side_effect=httpx.HTTPError("Connection failed"),
            ),
        ):
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            result = await enrich_property(_make_address())

        assert result is not None
        assert isinstance(result, PropertyEnrichment)
        assert result.match_quality == "none"
        assert result.source == "regrid"

    async def test_os_error(self):
        """OSError (e.g. DNS failure) should also be caught."""
        with (
            patch("property_prefill.is_configured", return_value=True),
            patch("property_prefill._get_regrid_client") as mock_get_client,
            patch(
                "property_prefill.asyncio.to_thread",
                side_effect=OSError("DNS resolution failed"),
            ),
        ):
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            result = await enrich_property(_make_address())

        assert result is not None
        assert result.match_quality == "none"

    async def test_value_error(self):
        """ValueError should also be caught."""
        with (
            patch("property_prefill.is_configured", return_value=True),
            patch("property_prefill._get_regrid_client") as mock_get_client,
            patch(
                "property_prefill.asyncio.to_thread",
                side_effect=ValueError("Unexpected response format"),
            ),
        ):
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            result = await enrich_property(_make_address())

        assert result is not None
        assert result.match_quality == "none"


@pytest.mark.asyncio
class TestEnrichPropertyMissingFields:
    """enrich_property returns None when required address fields are missing."""

    async def test_no_street(self):
        """No street_number and no street_name -> None."""
        address = _make_address(street_number="", street_name="")
        with patch("property_prefill.is_configured", return_value=True):
            result = await enrich_property(address)
        assert result is None

    async def test_no_city(self):
        address = _make_address(city="")
        with patch("property_prefill.is_configured", return_value=True):
            result = await enrich_property(address)
        assert result is None

    async def test_no_state(self):
        address = _make_address(state_or_province="")
        with patch("property_prefill.is_configured", return_value=True):
            result = await enrich_property(address)
        assert result is None

    async def test_none_values(self):
        """None values in address fields should be treated as missing."""
        address = _make_address(street_number=None, street_name=None)
        with patch("property_prefill.is_configured", return_value=True):
            result = await enrich_property(address)
        assert result is None

    async def test_whitespace_only_street(self):
        """Whitespace-only street should be treated as empty."""
        address = _make_address(street_number="  ", street_name="  ")
        with patch("property_prefill.is_configured", return_value=True):
            result = await enrich_property(address)
        assert result is None


@pytest.mark.asyncio
class TestEnrichPropertyNotConfigured:
    """enrich_property returns None when REGRID_API_KEY is not set."""

    async def test_not_configured_returns_none(self):
        with patch("property_prefill.is_configured", return_value=False):
            result = await enrich_property(_make_address())
        assert result is None

    async def test_not_configured_does_not_call_regrid(self):
        """When not configured, no Regrid client call should be made."""
        with (
            patch("property_prefill.is_configured", return_value=False),
            patch("property_prefill._get_regrid_client") as mock_get_client,
        ):
            result = await enrich_property(_make_address())

        assert result is None
        mock_get_client.assert_not_called()


@pytest.mark.asyncio
class TestEnrichPropertyNoneValuesFiltered:
    """None values in the Regrid result should not be passed to PropertyEnrichment."""

    async def test_none_values_excluded_from_enrichment(self):
        """Fields with None values in the result dict should be excluded."""
        mock_result = _make_regrid_result(
            lot_size_sqft=None,
            year_built=None,
            assessed_total=None,
        )

        with (
            patch("property_prefill.is_configured", return_value=True),
            patch("property_prefill._get_regrid_client") as mock_get_client,
            patch("property_prefill.asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)),
        ):
            mock_client = MagicMock()
            mock_client.lookup_by_address.return_value = mock_result
            mock_get_client.return_value = mock_client

            result = await enrich_property(_make_address())

        assert result is not None
        assert result.match_quality == "exact"
        # These should fall back to their Pydantic defaults (None)
        assert result.lot_size_sqft is None
        assert result.year_built is None
        assert result.assessed_total is None
        # But other fields should still be populated
        assert result.parcel_id == "12-345-678"
        assert result.owner_name == "Jane Doe"
