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


class PIISeverity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


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
                    "Offer Date": getattr(dates, "offer_date", "") or "",
                    "Offer Expiration Date": getattr(dates, "offer_expiration_date", "") or "",
                    "Inspection Date": getattr(dates, "inspection_date", "") or "",
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

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "loop_name": "Michael B. Curtis, 2100 Waterview Dr, Billings, MT 59101",
                    "transaction_type": "PURCHASE_OFFER",
                    "transaction_status": "PRE_OFFER",
                    "property_address": {
                        "street_number": "2100",
                        "street_name": "Waterview Dr",
                        "unit_number": "B",
                        "city": "Billings",
                        "state_or_province": "MT",
                        "postal_code": "59101",
                        "country": "US",
                    },
                    "financials": {
                        "purchase_price": 485000.00,
                        "earnest_money_amount": 10000.00,
                        "earnest_money_held_by": "First American Title",
                    },
                    "contract_dates": {
                        "closing_date": "03/15/2025",
                        "offer_date": "01/28/2025",
                    },
                    "participants": [
                        {"full_name": "Michael B. Curtis", "role": "BUYER"},
                        {"full_name": "Tiffany J. Selong", "role": "SELLER"},
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
                        "first_name": "Sarah",
                        "last_name": "Mitchell",
                        "email": "s.mitchell@springfield-news.org",
                        "phone": "(217) 555-0134",
                        "address_street": "742 Evergreen Terrace",
                        "address_city": "Springfield",
                        "address_state": "IL",
                        "address_zip": "62704",
                        "organization": "Springfield Daily Register",
                    },
                    "request_description": "All records related to border technology procurement contracts",
                    "request_category": "media",
                    "agency": "Department of Homeland Security",
                    "agency_component_name": "Office of Privacy",
                    "fee_waiver": True,
                    "expedited_processing": True,
                    "date_range_start": "01/01/2023",
                    "date_range_end": "12/31/2024",
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

    # Verification
    citations: List[VerificationCitation] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)

    # PII (gov mode only)
    pii_report: Optional[PIIReport] = None
