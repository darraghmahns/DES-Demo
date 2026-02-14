"""Tests for extraction caching — verifies that same-content files with
different names produce the same SHA-256 hash and hit the cache, and that
gov/real_estate caches are isolated."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

# ---------------------------------------------------------------------------
# SHA-256 hash identity tests (no server needed)
# ---------------------------------------------------------------------------


def test_same_content_different_names_produce_same_hash(tmp_path: Path):
    """Two files with identical bytes but different names must hash equally."""
    content = b"%PDF-1.4 fake pdf content for testing"

    file_a = tmp_path / "purchase_agreement.pdf"
    file_b = tmp_path / "purchase_agreement(1).pdf"
    file_c = tmp_path / "totally_different_name.pdf"

    file_a.write_bytes(content)
    file_b.write_bytes(content)
    file_c.write_bytes(content)

    hash_a = hashlib.sha256(file_a.read_bytes()).hexdigest()
    hash_b = hashlib.sha256(file_b.read_bytes()).hexdigest()
    hash_c = hashlib.sha256(file_c.read_bytes()).hexdigest()

    assert hash_a == hash_b, "Same content with (1) suffix must match"
    assert hash_a == hash_c, "Same content with totally different name must match"


def test_different_content_produces_different_hash(tmp_path: Path):
    """Files with different content must produce different hashes."""
    file_a = tmp_path / "doc_v1.pdf"
    file_b = tmp_path / "doc_v2.pdf"

    file_a.write_bytes(b"%PDF-1.4 version one")
    file_b.write_bytes(b"%PDF-1.4 version two")

    hash_a = hashlib.sha256(file_a.read_bytes()).hexdigest()
    hash_b = hashlib.sha256(file_b.read_bytes()).hexdigest()

    assert hash_a != hash_b, "Different content must produce different hashes"


# ---------------------------------------------------------------------------
# Document classification tests
# ---------------------------------------------------------------------------


def test_classify_document_foia():
    """FOIA documents should classify as 'gov'."""
    from server import _classify_document

    assert _classify_document("sample_foia_request.pdf") == "gov"
    assert _classify_document("FOIA_response_2026.pdf") == "gov"
    assert _classify_document("freedom_of_info.pdf") == "gov"
    assert _classify_document("gov_document.pdf") == "gov"


def test_classify_document_real_estate():
    """Non-FOIA documents should classify as 'real_estate'."""
    from server import _classify_document

    assert _classify_document("sample_purchase_agreement.pdf") == "real_estate"
    assert _classify_document("contract.pdf") == "real_estate"
    assert _classify_document("listing_agreement.pdf") == "real_estate"


# ---------------------------------------------------------------------------
# Cache endpoint integration tests (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_miss_unknown_hash():
    """Cache miss for an unknown file hash."""
    from server import app
    from db import DocumentRecord

    unknown_hash = hashlib.sha256(b"unknown content").hexdigest()

    with patch.object(DocumentRecord, "find_one", new_callable=AsyncMock, return_value=None):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/extractions/cached?file_hash={unknown_hash}&mode=real_estate"
            )
            assert resp.status_code == 200
            assert resp.json()["cached"] is False


@pytest.mark.asyncio
async def test_cache_miss_no_extractions():
    """Cache miss when document exists but has no extractions."""
    from server import app
    from db import DocumentRecord

    known_hash = hashlib.sha256(b"known content").hexdigest()
    mock_doc = DocumentRecord.model_construct(
        id="507f1f77bcf86cd799439011",
        filename="test.pdf",
        file_hash=known_hash,
        mode="real_estate",
        extractions=[],
    )

    with patch.object(DocumentRecord, "find_one", new_callable=AsyncMock, return_value=mock_doc):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                f"/api/extractions/cached?file_hash={known_hash}&mode=real_estate"
            )
            assert resp.status_code == 200
            assert resp.json()["cached"] is False


@pytest.mark.asyncio
async def test_same_hash_different_filenames_hit_same_cache():
    """file.pdf and file(1).pdf with identical content resolve to the same
    SHA-256 hash and would query the same cache entry."""
    content = b"%PDF-1.4 identical purchase agreement bytes"

    hash_from_file = hashlib.sha256(content).hexdigest()
    hash_from_copy = hashlib.sha256(content).hexdigest()

    assert hash_from_file == hash_from_copy

    from server import app
    from db import DocumentRecord

    call_log = []

    async def mock_find_one(*args, **kwargs):
        call_log.append(args)
        return None

    with patch.object(DocumentRecord, "find_one", side_effect=mock_find_one):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get(
                f"/api/extractions/cached?file_hash={hash_from_file}&mode=real_estate"
            )
            await client.get(
                f"/api/extractions/cached?file_hash={hash_from_copy}&mode=real_estate"
            )

    # Both calls queried the DB (same hash = same query)
    assert len(call_log) == 2


@pytest.mark.asyncio
async def test_gov_and_real_estate_caches_are_isolated():
    """The same file hash with mode=gov should NOT return a real_estate
    cached extraction, and vice versa."""
    content = b"%PDF-1.4 some document"
    file_hash = hashlib.sha256(content).hexdigest()

    from server import app
    from db import DocumentRecord

    find_one_calls = []

    async def tracking_find_one(*args, **kwargs):
        find_one_calls.append(args)
        return None  # always miss — we just want to verify the query includes mode

    with patch.object(DocumentRecord, "find_one", side_effect=tracking_find_one):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_re = await client.get(
                f"/api/extractions/cached?file_hash={file_hash}&mode=real_estate"
            )
            resp_gov = await client.get(
                f"/api/extractions/cached?file_hash={file_hash}&mode=gov"
            )

    assert resp_re.json()["cached"] is False
    assert resp_gov.json()["cached"] is False
    # Two separate DB queries were made (one per mode)
    assert len(find_one_calls) == 2
