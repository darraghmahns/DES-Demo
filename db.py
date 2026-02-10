"""Beanie ODM document models and MongoDB initialization for D.E.S."""

import os
from datetime import datetime, timezone
from typing import List, Optional

from beanie import Document, init_beanie
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pymongo import AsyncMongoClient

from schemas import ComplianceReport, PIIReport, VerificationCitation
from scout_models import ScoutResult

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB", "des")


# ---------------------------------------------------------------------------
# Embedded Models (subdocuments — not standalone collections)
# ---------------------------------------------------------------------------


class ExtractionRecord(BaseModel):
    """Single extraction run, embedded inside a DocumentRecord."""

    engine: str = "openai"
    model_used: str = "docextract-vision-v1"
    mode: str = "real_estate"
    extracted_data: Optional[dict] = None
    dotloop_api_payload: Optional[dict] = None
    validation_success: bool = True
    validation_errors: Optional[List[str]] = None
    overall_confidence: float = 0.0
    pages_processed: int = 0
    extraction_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Embedded children (were separate tables in Postgres)
    citations: List[VerificationCitation] = Field(default_factory=list)
    pii_report: Optional[PIIReport] = None
    compliance_report: Optional[ComplianceReport] = None


# ---------------------------------------------------------------------------
# Top-Level Collection Documents
# ---------------------------------------------------------------------------


class DocumentRecord(Document):
    """A processed PDF document — top-level MongoDB collection."""

    filename: str
    source: str = "upload"  # upload | dotloop | docusign
    source_id: Optional[str] = None  # external ID (loop_id, envelope_id)
    mode: str = "real_estate"  # real_estate | gov
    page_count: int = 0
    file_size_bytes: int = 0
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    extractions: List[ExtractionRecord] = Field(default_factory=list)

    class Settings:
        name = "documents"


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

_client: Optional[AsyncMongoClient] = None


async def init_db():
    """Connect to MongoDB Atlas and register Beanie document models."""
    global _client
    _client = AsyncMongoClient(MONGODB_URI)
    await init_beanie(database=_client[DB_NAME], document_models=[DocumentRecord, ScoutResult])


async def close_db():
    """Close the MongoDB connection."""
    global _client
    if _client:
        await _client.close()
        _client = None
