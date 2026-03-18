from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from schemas import DotloopSyncStatus


class DummyTransaction:
    def __init__(self, txn_id: str):
        self.id = txn_id
        self.dotloop_loop_id = '321'
        self.dotloop_sync_status = DotloopSyncStatus.CURRENT
        self.dotloop_last_remote_updated_at = None
        self.dotloop_sync_error = 'old error'
        self.updated_at = datetime.now(timezone.utc)
        self.save = AsyncMock()


@pytest.mark.asyncio
async def test_handle_webhook_marks_linked_transactions_stale():
    from dotloop_connector import handle_webhook

    transactions = [DummyTransaction('txn-1'), DummyTransaction('txn-2')]
    query = MagicMock()
    query.to_list = AsyncMock(return_value=transactions)

    with patch('dotloop_connector.Transaction.find', return_value=query):
        result = await handle_webhook({
            'event_type': 'LOOP_UPDATED',
            'loop_id': '321',
            'profile_id': '99',
        })

    assert result['status'] == 'processed'
    assert result['marked_stale'] == 2
    for txn in transactions:
        assert txn.dotloop_sync_status == DotloopSyncStatus.STALE
        assert txn.dotloop_last_remote_updated_at is not None
        assert txn.dotloop_sync_error is None
        txn.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_ignores_other_events():
    from dotloop_connector import handle_webhook

    result = await handle_webhook({'event_type': 'LOOP_ARCHIVED', 'loop_id': '321'})
    assert result['status'] == 'ignored'


def test_resolve_profile_id_prefers_user_token_profile_id():
    from dotloop_connector import resolve_profile_id

    profile_id = resolve_profile_id(user_tokens={"access_token": "token", "profile_id": "77"})

    assert profile_id == 77


def test_resolve_profile_id_discovers_profile_id_from_connected_user():
    from dotloop_connector import resolve_profile_id

    client = MagicMock()
    client.resolve_default_profile_id.return_value = 81
    context_manager = MagicMock()
    context_manager.__enter__.return_value = client
    context_manager.__exit__.return_value = None

    user_tokens = {"access_token": "token", "refresh_token": "refresh"}

    with patch("dotloop_connector.get_dotloop_client", return_value=context_manager):
        profile_id = resolve_profile_id(user_tokens=user_tokens)

    assert profile_id == 81
    assert user_tokens["profile_id"] == 81
