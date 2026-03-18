from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from schemas import DotloopPropertyAddress, TransactionStatus


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
        self.document_requirements = []
        self.participants = []
        self.updated_at = datetime.now(timezone.utc)
        self.save = AsyncMock()


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
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
        ):
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
