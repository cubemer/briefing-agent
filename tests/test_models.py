"""Tests for Pydantic models."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import BriefOutput, Story, StoryBullet, TOPIC_WEIGHTS


# ============================================================
# Story
# ============================================================


def test_story_content_hash_deterministic():
    s1 = Story(url="https://example.com/1", title="Test", source="newsapi")
    s2 = Story(url="https://example.com/1", title="Test", source="newsapi")
    assert s1.content_hash == s2.content_hash


def test_story_content_hash_case_insensitive_title():
    s1 = Story(url="https://example.com/1", title="Test Story", source="newsapi")
    s2 = Story(url="https://example.com/1", title="test story", source="newsapi")
    assert s1.content_hash == s2.content_hash


def test_story_content_hash_strips_whitespace():
    s1 = Story(url="https://example.com/1", title="Test", source="newsapi")
    s2 = Story(url="https://example.com/1", title="  Test  ", source="newsapi")
    assert s1.content_hash == s2.content_hash


def test_story_content_hash_differs_for_different_urls():
    s1 = Story(url="https://example.com/1", title="Same Title", source="newsapi")
    s2 = Story(url="https://example.com/2", title="Same Title", source="newsapi")
    assert s1.content_hash != s2.content_hash


def test_story_content_hash_differs_for_different_titles():
    s1 = Story(url="https://example.com/1", title="Title A", source="newsapi")
    s2 = Story(url="https://example.com/1", title="Title B", source="newsapi")
    assert s1.content_hash != s2.content_hash


def test_story_defaults():
    s = Story(url="https://example.com", title="Test", source="rss")
    assert s.published_at is None
    assert s.description == ""
    assert s.topic_scores == {}
    assert s.relevance_score == 0.0


def test_story_with_all_fields():
    now = datetime.now(timezone.utc)
    s = Story(
        url="https://example.com",
        title="Full Story",
        source="gdelt",
        published_at=now,
        description="A description",
        topic_scores={"ai_ml": 0.9, "geopolitics": 0.3},
        relevance_score=0.85,
    )
    assert s.published_at == now
    assert s.topic_scores["ai_ml"] == 0.9


# ============================================================
# StoryBullet
# ============================================================


def test_story_bullet_defaults():
    b = StoryBullet(headline="News", context="Context", url="https://x.com")
    assert b.topic == ""


def test_story_bullet_with_topic():
    b = StoryBullet(headline="AI News", context="LLMs", url="https://x.com", topic="ai_ml")
    assert b.topic == "ai_ml"


# ============================================================
# BriefOutput
# ============================================================


def test_brief_output_format_header():
    brief = BriefOutput(
        date="2026-03-26",
        synthesis="Big day for AI.",
        bullets=[],
    )
    formatted = brief.format()
    assert formatted.startswith("🌅 BRIEF — 2026-03-26")
    assert "Big day for AI." in formatted


def test_brief_output_format_bullets():
    brief = BriefOutput(
        date="2026-03-26",
        synthesis="Summary",
        bullets=[
            StoryBullet(headline="H1", context="C1", url="https://a.com"),
            StoryBullet(headline="H2", context="C2", url="https://b.com"),
        ],
    )
    formatted = brief.format()
    assert "• H1 — C1 → https://a.com" in formatted
    assert "• H2 — C2 → https://b.com" in formatted


def test_brief_output_format_separator():
    brief = BriefOutput(
        date="2026-03-26",
        synthesis="Summary",
        bullets=[StoryBullet(headline="H", context="C", url="https://x.com")],
    )
    formatted = brief.format()
    assert "---" in formatted


def test_brief_output_format_empty_bullets():
    brief = BriefOutput(date="2026-03-26", synthesis="Nothing today.", bullets=[])
    formatted = brief.format()
    assert "🌅 BRIEF" in formatted
    assert "Nothing today." in formatted
    # Should not have any bullet lines
    assert "•" not in formatted


# ============================================================
# TOPIC_WEIGHTS
# ============================================================


def test_topic_weights_has_all_categories():
    expected = {"geopolitics", "ai_ml", "embedded", "graphics", "space", "crypto"}
    assert set(TOPIC_WEIGHTS.keys()) == expected


def test_high_weight_topics():
    for topic in ("geopolitics", "ai_ml", "embedded"):
        assert TOPIC_WEIGHTS[topic] == 1.0


def test_medium_weight_topics():
    for topic in ("graphics", "space"):
        assert TOPIC_WEIGHTS[topic] == 0.6


def test_low_weight_topics():
    assert TOPIC_WEIGHTS["crypto"] == 0.3
