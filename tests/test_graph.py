"""Tests for the LangGraph pipeline wiring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.graph import briefing_graph
from app.models import Story, StoryBullet


def _make_story(title="Test", url="https://example.com", topic_scores=None):
    s = Story(url=url, title=title, source="test", description=f"Desc for {title}")
    if topic_scores:
        s.topic_scores = topic_scores
        s.relevance_score = max(topic_scores.values())
    return s


def _initial_state():
    return {
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


def test_graph_compiles():
    """Graph should compile without errors."""
    assert briefing_graph is not None


def test_graph_has_all_nodes():
    """Graph should have all 7 pipeline nodes."""
    graph = briefing_graph.get_graph()
    node_names = {node.name for node in graph.nodes.values() if node.name not in ("__start__", "__end__")}
    expected = {"ingest", "memory_filter", "score_filter", "completeness_check", "summarize", "synthesize", "store_deliver"}
    assert expected == node_names


@pytest.mark.asyncio
async def test_full_pipeline_smoke():
    """End-to-end smoke test with all external calls mocked."""
    stories = [
        _make_story("Geopolitics News", "https://a.com", {"geopolitics": 0.9}),
        _make_story("AI Breakthrough", "https://b.com", {"ai_ml": 0.95}),
        _make_story("RISC-V Update", "https://c.com", {"embedded": 0.8}),
    ]

    # Mock all external dependencies
    mock_haiku = AsyncMock()
    mock_sonnet = AsyncMock()

    # Score responses
    score_responses = [
        MagicMock(content=json.dumps({"topic_scores": s.topic_scores, "relevance_score": s.relevance_score}))
        for s in stories
    ]
    # Summarize responses
    summarize_responses = [
        MagicMock(content=json.dumps({"headline": s.title, "context": f"About {s.title}"}))
        for s in stories
    ]
    mock_haiku.ainvoke = AsyncMock(side_effect=score_responses + summarize_responses)
    mock_sonnet.ainvoke = AsyncMock(
        return_value=MagicMock(content="Big moves in geopolitics and AI today.")
    )

    mock_memory = MagicMock()
    mock_memory.filter_seen = AsyncMock(return_value=stories)
    mock_memory.store_brief = AsyncMock()
    mock_memory.store_stories = AsyncMock()
    mock_memory.cleanup_old = AsyncMock()

    with (
        patch("app.agent.nodes.fetch_newsapi", new_callable=AsyncMock, return_value=stories),
        patch("app.agent.nodes.fetch_gdelt", new_callable=AsyncMock, return_value=[]),
        patch("app.agent.nodes.fetch_rss", new_callable=AsyncMock, return_value=[]),
        patch("app.agent.nodes.BriefMemory", return_value=mock_memory),
        patch("app.agent.nodes._get_haiku", return_value=mock_haiku),
        patch("app.agent.nodes._get_sonnet", return_value=mock_sonnet),
        patch("app.agent.nodes.send_brief", new_callable=AsyncMock, return_value=True),
    ):
        result = await briefing_graph.ainvoke(_initial_state())

    assert result["final_brief"]
    assert "BRIEF" in result["final_brief"]
    assert len(result["summaries"]) == 3
    assert result["synthesis"]


@pytest.mark.asyncio
async def test_pipeline_completeness_retry():
    """Pipeline should retry ingest when completeness check fails."""
    # First ingest: only 1 story, not enough coverage
    first_story = _make_story("Lone Story", "https://a.com")

    # Second ingest: enough stories after retry
    retry_stories = [
        _make_story("Geo", "https://b.com", {"geopolitics": 0.9}),
        _make_story("AI", "https://c.com", {"ai_ml": 0.8}),
        _make_story("Embedded", "https://d.com", {"embedded": 0.7}),
    ]

    ingest_call_count = 0

    async def mock_newsapi(*args, **kwargs):
        nonlocal ingest_call_count
        ingest_call_count += 1
        if ingest_call_count == 1:
            return [first_story]
        return retry_stories

    mock_haiku = AsyncMock()

    # First call: score the lone story low
    # Then completeness generates queries
    # Then: score retry stories high
    # Then: summarize
    score_first = MagicMock(content=json.dumps({"topic_scores": {"ai_ml": 0.5}, "relevance_score": 0.5}))
    completeness_resp = MagicMock(content=json.dumps({"suggested_queries": ["geopolitics", "embedded systems"]}))
    score_retry = [
        MagicMock(content=json.dumps({"topic_scores": s.topic_scores, "relevance_score": max(s.topic_scores.values())}))
        for s in retry_stories
    ]
    summarize_resps = [
        MagicMock(content=json.dumps({"headline": s.title, "context": "ctx"}))
        for s in retry_stories
    ]

    mock_haiku.ainvoke = AsyncMock(
        side_effect=[score_first, completeness_resp] + score_retry + summarize_resps
    )

    mock_sonnet = AsyncMock()
    mock_sonnet.ainvoke = AsyncMock(return_value=MagicMock(content="Synthesis."))

    mock_memory = MagicMock()
    mock_memory.filter_seen = AsyncMock(side_effect=lambda stories: stories)
    mock_memory.store_brief = AsyncMock()
    mock_memory.store_stories = AsyncMock()
    mock_memory.cleanup_old = AsyncMock()

    with (
        patch("app.agent.nodes.fetch_newsapi", new_callable=AsyncMock, side_effect=mock_newsapi),
        patch("app.agent.nodes.fetch_gdelt", new_callable=AsyncMock, return_value=[]),
        patch("app.agent.nodes.fetch_rss", new_callable=AsyncMock, return_value=[]),
        patch("app.agent.nodes.BriefMemory", return_value=mock_memory),
        patch("app.agent.nodes._get_haiku", return_value=mock_haiku),
        patch("app.agent.nodes._get_sonnet", return_value=mock_sonnet),
        patch("app.agent.nodes.send_brief", new_callable=AsyncMock, return_value=True),
    ):
        result = await briefing_graph.ainvoke(_initial_state())

    # Should have retried at least once
    assert ingest_call_count >= 2
    assert result["final_brief"]


@pytest.mark.asyncio
async def test_pipeline_empty_sources_sends_failure():
    """If all sources return nothing, failure alert should fire."""
    mock_memory = MagicMock()
    mock_memory.filter_seen = AsyncMock(return_value=[])

    with (
        patch("app.agent.nodes.fetch_newsapi", new_callable=AsyncMock, return_value=[]),
        patch("app.agent.nodes.fetch_gdelt", new_callable=AsyncMock, return_value=[]),
        patch("app.agent.nodes.fetch_rss", new_callable=AsyncMock, return_value=[]),
        patch("app.agent.nodes.BriefMemory", return_value=mock_memory),
        patch("app.agent.nodes.send_failure_alert", new_callable=AsyncMock) as mock_alert,
        patch("app.agent.nodes._get_haiku", return_value=AsyncMock(ainvoke=AsyncMock(return_value=MagicMock(content='{"suggested_queries":["test"]}')))),
    ):
        result = await briefing_graph.ainvoke(_initial_state())

    mock_alert.assert_called()
    assert result["final_brief"] == ""
