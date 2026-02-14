"""AI Scout — LLM-powered compliance research for JACE.

Two-pass GPT-4o design mirroring extractor.py → verifier.py:
  1. Research Pass: discover compliance requirements for a jurisdiction
  2. Verify Pass: cross-check each requirement, filter hallucinations, score confidence

Usage:
    from scout import run_scout
    result = await run_scout("MT", county="Gallatin", city="Bozeman")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI

from compliance_engine import resolve_jurisdiction
from scout_models import ScoutRequirement, ScoutResult
from schemas import RequirementCategory, RequirementStatus

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_PROMPT = """You are an expert real estate compliance researcher specializing in US municipal, county, and state regulations for property transfers and sales.

Given a jurisdiction (state, county, city), identify ALL compliance requirements that apply to a standard residential real property sale or transfer in that jurisdiction.

For each requirement, provide:
- name: Short descriptive name (e.g., "9A Report", "Connect on Sale", "Transfer Disclosure Statement")
- code: Official code, form number, or statute reference (e.g., "MMC 13.04.020", "MCA 75-3-606") — null if unknown
- category: One of: FORM, INSPECTION, DISCLOSURE, CERTIFICATE, FEE
- description: What the requirement entails, when it applies, and who is responsible
- authority: Issuing/enforcing authority (e.g., "City of Missoula Public Works", "Montana DEQ")
- fee: Associated fee if known (e.g., "$225", "$100 (first right) + $20 each additional") — null if unknown
- url: Official reference URL — null if unknown
- status: One of: REQUIRED (always required), LIKELY_REQUIRED (required in most cases), NOT_REQUIRED, UNKNOWN
- notes: Additional context, exceptions, or caveats
- source_reasoning: Your reasoning for why this requirement exists and how you know about it (cite the specific statute, municipal code, or regulation)

Focus on:
1. Pre-sale disclosure requirements (seller disclosures, natural hazard, lead paint, radon)
2. Municipal forms and certificates (building reports, retrofit certificates, transfer certificates)
3. Required inspections (sewer, septic, well, radon, structural)
4. Transfer taxes and recording fees
5. State-level requirements that apply to all jurisdictions in the state
6. City-specific ordinances that distinguish this jurisdiction from others

CRITICAL RULES:
- Only include requirements you are confident actually exist. Do NOT fabricate requirements.
- Cite specific statute numbers, municipal code sections, or regulatory authority names.
- If a requirement is specific to the city (not the county or state), note that in the description.
- Include both local AND state-level requirements that apply.
- If you are uncertain about a requirement, include it but set status to "UNKNOWN".

You MUST return a JSON object with this structure:
{
  "requirements": [
    {
      "name": "...",
      "code": "...",
      "category": "FORM|INSPECTION|DISCLOSURE|CERTIFICATE|FEE",
      "description": "...",
      "authority": "...",
      "fee": "...",
      "url": "...",
      "status": "REQUIRED|LIKELY_REQUIRED|NOT_REQUIRED|UNKNOWN",
      "notes": "...",
      "source_reasoning": "..."
    }
  ]
}
"""

VERIFY_SYSTEM_PROMPT = """You are a compliance verification specialist. You are reviewing a list of proposed real estate compliance requirements for a specific US jurisdiction.

Your job is to VERIFY each requirement:
1. Is this a real requirement that actually exists for this jurisdiction?
2. Is the code/statute citation accurate?
3. Is the description correct?
4. Is the issuing authority correct?
5. Assign a confidence score (0.0–1.0) based on how certain you are this requirement is real and accurate.

Rules for scoring:
- 0.9–1.0: You are very confident this is a real, accurately described requirement
- 0.7–0.89: Likely real but some details may be imprecise
- 0.5–0.69: Possibly real but significant uncertainty
- Below 0.5: Likely fabricated or significantly inaccurate — REMOVE from the list

For each requirement, return the SAME fields plus:
- confidence: Your verification confidence (0.0–1.0)
- verification_notes: Brief explanation of your confidence assessment

REMOVE any requirement with confidence below 0.5. These are likely hallucinations.

You MUST return a JSON object with this structure:
{
  "verified_requirements": [
    {
      "name": "...",
      "code": "...",
      "category": "FORM|INSPECTION|DISCLOSURE|CERTIFICATE|FEE",
      "description": "...",
      "authority": "...",
      "fee": "...",
      "url": "...",
      "status": "REQUIRED|LIKELY_REQUIRED|NOT_REQUIRED|UNKNOWN",
      "notes": "...",
      "source_reasoning": "...",
      "confidence": 0.95,
      "verification_notes": "..."
    }
  ],
  "removed": [
    {
      "name": "...",
      "reason": "..."
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# Core research functions
# ---------------------------------------------------------------------------

def _get_client() -> AsyncOpenAI:
    """Create an AsyncOpenAI client using env config."""
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def research_jurisdiction(
    state: str,
    county: Optional[str] = None,
    city: Optional[str] = None,
    *,
    client: Optional[AsyncOpenAI] = None,
) -> list[dict]:
    """Research Pass: discover compliance requirements for a jurisdiction.

    Args:
        state: State abbreviation (e.g., "MT")
        county: County name (e.g., "Gallatin")
        city: City name (e.g., "Bozeman")
        client: Optional AsyncOpenAI client (created if not provided)

    Returns:
        List of raw requirement dicts from GPT-4o.
    """
    client = client or _get_client()

    # Build the jurisdiction description for the prompt
    parts = []
    if city:
        parts.append(f"City: {city}")
    if county:
        parts.append(f"County: {county}")
    parts.append(f"State: {state}")

    jurisdiction_desc = ", ".join(parts)

    user_prompt = (
        f"Research ALL real estate compliance requirements for a standard "
        f"residential property sale in the following jurisdiction:\n\n"
        f"{jurisdiction_desc}\n\n"
        f"Include both local and state-level requirements that apply. "
        f"Be thorough but only include requirements you are confident exist."
    )

    log.info("Scout research pass for: %s", jurisdiction_desc)

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,  # Low but not 0 — allows some creativity for research
        max_tokens=4096,
    )

    raw = json.loads(response.choices[0].message.content)
    requirements = raw.get("requirements", [])

    log.info(
        "Research pass found %d proposed requirements for %s",
        len(requirements),
        jurisdiction_desc,
    )

    return requirements


async def verify_requirements(
    state: str,
    proposed: list[dict],
    county: Optional[str] = None,
    city: Optional[str] = None,
    *,
    client: Optional[AsyncOpenAI] = None,
) -> tuple[list[dict], list[dict]]:
    """Verify Pass: cross-check proposed requirements, filter hallucinations.

    Args:
        state: State abbreviation
        proposed: List of requirement dicts from research pass
        county: County name
        city: City name
        client: Optional AsyncOpenAI client

    Returns:
        (verified_requirements, removed_requirements)
    """
    client = client or _get_client()

    parts = []
    if city:
        parts.append(f"City: {city}")
    if county:
        parts.append(f"County: {county}")
    parts.append(f"State: {state}")

    jurisdiction_desc = ", ".join(parts)

    user_prompt = (
        f"Verify the following proposed real estate compliance requirements "
        f"for: {jurisdiction_desc}\n\n"
        f"Proposed requirements:\n{json.dumps(proposed, indent=2)}\n\n"
        f"Cross-check each requirement. Remove any with confidence below 0.5."
    )

    log.info("Scout verify pass for: %s (%d proposed)", jurisdiction_desc, len(proposed))

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,  # Strict for verification
        max_tokens=4096,
    )

    raw = json.loads(response.choices[0].message.content)
    verified = raw.get("verified_requirements", [])
    removed = raw.get("removed", [])

    log.info(
        "Verify pass: %d verified, %d removed for %s",
        len(verified),
        len(removed),
        jurisdiction_desc,
    )

    return verified, removed


# ---------------------------------------------------------------------------
# Parse verified dicts → ScoutRequirement models
# ---------------------------------------------------------------------------

_CATEGORY_MAP = {v.value: v for v in RequirementCategory}
_STATUS_MAP = {v.value: v for v in RequirementStatus}


def _parse_requirement(raw: dict) -> Optional[ScoutRequirement]:
    """Parse a raw requirement dict into a ScoutRequirement model.

    Returns None if the dict is malformed.
    """
    try:
        # Normalize category and status strings
        cat_str = (raw.get("category") or "FORM").upper()
        status_str = (raw.get("status") or "REQUIRED").upper()

        return ScoutRequirement(
            name=raw["name"],
            code=raw.get("code"),
            category=_CATEGORY_MAP.get(cat_str, RequirementCategory.FORM),
            description=raw.get("description", ""),
            authority=raw.get("authority"),
            fee=raw.get("fee"),
            url=raw.get("url"),
            status=_STATUS_MAP.get(status_str, RequirementStatus.REQUIRED),
            notes=raw.get("notes"),
            confidence=float(raw.get("confidence", 0.0)),
            source_reasoning=raw.get("source_reasoning"),
        )
    except Exception as e:
        log.warning("Failed to parse requirement: %s — %s", raw.get("name", "?"), e)
        return None


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def run_scout(
    state: str,
    county: Optional[str] = None,
    city: Optional[str] = None,
    *,
    save_to_db: bool = True,
) -> ScoutResult:
    """Full AI Scout pipeline: research → verify → persist.

    Args:
        state: State abbreviation (e.g., "MT")
        county: County name (e.g., "Gallatin")
        city: City name (e.g., "Bozeman")
        save_to_db: Whether to persist the result to MongoDB

    Returns:
        ScoutResult document (saved to DB if save_to_db=True)
    """
    client = _get_client()

    # 1. Resolve jurisdiction
    key, display, jtype = resolve_jurisdiction(state, county, city)
    log.info("Scout starting for: %s (%s)", display, key)

    # 2. Research pass
    proposed = await research_jurisdiction(
        state, county, city, client=client,
    )

    if not proposed:
        log.warning("Research pass returned 0 requirements for %s", display)

    # 3. Verify pass
    verified, removed = await verify_requirements(
        state, proposed, county, city, client=client,
    )

    # 4. Parse into models
    requirements: list[ScoutRequirement] = []
    for raw in verified:
        req = _parse_requirement(raw)
        if req is not None:
            requirements.append(req)

    # 5. Build ScoutResult
    result = ScoutResult(
        state=state.upper().strip(),
        county=(county or "").strip().title() or None,
        city=(city or "").strip().title() or None,
        jurisdiction_key=key,
        jurisdiction_type=jtype,
        requirements=requirements,
        source="ai_scout",
        is_verified=False,
        is_active=False,
        model_used="gpt-4o",
        research_timestamp=datetime.now(timezone.utc),
        notes=f"AI Scout discovered {len(requirements)} requirements "
              f"({len(removed)} removed during verification).",
    )

    # 6. Persist
    if save_to_db:
        await result.insert()
        log.info(
            "Scout result saved to DB: %s — %d requirements (id=%s)",
            display,
            len(requirements),
            result.id,
        )

    return result
