"""Phase 4 tests — AI Chatbot Profile Builder."""

import json
import pytest

from schemas import (
    UserType,
    PreApprovalStatus,
    OwnershipType,
    AgentProfile,
    BuyerProfile,
    SellerProfile,
    LoanOfficerProfile,
)


# ===========================================================================
# System Prompt Construction
# ===========================================================================


class TestSystemPrompt:
    """System prompt built from profile state."""

    def _make_user(self):
        """Create a mock user for prompt testing."""
        from unittest.mock import MagicMock
        user = MagicMock()
        user.name = "Jane Doe"
        user.email = "jane@example.com"
        user.phone = "(555) 123-4567"
        user.address = None
        user.user_types = [UserType.BUYER]
        user.agent_profile = None
        user.buyer_profile = BuyerProfile(
            pre_approval_status=PreApprovalStatus.PRE_APPROVED,
            pre_approval_amount=485000,
            employer_name="Acme Corp",
        )
        user.seller_profile = None
        user.loan_officer_profile = None
        return user

    def test_prompt_includes_profile_state(self):
        from chat_routes import _build_system_prompt
        user = self._make_user()
        completion = {"overall": 65, "roles": {"buyer": 80}, "missing_fields": {"buyer": ["annual_income"]}}
        prompt = _build_system_prompt(user, completion)

        assert "Jane Doe" in prompt
        assert "jane@example.com" in prompt
        assert "(555) 123-4567" in prompt
        assert "buyer" in prompt.lower()
        assert "485000" in prompt

    def test_prompt_includes_missing_fields(self):
        from chat_routes import _build_system_prompt
        user = self._make_user()
        completion = {"overall": 50, "roles": {}, "missing_fields": {"shared": ["address"], "buyer": ["annual_income"]}}
        prompt = _build_system_prompt(user, completion)

        assert "annual_income" in prompt
        assert "address" in prompt

    def test_prompt_includes_extraction_format(self):
        from chat_routes import _build_system_prompt
        user = self._make_user()
        completion = {"overall": 50, "roles": {}, "missing_fields": {}}
        prompt = _build_system_prompt(user, completion)

        assert "```json" in prompt
        assert '"extracted"' in prompt
        assert '"field"' in prompt

    def test_prompt_includes_all_role_fields(self):
        from chat_routes import _build_system_prompt
        user = self._make_user()
        completion = {"overall": 50, "roles": {}, "missing_fields": {}}
        prompt = _build_system_prompt(user, completion)

        # Check that valid fields are documented
        assert "license_number" in prompt
        assert "nmls_id" in prompt
        assert "pre_approval_amount" in prompt
        assert "ownership_type" in prompt

    def test_prompt_shows_agent_state_when_agent(self):
        from chat_routes import _build_system_prompt
        user = self._make_user()
        user.user_types = [UserType.AGENT]
        user.agent_profile = AgentProfile(
            license_number="AG-12345",
            license_state="CO",
            brokerage_name="Summit Realty",
        )
        user.buyer_profile = None
        completion = {"overall": 40, "roles": {}, "missing_fields": {}}
        prompt = _build_system_prompt(user, completion)

        assert "AG-12345" in prompt
        assert "Summit Realty" in prompt


# ===========================================================================
# JSON Extraction Parsing
# ===========================================================================


class TestJsonExtractionParsing:
    """Parse extracted fields JSON from AI responses."""

    def test_parse_basic_extraction(self):
        from chat_routes import _parse_extracted_json
        reply = 'Great! Let me update that.\n```json\n{"extracted": [{"field": "name", "value": "Jane Doe", "section": "shared"}]}\n```'
        result = _parse_extracted_json(reply)
        assert len(result) == 1
        assert result[0]["field"] == "name"
        assert result[0]["value"] == "Jane Doe"

    def test_parse_multiple_fields(self):
        from chat_routes import _parse_extracted_json
        reply = 'Got it!\n```json\n{"extracted": [{"field": "name", "value": "Jane", "section": "shared"}, {"field": "phone", "value": "555-1234", "section": "shared"}]}\n```'
        result = _parse_extracted_json(reply)
        assert len(result) == 2

    def test_parse_no_json_block(self):
        from chat_routes import _parse_extracted_json
        reply = "What is your name?"
        result = _parse_extracted_json(reply)
        assert result == []

    def test_parse_invalid_json(self):
        from chat_routes import _parse_extracted_json
        reply = '```json\n{invalid json}\n```'
        result = _parse_extracted_json(reply)
        assert result == []

    def test_clean_reply_removes_json(self):
        from chat_routes import _clean_reply
        reply = 'Great, I updated your name!\n```json\n{"extracted": [{"field": "name", "value": "Jane", "section": "shared"}]}\n```\n'
        cleaned = _clean_reply(reply)
        assert "```json" not in cleaned
        assert "extracted" not in cleaned
        assert "Great, I updated your name!" in cleaned


# ===========================================================================
# Field Application Logic
# ===========================================================================


class TestFieldApplication:
    """Apply extracted fields to user profile."""

    def _make_user(self):
        from unittest.mock import MagicMock
        user = MagicMock()
        user.name = ""
        user.phone = None
        user.address = None
        user.user_types = [UserType.BUYER, UserType.AGENT]
        user.agent_profile = AgentProfile()
        user.buyer_profile = BuyerProfile()
        user.seller_profile = None
        user.loan_officer_profile = None
        return user

    def test_apply_shared_name(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        fields = [{"field": "name", "value": "Jane Marie Doe", "section": "shared"}]
        applied = _apply_extracted_fields(user, fields)
        assert len(applied) == 1
        assert user.name == "Jane Marie Doe"

    def test_apply_shared_phone(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        fields = [{"field": "phone", "value": "(555) 987-6543", "section": "shared"}]
        applied = _apply_extracted_fields(user, fields)
        assert len(applied) == 1
        assert user.phone == "(555) 987-6543"

    def test_apply_buyer_fields(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        fields = [
            {"field": "pre_approval_amount", "value": "500000", "section": "buyer"},
            {"field": "employer_name", "value": "Tech Corp", "section": "buyer"},
            {"field": "annual_income", "value": "$120,000", "section": "buyer"},
        ]
        applied = _apply_extracted_fields(user, fields)
        assert len(applied) == 3
        assert user.buyer_profile.pre_approval_amount == 500000.0
        assert user.buyer_profile.employer_name == "Tech Corp"
        assert user.buyer_profile.annual_income == 120000.0

    def test_apply_agent_fields(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        fields = [
            {"field": "license_number", "value": "AG-99999", "section": "agent"},
            {"field": "license_state", "value": "CO", "section": "agent"},
            {"field": "brokerage_name", "value": "Peak Realty", "section": "agent"},
            {"field": "areas_served", "value": "Denver, Boulder, Aurora", "section": "agent"},
        ]
        applied = _apply_extracted_fields(user, fields)
        assert len(applied) == 4
        assert user.agent_profile.license_number == "AG-99999"
        assert user.agent_profile.areas_served == ["Denver", "Boulder", "Aurora"]

    def test_apply_add_role(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        user.user_types = []
        user.agent_profile = None
        user.buyer_profile = None
        fields = [{"field": "add_role", "value": "buyer", "section": "shared"}]
        applied = _apply_extracted_fields(user, fields)
        assert len(applied) == 1
        assert UserType.BUYER in user.user_types
        assert user.buyer_profile is not None

    def test_apply_pre_approval_status(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        fields = [{"field": "pre_approval_status", "value": "pre_approved", "section": "buyer"}]
        applied = _apply_extracted_fields(user, fields)
        assert user.buyer_profile.pre_approval_status == PreApprovalStatus.PRE_APPROVED

    def test_apply_first_time_buyer(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        fields = [{"field": "first_time_buyer", "value": "yes", "section": "buyer"}]
        applied = _apply_extracted_fields(user, fields)
        assert user.buyer_profile.first_time_buyer is True

    def test_apply_loan_officer_fields(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        user.user_types.append(UserType.LOAN_OFFICER)
        user.loan_officer_profile = LoanOfficerProfile()
        fields = [
            {"field": "nmls_id", "value": "123456", "section": "loan_officer"},
            {"field": "company_name", "value": "First National", "section": "loan_officer"},
            {"field": "loan_types_offered", "value": "conventional, FHA, VA", "section": "loan_officer"},
        ]
        applied = _apply_extracted_fields(user, fields)
        assert len(applied) == 3
        assert user.loan_officer_profile.nmls_id == "123456"
        assert user.loan_officer_profile.loan_types_offered == ["conventional", "FHA", "VA"]

    def test_skip_invalid_section(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        user.seller_profile = None  # No seller role
        fields = [{"field": "ownership_type", "value": "sole", "section": "seller"}]
        applied = _apply_extracted_fields(user, fields)
        assert len(applied) == 0  # Skipped — no seller profile

    def test_skip_empty_value(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        fields = [{"field": "name", "value": "", "section": "shared"}]
        applied = _apply_extracted_fields(user, fields)
        assert len(applied) == 0

    def test_apply_dollar_amount_parsing(self):
        from chat_routes import _apply_extracted_fields
        user = self._make_user()
        fields = [{"field": "purchase_budget_max", "value": "$750,000", "section": "buyer"}]
        applied = _apply_extracted_fields(user, fields)
        assert user.buyer_profile.purchase_budget_max == 750000.0


# ===========================================================================
# Route Models
# ===========================================================================


class TestChatRouteModels:
    """Request/response models from chat_routes.py."""

    def test_chat_message_request(self):
        from chat_routes import ChatMessageRequest
        req = ChatMessageRequest(message="I'm a buyer in Denver")
        assert req.message == "I'm a buyer in Denver"
        assert req.session_id is None

    def test_chat_message_request_with_session(self):
        from chat_routes import ChatMessageRequest
        req = ChatMessageRequest(message="My budget is 500k", session_id="chat-abc123")
        assert req.session_id == "chat-abc123"

    def test_extracted_field_model(self):
        from chat_routes import ExtractedField
        field = ExtractedField(field="name", value="Jane", section="shared")
        assert field.field == "name"
        assert field.section == "shared"

    def test_chat_response_model(self):
        from chat_routes import ChatMessageResponse, ExtractedField
        resp = ChatMessageResponse(
            reply="Great!",
            session_id="chat-123",
            extracted_fields=[ExtractedField(field="name", value="Jane", section="shared")],
            profile_updated=True,
            completion_before=15.0,
            completion_after=30.0,
        )
        assert resp.profile_updated
        assert resp.completion_after > resp.completion_before
        assert len(resp.extracted_fields) == 1
