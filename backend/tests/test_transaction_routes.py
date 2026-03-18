from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from schemas import (
    DocumentRequirement,
    DotloopPropertyAddress,
    ParticipantRole,
    ParticipantStatus,
    TransactionStatus,
    UserDocumentType,
)


class DummyUser:
    def __init__(self, user_id: str, name: str, email: str):
        self.id = user_id
        self.name = name
        self.email = email


class DummyTransaction:
    def __init__(self, property_address: DotloopPropertyAddress | None):
        self.id = "txn-123"
        self.created_by = "user-1"
        self.name = "2760 Carla Jo Lane"
        self.transaction_type = "purchase"
        self.status = TransactionStatus.DRAFT
        self.property_address = property_address
        self.mls_number = None
        self.purchase_price = None
        self.earnest_money = None
        self.closing_date = None
        self.document_requirements: list[DocumentRequirement] = []
        self.participants = []
        self.extraction_ids: list[str] = []
        self.agent_side = "seller"
        self.dotloop_loop_id = None
        self.dotloop_sync_status = None
        self.dotloop_last_synced_at = None
        self.dotloop_last_remote_updated_at = None
        self.dotloop_sync_error = None
        self.updated_at = datetime.now(timezone.utc)
        self.org_id = None
        self.save = AsyncMock()
        self.insert = AsyncMock()
        self.delete = AsyncMock()


@pytest.mark.asyncio
class TestTransactionRouteUpdates:
    async def test_update_transaction_merges_partial_property_address(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(
            DotloopPropertyAddress(
                street_number="2760",
                street_name="Carla Jo Lane",
                city="Missoula",
                state_or_province="ID",
                postal_code="59801",
            )
        )

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
            patch(
                "transaction_routes._serialize_transaction",
                side_effect=lambda value: {
                    "_id": value.id,
                    "transaction_type": value.transaction_type,
                    "property_address": value.property_address.model_dump(mode="json") if value.property_address else None,
                },
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.put(
                    "/api/transactions/txn-123",
                    json={
                        "transaction_type": "sale",
                        "property_address": {
                            "state_or_province": "MT",
                            "county": "Missoula",
                        },
                    },
                )

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["transaction_type"] == "sale"
            assert payload["property_address"]["street_number"] == "2760"
            assert payload["property_address"]["street_name"] == "Carla Jo Lane"
            assert payload["property_address"]["state_or_province"] == "MT"
            assert payload["property_address"]["county"] == "Missoula"
        finally:
            app.dependency_overrides.clear()

    async def test_update_transaction_rejects_incomplete_new_property_address(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.put(
                    "/api/transactions/txn-123",
                    json={
                        "property_address": {
                            "state_or_province": "MT",
                        },
                    },
                )

        try:
            assert response.status_code == 400
            assert "Property address is incomplete" in response.json()["detail"]
        finally:
            app.dependency_overrides.clear()

    async def test_completion_returns_setup_progress_with_blockers(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.agent_side = None
        txn.participants = [
            MagicMock(user_id="user-1", role=ParticipantRole.LISTING_AGENT, status=ParticipantStatus.ACTIVE),
            MagicMock(user_id="user-2", role=ParticipantRole.BUYER, status=ParticipantStatus.INVITED),
        ]
        txn.document_requirements = [
            DocumentRequirement(
                doc_type=UserDocumentType.PRE_APPROVAL_LETTER,
                role=ParticipantRole.BUYER,
                required=True,
                satisfied=False,
            )
        ]

        users = {
            "user-1": DummyUser("user-1", "Owner", "owner@example.com"),
            "user-2": DummyUser("user-2", "Buyer", "buyer@example.com"),
        }

        def compute_completion(user):
            overall = 100.0 if user.email == "owner@example.com" else 45.0
            return MagicMock(overall=overall)

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
            patch("transaction_routes.UserProfile.get", AsyncMock(side_effect=lambda user_id: users[user_id])),
            patch("profile_routes._compute_completion", side_effect=compute_completion),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/transactions/txn-123/completion")

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["kind"] == "setup_progress"
            assert {bucket["key"] for bucket in payload["buckets"]} == {
                "transaction_fields",
                "participant_acceptance",
                "participant_profiles",
                "required_documents",
            }
            assert any("Property address" in blocker for blocker in payload["blockers"])
            assert any("participant" in blocker.lower() for blocker in payload["blockers"])
            assert payload["documents"]["completion"] == 0.0
        finally:
            app.dependency_overrides.clear()

    async def test_preview_transaction_from_dotloop_returns_existing_transaction_id(self):
        from auth import get_current_user
        from server import app

        loop_detail = {
            "id": 321,
            "name": "123 Main Street",
            "transaction_type": "listing",
            "updated": "2026-03-18T16:00:00+00:00",
            "property_address": {
                "street_number": "123",
                "street_name": "Main Street",
                "city": "Missoula",
                "state_or_province": "MT",
                "postal_code": "59802",
            },
            "financials": {"purchase_price": "550000", "earnest_money": "5000"},
            "contract_dates": {"closing_date": "2026-04-20"},
            "participants": [{"full_name": "Buyer", "email": "buyer@example.com", "role": "BUYER"}],
            "documents": [{"id": 1, "name": "BuySell.pdf", "folder_id": 11, "folder_name": "Contracts"}],
        }

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1", dotloop_tokens=None)
        with (
            patch("transaction_routes.dotloop_configured", return_value=True),
            patch("transaction_routes.get_loop_with_details", return_value=loop_detail),
            patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=MagicMock(id="txn-existing"))),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/transactions/from-dotloop/321/preview")

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["existing_transaction_id"] == "txn-existing"
            assert payload["normalized_transaction"]["name"] == "123 Main Street"
            assert payload["normalized_transaction"]["agent_role"] == "listing_agent"
            assert payload["available_documents"]["pdf_count"] == 1
        finally:
            app.dependency_overrides.clear()

    async def test_create_transaction_from_dotloop_rejects_duplicate_loop_link(self):
        from auth import get_current_user
        from server import app

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=MagicMock(id="txn-existing"))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/transactions/from-dotloop/321")

        try:
            assert response.status_code == 409
            assert response.json()["detail"]["existing_transaction_id"] == "txn-existing"
        finally:
            app.dependency_overrides.clear()

    async def test_import_dotloop_documents_rejects_non_pdf(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.dotloop_loop_id = "321"

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
            patch("transaction_routes.dotloop_configured", return_value=True),
            patch("transaction_routes._import_dotloop_document", AsyncMock()) as import_mock,
            patch("transaction_routes._mark_transaction_dotloop_state", AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/transactions/txn-123/dotloop/import-documents",
                    json={
                        "documents": [
                            {"folder_id": 11, "document_id": 22, "name": "Disclosure.docx"},
                        ]
                    },
                )

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["failed"] == 1
            assert payload["results"][0]["error"] == "Only PDF documents can be imported."
            import_mock.assert_not_awaited()
        finally:
            app.dependency_overrides.clear()
