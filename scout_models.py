"""Beanie document models for AI Scout compliance research results.

ScoutResult lives in the `compliance_rules` MongoDB collection.  Each document
represents one research run for a single jurisdiction — a list of proposed
compliance requirements discovered by GPT-4o, each with a confidence score.

Requirements start as unverified (is_verified=False, is_active=False).  A human
reviews via the admin API and flips is_verified + is_active to make them live.
The compliance engine's async_lookup_requirements() then picks them up
automatically during extraction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from beanie import Document
from pydantic import BaseModel, Field

from schemas import RequirementCategory, RequirementStatus


# ---------------------------------------------------------------------------
# Embedded sub-document
# ---------------------------------------------------------------------------


class ScoutRequirement(BaseModel):
    """Single researched compliance requirement — embeds inside ScoutResult."""

    name: str = Field(description="Requirement name (e.g., 'Connect on Sale')")
    code: Optional[str] = Field(default=None, description="Official code or form number")
    category: RequirementCategory = Field(description="Requirement category")
    description: str = Field(description="What this requirement entails")
    authority: Optional[str] = Field(default=None, description="Issuing authority")
    fee: Optional[str] = Field(default=None, description="Associated fee")
    url: Optional[str] = Field(default=None, description="Reference URL")
    status: RequirementStatus = Field(default=RequirementStatus.REQUIRED)
    notes: Optional[str] = Field(default=None, description="Additional context")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Verification confidence (0.0–1.0)",
    )
    source_reasoning: Optional[str] = Field(
        default=None,
        description="LLM's reasoning for why this requirement exists",
    )


# ---------------------------------------------------------------------------
# Top-level collection document
# ---------------------------------------------------------------------------


class ScoutResult(Document):
    """One AI Scout research run for a jurisdiction.

    Stored in the `compliance_rules` collection.  Each document holds
    the full list of proposed requirements for a single jurisdiction
    key (state:county:city).
    """

    # Jurisdiction identity
    state: str = Field(description="State abbreviation (e.g., 'MT')")
    county: Optional[str] = Field(default=None, description="County name")
    city: Optional[str] = Field(default=None, description="City name")
    jurisdiction_key: str = Field(
        description="Normalized key (e.g., 'MT:Gallatin:Bozeman')"
    )
    jurisdiction_type: str = Field(
        description="'city', 'county', or 'state'"
    )

    # Requirements
    requirements: List[ScoutRequirement] = Field(default_factory=list)

    # Metadata
    source: str = Field(default="ai_scout")
    is_verified: bool = Field(
        default=False,
        description="Human has reviewed and approved these requirements",
    )
    is_active: bool = Field(
        default=False,
        description="Active in the compliance engine (requires verification)",
    )
    model_used: str = Field(default="gpt-4o")
    research_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    verification_timestamp: Optional[datetime] = Field(default=None)
    verified_by: Optional[str] = Field(
        default=None,
        description="User who approved this result",
    )
    notes: Optional[str] = Field(default=None)

    class Settings:
        name = "compliance_rules"
        indexes = [
            [("jurisdiction_key", 1)],
            [("state", 1), ("is_active", 1)],
            [("is_verified", 1)],
        ]
