"""Comprehensive demo seed script for D.E.S.

Populates the entire application with realistic sample data so every feature
feels alive.  Zero external API dependencies — all extraction results are
pre-computed fixtures indistinguishable from real pipeline output.

Usage:
    python seed_demo.py              # Seed all demo data (idempotent)
    python seed_demo.py --clean      # Remove all demo data, then re-seed

Demo entities are identifiable by the @deslabs.local email domain.
"""

import asyncio
import hashlib
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Pre-computed extraction fixtures (financial documents)
# ---------------------------------------------------------------------------

FINANCIAL_EXTRACTIONS = {
    "pre_approval_letter": {
        "lender_name": "Summit National Bank",
        "lender_address": "1200 Financial Plaza, Suite 400, Denver, CO 80202",
        "lender_nmls": "445521",
        "loan_officer_name": "Michael R. Thompson",
        "loan_officer_nmls": "887234",
        "borrower_name": "Jane Marie Doe",
        "co_borrower_name": None,
        "approval_amount": 485000.00,
        "loan_type": "conventional",
        "interest_rate": 6.375,
        "approval_date": "01/15/2026",
        "expiration_date": "04/15/2026",
        "conditions": [
            "Satisfactory property appraisal",
            "Verification of employment within 10 days of closing",
            "Clear title search and title insurance",
            "Homeowner's insurance declaration page",
        ],
        "property_type": "Single Family Residence",
    },
    "bank_statement": {
        "institution_name": "Pacific Coast Credit Union",
        "account_holder": "Jane Marie Doe",
        "account_type": "savings",
        "account_number_last4": "7823",
        "statement_period_start": "12/01/2025",
        "statement_period_end": "12/31/2025",
        "beginning_balance": 42318.56,
        "ending_balance": 47853.14,
        "total_deposits": 8750.00,
        "total_withdrawals": 3215.42,
        "average_daily_balance": 44892.33,
    },
    "pay_stub": {
        "employer_name": "Meridian Technology Solutions",
        "employer_address": "8900 Innovation Drive, Suite 200, Austin, TX 78759",
        "employee_name": "Jane Marie Doe",
        "employee_id": "EMP-20847",
        "pay_period_start": "12/01/2025",
        "pay_period_end": "12/15/2025",
        "pay_date": "12/20/2025",
        "pay_frequency": "semi-monthly",
        "gross_pay": 5000.00,
        "net_pay": 3380.00,
        "federal_tax": 762.50,
        "state_tax": 0.00,
        "ytd_gross": 115000.00,
        "ytd_net": 77740.00,
    },
    "w2": {
        "tax_year": 2025,
        "employer_name": "Meridian Technology Solutions",
        "employer_ein": "84-2957301",
        "employer_address": "8900 Innovation Drive, Suite 200, Austin, TX 78759",
        "employee_name": "Jane Marie Doe",
        "employee_ssn_last4": "4523",
        "wages_tips_compensation": 120000.00,
        "federal_tax_withheld": 19100.00,
        "social_security_wages": 120000.00,
        "social_security_tax": 7440.00,
        "medicare_wages": 120000.00,
        "medicare_tax": 1740.00,
        "state": "TX",
        "state_wages": 120000.00,
        "state_tax_withheld": 0.00,
    },
    "proof_of_funds": {
        "institution_name": "Pacific Coast Credit Union",
        "account_holder": "Jane Marie Doe",
        "letter_date": "01/18/2026",
        "account_type": "savings",
        "available_funds": 47853.14,
        "currency": "USD",
        "officer_name": "Sarah L. Martinez",
        "officer_title": "Branch Manager",
        "contact_phone": "(562) 555-0100",
    },
}

# Doc types that have no financial extraction schema (just mark completed)
NO_EXTRACTION_TYPES = {"drivers_license", "proof_of_insurance"}

# Map doc types to sample PDF filenames
DOC_FILES = {
    "pre_approval_letter": "sample_pre_approval.pdf",
    "bank_statement": "sample_bank_statement.pdf",
    "pay_stub": "sample_pay_stub.pdf",
    "w2": "sample_w2.pdf",
    "proof_of_funds": "sample_proof_of_funds.pdf",
    "drivers_license": "sample_drivers_license.pdf",
    "proof_of_insurance": "sample_proof_of_insurance.pdf",
}

# Confidence scores per doc type
DOC_CONFIDENCE = {
    "pre_approval_letter": 0.94,
    "bank_statement": 0.92,
    "pay_stub": 0.91,
    "w2": 0.93,
    "proof_of_funds": 0.90,
    "drivers_license": 0.88,
    "proof_of_insurance": 0.87,
}

# Citations per doc type (3-5 per document)
DOC_CITATIONS = {
    "pre_approval_letter": [
        {"field_name": "approval_amount", "extracted_value": "485000.00", "page_number": 1,
         "line_or_region": "Paragraph 2", "surrounding_text": "...approved for up to $485,000.00 (Four Hundred...", "confidence": 0.97},
        {"field_name": "lender_name", "extracted_value": "Summit National Bank", "page_number": 1,
         "line_or_region": "Header", "surrounding_text": "Summit National Bank — Pre-Approval...", "confidence": 0.99},
        {"field_name": "interest_rate", "extracted_value": "6.375", "page_number": 1,
         "line_or_region": "Paragraph 3", "surrounding_text": "...fixed rate of 6.375% for a 30-year...", "confidence": 0.96},
        {"field_name": "borrower_name", "extracted_value": "Jane Marie Doe", "page_number": 1,
         "line_or_region": "Salutation", "surrounding_text": "Dear Jane Marie Doe,", "confidence": 0.99},
    ],
    "bank_statement": [
        {"field_name": "ending_balance", "extracted_value": "47853.14", "page_number": 1,
         "line_or_region": "Summary Box", "surrounding_text": "Ending Balance: $47,853.14", "confidence": 0.98},
        {"field_name": "institution_name", "extracted_value": "Pacific Coast Credit Union", "page_number": 1,
         "line_or_region": "Header", "surrounding_text": "Pacific Coast Credit Union — Monthly Statement", "confidence": 0.99},
        {"field_name": "account_holder", "extracted_value": "Jane Marie Doe", "page_number": 1,
         "line_or_region": "Account Info", "surrounding_text": "Account Holder: Jane Marie Doe", "confidence": 0.99},
    ],
    "pay_stub": [
        {"field_name": "gross_pay", "extracted_value": "5000.00", "page_number": 1,
         "line_or_region": "Earnings Section", "surrounding_text": "Gross Pay: $5,000.00", "confidence": 0.97},
        {"field_name": "employer_name", "extracted_value": "Meridian Technology Solutions", "page_number": 1,
         "line_or_region": "Header", "surrounding_text": "Meridian Technology Solutions — Pay Statement", "confidence": 0.99},
        {"field_name": "ytd_gross", "extracted_value": "115000.00", "page_number": 1,
         "line_or_region": "YTD Section", "surrounding_text": "YTD Gross: $115,000.00", "confidence": 0.96},
    ],
    "w2": [
        {"field_name": "wages_tips_compensation", "extracted_value": "120000.00", "page_number": 1,
         "line_or_region": "Box 1", "surrounding_text": "1. Wages, tips, other compensation: $120,000.00", "confidence": 0.98},
        {"field_name": "employer_name", "extracted_value": "Meridian Technology Solutions", "page_number": 1,
         "line_or_region": "Box c", "surrounding_text": "c. Employer: Meridian Technology Solutions", "confidence": 0.99},
        {"field_name": "federal_tax_withheld", "extracted_value": "19100.00", "page_number": 1,
         "line_or_region": "Box 2", "surrounding_text": "2. Federal income tax withheld: $19,100.00", "confidence": 0.97},
    ],
    "proof_of_funds": [
        {"field_name": "available_funds", "extracted_value": "47853.14", "page_number": 1,
         "line_or_region": "Paragraph 1", "surrounding_text": "...available funds of $47,853.14 in their...", "confidence": 0.96},
        {"field_name": "institution_name", "extracted_value": "Pacific Coast Credit Union", "page_number": 1,
         "line_or_region": "Letterhead", "surrounding_text": "Pacific Coast Credit Union — Verification Letter", "confidence": 0.99},
        {"field_name": "account_holder", "extracted_value": "Jane Marie Doe", "page_number": 1,
         "line_or_region": "Body", "surrounding_text": "This letter certifies that Jane Marie Doe...", "confidence": 0.98},
    ],
}

# ---------------------------------------------------------------------------
# Pre-computed real estate extraction fixtures (for Extraction page)
# ---------------------------------------------------------------------------

REAL_ESTATE_EXTRACTIONS = [
    {
        "filename": "sample_purchase_agreement.pdf",
        "extracted_data": {
            "loop_name": "Daniel R. Whitfield, 4738 Ridgeline Ct, Helena, MT 59601",
            "transaction_type": "PURCHASE_OFFER",
            "transaction_status": "PRE_OFFER",
            "property_address": {
                "street_number": "4738", "street_name": "Ridgeline Ct",
                "city": "Helena", "state_or_province": "MT",
                "postal_code": "59601", "county": "Lewis And Clark", "country": "US",
            },
            "financials": {
                "purchase_price": 612500.00,
                "earnest_money_amount": 15000.00,
                "earnest_money_held_by": "Montana Title & Escrow",
                "sale_commission_rate": "6%",
            },
            "contract_dates": {
                "closing_date": "04/18/2026",
                "offer_date": "03/04/2026",
                "offer_expiration_date": "03/11/2026",
            },
            "participants": [
                {"full_name": "Daniel R. Whitfield", "role": "BUYER", "email": "d.whitfield@email.com"},
                {"full_name": "Gregory T. Navarro", "role": "SELLER", "email": "g.navarro@email.com"},
                {"full_name": "Jane Marie Doe", "role": "BUYING_AGENT", "email": "jane@rockymtnrealty.com",
                 "company_name": "Rocky Mountain Real Estate Group"},
            ],
        },
        "pages": 2,
        "confidence": 0.94,
        "citations": [
            {"field_name": "financials.purchase_price", "extracted_value": "612500.00", "page_number": 1,
             "line_or_region": "Section 2, Paragraph A", "surrounding_text": "...purchase price of $612,500.00 (Six Hundred...", "confidence": 0.97},
            {"field_name": "property_address.street_name", "extracted_value": "Ridgeline Ct", "page_number": 1,
             "line_or_region": "Section 1", "surrounding_text": "...property located at 4738 Ridgeline Ct...", "confidence": 0.99},
            {"field_name": "property_address.city", "extracted_value": "Helena", "page_number": 1,
             "line_or_region": "Section 1", "surrounding_text": "...Helena, MT 59601, Lewis And Clark County...", "confidence": 0.99},
            {"field_name": "financials.earnest_money_amount", "extracted_value": "15000.00", "page_number": 1,
             "line_or_region": "Section 3", "surrounding_text": "...earnest money deposit of $15,000.00...", "confidence": 0.96},
            {"field_name": "contract_dates.closing_date", "extracted_value": "04/18/2026", "page_number": 2,
             "line_or_region": "Section 8", "surrounding_text": "...closing shall occur on or before April 18, 2026...", "confidence": 0.95},
            {"field_name": "participants[0].full_name", "extracted_value": "Daniel R. Whitfield", "page_number": 1,
             "line_or_region": "Buyer Signature Block", "surrounding_text": "BUYER: Daniel R. Whitfield", "confidence": 0.99},
            {"field_name": "participants[1].full_name", "extracted_value": "Gregory T. Navarro", "page_number": 2,
             "line_or_region": "Seller Signature Block", "surrounding_text": "SELLER: Gregory T. Navarro", "confidence": 0.99},
            {"field_name": "financials.earnest_money_held_by", "extracted_value": "Montana Title & Escrow", "page_number": 1,
             "line_or_region": "Section 3, Paragraph B", "surrounding_text": "...deposited with Montana Title & Escrow...", "confidence": 0.94},
        ],
        "tokens": {"prompt": 12450, "completion": 2830, "total": 15280},
        "cost": 0.059,
        "duration_ms": 8420,
    },
    {
        "filename": "sample_ranch_contract.pdf",
        "extracted_data": {
            "loop_name": "J. Martinez, 8200 Clark Fork River Rd, Missoula, MT 59801",
            "transaction_type": "PURCHASE_OFFER",
            "transaction_status": "PRE_OFFER",
            "property_address": {
                "street_number": "8200", "street_name": "Clark Fork River Rd",
                "city": "Missoula", "state_or_province": "MT",
                "postal_code": "59801", "county": "Missoula", "country": "US",
            },
            "financials": {
                "purchase_price": 875000.00,
                "earnest_money_amount": 25000.00,
                "earnest_money_held_by": "First Security Title",
                "sale_commission_rate": "5%",
            },
            "contract_dates": {
                "closing_date": "05/30/2026",
                "offer_date": "02/15/2026",
            },
            "participants": [
                {"full_name": "Jose L. Martinez", "role": "BUYER", "email": "jose.martinez@email.com"},
                {"full_name": "Patricia A. Wells", "role": "SELLER", "email": "p.wells@email.com"},
            ],
        },
        "pages": 1,
        "confidence": 0.91,
        "citations": [
            {"field_name": "financials.purchase_price", "extracted_value": "875000.00", "page_number": 1,
             "line_or_region": "Section 2", "surrounding_text": "...purchase price of $875,000.00...", "confidence": 0.96},
            {"field_name": "property_address.city", "extracted_value": "Missoula", "page_number": 1,
             "line_or_region": "Section 1", "surrounding_text": "...Missoula, MT 59801, Missoula County...", "confidence": 0.98},
            {"field_name": "contract_dates.closing_date", "extracted_value": "05/30/2026", "page_number": 1,
             "line_or_region": "Section 7", "surrounding_text": "...closing on or before May 30, 2026...", "confidence": 0.94},
            {"field_name": "participants[0].full_name", "extracted_value": "Jose L. Martinez", "page_number": 1,
             "line_or_region": "Buyer Block", "surrounding_text": "BUYER: Jose L. Martinez", "confidence": 0.99},
            {"field_name": "financials.earnest_money_amount", "extracted_value": "25000.00", "page_number": 1,
             "line_or_region": "Section 3", "surrounding_text": "...earnest money of $25,000.00 deposited...", "confidence": 0.95},
        ],
        "tokens": {"prompt": 8920, "completion": 2150, "total": 11070},
        "cost": 0.043,
        "duration_ms": 6830,
    },
    {
        "filename": "sample_condo_offer.pdf",
        "extracted_data": {
            "loop_name": "A. Chen, 1847 Wilshire Blvd #4C, Los Angeles, CA 90025",
            "transaction_type": "PURCHASE_OFFER",
            "transaction_status": "PRE_OFFER",
            "property_address": {
                "street_number": "1847", "street_name": "Wilshire Blvd",
                "unit_number": "4C",
                "city": "Los Angeles", "state_or_province": "CA",
                "postal_code": "90025", "county": "Los Angeles", "country": "US",
            },
            "financials": {
                "purchase_price": 725000.00,
                "earnest_money_amount": 20000.00,
                "earnest_money_held_by": "Pacific Escrow Services",
            },
            "contract_dates": {
                "closing_date": "04/01/2026",
                "offer_date": "02/20/2026",
                "inspection_date": "03/05/2026",
            },
            "participants": [
                {"full_name": "Amy S. Chen", "role": "BUYER", "email": "amy.chen@email.com"},
                {"full_name": "Robert J. Feldman", "role": "SELLER", "email": "r.feldman@email.com"},
            ],
        },
        "pages": 1,
        "confidence": 0.93,
        "citations": [
            {"field_name": "financials.purchase_price", "extracted_value": "725000.00", "page_number": 1,
             "line_or_region": "Section 2", "surrounding_text": "...purchase price of $725,000.00...", "confidence": 0.97},
            {"field_name": "property_address.unit_number", "extracted_value": "4C", "page_number": 1,
             "line_or_region": "Section 1", "surrounding_text": "...1847 Wilshire Blvd, Unit 4C...", "confidence": 0.98},
            {"field_name": "property_address.city", "extracted_value": "Los Angeles", "page_number": 1,
             "line_or_region": "Section 1", "surrounding_text": "...Los Angeles, CA 90025...", "confidence": 0.99},
            {"field_name": "contract_dates.closing_date", "extracted_value": "04/01/2026", "page_number": 1,
             "line_or_region": "Section 6", "surrounding_text": "...closing date of April 1, 2026...", "confidence": 0.95},
            {"field_name": "participants[0].full_name", "extracted_value": "Amy S. Chen", "page_number": 1,
             "line_or_region": "Buyer Block", "surrounding_text": "BUYER: Amy S. Chen", "confidence": 0.99},
            {"field_name": "financials.earnest_money_amount", "extracted_value": "20000.00", "page_number": 1,
             "line_or_region": "Section 3", "surrounding_text": "...earnest money deposit of $20,000.00...", "confidence": 0.96},
        ],
        "tokens": {"prompt": 9100, "completion": 2280, "total": 11380},
        "cost": 0.044,
        "duration_ms": 7150,
    },
]

# ---------------------------------------------------------------------------
# Transaction fixtures
# ---------------------------------------------------------------------------

NOW = datetime.now(timezone.utc)

TRANSACTION_FIXTURES = [
    {
        "name": "789 Spruce Lane — New Listing",
        "status": "draft",
        "property_address": {
            "street_number": "789", "street_name": "Spruce Lane",
            "city": "Helena", "state_or_province": "MT",
            "postal_code": "59601", "county": "Lewis And Clark", "country": "US",
        },
        "purchase_price": None,
        "earnest_money": None,
        "mls_number": None,
        "closing_date": None,
        "created_offset_days": 0,
        "participants": [
            {"role": "LISTING_AGENT", "user_key": "primary", "status": "active"},
        ],
        "satisfied_docs": [],
    },
    {
        "name": "456 Elm Avenue Purchase",
        "status": "active",
        "property_address": {
            "street_number": "456", "street_name": "Elm Avenue",
            "city": "Denver", "state_or_province": "CO",
            "postal_code": "80202", "country": "US",
        },
        "purchase_price": 485000.00,
        "earnest_money": 10000.00,
        "mls_number": "MLS-20260045",
        "closing_date": (NOW + timedelta(days=50)).isoformat(),
        "created_offset_days": -5,
        "participants": [
            {"role": "BUYER", "user_key": "primary", "status": "active"},
            {"role": "BUYING_AGENT", "user_key": "agent2", "status": "active"},
            {"role": "LOAN_OFFICER", "user_key": "lender", "status": "invited"},
        ],
        "satisfied_docs": ["pre_approval_letter", "bank_statement", "pay_stub"],
    },
    {
        "name": "2100 Waterview Drive Purchase",
        "status": "under_contract",
        "property_address": {
            "street_number": "2100", "street_name": "Waterview Dr",
            "city": "Helena", "state_or_province": "MT",
            "postal_code": "59601", "county": "Lewis And Clark", "country": "US",
        },
        "purchase_price": 612500.00,
        "earnest_money": 15000.00,
        "mls_number": "MLS-20261234",
        "closing_date": (NOW + timedelta(days=35)).isoformat(),
        "created_offset_days": -14,
        "participants": [
            {"role": "BUYING_AGENT", "user_key": "primary", "status": "active"},
            {"role": "SELLER", "user_key": "seller", "status": "active"},
            {"role": "LOAN_OFFICER", "user_key": "lender", "status": "active"},
        ],
        "satisfied_docs": [
            "pre_approval_letter", "bank_statement", "proof_of_funds",
            "drivers_license", "pay_stub",
        ],
    },
    {
        "name": "1425 Heritage Court Sale",
        "status": "closed",
        "property_address": {
            "street_number": "1425", "street_name": "Heritage Ct",
            "city": "Missoula", "state_or_province": "MT",
            "postal_code": "59801", "county": "Missoula", "country": "US",
        },
        "purchase_price": 375000.00,
        "earnest_money": 7500.00,
        "mls_number": "MLS-20259876",
        "closing_date": (NOW - timedelta(days=5)).isoformat(),
        "created_offset_days": -60,
        "participants": [
            {"role": "LISTING_AGENT", "user_key": "primary", "status": "active"},
            {"role": "SELLER", "user_key": "seller", "status": "active"},
        ],
        "satisfied_docs": [
            "pre_approval_letter", "bank_statement", "proof_of_funds",
            "drivers_license", "pay_stub", "w2", "proof_of_insurance",
        ],
    },
]


# ---------------------------------------------------------------------------
# Main seed logic
# ---------------------------------------------------------------------------

async def main():
    clean = "--clean" in sys.argv

    from db import (
        init_db, close_db, UserProfile, Transaction, UserDocument,
        DocumentRecord, TransactionDocument, ExtractionRecord,
        OnboardingStepStatus, VALID_STEP_IDS,
    )
    from schemas import (
        UserType, UserDocumentType, TransactionStatus, ParticipantRole,
        ParticipantStatus, TransactionParticipant, DocumentRequirement,
        AgentProfile, BuyerProfile, SellerProfile, LoanOfficerProfile,
        DotloopPropertyAddress, DotloopLoopDetails, DotloopFinancials,
        DotloopContractDates, DotloopParticipant, PreApprovalStatus,
        OwnershipType, VerificationCitation,
        DEFAULT_PURCHASE_REQUIREMENTS,
    )
    from compliance_engine import run_compliance_check

    await init_db()

    test_docs_dir = Path(__file__).parent / "test_docs" / "financial"
    uploads_dir = Path(__file__).parent / "profile_uploads"

    # Check that sample PDFs exist
    missing = [f for f in DOC_FILES.values() if not (test_docs_dir / f).exists()]
    if missing:
        print(f"ERROR: Missing sample PDFs: {missing}")
        print("Run `python generate_test_docs.py` first")
        await close_db()
        sys.exit(1)

    # ==================================================================
    # Phase 1: Clean
    # ==================================================================
    demo_emails = [
        "dev@deslabs.local",
        "seller.demo@deslabs.local",
        "lender.demo@deslabs.local",
        "agent2.demo@deslabs.local",
    ]

    if clean:
        print("=== Cleaning demo data ===")
        for email in demo_emails:
            user = await UserProfile.find_one(UserProfile.email == email)
            if not user:
                continue
            uid = str(user.id)
            # Delete UserDocuments
            user_docs = await UserDocument.find(UserDocument.user_id == uid).to_list()
            for doc in user_docs:
                try:
                    Path(doc.file_path).unlink(missing_ok=True)
                except Exception:
                    pass
                await doc.delete()
            # Delete TransactionDocuments
            txn_docs = await TransactionDocument.find(TransactionDocument.uploaded_by == uid).to_list()
            for td in txn_docs:
                await td.delete()
            # Delete Transactions created by this user
            txns = await Transaction.find(Transaction.created_by == uid).to_list()
            for txn in txns:
                await txn.delete()
            # Delete DocumentRecords
            doc_records = await DocumentRecord.find(DocumentRecord.user_id == uid).to_list()
            for dr in doc_records:
                await dr.delete()
            # Delete user upload dir
            user_upload_dir = uploads_dir / uid
            if user_upload_dir.exists():
                shutil.rmtree(user_upload_dir)
            # Delete secondary users (not the dev user — reset instead)
            if email != "dev@deslabs.local":
                await user.delete()
                print(f"  Deleted user {email} and associated data")
            else:
                # Reset dev user to blank
                user.name = ""
                user.phone = None
                user.address = None
                user.user_types = []
                user.agent_profile = None
                user.buyer_profile = None
                user.seller_profile = None
                user.loan_officer_profile = None
                user.onboarding_completed = False
                user.onboarding_step_statuses = []
                user.onboarding_current_step = 0
                user.onboarding_version = 1
                await user.save()
                print(f"  Reset dev user and deleted {len(user_docs)} docs, {len(txns)} txns")
        print()

    # ==================================================================
    # Phase 2: Create/update users
    # ==================================================================
    print("=== Phase 2: Users ===")

    # Primary user (dev user)
    primary = await UserProfile.find_one(UserProfile.email == "dev@deslabs.local")
    if not primary:
        primary = UserProfile(email="dev@deslabs.local", name="Jane Marie Doe", has_clerk_account=False)
        await primary.insert()
        print(f"  Created primary user: {primary.id}")
    else:
        print(f"  Primary user exists: {primary.id}")

    primary.name = "Jane Marie Doe"
    primary.phone = "(303) 555-7890"
    primary.address = {"street": "456 Elm Avenue", "city": "Denver", "state": "CO", "zip": "80202"}
    primary.user_types = [UserType.AGENT, UserType.BUYER]
    primary.agent_profile = AgentProfile(
        license_number="MT-2024-08321",
        license_state="MT",
        brokerage_name="Rocky Mountain Real Estate Group",
        mls_id="MLS-44521",
        nar_member_id="NAR-778811",
        areas_served=["Helena, MT", "Missoula, MT", "Denver, CO"],
    )
    primary.buyer_profile = BuyerProfile(
        pre_approval_status=PreApprovalStatus.PRE_APPROVED,
        pre_approval_amount=485000.00,
        pre_approval_lender="Summit National Bank",
        purchase_budget_min=400000.00,
        purchase_budget_max=550000.00,
        first_time_buyer=True,
        employment_status="employed",
        employer_name="Meridian Technology Solutions",
        annual_income=125000.00,
    )
    await primary.save()
    print(f"  Updated primary profile: Jane Marie Doe (agent + buyer)")

    # Secondary users
    user_map = {"primary": primary}

    # Seller
    seller = await UserProfile.find_one(UserProfile.email == "seller.demo@deslabs.local")
    if not seller:
        seller = UserProfile(email="seller.demo@deslabs.local", name="Gregory T. Navarro", has_clerk_account=False)
        await seller.insert()
    seller.name = "Gregory T. Navarro"
    seller.phone = "(406) 555-2341"
    seller.address = {"street": "1425 Heritage Ct", "city": "Missoula", "state": "MT", "zip": "59801"}
    seller.user_types = [UserType.SELLER]
    seller.seller_profile = SellerProfile(
        property_addresses=[
            {"street": "1425 Heritage Ct", "city": "Missoula", "state": "MT", "zip": "59801"},
            {"street": "2100 Waterview Dr", "city": "Helena", "state": "MT", "zip": "59601"},
        ],
        ownership_type=OwnershipType.SOLE,
    )
    await seller.save()
    user_map["seller"] = seller
    print(f"  Seller: {seller.name} ({seller.id})")

    # Loan Officer
    lender = await UserProfile.find_one(UserProfile.email == "lender.demo@deslabs.local")
    if not lender:
        lender = UserProfile(email="lender.demo@deslabs.local", name="Michael R. Thompson", has_clerk_account=False)
        await lender.insert()
    lender.name = "Michael R. Thompson"
    lender.phone = "(303) 555-8900"
    lender.address = {"street": "1200 Financial Plaza", "city": "Denver", "state": "CO", "zip": "80202"}
    lender.user_types = [UserType.LOAN_OFFICER]
    lender.loan_officer_profile = LoanOfficerProfile(
        nmls_id="887234",
        company_name="Summit National Bank",
        company_nmls="445521",
        license_states=["MT", "CO", "WY"],
        loan_types_offered=["conventional", "FHA", "VA", "jumbo"],
    )
    await lender.save()
    user_map["lender"] = lender
    print(f"  Lender: {lender.name} ({lender.id})")

    # Second Agent
    agent2 = await UserProfile.find_one(UserProfile.email == "agent2.demo@deslabs.local")
    if not agent2:
        agent2 = UserProfile(email="agent2.demo@deslabs.local", name="Sarah Chen", has_clerk_account=False)
        await agent2.insert()
    agent2.name = "Sarah Chen"
    agent2.phone = "(406) 555-6789"
    agent2.address = {"street": "820 Main St", "city": "Helena", "state": "MT", "zip": "59601"}
    agent2.user_types = [UserType.AGENT]
    agent2.agent_profile = AgentProfile(
        license_number="MT-2023-05678",
        license_state="MT",
        brokerage_name="Big Sky Realty",
        mls_id="MLS-33102",
        areas_served=["Helena, MT", "Great Falls, MT"],
    )
    await agent2.save()
    user_map["agent2"] = agent2
    print(f"  Agent2: {agent2.name} ({agent2.id})")

    # ==================================================================
    # Phase 3: Profile Documents (UserDocument)
    # ==================================================================
    print("\n=== Phase 3: Profile Documents ===")
    primary_uid = str(primary.id)
    user_upload_dir = uploads_dir / primary_uid
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    uploaded_docs = {}  # doc_type_str -> UserDocument

    for doc_type_str, filename in DOC_FILES.items():
        src = test_docs_dir / filename
        content = src.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        dest = user_upload_dir / f"{file_hash[:16]}_{filename}"
        dest.write_bytes(content)

        doc_type = UserDocumentType(doc_type_str)

        existing = await UserDocument.find_one(
            UserDocument.user_id == primary_uid,
            UserDocument.doc_type == doc_type,
        )
        if existing:
            doc = existing
        else:
            doc = UserDocument(
                user_id=primary_uid,
                doc_type=doc_type,
                filename=filename,
                file_path=str(dest),
                file_hash=file_hash,
                file_size_bytes=len(content),
                extraction_status="pending",
                description="Demo — sample data",
            )
            await doc.insert()

        # Apply extraction data
        extraction_data = FINANCIAL_EXTRACTIONS.get(doc_type_str)
        doc.extraction_status = "completed"
        doc.extracted_data = extraction_data  # None for drivers_license/proof_of_insurance
        doc.overall_confidence = DOC_CONFIDENCE.get(doc_type_str, 0.85)
        doc.citations = DOC_CITATIONS.get(doc_type_str, [])
        doc.description = "Demo — sample data"
        await doc.save()

        uploaded_docs[doc_type_str] = doc
        status = f"{len(extraction_data or {})} fields" if extraction_data else "no extraction"
        print(f"  {doc_type_str}: {status}, confidence={doc.overall_confidence}")

    # ==================================================================
    # Phase 4: Transactions
    # ==================================================================
    print("\n=== Phase 4: Transactions ===")
    created_txns = []

    for txn_fix in TRANSACTION_FIXTURES:
        # Check if transaction already exists by name
        existing_txn = await Transaction.find_one(Transaction.name == txn_fix["name"])
        if existing_txn:
            txn = existing_txn
        else:
            created_at = NOW + timedelta(days=txn_fix["created_offset_days"])

            # Build participants
            participants = []
            for p in txn_fix["participants"]:
                user_obj = user_map[p["user_key"]]
                participants.append(TransactionParticipant(
                    user_id=str(user_obj.id),
                    role=ParticipantRole(p["role"]),
                    status=ParticipantStatus(p["status"]),
                    added_at=created_at,
                    added_by=primary_uid,
                ))

            # Build property address
            addr_dict = txn_fix["property_address"]
            prop_addr = DotloopPropertyAddress(**addr_dict)

            # Build document requirements from template
            doc_reqs = [
                DocumentRequirement(
                    doc_type=r.doc_type, role=r.role,
                    required=r.required, satisfied=False,
                )
                for r in DEFAULT_PURCHASE_REQUIREMENTS
            ]

            closing_date = None
            if txn_fix["closing_date"]:
                closing_date = datetime.fromisoformat(txn_fix["closing_date"].replace("Z", "+00:00"))

            txn = Transaction(
                name=txn_fix["name"],
                transaction_type="purchase",
                status=TransactionStatus(txn_fix["status"]),
                property_address=prop_addr,
                mls_number=txn_fix["mls_number"],
                participants=participants,
                purchase_price=txn_fix["purchase_price"],
                earnest_money=txn_fix["earnest_money"],
                closing_date=closing_date,
                document_requirements=doc_reqs,
                created_by=primary_uid,
                created_at=created_at,
                updated_at=NOW,
            )
            await txn.insert()

        # Satisfy document requirements
        for doc_type_str in txn_fix["satisfied_docs"]:
            user_doc = uploaded_docs.get(doc_type_str)
            if not user_doc:
                continue
            doc_type = UserDocumentType(doc_type_str)
            for req in txn.document_requirements:
                if req.doc_type == doc_type and not req.satisfied:
                    req.satisfied = True
                    req.satisfied_by = str(user_doc.id)
                    break
        await txn.save()

        satisfied = sum(1 for r in txn.document_requirements if r.satisfied)
        total = len(txn.document_requirements)
        print(f"  {txn.name}: {txn.status.value}, {len(txn.participants)} participants, docs {satisfied}/{total}")
        created_txns.append(txn)

    # ==================================================================
    # Phase 5: Extraction Records (DocumentRecord + ExtractionRecord)
    # ==================================================================
    print("\n=== Phase 5: Extraction Records ===")
    test_docs_root = Path(__file__).parent / "test_docs"

    for re_fix in REAL_ESTATE_EXTRACTIONS:
        filename = re_fix["filename"]

        # Check if already exists
        existing_dr = await DocumentRecord.find_one(
            DocumentRecord.filename == filename,
            DocumentRecord.user_id == primary_uid,
        )
        if existing_dr:
            dr = existing_dr
        else:
            pdf_path = test_docs_root / filename
            file_size = pdf_path.stat().st_size if pdf_path.exists() else 0
            file_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest() if pdf_path.exists() else ""

            dr = DocumentRecord(
                filename=filename,
                file_path=str(pdf_path),
                source="upload",
                mode="real_estate",
                page_count=re_fix["pages"],
                file_size_bytes=file_size,
                file_hash=file_hash,
                user_id=primary_uid,
                uploaded_at=NOW - timedelta(days=3),
            )
            await dr.insert()

        # Build DotloopLoopDetails for API payloads
        ed = re_fix["extracted_data"]
        try:
            loop_details = DotloopLoopDetails(
                loop_name=ed["loop_name"],
                transaction_type=ed.get("transaction_type", "PURCHASE_OFFER"),
                transaction_status=ed.get("transaction_status", "PRE_OFFER"),
                property_address=DotloopPropertyAddress(**ed["property_address"]),
                financials=DotloopFinancials(**ed["financials"]),
                contract_dates=DotloopContractDates(**ed.get("contract_dates", {})),
                participants=[
                    DotloopParticipant(
                        full_name=p["full_name"],
                        role=ParticipantRole(p["role"]),
                        email=p.get("email"),
                        company_name=p.get("company_name"),
                    )
                    for p in ed.get("participants", [])
                ],
            )
            dotloop_payload = loop_details.to_dotloop_api_format()
            docusign_payload = loop_details.to_docusign_api_format()
        except Exception as e:
            print(f"  WARNING: Could not build API payloads for {filename}: {e}")
            dotloop_payload = None
            docusign_payload = None

        # Generate compliance report
        compliance_report = None
        try:
            report = run_compliance_check(ed)
            compliance_report = report
        except Exception as e:
            print(f"  WARNING: Compliance check failed for {filename}: {e}")

        # Build ExtractionRecord
        tokens = re_fix["tokens"]
        extraction_timestamp = NOW - timedelta(days=2, hours=3)

        citations = [
            VerificationCitation(**c)
            for c in re_fix["citations"]
        ]

        extraction = ExtractionRecord(
            engine="openai",
            model_used="gpt-4o-2024-08-06",
            mode="real_estate",
            extracted_data=ed,
            dotloop_api_payload=dotloop_payload,
            docusign_api_payload=docusign_payload,
            validation_success=True,
            overall_confidence=re_fix["confidence"],
            pages_processed=re_fix["pages"],
            extraction_timestamp=extraction_timestamp,
            duration_ms=re_fix["duration_ms"],
            created_at=extraction_timestamp,
            prompt_tokens=tokens["prompt"],
            completion_tokens=tokens["completion"],
            total_tokens=tokens["total"],
            cost_usd=re_fix["cost"],
            citations=citations,
            compliance_report=compliance_report,
        )

        dr.extractions = [extraction]
        await dr.save()

        compliance_status = getattr(compliance_report, "overall_status", "?") if compliance_report else "none"
        print(f"  {filename}: confidence={re_fix['confidence']}, "
              f"{len(citations)} citations, compliance={compliance_status}")

    # ==================================================================
    # Phase 6: Mark onboarding complete
    # ==================================================================
    print("\n=== Phase 6: Onboarding ===")
    primary = await UserProfile.get(primary.id)
    primary.onboarding_completed = True
    primary.onboarding_completed_at = NOW
    primary.onboarding_version = 2
    primary.onboarding_step_statuses = [
        OnboardingStepStatus(step_id=sid, status="completed", completed_at=NOW.isoformat())
        for sid in VALID_STEP_IDS
    ]
    primary.onboarding_current_step = len(VALID_STEP_IDS)
    await primary.save()
    print("  Onboarding marked complete for primary user")

    # ==================================================================
    # Phase 7: Validate & Summary
    # ==================================================================
    print("\n=== Validation ===")
    user_count = await UserProfile.find({"email": {"$regex": r"deslabs\.local$"}}).count()
    doc_count = await UserDocument.find(UserDocument.user_id == primary_uid).count()
    txn_count = await Transaction.find(Transaction.created_by == primary_uid).count()
    ext_count = await DocumentRecord.find(DocumentRecord.user_id == primary_uid).count()

    print(f"  Users:        {user_count} (expected 4)")
    print(f"  Documents:    {doc_count} (expected 7)")
    print(f"  Transactions: {txn_count} (expected 4)")
    print(f"  Extractions:  {ext_count} (expected 3)")

    ok = user_count >= 4 and doc_count >= 7 and txn_count >= 4 and ext_count >= 3
    if ok:
        print("\n  All demo data seeded successfully!")
    else:
        print("\n  WARNING: Some counts are lower than expected")

    await close_db()


if __name__ == "__main__":
    asyncio.run(main())
