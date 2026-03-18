"""Beanie ODM document models and MongoDB initialization for D.E.S."""

import os
from datetime import datetime, timezone
from typing import List, Literal, Optional

from beanie import Document, Indexed, init_beanie
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pymongo import AsyncMongoClient

from schemas import (
    AgentProfile,
    BuyerProfile,
    ComplianceReport,
    DocumentRequirement,
    DotloopSyncStatus,
    LoanOfficerProfile,
    PIIReport,
    SellerProfile,
    TransactionParticipant,
    TransactionStatus,
    InvitationStatus,
    UserDocumentType,
    UserType,
    VerificationCitation,
    DotloopPropertyAddress,
    ParticipantRole,
)
from scout_models import ScoutResult

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB", "des")


# ---------------------------------------------------------------------------
# Onboarding constants
# ---------------------------------------------------------------------------

VALID_STEP_IDS = ["welcome", "profile", "documents", "extraction", "complete"]


# ---------------------------------------------------------------------------
# Embedded Models (subdocuments — not standalone collections)
# ---------------------------------------------------------------------------


class OnboardingStepStatus(BaseModel):
    """Status of a single onboarding step (embedded in UserProfile)."""

    step_id: str
    status: Literal["completed", "skipped", "pending"] = "pending"
    completed_at: Optional[str] = None


class ExtractionRecord(BaseModel):
    """Single extraction run, embedded inside a DocumentRecord."""

    engine: str = "openai"
    model_used: str = "docextract-vision-v1"
    mode: str = "real_estate"
    extracted_data: Optional[dict] = None
    dotloop_api_payload: Optional[dict] = None
    docusign_api_payload: Optional[dict] = None
    validation_success: bool = True
    validation_errors: Optional[List[str]] = None
    overall_confidence: float = 0.0
    pages_processed: int = 0
    extraction_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # API usage tracking
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0

    # User-edited field overrides — take precedence over extracted_data in the comparison view
    field_overrides: dict = Field(default_factory=dict)

    # Embedded children
    citations: List[VerificationCitation] = Field(default_factory=list)
    pii_report: Optional[PIIReport] = None
    compliance_report: Optional[ComplianceReport] = None
    property_enrichment: Optional[dict] = None


# ---------------------------------------------------------------------------
# Top-Level Collection Documents
# ---------------------------------------------------------------------------


class OAuthTokenSet(BaseModel):
    """Embedded OAuth credentials for Dotloop or DocuSign."""

    access_token: str
    refresh_token: Optional[str] = None
    account_id: Optional[str] = None
    profile_id: Optional[int] = None
    expires_at: Optional[datetime] = None


class UserProfile(Document):
    """A registered user with multi-role support.

    Replaces the old UserRecord. A single user can hold multiple roles
    (e.g., an agent who is also a buyer) via the user_types list and
    corresponding role-specific sub-documents.
    """

    # Identity
    clerk_user_id: Optional[str] = None  # None for magic-link-only users
    email: Indexed(str, unique=True)  # type: ignore[valid-type]
    name: str = ""
    phone: Optional[str] = None
    address: Optional[dict] = None  # {street, city, state, zip}

    # Multi-role support
    user_types: List[UserType] = Field(default_factory=list)

    # Role-specific sub-documents (populated when user has that role)
    agent_profile: Optional[AgentProfile] = None
    buyer_profile: Optional[BuyerProfile] = None
    seller_profile: Optional[SellerProfile] = None
    loan_officer_profile: Optional[LoanOfficerProfile] = None

    # OAuth tokens
    dotloop_tokens: Optional[OAuthTokenSet] = None
    docusign_tokens: Optional[OAuthTokenSet] = None

    # Magic link support
    magic_link_token: Optional[str] = None
    magic_link_expires: Optional[datetime] = None
    has_clerk_account: bool = False

    # Organization (legacy compat + brokerage linking)
    org_id: Optional[str] = None
    org_name: Optional[str] = None
    role: str = "agent"  # Legacy admin|agent|viewer for brokerage admin checks

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None

    # Onboarding wizard state (v1 fields — kept for backward compat)
    onboarding_completed: bool = False
    onboarding_completed_at: Optional[datetime] = None
    onboarding_skipped_steps: List[str] = Field(default_factory=list)

    # Onboarding v2 fields
    onboarding_version: int = 1  # 1=old wizard, 2=new panel
    onboarding_step_statuses: List[OnboardingStepStatus] = Field(default_factory=list)
    onboarding_current_step: int = 0  # Resume index

    class Settings:
        name = "user_profiles"
        indexes = [
            "clerk_user_id",
            "org_id",
        ]


# Alias for backward compatibility — existing code imports UserRecord
UserRecord = UserProfile


class BrokerageDefaultSettings(BaseModel):
    """Brokerage-wide defaults applied to new transactions."""

    default_commission_rate: Optional[str] = None
    preferred_title_company: Optional[str] = None
    preferred_escrow_company: Optional[str] = None
    default_earnest_money_pct: Optional[float] = None
    required_insurance_providers: List[str] = Field(default_factory=list)


class BrokerageProfile(Document):
    """Brokerage-level compliance profile — one per Clerk Organization."""

    org_id: str
    name: str
    license_number: Optional[str] = None
    license_state: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    active_markets: List[str] = Field(default_factory=list)

    custom_requirements: List[dict] = Field(default_factory=list)

    defaults: Optional[BrokerageDefaultSettings] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "brokerage_profiles"
        indexes = ["org_id"]


class DocumentRecord(Document):
    """A processed PDF document — top-level MongoDB collection."""

    filename: str
    file_path: Optional[str] = None
    source: str = "upload"  # upload | dotloop | docusign
    source_id: Optional[str] = None
    mode: str = "real_estate"
    page_count: int = 0
    file_size_bytes: int = 0
    file_hash: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: Optional[str] = None
    org_id: Optional[str] = None

    extractions: List[ExtractionRecord] = Field(default_factory=list)

    class Settings:
        name = "documents"


# ---------------------------------------------------------------------------
# New Collections: Transaction, UserDocument, TransactionDocument
# ---------------------------------------------------------------------------


class Transaction(Document):
    """A real estate transaction linking participants, documents, and compliance."""

    name: str  # e.g., "123 Main St Purchase"
    transaction_type: str = "purchase"
    status: TransactionStatus = TransactionStatus.DRAFT

    # Property
    property_address: Optional[DotloopPropertyAddress] = None
    mls_number: Optional[str] = None

    # Participants
    participants: List[TransactionParticipant] = Field(default_factory=list)

    # Financial summary (auto-filled from extraction/profiles)
    purchase_price: Optional[float] = None
    earnest_money: Optional[float] = None
    closing_date: Optional[datetime] = None

    # Document requirements (default template + agent overrides)
    document_requirements: List[DocumentRequirement] = Field(default_factory=list)

    # Linked extractions
    extraction_ids: List[str] = Field(default_factory=list)

    # Agent perspective — "buyer" or "seller"
    agent_side: Optional[str] = None  # "buyer" | "seller"

    # Dotloop loop linked to this transaction
    dotloop_loop_id: Optional[str] = None
    dotloop_sync_status: DotloopSyncStatus = DotloopSyncStatus.NEVER
    dotloop_last_synced_at: Optional[datetime] = None
    dotloop_last_remote_updated_at: Optional[datetime] = None
    dotloop_sync_error: Optional[str] = None

    # Compliance
    compliance_report_id: Optional[str] = None

    # Metadata
    created_by: str  # UserProfile document ID
    org_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "transactions"
        indexes = [
            "participants.user_id",
            "status",
            "created_by",
            "dotloop_loop_id",
        ]


class TransactionInvitation(Document):
    """A first-class invitation tied to a transaction."""

    transaction_id: str
    invitee_user_id: Optional[str] = None
    email: str
    name: Optional[str] = None
    role: ParticipantRole
    created_by: str
    token_hash: Optional[str] = None
    signed_token: Optional[str] = None
    status: InvitationStatus = InvitationStatus.CREATED
    expires_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    provider: Optional[str] = None
    provider_message_id: Optional[str] = None
    last_error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "transaction_invitations"
        indexes = [
            "transaction_id",
            "invitee_user_id",
            "email",
            "status",
            "token_hash",
        ]


class UserDocument(Document):
    """A document uploaded to a user's profile (persists across transactions)."""

    user_id: str  # UserProfile document ID
    doc_type: UserDocumentType
    filename: str
    file_path: str
    file_hash: str
    file_size_bytes: int = 0

    # Extraction results
    extraction_status: str = "pending"  # pending | processing | completed | failed
    extracted_data: Optional[dict] = None
    extraction_id: Optional[str] = None  # task ID for SSE streaming
    overall_confidence: Optional[float] = None
    citations: List[dict] = Field(default_factory=list)

    # PII detection
    pii_report: Optional[dict] = None

    # Metadata
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: Optional[str] = None

    class Settings:
        name = "user_documents"
        indexes = [
            "user_id",
            "doc_type",
            "file_hash",
        ]


class TransactionDocument(Document):
    """A document attached to a specific transaction."""

    transaction_id: str
    doc_type: str  # purchase_offer, addendum, etc.
    source: str = "upload"  # upload | dotloop | docusign | user_profile

    # Reference to user's profile document (if linked from there)
    source_user_document_id: Optional[str] = None

    # File info
    filename: str
    file_path: str
    file_hash: str

    # Link to existing extraction pipeline
    document_record_id: Optional[str] = None

    # If set, this document is scoped to a specific offer (extraction_id)
    offer_extraction_id: Optional[str] = None

    # Metadata
    uploaded_by: str  # UserProfile ID
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "transaction_documents"
        indexes = [
            "transaction_id",
            "doc_type",
        ]


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

_client: Optional[AsyncMongoClient] = None

ALL_DOCUMENT_MODELS = [
    DocumentRecord,
    UserProfile,
    ScoutResult,
    BrokerageProfile,
    Transaction,
    TransactionInvitation,
    UserDocument,
    TransactionDocument,
]


async def init_db():
    """Connect to MongoDB Atlas and register Beanie document models."""
    global _client
    import certifi

    _client = AsyncMongoClient(MONGODB_URI, tlsCAFile=certifi.where())
    await init_beanie(database=_client[DB_NAME], document_models=ALL_DOCUMENT_MODELS)


async def close_db():
    """Close the MongoDB connection."""
    global _client
    if _client:
        await _client.close()
        _client = None
