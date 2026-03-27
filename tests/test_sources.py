"""Tests for source ingestion modules (NewsAPI, GDELT, RSS)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.sources.newsapi import DEFAULT_QUERIES, fetch_newsapi
from app.sources.gdelt import fetch_gdelt
from app.sources.rss import _parse_feed, fetch_rss


# ============================================================
# NewsAPI
# ============================================================


@pytest.mark.asyncio
async def test_newsapi_returns_empty_without_key():
    result = await fetch_newsapi(api_key="")
    assert result == []


@pytest.mark.asyncio
async def test_newsapi_parses_articles():
    mock_response = httpx.Response(
        200,
        json={
            "articles": [
                {
                    "url": "https://example.com/1",
                    "title": "AI Breakthrough",
                    "description": "Major advance in LLMs",
                    "publishedAt": "2026-03-26T10:00:00Z",
                },
                {
                    "url": "https://example.com/2",
                    "title": "Chip Exports",
                    "description": "New sanctions",
                    "publishedAt": "2026-03-26T11:00:00Z",
                },
            ]
        },
        request=httpx.Request("GET", "https://newsapi.org"),
    )

    with patch("app.sources.newsapi.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_newsapi(queries=["test query"], api_key="fake-key")

    assert len(result) == 2
    assert result[0].title == "AI Breakthrough"
    assert result[0].source == "newsapi"
    assert result[0].published_at is not None
    assert result[0].published_at.tzinfo is not None


@pytest.mark.asyncio
async def test_newsapi_handles_missing_fields():
    mock_response = httpx.Response(
        200,
        json={
            "articles": [
                {
                    "url": "https://example.com/1",
                    "title": "Bare Minimum",
                    # no description, no publishedAt
                },
            ]
        },
        request=httpx.Request("GET", "https://newsapi.org"),
    )

    with patch("app.sources.newsapi.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_newsapi(queries=["test"], api_key="fake-key")

    assert len(result) == 1
    assert result[0].description == ""
    assert result[0].published_at is None


@pytest.mark.asyncio
async def test_newsapi_survives_http_error():
    with patch("app.sources.newsapi.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=httpx.Request("GET", "https://newsapi.org"),
                response=httpx.Response(500),
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_newsapi(queries=["test"], api_key="fake-key")

    assert result == []


@pytest.mark.asyncio
async def test_newsapi_uses_default_queries_when_none():
    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={"articles": []},
            request=httpx.Request("GET", "https://newsapi.org"),
        )

    with patch("app.sources.newsapi.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await fetch_newsapi(queries=None, api_key="fake-key")

    assert call_count == len(DEFAULT_QUERIES)


# ============================================================
# GDELT
# ============================================================


@pytest.mark.asyncio
async def test_gdelt_parses_articles():
    mock_response = httpx.Response(
        200,
        json={
            "articles": [
                {
                    "url": "https://gdelt.example.com/1",
                    "title": "NATO Summit",
                    "seendate": "20260326T100000Z",
                },
            ]
        },
        request=httpx.Request("GET", "https://api.gdeltproject.org"),
    )

    with patch("app.sources.gdelt.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_gdelt(queries=["NATO"])

    assert len(result) == 1
    assert result[0].title == "NATO Summit"
    assert result[0].source == "gdelt"
    assert result[0].published_at == datetime(2026, 3, 26, 10, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_gdelt_handles_bad_date():
    mock_response = httpx.Response(
        200,
        json={
            "articles": [
                {
                    "url": "https://gdelt.example.com/1",
                    "title": "Bad Date",
                    "seendate": "not-a-date",
                },
            ]
        },
        request=httpx.Request("GET", "https://api.gdeltproject.org"),
    )

    with patch("app.sources.gdelt.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_gdelt(queries=["test"])

    assert len(result) == 1
    assert result[0].published_at is None


@pytest.mark.asyncio
async def test_gdelt_survives_http_error():
    with patch("app.sources.gdelt.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "500", request=httpx.Request("GET", "https://api.gdeltproject.org"),
                response=httpx.Response(500),
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await fetch_gdelt(queries=["test"])

    assert result == []


# ============================================================
# RSS
# ============================================================


def test_parse_feed_returns_stories():
    mock_entry = MagicMock()
    mock_entry.get = lambda key, default="": {
        "link": "https://rss.example.com/1",
        "title": "RSS Story",
        "summary": "RSS description",
    }.get(key, default)
    mock_entry.published = "Thu, 26 Mar 2026 10:00:00 GMT"

    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]

    with patch("app.sources.rss.feedparser.parse", return_value=mock_feed):
        stories = _parse_feed("Test Feed", "https://example.com/rss")

    assert len(stories) == 1
    assert stories[0].title == "RSS Story"
    assert stories[0].source == "rss"


def test_parse_feed_handles_no_date():
    mock_entry = MagicMock(spec=[])  # no 'published' attribute
    mock_entry.get = lambda key, default="": {
        "link": "https://rss.example.com/1",
        "title": "No Date Story",
        "summary": "",
    }.get(key, default)

    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]

    with patch("app.sources.rss.feedparser.parse", return_value=mock_feed):
        stories = _parse_feed("Test Feed", "https://example.com/rss")

    assert len(stories) == 1
    assert stories[0].published_at is None


def test_parse_feed_limits_to_10_entries():
    mock_entries = []
    for i in range(20):
        entry = MagicMock(spec=[])
        entry.get = lambda key, default="", i=i: {
            "link": f"https://example.com/{i}",
            "title": f"Story {i}",
            "summary": "",
        }.get(key, default)
        mock_entries.append(entry)

    mock_feed = MagicMock()
    mock_feed.entries = mock_entries

    with patch("app.sources.rss.feedparser.parse", return_value=mock_feed):
        stories = _parse_feed("Test Feed", "https://example.com/rss")

    assert len(stories) == 10


def test_parse_feed_survives_exception():
    with patch("app.sources.rss.feedparser.parse", side_effect=Exception("parse boom")):
        stories = _parse_feed("Bad Feed", "https://broken.com/rss")

    assert stories == []


@pytest.mark.asyncio
async def test_fetch_rss_returns_empty_for_missing_config():
    result = await fetch_rss(feeds_path="/nonexistent/feeds.yaml")
    assert result == []


@pytest.mark.asyncio
async def test_fetch_rss_loads_feeds_from_yaml(tmp_path):
    feeds_yaml = tmp_path / "feeds.yaml"
    feeds_yaml.write_text(
        "feeds:\n"
        "  - name: Test Feed\n"
        "    url: https://example.com/rss\n"
    )

    mock_entry = MagicMock(spec=[])
    mock_entry.get = lambda key, default="": {
        "link": "https://example.com/1",
        "title": "YAML Story",
        "summary": "From YAML",
    }.get(key, default)

    mock_feed = MagicMock()
    mock_feed.entries = [mock_entry]

    with patch("app.sources.rss.feedparser.parse", return_value=mock_feed):
        stories = await fetch_rss(feeds_path=str(feeds_yaml))

    assert len(stories) == 1
    assert stories[0].title == "YAML Story"


@pytest.mark.asyncio
async def test_fetch_rss_returns_empty_for_no_feeds(tmp_path):
    feeds_yaml = tmp_path / "feeds.yaml"
    feeds_yaml.write_text("feeds: []\n")

    result = await fetch_rss(feeds_path=str(feeds_yaml))
    assert result == []
