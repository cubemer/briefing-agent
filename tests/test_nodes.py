from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.nodes import (
    BriefingState,
    completeness_check_node,
    ingest_node,
    memory_filter_node,
    route_completeness,
    score_filter_node,
    store_deliver_node,
    summarize_node,
    synthesize_node,
)
from app.models import BriefOutput, Story, StoryBullet


def _make_story(title: str = "Test Story", url: str = "https://example.com") -> Story:
    return Story(
        url=url,
        title=title,
        source="test",
        published_at=datetime.now(timezone.utc),
        description=f"Description for {title}",
    )


def _make_state(**overrides) -> BriefingState:
    base: BriefingState = {
        "stories": [],
        "filtered_stories": [],
        "summaries": [],
        "synthesis": "",
        "final_brief": "",
        "retry_count": 0,
        "expanded_queries": [],
        "errors": [],
        "route": "",
    }
    base.update(overrides)
    return base


# --- Ingest node ---


@pytest.mark.asyncio
async def test_ingest_deduplicates():
    story_a = _make_story("Same Title", "https://a.com")
    story_b = _make_story("Same Title", "https://a.com")  # same hash
    story_c = _make_story("Different", "https://b.com")

    with (
        patch("app.agent.nodes.fetch_newsapi", new_callable=AsyncMock, return_value=[story_a]),
        patch("app.agent.nodes.fetch_gdelt", new_callable=AsyncMock, return_value=[story_b]),
        patch("app.agent.nodes.fetch_rss", new_callable=AsyncMock, return_value=[story_c]),
    ):
        result = await ingest_node(_make_state())

    assert len(result["stories"]) == 2
    hashes = {s.content_hash for s in result["stories"]}
    assert len(hashes) == 2


@pytest.mark.asyncio
async def test_ingest_handles_source_failure():
    with (
        patch("app.agent.nodes.fetch_newsapi", new_callable=AsyncMock, side_effect=Exception("boom")),
        patch("app.agent.nodes.fetch_gdelt", new_callable=AsyncMock, side_effect=Exception("boom")),
        patch("app.agent.nodes.fetch_rss", new_callable=AsyncMock, side_effect=Exception("boom")),
    ):
        result = await ingest_node(_make_state())

    assert result["stories"] == []
    assert len(result["errors"]) > 0


# --- Memory filter node ---


@pytest.mark.asyncio
async def test_memory_filter_drops_seen():
    stories = [_make_story("Novel"), _make_story("Seen")]

    mock_memory = MagicMock()
    mock_memory.filter_seen = AsyncMock(return_value=[stories[0]])

    with patch("app.agent.nodes.BriefMemory", return_value=mock_memory):
        result = await memory_filter_node(_make_state(stories=stories))

    assert len(result["filtered_stories"]) == 1
    assert result["filtered_stories"][0].title == "Novel"


@pytest.mark.asyncio
async def test_memory_filter_passes_all_on_error():
    stories = [_make_story("A"), _make_story("B")]

    with patch("app.agent.nodes.BriefMemory", side_effect=Exception("pinecone down")):
        result = await memory_filter_node(_make_state(stories=stories))

    assert len(result["filtered_stories"]) == 2


# --- Score filter node ---


@pytest.mark.asyncio
async def test_score_filter_ranks_correctly():
    stories = [_make_story("Low"), _make_story("High")]

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(content=json.dumps({"topic_scores": {"ai_ml": 0.2}, "relevance_score": 0.2})),
            MagicMock(content=json.dumps({"topic_scores": {"ai_ml": 0.9}, "relevance_score": 0.9})),
        ]
    )

    with patch("app.agent.nodes._get_haiku", return_value=mock_llm):
        result = await score_filter_node(_make_state(filtered_stories=stories))

    # Only the high-scoring story should pass the threshold
    assert len(result["filtered_stories"]) == 1
    assert result["filtered_stories"][0].relevance_score == 0.9


# --- Completeness check ---


@pytest.mark.asyncio
async def test_completeness_routes_retry():
    stories = [_make_story("Only one")]
    stories[0].topic_scores = {"ai_ml": 0.8}

    result = await completeness_check_node(
        _make_state(filtered_stories=stories, retry_count=0)
    )

    assert result["route"] == "retry"
    assert result["retry_count"] == 1


@pytest.mark.asyncio
async def test_completeness_routes_continue():
    stories = []
    for i, (title, topics) in enumerate([
        ("Geopolitics story", {"geopolitics": 0.9}),
        ("AI story", {"ai_ml": 0.8}),
        ("Embedded story", {"embedded": 0.7}),
    ]):
        s = _make_story(title, f"https://example.com/{i}")
        s.topic_scores = topics
        stories.append(s)

    result = await completeness_check_node(
        _make_state(filtered_stories=stories, retry_count=0)
    )

    assert result["route"] == "continue"


@pytest.mark.asyncio
async def test_completeness_max_retries():
    result = await completeness_check_node(
        _make_state(filtered_stories=[_make_story()], retry_count=2)
    )
    assert result["route"] == "continue"


def test_route_completeness():
    assert route_completeness(_make_state(route="retry")) == "retry"
    assert route_completeness(_make_state(route="continue")) == "continue"


# --- Summarize node ---


@pytest.mark.asyncio
async def test_summarize_node():
    story = _make_story("Big AI News")
    story.topic_scores = {"ai_ml": 0.9}

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(
            content=json.dumps({"headline": "AI Breakthrough", "context": "Major advance in LLMs"})
        )
    )

    with patch("app.agent.nodes._get_haiku", return_value=mock_llm):
        result = await summarize_node(_make_state(filtered_stories=[story]))

    assert len(result["summaries"]) == 1
    assert result["summaries"][0].headline == "AI Breakthrough"


# --- Synthesize node ---


@pytest.mark.asyncio
async def test_synthesize_node():
    bullet = StoryBullet(headline="AI News", context="It happened", url="https://x.com", topic="ai_ml")

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(content="AI is advancing rapidly today.")
    )

    with patch("app.agent.nodes._get_sonnet", return_value=mock_llm):
        result = await synthesize_node(_make_state(summaries=[bullet]))

    assert "AI" in result["synthesis"]


# --- Store & deliver node ---


@pytest.mark.asyncio
async def test_store_deliver_sends_brief():
    bullet = StoryBullet(headline="News", context="Context", url="https://x.com", topic="ai_ml")

    mock_memory = MagicMock()
    mock_memory.store_brief = AsyncMock()
    mock_memory.store_stories = AsyncMock()
    mock_memory.cleanup_old = AsyncMock()

    with (
        patch("app.agent.nodes.BriefMemory", return_value=mock_memory),
        patch("app.agent.nodes.send_brief", new_callable=AsyncMock, return_value=True) as mock_send,
    ):
        result = await store_deliver_node(
            _make_state(summaries=[bullet], synthesis="TL;DR", filtered_stories=[])
        )

    assert result["final_brief"]
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_store_deliver_alerts_on_empty():
    with patch("app.agent.nodes.send_failure_alert", new_callable=AsyncMock) as mock_alert:
        result = await store_deliver_node(_make_state())

    mock_alert.assert_called_once()
    assert not result["final_brief"]


# --- BriefOutput format ---


def test_brief_output_format():
    brief = BriefOutput(
        date="2026-03-26",
        synthesis="AI and geopolitics dominate today.",
        bullets=[
            StoryBullet(headline="AI Bill", context="New regulation", url="https://a.com", topic="ai_ml"),
            StoryBullet(headline="NATO Move", context="Alliance shift", url="https://b.com", topic="geopolitics"),
        ],
    )
    formatted = brief.format()

    assert "🌅 BRIEF — 2026-03-26" in formatted
    assert "AI and geopolitics" in formatted
    assert "• AI Bill — New regulation → https://a.com" in formatted
    assert "• NATO Move — Alliance shift → https://b.com" in formatted
