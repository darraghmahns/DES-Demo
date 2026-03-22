from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self):
        return self._docs


@pytest.mark.asyncio
async def test_get_extractions_uses_canonical_and_legacy_ids():
    from server import get_extractions

    user = SimpleNamespace(id="user-doc-1", clerk_user_id="clerk-1", org_id=None)

    with patch("db_writer.list_extractions", new_callable=AsyncMock, return_value=[]) as mock_list:
        response = await get_extractions(mode="real_estate", limit=25, user=user)

    assert response == {"extractions": []}
    mock_list.assert_awaited_once_with(
        mode="real_estate",
        limit=25,
        user_id="user-doc-1",
        org_id=None,
        legacy_user_ids=["clerk-1"],
    )


def test_can_access_document_accepts_canonical_legacy_and_unowned_docs():
    from server import _can_access_document

    user = SimpleNamespace(id="user-doc-1", clerk_user_id="clerk-1", org_id=None)

    assert _can_access_document(SimpleNamespace(user_id="user-doc-1", org_id=None), user=user)
    assert _can_access_document(SimpleNamespace(user_id="clerk-1", org_id=None), user=user)
    assert _can_access_document(SimpleNamespace(user_id=None, org_id=None), user=user)
    assert not _can_access_document(SimpleNamespace(user_id="someone-else", org_id=None), user=user)


@pytest.mark.asyncio
async def test_list_extractions_builds_compatibility_filter():
    from db_writer import list_extractions
    from db import DocumentRecord

    captured: dict = {}

    def fake_find(filters):
        captured["filters"] = filters
        return _FakeQuery([])

    with (
        patch.object(DocumentRecord, "find", side_effect=fake_find),
        patch.object(DocumentRecord, "uploaded_at", 1, create=True),
    ):
        results = await list_extractions(
            mode="real_estate",
            limit=10,
            user_id="user-doc-1",
            legacy_user_ids=["clerk-1"],
        )

    assert results == []
    assert captured["filters"]["mode"] == "real_estate"
    assert captured["filters"]["$or"] == [
        {"user_id": "user-doc-1"},
        {"user_id": "clerk-1"},
        {"user_id": None},
    ]
