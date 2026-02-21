"""Unit tests for User Management models and schemas (Phase 1)."""

from datetime import datetime, timezone, timedelta

import pytest

from schemas import (
    # Enums
    UserType,
    UserDocumentType,
    TransactionStatus,
    ParticipantStatus,
    PreApprovalStatus,
    OwnershipType,
    ParticipantRole,
    # Profile sub-documents
    AgentProfile,
    BuyerProfile,
    SellerProfile,
    LoanOfficerProfile,
    # Transaction sub-documents
    TransactionParticipant,
    DocumentRequirement,
    # Financial extraction schemas
    PreApprovalExtraction,
    BankStatementExtraction,
    PayStubExtraction,
    W2Extraction,
    ProofOfFundsExtraction,
    # Templates
    FINANCIAL_EXTRACTION_SCHEMAS,
    PURCHASE_BUYER_REQUIREMENTS,
    PURCHASE_SELLER_REQUIREMENTS,
    DEFAULT_PURCHASE_REQUIREMENTS,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestUserType:
    def test_values(self):
        assert UserType.BUYER == "buyer"
        assert UserType.SELLER == "seller"
        assert UserType.AGENT == "agent"
        assert UserType.LOAN_OFFICER == "loan_officer"

    def test_all_members(self):
        assert len(UserType) == 4


class TestUserDocumentType:
    def test_values(self):
        assert UserDocumentType.PRE_APPROVAL_LETTER == "pre_approval_letter"
        assert UserDocumentType.BANK_STATEMENT == "bank_statement"
        assert UserDocumentType.W2 == "w2"
        assert UserDocumentType.OTHER == "other"

    def test_all_members(self):
        assert len(UserDocumentType) == 9


class TestTransactionStatus:
    def test_lifecycle_stages(self):
        statuses = [s.value for s in TransactionStatus]
        assert "draft" in statuses
        assert "active" in statuses
        assert "under_contract" in statuses
        assert "pending_close" in statuses
        assert "closed" in statuses
        assert "cancelled" in statuses
        assert "expired" in statuses

    def test_all_members(self):
        assert len(TransactionStatus) == 7


class TestParticipantStatus:
    def test_values(self):
        assert ParticipantStatus.INVITED == "invited"
        assert ParticipantStatus.ACTIVE == "active"
        assert ParticipantStatus.REMOVED == "removed"


class TestPreApprovalStatus:
    def test_values(self):
        assert PreApprovalStatus.NONE == "none"
        assert PreApprovalStatus.FULLY_APPROVED == "fully_approved"


# ---------------------------------------------------------------------------
# Profile Sub-Document Tests
# ---------------------------------------------------------------------------


class TestAgentProfile:
    def test_defaults(self):
        profile = AgentProfile()
        assert profile.license_number is None
        assert profile.areas_served == []

    def test_full_profile(self):
        profile = AgentProfile(
            license_number="MT-12345",
            license_state="MT",
            license_expiry=datetime(2027, 6, 30, tzinfo=timezone.utc),
            brokerage_name="Test Realty",
            mls_id="MLS-001",
            areas_served=["Helena", "Bozeman"],
        )
        assert profile.license_number == "MT-12345"
        assert len(profile.areas_served) == 2

    def test_serialization_roundtrip(self):
        profile = AgentProfile(license_number="CA-99999", license_state="CA")
        data = profile.model_dump()
        restored = AgentProfile.model_validate(data)
        assert restored.license_number == "CA-99999"


class TestBuyerProfile:
    def test_defaults(self):
        profile = BuyerProfile()
        assert profile.pre_approval_status == PreApprovalStatus.NONE
        assert profile.annual_income is None

    def test_full_profile(self):
        profile = BuyerProfile(
            pre_approval_status=PreApprovalStatus.PRE_APPROVED,
            pre_approval_amount=500000.0,
            pre_approval_lender="Bank of Montana",
            purchase_budget_min=400000,
            purchase_budget_max=600000,
            first_time_buyer=True,
            employment_status="employed",
            employer_name="Tech Corp",
            annual_income=120000.0,
        )
        assert profile.pre_approval_amount == 500000.0
        assert profile.first_time_buyer is True


class TestSellerProfile:
    def test_defaults(self):
        profile = SellerProfile()
        assert profile.property_addresses == []
        assert profile.ownership_type is None

    def test_with_data(self):
        profile = SellerProfile(
            property_addresses=[{"street": "123 Main St", "city": "Helena"}],
            ownership_type=OwnershipType.JOINT,
        )
        assert len(profile.property_addresses) == 1
        assert profile.ownership_type == OwnershipType.JOINT


class TestLoanOfficerProfile:
    def test_defaults(self):
        profile = LoanOfficerProfile()
        assert profile.nmls_id is None
        assert profile.loan_types_offered == []

    def test_full_profile(self):
        profile = LoanOfficerProfile(
            nmls_id="123456",
            company_name="First National",
            company_nmls="789012",
            license_states=["MT", "WA", "OR"],
            loan_types_offered=["conventional", "FHA", "VA"],
            contact_preference="email",
        )
        assert len(profile.license_states) == 3
        assert "FHA" in profile.loan_types_offered


# ---------------------------------------------------------------------------
# Transaction Sub-Document Tests
# ---------------------------------------------------------------------------


class TestTransactionParticipant:
    def test_defaults(self):
        p = TransactionParticipant(
            user_id="user123",
            role=ParticipantRole.BUYER,
        )
        assert p.status == ParticipantStatus.INVITED
        assert p.removed_at is None

    def test_full_participant(self):
        now = datetime.now(timezone.utc)
        p = TransactionParticipant(
            user_id="user456",
            role=ParticipantRole.LISTING_AGENT,
            status=ParticipantStatus.ACTIVE,
            added_at=now,
            added_by="agent789",
            profile_completion=0.85,
        )
        assert p.profile_completion == 0.85
        assert p.status == ParticipantStatus.ACTIVE


class TestDocumentRequirement:
    def test_defaults(self):
        req = DocumentRequirement(
            doc_type=UserDocumentType.PRE_APPROVAL_LETTER,
            role=ParticipantRole.BUYER,
        )
        assert req.required is True
        assert req.satisfied is False
        assert req.satisfied_by is None

    def test_satisfied(self):
        req = DocumentRequirement(
            doc_type=UserDocumentType.BANK_STATEMENT,
            role=ParticipantRole.BUYER,
            satisfied=True,
            satisfied_by="doc123",
        )
        assert req.satisfied is True


# ---------------------------------------------------------------------------
# Financial Extraction Schema Tests
# ---------------------------------------------------------------------------


class TestPreApprovalExtraction:
    def test_empty(self):
        ex = PreApprovalExtraction()
        assert ex.lender_name is None
        assert ex.conditions == []

    def test_full(self):
        ex = PreApprovalExtraction(
            lender_name="First National Bank",
            approval_amount=450000.0,
            loan_type="conventional",
            expiration_date="2026-06-30",
            conditions=["Employment verification", "Appraisal required"],
        )
        assert ex.approval_amount == 450000.0
        assert len(ex.conditions) == 2


class TestBankStatementExtraction:
    def test_full(self):
        ex = BankStatementExtraction(
            institution_name="Chase Bank",
            account_holder="John Doe",
            account_type="checking",
            account_number_last4="4567",
            ending_balance=85000.50,
        )
        assert ex.ending_balance == 85000.50
        assert ex.account_number_last4 == "4567"


class TestPayStubExtraction:
    def test_full(self):
        ex = PayStubExtraction(
            employer_name="Tech Corp",
            gross_pay=5000.0,
            net_pay=3800.0,
            ytd_gross=60000.0,
            pay_frequency="semi-monthly",
        )
        assert ex.gross_pay == 5000.0


class TestW2Extraction:
    def test_pii_safety(self):
        """W2 only stores last 4 of SSN, not full SSN."""
        ex = W2Extraction(
            employee_ssn_last4="1234",
            wages_tips_compensation=95000.0,
            tax_year=2025,
        )
        assert ex.employee_ssn_last4 == "1234"
        assert len(ex.employee_ssn_last4) == 4


class TestProofOfFundsExtraction:
    def test_full(self):
        ex = ProofOfFundsExtraction(
            institution_name="Wells Fargo",
            available_funds=200000.0,
            currency="USD",
            letter_date="2026-02-15",
        )
        assert ex.available_funds == 200000.0


# ---------------------------------------------------------------------------
# Schema Map & Template Tests
# ---------------------------------------------------------------------------


class TestFinancialExtractionSchemas:
    def test_all_financial_types_have_schemas(self):
        assert UserDocumentType.PRE_APPROVAL_LETTER in FINANCIAL_EXTRACTION_SCHEMAS
        assert UserDocumentType.BANK_STATEMENT in FINANCIAL_EXTRACTION_SCHEMAS
        assert UserDocumentType.PAY_STUB in FINANCIAL_EXTRACTION_SCHEMAS
        assert UserDocumentType.W2 in FINANCIAL_EXTRACTION_SCHEMAS
        assert UserDocumentType.PROOF_OF_FUNDS in FINANCIAL_EXTRACTION_SCHEMAS

    def test_non_financial_types_not_mapped(self):
        assert UserDocumentType.DRIVERS_LICENSE not in FINANCIAL_EXTRACTION_SCHEMAS
        assert UserDocumentType.OTHER not in FINANCIAL_EXTRACTION_SCHEMAS

    def test_schema_instances_constructable(self):
        for doc_type, schema_cls in FINANCIAL_EXTRACTION_SCHEMAS.items():
            instance = schema_cls()
            assert instance is not None


class TestDocumentRequirementTemplates:
    def test_buyer_requirements_count(self):
        assert len(PURCHASE_BUYER_REQUIREMENTS) == 6

    def test_seller_requirements_count(self):
        assert len(PURCHASE_SELLER_REQUIREMENTS) == 2

    def test_combined_default_count(self):
        assert len(DEFAULT_PURCHASE_REQUIREMENTS) == 8

    def test_buyer_has_required_docs(self):
        required_types = {
            r.doc_type for r in PURCHASE_BUYER_REQUIREMENTS if r.required
        }
        assert UserDocumentType.PRE_APPROVAL_LETTER in required_types
        assert UserDocumentType.BANK_STATEMENT in required_types
        assert UserDocumentType.PROOF_OF_FUNDS in required_types
        assert UserDocumentType.DRIVERS_LICENSE in required_types

    def test_optional_docs_exist(self):
        optional_types = {
            r.doc_type for r in PURCHASE_BUYER_REQUIREMENTS if not r.required
        }
        assert UserDocumentType.PAY_STUB in optional_types
        assert UserDocumentType.W2 in optional_types

    def test_all_buyer_reqs_have_buyer_role(self):
        for req in PURCHASE_BUYER_REQUIREMENTS:
            assert req.role == ParticipantRole.BUYER

    def test_all_seller_reqs_have_seller_role(self):
        for req in PURCHASE_SELLER_REQUIREMENTS:
            assert req.role == ParticipantRole.SELLER


# ---------------------------------------------------------------------------
# Magic Link Tests
# ---------------------------------------------------------------------------


class TestMagicLink:
    def test_generate_token(self):
        from auth import generate_magic_link_token
        token = generate_magic_link_token()
        assert len(token) > 32  # urlsafe_b64 of 48 bytes = 64 chars
        # Each call should produce a unique token
        token2 = generate_magic_link_token()
        assert token != token2

    def test_sign_and_verify(self):
        from auth import sign_magic_link, verify_magic_link
        signed = sign_magic_link("test-token-123", "buyer@example.com", "txn-456")
        payload = verify_magic_link(signed)
        assert payload["token"] == "test-token-123"
        assert payload["email"] == "buyer@example.com"
        assert payload["txn_id"] == "txn-456"

    def test_sign_without_transaction(self):
        from auth import sign_magic_link, verify_magic_link
        signed = sign_magic_link("token-abc", "agent@example.com")
        payload = verify_magic_link(signed)
        assert payload["email"] == "agent@example.com"
        assert "txn_id" not in payload

    def test_tampered_signature_rejected(self):
        from auth import sign_magic_link, verify_magic_link
        from fastapi import HTTPException
        signed = sign_magic_link("token-x", "test@example.com")
        tampered = signed[:-5] + "XXXXX"
        with pytest.raises(HTTPException) as exc_info:
            verify_magic_link(tampered)
        assert exc_info.value.status_code == 400

    def test_malformed_token_rejected(self):
        from auth import verify_magic_link
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            verify_magic_link("not-a-valid-token")
