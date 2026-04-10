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
    TransactionParticipant,
    TransactionStatus,
    TransactionUploadJobStatus,
    UserDocumentType,
)


class DummyUser:
    def __init__(self, user_id: str, name: str, email: str):
        self.id = user_id
        self.name = name
        self.email = email


class FakeCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    async def to_list(self):
        return self.items


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

    async def test_update_transaction_sets_agent_side_and_creator_agent_role(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.agent_side = "buyer"
        txn.participants = [
            TransactionParticipant(
                user_id="user-1",
                role=ParticipantRole.BUYING_AGENT,
                status=ParticipantStatus.ACTIVE,
                added_at=datetime.now(timezone.utc),
            ),
            TransactionParticipant(
                user_id="user-2",
                role=ParticipantRole.BUYER,
                status=ParticipantStatus.INVITED,
                added_at=datetime.now(timezone.utc),
            ),
        ]

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_owned_transaction", AsyncMock(return_value=txn)),
            patch(
                "transaction_routes._serialize_transaction",
                side_effect=lambda value: {
                    "_id": value.id,
                    "agent_side": value.agent_side,
                    "participants": [
                        {"user_id": participant.user_id, "role": participant.role.value}
                        for participant in value.participants
                    ],
                },
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.put(
                    "/api/transactions/txn-123",
                    json={"agent_role": "listing_agent"},
                )

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["agent_side"] == "seller"
            assert payload["participants"][0]["role"] == "LISTING_AGENT"
            assert payload["participants"][1]["role"] == "BUYER"
        finally:
            app.dependency_overrides.clear()

    async def test_update_transaction_only_changes_side_when_creator_is_not_agent_participant(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.agent_side = "seller"
        txn.participants = [
            TransactionParticipant(
                user_id="user-1",
                role=ParticipantRole.SELLER,
                status=ParticipantStatus.ACTIVE,
                added_at=datetime.now(timezone.utc),
            ),
        ]

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_owned_transaction", AsyncMock(return_value=txn)),
            patch(
                "transaction_routes._serialize_transaction",
                side_effect=lambda value: {
                    "_id": value.id,
                    "agent_side": value.agent_side,
                    "participants": [
                        {"user_id": participant.user_id, "role": participant.role.value}
                        for participant in value.participants
                    ],
                },
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.put(
                    "/api/transactions/txn-123",
                    json={"agent_role": "buying_agent"},
                )

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["agent_side"] == "buyer"
            assert payload["participants"][0]["role"] == "SELLER"
        finally:
            app.dependency_overrides.clear()

    async def test_set_dotloop_loop_conflict_reports_same_owner_transfer_allowed(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        existing = DummyTransaction(None)
        existing.id = "txn-existing"
        existing.dotloop_loop_id = "321"
        existing.created_by = "user-1"

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_owned_transaction", AsyncMock(return_value=txn)),
            patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=existing)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.patch(
                    "/api/transactions/txn-123/dotloop-loop",
                    json={"loop_id": "321"},
                )

        try:
            assert response.status_code == 409
            detail = response.json()["detail"]
            assert detail["existing_transaction_id"] == "txn-existing"
            assert detail["transfer_allowed"] is True
        finally:
            app.dependency_overrides.clear()

    async def test_set_dotloop_loop_conflict_reports_cross_owner_transfer_blocked(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        existing = DummyTransaction(None)
        existing.id = "txn-other"
        existing.dotloop_loop_id = "321"
        existing.created_by = "user-2"

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_owned_transaction", AsyncMock(return_value=txn)),
            patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=existing)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.patch(
                    "/api/transactions/txn-123/dotloop-loop",
                    json={"loop_id": "321"},
                )

        try:
            assert response.status_code == 409
            detail = response.json()["detail"]
            assert detail["existing_transaction_id"] == "txn-other"
            assert detail["transfer_allowed"] is False
        finally:
            app.dependency_overrides.clear()

    async def test_set_dotloop_loop_force_transfer_moves_link_and_resets_sync_state(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.dotloop_loop_id = "123"
        txn.dotloop_sync_status = "error"
        txn.dotloop_last_synced_at = datetime.now(timezone.utc)
        txn.dotloop_last_remote_updated_at = datetime.now(timezone.utc)
        txn.dotloop_sync_error = "Old failure"

        existing = DummyTransaction(None)
        existing.id = "txn-existing"
        existing.dotloop_loop_id = "321"
        existing.dotloop_sync_status = "current"
        existing.dotloop_last_synced_at = datetime.now(timezone.utc)
        existing.dotloop_last_remote_updated_at = datetime.now(timezone.utc)
        existing.dotloop_sync_error = "Needs review"
        existing.created_by = "user-1"

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_owned_transaction", AsyncMock(return_value=txn)),
            patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=existing)),
            patch(
                "transaction_routes._serialize_transaction",
                side_effect=lambda value: {
                    "_id": value.id,
                    "dotloop_loop_id": value.dotloop_loop_id,
                    "dotloop_sync_status": value.dotloop_sync_status,
                    "dotloop_sync_error": value.dotloop_sync_error,
                },
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.patch(
                    "/api/transactions/txn-123/dotloop-loop",
                    json={"loop_id": "321", "force_transfer": True},
                )

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["dotloop_loop_id"] == "321"
            assert payload["dotloop_sync_status"] == "never"
            assert payload["dotloop_sync_error"] is None

            assert existing.dotloop_loop_id is None
            assert existing.dotloop_sync_status == "never"
            assert existing.dotloop_last_synced_at is None
            assert existing.dotloop_last_remote_updated_at is None
            assert existing.dotloop_sync_error is None
            existing.save.assert_awaited_once()

            assert txn.dotloop_loop_id == "321"
            assert txn.dotloop_sync_status == "never"
            assert txn.dotloop_last_synced_at is None
            assert txn.dotloop_last_remote_updated_at is None
            assert txn.dotloop_sync_error is None
            txn.save.assert_awaited_once()
        finally:
            app.dependency_overrides.clear()

    async def test_set_dotloop_loop_force_transfer_rejected_for_cross_owner(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        existing = DummyTransaction(None)
        existing.id = "txn-other"
        existing.dotloop_loop_id = "321"
        existing.created_by = "user-2"

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_owned_transaction", AsyncMock(return_value=txn)),
            patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=existing)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.patch(
                    "/api/transactions/txn-123/dotloop-loop",
                    json={"loop_id": "321", "force_transfer": True},
                )

        try:
            assert response.status_code == 409
            detail = response.json()["detail"]
            assert detail["existing_transaction_id"] == "txn-other"
            assert detail["transfer_allowed"] is False
            existing.save.assert_not_awaited()
            txn.save.assert_not_awaited()
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

    async def test_transaction_upload_start_creates_job_and_launches_background_task(self, tmp_path):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        user = MagicMock(id="user-1", org_id="org-1")

        created_task = MagicMock(task_id="task-123", metadata={}, _asyncio_task=None)

        async def assign_job_id(job):
            job.id = "job-123"

        def schedule_and_close(coro):
            coro.close()
            return MagicMock()

        app.dependency_overrides[get_current_user] = lambda: user
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
            patch("transaction_routes._TXN_DOCS_DIR", str(tmp_path)),
            patch("transaction_routes.TransactionUploadJob.get_settings", return_value=MagicMock(pymongo_collection=MagicMock())),
            patch("transaction_routes.TransactionUploadJob.insert", new=assign_job_id),
            patch("transaction_routes.TransactionUploadJob.save", new=AsyncMock()),
            patch("task_manager.create_task", return_value=created_task) as create_task_mock,
            patch("server._run_extraction_task", new=AsyncMock()),
            patch("transaction_routes.asyncio.create_task", side_effect=schedule_and_close) as schedule_mock,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/transactions/txn-123/documents/upload-and-extract",
                    files={"file": ("offer.pdf", b"%PDF-1.4 sample", "application/pdf")},
                )

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["id"] == "job-123"
            assert payload["task_id"] == "task-123"
            assert payload["original_filename"] == "offer.pdf"
            assert payload["status"] == "pending"
            create_task_mock.assert_called_once()
            create_args = create_task_mock.call_args
            assert create_args.args[0] == "real_estate"
            assert create_args.kwargs["metadata"]["transaction_id"] == "txn-123"
            assert create_args.kwargs["metadata"]["upload_job_id"] == "job-123"
            assert create_args.kwargs["metadata"]["display_filename"] == "offer.pdf"
            assert create_args.kwargs["metadata"]["auto_link"] is True
            schedule_mock.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    async def test_list_transaction_upload_jobs_returns_live_task_snapshot(self):
        from auth import get_current_user
        from db import TransactionUploadJob, TransactionUploadStep
        from server import app

        txn = DummyTransaction(None)
        job = TransactionUploadJob.model_construct(
            transaction_id="txn-123",
            uploaded_by="user-1",
            original_filename="offer.pdf",
            stored_filename="stored_offer.pdf",
            file_path="/tmp/stored_offer.pdf",
            file_hash="abc123",
            task_id="task-123",
            steps=[TransactionUploadStep(key="upload", title="Upload document", status="complete")],
        )
        job.id = "job-123"

        task = MagicMock(
            task_id="task-123",
            completed_at=None,
            events=[
                {"type": "step", "data": {"step": 1, "total": 7, "title": "Convert to Images"}},
                {"type": "step_complete", "data": {"step": 1, "title": "Convert to Images"}},
            ],
        )

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
            patch("transaction_routes.TransactionUploadJob.find", return_value=FakeCursor([job])),
            patch("task_manager.get_task", return_value=task),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/transactions/txn-123/upload-jobs")

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["jobs"][0]["id"] == "job-123"
            assert payload["jobs"][0]["status"] == "running"
            assert payload["jobs"][0]["current_step"] == 1
            assert payload["jobs"][0]["progress_message"] == "Convert to Images"
            assert payload["jobs"][0]["steps"][-1]["title"] == "Convert to Images"
            assert payload["jobs"][0]["steps"][-1]["status"] == "complete"
        finally:
            app.dependency_overrides.clear()

    async def test_post_extraction_attachment_uses_requested_doc_type_for_attached_offer_docs(self):
        from db import DocumentRecord, ExtractionRecord, TransactionUploadJob
        from transaction_routes import _apply_post_extraction_attachment_state

        txn = DummyTransaction(None)
        upload_job = TransactionUploadJob.model_construct(
            transaction_id="txn-123",
            uploaded_by="user-1",
            original_filename="Escalation Addendum.pdf",
            stored_filename="stored_escalation.pdf",
            file_path="/tmp/stored_escalation.pdf",
            file_hash="hash-123",
            task_id="task-123",
            offer_extraction_id="root-doc:0",
            requested_doc_type="escalation_addendum",
        )

        extraction = ExtractionRecord.model_construct(
            mode="real_estate",
            document_type="ADDENDUM",
            document_title="Escalation Addendum",
            support_level="partial",
            overall_confidence=0.9,
            pages_processed=1,
            created_at=datetime.now(timezone.utc),
        )
        doc_record = DocumentRecord.model_construct(
            id="child-doc",
            filename="Escalation Addendum.pdf",
            mode="real_estate",
            page_count=1,
            extractions=[extraction],
            source="upload",
            file_hash="hash-123",
        )

        with (
            patch("transaction_routes.DocumentRecord.get", AsyncMock(return_value=doc_record)),
            patch("transaction_routes.TransactionUploadJob.save", new=AsyncMock()),
            patch("transaction_routes._ensure_transaction_document_link", AsyncMock()) as ensure_link_mock,
        ):
            await _apply_post_extraction_attachment_state(
                txn,
                upload_job=upload_job,
                extraction_id="child-doc:0",
            )

        ensure_link_mock.assert_awaited_once()
        assert ensure_link_mock.call_args.kwargs["doc_type"] == "escalation_addendum"
        assert ensure_link_mock.call_args.kwargs["offer_extraction_id"] == "root-doc:0"
        assert upload_job.attachment_state == "attached"
        assert upload_job.document_type == "ADDENDUM"

    async def test_list_active_transaction_upload_jobs_only_returns_incomplete_jobs(self):
        from auth import get_current_user
        from db import TransactionUploadJob
        from server import app

        active_job = TransactionUploadJob.model_construct(
            transaction_id="txn-123",
            uploaded_by="user-1",
            original_filename="offer.pdf",
            stored_filename="stored_offer.pdf",
            file_path="/tmp/stored_offer.pdf",
            file_hash="abc123",
        )
        active_job.id = "job-123"
        active_job.status = TransactionUploadJobStatus.PENDING

        txn = DummyTransaction(None)
        txn.id = "txn-123"

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes.TransactionUploadJob.find", return_value=FakeCursor([active_job])),
            patch("transaction_routes.Transaction.find", return_value=FakeCursor([txn])),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/transactions/upload-jobs/active")

        try:
            assert response.status_code == 200
            payload = response.json()
            assert len(payload["jobs"]) == 1
            assert payload["jobs"][0]["id"] == "job-123"
            assert payload["jobs"][0]["transaction_name"] == txn.name
        finally:
            app.dependency_overrides.clear()

    async def test_list_transaction_extractions_includes_classification_metadata(self):
        from auth import get_current_user
        from db import DocumentRecord, ExtractionRecord
        from server import app

        txn = DummyTransaction(None)
        txn.extraction_ids = ["doc-123"]
        extraction = ExtractionRecord.model_construct(
            mode="real_estate",
            overall_confidence=0.94,
            pages_processed=3,
            created_at=datetime.now(timezone.utc),
            document_type="COUNTEROFFER",
            document_form_id="MAR_COUNTER_OFFER",
            document_title="Counter Offer",
            document_revision="April 2022",
            support_level="full",
        )
        doc_record = DocumentRecord.model_construct(
            id="doc-123",
            filename="counter_offer.pdf",
            mode="real_estate",
            page_count=3,
            extractions=[extraction],
        )

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
            patch("transaction_routes.DocumentRecord.get", AsyncMock(return_value=doc_record)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/transactions/txn-123/extractions")

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["extractions"][0]["document_type"] == "COUNTEROFFER"
            assert payload["extractions"][0]["document_form_id"] == "MAR_COUNTER_OFFER"
            assert payload["extractions"][0]["document_title"] == "Counter Offer"
            assert payload["extractions"][0]["document_revision"] == "April 2022"
            assert payload["extractions"][0]["support_level"] == "full"
        finally:
            app.dependency_overrides.clear()

    async def test_get_offer_workspace_groups_root_offers_and_loose_extractions(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.extraction_ids = ["root-doc", "child-doc", "loose-doc"]

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
            patch(
                "transaction_routes.build_offer_workspace",
                AsyncMock(
                    return_value={
                        "offers": [
                            {
                                "extraction_id": "root-doc:0",
                                "document_id": "root-doc",
                                "summary": {
                                    "id": "root-doc",
                                    "filename": "offer.pdf",
                                    "mode": "real_estate",
                                    "overall_confidence": 0.9,
                                    "pages_processed": 2,
                                    "created_at": None,
                                    "document_type": "PURCHASE_OFFER",
                                    "document_title": "Buy-Sell Agreement",
                                    "document_revision": "April 2022",
                                    "support_level": "full",
                                },
                                "fields": {},
                                "raw_extras": {},
                                "field_citations": {},
                                "field_citation_meta": {},
                                "overridden_fields": [],
                                "attached_extractions": [
                                    {
                                        "id": "child-doc",
                                        "filename": "counter.pdf",
                                        "mode": "real_estate",
                                        "overall_confidence": 0.8,
                                        "pages_processed": 1,
                                        "created_at": None,
                                        "document_type": "COUNTEROFFER",
                                        "document_title": "Counter Offer",
                                        "document_revision": None,
                                        "support_level": "partial",
                                        "attached_at": None,
                                    }
                                ],
                                "supporting_documents": [],
                            }
                        ],
                        "loose_extractions": [
                            {
                                "id": "loose-doc",
                                "filename": "inspection.pdf",
                                "mode": "real_estate",
                                "overall_confidence": 0.5,
                                "pages_processed": 1,
                                "created_at": None,
                                "document_type": "INSPECTION_NOTICE",
                                "document_title": "Inspection Notice",
                                "document_revision": None,
                                "support_level": "partial",
                            }
                        ],
                        "loose_documents": [],
                        "root_offer_ids": ["root-doc:0"],
                        "attachment_candidates": [{"extraction_id": "root-doc:0", "label": "Buy-Sell Agreement"}],
                    }
                ),
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/transactions/txn-123/offer-workspace")

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["root_offer_ids"] == ["root-doc:0"]
            assert payload["offers"][0]["summary"]["document_type"] == "PURCHASE_OFFER"
            assert payload["offers"][0]["attached_extractions"][0]["document_type"] == "COUNTEROFFER"
            assert payload["loose_extractions"][0]["id"] == "loose-doc"
        finally:
            app.dependency_overrides.clear()

    async def test_attach_extracted_document_to_offer_creates_attachment_link(self):
        from auth import get_current_user
        from db import DocumentRecord, ExtractionRecord
        from server import app

        txn = DummyTransaction(None)
        txn.extraction_ids = ["child-doc", "root-doc"]
        extraction = ExtractionRecord.model_construct(
            mode="real_estate",
            document_type="COUNTEROFFER",
            overall_confidence=0.8,
            pages_processed=1,
            created_at=datetime.now(timezone.utc),
        )
        doc_record = DocumentRecord.model_construct(
            id="child-doc",
            filename="counter.pdf",
            mode="real_estate",
            page_count=1,
            extractions=[extraction],
            source="upload",
            file_hash="hash-123",
        )

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
            patch("transaction_routes.DocumentRecord.get", AsyncMock(return_value=doc_record)),
            patch(
                "transaction_routes.build_offer_workspace",
                AsyncMock(return_value={"root_offer_ids": ["root-doc:0"]}),
            ),
            patch("transaction_routes._ensure_transaction_document_link", AsyncMock()) as ensure_link_mock,
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/transactions/txn-123/offer-attachments",
                    json={"document_record_id": "child-doc", "offer_extraction_id": "root-doc:0"},
                )

        try:
            assert response.status_code == 200
            assert response.json() == {"attached": True}
            ensure_link_mock.assert_awaited_once()
            assert ensure_link_mock.call_args.kwargs["offer_extraction_id"] == "root-doc:0"
            assert ensure_link_mock.call_args.kwargs["attachment_role"] == "extracted_offer_doc"
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

    async def test_preview_transaction_from_dotloop_defaults_ambiguous_loop_to_listing_agent(self):
        from auth import get_current_user
        from server import app

        loop_detail = {
            "id": 555,
            "name": "Unknown Loop",
            "transaction_type": "",
            "participants": [],
            "documents": [],
        }

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1", dotloop_tokens=None)
        with (
            patch("transaction_routes.dotloop_configured", return_value=True),
            patch("transaction_routes.get_loop_with_details", return_value=loop_detail),
            patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=None)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/transactions/from-dotloop/555/preview")

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["normalized_transaction"]["agent_role"] == "listing_agent"
            assert payload["normalized_transaction"]["agent_side"] == "seller"
        finally:
            app.dependency_overrides.clear()

    async def test_preview_transaction_from_dotloop_infers_buying_agent_for_purchase_offer(self):
        from auth import get_current_user
        from server import app

        loop_detail = {
            "id": 556,
            "name": "Purchase Offer",
            "transaction_type": "purchase offer",
            "participants": [],
            "documents": [],
        }

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1", dotloop_tokens=None)
        with (
            patch("transaction_routes.dotloop_configured", return_value=True),
            patch("transaction_routes.get_loop_with_details", return_value=loop_detail),
            patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=None)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/transactions/from-dotloop/556/preview")

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["normalized_transaction"]["agent_role"] == "buying_agent"
            assert payload["normalized_transaction"]["agent_side"] == "buyer"
        finally:
            app.dependency_overrides.clear()

    async def test_create_transaction_from_dotloop_uses_selected_agent_role(self):
        from auth import get_current_user
        from server import app

        loop_detail = {
            "id": 777,
            "name": "Offer Loop",
            "transaction_type": "purchase offer",
            "participants": [],
            "documents": [],
        }

        app.dependency_overrides[get_current_user] = lambda: MagicMock(
            id="user-1",
            dotloop_tokens=None,
            org_id=None,
        )
        mock_settings = MagicMock()
        mock_settings.motor_collection = MagicMock()
        with (
            patch("transaction_routes.dotloop_configured", return_value=True),
            patch("transaction_routes.get_loop_with_details", return_value=loop_detail),
            patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=None)),
            patch("transaction_routes.Transaction.get_settings", return_value=mock_settings),
            patch("transaction_routes.Transaction.insert", AsyncMock()),
            patch(
                "transaction_routes._serialize_transaction",
                side_effect=lambda value: {
                    "_id": str(value.id),
                    "agent_side": value.agent_side,
                    "participants": [
                        {"user_id": participant.user_id, "role": participant.role.value}
                        for participant in value.participants
                    ],
                },
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/transactions/from-dotloop/777",
                    json={"agent_role": "listing_agent"},
                )

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload["agent_side"] == "seller"
            assert payload["participants"][0]["role"] == "LISTING_AGENT"
        finally:
            app.dependency_overrides.clear()

    async def test_create_transaction_from_dotloop_does_not_auto_add_loop_participants(self):
        from auth import get_current_user
        from server import app

        loop_detail = {
            "id": 778,
            "name": "Offer Loop",
            "transaction_type": "purchase offer",
            "participants": [
                {
                    "full_name": "Buyer One",
                    "email": "buyer@example.com",
                    "role": "BUYER",
                },
                {
                    "full_name": "Seller One",
                    "email": "seller@example.com",
                    "role": "SELLER",
                },
            ],
            "documents": [],
        }

        app.dependency_overrides[get_current_user] = lambda: MagicMock(
            id="user-1",
            dotloop_tokens=None,
            org_id=None,
        )
        mock_settings = MagicMock()
        mock_settings.motor_collection = MagicMock()
        with (
            patch("transaction_routes.dotloop_configured", return_value=True),
            patch("transaction_routes.get_loop_with_details", return_value=loop_detail),
            patch("transaction_routes.Transaction.find_one", AsyncMock(return_value=None)),
            patch("transaction_routes.Transaction.get_settings", return_value=mock_settings),
            patch("transaction_routes.Transaction.insert", AsyncMock()),
            patch(
                "transaction_routes._serialize_transaction",
                side_effect=lambda value: {
                    "_id": str(value.id),
                    "participants": [
                        {"user_id": participant.user_id, "role": participant.role.value}
                        for participant in value.participants
                    ],
                },
            ),
            patch("transaction_routes.UserProfile.find_one", AsyncMock()),
            patch("transaction_routes.UserProfile.insert", AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/transactions/from-dotloop/778",
                    json={"agent_role": "listing_agent"},
                )

        try:
            assert response.status_code == 200
            payload = response.json()
            assert len(payload["participants"]) == 1
            assert payload["participants"][0]["user_id"] == "user-1"
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

    async def test_import_dotloop_documents_uses_connected_user_profile_id(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.dotloop_loop_id = "321"

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with (
            patch("transaction_routes._get_transaction_for_user", AsyncMock(return_value=txn)),
            patch("transaction_routes.dotloop_configured", return_value=True),
            patch("transaction_routes.resolve_dotloop_profile_id", return_value=77),
            patch(
                "transaction_routes._import_dotloop_document",
                AsyncMock(
                    return_value={
                        "local_document_id": "doc-1",
                        "extraction_id": "doc-1:0",
                        "filename": "BuySell.pdf",
                        "duplicate": False,
                        "linked_existing": False,
                    }
                ),
            ) as import_mock,
            patch("transaction_routes._mark_transaction_dotloop_state", AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/transactions/txn-123/dotloop/import-documents",
                    json={
                        "documents": [
                            {"folder_id": 11, "document_id": 22, "name": "BuySell.pdf"},
                        ]
                    },
                )

        try:
            assert response.status_code == 200
            import_mock.assert_awaited_once()
            assert import_mock.await_args.kwargs["profile_id"] == 77
            assert response.json()["imported"] == 1
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Issue 13: Transaction ownership enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTransactionOwnershipEnforcement:
    """Verify that transactions are isolated per user and ownership rules are enforced."""

    async def test_list_transactions_user_isolation(self):
        """GET /api/transactions — user_b does not see user_a's transaction."""
        from auth import get_current_user
        from server import app

        txn_a = DummyTransaction(None)
        txn_a.id = "txn-user-a"
        txn_a.created_by = "user-a"
        txn_a.participants = []

        # The DB query returns user_a's transaction; the route then filters by creator/participant.
        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-b")
        with patch(
            "transaction_routes.Transaction.find",
            return_value=FakeCursor([txn_a]),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/transactions")

        try:
            assert response.status_code == 200
            # user_b is neither creator nor participant — list must be empty
            assert response.json() == []
        finally:
            app.dependency_overrides.clear()

    async def test_delete_transaction_not_owner(self):
        """DELETE /api/transactions/{id} — non-owner gets 403."""
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.created_by = "user-a"

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-b")
        with patch("transaction_routes.Transaction.get", AsyncMock(return_value=txn)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.delete("/api/transactions/txn-123")

        try:
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()

    async def test_delete_transaction_non_draft_blocked(self):
        """DELETE /api/transactions/{id} — owner cannot delete an ACTIVE transaction."""
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.created_by = "user-1"
        txn.status = TransactionStatus.ACTIVE

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-1")
        with patch("transaction_routes.Transaction.get", AsyncMock(return_value=txn)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.delete("/api/transactions/txn-123")

        try:
            assert response.status_code == 400
            assert "draft" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    async def test_create_transaction_visible_only_to_creator(self):
        """GET /api/transactions/{id} — non-participant user_b gets 403."""
        from auth import get_current_user
        from server import app

        txn = DummyTransaction(None)
        txn.id = "txn-private"
        txn.created_by = "user-a"
        txn.participants = []

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id="user-b")
        with patch("transaction_routes.Transaction.get", AsyncMock(return_value=txn)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/transactions/txn-private")

        try:
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()
