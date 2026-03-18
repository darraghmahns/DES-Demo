from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from httpx import ASGITransport, AsyncClient

from schemas import InvitationStatus, ParticipantRole, ParticipantStatus


class DummyInvitation:
    def __init__(self, *, invitation_id: str, email: str, transaction_id: str, role: ParticipantRole):
        self.id = invitation_id
        self.transaction_id = transaction_id
        self.invitee_user_id = 'user-2'
        self.email = email
        self.name = 'Buyer Name'
        self.role = role
        self.created_by = 'owner-1'
        self.token_hash = None
        self.signed_token = None
        self.status = InvitationStatus.CREATED
        self.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        self.sent_at = None
        self.opened_at = None
        self.accepted_at = None
        self.revoked_at = None
        self.provider = None
        self.provider_message_id = None
        self.last_error = None
        self.updated_at = datetime.now(timezone.utc)
        self.save = AsyncMock()
        self.insert = AsyncMock()


class DummyTransaction:
    def __init__(self):
        self.id = 'txn-1'
        self.name = '123 Main Street'
        self.created_by = 'owner-1'
        self.participants = [MagicMock(user_id='user-2', role=ParticipantRole.BUYER, status=ParticipantStatus.INVITED)]
        self.updated_at = datetime.now(timezone.utc)
        self.save = AsyncMock()


class DummyUser:
    def __init__(self, user_id: str, email: str, name: str):
        self.id = user_id
        self.email = email
        self.name = name
        self.has_clerk_account = False
        self.last_login = None
        self.save = AsyncMock()


@pytest.mark.asyncio
class TestInvitationRoutes:
    async def test_create_invitation_returns_manual_link_when_delivery_not_configured(self):
        from auth import get_current_user
        from server import app

        txn = DummyTransaction()
        invitee = DummyUser('user-2', 'buyer@example.com', 'Buyer Name')

        def fake_find(*_args, **_kwargs):
            chain = MagicMock()
            chain.sort.return_value.first_or_none = AsyncMock(return_value=None)
            return chain

        async def fake_prepare(invitation, **_kwargs):
            invitation.id = ObjectId("507f1f77bcf86cd799439012")
            invitation.signed_token = 'signed-token'
            invitation.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            invitation.status = InvitationStatus.CREATED

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id='owner-1')
        with (
            patch('invitation_routes._load_transaction_for_owner', AsyncMock(return_value=txn)),
            patch('invitation_routes.UserProfile.find_one', AsyncMock(return_value=invitee)),
            patch('invitation_routes._ensure_transaction_participant', AsyncMock()),
            patch('invitation_routes.TransactionInvitation.find', side_effect=fake_find),
            patch('invitation_routes.TransactionInvitation.get_settings', return_value=MagicMock(pymongo_collection=MagicMock())),
            patch('invitation_routes.TransactionInvitation.save', new=AsyncMock()),
            patch('invitation_routes._prepare_invitation', AsyncMock(side_effect=fake_prepare)),
            patch('invitation_routes._deliver_invitation', AsyncMock()),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post(
                    '/api/invitations',
                    json={
                        'email': 'buyer@example.com',
                        'role': 'BUYER',
                        'transaction_id': 'txn-1',
                        'name': 'Buyer Name',
                    },
                )

        try:
            assert response.status_code == 200
            payload = response.json()
            assert payload['status'] == 'created'
            assert payload['invite_url'].endswith('/invite/signed-token')
        finally:
            app.dependency_overrides.clear()

    async def test_validate_and_accept_invitation_updates_status(self):
        from server import app
        from invitation_routes import _hash_invitation_token, _sign_invitation_token

        email = 'buyer@example.com'
        raw_token = 'raw-token'
        invitation = DummyInvitation(
            invitation_id='invite-1',
            email=email,
            transaction_id='txn-1',
            role=ParticipantRole.BUYER,
        )
        invitation.signed_token = _sign_invitation_token(raw_token, email, 'txn-1', 'invite-1')
        invitation.token_hash = _hash_invitation_token(raw_token)
        invitee = DummyUser('user-2', email, 'Buyer Name')
        txn = DummyTransaction()

        with (
            patch('invitation_routes.TransactionInvitation.get', AsyncMock(return_value=invitation)),
            patch('invitation_routes.UserProfile.get', AsyncMock(return_value=invitee)),
            patch('invitation_routes.Transaction.get', AsyncMock(return_value=txn)),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                validate_response = await client.get(f'/api/invitations/{invitation.signed_token}/validate')
                accept_response = await client.post(f'/api/invitations/{invitation.signed_token}/accept')

        assert validate_response.status_code == 200
        assert validate_response.json()['transaction']['id'] == 'txn-1'
        assert invitation.status == InvitationStatus.ACCEPTED
        assert accept_response.status_code == 200
        assert txn.participants[0].status == ParticipantStatus.ACTIVE
        assert invitee.last_login is not None

    async def test_revoke_invitation_clears_token(self):
        from auth import get_current_user
        from server import app

        invitation = DummyInvitation(
            invitation_id='invite-1',
            email='buyer@example.com',
            transaction_id='txn-1',
            role=ParticipantRole.BUYER,
        )
        invitation.signed_token = 'signed-token'
        invitation.token_hash = 'hashed-token'

        app.dependency_overrides[get_current_user] = lambda: MagicMock(id='owner-1')
        with (
            patch('invitation_routes.TransactionInvitation.get', AsyncMock(return_value=invitation)),
            patch('invitation_routes._load_transaction_for_owner', AsyncMock(return_value=DummyTransaction())),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
                response = await client.post('/api/invitations/invite-1/revoke')

        try:
            assert response.status_code == 200
            assert invitation.status == InvitationStatus.REVOKED
            assert invitation.signed_token is None
            assert invitation.token_hash is None
        finally:
            app.dependency_overrides.clear()
