"""Phase 2 unit tests: profile routes, document routes, extraction mapping, completion."""

import sys
import os
import pytest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from schemas import (
    AgentProfile,
    BuyerProfile,
    LoanOfficerProfile,
    SellerProfile,
    UserType,
    UserDocumentType,
    PreApprovalStatus,
    OwnershipType,
    FINANCIAL_EXTRACTION_SCHEMAS,
)


# ============================================================================
# Profile Completion Logic Tests
# ============================================================================


class TestProfileCompletion:
    """Test the profile completion calculation logic."""

    def _compute_role_completion(self, user_type, profile):
        """Replicate profile_routes._role_tracked_fields logic for testing."""
        from profile_routes import _role_tracked_fields

        fields = _role_tracked_fields(user_type)
        if not fields:
            return 100.0, []

        filled = 0
        missing = []
        for field_name, label in fields:
            val = getattr(profile, field_name, None)
            if val is not None and val != "" and val != []:
                filled += 1
            else:
                missing.append(label)

        pct = (filled / len(fields) * 100) if fields else 100.0
        return round(pct, 1), missing

    def test_agent_empty_completion(self):
        profile = AgentProfile()
        pct, missing = self._compute_role_completion(UserType.AGENT, profile)
        assert pct == 0.0
        assert len(missing) == 4

    def test_agent_full_completion(self):
        profile = AgentProfile(
            license_number="RE-123",
            license_state="CA",
            brokerage_name="KW",
            mls_id="MLS-456",
        )
        pct, missing = self._compute_role_completion(UserType.AGENT, profile)
        assert pct == 100.0
        assert len(missing) == 0

    def test_agent_partial_completion(self):
        profile = AgentProfile(license_number="RE-123", license_state="CA")
        pct, missing = self._compute_role_completion(UserType.AGENT, profile)
        assert pct == 50.0
        assert "Brokerage Name" in missing
        assert "MLS ID" in missing

    def test_buyer_empty_completion(self):
        profile = BuyerProfile()
        pct, missing = self._compute_role_completion(UserType.BUYER, profile)
        # pre_approval_status has default NONE which is not empty
        assert pct > 0
        assert len(missing) > 0

    def test_buyer_full_completion(self):
        profile = BuyerProfile(
            pre_approval_status=PreApprovalStatus.PRE_APPROVED,
            pre_approval_amount=500000,
            pre_approval_lender="Wells Fargo",
            employment_status="employed",
            employer_name="Google",
            annual_income=120000,
        )
        pct, missing = self._compute_role_completion(UserType.BUYER, profile)
        assert pct == 100.0

    def test_seller_empty_completion(self):
        profile = SellerProfile()
        pct, missing = self._compute_role_completion(UserType.SELLER, profile)
        assert pct == 0.0
        assert "Ownership Type" in missing

    def test_seller_full_completion(self):
        profile = SellerProfile(
            property_addresses=[{"street": "123 Main"}],
            ownership_type=OwnershipType.SOLE,
        )
        pct, missing = self._compute_role_completion(UserType.SELLER, profile)
        assert pct == 100.0

    def test_loan_officer_empty_completion(self):
        profile = LoanOfficerProfile()
        pct, missing = self._compute_role_completion(UserType.LOAN_OFFICER, profile)
        assert pct == 0.0
        assert len(missing) == 4

    def test_loan_officer_full_completion(self):
        profile = LoanOfficerProfile(
            nmls_id="123456",
            company_name="Quicken",
            license_states=["CA", "NY"],
            loan_types_offered=["conventional", "FHA"],
        )
        pct, missing = self._compute_role_completion(UserType.LOAN_OFFICER, profile)
        assert pct == 100.0


# ============================================================================
# Extraction-to-Profile Mapping Tests
# ============================================================================


class TestExtractionMapping:
    """Test extraction results mapping to profile fields."""

    def test_pre_approval_mapping(self):
        from profile_extraction import _apply_pre_approval, _ensure_buyer_profile

        # Create a mock user-like object
        class MockUser:
            def __init__(self):
                self.user_types = []
                self.buyer_profile = None
                self.name = ""

        user = MockUser()
        _ensure_buyer_profile(user)

        data = {
            "approval_amount": 500000,
            "lender_name": "Wells Fargo",
            "borrower_name": "John Doe",
        }

        changed = _apply_pre_approval(user, data)
        assert changed is True
        assert user.buyer_profile.pre_approval_amount == 500000
        assert user.buyer_profile.pre_approval_lender == "Wells Fargo"
        assert user.buyer_profile.pre_approval_status == PreApprovalStatus.PRE_APPROVED
        assert user.name == "John Doe"

    def test_pre_approval_no_overwrite(self):
        from profile_extraction import _apply_pre_approval, _ensure_buyer_profile

        class MockUser:
            def __init__(self):
                self.user_types = []
                self.buyer_profile = None
                self.name = "Existing Name"

        user = MockUser()
        _ensure_buyer_profile(user)
        user.buyer_profile.pre_approval_amount = 300000
        user.buyer_profile.pre_approval_lender = "Chase"

        data = {
            "approval_amount": 500000,
            "lender_name": "Wells Fargo",
            "borrower_name": "John Doe",
        }

        _apply_pre_approval(user, data)
        # Should NOT overwrite existing values
        assert user.buyer_profile.pre_approval_amount == 300000
        assert user.buyer_profile.pre_approval_lender == "Chase"
        assert user.name == "Existing Name"

    def test_pay_stub_annual_income_calculation(self):
        from profile_extraction import _apply_pay_stub, _ensure_buyer_profile

        class MockUser:
            def __init__(self):
                self.user_types = []
                self.buyer_profile = None
                self.name = ""

        user = MockUser()
        _ensure_buyer_profile(user)

        data = {
            "gross_pay": 5000.00,
            "pay_frequency": "biweekly",
            "employer_name": "Acme Corp",
            "employee_name": "Jane Smith",
        }

        changed = _apply_pay_stub(user, data)
        assert changed is True
        assert user.buyer_profile.annual_income == 130000.00  # 5000 * 26
        assert user.buyer_profile.employer_name == "Acme Corp"
        assert user.buyer_profile.employment_status == "employed"
        assert user.name == "Jane Smith"

    def test_pay_stub_ytd_preferred(self):
        from profile_extraction import _apply_pay_stub, _ensure_buyer_profile

        class MockUser:
            def __init__(self):
                self.user_types = []
                self.buyer_profile = None
                self.name = "Already Set"

        user = MockUser()
        _ensure_buyer_profile(user)

        data = {
            "ytd_gross": 95000.00,
            "gross_pay": 5000.00,
            "pay_frequency": "biweekly",
        }

        _apply_pay_stub(user, data)
        # YTD gross should be preferred over calculated annual
        assert user.buyer_profile.annual_income == 95000.00

    def test_w2_mapping(self):
        from profile_extraction import _apply_w2, _ensure_buyer_profile

        class MockUser:
            def __init__(self):
                self.user_types = []
                self.buyer_profile = None
                self.name = ""

        user = MockUser()
        _ensure_buyer_profile(user)

        data = {
            "wages_tips_compensation": 85000.00,
            "employer_name": "BigCo",
            "employee_name": "Bob Builder",
        }

        changed = _apply_w2(user, data)
        assert changed is True
        assert user.buyer_profile.annual_income == 85000.00
        assert user.buyer_profile.employer_name == "BigCo"
        assert user.name == "Bob Builder"

    def test_bank_statement_mapping(self):
        from profile_extraction import _apply_bank_statement, _ensure_buyer_profile

        class MockUser:
            def __init__(self):
                self.user_types = []
                self.buyer_profile = None
                self.name = ""

        user = MockUser()
        _ensure_buyer_profile(user)

        data = {"account_holder": "Alice Wonderland"}
        changed = _apply_bank_statement(user, data)
        assert changed is True
        assert user.name == "Alice Wonderland"

    def test_proof_of_funds_mapping(self):
        from profile_extraction import _apply_proof_of_funds, _ensure_buyer_profile

        class MockUser:
            def __init__(self):
                self.user_types = []
                self.buyer_profile = None
                self.name = ""

        user = MockUser()
        _ensure_buyer_profile(user)

        data = {"account_holder": "Charlie Brown"}
        changed = _apply_proof_of_funds(user, data)
        assert changed is True
        assert user.name == "Charlie Brown"


# ============================================================================
# Financial Extraction Prompt Tests
# ============================================================================


class TestFinancialExtractionPrompts:
    """Test that extraction prompts are properly configured."""

    def test_all_financial_types_have_prompts(self):
        from profile_extraction import FINANCIAL_SYSTEM_PROMPTS

        for doc_type in FINANCIAL_EXTRACTION_SCHEMAS:
            assert doc_type in FINANCIAL_SYSTEM_PROMPTS, f"Missing prompt for {doc_type}"

    def test_prompts_contain_json_instruction(self):
        from profile_extraction import FINANCIAL_SYSTEM_PROMPTS

        for doc_type, prompt in FINANCIAL_SYSTEM_PROMPTS.items():
            assert "JSON" in prompt or "json" in prompt, f"Prompt for {doc_type} should mention JSON"

    def test_prompts_contain_null_instruction(self):
        from profile_extraction import FINANCIAL_SYSTEM_PROMPTS

        for doc_type, prompt in FINANCIAL_SYSTEM_PROMPTS.items():
            assert "null" in prompt, f"Prompt for {doc_type} should instruct null for missing"

    def test_prompts_mention_pii_safety(self):
        """PII-sensitive prompts should mention 'last 4' for SSN/account numbers."""
        from profile_extraction import FINANCIAL_SYSTEM_PROMPTS

        # Bank statement should mention last 4 for account numbers
        bs_prompt = FINANCIAL_SYSTEM_PROMPTS[UserDocumentType.BANK_STATEMENT]
        assert "last 4" in bs_prompt.lower() or "LAST 4" in bs_prompt

        # W-2 should mention last 4 for SSN
        w2_prompt = FINANCIAL_SYSTEM_PROMPTS[UserDocumentType.W2]
        assert "last 4" in w2_prompt.lower() or "LAST 4" in w2_prompt

    def test_prompt_count_matches_schema_count(self):
        from profile_extraction import FINANCIAL_SYSTEM_PROMPTS

        assert len(FINANCIAL_SYSTEM_PROMPTS) == len(FINANCIAL_EXTRACTION_SCHEMAS)


# ============================================================================
# Profile Route Helper Tests
# ============================================================================


class TestProfileRouteHelpers:
    """Test profile_routes helper functions."""

    def test_role_tracked_fields_agent(self):
        from profile_routes import _role_tracked_fields

        fields = _role_tracked_fields(UserType.AGENT)
        assert len(fields) == 4
        field_names = [f[0] for f in fields]
        assert "license_number" in field_names
        assert "brokerage_name" in field_names

    def test_role_tracked_fields_buyer(self):
        from profile_routes import _role_tracked_fields

        fields = _role_tracked_fields(UserType.BUYER)
        assert len(fields) == 6
        field_names = [f[0] for f in fields]
        assert "annual_income" in field_names

    def test_role_tracked_fields_seller(self):
        from profile_routes import _role_tracked_fields

        fields = _role_tracked_fields(UserType.SELLER)
        assert len(fields) == 2

    def test_role_tracked_fields_loan_officer(self):
        from profile_routes import _role_tracked_fields

        fields = _role_tracked_fields(UserType.LOAN_OFFICER)
        assert len(fields) == 4
        field_names = [f[0] for f in fields]
        assert "nmls_id" in field_names
