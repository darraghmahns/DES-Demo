"""Comprehensive tests for JACE AI Scout.

Layered structure:
  A. Unit tests — pure functions, no IO, no mocking needed
  B. Async integration tests — mock OpenAI + Beanie, test async business logic
  C. API endpoint tests — FastAPI TestClient against scout server routes
  D. Scout model validation tests
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from compliance_engine import (
    async_lookup_requirements,
    async_run_compliance_check,
    lookup_requirements,
    resolve_jurisdiction,
    run_compliance_check,
)
from schemas import (
    ComplianceOverallStatus,
    RequirementCategory,
    RequirementStatus,
)
from scout import _parse_requirement, research_jurisdiction, run_scout, verify_requirements
from scout_models import ScoutRequirement, ScoutResult

from tests.conftest import make_openai_response, make_scout_requirement, make_scout_result, MOCK_OBJECT_ID


# =========================================================================
# A. UNIT TESTS — Pure Functions, No IO
# =========================================================================


class TestResolveJurisdiction:
    """Tests for compliance_engine.resolve_jurisdiction()."""

    def test_city_level(self):
        key, display, jtype = resolve_jurisdiction("MT", "Gallatin", "Bozeman")
        assert key == "MT:Gallatin:Bozeman"
        assert jtype == "city"
        assert "Bozeman" in display
        assert "MT" in display

    def test_county_level(self):
        key, display, jtype = resolve_jurisdiction("MT", "Missoula")
        assert key == "MT:Missoula:"
        assert jtype == "county"
        assert "unincorporated" in display.lower()

    def test_state_level(self):
        key, display, jtype = resolve_jurisdiction("CA")
        assert key == "CA::"
        assert jtype == "state"
        assert "statewide" in display.lower()

    def test_normalizes_case(self):
        key, _, _ = resolve_jurisdiction("mt", "gallatin", "bozeman")
        assert key == "MT:Gallatin:Bozeman"

    def test_strips_whitespace(self):
        key, _, _ = resolve_jurisdiction("  MT ", " Gallatin ", " Bozeman ")
        assert key == "MT:Gallatin:Bozeman"

    def test_empty_string_county_treated_as_state(self):
        key, _, jtype = resolve_jurisdiction("CA", "", "")
        assert key == "CA::"
        assert jtype == "state"

    def test_county_with_no_city(self):
        key, display, jtype = resolve_jurisdiction("CA", "Los Angeles")
        assert key == "CA:Los Angeles:"
        assert jtype == "county"


class TestLookupRequirements:
    """Tests for compliance_engine.lookup_requirements() — sync SEED_RULES."""

    def test_exact_city_match_helena(self):
        rules, matched = lookup_requirements("MT:Lewis And Clark:Helena", "MT")
        assert matched == "MT:Lewis And Clark:Helena"
        assert len(rules) == 7
        names = [r["name"] for r in rules]
        assert "Water Rights Form 608" in names

    def test_missoula_city_includes_connect_on_sale(self):
        rules, matched = lookup_requirements("MT:Missoula:Missoula", "MT")
        assert matched == "MT:Missoula:Missoula"
        names = [r["name"] for r in rules]
        assert "Connect on Sale — Sewer Connection" in names

    def test_county_fallback_excludes_city_rules(self):
        """Unincorporated Missoula County should NOT have Connect on Sale."""
        rules, matched = lookup_requirements("MT:Missoula:", "MT")
        assert matched == "MT:Missoula:"
        names = [r["name"] for r in rules]
        assert "Connect on Sale — Sewer Connection" not in names

    def test_unknown_city_falls_to_county(self):
        rules, matched = lookup_requirements("MT:Missoula:Lolo", "MT")
        assert matched == "MT:Missoula:"

    def test_unknown_county_falls_to_state(self):
        rules, matched = lookup_requirements("MT:Flathead:Kalispell", "MT")
        assert matched == "MT::"

    def test_completely_unknown_returns_empty(self):
        rules, matched = lookup_requirements("NY:Kings:Brooklyn", "NY")
        assert rules == []
        assert matched == ""

    def test_la_city_has_9a_report(self):
        rules, _ = lookup_requirements("CA:Los Angeles:Los Angeles", "CA")
        names = [r["name"] for r in rules]
        assert "9A Report (Residential Property Report)" in names

    def test_la_county_no_9a_report(self):
        rules, _ = lookup_requirements("CA:Los Angeles:", "CA")
        names = [r["name"] for r in rules]
        assert "9A Report (Residential Property Report)" not in names

    def test_ca_statewide_fallback(self):
        rules, matched = lookup_requirements("CA:San Diego:San Diego", "CA")
        assert matched == "CA::"
        assert len(rules) == 2


class TestParseRequirement:
    """Tests for scout._parse_requirement() — dict → ScoutRequirement."""

    def test_valid_full_dict(self):
        raw = {
            "name": "Test Req",
            "code": "TEST-001",
            "category": "FORM",
            "description": "A test requirement.",
            "authority": "Test Authority",
            "fee": "$50",
            "url": "https://example.com",
            "status": "REQUIRED",
            "notes": "Some notes",
            "confidence": 0.9,
            "source_reasoning": "Because tests.",
        }
        result = _parse_requirement(raw)
        assert result is not None
        assert result.name == "Test Req"
        assert result.category == RequirementCategory.FORM
        assert result.confidence == 0.9

    def test_minimal_dict(self):
        raw = {"name": "Minimal Req"}
        result = _parse_requirement(raw)
        assert result is not None
        assert result.name == "Minimal Req"
        assert result.category == RequirementCategory.FORM  # default
        assert result.confidence == 0.0

    def test_missing_name_returns_none(self):
        raw = {"code": "NO-NAME"}
        result = _parse_requirement(raw)
        assert result is None

    def test_case_insensitive_category(self):
        raw = {"name": "Test", "category": "inspection"}
        result = _parse_requirement(raw)
        assert result is not None
        assert result.category == RequirementCategory.INSPECTION

    def test_unknown_category_defaults_to_form(self):
        raw = {"name": "Test", "category": "BOGUS"}
        result = _parse_requirement(raw)
        assert result is not None
        assert result.category == RequirementCategory.FORM

    def test_unknown_status_defaults_to_required(self):
        raw = {"name": "Test", "status": "MAYBE"}
        result = _parse_requirement(raw)
        assert result is not None
        assert result.status == RequirementStatus.REQUIRED

    def test_confidence_over_1_returns_none(self):
        """Pydantic ge/le constraint rejects confidence > 1.0."""
        raw = {"name": "Test", "confidence": 5.0}
        result = _parse_requirement(raw)
        assert result is None

    def test_null_optional_fields(self):
        raw = {
            "name": "Test",
            "code": None,
            "authority": None,
            "fee": None,
            "url": None,
            "notes": None,
            "source_reasoning": None,
        }
        result = _parse_requirement(raw)
        assert result is not None
        assert result.code is None


class TestSyncComplianceCheck:
    """Tests for run_compliance_check() — sync version using SEED_RULES."""

    def test_helena_returns_action_needed(self, helena_extracted_data):
        report = run_compliance_check(helena_extracted_data)
        assert report.jurisdiction_key == "MT:Lewis And Clark:Helena"
        assert report.overall_status == ComplianceOverallStatus.ACTION_NEEDED
        assert report.requirement_count == 7

    def test_unknown_jurisdiction_returns_unknown_status(self, unknown_jurisdiction_data):
        report = run_compliance_check(unknown_jurisdiction_data)
        assert report.overall_status == ComplianceOverallStatus.UNKNOWN_JURISDICTION

    def test_missing_state_returns_unknown(self, no_state_data):
        report = run_compliance_check(no_state_data)
        assert report.overall_status == ComplianceOverallStatus.UNKNOWN_JURISDICTION
        assert report.jurisdiction_key == ""

    def test_fallback_generates_note(self):
        data = {
            "property_address": {
                "state_or_province": "MT",
                "county": "Missoula",
                "city": "Lolo",
            }
        }
        report = run_compliance_check(data)
        assert report.notes is not None
        assert "county" in report.notes.lower() or "level" in report.notes.lower()

    def test_missoula_city_has_connect_on_sale(self, missoula_extracted_data):
        report = run_compliance_check(missoula_extracted_data)
        names = [r.name for r in report.requirements]
        assert "Connect on Sale — Sewer Connection" in names


# =========================================================================
# B. ASYNC INTEGRATION TESTS — Mock OpenAI + Beanie
# =========================================================================


class TestResearchJurisdiction:
    """Tests for scout.research_jurisdiction() with mocked OpenAI."""

    async def test_returns_requirements_list(self, mock_openai_client, mock_research_response):
        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=mock_research_response
        )
        result = await research_jurisdiction(
            "MT", "Gallatin", "Bozeman", client=mock_openai_client
        )
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "Water Rights Form 608"

    async def test_calls_openai_with_correct_model(
        self, mock_openai_client, mock_research_response
    ):
        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=mock_research_response
        )
        await research_jurisdiction("MT", client=mock_openai_client)
        call_kwargs = mock_openai_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o"
        assert call_kwargs.kwargs["response_format"] == {"type": "json_object"}

    async def test_includes_jurisdiction_in_prompt(
        self, mock_openai_client, mock_research_response
    ):
        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=mock_research_response
        )
        await research_jurisdiction(
            "MT", "Gallatin", "Bozeman", client=mock_openai_client
        )
        call_kwargs = mock_openai_client.chat.completions.create.call_args
        user_msg = call_kwargs.kwargs["messages"][1]["content"]
        assert "Bozeman" in user_msg
        assert "Gallatin" in user_msg

    async def test_handles_empty_requirements(self, mock_openai_client):
        empty_resp = make_openai_response({"requirements": []})
        mock_openai_client.chat.completions.create = AsyncMock(return_value=empty_resp)
        result = await research_jurisdiction("MT", client=mock_openai_client)
        assert result == []


class TestVerifyRequirements:
    """Tests for scout.verify_requirements() with mocked OpenAI."""

    async def test_returns_verified_and_removed(
        self, mock_openai_client, mock_verify_response
    ):
        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=mock_verify_response
        )
        proposed = [
            {"name": "Water Rights Form 608"},
            {"name": "Realty Transfer Certificate"},
        ]
        verified, removed = await verify_requirements(
            "MT", proposed, "Gallatin", "Bozeman", client=mock_openai_client
        )
        assert len(verified) == 1
        assert verified[0]["name"] == "Water Rights Form 608"
        assert verified[0]["confidence"] == 0.95
        assert len(removed) == 1
        assert removed[0]["name"] == "Realty Transfer Certificate"

    async def test_uses_temperature_zero(
        self, mock_openai_client, mock_verify_response
    ):
        mock_openai_client.chat.completions.create = AsyncMock(
            return_value=mock_verify_response
        )
        await verify_requirements(
            "MT", [{"name": "test"}], client=mock_openai_client
        )
        call_kwargs = mock_openai_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["temperature"] == 0.0


class TestRunScout:
    """Tests for scout.run_scout() — full pipeline with mocked OpenAI + Beanie."""

    async def test_full_pipeline_returns_scout_result(
        self, mock_openai_client, patch_beanie_scout_result
    ):
        with patch("scout._get_client", return_value=mock_openai_client):
            result = await run_scout(
                "MT", county="Gallatin", city="Bozeman", save_to_db=True
            )

        assert isinstance(result, ScoutResult)
        assert result.state == "MT"
        assert result.jurisdiction_key == "MT:Gallatin:Bozeman"
        assert result.jurisdiction_type == "city"
        assert len(result.requirements) == 1  # only 1 survived verify pass
        assert result.requirements[0].name == "Water Rights Form 608"
        assert result.is_verified is False
        assert result.is_active is False

    async def test_saves_to_db_when_flag_true(
        self, mock_openai_client, patch_beanie_scout_result
    ):
        with patch("scout._get_client", return_value=mock_openai_client):
            await run_scout("MT", save_to_db=True)
        patch_beanie_scout_result["insert"].assert_called_once()

    async def test_skips_db_when_flag_false(
        self, mock_openai_client, patch_beanie_scout_result
    ):
        with patch("scout._get_client", return_value=mock_openai_client):
            await run_scout("MT", save_to_db=False)
        patch_beanie_scout_result["insert"].assert_not_called()

    async def test_notes_contain_requirement_counts(
        self, mock_openai_client, patch_beanie_scout_result
    ):
        with patch("scout._get_client", return_value=mock_openai_client):
            result = await run_scout("MT", save_to_db=False)
        assert "1 requirements" in result.notes
        assert "1 removed" in result.notes

    async def test_normalizes_state_case(
        self, mock_openai_client, patch_beanie_scout_result
    ):
        with patch("scout._get_client", return_value=mock_openai_client):
            result = await run_scout("mt", save_to_db=False)
        assert result.state == "MT"


class TestAsyncLookupRequirements:
    """Tests for compliance_engine.async_lookup_requirements() — DB-first cascade."""

    async def test_db_hit_returns_db_rules(self, patch_beanie_scout_result):
        db_result = make_scout_result(
            is_verified=True,
            is_active=True,
            jurisdiction_key="MT:Gallatin:Bozeman",
            requirements=[make_scout_requirement(name="DB Rule")],
        )
        patch_beanie_scout_result["find_one"].return_value = db_result

        rules, matched = await async_lookup_requirements("MT:Gallatin:Bozeman", "MT")
        assert len(rules) == 1
        assert rules[0]["name"] == "DB Rule"
        assert matched == "MT:Gallatin:Bozeman"

    async def test_db_miss_falls_back_to_seed(self, patch_beanie_scout_result):
        patch_beanie_scout_result["find_one"].return_value = None

        rules, matched = await async_lookup_requirements(
            "MT:Lewis And Clark:Helena", "MT"
        )
        assert matched == "MT:Lewis And Clark:Helena"
        assert len(rules) == 7  # SEED_RULES for Helena

    async def test_cascade_city_to_county_in_db(self, patch_beanie_scout_result):
        county_result = make_scout_result(
            is_verified=True,
            is_active=True,
            jurisdiction_key="MT:Gallatin:",
            requirements=[make_scout_requirement(name="County DB Rule")],
        )
        # First call (city) returns None, second (county) returns result
        patch_beanie_scout_result["find_one"].side_effect = [None, county_result]

        rules, matched = await async_lookup_requirements("MT:Gallatin:Bozeman", "MT")
        assert matched == "MT:Gallatin:"
        assert rules[0]["name"] == "County DB Rule"

    async def test_cascade_all_miss_in_db_then_seed_state(
        self, patch_beanie_scout_result
    ):
        patch_beanie_scout_result["find_one"].return_value = None

        rules, matched = await async_lookup_requirements(
            "MT:Flathead:Kalispell", "MT"
        )
        assert matched == "MT::"  # Falls to SEED_RULES state level

    async def test_unverified_db_result_skipped(self, patch_beanie_scout_result):
        """find_one filters on is_active+is_verified, so mock returns None."""
        patch_beanie_scout_result["find_one"].return_value = None

        rules, matched = await async_lookup_requirements(
            "MT:Lewis And Clark:Helena", "MT"
        )
        assert matched == "MT:Lewis And Clark:Helena"
        assert len(rules) == 7  # Falls back to SEED_RULES

    async def test_completely_unknown_returns_empty(self, patch_beanie_scout_result):
        patch_beanie_scout_result["find_one"].return_value = None
        rules, matched = await async_lookup_requirements("NY:Kings:Brooklyn", "NY")
        assert rules == []
        assert matched == ""


class TestAsyncRunComplianceCheck:
    """Tests for compliance_engine.async_run_compliance_check()."""

    async def test_helena_with_seed_rules(
        self, helena_extracted_data, patch_beanie_scout_result
    ):
        patch_beanie_scout_result["find_one"].return_value = None
        report = await async_run_compliance_check(helena_extracted_data)
        assert report.overall_status == ComplianceOverallStatus.ACTION_NEEDED
        assert report.requirement_count == 7

    async def test_with_db_rules(self, patch_beanie_scout_result):
        db_result = make_scout_result(
            is_verified=True,
            is_active=True,
            jurisdiction_key="MT:Gallatin:Bozeman",
            requirements=[
                make_scout_requirement(
                    name="DB Only Rule",
                    status=RequirementStatus.REQUIRED,
                )
            ],
        )
        patch_beanie_scout_result["find_one"].return_value = db_result

        data = {
            "property_address": {
                "state_or_province": "MT",
                "county": "Gallatin",
                "city": "Bozeman",
            }
        }
        report = await async_run_compliance_check(data)
        assert report.requirement_count == 1
        names = [r.name for r in report.requirements]
        assert "DB Only Rule" in names

    async def test_missing_state_returns_unknown(
        self, no_state_data, patch_beanie_scout_result
    ):
        report = await async_run_compliance_check(no_state_data)
        assert report.overall_status == ComplianceOverallStatus.UNKNOWN_JURISDICTION

    async def test_fallback_note_present(self, patch_beanie_scout_result):
        patch_beanie_scout_result["find_one"].return_value = None
        data = {
            "property_address": {
                "state_or_province": "MT",
                "county": "Missoula",
                "city": "Lolo",
            }
        }
        report = await async_run_compliance_check(data)
        assert report.notes is not None


# =========================================================================
# C. API ENDPOINT TESTS — FastAPI + httpx AsyncClient
# =========================================================================


class TestScoutAPIEndpoints:
    """Tests for the 5 scout API endpoints in server.py."""

    @pytest.fixture
    def patched_app(self, mock_openai_client, patch_beanie_scout_result):
        """FastAPI app with DB + scout mocked out."""
        with (
            patch("server.init_db", new_callable=AsyncMock),
            patch("server.close_db", new_callable=AsyncMock),
            patch("scout._get_client", return_value=mock_openai_client),
        ):
            from server import app

            yield app

    async def test_post_scout_research(self, patched_app, patch_beanie_scout_result):
        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/scout/research",
                json={"state": "MT", "county": "Gallatin", "city": "Bozeman"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["jurisdiction_key"] == "MT:Gallatin:Bozeman"
        assert data["is_verified"] is False

    async def test_post_scout_research_missing_state(self, patched_app):
        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/scout/research", json={"state": ""})
        assert response.status_code == 400

    async def test_get_scout_results_empty(self, patched_app, patch_beanie_scout_result):
        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/scout/results")
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_scout_results_with_data(
        self, patched_app, patch_beanie_scout_result
    ):
        mock_results = [make_scout_result()]
        patch_beanie_scout_result["find"].return_value.sort.return_value.to_list = (
            AsyncMock(return_value=mock_results)
        )
        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/scout/results")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["jurisdiction_key"] == "MT:Gallatin:Bozeman"

    async def test_get_scout_result_by_id(
        self, patched_app, patch_beanie_scout_result
    ):
        mock_result = make_scout_result()
        patch_beanie_scout_result["get"].return_value = mock_result

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(f"/api/scout/results/{MOCK_OBJECT_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data["jurisdiction_key"] == "MT:Gallatin:Bozeman"

    async def test_get_scout_result_not_found(
        self, patched_app, patch_beanie_scout_result
    ):
        patch_beanie_scout_result["get"].side_effect = Exception("not found")
        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/scout/results/000000000000000000000000")
        assert response.status_code == 404

    async def test_put_verify_result(self, patched_app, patch_beanie_scout_result):
        mock_result = make_scout_result()
        patch_beanie_scout_result["get"].return_value = mock_result

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.put(
                f"/api/scout/results/{MOCK_OBJECT_ID}/verify",
                params={"verified_by": "test_user"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["is_verified"] is True
        assert data["is_active"] is True
        assert data["verified_by"] == "test_user"
        patch_beanie_scout_result["save"].assert_called_once()

    async def test_put_reject_result(self, patched_app, patch_beanie_scout_result):
        mock_result = make_scout_result(notes="Original note")
        patch_beanie_scout_result["get"].return_value = mock_result

        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.put(
                f"/api/scout/results/{MOCK_OBJECT_ID}/reject"
            )
        assert response.status_code == 200
        data = response.json()
        assert data["is_verified"] is False
        assert data["is_active"] is False
        assert data["status"] == "rejected"

    async def test_standalone_compliance_check_endpoint(
        self, patched_app, patch_beanie_scout_result
    ):
        """GET /api/compliance-check uses async_run_compliance_check."""
        patch_beanie_scout_result["find_one"].return_value = None
        transport = ASGITransport(app=patched_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/compliance-check",
                params={
                    "state": "MT",
                    "county": "Lewis And Clark",
                    "city": "Helena",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["jurisdiction_key"] == "MT:Lewis And Clark:Helena"
        assert data["overall_status"] == "ACTION_NEEDED"


# =========================================================================
# D. SCOUT MODEL VALIDATION TESTS
# =========================================================================


class TestScoutModels:
    """Tests for ScoutRequirement and ScoutResult model validation."""

    def test_scout_requirement_rejects_confidence_above_1(self):
        with pytest.raises(Exception):
            ScoutRequirement(
                name="Test",
                category=RequirementCategory.FORM,
                description="Test",
                confidence=1.5,
            )

    def test_scout_requirement_rejects_confidence_below_0(self):
        with pytest.raises(Exception):
            ScoutRequirement(
                name="Test",
                category=RequirementCategory.FORM,
                description="Test",
                confidence=-0.1,
            )

    def test_scout_result_collection_name(self):
        assert ScoutResult.Settings.name == "compliance_rules"

    def test_scout_result_defaults(self):
        result = ScoutResult.model_construct(
            state="MT",
            jurisdiction_key="MT::",
            jurisdiction_type="state",
        )
        assert result.is_verified is False
        assert result.is_active is False
        assert result.source == "ai_scout"
