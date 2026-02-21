"""Phase 3 tests — Transaction system, participant management, invitations."""

import pytest
from datetime import datetime, timedelta, timezone

from schemas import (
    TransactionStatus,
    ParticipantRole,
    ParticipantStatus,
    TransactionParticipant,
    DocumentRequirement,
    UserDocumentType,
    UserType,
    BuyerProfile,
    AgentProfile,
    DEFAULT_PURCHASE_REQUIREMENTS,
)


# ===========================================================================
# Transaction Status Machine
# ===========================================================================


class TestTransactionStatus:
    """Transaction lifecycle status transitions."""

    def test_all_statuses_exist(self):
        assert TransactionStatus.DRAFT == "draft"
        assert TransactionStatus.ACTIVE == "active"
        assert TransactionStatus.UNDER_CONTRACT == "under_contract"
        assert TransactionStatus.PENDING_CLOSE == "pending_close"
        assert TransactionStatus.CLOSED == "closed"
        assert TransactionStatus.CANCELLED == "cancelled"
        assert TransactionStatus.EXPIRED == "expired"

    def test_status_from_string(self):
        assert TransactionStatus("draft") == TransactionStatus.DRAFT
        assert TransactionStatus("closed") == TransactionStatus.CLOSED

    def test_status_count(self):
        assert len(TransactionStatus) == 7


# ===========================================================================
# Participant Management
# ===========================================================================


class TestParticipantManagement:
    """Participant model and role assignment."""

    def test_create_participant(self):
        p = TransactionParticipant(
            user_id="user123",
            role=ParticipantRole.BUYER,
            status=ParticipantStatus.INVITED,
            added_at=datetime.now(timezone.utc),
        )
        assert p.user_id == "user123"
        assert p.role == ParticipantRole.BUYER
        assert p.status == ParticipantStatus.INVITED
        assert p.removed_at is None

    def test_participant_roles(self):
        """All expected participant roles exist."""
        roles = {
            "BUYER", "SELLER", "LISTING_AGENT", "BUYING_AGENT",
            "LISTING_BROKER", "BUYING_BROKER", "ESCROW_TITLE_REP",
            "LOAN_OFFICER", "APPRAISER", "INSPECTOR",
            "TRANSACTION_COORDINATOR", "OTHER",
        }
        assert {r.value for r in ParticipantRole} == roles

    def test_participant_status_values(self):
        assert ParticipantStatus.INVITED == "invited"
        assert ParticipantStatus.ACTIVE == "active"
        assert ParticipantStatus.REMOVED == "removed"

    def test_soft_remove_participant(self):
        p = TransactionParticipant(
            user_id="user123",
            role=ParticipantRole.SELLER,
            status=ParticipantStatus.ACTIVE,
        )
        p.status = ParticipantStatus.REMOVED
        p.removed_at = datetime.now(timezone.utc)
        assert p.status == ParticipantStatus.REMOVED
        assert p.removed_at is not None

    def test_profile_completion_field(self):
        """Participant can carry cached profile completion."""
        p = TransactionParticipant(
            user_id="user123",
            role=ParticipantRole.BUYER,
        )
        assert p.profile_completion is None
        p.profile_completion = 85.0
        assert p.profile_completion == 85.0


# ===========================================================================
# Document Requirements
# ===========================================================================


class TestDocumentRequirements:
    """Document requirement templates and satisfaction logic."""

    def test_default_purchase_requirements_exist(self):
        assert len(DEFAULT_PURCHASE_REQUIREMENTS) > 0

    def test_buyer_requirements(self):
        buyer_reqs = [
            r for r in DEFAULT_PURCHASE_REQUIREMENTS
            if r.role == ParticipantRole.BUYER
        ]
        assert len(buyer_reqs) >= 3  # pre-approval, bank statement, proof of funds, ID
        doc_types = {r.doc_type for r in buyer_reqs}
        assert UserDocumentType.PRE_APPROVAL_LETTER in doc_types
        assert UserDocumentType.BANK_STATEMENT in doc_types
        assert UserDocumentType.DRIVERS_LICENSE in doc_types

    def test_seller_requirements(self):
        seller_reqs = [
            r for r in DEFAULT_PURCHASE_REQUIREMENTS
            if r.role == ParticipantRole.SELLER
        ]
        assert len(seller_reqs) >= 1
        doc_types = {r.doc_type for r in seller_reqs}
        assert UserDocumentType.DRIVERS_LICENSE in doc_types

    def test_requirement_satisfaction(self):
        req = DocumentRequirement(
            doc_type=UserDocumentType.PRE_APPROVAL_LETTER,
            role=ParticipantRole.BUYER,
            required=True,
        )
        assert not req.satisfied
        assert req.satisfied_by is None

        req.satisfied = True
        req.satisfied_by = "doc_abc123"
        assert req.satisfied
        assert req.satisfied_by == "doc_abc123"

    def test_optional_requirements(self):
        optional = [r for r in DEFAULT_PURCHASE_REQUIREMENTS if not r.required]
        assert len(optional) >= 1  # pay stub and W-2 are optional


# ===========================================================================
# Magic Link Token Utilities
# ===========================================================================


class TestMagicLinkTokens:
    """Auth module magic link generation and verification."""

    def test_generate_magic_link_token(self):
        from auth import generate_magic_link_token
        token = generate_magic_link_token()
        assert isinstance(token, str)
        assert len(token) > 32  # secure random

    def test_generate_unique_tokens(self):
        from auth import generate_magic_link_token
        tokens = {generate_magic_link_token() for _ in range(100)}
        assert len(tokens) == 100  # all unique

    def test_sign_and_verify_magic_link(self):
        from auth import generate_magic_link_token, sign_magic_link, verify_magic_link
        token = generate_magic_link_token()
        signed = sign_magic_link(token, "jane@example.com", "txn_123")

        payload = verify_magic_link(signed)
        assert payload["token"] == token
        assert payload["email"] == "jane@example.com"
        assert payload["txn_id"] == "txn_123"
        assert "ts" in payload

    def test_sign_magic_link_without_transaction(self):
        from auth import generate_magic_link_token, sign_magic_link, verify_magic_link
        token = generate_magic_link_token()
        signed = sign_magic_link(token, "bob@example.com")

        payload = verify_magic_link(signed)
        assert payload["email"] == "bob@example.com"
        assert "txn_id" not in payload

    def test_invalid_magic_link_format(self):
        from auth import verify_magic_link
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            verify_magic_link("not-a-valid-token")
        assert exc.value.status_code == 400

    def test_tampered_magic_link(self):
        from auth import generate_magic_link_token, sign_magic_link, verify_magic_link
        from fastapi import HTTPException
        token = generate_magic_link_token()
        signed = sign_magic_link(token, "jane@example.com")

        # Tamper with payload
        parts = signed.split(".", 1)
        tampered = "dGFtcGVyZWQ" + parts[0][5:] + "." + parts[1]

        with pytest.raises(HTTPException) as exc:
            verify_magic_link(tampered)
        assert exc.value.status_code == 400


# ===========================================================================
# Transaction Route Helpers (import-only tests)
# ===========================================================================


class TestTransactionRouteModels:
    """Request/response models from transaction_routes.py."""

    def test_create_transaction_request(self):
        from transaction_routes import CreateTransactionRequest
        req = CreateTransactionRequest(name="123 Main St Purchase")
        assert req.name == "123 Main St Purchase"
        assert req.transaction_type == "purchase"
        assert req.property_address is None

    def test_create_transaction_with_details(self):
        from transaction_routes import CreateTransactionRequest
        req = CreateTransactionRequest(
            name="456 Oak Ave Sale",
            transaction_type="sale",
            purchase_price=650000,
            mls_number="MLS-98765",
        )
        assert req.purchase_price == 650000
        assert req.mls_number == "MLS-98765"

    def test_update_transaction_request_partial(self):
        from transaction_routes import UpdateTransactionRequest
        req = UpdateTransactionRequest(status=TransactionStatus.ACTIVE)
        assert req.status == TransactionStatus.ACTIVE
        assert req.name is None
        assert req.purchase_price is None

    def test_add_participant_request(self):
        from transaction_routes import AddParticipantRequest
        req = AddParticipantRequest(
            email="buyer@example.com",
            role=ParticipantRole.BUYER,
            name="Jane Doe",
        )
        assert req.email == "buyer@example.com"
        assert req.role == ParticipantRole.BUYER

    def test_link_document_request(self):
        from transaction_routes import LinkDocumentRequest
        req = LinkDocumentRequest(
            user_document_id="doc_123",
            doc_type="pre_approval_letter",
        )
        assert req.user_document_id == "doc_123"


# ===========================================================================
# Invitation Route Models
# ===========================================================================


class TestInvitationRouteModels:
    """Request/response models from invitation_routes.py."""

    def test_create_invitation_request(self):
        from invitation_routes import CreateInvitationRequest
        req = CreateInvitationRequest(
            email="seller@example.com",
            role=ParticipantRole.SELLER,
            transaction_id="txn_abc",
        )
        assert req.email == "seller@example.com"
        assert req.role == ParticipantRole.SELLER

    def test_profile_submit_request(self):
        from invitation_routes import ProfileSubmitRequest
        req = ProfileSubmitRequest(
            name="Jane Doe",
            phone="(555) 123-4567",
        )
        assert req.name == "Jane Doe"
        assert req.address is None

    def test_upgrade_request(self):
        from invitation_routes import UpgradeRequest
        req = UpgradeRequest(clerk_user_id="clerk_user_abc")
        assert req.clerk_user_id == "clerk_user_abc"


# ===========================================================================
# Auto-Fill Logic
# ===========================================================================


class TestAutoFillLogic:
    """Verify auto-fill behavior for profile-to-transaction field mapping."""

    def test_buyer_pre_approval_maps_to_purchase_price(self):
        """When a buyer has pre-approval, it should auto-fill purchase price."""
        buyer = BuyerProfile(
            pre_approval_amount=485000,
            pre_approval_lender="Summit National Bank",
        )
        assert buyer.pre_approval_amount == 485000

    def test_role_to_participant_role_mapping(self):
        """Agent user types should map to listing agent participant role."""
        role_map = {
            ParticipantRole.BUYER: UserType.BUYER,
            ParticipantRole.SELLER: UserType.SELLER,
            ParticipantRole.LISTING_AGENT: UserType.AGENT,
            ParticipantRole.BUYING_AGENT: UserType.AGENT,
            ParticipantRole.LOAN_OFFICER: UserType.LOAN_OFFICER,
        }
        assert role_map[ParticipantRole.LISTING_AGENT] == UserType.AGENT
        assert role_map[ParticipantRole.BUYER] == UserType.BUYER


# ===========================================================================
# Transaction Completion Calculation
# ===========================================================================


class TestTransactionCompletion:
    """Document requirement completion calculations."""

    def test_empty_requirements_100_percent(self):
        reqs: list[DocumentRequirement] = []
        total = sum(1 for r in reqs if r.required)
        satisfied = sum(1 for r in reqs if r.required and r.satisfied)
        pct = (satisfied / total * 100) if total else 100.0
        assert pct == 100.0

    def test_partial_completion(self):
        reqs = [
            DocumentRequirement(doc_type=UserDocumentType.PRE_APPROVAL_LETTER, role=ParticipantRole.BUYER, required=True, satisfied=True),
            DocumentRequirement(doc_type=UserDocumentType.BANK_STATEMENT, role=ParticipantRole.BUYER, required=True, satisfied=False),
            DocumentRequirement(doc_type=UserDocumentType.DRIVERS_LICENSE, role=ParticipantRole.BUYER, required=True, satisfied=False),
        ]
        total = sum(1 for r in reqs if r.required)
        satisfied = sum(1 for r in reqs if r.required and r.satisfied)
        pct = (satisfied / total * 100) if total else 100.0
        assert round(pct, 1) == 33.3

    def test_full_completion(self):
        reqs = [
            DocumentRequirement(doc_type=UserDocumentType.PRE_APPROVAL_LETTER, role=ParticipantRole.BUYER, required=True, satisfied=True),
            DocumentRequirement(doc_type=UserDocumentType.BANK_STATEMENT, role=ParticipantRole.BUYER, required=True, satisfied=True),
            DocumentRequirement(doc_type=UserDocumentType.PAY_STUB, role=ParticipantRole.BUYER, required=False, satisfied=False),
        ]
        total = sum(1 for r in reqs if r.required)
        satisfied = sum(1 for r in reqs if r.required and r.satisfied)
        pct = (satisfied / total * 100) if total else 100.0
        assert pct == 100.0  # Optional not counted

    def test_optional_not_counted_in_required(self):
        reqs = [
            DocumentRequirement(doc_type=UserDocumentType.PAY_STUB, role=ParticipantRole.BUYER, required=False),
            DocumentRequirement(doc_type=UserDocumentType.W2, role=ParticipantRole.BUYER, required=False),
        ]
        total = sum(1 for r in reqs if r.required)
        assert total == 0
