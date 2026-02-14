"""Shared fixtures for AI Scout test suite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from schemas import RequirementCategory, RequirementStatus
from scout_models import ScoutRequirement, ScoutResult


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MOCK_OBJECT_ID = ObjectId("507f1f77bcf86cd799439011")


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------


def make_scout_requirement(**overrides) -> ScoutRequirement:
    """Factory for a single ScoutRequirement with sensible MT defaults."""
    defaults = {
        "name": "Water Rights Form 608",
        "code": "DNRC-608",
        "category": RequirementCategory.FORM,
        "description": "Montana DNRC Form 608 — Ownership Update.",
        "authority": "Montana DNRC",
        "fee": "$100",
        "url": "https://dnrc.mt.gov/water-rights/",
        "status": RequirementStatus.REQUIRED,
        "notes": "Submit within 60 days of closing.",
        "confidence": 0.92,
        "source_reasoning": "MCA 85-2-424 requires ownership updates.",
    }
    defaults.update(overrides)
    return ScoutRequirement(**defaults)


def make_scout_result(**overrides) -> ScoutResult:
    """Factory for a ScoutResult document (defaults to Bozeman, MT)."""
    defaults = {
        "id": MOCK_OBJECT_ID,
        "state": "MT",
        "county": "Gallatin",
        "city": "Bozeman",
        "jurisdiction_key": "MT:Gallatin:Bozeman",
        "jurisdiction_type": "city",
        "requirements": [make_scout_requirement()],
        "source": "ai_scout",
        "is_verified": False,
        "is_active": False,
        "model_used": "gpt-4o",
        "research_timestamp": datetime(2026, 2, 9, 12, 0, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return ScoutResult.model_construct(**defaults)


# ---------------------------------------------------------------------------
# Mock OpenAI response builders
# ---------------------------------------------------------------------------


def make_openai_response(content_dict: dict) -> MagicMock:
    """Build a mock that looks like an OpenAI ChatCompletion response."""
    msg = MagicMock()
    msg.content = json.dumps(content_dict)
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture
def mock_research_response():
    """Mock OpenAI response for the research pass — 2 proposed requirements."""
    return make_openai_response({
        "requirements": [
            {
                "name": "Water Rights Form 608",
                "code": "DNRC-608",
                "category": "FORM",
                "description": "Ownership update for water rights.",
                "authority": "Montana DNRC",
                "fee": "$100",
                "url": "https://dnrc.mt.gov/water-rights/",
                "status": "REQUIRED",
                "notes": "Submit within 60 days.",
                "source_reasoning": "MCA 85-2-424",
            },
            {
                "name": "Realty Transfer Certificate",
                "code": "RTC",
                "category": "CERTIFICATE",
                "description": "Filed with county clerk at closing.",
                "authority": "Montana DOR",
                "fee": None,
                "url": None,
                "status": "REQUIRED",
                "notes": None,
                "source_reasoning": "Required by Montana DOR.",
            },
        ]
    })


@pytest.fixture
def mock_verify_response():
    """Mock OpenAI response for the verify pass — 1 verified, 1 removed."""
    return make_openai_response({
        "verified_requirements": [
            {
                "name": "Water Rights Form 608",
                "code": "DNRC-608",
                "category": "FORM",
                "description": "Ownership update for water rights.",
                "authority": "Montana DNRC",
                "fee": "$100",
                "url": "https://dnrc.mt.gov/water-rights/",
                "status": "REQUIRED",
                "notes": "Submit within 60 days.",
                "source_reasoning": "MCA 85-2-424",
                "confidence": 0.95,
                "verification_notes": "Confirmed via Montana statutes.",
            },
        ],
        "removed": [
            {
                "name": "Realty Transfer Certificate",
                "reason": "Confidence below threshold.",
            },
        ],
    })


@pytest.fixture
def mock_openai_client(mock_research_response, mock_verify_response):
    """AsyncMock OpenAI client that returns research then verify responses."""
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[mock_research_response, mock_verify_response]
    )
    return client


# ---------------------------------------------------------------------------
# Beanie mock patches
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_beanie_scout_result():
    """Patch all ScoutResult DB operations to be no-ops / controllable mocks.

    Patches:
    - Document.insert / Document.save (instance methods on base class)
    - ScoutResult.find_one / find / get (classmethods)
    - ScoutResult.get_settings (to avoid CollectionWasNotInitialized on construction)
    """
    from beanie import Document

    mock_insert = AsyncMock()
    mock_save = AsyncMock()
    mock_find_one = AsyncMock(return_value=None)
    mock_find = MagicMock()
    mock_get = AsyncMock(return_value=None)

    # Make find().sort().to_list() chain work
    mock_find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])

    # Mock get_settings to avoid CollectionWasNotInitialized when constructing ScoutResult
    mock_settings = MagicMock()
    mock_settings.motor_collection = MagicMock()

    with (
        patch.object(Document, "insert", mock_insert),
        patch.object(Document, "save", mock_save),
        patch.object(ScoutResult, "find_one", mock_find_one),
        patch.object(ScoutResult, "find", mock_find),
        patch.object(ScoutResult, "get", mock_get),
        patch.object(ScoutResult, "get_settings", return_value=mock_settings),
    ):
        yield {
            "insert": mock_insert,
            "save": mock_save,
            "find_one": mock_find_one,
            "find": mock_find,
            "get": mock_get,
        }


# ---------------------------------------------------------------------------
# Extracted data fixtures (mimic Dotloop extraction output)
# ---------------------------------------------------------------------------


@pytest.fixture
def helena_extracted_data():
    """Extracted data for Helena, MT (matches SEED_RULES)."""
    return {
        "property_address": {
            "state_or_province": "MT",
            "county": "Lewis And Clark",
            "city": "Helena",
        }
    }


@pytest.fixture
def missoula_extracted_data():
    """Extracted data for Missoula City, MT (matches SEED_RULES)."""
    return {
        "property_address": {
            "state_or_province": "MT",
            "county": "Missoula",
            "city": "Missoula",
        }
    }


@pytest.fixture
def unknown_jurisdiction_data():
    """Extracted data for a jurisdiction not in SEED_RULES or MongoDB."""
    return {
        "property_address": {
            "state_or_province": "NY",
            "county": "Kings",
            "city": "Brooklyn",
        }
    }


@pytest.fixture
def no_state_data():
    """Extracted data missing the state field."""
    return {
        "property_address": {
            "state_or_province": "",
            "county": "",
            "city": "",
        }
    }
