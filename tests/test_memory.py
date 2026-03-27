"""Tests for Pinecone memory module."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models import Story


# We need to patch settings before importing BriefMemory
@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.memory.pinecone.settings") as mock_s:
        mock_s.pinecone_api_key = "fake-key"
        mock_s.pinecone_index_name = "test-index"
        mock_s.similarity_threshold = 0.85
        mock_s.memory_ttl_days = 7
        yield mock_s


def _make_story(title="Test", url="https://example.com"):
    return Story(url=url, title=title, source="test", description=f"Desc for {title}")


def _mock_embed_result(vectors):
    """Create a mock embedding result."""
    result = MagicMock()
    result.data = [MagicMock(values=v) for v in vectors]
    return result


# ============================================================
# BriefMemory.__init__
# ============================================================


def test_memory_uses_provided_pinecone_client():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_pc.Index.return_value = MagicMock()

    memory = BriefMemory(pc=mock_pc)

    mock_pc.Index.assert_called_once_with("test-index")


def test_memory_creates_default_client_without_arg():
    from app.memory.pinecone import BriefMemory

    with patch("app.memory.pinecone.Pinecone") as mock_pc_cls:
        mock_pc = MagicMock()
        mock_pc.Index.return_value = MagicMock()
        mock_pc_cls.return_value = mock_pc

        memory = BriefMemory()

    mock_pc_cls.assert_called_once_with(api_key="fake-key")


# ============================================================
# filter_seen
# ============================================================


@pytest.mark.asyncio
async def test_filter_seen_keeps_novel_stories():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index

    # Pinecone returns low similarity (novel)
    mock_index.query.return_value = MagicMock(
        matches=[MagicMock(score=0.3)]
    )
    mock_pc.inference.embed.return_value = _mock_embed_result([[0.1] * 10])

    memory = BriefMemory(pc=mock_pc)
    stories = [_make_story("Novel Story")]
    result = await memory.filter_seen(stories)

    assert len(result) == 1
    assert result[0].title == "Novel Story"


@pytest.mark.asyncio
async def test_filter_seen_drops_similar_stories():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index

    # Pinecone returns high similarity (seen)
    mock_index.query.return_value = MagicMock(
        matches=[MagicMock(score=0.95)]
    )
    mock_pc.inference.embed.return_value = _mock_embed_result([[0.1] * 10])

    memory = BriefMemory(pc=mock_pc)
    stories = [_make_story("Seen Story")]
    result = await memory.filter_seen(stories)

    assert len(result) == 0


@pytest.mark.asyncio
async def test_filter_seen_returns_empty_for_empty_input():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_pc.Index.return_value = MagicMock()

    memory = BriefMemory(pc=mock_pc)
    result = await memory.filter_seen([])

    assert result == []


@pytest.mark.asyncio
async def test_filter_seen_includes_on_error():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index

    # Pinecone query fails
    mock_pc.inference.embed.side_effect = Exception("Pinecone down")

    memory = BriefMemory(pc=mock_pc)
    stories = [_make_story("Error Story")]
    result = await memory.filter_seen(stories)

    # Should include the story on error (err on side of inclusion)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_filter_seen_no_matches_means_novel():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index

    # No matches at all (empty index)
    mock_index.query.return_value = MagicMock(matches=[])
    mock_pc.inference.embed.return_value = _mock_embed_result([[0.1] * 10])

    memory = BriefMemory(pc=mock_pc)
    stories = [_make_story("Brand New")]
    result = await memory.filter_seen(stories)

    assert len(result) == 1


# ============================================================
# store_brief
# ============================================================


@pytest.mark.asyncio
async def test_store_brief_upserts_to_pinecone():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index
    mock_pc.inference.embed.return_value = _mock_embed_result([[0.1] * 10])

    memory = BriefMemory(pc=mock_pc)
    await memory.store_brief("Test brief text", ["https://a.com", "https://b.com"])

    mock_index.upsert.assert_called_once()
    vectors = mock_index.upsert.call_args.kwargs.get("vectors") or mock_index.upsert.call_args[1].get("vectors")
    assert len(vectors) == 1
    assert vectors[0]["metadata"]["type"] == "brief"
    assert "https://a.com" in vectors[0]["metadata"]["urls"]


@pytest.mark.asyncio
async def test_store_brief_survives_error():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index
    mock_pc.inference.embed.side_effect = Exception("embed failed")

    memory = BriefMemory(pc=mock_pc)
    # Should not raise
    await memory.store_brief("Test", [])


# ============================================================
# store_stories
# ============================================================


@pytest.mark.asyncio
async def test_store_stories_upserts_batch():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index
    mock_pc.inference.embed.return_value = _mock_embed_result([[0.1] * 10, [0.2] * 10])

    memory = BriefMemory(pc=mock_pc)
    stories = [_make_story("A", "https://a.com"), _make_story("B", "https://b.com")]
    await memory.store_stories(stories)

    mock_index.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_store_stories_skips_empty():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index

    memory = BriefMemory(pc=mock_pc)
    await memory.store_stories([])

    mock_index.upsert.assert_not_called()


# ============================================================
# cleanup_old
# ============================================================


@pytest.mark.asyncio
async def test_cleanup_old_deletes_by_timestamp():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index

    memory = BriefMemory(pc=mock_pc)
    await memory.cleanup_old(days=7)

    mock_index.delete.assert_called_once()
    filter_arg = mock_index.delete.call_args.kwargs.get("filter") or mock_index.delete.call_args[1].get("filter")
    cutoff = filter_arg["timestamp"]["$lt"]
    expected_cutoff = int(time.time()) - (7 * 86400)
    # Allow 5 seconds tolerance
    assert abs(cutoff - expected_cutoff) < 5


@pytest.mark.asyncio
async def test_cleanup_old_survives_error():
    from app.memory.pinecone import BriefMemory

    mock_pc = MagicMock()
    mock_index = MagicMock()
    mock_pc.Index.return_value = mock_index
    mock_index.delete.side_effect = Exception("delete failed")

    memory = BriefMemory(pc=mock_pc)
    # Should not raise
    await memory.cleanup_old()
