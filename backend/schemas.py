"""Pydantic models for document extraction — Dotloop, FOIA, PII, and Verification schemas."""

from pydantic import BaseModel, Field, computed_field
from typing import Optional, List
from enum import Enum


# =============================================================================
# Enums
# =============================================================================

class ParticipantRole(str, Enum):
    BUYER = "BUYER"
    SELLER = "SELLER"
    LISTING_AGENT = "LISTING_AGENT"
    BUYING_AGENT = "BUYING_AGENT"
    LISTING_BROKER = "LISTING_BROKER"
    BUYING_BROKER = "BUYING_BROKER"
    ESCROW_TITLE_REP = "ESCROW_TITLE_REP"
    LOAN_OFFICER = "LOAN_OFFICER"
    APPRAISER = "APPRAISER"
    INSPECTOR = "INSPECTOR"
    TRANSACTION_COORDINATOR = "TRANSACTION_COORDINATOR"
    OTHER = "OTHER"


class PIIType(str, Enum):
    SSN = "SSN"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    ADDRESS = "ADDRESS"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    DRIVERS_LICENSE = "DRIVERS_LICENSE"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    CREDIT_CARD = "CREDIT_CARD"


class PIISeverity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RequirementCategory(str, Enum):
    FORM = "FORM"
    INSPECTION = "INSPECTION"
    DISCLOSURE = "DISCLOSURE"
    CERTIFICATE = "CERTIFICATE"
    FEE = "FEE"


class RequirementStatus(str, Enum):
    REQUIRED = "REQUIRED"
    LIKELY_REQUIRED = "LIKELY_REQUIRED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNKNOWN = "UNKNOWN"


class ComplianceOverallStatus(str, Enum):
    PASS = "PASS"
    ACTION_NEEDED = "ACTION_NEEDED"
    UNKNOWN_JURISDICTION = "UNKNOWN_JURISDICTION"


class RequirementSource(str, Enum):
    """Where a compliance requirement originated."""
    JURISDICTION = "JURISDICTION"  # From SEED_RULES or AI Scout
    BROKERAGE = "BROKERAGE"  # From BrokerageProfile.custom_requirements
    AI_SCOUT = "AI_SCOUT"  # From ScoutResult (future)


# =============================================================================
# Dotloop-Compatible Models (Real Estate)
# =============================================================================

class DotloopPropertyAddress(BaseModel):
    """Maps to Dotloop Loop Details -> 'Property Address' section."""
    street_number: str = Field(description="Street number (e.g., '2100')")
    street_name: str = Field(description="Street name (e.g., 'Waterview Dr')")
    unit_number: Optional[str] = Field(default=None, description="Unit/apt number")
    city: str = Field(description="City name")
    state_or_province: str = Field(description="State abbreviation (e.g., 'MT')")
    postal_code: str = Field(description="ZIP code (e.g., '59101')")
    country: str = Field(default="US", description="Country code")
    county: Optional[str] = Field(default=None, description="County name")
    mls_number: Optional[str] = Field(default=None, description="MLS listing number")
    parcel_tax_id: Optional[str] = Field(default=None, description="Parcel/Tax ID")


class DotloopFinancials(BaseModel):
    """Maps to Dotloop Loop Details -> 'Financials' section."""
    purchase_price: float = Field(description="Purchase/sale price in USD")
    earnest_money_amount: Optional[float] = Field(default=None, description="Earnest money deposit in USD")
    earnest_money_held_by: Optional[str] = Field(default=None, description="Entity holding earnest money")
    sale_commission_rate: Optional[str] = Field(default=None, description="Commission rate (e.g., '6%')")
    sale_commission_total: Optional[float] = Field(default=None, description="Total commission in USD")


class DotloopParticipant(BaseModel):
    """Maps to Dotloop Loop Participant."""
    full_name: str = Field(description="Full legal name")
    role: ParticipantRole = Field(description="Dotloop participant role")
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    company_name: Optional[str] = Field(default=None)


class DotloopContractDates(BaseModel):
    """Maps to Dotloop Loop Details -> 'Contract Dates' section."""
    contract_agreement_date: Optional[str] = Field(default=None, description="Date contract was agreed upon")
    closing_date: Optional[str] = Field(default=None, description="Anticipated closing date")
    offer_date: Optional[str] = Field(default=None, description="Date offer was made")
    offer_expiration_date: Optional[str] = Field(default=None, description="Offer expiration date")
    inspection_date: Optional[str] = Field(default=None, description="Inspection deadline")


class DotloopLoopDetails(BaseModel):
    """Complete Dotloop Loop Details — the final output for real_estate mode.

    Matches Dotloop's sections-based API structure.
    """
    loop_name: str = Field(description="Loop name, typically 'Buyer Name, Property Address'")
    transaction_type: str = Field(default="PURCHASE_OFFER")
    transaction_status: str = Field(default="PRE_OFFER")
    property_address: DotloopPropertyAddress
    financials: DotloopFinancials
    contract_dates: DotloopContractDates
    participants: List[DotloopParticipant]

    def to_dotloop_api_format(self) -> dict:
        """Serialize to Dotloop's actual API section format.

        Field keys match dotloop_mapping.py from the doc_intel project.
        Uses getattr() throughout so model_construct() partial objects work.
        """
        addr = self.property_address
        fin = self.financials
        dates = self.contract_dates

        return {
            "name": getattr(self, "loop_name", "") or "Untitled Loop",
            "transactionType": getattr(self, "transaction_type", "PURCHASE_OFFER"),
            "status": getattr(self, "transaction_status", "PRE_OFFER"),
            "loopDetails": {
                "Property Address": {
                    "Country": getattr(addr, "country", "US") or "US",
                    "Street Number": getattr(addr, "street_number", "") or "",
                    "Street Name": getattr(addr, "street_name", "") or "",
                    "Unit Number": getattr(addr, "unit_number", "") or "",
                    "City": getattr(addr, "city", "") or "",
                    "State/Prov": getattr(addr, "state_or_province", "") or "",
                    "Zip/Postal Code": getattr(addr, "postal_code", "") or "",
                    "County": getattr(addr, "county", "") or "",
                    "MLS Number": getattr(addr, "mls_number", "") or "",
                    "Parcel/Tax ID": getattr(addr, "parcel_tax_id", "") or "",
                } if addr else {},
                "Financials": {
                    "Purchase/Sale Price": str(getattr(fin, "purchase_price", "") or ""),
                    "Earnest Money Amount": str(getattr(fin, "earnest_money_amount", "") or ""),
                    "Earnest Money Held By": getattr(fin, "earnest_money_held_by", "") or "",
                    "Sale Commission Rate": getattr(fin, "sale_commission_rate", "") or "",
                    "Sale Commission Total": str(getattr(fin, "sale_commission_total", "") or ""),
                } if fin else {},
                "Contract Dates": {
                    "Contract Agreement Date": getattr(dates, "contract_agreement_date", "") or "",
                    "Closing Date": getattr(dates, "closing_date", "") or "",
                } if dates else {},
            },
            "participants": [
                {
                    "fullName": getattr(p, "full_name", "") or "",
                    "role": p.role.value if hasattr(getattr(p, "role", None), "value") else str(getattr(p, "role", "OTHER") or "OTHER"),
                    "email": getattr(p, "email", "") or "",
                    "Phone": getattr(p, "phone", "") or "",
                    "Company Name": getattr(p, "company_name", "") or "",
                }
                for p in (self.participants or [])
            ],
        }

    def to_docusign_api_format(self) -> dict:
        """Serialize to DocuSign eSignature API format.

        Returns a dict suitable for creating/updating a DocuSign envelope:
        - emailSubject: Descriptive subject line
        - customFields: Property, financial, and contract data as text custom fields
        - recipients: Signers (buyers/sellers) and carbon copies (agents/brokers)
        """
        addr = self.property_address
        fin = self.financials
        dates = self.contract_dates

        # Build a human-readable address string
        street = f"{getattr(addr, 'street_number', '')} {getattr(addr, 'street_name', '')}".strip()
        unit = getattr(addr, "unit_number", "") or ""
        if unit:
            street = f"{street} #{unit}"
        city = getattr(addr, "city", "") or ""
        state = getattr(addr, "state_or_province", "") or ""
        zipcode = getattr(addr, "postal_code", "") or ""
        full_address = f"{street}, {city}, {state} {zipcode}".strip(", ")

        email_subject = f"Purchase Agreement: {full_address}" if full_address else f"Purchase Agreement: {getattr(self, 'loop_name', 'Untitled')}"

        # Custom fields carry property/financial/contract data
        text_custom_fields = [
            {"name": "PropertyAddress", "value": full_address, "show": "true"},
            {"name": "City", "value": city, "show": "true"},
            {"name": "State", "value": state, "show": "true"},
            {"name": "ZipCode", "value": zipcode, "show": "true"},
            {"name": "County", "value": getattr(addr, "county", "") or "", "show": "true"},
            {"name": "MLSNumber", "value": getattr(addr, "mls_number", "") or "", "show": "true"},
            {"name": "ParcelTaxID", "value": getattr(addr, "parcel_tax_id", "") or "", "show": "true"},
            {"name": "PurchasePrice", "value": str(getattr(fin, "purchase_price", "") or ""), "show": "true"},
            {"name": "EarnestMoney", "value": str(getattr(fin, "earnest_money_amount", "") or ""), "show": "true"},
            {"name": "EarnestMoneyHeldBy", "value": getattr(fin, "earnest_money_held_by", "") or "", "show": "true"},
            {"name": "CommissionRate", "value": getattr(fin, "sale_commission_rate", "") or "", "show": "true"},
            {"name": "ClosingDate", "value": getattr(dates, "closing_date", "") or "", "show": "true"},
            {"name": "ContractDate", "value": getattr(dates, "contract_agreement_date", "") or "", "show": "true"},
            {"name": "TransactionType", "value": getattr(self, "transaction_type", "PURCHASE_OFFER"), "show": "true"},
        ]

        # Recipients: signers are buyers/sellers, CCs are agents/brokers
        signer_roles = {"BUYER", "SELLER"}
        signers = []
        carbon_copies = []
        recipient_id = 1

        for p in (self.participants or []):
            role_val = p.role.value if hasattr(getattr(p, "role", None), "value") else str(getattr(p, "role", "OTHER") or "OTHER")
            name = getattr(p, "full_name", "") or ""
            email = getattr(p, "email", "") or ""

            recipient = {
                "name": name,
                "email": email,
                "recipientId": str(recipient_id),
                "routingOrder": str(recipient_id),
            }
            recipient_id += 1

            if role_val in signer_roles and email:
                signers.append(recipient)
            elif email:
                carbon_copies.append(recipient)

        result: dict = {
            "emailSubject": email_subject,
            "customFields": {
                "textCustomFields": text_custom_fields,
            },
        }

        if signers or carbon_copies:
            result["recipients"] = {}
            if signers:
                result["recipients"]["signers"] = signers
            if carbon_copies:
                result["recipients"]["carbonCopies"] = carbon_copies

        return result

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "loop_name": "Daniel R. Whitfield, 4738 Ridgeline Ct, Helena, MT 59601",
                    "transaction_type": "PURCHASE_OFFER",
                    "transaction_status": "PRE_OFFER",
                    "property_address": {
                        "street_number": "4738",
                        "street_name": "Ridgeline Ct",
                        "city": "Helena",
                        "state_or_province": "MT",
                        "postal_code": "59601",
                        "country": "US",
                    },
                    "financials": {
                        "purchase_price": 612500.00,
                        "earnest_money_amount": 15000.00,
                        "earnest_money_held_by": "Montana Title & Escrow",
                    },
                    "contract_dates": {
                        "closing_date": "04/18/2025",
                        "offer_date": "03/04/2025",
                    },
                    "participants": [
                        {"full_name": "Daniel R. Whitfield", "role": "BUYER"},
                        {"full_name": "Gregory T. Navarro", "role": "SELLER"},
                    ],
                }
            ]
        }
    }


# =============================================================================
# FOIA.gov v1.1.0 Models (Government)
# =============================================================================

class FOIARequesterInfo(BaseModel):
    """Requester information matching FOIA.gov API Spec v1.1.0 field names."""
    first_name: str = Field(description="Requester first name")
    last_name: str = Field(description="Requester last name")
    email: Optional[str] = Field(default=None, description="Requester email address")
    phone: Optional[str] = Field(default=None, description="Requester phone number")
    address_street: Optional[str] = Field(default=None, description="Mailing street address")
    address_city: Optional[str] = Field(default=None, description="Mailing city")
    address_state: Optional[str] = Field(default=None, description="Mailing state abbreviation")
    address_zip: Optional[str] = Field(default=None, description="Mailing ZIP code")
    organization: Optional[str] = Field(default=None, description="Organization or company affiliation")


class FOIARequest(BaseModel):
    """FOIA request data matching FOIA.gov API Spec v1.1.0."""
    requester: FOIARequesterInfo = Field(description="Requester contact information")
    request_description: str = Field(description="Description of records being requested")
    request_category: Optional[str] = Field(
        default=None,
        description="Category: commercial, educational, media, other",
    )
    agency: str = Field(description="Target federal agency")
    agency_component_name: Optional[str] = Field(default=None, description="Specific office or component")
    fee_amount_willing: Optional[float] = Field(default=None, description="Max fee willing to pay (USD)")
    fee_waiver: bool = Field(default=False, description="Fee waiver requested")
    expedited_processing: bool = Field(default=False, description="Expedited processing requested")
    date_range_start: Optional[str] = Field(default=None, description="Start of requested date range")
    date_range_end: Optional[str] = Field(default=None, description="End of requested date range")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "requester": {
                        "first_name": "James",
                        "last_name": "Callahan",
                        "email": "j.callahan@capitaltribune.com",
                        "phone": "(317) 555-0261",
                        "address_street": "310 Wabash Ave, Suite 400",
                        "address_city": "Indianapolis",
                        "address_state": "IN",
                        "address_zip": "46204",
                        "organization": "Capital City Tribune",
                    },
                    "request_description": "All records related to ALPR system procurement contracts",
                    "request_category": "media",
                    "agency": "Department of Justice",
                    "agency_component_name": "Office of Information Policy",
                    "fee_waiver": True,
                    "expedited_processing": True,
                    "date_range_start": "06/01/2023",
                    "date_range_end": "05/31/2025",
                }
            ]
        }
    }


# =============================================================================
# PII Detection Models
# =============================================================================

class PIIFinding(BaseModel):
    """Individual PII detection result."""
    pii_type: PIIType = Field(description="Type of PII detected")
    value_redacted: str = Field(description="Redacted value (e.g., '***-**-1234')")
    severity: PIISeverity = Field(description="Risk severity level")
    confidence: float = Field(ge=0.0, le=1.0, description="Detection confidence")
    location: str = Field(description="Source location (e.g., 'Page 1, line 3')")
    recommendation: str = Field(description="Handling recommendation")


class PIIReport(BaseModel):
    """Aggregated PII detection report with risk score."""
    findings: List[PIIFinding] = Field(default_factory=list)

    @computed_field
    @property
    def pii_risk_score(self) -> int:
        """Compute risk score 0-100 from findings.

        Weights: SSN=40, PHONE=15, EMAIL=10. Capped at 100.
        """
        weights = {PIIType.SSN: 40, PIIType.PHONE: 15, PIIType.EMAIL: 10}
        score = sum(weights.get(f.pii_type, 5) for f in self.findings)
        return min(score, 100)

    @computed_field
    @property
    def risk_level(self) -> PIISeverity:
        if self.pii_risk_score >= 60:
            return PIISeverity.HIGH
        elif self.pii_risk_score >= 25:
            return PIISeverity.MEDIUM
        return PIISeverity.LOW


# =============================================================================
# Compliance Models
# =============================================================================

class ComplianceRequirement(BaseModel):
    """Single jurisdiction-specific requirement for a transaction."""
    name: str = Field(description="Requirement name (e.g., '9A Report')")
    code: Optional[str] = Field(default=None, description="Official code or form number")
    category: RequirementCategory = Field(description="Requirement category")
    description: str = Field(description="What this requirement entails")
    authority: Optional[str] = Field(default=None, description="Issuing authority")
    fee: Optional[str] = Field(default=None, description="Associated fee (e.g., '$225')")
    url: Optional[str] = Field(default=None, description="Reference URL for more info")
    status: RequirementStatus = Field(default=RequirementStatus.REQUIRED)
    notes: Optional[str] = Field(default=None, description="Additional context or caveats")
    source: RequirementSource = Field(default=RequirementSource.JURISDICTION, description="Where this requirement originated")


class ComplianceReport(BaseModel):
    """Jurisdiction compliance report for a transaction."""
    jurisdiction_key: str = Field(description="Normalized key (e.g., 'CA:Los Angeles:Los Angeles')")
    jurisdiction_display: str = Field(description="Human-readable name")
    jurisdiction_type: str = Field(description="'city', 'county', or 'state'")
    overall_status: ComplianceOverallStatus = Field(default=ComplianceOverallStatus.UNKNOWN_JURISDICTION)
    requirements: List[ComplianceRequirement] = Field(default_factory=list)
    transaction_type: Optional[str] = Field(default=None, description="Transaction type checked")
    notes: Optional[str] = Field(default=None, description="General compliance notes")

    @computed_field
    @property
    def requirement_count(self) -> int:
        return len(self.requirements)

    @computed_field
    @property
    def action_items(self) -> int:
        return sum(
            1 for r in self.requirements
            if r.status in (RequirementStatus.REQUIRED, RequirementStatus.LIKELY_REQUIRED)
        )


# =============================================================================
# Property Enrichment Models (Cadastral / Assessor Data)
# =============================================================================


class PropertyEnrichment(BaseModel):
    """Enriched property data from cadastral/assessor lookup (e.g., Regrid)."""
    parcel_id: Optional[str] = Field(default=None, description="Parcel number / APN")
    apn: Optional[str] = Field(default=None, description="Assessor's Parcel Number (unformatted)")
    owner_name: Optional[str] = Field(default=None, description="Current owner on record")
    lot_size_sqft: Optional[float] = Field(default=None, description="Lot size in square feet")
    lot_size_acres: Optional[float] = Field(default=None, description="Lot size in acres")
    year_built: Optional[int] = Field(default=None, description="Year structure was built")
    assessed_total: Optional[float] = Field(default=None, description="Total assessed value (USD)")
    assessed_land: Optional[float] = Field(default=None, description="Assessed land value (USD)")
    assessed_improvement: Optional[float] = Field(default=None, description="Assessed improvement value (USD)")
    zoning: Optional[str] = Field(default=None, description="Zoning designation")
    land_use: Optional[str] = Field(default=None, description="Land use description")
    latitude: Optional[float] = Field(default=None, description="Parcel centroid latitude")
    longitude: Optional[float] = Field(default=None, description="Parcel centroid longitude")
    source: str = Field(default="regrid", description="Data provider")
    lookup_timestamp: Optional[str] = Field(default=None, description="ISO 8601 timestamp of lookup")
    match_quality: str = Field(default="none", description="Match quality: exact | fuzzy | none")


# =============================================================================
# Verification / Citation Models
# =============================================================================

class VerificationCitation(BaseModel):
    """Citation proving where an extracted value was found in the source document."""
    field_name: str = Field(description="Schema field this cites")
    extracted_value: str = Field(description="The value that was extracted")
    page_number: int = Field(description="Page number where value appears")
    line_or_region: str = Field(description="Line number or region description")
    surrounding_text: str = Field(description="~20 chars of context around the value")
    confidence: float = Field(ge=0.0, le=1.0, description="Verification confidence")


# =============================================================================
# Top-Level Extraction Result
# =============================================================================

class ExtractionResult(BaseModel):
    """Top-level wrapper for all extraction output."""
    mode: str = Field(description="'real_estate' or 'gov'")
    source_file: str = Field(description="Input file path")
    extraction_timestamp: str = Field(description="ISO 8601 timestamp")
    model_used: str = Field(default="docextract-vision-v1")
    pages_processed: int = Field(description="Number of pages analyzed")

    # Extracted data (one will be populated based on mode)
    # Using dict to allow partial/lenient data from model_construct()
    dotloop_data: Optional[dict] = None
    foia_data: Optional[dict] = None

    # Dotloop API-ready format (populated for real_estate mode)
    dotloop_api_payload: Optional[dict] = None

    # DocuSign API-ready format (populated for real_estate mode)
    docusign_api_payload: Optional[dict] = None

    # Verification
    citations: List[VerificationCitation] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # PII (gov mode only)
    pii_report: Optional[PIIReport] = None

    # Compliance (real_estate mode)
    compliance_report: Optional[ComplianceReport] = None

    # Property enrichment (real_estate mode — cadastral/assessor data)
    property_enrichment: Optional[PropertyEnrichment] = None

    # Document type classification
    document_type: Optional[str] = Field(
        default=None,
        description="Classified document type (PURCHASE_OFFER, COUNTEROFFER, etc.)",
    )

    # API usage tracking
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


# =============================================================================
# Document Type Classification
# =============================================================================


class DocumentType(str, Enum):
    """Classification of real estate document types."""
    PURCHASE_OFFER = "PURCHASE_OFFER"
    COUNTEROFFER = "COUNTEROFFER"
    INSPECTION_NOTICE = "INSPECTION_NOTICE"
    INSPECTION_RESPONSE = "INSPECTION_RESPONSE"
    ADDENDUM = "ADDENDUM"
    AMENDMENT = "AMENDMENT"
    LISTING_AGREEMENT = "LISTING_AGREEMENT"
    UNKNOWN = "UNKNOWN"


# =============================================================================
# Comparison Models
# =============================================================================


class FieldSignificance(str, Enum):
    """How important a field change is for decision-making."""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class ComparisonFieldDelta(BaseModel):
    """A single field that differs between two documents."""
    field_path: str = Field(description="Dot-separated path (e.g., 'financials.purchase_price')")
    field_label: str = Field(description="Human-readable label (e.g., 'Purchase Price')")
    original_value: Optional[str] = None
    new_value: Optional[str] = None
    change_type: str = Field(description="'modified', 'added', or 'removed'")
    significance: FieldSignificance = Field(default=FieldSignificance.MINOR)


class ComparisonResult(BaseModel):
    """Result of comparing two document extractions."""
    comparison_id: str = Field(description="Unique comparison ID")
    from_extraction_id: str = Field(description="Extraction ID of the original document")
    to_extraction_id: str = Field(description="Extraction ID of the compared document")
    from_source: Optional[str] = None
    to_source: Optional[str] = None
    deltas: List[ComparisonFieldDelta] = Field(default_factory=list)
    summary: str = Field(default="", description="Natural language summary of changes")
    critical_count: int = 0
    major_count: int = 0
    minor_count: int = 0
    total_changes: int = 0
    comparison_timestamp: str = Field(default="")
